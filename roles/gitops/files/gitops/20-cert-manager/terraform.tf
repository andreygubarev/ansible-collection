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

variable "cert_manager_version" {
  description = "cert-manager chart version."
  type        = string
  default     = "v1.21.3"
}

# ---------------------------------------------------------------------------
# Kustomization
# ---------------------------------------------------------------------------

resource "kustomization_resource" "namespace" {
  manifest = jsonencode({
    apiVersion = "v1"
    kind       = "Namespace"
    metadata = {
      name = "cert-manager"
    }
  })
}

data "kustomization_overlay" "this" {
  helm_charts {
    name         = "cert-manager"
    repo         = "oci://quay.io/jetstack/charts"
    release_name = "cert-manager"
    namespace    = "cert-manager"
    version      = var.cert_manager_version
    skip_tests   = true

    values_inline = yamlencode({
      crds = {
        enabled = true
      }
      config = {
        apiVersion = "controller.config.cert-manager.io/v1alpha1"
        kind       = "ControllerConfiguration"
        gatewayAPI = {
          enabled = true
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

  depends_on = [kustomization_resource.namespace]
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
