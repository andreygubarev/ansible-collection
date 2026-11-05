# andreygubarev.com

Ansible roles and local playbooks for Ubuntu 26.04 and Debian 13 infrastructure.

## Requirements

Ubuntu 26.04 or Debian 13 on amd64 or arm64, ansible-core ≥ 2.20, and root or sudo access.

## Getting started

On Ubuntu 26.04, install the minimal Ansible package:

```bash
sudo apt-get update -q
sudo apt-get install -yq --no-install-recommends ansible-core
```

On Debian 13, use an isolated environment to meet the ansible-core minimum:

```bash
sudo apt-get update -q
sudo apt-get install -yq --no-install-recommends pipx
pipx install 'ansible-core>=2.20'
export PATH="$HOME/.local/bin:$PATH"
```

Then install the collection:

```bash
ansible-galaxy collection install andreygubarev.com --upgrade
```

## Run

Run on the machine to configure. No inventory or SSH connection is required; add `-K` if sudo requires a password.

Choose the matching host baseline, not both:

```bash
# Ubuntu 26.04
ansible-playbook andreygubarev.com.ubuntu2604 -e ubuntu2604_hostname=worker-1
# Debian 13
ansible-playbook andreygubarev.com.debian13 -e debian13_hostname=worker-1
```

The other roles support either OS:

```bash
ansible-playbook andreygubarev.com.kubernetes -e kubernetes_cluster_name=my-cluster
ansible-playbook andreygubarev.com.terraform
ansible-playbook andreygubarev.com.gitops
ansible-playbook andreygubarev.com.agents
```

| Role / playbook | Purpose | Documentation |
|---|---|---|
| `andreygubarev.com.ubuntu2604` | Ubuntu container-host baseline | [Quickstart](docs/getting-started/quickstart.md) · [Configuration](docs/reference/configuration.md) |
| `andreygubarev.com.debian13` | Debian container-host baseline | [Usage and configuration](roles/debian13/README.md) |
| `andreygubarev.com.kubernetes` | Single-node kubeadm cluster | [Quickstart](docs/kubernetes/getting-started/quickstart.md) · [Configuration](docs/kubernetes/reference/configuration.md) |
| `andreygubarev.com.terraform` | direnv, tenv, OpenTofu, and Terragrunt | [Quickstart](docs/terraform/getting-started/quickstart.md) · [Configuration](docs/terraform/reference/configuration.md) |
| `andreygubarev.com.gitops` | Host-local GitOps workspace and workload scaffold | [Usage](roles/gitops/README.md) |
| `andreygubarev.com.agents` | Pi harness, Claude Code, and persistent BB user service | [Usage](roles/agents/README.md) |

The playbooks are independent. None automatically applies another role.

- The baselines require `ubuntu2604_hostname` or `debian13_hostname` once and remember the complete validated configuration, including defaults. Future runs need no repeated overrides; supply a new value once to change a setting.
- Kubernetes requires `kubernetes_cluster_name` once and remembers the complete configuration, including the initial API address and kubeconfig owner. Cluster name, Kubernetes minor version, and cluster CIDRs remain immutable.
- Terraform tooling defaults to the invoking user, latest stable tenv, OpenTofu 1.12.x, and Terragrunt 1.1.x. Exact resolved versions are remembered. OpenTofu/Terragrunt are installed through tenv in the user's `~/.tenv`; direnv is hooked into Bash, but `.envrc` authorization remains manual. HashiCorp Terraform is not installed.

- GitOps installs Git and Helm 3, prepares `~/gitops` for the invoking user (`gitops_user` overrides the account), initializes Git, and records the initial baseline once. Later code overlays remain uncommitted. User `terraform.tfvars.yaml` files are created only if missing; workload application and direnv authorization remain manual.

**Host baselines:** require SSH authorized keys, disable password authentication, and regenerate SSH host keys on first configuration. Review the quickstart before use.

## Development

```bash
make deps     # Install the local collection and dependencies
make check    # Lint and syntax-check all playbooks
make build    # Build the collection artifact in dist/
make publish  # Check, build, and publish to Galaxy
make test     # Test all roles in fresh Ubuntu and Debian Incus VMs
```

### Integration tests

`make test` requires a running local Incus server with VM support, `uv`, and an SSH client compatible with the role's SSH policy. It creates separate fresh Ubuntu 26.04 and Debian 13 cloud VMs sequentially, each with 4 vCPUs, 6 GiB RAM, and a 30 GiB disk. Select one with `make test INCUS_DISTRIBUTIONS=debian13` or `INCUS_DISTRIBUTIONS=ubuntu2604`. VM architecture follows the Incus host; arm64 verification needs an arm64 host. The existing Incus network and storage pool default to `incusbr0` and `default`; override them with `INCUS_NETWORK` and `INCUS_STORAGE_POOL` if needed. The VMs need outbound access to distro archives, Kubernetes repositories, GitHub, the npm registry, and container registries. Debian also needs `download.docker.com` and `deb.nodesource.com`.

Each test applies its host baseline, Kubernetes, Terraform tooling, GitOps, and agents, waits for the node and system workloads, and runs all five testinfra suites. GitOps prepares only its workspace; no workload is applied. It reapplies the roles without first-run overrides and requires `changed=0`, then reboots and reruns verification. The tests move administrative SSH to port `22022`, verify a fresh connection and unchanged host keys, then retain that setting through repeat application and reboot. Kubernetes firewall checks include external TCP probes, pod API/DNS/metrics access, isolated IPv6/UDP/forwarding tests, rule repair, and preservation of independently managed tables across nftables reload/restart. This tests the combined fresh-machine workflow; the roles remain independently usable.

Successful runs delete the VM and temporary files. Failed or interrupted runs retain the VM, generated inventory, disposable SSH key, and logs under `.cache/incus-<distribution>.*`, printing inspection and cleanup commands. No existing instances or host SSH keys are used. `make test` no longer reads `inventory.ini` or verifies the local host.

## Publish

Obtain a [Galaxy API token](https://galaxy.ansible.com/ui/token/) with access to the `andreygubarev` namespace.

### GitHub Actions

Add the token as the repository Actions secret `GALAXY_API_KEY`. The workflow in `.github/workflows/ci.yml` publishes to Galaxy when a numeric version tag is pushed, without a `v` prefix.

Update `version` in `galaxy.yml` and `CHANGELOG.md`, commit the release, then tag that commit and push:

```bash
git tag 2026.10.6
git push origin HEAD
git push origin 2026.10.6
```

The tag must exactly match `version` in `galaxy.yml`. The workflow runs `make publish`, which checks the collection, builds a fresh artifact, and waits for Galaxy import validation. Published versions are immutable; rerunning a successful publication does not overwrite them.

### Local publishing

Store the token outside the repository in `~/.ansible/galaxy_token` with permissions `0600`:

```yaml
token: <your-galaxy-api-token>
```

Increment `version` in `galaxy.yml`, then run `make publish`.

## Project

[Documentation](docs/index.md) · [Changelog](CHANGELOG.md) · [Source](https://github.com/andreygubarev/ansible-collection) · [Apache-2.0](LICENSE) · [NOTICE](NOTICE)
