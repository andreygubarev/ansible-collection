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

variable "k8up_version" {
  description = "K8up chart and CRD release version, not the operator image version."
  type        = string
  default     = "4.10.1"
}

variable "b2_endpoint" {
  description = "Backblaze B2 S3 endpoint; use the region of the bucket."
  type        = string
  default     = "https://s3.us-east-005.backblazeb2.com"
}

variable "b2_bucket" {
  type     = string
  nullable = false

  validation {
    condition     = length(trimspace(var.b2_bucket)) > 0
    error_message = "Set b2_bucket in terraform.tfvars.yaml."
  }
}

variable "b2_access_key_id" {
  type      = string
  sensitive = true
  nullable  = false

  validation {
    condition     = length(trimspace(var.b2_access_key_id)) > 0
    error_message = "Set b2_access_key_id in encrypted terraform.tfvars.sops.yaml."
  }
}

variable "b2_secret_access_key" {
  type      = string
  sensitive = true
  nullable  = false

  validation {
    condition     = length(trimspace(var.b2_secret_access_key)) > 0
    error_message = "Set b2_secret_access_key in encrypted terraform.tfvars.sops.yaml."
  }
}

variable "k8up_repo_password" {
  description = "Restic repository password. Hidden from plans, but stored in plaintext in local state."
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = length(trimspace(var.k8up_repo_password)) > 0
    error_message = "Set k8up_repo_password in encrypted terraform.tfvars.sops.yaml."
  }
}

# ---------------------------------------------------------------------------
# Kustomization
# ---------------------------------------------------------------------------

locals {
  credentials = {
    "access-key-id"     = var.b2_access_key_id
    "secret-access-key" = var.b2_secret_access_key
    "repo-password"    = var.k8up_repo_password
  }
  # Kustomization has no Helm lifecycle: never deploy cleanup hooks as normal Jobs/RBAC.
  helm_hooks = toset([
    for id, manifest in data.kustomization_overlay.this.manifests : id
    if contains(try(keys(yamldecode(manifest).metadata.annotations), []), "helm.sh/hook")
  ])
}

resource "kustomization_resource" "namespace" {
  manifest = jsonencode({
    apiVersion = "v1"
    kind       = "Namespace"
    metadata = {
      name = "k8up-system"
    }
  })
}

resource "kustomization_resource" "credentials" {
  manifest = jsonencode({
    apiVersion = "v1"
    kind       = "Secret"
    metadata = {
      name      = "k8up-credentials"
      namespace = "k8up-system"
    }
    type = "Opaque"
    data = { for key, value in local.credentials : key => base64encode(value) }
  })

  depends_on = [kustomization_resource.namespace]
}

# The chart does not manage CRDs; use the bundle from the same chart release.
data "kustomization_overlay" "crds" {
  resources = [
    "https://github.com/k8up-io/k8up/releases/download/k8up-${var.k8up_version}/k8up-crd.yaml",
  ]
}

resource "kustomization_resource" "crds" {
  for_each = data.kustomization_overlay.crds.ids
  manifest = data.kustomization_overlay.crds.manifests[each.value]
}

data "kustomization_overlay" "this" {
  helm_charts {
    name         = "k8up"
    repo         = "https://k8up-io.github.io/k8up"
    release_name = "k8up"
    namespace    = "k8up-system"
    version      = var.k8up_version
    skip_tests   = true

    values_inline = yamlencode({
      # Secret-backed environment variables are read only at Pod startup.
      podAnnotations = {
        "checksum/credentials" = nonsensitive(sha256(jsonencode(local.credentials)))
      }
      k8up = {
        skipWithoutAnnotation = true
        envVars = [
          {
            name  = "BACKUP_GLOBALS3ENDPOINT"
            value = var.b2_endpoint
          },
          {
            name  = "BACKUP_GLOBALS3BUCKET"
            value = var.b2_bucket
          },
          {
            name = "BACKUP_GLOBALACCESSKEYID"
            valueFrom = {
              secretKeyRef = { name = "k8up-credentials", key = "access-key-id" }
            }
          },
          {
            name = "BACKUP_GLOBALSECRETACCESSKEY"
            valueFrom = {
              secretKeyRef = { name = "k8up-credentials", key = "secret-access-key" }
            }
          },
          {
            name = "BACKUP_GLOBALREPOPASSWORD"
            valueFrom = {
              secretKeyRef = { name = "k8up-credentials", key = "repo-password" }
            }
          },
          {
            name  = "BACKUP_GLOBALSTATSURL"
            value = ""
          },
        ]
      }
    })
  }

  kustomize_options {
    enable_helm = true
    helm_path   = "/usr/local/bin/helm"
  }
}

resource "kustomization_resource" "p0" {
  for_each = setsubtract(data.kustomization_overlay.this.ids_prio[0], local.helm_hooks)
  manifest = data.kustomization_overlay.this.manifests[each.value]

  depends_on = [kustomization_resource.crds, kustomization_resource.credentials]
}

resource "kustomization_resource" "p1" {
  for_each = setsubtract(data.kustomization_overlay.this.ids_prio[1], local.helm_hooks)
  manifest = data.kustomization_overlay.this.manifests[each.value]

  depends_on = [kustomization_resource.p0]
}

resource "kustomization_resource" "p2" {
  for_each = setsubtract(data.kustomization_overlay.this.ids_prio[2], local.helm_hooks)
  manifest = data.kustomization_overlay.this.manifests[each.value]

  depends_on = [kustomization_resource.p1]
}
