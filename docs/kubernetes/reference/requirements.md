# Kubernetes requirements

- Ubuntu 26.04 or Debian 13 on amd64 or arm64; ansible-core ≥ 2.20.
- Root or sudo access; add `-K` if sudo requires a password.
- A stable IPv4 API address outside the pod/service CIDRs, and an existing kubeconfig owner account.
- Valid, non-overlapping IPv4 pod and service networks.
- `kubernetes_cluster_name` supplied on the first run.
- `community.general`, installed with the collection or by `make deps`.

The local playbook runs on the target host. For remote roles, set `ansible_user` or explicitly set `kubernetes_kubeconfig_user`.

## Network

Allow outbound access to distro APT repositories and HTTPS access to:

| Endpoint | Purpose |
|---|---|
| `pkgs.k8s.io` | Kubernetes packages |
| `download.docker.com` | Debian-only containerd 2.x packages |
| `github.com` | Flannel and metrics-server manifests |
| `registry.k8s.io` | Kubernetes images |
| `ghcr.io` | Flannel images |

The role protects its host-side Kubernetes endpoints with nftables. Remote API connections are blocked by default; use SSH and local `kubectl`. SSH, Tailscale, forwarded applications, and a host-wide default-deny firewall remain outside this policy. See [architecture](../concepts/architecture.md).

Installed packages include APT prerequisites, `containernetworking-plugins`, `nftables`, `kubeadm`, `kubectl`, and `kubelet`. Ubuntu uses distro `containerd` 2.x. Debian uses Docker's signed `containerd.io` 2.x package with an APT major-version pin; Docker Engine is not installed. Existing Debian distro `containerd` or `runc` packages are rejected before mutation, not removed automatically. Vendor package updates follow their own repository policy; adding the source does not extend unattended-upgrades' allowed origins.

[Quickstart](../getting-started/quickstart.md) · [Configuration](configuration.md)
