# Terraform tooling quickstart

## Requirements

- Ubuntu 26.04 or Debian 13 on amd64 or arm64, ansible-core ≥ 2.20, and root or sudo access.
- An existing user account with a home directory. By default, the local playbook configures the invoking user.
- HTTPS access to the GitHub API, GitHub release assets, and `get.opentofu.org`, plus the distro package archives.

## Run locally

```bash
ansible-galaxy collection install andreygubarev.com --upgrade
ansible-playbook andreygubarev.com.terraform
```

Add `-K` if sudo requires a password. Run without `sudo` when configuring your own account; the role escalates only for system installation. Running as root selects root unless `terraform_user` names another existing account:

```bash
ansible-playbook andreygubarev.com.terraform -e terraform_user=ubuntu
```

The role independently installs direnv and tenv. OpenTofu and Terragrunt are installed **through tenv**, under the selected user's `~/.tenv`, and selected as that user's defaults. Host baselines and Kubernetes are not applied automatically.

Initial selections are latest stable tenv, latest stable OpenTofu 1.12.x, and latest stable Terragrunt 1.1.x. Exact versions are saved before application and reused on later runs. See [configuration](../reference/configuration.md) for explicit version changes.

## Use

Open a new interactive Bash session, then check:

```bash
tenv version
tofu version
terragrunt --version
```

The role adds `eval "$(direnv hook bash)"` to the selected user's `.bashrc`. Inspect each project's `.envrc` before authorizing it yourself:

```bash
direnv allow .
```

`.envrc` files execute Bash code. The role never authorizes them automatically. Other shells are not configured. Project version files such as `.opentofu-version` and `.terragrunt-version` retain precedence over tenv's user defaults.

## Remote provisioning

Use the fully qualified role in your own playbook:

```yaml
- name: Prepare OpenTofu and Terragrunt tooling
  hosts: workstations
  roles:
    - andreygubarev.com.terraform
```

Set the SSH user in inventory, or provide `terraform_user` to configure another existing account.

## Integration tests

From a checkout on a machine with local Incus VM support, run `make test`. Separate fresh Ubuntu and Debian VMs receive their host baseline and all shared roles, including GitOps and agents; all five suites run before and after reboot, with repeat application required to report `changed=0`. No infrastructure is provisioned by the tooling smoke tests.
