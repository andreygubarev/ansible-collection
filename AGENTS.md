# andreygubarev.com

## IMPORTANT behavioral guardrails

These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### Think before coding

- State material assumptions explicitly.
- If multiple reasonable interpretations exist, present them instead of choosing silently.
- If a simpler approach exists, say so. Push back when warranted.
- If the request is materially unclear, stop, name the ambiguity, and ask.

### Simplicity first

- Implement the minimum code that solves the request.
- Do not add speculative features, abstractions, configurability, or future-proofing.
- Do not add error handling for hypothetical scenarios outside the role contract.
- If the solution is much larger than necessary, simplify before finalizing.

### Surgical changes

- Touch only what the request requires.
- Do not refactor, reformat, or "improve" adjacent unrelated code.
- Match existing style, even when another style would be preferable.
- Remove only imports, variables, functions, or files made unused by your own change.
- Mention unrelated dead code or issues instead of changing them.

Every changed line should trace directly to the user request or to keeping that change correct, tested, and lint-clean.

## Collection scope

- This repository is the `andreygubarev.com` collection of public infrastructure roles and playbooks.
- Keep roles in `roles/` and collection playbooks in `playbooks/`; use fully qualified role names.

## Ubuntu 26.04 role target

- The `ubuntu2604` role configures Ubuntu 26.04 VMs that are expected to actively run container workloads.
- Prefer host defaults that support container networking, dense service processes, and predictable VM recovery.
- Keep all public Ubuntu settings in `defaults/main.yml`, resolving saved facts before fallback defaults. Validate and persist the complete configuration before application; hostname is required on first use.

## Debian 13 role target

- The independent `debian13` role provides the same container-worker host policy on Debian 13 amd64/arm64. Keep Ubuntu's role, variable names, saved facts, and sources unchanged.
- Keep Debian public settings in `defaults/main.yml` with saved-fact fallbacks, validate and persist the complete configuration before application, and require hostname on first use.
- Use Debian's official archive/security sources, service-based SSH, `/etc/locale.conf`, and native kernel restart reporting. Reboots remain manual. Do not perform Ubuntu-to-Debian migration.
- Debian Kubernetes uses signed vendor APT packages for containerd.io 2.x without Docker Engine; existing distro containerd/runc packages require explicit migration.
- Agents use the same signed NodeSource Node.js 24 LTS package with bundled npm on both Ubuntu and Debian. Keep the package list literal, without distribution-specific Node.js/npm branches.
- Scope checksum-verified vendor keys with Signed-By; never execute setup scripts or import testing/unstable repositories.

## Kubernetes role target

- The `kubernetes` role provisions a standalone single-node kubeadm cluster on Ubuntu 26.04 or Debian 13.
- Keep public settings in `defaults/main.yml` with local-fact fallbacks. Validate and save the complete desired configuration; reject changes to stored cluster identity before writing.
- Collection playbooks target localhost and do not automatically apply other roles.

## Terraform tooling role target

- The `terraform` role installs system-wide direnv and tenv on Ubuntu 26.04 or Debian 13 amd64/arm64, then installs OpenTofu and Terragrunt through tenv for an existing user. It does not install HashiCorp Terraform.
- Keep public settings in `defaults/main.yml` with local-fact fallbacks. Initially resolve latest stable tenv, OpenTofu 1.12.x, and Terragrunt 1.1.x to exact versions; validate and save the complete configuration before installation. Reuse saved versions unless explicitly overridden.
- User tool versions live in `~/.tenv`; system proxies live in `/usr/local/bin`. Configure only the selected user's Bash direnv hook and never authorize `.envrc` files automatically.
- Install checksummed, versioned SOPS and age binaries system-wide. Create the selected user's age identity at `~/.config/sops/age/keys.txt` only when absent, with private directory/file permissions; never replace it, log its content, or store it in facts.

## GitOps role target

- The `gitops` role installs Git and a checksummed system-wide Helm 3 binary, prepares `~/gitops` for `gitops_user`, overlays bundled code without deleting host-only data, and commits the initial Git baseline once. Later updates remain uncommitted. Helm 4 is incompatible with the Kustomize version embedded in `kbst/kustomization`.
- Require `gitops_git_user_name` and `gitops_git_user_email` before initializing the repository; explicit values override saved repository-local identity. Never fall back to global or auto-detected system identity, and never change global Git configuration. Use the repository identity for the initial baseline commit.
- Create `terraform.tfvars.yaml` only if missing; preserve existing user overrides. Keep defaults in HCL variable declarations. Keep public documentation brief and reusable, without per-server runbooks. Deployment-specific hostnames, addresses, account names, and email belong in host overrides, not bundled defaults or instructions.
- The local playbook does not apply other roles or run OpenTofu/Terragrunt. Never authorize `.envrc` automatically.
- Keep local backend state at absolute `~/.local/state/gitops/<workload>/` paths through shared `root.hcl`, including named workspaces. Treat workload paths as state identities. State is never cache data: block scaffold updates when legacy authoritative state remains in the default Terragrunt cache, and require explicit migration before cache cleanup. The role creates private state directories but never runs init, migrates state, or applies workloads automatically.
- Require SOPS/age and the workspace owner's age identity from the independent Terraform tooling role. Seed `.sops.yaml` and encrypted `terraform.tfvars.sops.yaml` maps only when missing; preserve existing recipient policies and ciphertext. Merge ordinary inputs first and decrypted SOPS inputs last. Do not migrate plaintext secrets or rewrite Git history automatically; private keys and state stay outside Git.
- Forgejo bootstrap is manual and sequential: gateway, ACME issuer, Forgejo/database, then runner registration and runner. Free host port 22 by moving and verifying administrative SSH before applying the gateway.
- Track non-secret overrides in ordinary `terraform.tfvars.yaml`; keep `admin_password`, `runner_uuid`, `runner_token`, `b2_access_key_id`, `b2_secret_access_key`, and `k8up_repo_password` only in encrypted `terraform.tfvars.sops.yaml`. Do not ignore ordinary Forgejo/runner inputs or migrate non-secret values into SOPS. Sensitive values still reside in plaintext local state. Runner jobs are trusted-only, use a privileged DinD sidecar without a node runtime socket, and receive no Kubernetes API credentials automatically.
- The `32-k8up` workload installs matching chart/CRDs and global B2/Restic defaults, not Backup/Schedule resources. Keep opt-in PVC selection (`skipWithoutAnnotation`), use Secret-backed credential environment variables, and restart the operator when credentials change. Exclude Helm hook resources so the chart's cleanup job/RBAC are not applied outside Helm lifecycle. Do not annotate existing PVCs or treat a live PostgreSQL filesystem copy as a database-consistent backup automatically.

- The `42-forgejo-backup` workload schedules online backups of only `forgejo-data` using an explicit per-application `b2_bucket` repository bucket/prefix while inheriting K8up's global endpoint and credentials. Keep the repository path stable across runs; do not use dated prefixes or silently inherit the global repository path. Keep PVC annotation/selection labels in `40-forgejo`, the PVC owner; do not adopt the PVC into a second state. Do not add PostgreSQL backups, application shutdown/hooks, or automatic snapshot pruning to this workload.

## Ansible style

- Keep each role's `tasks/main.yml` as an explicit, ordered list of static `ansible.builtin.import_tasks` entries.
- Keep tasks in numbered `XX-section.yml` files: tens group related areas, units identify their parts.
- Preserve task-level tags and execution order when splitting files; do not auto-discover task files.
- Group tasks with comment sections using full-width separators and a short rationale:

  ```yaml
  # -----------------------------------------------------------------------------
  # Section name
  # -----------------------------------------------------------------------------
  # Explain why this section exists and why this approach is used. Do not repeat
  # what the tasks already say.
  # -----------------------------------------------------------------------------
  ```

- Prefix task names with the semantic section, for example `APT | Update package cache`.
- When commenting individual settings, explain both the effect and the reason; assume the reader may not know the kernel/sysctl name.
- Prefer clear literals over variables for values that are not real user-facing configuration.
- Add defaults only for values users are expected to override.
- Use fully qualified module names, for example `ansible.builtin.apt`.
- Keep tasks readable and lint-clean with `make check`.

## Testinfra verification

- Use testinfra to verify role application in a fresh local Incus VM.
- Keep verification in each role's `tests/` directory, including `roles/debian13/tests/test_debian13.py` for the Debian baseline.
- `make test` applies the matching baseline, Kubernetes, Terraform tooling, GitOps, and agents on separate fresh Ubuntu 26.04 and Debian 13 VMs. `INCUS_DISTRIBUTIONS` selects either or both targets. All five suites run for each OS; no GitOps workloads are applied. The roles remain independently usable; standalone Kubernetes testing is not required.
- Keep tests self-contained by hardcoding the expected role contract in the tests.
- Use native testinfra modules such as `host.sysctl`, `host.file`, `host.service`, and `host.package`.
- Place expected-value constants close to the tests that use them, grouped by semantic section.
- Use parametrized tests for repeated settings such as sysctls, kernel modules, and PAM limits.
- Run verification through `make test`, which uses pytest/testinfra with xdist parallelism and SSH ControlPersist connection reuse, checks repeat application for `changed=0`, and verifies persistence after reboot.
- Delete successful test VMs; retain failed or interrupted runs and their diagnostics under `.cache/`. Do not target existing hosts or instances.

## Releases

- A release includes updating `galaxy.yml` and `CHANGELOG.md`, committing and pushing the changes, and creating and pushing the matching numeric version tag without a `v` prefix. Do not leave tag creation as a separate manual step; pushing the tag triggers Galaxy publication.

## Makefile style

- Prefix Ansible-related knobs with `ANSIBLE_` and testinfra-related knobs with `TESTINFRA_`.
- Group Makefile variables by tool area with short comments such as `# Ansible`, `# Incus`, and `# Testinfra`.
- Put each `.PHONY` declaration immediately above the target it declares.
