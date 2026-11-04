# Ubuntu configuration

## Variables

| Variable | Initial fallback | Effect |
|---|---|---|
| `ubuntu2604_hostname` | Required once | Mandatory hostname; reused from saved settings |
| `ubuntu2604_disable_ipv6` | `true` | Disable IPv6; set `false` for IPv6/dual-stack workloads |
| `ubuntu2604_locale` | `en_US.UTF-8` | Generated system locale |
| `ubuntu2604_timezone` | `UTC` | System timezone |
| `ubuntu2604_ssh_allow_root_login` | `false` | Root SSH policy for non-root provisioning |
| `ubuntu2604_ssh_allow_tcp_forwarding` | `false` | Allow SSH TCP forwarding |
| `ubuntu2604_ssh_port` | `22` | SSH service/socket listener port |

All public variables remain in [defaults/main.yml](../../roles/ubuntu2604/defaults/main.yml). Their precedence is **explicit Ansible input → saved settings → fallback defaults**.

## Persistence

The complete validated configuration, including defaults, is saved to `/etc/ansible/facts.d/ubuntu2604.fact` before application. Later runs need no repeated overrides; changed role defaults do not reset an existing host. Invalid input is rejected before writing. Failed application retains the desired settings for retry; `--check` never writes them.

The JSON keys omit the `ubuntu2604_` prefix. Boolean values and CLI port strings are normalized to booleans and integers. Unknown existing fact keys are retained. Older hostname-only files are supported; supply other existing custom settings once when upgrading.

Configuration processing uses `always`, including selective runs. Root SSH auto-preservation is a runtime rule and does not change the saved `ssh_allow_root_login` choice.

## `ubuntu2604_hostname`

Accepts a lowercase DNS hostname or FQDN: at most 64 characters total and 63 per label. Labels allow letters, digits, and internal hyphens; empty and non-string values are rejected.

| Input | Behavior |
|---|---|
| Explicit name | Validate, save, and apply it |
| Omitted, saved name exists | Reuse it |
| Omitted, no saved name | Fail before any configuration is written |

The public default resolves the saved name or an empty, invalid first-run value. The saved name is available as `ansible_facts['ansible_local']['ubuntu2604']['hostname']`.

The role manages the runtime/static hostname and the `127.0.1.1` hosts entry, including a short alias for FQDNs. When cloud-init is installed, a drop-in sets `preserve_hostname: true` and `manage_etc_hosts: false`.

```bash
ansible-playbook andreygubarev.com.ubuntu2604 --tags hostname -e ubuntu2604_hostname=worker-1.example.com
ansible-playbook andreygubarev.com.ubuntu2604 --tags hostname
```

## SSH policy

- Password authentication is disabled; the provisioning account must have non-empty authorized keys.
- Local root invocation or remote root SSH forces `PermitRootLogin yes`, even if the variable is `false`. Otherwise, `ubuntu2604_ssh_allow_root_login` controls the value. Sudo escalation alone does not enable root SSH.
- Hardening is applied through `/etc/ssh/sshd_config.d/00-ubuntu2604-hardening.conf` and validated with `sshd -t`.
- Crypto algorithms and minimum RSA key size use Ubuntu's OpenSSH defaults. ECDSA and RSA 2048 user keys, ECDH key exchange, AES-CTR, and HMAC-SHA2 remain compatible; the role does not enable DSA or RSA/SHA-1 signatures. The authorized-keys check only verifies a non-empty file, not successful authentication.
- The first SSH run replaces `/etc/ssh/ssh_host_*` with Ed25519, ECDSA P-256, and 4096-bit RSA keys. Verify the new fingerprints. The hardening drop-in is the first-run marker; removing it triggers regeneration. Existing role-managed hosts gain a missing ECDSA key without replacing their other host keys.

For remote port changes, connect on the current port while applying `ubuntu2604_ssh_port`, then update inventory `ansible_port`. The handler reloads systemd and restarts `ssh.socket` before `ssh.service`. Local execution needs no inventory update.

## Fixed host policy

| Area | Policy |
|---|---|
| Kernel | Persist `br_netfilter`, `nf_conntrack`, and `overlay`; tune networking, resource density, and panic recovery |
| Limits | PAM `nofile`/`nproc`: soft and hard `65536`; systemd `NOFILE`, `NPROC`, and `TasksMax`: `65536`; memory/task accounting enabled |
| Memory | Disable swap and fstab entries; transparent hugepages use `madvise` |
| APT | DEB822 sources at `archive.ubuntu.com` and `security.ubuntu.com` for amd64 and arm64; no provider detection |
| Upgrades | Safe upgrade and autoclean without autoremove; 10-minute APT lock timeout; report reboot requirements without rebooting |
| Unattended updates | Security timers enabled; automatic reboot, shutdown installs, and needrestart service restarts disabled |
| Logs | Persistent journald; 1 GiB cap, 30-day retention, 2 GiB free-space reserve on `/var/log`; volatile logs also bounded |
| Firewall | Enable nftables without global ruleset flushing, mask UFW, select nft-backed iptables tools; no filtering rules managed |
| Packages | Remove selected hardware agents, crash reporting, and interactive update helpers; retain Ubuntu Pro, `ubuntu-minimal`, storage/network integration, and administrative tools; install troubleshooting tools; no explicit Snap cleanup or reinstallation block |
| Time / DNS | Use the stock chrony service and systemd-resolved stub; fallback DNS `1.1.1.1`, `1.0.0.1` does not replace per-link resolvers |
| Login | Clear MOTD and mask `motd-news.timer` |

Exact values and package lists are defined in [numbered task files](../../roles/ubuntu2604/tasks/) and verified by [testinfra](../../roles/ubuntu2604/tests/test_ubuntu2604.py). The role does not manage application logrotate policy or replace the time-sync stack.

## Tags

| Tag | Scope |
|---|---|
| `hostname` | Hostname, hosts mapping, cloud-init policy |
| `kernel` | Modules, sysctls, PAM limits, transparent hugepages |
| `network` | Sysctls and prerequisite modules |
| `ssh` | SSH configuration, host keys, access checks |
| `systemd` | Manager limits and accounting |
| `swap` | Swap and fstab cleanup |
| `apt` | Sources, cache, package cleanup, upgrades, reboot reporting |
| `upgrade` | Safe upgrade, autoclean |
| `packages` | Installs, removals, upgrades, reboot reporting |
| `unattended_upgrades` | Security updates, reboot policy, needrestart |
| `logs` | Journald retention and disk-pressure controls |
| `firewall` | nftables, UFW, compatibility tools |
| `locale` | Locale generation and default |
| `time` | Timezone and chrony |
| `dns` | systemd-resolved and fallback DNS |
| `motd` | Login-message cleanup |

OS/architecture checks, the cloud-init barrier, and configuration validation/persistence use `always`; do not skip them.

[Quickstart](../getting-started/quickstart.md)
