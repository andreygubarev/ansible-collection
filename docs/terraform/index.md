# Terraform tooling

The `andreygubarev.com.terraform` role prepares an OpenTofu/Terragrunt environment on Ubuntu 26.04 or Debian 13. The role name identifies the infrastructure-as-code workflow; it does not install HashiCorp Terraform.

- [Quickstart](getting-started/quickstart.md)
- [Configuration and persistence](reference/configuration.md)
- [Task index](../../roles/terraform/tasks/main.yml)

The role installs system-wide direnv and tenv, user-owned OpenTofu/Terragrunt versions, and a Bash direnv hook. It does not create user accounts, authorize `.envrc` files, or provision infrastructure.
