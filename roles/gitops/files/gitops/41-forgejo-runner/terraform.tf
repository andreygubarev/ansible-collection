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

variable "runner_version" {
  description = "Official Forgejo Runner image version."
  type        = string
  default     = "13.2.1"
}

variable "dind_version" {
  description = "Official Docker-in-Docker image version."
  type        = string
  default     = "29.9.3"
}

variable "forgejo_url" {
  type = string
}

variable "runner_uuid" {
  description = "UUID from Forgejo's instance-wide Create new runner dialog."
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = length(trimspace(var.runner_uuid)) > 0
    error_message = "Set runner_uuid in the Git-ignored terraform.tfvars.yaml after registering the runner."
  }
}

variable "runner_token" {
  description = "Runner authentication token. Hidden from plans, but stored in plaintext in local state."
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = length(trimspace(var.runner_token)) > 0
    error_message = "Set runner_token in the Git-ignored terraform.tfvars.yaml after registering the runner."
  }
}

variable "runner_labels" {
  description = "Job execution labels. The default is a Debian/Node container, not a GitHub-hosted Ubuntu VM."
  type        = list(string)
  default     = ["ubuntu-latest:docker://node:24-bookworm"]
}

# ---------------------------------------------------------------------------
# Kustomization
# ---------------------------------------------------------------------------

locals {
  runner_config = {
    log = {
      level = "info"
    }
    runner = {
      capacity         = 1
      labels           = var.runner_labels
      shutdown_timeout = "110s"
    }
    server = {
      connections = {
        forgejo = {
          url   = var.forgejo_url
          uuid  = var.runner_uuid
          token = var.runner_token
        }
      }
    }
    cache = {
      enabled    = true
      host       = "forgejo-runner.forgejo-runners.svc.cluster.local"
      port       = 8089
      proxy_port = 8088
      dir        = "/data/cache"
    }
    container = {
      privileged = false
      # This is the sidecar's socket, never the Kubernetes node's runtime socket.
      # Jobs may use this daemon to build/push images; only trusted workflows belong here.
      docker_host   = "unix:///run/docker/docker.sock"
      valid_volumes = []
    }
  }
}

resource "kustomization_resource" "namespace" {
  manifest = jsonencode({
    apiVersion = "v1"
    kind       = "Namespace"
    metadata = {
      name = "forgejo-runners"
    }
  })
}

resource "kustomization_resource" "config" {
  manifest = jsonencode({
    apiVersion = "v1"
    kind       = "Secret"
    metadata = {
      name      = "forgejo-runner-config"
      namespace = "forgejo-runners"
    }
    type = "Opaque"
    data = {
      "config.yaml" = base64encode(yamlencode(local.runner_config))
    }
  })

  depends_on = [kustomization_resource.namespace]
}

resource "kustomization_resource" "cache" {
  manifest = jsonencode({
    apiVersion = "v1"
    kind       = "Service"
    metadata = {
      name      = "forgejo-runner"
      namespace = "forgejo-runners"
    }
    spec = {
      selector = { app = "forgejo-runner" }
      ports    = [{ name = "cache", port = 8088, targetPort = 8088 }]
    }
  })

  depends_on = [kustomization_resource.namespace]
}

resource "kustomization_resource" "runner" {
  manifest = jsonencode({
    apiVersion = "apps/v1"
    kind       = "Deployment"
    metadata = {
      name      = "forgejo-runner"
      namespace = "forgejo-runners"
    }
    spec = {
      replicas = 1
      strategy = { type = "Recreate" }
      selector = { matchLabels = { app = "forgejo-runner" } }
      template = {
        metadata = {
          labels = { app = "forgejo-runner" }
          annotations = {
            "sidecar.istio.io/inject" = "false"
            # Reveal only a fingerprint, so credential changes restart the daemon.
            "checksum/config" = nonsensitive(sha256(yamlencode(local.runner_config)))
          }
        }
        spec = {
          automountServiceAccountToken  = false
          terminationGracePeriodSeconds = 120
          securityContext = {
            fsGroup = 1000
          }
          # A native sidecar starts Docker before the runner and stops it after the runner.
          initContainers = [{
            name          = "docker"
            image         = "docker:${var.dind_version}-dind"
            restartPolicy = "Always"
            args          = ["dockerd", "--host=unix:///run/docker/docker.sock", "--group=1000"]
            env = [
              { name = "DOCKER_TLS_CERTDIR", value = "" },
              { name = "DOCKER_HOST", value = "unix:///run/docker/docker.sock" },
            ]
            securityContext = {
              runAsUser  = 0
              runAsGroup = 0
              privileged = true
            }
            startupProbe = {
              exec             = { command = ["docker", "info"] }
              periodSeconds    = 2
              timeoutSeconds   = 5
              failureThreshold = 90
            }
            volumeMounts = [
              { name = "docker-socket", mountPath = "/run/docker" },
              { name = "docker-data", mountPath = "/var/lib/docker" },
            ]
            resources = {}
          }]
          containers = [{
            name       = "runner"
            image      = "data.forgejo.org/forgejo/runner:${var.runner_version}"
            command    = ["forgejo-runner"]
            args       = ["daemon", "--config", "/etc/forgejo-runner/config.yaml"]
            workingDir = "/data"
            env = [
              { name = "HOME", value = "/data" },
              { name = "DOCKER_HOST", value = "unix:///run/docker/docker.sock" },
            ]
            securityContext = {
              runAsNonRoot             = true
              runAsUser                = 1000
              runAsGroup               = 1000
              allowPrivilegeEscalation = false
            }
            ports = [{ name = "cache", containerPort = 8088 }]
            volumeMounts = [
              { name = "config", mountPath = "/etc/forgejo-runner", readOnly = true },
              { name = "docker-socket", mountPath = "/run/docker" },
              { name = "runner-data", mountPath = "/data" },
            ]
            resources = {}
          }]
          volumes = [
            { name = "config", secret = { secretName = "forgejo-runner-config", defaultMode = 288 } },
            { name = "docker-socket", emptyDir = {} },
            { name = "docker-data", emptyDir = {} },
            { name = "runner-data", emptyDir = {} },
          ]
        }
      }
    }
  })

  depends_on = [kustomization_resource.config, kustomization_resource.cache]
}
