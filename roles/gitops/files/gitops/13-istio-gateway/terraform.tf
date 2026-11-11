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
  description = "Istio gateway chart version, matching base and istiod."
  type        = string
  default     = "1.31.4"
}

variable "gateway_ports" {
  description = "Host and Service ports mapped to the gateway container. Free host port 22 before applying."
  type = list(object({
    name           = string
    port           = number
    container_port = number
  }))
  default = [
    { name = "http", port = 80, container_port = 8080 },
    { name = "https", port = 443, container_port = 8443 },
    { name = "ssh", port = 22, container_port = 2222 },
  ]
}

variable "gateway_listeners" {
  description = "Gateway listeners; HTTPS hostname and secret drive cert-manager's Gateway shim."
  type = list(object({
    name       = string
    port       = number
    protocol   = string
    hostname   = optional(string)
    tls_secret = optional(string)
  }))
}

# ---------------------------------------------------------------------------
# Kustomization
# ---------------------------------------------------------------------------

data "kustomization_overlay" "this" {
  helm_charts {
    name         = "gateway"
    repo         = "https://blob.istio.io/istio-release/charts"
    release_name = "gateway-istio"
    namespace    = "istio-system"
    version      = var.istio_version
    skip_tests   = true

    values_inline = yamlencode({
      replicaCount = 1
      autoscaling = {
        enabled = false
      }
      # A second Pod cannot bind the same host ports on this single node.
      strategy = {
        type = "Recreate"
      }
      labels = {
        "gateway.networking.k8s.io/gateway-name" = "gateway"
      }
      resources = {
        requests = {
          cpu    = "10m"
          memory = "128Mi"
        }
      }
      service = {
        type = "ClusterIP"
        ports = concat(
          [{ name = "status-port", port = 15021, targetPort = 15021 }],
          [for p in var.gateway_ports : {
            name       = p.name
            port       = p.port
            targetPort = p.container_port
          }],
        )
      }
    })
  }

  patches {
    target {
      kind = "Deployment"
      name = "gateway-istio"
    }
    patch = yamlencode({
      apiVersion = "apps/v1"
      kind       = "Deployment"
      metadata = {
        name = "gateway-istio"
      }
      spec = {
        template = {
          spec = {
            containers = [{
              name = "istio-proxy"
              ports = concat(
                [for p in var.gateway_ports : {
                  name          = p.name
                  containerPort = p.container_port
                  hostPort      = p.port
                  protocol      = "TCP"
                }],
                [{ name = "http-envoy-prom", containerPort = 15090, protocol = "TCP" }],
              )
            }]
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

resource "kustomization_resource" "gateway" {
  manifest = jsonencode({
    apiVersion = "gateway.networking.k8s.io/v1"
    kind       = "Gateway"
    metadata = {
      name      = "gateway"
      namespace = "istio-system"
      annotations = {
        "cert-manager.io/cluster-issuer" = "letsencrypt"
      }
    }
    spec = {
      gatewayClassName = "istio"
      # Istiod does not provision this Deployment/Service automatically.
      addresses = [{ type = "Hostname", value = "gateway-istio.istio-system.svc.cluster.local" }]
      listeners = [for l in var.gateway_listeners : merge(
        {
          name     = l.name
          protocol = l.protocol
          port     = l.port
          allowedRoutes = {
            namespaces = { from = "All" }
            kinds      = [{ group = "gateway.networking.k8s.io", kind = l.protocol == "TCP" ? "TCPRoute" : "HTTPRoute" }]
          }
        },
        l.hostname != null ? { hostname = l.hostname } : {},
        l.tls_secret != null ? {
          tls = {
            mode            = "Terminate"
            certificateRefs = [{ name = l.tls_secret }]
          }
        } : {},
      )]
    }
  })

  depends_on = [kustomization_resource.p2]
}
