# Kubernetes architecture

## Topology

One Ubuntu 26.04 or Debian 13 node runs the control plane, etcd, kubelet, containerd, and workloads. The control-plane taint is removed to allow workload scheduling.

Both platforms use containerd 2.x with configuration version 3. Ubuntu uses its distro package; Debian uses Docker's `containerd.io` package without Docker Engine. Containerd uses systemd cgroups, `io.containerd.runc.v2`, and pause image `registry.k8s.io/pause:3.10.2`. Kubeconfig is copied to an existing operator account; no account is created.

k9s is installed system-wide from the official, SHA256-verified Debian package for the host architecture. It uses the operator's existing kubeconfig; no additional credentials or cluster resources are created.

The node name defaults to the OS hostname at initialization. Set it beforehand; changing a running node's hostname is not a supported rename procedure.

## Configuration lifecycle

- `/etc/kubernetes/admin.conf` marks initialization; full `kubeadm init` bootstrap is skipped when it exists.
- `/etc/kubernetes/kubeadm-config.yaml` is rendered on every run using the installed kubeadm version.
- Non-identity changes are uploaded to the `kubeadm-config` ConfigMap, followed by static-manifest regeneration and a readiness check. Expect a brief API outage.
- All public settings are validated and saved before application. Subsequent runs reuse the full snapshot, including defaults, API address, and kubeconfig owner.
- Cluster name, Kubernetes minor version, and cluster CIDRs are immutable; conflicting overrides are rejected before facts are written. Legacy INI facts retain the same `cluster` namespace when converted to JSON.
- API server `GOGC=50` reduces GC headroom; optional `GOMEMLIMIT` requires workload-specific tuning.

## Security and networking

- The API keeps its `kubernetes_advertise_address` binding and certificates. The role loads its own `inet andreygubarev_kubernetes` nftables table before kubelet. New connections to host API/kubelet endpoints are allowed only through loopback or Flannel's `cni0` with a pod source address. Host etcd and health endpoints are local-only. External VXLAN UDP/8472 is blocked. Established and related traffic is preserved.
- The endpoint policy covers IPv4 and IPv6 without changing other host ports or `FORWARD`. It does not configure SSH, Tailscale, application ingress, or a host-wide default-deny policy. Published NodePort/hostPort traffic and pod isolation still need separate policy. Use SSH and local `kubectl` for administration.
- The `firewall` tag reconciles loaded rules, including missing or modified rules, without restarting Kubernetes. Updates replace only the role's table atomically. A dedicated systemd unit restores it on boot. The nftables loader no longer flushes independently managed tables on stop or reload.
- New clusters set kube-proxy `conntrack.maxPerCore=0`, preserving the host's `nf_conntrack_max` rather than overwriting the Ubuntu baseline. Existing clusters' kube-proxy configuration is not migrated automatically.
- Flannel provides VXLAN networking, not NetworkPolicy enforcement. It is installed only when absent; existing Flannel is not upgraded automatically.
- Optional exact-name CoreDNS rewrites provide cluster-wide split DNS without changing public URLs. The role patches only its marked block in kubeadm's existing Corefile, preserving other configuration and relying on CoreDNS reload rather than restarting Pods. Reapply after kubeadm replaces the Corefile.
- Existing Calico clusters are not migrated or cleaned up. Plan a separate migration or rebuild.
- metrics-server is pinned and reconciled on image-version drift. It uses `--kubelet-insecure-tls` for self-signed kubelet certificates; use a separate TLS hardening procedure where verified serving certificates are required.

[Configuration](../reference/configuration.md) · [Networking](../guides/customize-networking.md)
