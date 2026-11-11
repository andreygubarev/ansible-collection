# CHANGELOG

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/), versions follow [CalVer](https://calver.org/) (`YYYY.M.MICRO`).

## [Unreleased]

## [2026.11.3] - 2026-11-11

### Changed
- Update Metrics Server to `v0.9.1` and the GitOps OpenTofu pin to `1.12.12`.
- Update all three Istio charts to `1.31.4`, cert-manager to `v1.21.3`, K8up chart/CRDs to `4.10.1` (operator `v2.16.1`), Forgejo chart to `17.3.2`, Forgejo Runner to `13.2.1`, and Docker-in-Docker to `29.9.3`.
- Update community.general to `13.5.1`, the SHA-pinned setup-uv action to `v10.3.3`, and the curl integration-test image to `8.23.0`.

## [2026.11.2] - 2026-11-06

### Changed
- **User-local agents**: Install Pi, Claude Code, and BB under the configurable `agents_user` account, defaulting to `agent`, so applications can update without sudo. Enable BB in-app updates unless its version is pinned. Keep Node.js system-wide.

## [2026.11.1] - 2026-11-06

### Added
- **Debian 13 support**: Add an independent `debian13` container-host baseline and local playbook. Kubernetes, Terraform tooling, GitOps, and agents support both Debian 13 and Ubuntu 26.04. Debian uses the signed Docker repository for containerd 2.x; existing distro containerd/runc packages require explicit migration. Both distributions use NodeSource's signed Node.js 24 LTS package with bundled npm. The Ubuntu baseline and public settings remain unchanged.
- **Cross-platform verification**: Run all five role suites on separate fresh Ubuntu and Debian Incus VMs, including GitOps workspace creation, administrative SSH port changes, idempotence, firewall repair, and reboot persistence. `INCUS_DISTRIBUTIONS` selects either or both targets; no GitOps workloads are applied.

## [2026.11.0] - 2026-11-05

### Security
- **Kubernetes host endpoints**: Protect IPv4 and IPv6 host-side API, kubelet, etcd, health, and Flannel VXLAN ports with a role-owned nftables table. New remote API connections are blocked; use SSH and local `kubectl`. Preserve established connections, node/pod API access, cluster addresses and certificates, and unrelated host and forwarded traffic. Restore protection on boot and reconcile missing or modified rules without restarting Kubernetes.

### Fixed
- **Shared nftables lifecycle**: Remove global ruleset flushing before Ubuntu package upgrades and on service stop or reload. Preserve tables managed by Kubernetes, CNI, Tailscale, and site policy. The Kubernetes role also configures the non-destructive loader when used independently.

### Added
- **Firewall integration checks**: Verify external blocking, pod API/DNS/metrics access, IPv6, UDP, source spoofing, established sessions, DNAT and transit forwarding, legacy-loader upgrades, rule repair, repeat application, and reboot persistence in disposable Incus VMs.

## [2026.10.27] - 2026-10-23

### Fixed
- **Unprivileged Ansible execution**: Install `acl` before agents tasks switch to the `bb` account, allowing Ansible to share temporary module files securely when pipelining is unavailable. Verify the package in testinfra and disable pipelining for the agents integration play to exercise this permission path.

## [2026.10.26] - 2026-10-23

### Fixed
- **SSH client compatibility**: Use Ubuntu's OpenSSH defaults for cryptographic algorithms and minimum RSA size instead of the restrictive ssh-audit lists and RSA 3072 minimum. Restore compatibility with ECDSA and RSA 2048 user keys, ECDH key exchange, AES-CTR, and HMAC-SHA2 while retaining key-only authentication and leaving DSA/RSA-SHA1 disabled by default. Create a missing ECDSA P-256 host key on new and existing role-managed hosts without replacing existing Ed25519/RSA keys during upgrades.

## [2026.10.25] - 2026-10-23

### Changed
- **Snap preservation**: Stop purging installed snaps and their data, stopping snapd services, or blocking snapd reinstallation. Previously removed snaps and existing snapd pinning policies are not restored automatically.

### Fixed
- **Cloud-image package preservation**: Disable autoremove and narrow the explicit cleanup list to retain `ubuntu-minimal`, Ubuntu Pro, `multipath-tools`, `open-iscsi`, `networkd-dispatcher`, `software-properties-common`, its PackageKit/polkit dependencies, and `sysstat`. Avoid removing automatically installed administrative tools such as sudo. Previously removed packages are not restored automatically.

## [2026.10.24] - 2026-10-23

### Added
- **Claude Code installation**: Install Claude Code system-wide in the agents role after Pi and before BB. Follow the latest stable npm release by default or pin an exact version with `agents_claude_code_version`; leave authentication and user settings untouched. Add testinfra checks for package installation and CLI availability to the BB account without model calls.

## [2026.10.23] - 2026-10-23

### Added
- **Agents role and local playbook**: Install the newest stable Pi 1.x harness and stable BB server on Ubuntu 26.04, with exact-version overrides. BB runs as a persistent systemd user service under the dedicated `bb` account, with linger, failure recovery, private state and loopback-only access. The account intentionally has unrestricted passwordless sudo; provider authentication and remote access remain manual.
- **Pi Web Access**: Install `pi-web-access` for `bb` using Pi's package manager, preserving other packages and settings. Follow the latest stable release or pin an exact version without restarting BB on Pi/package updates. Search-provider settings and API keys remain user-managed.
- **Agents verification**: Add testinfra coverage for installation, user-service persistence, sudo access, loopback listeners and web-tool loading; include the role in collection syntax checks and the fresh-VM integration scenario.

## [2026.10.22] - 2026-10-21

### Added
- **Forgejo PVC backups**: Add `42-forgejo-backup` with a daily 03:00 UTC K8up Schedule for only `forgejo-data`, an explicit dedicated repository bucket/prefix, and inherited global endpoint/credentials. The existing Forgejo workload owns the PVC's backup annotation/selection label. Backup jobs use read-only mounts with root access for complete file coverage; no application shutdown, hooks, database backup, or snapshot pruning is configured.

## [2026.10.21] - 2026-10-20

### Added
- **K8up backup operator**: Add `32-k8up` with matching chart/CRDs `4.10.0` (operator `v2.16.0`), the `k8up-system` namespace, and global Backblaze B2/Restic settings. Credentials come from SOPS-backed Kubernetes Secret references; credential changes restart the operator. PVC selection is opt-in, Helm cleanup hooks are excluded, and no backup schedules or PVC annotations are created automatically.

### Fixed
- **GitOps input separation**: Track ordinary non-secret YAML overrides for every workload, including Forgejo and runner. Keep the administrator password and runner credentials in SOPS-encrypted inputs instead of ignoring entire ordinary override files.

## [2026.10.20] - 2026-10-20

### Fixed
- **Durable GitOps state**: Generate local backends from shared `root.hcl` with absolute per-workload paths under `~/.local/state/gitops/`, including named workspaces, rather than placing resource state in Terragrunt caches. Prepare private state directories and reject scaffold updates when legacy cached state requires migration. Existing deployments must migrate their states explicitly before clearing caches or updating the scaffold; the role does not initialize backends or migrate state automatically.

## [2026.10.19] - 2026-10-20

### Added
- **GitOps repository identity**: Require `gitops_git_user_name` and `gitops_git_user_email` before repository initialization, then save them in `.git/config`. Reuse repository-local values on later runs and allow explicit overrides without changing global Git settings. Initial baseline commits use this identity instead of a hardcoded bootstrap author.

## [2026.10.18] - 2026-10-20

### Added
- **SOPS and age tooling**: Install checksummed SOPS `3.13.3` and age `1.3.2` binaries for amd64/arm64, persisting exact version settings. Generate the selected user's private age identity only when absent, outside Git, without logging or storing it in facts.
- **Encrypted GitOps inputs**: Seed a recipient-based `.sops.yaml` policy and encrypted empty `terraform.tfvars.sops.yaml` maps only when missing. Merge decrypted values after ordinary workload inputs. Preserve existing policies, keys, ciphertext, and plaintext overrides; no secret migration or history rewrite is automatic.

## [2026.10.17] - 2026-10-20

### Added
- **Kubernetes split DNS**: Validate and persist `kubernetes_coredns_rewrites`, an optional mapping of canonical hostnames to internal DNS names. The `coredns` tag reconciles only a marked exact-name rewrite block in kubeadm's existing Corefile, preserving other settings and relying on CoreDNS reload. Empty mappings remove managed rewrites; public DNS and application URLs are unchanged.

## [2026.10.16] - 2026-10-20

### Added
- **Istio edge gateway and ACME**: Add `13-istio-gateway` with manually linked Gateway API, host ports 80/443/22, and single-node Recreate updates; add `21-letsencrypt` for HTTP-01 through its HTTP listener. The gateway annotation lets cert-manager own the origin certificate and private key. Move and verify administrative SSH before occupying port 22.
- **Forgejo and Actions**: Add `40-forgejo` with chart `17.3.1` (Forgejo `15.0.10`), rootless deployment, a 100 GiB Retain data PVC, a single-instance 20 GiB CNPG database, HTTPS/SSH routes, LFS, packages/registry, and Actions. Add `41-forgejo-runner` with official Runner `13.2.0`, Docker `29.9.1` DinD, one concurrent job, ephemeral cache/storage, and no CPU/RAM limits. Runner jobs are trusted-only, use a Pod-local Docker socket, and receive no Kubernetes API credentials automatically. Keep deployment-specific identities in host overrides and ignore credential-bearing YAML files; sensitive values remain in plaintext local state. Bootstrap is sequential with manual runner registration. No live-host changes or workload application are automated.

## [2026.10.15] - 2026-10-20

### Added
- **CloudNativePG workload**: Add `31-cnpg`, defaulting to chart `0.29.1` (operator `1.30.1`), with the `cnpg-system` namespace, CRDs, and cluster-wide reconciliation. Use local state and the current kubeconfig context; allow chart version overrides through `cnpg_version`. No PostgreSQL clusters or databases are created, and workload application remains manual.

## [2026.10.14] - 2026-10-20

### Added
- **OpenEBS workload**: Add `30-openebs`, defaulting to chart `4.6.2`, with the namespace, LocalPV Hostpath provisioner, local state, and current kubeconfig context. Make `openebs-hostpath` the default StorageClass through the chart's native setting and add `openebs-hostpath-retain` with `Retain` and `WaitForFirstConsumer`. Disable LVM, ZFS, Rawfile, Mayastor, Loki/MinIO, and Alloy. Existing default StorageClasses are not modified; review them before applying. Local volumes are not replicated or backed up; workload application remains manual.

## [2026.10.13] - 2026-10-20

### Added
- **cert-manager workload**: Add `20-cert-manager`, defaulting to cert-manager `v1.21.2` from the upstream OCI chart registry. Manage the namespace and CRDs with local state and the current kubeconfig context, enable Gateway API integration through `config.gatewayAPI.enabled`, and declare Terragrunt ordering after Gateway API. No Issuer, ClusterIssuer, or ACME account is created; workload application remains manual.

## [2026.10.12] - 2026-10-20

### Added
- **Kubernetes k9s installation**: Install k9s `0.51.0` system-wide from the official amd64/arm64 Debian package after upstream SHA256 verification, without Snap. Validate and persist `kubernetes_k9s_version` with the complete desired configuration; explicit version overrides take precedence over saved settings. The `k9s` tag supports selective installation on configured hosts, using the operator's existing kubeconfig.

## [2026.10.11] - 2026-10-20

### Added
- **Istio workloads**: Add separate `11-istio-base` and `12-istiod` workloads, defaulting to Istio `1.31.2`, with local state and the current kubeconfig context. Manage the namespace directly through `kbst/kustomization`; Terragrunt records Istiod's ordering dependencies on Gateway API and base. Preserve the small resource requests and disabled Gateway Deployment/Service provisioning, using current chart values and DNS auto-allocation defaults.
- **GitOps Helm installation**: Install Helm `3.22.1` system-wide for amd64/arm64 from an upstream SHA256-verified archive. Expose `/usr/local/bin/helm`, allow exact Helm 3 version overrides through `gitops_helm_version`, and reject Helm 4 because the embedded Kustomize requires Helm 3. Workload application remains manual.

### Changed
- **Gateway API channel**: Default to Standard CRDs `1.6.3` instead of Experimental `1.5.0`. Review the plan before applying to an existing workspace: resources exclusive to the Experimental bundle may be removed.

## [2026.10.10] - 2026-10-20

### Added
- **Local GitOps playbook**: Run `ansible-playbook andreygubarev.com.gitops` to prepare the invoking user's workspace without applying other roles or workloads. The playbook is included in syntax checks and documented alongside the existing entry points.

### Fixed
- **GitOps user overrides**: Create each workload's `terraform.tfvars.yaml` only when absent instead of overwriting local inputs during code updates. Defaults remain in HCL; new workload directories still receive their initial YAML in an existing workspace.

## [2026.10.9] - 2026-10-20

### Added
- **GitOps workspace role**: Add `andreygubarev.com.gitops` to create a private `~/gitops` workspace for the selected user, initialize Git, overlay bundled files without deleting host-only data, and create a baseline commit once. Later overlays remain uncommitted; matching files overwrite local edits. The scaffold includes direnv setup and pinned OpenTofu/Terragrunt versions without automatic `.envrc` approval.
- **Gateway API workload**: Add a Terragrunt/OpenTofu configuration using `kbst/kustomization`, local state, the current kubeconfig context, and ordered resource priorities. The Gateway API experimental release is configurable, defaulting to `1.5.0`; state, provider lock files, and runtime caches are ignored by the workspace repository.

## [2026.10.8] - 2026-10-20

### Added
- **Terraform tooling role**: Add `andreygubarev.com.terraform` for Ubuntu 26.04, installing system-wide direnv and tenv plus per-user OpenTofu 1.12.x and Terragrunt 1.1.x through tenv. Release selectors resolve to saved exact versions; Bash gets a direnv hook without automatic `.envrc` approval. The local playbook and Incus/testinfra checks cover installation, repeat application, and reboot persistence.

## [2026.10.7] - 2026-10-20

### Changed
- **Incus integration tests**: `make test` now provisions a fresh Ubuntu 26.04 VM, applies Ubuntu followed by Kubernetes, runs both testinfra suites, checks repeat application for idempotence, and verifies persistence after reboot. Successful VMs are removed; failed runs retain diagnostics. Existing hosts and `inventory.ini` are no longer targeted.

### Fixed
- **Minimal Ubuntu images**: Skip stopping UFW when its service is absent, while still masking it to prevent later activation; explicitly install chrony before starting time synchronization.
- **Combined role networking**: New clusters configure kube-proxy to preserve the host's connection-tracking limit instead of overwriting the Ubuntu baseline.

## [2026.10.6] - 2026-10-20

### Added
- **Automated Galaxy publishing**: GitHub Actions runs `make publish` when a numeric version tag without a `v` prefix is pushed, after checking that the tag matches `galaxy.yml`. Authentication uses the repository secret `GALAXY_API_KEY`.

## [2026.10.5] - 2026-10-20

### Changed
- **Kubernetes task layout**: Split the role into numbered task files with static imports. Application task order and behavior are preserved; preflight/configuration run with `always`.
- **Ubuntu task layout**: Split the role into numbered task files with explicit static imports in `tasks/main.yml`. Task order, tags, conditions, and handler behavior are unchanged.

### Breaking Changes
- **Kubernetes desired configuration**: All ten public variables retain their names in `defaults/main.yml` and reuse a full validated snapshot, including initial API address and kubeconfig owner. Legacy INI facts are automatically expanded to JSON under the existing `cluster` namespace. Immutable identity conflicts, invalid IPv4 networking, or missing users fail before writing; repeat other previous custom settings once when upgrading.
- **Ubuntu desired configuration**: Hostname is now required on first use. All seven public variables remain in `defaults/main.yml` with saved-value fallbacks. The complete validated configuration, including defaults, is persisted before application and reused on later runs. Old hostname-only facts remain readable; existing custom values for other settings should be supplied once when upgrading.
- **Required initial cluster name**: `kubernetes_cluster_name` no longer defaults to `kubernetes`. Supply a non-empty string on the first run; later runs reuse the stored cluster name automatically. An explicitly different name is rejected before mutation without overwriting the local fact. Stored cluster identity remains immutable.

## [2026.10.4] - 2026-10-20

### Added
- **Remembered hostname**: `ubuntu2604_hostname` applies and saves explicit names to `/etc/ansible/facts.d/ubuntu2604.fact`. Later runs reuse the saved value without rewriting it; hosts without an explicit or saved name are untouched. The `hostname` section also maintains local name resolution and prevents cloud-init from resetting the chosen name.

## [2026.10.3] - 2026-10-20

### Changed
- **Automatic root SSH preservation**: Running the Ubuntu role as root now forces `PermitRootLogin yes` regardless of `ubuntu2604_ssh_allow_root_login`, including an explicit `false`. Non-root provisioning still honors the variable. Password authentication remains disabled and authorized keys are still required.

### Added
- **Galaxy publishing target**: `make publish` checks the collection, builds a fresh artifact, and publishes the version declared in `galaxy.yml` using the configured Galaxy token.

## [2026.10.2] - 2026-10-20

### Added
- **Kubernetes role and playbook**: Imported the standalone single-node Kubernetes role, its testinfra verification, and documentation from `ansible-role-kubernetes`. Run `ansible-playbook andreygubarev.com.kubernetes` locally; kubeconfig defaults to the invoking user, and the Ubuntu role is not applied automatically.

### Changed
- **License**: The collection and both roles are now licensed under Apache-2.0.

## [2026.10.1] - 2026-10-20

### Breaking Changes
- **Local playbook**: The included `ubuntu2604` playbook now configures localhost using a local connection, without inventory or SSH transport. It derives the guardrail user from local facts and preserves SSH key and root-login checks. Remote provisioning uses the role in a caller-owned playbook.
- **Collection packaging**: The repository is now the `andreygubarev.com` collection. The Ubuntu role lives in `roles/ubuntu2604` and is referenced as `andreygubarev.com.ubuntu2604`. Install the published collection with `ansible-galaxy collection install andreygubarev.com` or the development checkout with `make deps`, then run `ansible-playbook andreygubarev.com.ubuntu2604` instead of the former root `playbook.yml`. Collection dependencies are declared in `galaxy.yml` instead of `requirements.yml`.
- **Source breadcrumbs**: Managed configuration files and their verification now point to `https://github.com/andreygubarev/ansible-collection`.
- **Purge installed snaps**: The role now removes all installed snap applications, dependencies, revisions, and their data with `--purge` before removing snapd, instead of refusing to continue when snaps are present. No automatic removal snapshots are created. Use `--skip-tags snap` if snaps must be retained.

## [2026.10.0] - 2026-10-20

### Highlights
This release adopts the exact ssh-audit Ubuntu 26.04 server crypto profile, regenerates image-provided SSH host keys on first configuration, and updates Ansible requirements and provisioning checks.

### Breaking Changes
- **Ansible requirement**: The minimum supported version is now ansible-core 2.20, which supports Ubuntu 26.04's Python 3.14. Control-node Python requirements are documented separately.
- **SSH crypto policy**: All nine crypto directives now match the ssh-audit Ubuntu 26.04 server guide v1 dated 2026-06-14. Clients must support hybrid post-quantum key exchange; ECDSA user keys and RSA user keys shorter than 3072 bits are no longer accepted.
- **First-run host identities**: When `/etc/ssh/sshd_config.d/00-ubuntu2604-hardening.conf` does not exist, existing host keys are replaced with Ed25519 and RSA 4096 keys. This changes server fingerprints. Existing role configuration prevents regeneration, including when crypto settings change.

### Improvements
- **Safe selective execution**: OS and architecture checks and the cloud-init barrier use `always`; SSH guardrails follow `ssh`; snapd guardrails and cleanup also follow `packages`. Network runs include prerequisite kernel modules, and package upgrades include reboot reporting.
- **SSH connection cleanup**: `ClientAliveCountMax` is now `3` with a 300-second interval, disconnecting unresponsive clients after approximately 15 minutes without terminating responsive idle sessions.
- **APT maintenance timers**: Both daily timers are started as well as enabled, so stopped timers do not require a reboot to become active.
- **Collection discovery**: `ansible.cfg` includes the repository-local collection directory alongside the standard user and system paths, making dependencies installed by `make deps` available to standalone Ansible commands.

### Internal
- Updated `community.general` from 13.0.0 to 13.5.0.
- SSH verification now expects the default port 22, checks all nine crypto directives, and verifies Ed25519 and RSA 4096 host keys.
- APT timer verification now checks both enabled and running state.
- Updated configuration and quickstart documentation to reflect the new requirements and behavior.

## [2026.6.1] - 2026-06-10

### Highlights
This release makes the SSH server port configurable so hosts can hand port 22 to another service (such as an application SSH endpoint) and serve OpenSSH admin access elsewhere.

### New Features
- **Configurable SSH port**: New `ubuntu2604_ssh_port` variable (default `22`) sets the `Port` directive in the hardening drop-in. Ubuntu 26.04's socket-activated sshd follows automatically because `sshd-socket-generator` derives `ssh.socket` `ListenStream` entries from `sshd_config`.

### Improvements
- **Socket-aware OpenSSH restart**: The restart handler now reloads systemd and restarts `ssh.socket` before `ssh.service` so listener changes take effect under socket activation instead of only restarting the daemon.

### Internal
- Tests verify the configured port is persistent in the drop-in, effective in `sshd -T`, and actually listening.
- The example inventory documents pairing `ansible_port` with `ubuntu2604_ssh_port` when the port moves.

## [2026.6.0] - 2026-06-09

### Highlights
This release makes the role fully provider-neutral by removing all AWS-specific integration and simplifies networking with an opt-in IPv6 disable flag. APT sources now point directly at Canonical endpoints without mirror-list indirection.

### Breaking Changes
- **Removed AWS integration**: Dropped EC2 metadata gathering, regional `ec2.archive.ubuntu.com` mirror fallback, the `ubuntu2604_cloud` variable, the `aws` task tag, and the `amazon.aws` collection dependency. AWS-specific behavior now belongs in a separate role.
- **Replaced `ubuntu2604_prefer_ipv4` with `ubuntu2604_disable_ipv6`**: The old gai.conf-based IPv4 preference and address-selection tasks are removed. The new `ubuntu2604_disable_ipv6` variable (default `true`) controls IPv6 at the sysctl level across all interfaces.
- **Removed `open-vm-tools` from package cleanup**: VMware-specific assumptions no longer apply in the provider-neutral baseline.

### Improvements
- **Provider-neutral APT sources**: The `ubuntu.sources` template now uses direct `archive.ubuntu.com` and `security.ubuntu.com` URIs instead of `mirror+file` indirection through managed mirror lists. Legacy mirror list files are cleaned up automatically.
- **Simplified APT cache logic**: Cache refresh condition no longer tracks mirror list changes, only source file changes.
- **IPv6 sysctl controls**: When IPv6 is enabled, the role explicitly configures RA acceptance and forwarding for bridge compatibility. When disabled, all interfaces including loopback are covered.
- **Container-worker terminology**: Task names, comments, and tests reframed from "VPS" to "container-worker" to better describe the role's target environment.

### Internal
- Kernel and network sysctl tasks now carry both `kernel` and `network` tags for selective execution.
- Tests updated: removed gai.conf and mirror-list assertions, added legacy mirror absence checks and direct-endpoint verification.

## [2026.5.7] - 2026-05-30

### Highlights
This release slims VPS images by removing snapd and desktop-style packages, renames the role and its variables for consistency, and adds tunable IPv4 preference for dual-stack hosts.

### New Features
- **IPv4 preference on dual-stack**: Configures `/etc/gai.conf` so IPv4 is preferred when both families are available without disabling IPv6; controlled by `ubuntu2604_prefer_ipv4` (default `true`)
- **Snapd removal with guardrails**: Removes `snapd` and residual directories when no snaps are installed, and pins the package at negative priority so it cannot be reinstalled accidentally
- **VPS image slimming**: Purges ~20 VPS-irrelevant packages including desktop helpers (`packagekit`, `polkitd`), hardware daemons (`fwupd`, `modemmanager`, `bolt`), cloud agents (`open-vm-tools`, `ubuntu-pro-client`), and interactive tooling (`apport`, `update-manager-core`, `sysstat`)

### Breaking Changes
- **Role renamed to `ubuntu2604`**: The role directory, variable prefix, and documentation references changed from `ubuntu_2604` to `ubuntu2604`. Update playbook imports, variable overrides, and any external references accordingly.

### Improvements
- **Removed `ansible.posix` dependency**: All configuration persistence now uses builtin `copy` and `command` modules, eliminating the external collection requirement
- **SSH test alignment**: Testinfra no longer hardcodes `PermitRootLogin no`; it now follows the `ubuntu2604_ssh_allow_root_login` default

### Internal
- Reverted restrictive `.envrc` setup to allow `dotenv` loading and added `.env` to `.gitignore`

## [2026.5.6] - 2026-05-30

### Highlights
This release makes SSH hardening safer and sequencing more robust by adding guardrails and a cloud-init wait barrier.

### New Features
- **SSH lockout guardrails**: Before disabling password authentication or root login, the role asserts that the Ansible user has an authorized_keys file and that root SSH remains reachable when connected as root
- **cloud-init wait barrier**: The role waits up to 30 minutes for cloud-init to complete before mutating the host, accepting completion-with-errors and warning when boot-time initialization issues remain

### Improvements
- **APT lock timeout**: Safe upgrades now wait up to 10 minutes for dpkg locks instead of failing when cloud-init or unattended upgrades hold the lock at boot

### Internal
- **Concise comments**: Rationale comments throughout tasks, ansible.cfg, and docs were tightened to reduce verbosity without losing intent
- **Role description**: Rephrased from "disposable container workers" to "container workloads"

## [2026.5.5] - 2026-05-28

### Highlights
This release adds SSH hardening, systemd manager density defaults, journald log pressure controls, nftables firewall ownership, and prerequisite assertions. APT mirror selection is safer, and more settings are exposed as user-configurable defaults.

### New Features
- **SSH hardening**: Priority drop-in (`00-ubuntu2604-hardening.conf`) pins a restricted algorithm set, disables password authentication, and limits forwarding; root login and TCP forwarding are configurable via `ubuntu2604_ssh_allow_root_login` and `ubuntu2604_ssh_allow_tcp_forwarding`
- **Systemd density defaults**: Manager drop-in sets `DefaultLimitNOFILE`, `DefaultLimitNPROC`, and `DefaultTasksMax` to `65536`, plus enables memory and task cgroup accounting so service-launched workloads inherit the same headroom as login sessions
- **Journald log pressure controls**: Persistent journals capped at 1 GB total, 128 MB per file, 30-day retention, with reserved free space on `/var/log` and `/run` so log bursts cannot crowd out packages or workload state
- **Firewall manager selection**: `nftables` is enabled as the host firewall manager, `ufw` is masked, and iptables-family compatibility commands are switched to the nft backend
- **Reboot-required reporting**: After safe upgrades, the role surfaces `/var/run/reboot-required` and the list of triggering packages without rebooting the host
- **Prerequisite assertions**: Role fails fast with a clear message when run on a non-Ubuntu 26.04 host or an unsupported architecture

### Improvements
- **APT mirror safety**: Canonical archives are now primary, with EC2 regional mirrors as fallback, avoiding stale-index sync races; arm64 hosts use the standard archive instead of `ports.ubuntu.com`
- **User-configurable defaults**: `ubuntu2604_locale`, `ubuntu2604_timezone`, and the new SSH toggles are now defined in `defaults/main.yml` instead of `vars/main.yml`
- **Expanded testinfra coverage**: New parametrized tests verify systemd manager settings, journald persistence, firewall state, SSH hardening, reboot markers, and APT mirror priorities

### Internal
- Added `ansible.cfg` with SSH connection multiplexing, pipelining, and retry tuning for faster playbook runs
- New task tags: `systemd`, `logs`, `firewall`, and `ssh`

## [2026.5.4] - 2026-05-27

### Highlights
This release adds operational troubleshooting packages, UTC time synchronization, systemd-resolved DNS fallback, and quiet MOTD handling. AWS integration now requires explicit opt-in instead of automatic platform detection.

### New Features
- **Operational packages**: Installs a standard troubleshooting toolbox (`htop`, `iotop`, `jq`, `tcpdump`, `tmux`, `bind9-dnsutils`, and others) so incident response does not start by changing package state
- **UTC timezone with chrony**: Pins the system timezone to UTC and ensures the `chrony` time synchronization service is active for predictable cross-region log correlation
- **systemd-resolved fallback DNS**: Configures `systemd-resolved` with Cloudflare fallback resolvers (`1.1.1.1`, `1.0.0.1`) that are only consulted when DHCP-supplied DNS is unavailable, preserving internal zone resolution
- **Quiet MOTD**: Removes dynamic MOTD entries, clears static `/etc/motd`, masks the `motd-news.timer`, and scrubs transient cache files for low-noise SSH logins on container workers

### Breaking Changes
- **AWS detection is now explicit**: The role no longer auto-detects EC2 via platform heuristics. Set `ubuntu2604_cloud: "aws"` to enable AWS-aware behavior such as regional APT mirror selection

### Improvements
- **Concise sysctl comments**: Rationale comments for kernel tuning settings were tightened to reduce redundancy without losing intent
- **Retained `overlay` module preload**: The role continues to force-load `overlay` so OverlayFS readiness is explicit for container runtimes that use overlay snapshotters
- **Expanded documentation**: Quickstart and configuration reference now cover task tag selectors and APT/unattended-upgrade behavior

### Internal
- New `aws` task tag for EC2 metadata gathering and regional mirror selection

## [2026.5.3] - 2026-05-26

### Highlights
This release adds deterministic APT source management with AWS regional mirror awareness, safe package upgrades, and explicit unattended security upgrade policies that block automatic reboots.

### New Features
- **AWS-aware APT mirror selection**: Detects EC2 instances via platform facts and IMDS, preferring regional `ec2.archive.ubuntu.com` mirrors with fallback to Canonical-operated endpoints; replaces cloud-init defaults with deterministic source lists
- **Safe APT upgrades**: Applies `safe` upgrades, `autoremove`, and `autoclean` during role runs so fresh VMs stay current without accepting disruptive dependency changes
- **Unattended security upgrades**: Explicitly enables periodic security updates while disabling automatic reboots, shutdown-time installs, and needrestart automatic service restarts; container workloads remain stable outside operator-controlled maintenance windows
- **Task tags**: All tasks tagged with semantic selectors (`kernel`, `swap`, `apt`, `locale`, `unattended_upgrades`, `upgrade`, `packages`) for selective execution

### Improvements
- **Expanded testinfra coverage**: New parametrized tests verify APT mirror lists, source file syntax, unattended-upgrade settings, needrestart policy, and APT maintenance timer state

### Internal
- Added `amazon.aws` collection dependency (`10.1.2`) for EC2 metadata fact gathering
- Removed unused `templates/.gitkeep` scaffolding

## [2026.5.2] - 2026-05-26

### Highlights
This release adds a comprehensive pytest-testinfra verification suite, user-facing documentation, and faster parallel test execution.

### New Features
- **Integration test suite**: `ubuntu2604/tests/test_ubuntu2604.py` verifies kernel modules, sysctl persistence, PAM limits, transparent hugepages, swap removal, and locale configuration using pytest-testinfra
- **Documentation site**: New `docs/` pages including a quickstart guide, configuration reference, and overview index

### Improvements
- **Parallel test execution**: `make test` runs testinfra checks across 8 workers with `pytest-xdist` for faster verification cycles
- **Makefile organization**: Variables renamed for clarity and separated by tool (Ansible vs. testinfra)

### Internal
- Replaced legacy Ansible role test scaffolding (`tests/test.yml`, `tests/inventory`) with the new pytest-based suite

## [2026.5.1] - 2026-05-26

### Highlights
Initial release of the `ubuntu2604` role for provisioning Ubuntu 26.04 VMs for container workloads. The role favors predictable networking, dense process scheduling, and automatic recovery over general-purpose desktop defaults.

### New Features
- **Container-optimized kernel tuning**: Loads `br_netfilter`, `nf_conntrack`, and `overlay` modules; applies 30+ sysctl parameters for bridge netfilter, IPv4/IPv6 forwarding, connection tracking, file descriptor limits, and VMA mapping
- **PAM limits**: Raises soft and hard `nofile` and `nproc` limits to 65536 so container-launched sessions can use the enlarged kernel ceilings
- **Transparent hugepages policy**: Installs a systemd one-shot service that sets THP to `madvise`, letting runtimes opt in without forcing global hugepages on latency-sensitive workloads
- **Swap disable**: Turns off active swap and scrubs swap entries from `/etc/fstab` to keep OOM behavior predictable and avoid container latency spikes
- **Locale enforcement**: Installs the `locales` package, generates a configurable UTF-8 locale, and sets it as the system default
- **Linting and dependency automation**: `Makefile` targets for `ansible-lint` and collection installation, run via `uvx` for reproducible tooling

### Internal
- Role metadata, handlers, and variable scaffolding established with production-grade `ansible-lint` configuration
