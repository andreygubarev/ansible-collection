# andreygubarev.com.debian13

Debian 13 container-worker VM baseline for amd64 and arm64. Requires ansible-core ≥ 2.20 and root or sudo access.

```bash
ansible-playbook andreygubarev.com.debian13 -e debian13_hostname=worker-1
```

Runs locally without applying other roles. SSH authorized keys are required; the first application replaces image-provided SSH host keys. Later applications preserve host identity.

All public settings are in [defaults/main.yml](defaults/main.yml). Explicit inputs override saved values, then defaults. The complete validated configuration is stored in `/etc/ansible/facts.d/debian13.fact`; hostname is required once. IPv6 defaults to disabled, locale to `en_US.UTF-8`, timezone to `UTC`, and administrative SSH to port `22` with key-only authentication.

The role configures official Debian archives, security update timers, container kernel/networking defaults, systemd/PAM limits, bounded persistent logging, chrony, and systemd-resolved. It preserves unrelated APT repositories and package data. `needrestart` reports kernel status; reboots remain manual. The nftables loader preserves other components' tables and does not define host filtering policy.

Kubernetes, Terraform tooling, GitOps, and agents remain independently applicable. Debian's containerd 2.x and Node.js 24 LTS vendor repositories are configured by the roles that need them, not this baseline. Ubuntu-to-Debian migration is not performed.

[Task index](tasks/main.yml) · [Verification](tests/test_debian13.py)
