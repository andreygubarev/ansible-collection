# andreygubarev.com.terraform

OpenTofu and Terragrunt tooling for Ubuntu 26.04 and Debian 13, included in the `andreygubarev.com` collection. The role installs direnv, tenv, SOPS, and age system-wide, then installs OpenTofu and Terragrunt through tenv for an existing user. HashiCorp Terraform is not installed.

[Quickstart](../../docs/terraform/getting-started/quickstart.md) · [Configuration](../../docs/terraform/reference/configuration.md) · [Task index](tasks/main.yml)

Initial defaults select the latest stable tenv, OpenTofu 1.12.x, and Terragrunt 1.1.x. Exact resolved versions and the selected user are validated and saved in local facts before installation. Later runs reuse them unless explicitly overridden.

SOPS defaults to `3.13.3` and age to `1.3.2`, with checksummed amd64/arm64 binaries and persisted exact version overrides. The role creates `~/.config/sops/age/keys.txt` for the selected user only if absent, with mode `0600`; existing identities are never replaced. Back up this identity separately from Git. It is not stored in local facts or task output.

All public settings are in `defaults/main.yml`. Numbered task files use explicit static imports. The role is independent of both host baselines and Kubernetes.

## License

[Apache-2.0](../../LICENSE).
