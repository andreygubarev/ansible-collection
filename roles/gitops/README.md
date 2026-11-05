# GitOps

Supports Ubuntu 26.04 and Debian 13. Creates `~/gitops` for `gitops_user`, defaulting to the invoking/SSH user. The directory belongs to that user and their primary group, with mode `0700` to protect instance-specific inputs and saved plans.

Run locally with `ansible-playbook andreygubarev.com.gitops`; use `-e gitops_user=operator` to select another existing user. The playbook does not apply other roles or cluster workloads. Set `gitops_git_user_name` and `gitops_git_user_email` on first use; both are mandatory and saved in the repository's `.git/config`. Later runs reuse those values unless explicitly overridden. Global Git identity and auto-detected system identity are not used as fallbacks.

First apply the independent `terraform` role for the same user to install SOPS/age and prepare an age identity. GitOps seeds a public `.sops.yaml` policy and an encrypted empty `terraform.tfvars.sops.yaml` in each workload, only when absent. Existing policies and encrypted inputs are preserved. Keep non-secret overrides in tracked `terraform.tfvars.yaml` and passwords/access keys/runner credentials only in `terraform.tfvars.sops.yaml`. Terragrunt merges regular YAML first and decrypted SOPS values last. No plaintext secrets are migrated automatically; keep the age private key outside Git and back it up separately. SOPS does not encrypt OpenTofu state or saved plans.

The role copies `files/gitops/` into the workspace on every run, including dotfiles, without deleting host-only files. Matching code files are overwritten, including uncommitted local edits. Each `terraform.tfvars.yaml` is created only if missing and is never overwritten; it contains user overrides, while defaults belong in the HCL variable declarations. Newly added workloads receive their own initial YAML even when the repository already exists.

Git is installed and the workspace is initialized as a repository before copying the scaffold. After copying, the first application creates a baseline commit using the validated repository identity; global Git settings are not changed. An existing `.git` prevents reinitialization, and an existing `HEAD` prevents another automatic commit. Subsequent overlays remain uncommitted for review with `git status` and `git diff`.

Shared `root.hcl` generates a local backend with absolute paths under `~/.local/state/gitops/<workload>/`, including a separate directory for named workspaces. State directories are private (`0700`) and independent of checkout/cache paths. Renaming a workload changes its state identity and requires migration. Existing authoritative state in the default Terragrunt cache blocks scaffold updates until explicitly migrated; never delete that cache to bypass the guard.

The scaffold includes `.envrc`, pinned OpenTofu/Terragrunt versions, and a `.gitignore` excluding generated backend files, local state and runtime caches. The provider lock file is also ignored. The role does not authorize direnv or run OpenTofu/Terragrunt commands.

## Workloads

- `10-gateway-api`: Standard Gateway API CRDs.
- `11-istio-base`: The `istio-system` namespace and Istio base chart.
- `12-istiod`: The Istio control plane, with automatic Gateway Deployment/Service provisioning disabled.
- `13-istio-gateway`: A manually managed Istio gateway with host ports and Gateway API listeners.
- `20-cert-manager`: The `cert-manager` namespace and cert-manager chart, including CRDs and Gateway API integration. No Issuer, ClusterIssuer, or ACME account is created.
- `21-letsencrypt`: A Let's Encrypt ClusterIssuer using Gateway API HTTP-01.
- `30-openebs`: The `openebs` namespace and OpenEBS LocalPV Hostpath provisioner. `openebs-hostpath` is the default StorageClass; `openebs-hostpath-retain` provides an explicit Retain alternative.
- `31-cnpg`: The `cnpg-system` namespace and cluster-wide CloudNativePG operator, including CRDs. No PostgreSQL clusters or databases are created.
- `32-k8up`: The `k8up-system` namespace, K8up CRDs/operator, and global Backblaze B2/Restic configuration. Only annotated PVCs are eligible; no Backup or Schedule resources are created.
- `40-forgejo`: Rootless Forgejo, a CNPG database, persistent storage, HTTPS/SSH routes, and Actions.
- `41-forgejo-runner`: A trusted-code-only Forgejo Runner with a privileged DinD sidecar and no automatic Kubernetes API access.
- `42-forgejo-backup`: A K8up Schedule for online backups of only the `forgejo-data` PVC, with a dedicated repository bucket/prefix and shared operator endpoint/credentials.

The role installs Helm `3.22.1` system-wide at `/usr/local/bin/helm`, linked to a versioned binary under `/usr/local/lib/helm/`. Downloads for amd64/arm64 are verified against the upstream SHA256 checksum. Override `gitops_helm_version` with an exact Helm 3 version; Helm 4 is not accepted because the Kustomize version embedded in `kbst/kustomization` requires Helm 3. Installing Helm does not install or apply charts.

All three Istio charts default to `1.31.2`; keep their `istio_version` overrides aligned.

cert-manager defaults to `v1.21.2` from the upstream OCI registry; override `cert_manager_version` in its `terraform.tfvars.yaml`. Gateway API integration uses `config.gatewayAPI.enabled`, replacing the deprecated `enableGatewayAPI` setting.

OpenEBS defaults to `4.6.2`; override `openebs_version` in its `terraform.tfvars.yaml`. LVM, ZFS, Rawfile, Mayastor, Loki (including MinIO), and Alloy are disabled. Both Hostpath classes use `/var/openebs/local` and `WaitForFirstConsumer`; the default class uses `Delete`, while the Retain class keeps volumes after PVC deletion for manual recovery. Local storage is not replicated or backed up by this workload. Other default StorageClasses are not modified; review them before applying to avoid multiple defaults. OpenEBS has no ordering dependencies on the other workloads.

CloudNativePG defaults to chart `0.29.1` (operator `1.30.1`); override the chart version through `cnpg_version` in its `terraform.tfvars.yaml`. The operator has no ordering dependencies on OpenEBS or cert-manager; provision storage before creating PostgreSQL clusters separately.

K8up defaults to chart/CRDs `4.10.0` (operator `v2.16.0`); override `k8up_version` to keep chart and CRDs aligned. Set `b2_bucket` and any `b2_endpoint` override in ordinary YAML; put `b2_access_key_id`, `b2_secret_access_key`, and `k8up_repo_password` only in SOPS YAML. Credentials use a Kubernetes Secret; changing them restarts the operator. Helm cleanup hooks are excluded rather than deployed as ordinary Jobs/RBAC. Back up the Restic password separately. Configure backup schedules and annotate selected PVCs explicitly; copying a live PostgreSQL data volume is not a substitute for a database-consistent CNPG backup. K8up has no ordering dependencies on OpenEBS or CNPG.

Set `b2_bucket` in `42-forgejo-backup/terraform.tfvars.yaml` to a dedicated stable repository path such as `backup-bucket/k8up/forgejo`; each run creates a new Restic snapshot in that same repository, not a dated prefix. Forgejo PVC backups default to daily at 03:00 UTC; override `backup_schedule` in the same YAML. Apply the updated `40-forgejo` first: it owns the PVC and adds its backup annotation/selection label. `42-forgejo-backup` depends on K8up and Forgejo, creates only the Schedule, and does not adopt the PVC, stop Forgejo, or configure snapshot pruning. Backup jobs read the volume as root via a read-only mount; this is a live file backup, not an atomic snapshot. No additional credentials are needed.

For Terragrunt `run --all`, Istiod declares ordering dependencies on Gateway API and Istio base; cert-manager depends on Gateway API so its CRDs are present when the controller starts. Single-workload commands do not apply dependencies automatically: apply Gateway API before cert-manager, apply Gateway API and base before Istiod, and destroy cert-manager and Istiod before their dependencies.

Instance-specific settings belong in host YAML overrides. Non-secret overrides are tracked normally; encrypt passwords, access keys, and runner credentials with SOPS. Sensitive values still reside in plaintext local state. Free host port 22 before applying the gateway. Initial bootstrap is sequential because runner credentials are obtained after Forgejo starts.
