# Kubernetes configuration

## Variables

| Variable | Initial fallback | Effect |
|---|---|---|
| `kubernetes_cluster_name` | Required once | Immutable cluster name; reused from local facts |
| `kubernetes_version` | `1.37` | Immutable minor version for the upstream APT repository |
| `kubernetes_advertise_address` | Default IPv4 address | API advertise/bind address, endpoint, certificate SAN |
| `kubernetes_pod_subnet` | `10.244.0.0/16` | Immutable pod CIDR; must match the Flannel manifest |
| `kubernetes_service_subnet` | `10.96.0.0/16` | Immutable service CIDR |
| `kubernetes_kubeconfig_user` | Ansible user | Existing account receiving `~/.kube/config`; invoking account for local execution |
| `kubernetes_apiserver_gogc` | `50` | API server Go GC target; empty string uses upstream default |
| `kubernetes_apiserver_gomemlimit` | Empty | Optional API server Go memory limit, e.g. `1536MiB` |
| `kubernetes_flannel_manifest_url` | [Flannel v0.28.10 manifest](https://github.com/flannel-io/flannel/releases/download/v0.28.10/kube-flannel.yml) | Applied only when Flannel is absent |
| `kubernetes_metrics_server_version` | `v0.9.1` | Release applied on installation or image-version drift |
| `kubernetes_k9s_version` | `0.51.0` | Exact k9s release without a `v` prefix; upstream Debian package verified with SHA256 |
| `kubernetes_coredns_rewrites` | `{}` | Mapping of exact canonical hostnames to internal DNS names; applies to cluster DNS clients |

All twelve public variables remain in [defaults/main.yml](../../../roles/kubernetes/defaults/main.yml). Precedence is **explicit Ansible input → saved settings → fallback defaults**. Values other than the rewrite mapping are strings; empty strings are allowed only for the two GC overrides. Kubernetes minor versions use `major.minor` format. An overly restrictive `GOMEMLIMIT` can cause GC thrashing.

## Persistence

The complete validated configuration, including initial API address and kubeconfig owner, is saved before application to `/etc/ansible/facts.d/kubernetes.fact`. Later runs need no repeated overrides; changed role defaults do not reset a host. Failed application retains the desired state for retry; `--check` does not write it.

The file is JSON under `cluster`, available as `ansible_facts['ansible_local']['kubernetes']['cluster']`. Existing INI identity facts are read automatically and expanded on the next valid run; supply previous custom values for other settings once when upgrading. Unknown fact keys and sections are preserved.

## `kubernetes_cluster_name`

Required on first use, without an interactive prompt. Its public default resolves the saved name or an empty, invalid first-run value. Explicit empty/non-string values or a different stored name are rejected before writing.

## Immutable identity

Cluster name, Kubernetes minor version, pod CIDR, and service CIDR are recorded on the first run and checked before mutation. Changing them requires a rebuild or a separate upgrade/migration procedure; this role provides neither.

Non-identity control-plane changes regenerate kubeadm manifests and briefly restart the API server. The configuration uses the installed kubeadm version, not a network-resolved version label. See [architecture](../concepts/architecture.md).

OS/cloud-init checks and configuration processing use `always`, including selective runs; do not skip it. Inspect the [task index](../../../roles/kubernetes/tasks/main.yml) or use `--list-tasks` / `--list-tags`.

## Internal DNS

`kubernetes_coredns_rewrites` keeps public URLs and TLS hostnames while routing cluster DNS clients internally, for example:

```yaml
kubernetes_coredns_rewrites:
  git.example.com: gateway.edge.svc.cluster.local
```

Sources and targets must be distinct lowercase DNS names without trailing dots, not IP addresses. Use an HTTPS-capable Service with a matching certificate when retaining an HTTPS URL. Public DNS is unchanged; clients must use cluster DNS, including nested job containers.

The `coredns` tag patches only a marked rewrite block in the existing kubeadm Corefile; other configuration is preserved and CoreDNS reloads it without Pod restarts. Explicitly set `{}` to remove managed rewrites; omitting the variable reuses saved settings. Reapply after a kubeadm operation that replaces the Corefile.

## Example

```yaml
kubernetes_cluster_name: my-cluster
kubernetes_advertise_address: 203.0.113.10
kubernetes_kubeconfig_user: ubuntu
```

[Quickstart](../getting-started/quickstart.md) · [Networking](../guides/customize-networking.md)
