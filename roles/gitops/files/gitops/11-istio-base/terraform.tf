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
  description = "Istio chart version, matching the istiod workload."
  type        = string
  default     = "1.31.4"
}

# ---------------------------------------------------------------------------
# Kustomization
# ---------------------------------------------------------------------------

resource "kustomization_resource" "namespace" {
  manifest = jsonencode({
    apiVersion = "v1"
    kind       = "Namespace"
    metadata = {
      name = "istio-system"
    }
  })
}

data "kustomization_overlay" "this" {
  helm_charts {
    name         = "base"
    repo         = "https://blob.istio.io/istio-release/charts"
    release_name = "istio-base"
    namespace    = "istio-system"
    version      = var.istio_version
    skip_tests   = true

    values_inline = yamlencode({
      defaultRevision = "default"
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
