# ---------------------------------------------------------------------------
# Terraform
# ---------------------------------------------------------------------------

terraform {
  required_version = "~> 1.12.0"

  required_providers {
    kustomization = {
      source  = "kbst/kustomization"
      version = "~> 0.9"
    }
  }
}

provider "kustomization" {
  kubeconfig_path = "~/.kube/config"
}

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

variable "forgejo_version" {
  description = "Forgejo Helm chart version, not the application version."
  type        = string
  default     = "17.3.2"
}

variable "forgejo_hostname" {
  description = "Public web/registry hostname; match the HTTPS listener in 13-istio-gateway."
  type        = string
}

variable "forgejo_ssh_hostname" {
  description = "DNS-only hostname for Git SSH, without Cloudflare proxying."
  type        = string
}

variable "admin_username" {
  type = string
}

variable "admin_email" {
  type = string
}

variable "admin_password" {
  description = "Initial admin password. Hidden from plans, but stored in plaintext in local state."
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = length(trimspace(var.admin_password)) > 0
    error_message = "Set a nonempty admin_password in the Git-ignored terraform.tfvars.yaml."
  }
}

variable "forgejo_storage_size" {
  type    = string
  default = "100Gi"
}

variable "postgres_storage_size" {
  type    = string
  default = "20Gi"
}

# ---------------------------------------------------------------------------
# Kustomization
# ---------------------------------------------------------------------------

resource "kustomization_resource" "namespace" {
  manifest = jsonencode({
    apiVersion = "v1"
    kind       = "Namespace"
    metadata = {
      name = "forgejo"
    }
  })
}

resource "kustomization_resource" "database" {
  manifest = jsonencode({
    apiVersion = "postgresql.cnpg.io/v1"
    kind       = "Cluster"
    metadata = {
      name      = "forgejo-db"
      namespace = "forgejo"
    }
    spec = {
      instances             = 1
      enableSuperuserAccess = false
      bootstrap = {
        initdb = {
          database = "forgejo"
          owner    = "forgejo"
        }
      }
      storage = {
        storageClass = "openebs-hostpath-retain"
        size         = var.postgres_storage_size
      }
    }
  })

  depends_on = [kustomization_resource.namespace]
}

resource "kustomization_resource" "admin" {
  manifest = jsonencode({
    apiVersion = "v1"
    kind       = "Secret"
    metadata = {
      name      = "forgejo-admin"
      namespace = "forgejo"
    }
    type = "Opaque"
    data = {
      username = base64encode(var.admin_username)
      password = base64encode(var.admin_password)
    }
  })

  depends_on = [kustomization_resource.namespace]
}

data "kustomization_overlay" "this" {
  helm_charts {
    name         = "forgejo"
    repo         = "oci://code.forgejo.org/forgejo-helm"
    release_name = "forgejo"
    namespace    = "forgejo"
    version      = var.forgejo_version
    skip_tests   = true

    values_inline = yamlencode({
      fullnameOverride = "forgejo"
      replicaCount     = 1
      image = {
        rootless = true
      }
      strategy = {
        type = "Recreate"
      }
      persistence = {
        enabled      = true
        create       = true
        claimName    = "forgejo-data"
        storageClass = "openebs-hostpath-retain"
        size         = var.forgejo_storage_size
        # This workload owns the PVC; backup scheduling belongs to 42-forgejo-backup.
        annotations = { "k8up.io/backup" = "true" }
        labels      = { "app.kubernetes.io/component" = "forgejo-data" }
      }
      httpRoute = {
        enabled   = true
        terminate = true
        parentRefs = [{
          name        = "gateway"
          namespace   = "istio-system"
          sectionName = "https-forgejo"
        }]
        hostnames = [var.forgejo_hostname]
        matches = {
          timeouts = {
            # Registry, LFS, and artifact uploads may take longer than an ordinary request.
            request = "0s"
          }
        }
      }
      gitea = {
        admin = {
          existingSecret = "forgejo-admin"
          email          = var.admin_email
          passwordMode   = "initialOnlyNoReset" # gitleaks:allow
        }
        additionalConfigFromEnvs = [{
          name = "FORGEJO__DATABASE__PASSWD"
          valueFrom = {
            secretKeyRef = {
              name = "forgejo-db-app"
              key  = "password"
            }
          }
        }]
        config = {
          server = {
            DOMAIN           = var.forgejo_hostname
            ROOT_URL         = "https://${var.forgejo_hostname}/"
            SSH_DOMAIN       = var.forgejo_ssh_hostname
            SSH_PORT         = 22
            SSH_LISTEN_PORT  = 2222
            START_SSH_SERVER = true
            LFS_START_SERVER = true
          }
          database = {
            DB_TYPE  = "postgres"
            HOST     = "forgejo-db-rw.forgejo.svc.cluster.local:5432"
            NAME     = "forgejo"
            USER     = "forgejo"
            SSL_MODE = "require"
          }
          service = {
            DISABLE_REGISTRATION = true
            REQUIRE_SIGNIN_VIEW  = true
          }
          mailer = {
            ENABLED = false
          }
          packages = {
            ENABLED = true
          }
          actions = {
            ENABLED = true
          }
        }
      }
    })
  }

  kustomize_options {
    enable_helm = true
    helm_path   = "/usr/local/bin/helm"
  }
}

resource "kustomization_resource" "p0" {
  for_each = data.kustomization_overlay.this.ids_prio[0]
  manifest = startswith(each.value, "_/Secret/") ? sensitive(data.kustomization_overlay.this.manifests[each.value]) : data.kustomization_overlay.this.manifests[each.value]

  depends_on = [kustomization_resource.admin, kustomization_resource.database]
}

resource "kustomization_resource" "p1" {
  for_each = data.kustomization_overlay.this.ids_prio[1]
  manifest = startswith(each.value, "_/Secret/") ? sensitive(data.kustomization_overlay.this.manifests[each.value]) : data.kustomization_overlay.this.manifests[each.value]

  depends_on = [kustomization_resource.p0]
}

resource "kustomization_resource" "p2" {
  for_each = data.kustomization_overlay.this.ids_prio[2]
  manifest = startswith(each.value, "_/Secret/") ? sensitive(data.kustomization_overlay.this.manifests[each.value]) : data.kustomization_overlay.this.manifests[each.value]

  depends_on = [kustomization_resource.p1]
}

resource "kustomization_resource" "http_redirect" {
  manifest = jsonencode({
    apiVersion = "gateway.networking.k8s.io/v1"
    kind       = "HTTPRoute"
    metadata = {
      name      = "forgejo-https-redirect"
      namespace = "forgejo"
    }
    spec = {
      parentRefs = [{ name = "gateway", namespace = "istio-system", sectionName = "http" }]
      hostnames  = [var.forgejo_hostname]
      # The solver's more specific challenge path takes precedence over this catch-all.
      rules = [{
        matches = [{ path = { type = "PathPrefix", value = "/" } }]
        filters = [{ type = "RequestRedirect", requestRedirect = { scheme = "https", statusCode = 301 } }]
      }]
    }
  })

  depends_on = [kustomization_resource.p2]
}

resource "kustomization_resource" "ssh" {
  manifest = jsonencode({
    apiVersion = "gateway.networking.k8s.io/v1"
    kind       = "TCPRoute"
    metadata = {
      name      = "forgejo-ssh"
      namespace = "forgejo"
    }
    spec = {
      parentRefs = [{ name = "gateway", namespace = "istio-system", sectionName = "ssh" }]
      rules      = [{ backendRefs = [{ name = "forgejo-ssh", port = 22 }] }]
    }
  })

  depends_on = [kustomization_resource.p2]
}
