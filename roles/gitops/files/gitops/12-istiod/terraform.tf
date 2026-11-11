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

variable "istio_version" {
  description = "Istio chart version, matching the istio-base workload."
  type        = string
  default     = "1.31.4"
}

# ---------------------------------------------------------------------------
# Kustomization
# ---------------------------------------------------------------------------

data "kustomization_overlay" "this" {
  helm_charts {
    name         = "istiod"
    repo         = "https://blob.istio.io/istio-release/charts"
    release_name = "istiod"
    namespace    = "istio-system"
    version      = var.istio_version
    skip_tests   = true

    values_inline = yamlencode({
      global = {
        proxy = {
          resources = {
            requests = {
              cpu    = "10m"
              memory = "32Mi"
            }
          }
        }
      }
      autoscaleEnabled = false
      replicaCount     = 1
      resources = {
        requests = {
          cpu    = "50m"
          memory = "128Mi"
        }
      }
      env = {
        # Gateway workloads are managed separately, not provisioned by Istiod.
        PILOT_ENABLE_GATEWAY_API_DEPLOYMENT_CONTROLLER = "false"
      }
      meshConfig = {
        enableTracing = false
        defaultConfig = {
          proxyMetadata = {
            ISTIO_META_DNS_CAPTURE = "true"
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
  manifest = data.kustomization_overlay.this.manifests[each.value]
}

resource "kustomization_resource" "p1" {
  for_each = data.kustomization_overlay.this.ids_prio[1]
  manifest = data.kustomization_overlay.this.manifests[each.value]

  depends_on = [kustomization_resource.p0]
}

resource "kustomization_resource" "p2" {
  for_each = data.kustomization_overlay.this.ids_prio[2]
  manifest = data.kustomization_overlay.this.manifests[each.value]

  depends_on = [kustomization_resource.p1]
}
