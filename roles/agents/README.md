# Agents

Installs the [Pi coding-agent harness](https://pi.dev/docs/latest/quickstart), [Claude Code](https://code.claude.com/docs/en/setup#install-with-npm), and the [BB server](https://github.com/get-bb/bb/blob/main/packages/bb-app/README.md), in that order, on Ubuntu 26.04 or Debian 13 with systemd. All three applications are installed system-wide under `/usr/local` and are available without shell initialization.

Ubuntu uses distro Node.js and npm. Debian uses NodeSource's signed Node.js 24 LTS package with bundled npm. Archive keys are checksum-verified and scoped with `Signed-By`; no vendor setup scripts run. The repository does not extend unattended-upgrades' allowed origins. Use normal APT maintenance for vendor runtime updates.

```bash
ansible-playbook andreygubarev.com.agents
pi --version
claude --version
```

## Versions

- `agents_pi_version` defaults to `1.x` (`>=1.0.0 <2.0.0`, excluding prereleases). Each application selects the newest stable Pi 1.x; an exact stable `1.x.y` version pins it instead.
- `agents_claude_code_version` defaults to `latest`, resolving the npm stable tag on each run. An exact stable version pins Claude Code instead.
- `agents_bb_version` defaults to `latest`, resolving the npm stable tag on each run. An exact stable version pins BB instead.
- `agents_pi_web_access_version` defaults to `latest`; an exact stable version pins the Pi Web Access package instead.

Unchanged versions are not reinstalled. npm registry access is required to resolve moving selectors. These npm installations do not lock transitive dependencies. Pi's lifecycle scripts are disabled; Claude Code's are enabled to link its platform binary from an optional dependency, and BB's are enabled because its SQLite, PTY and watcher add-ons require native binaries. Build prerequisites are installed for hosts without matching prebuilt binaries.

## Claude Code

The root-owned npm installation exposes `claude` in `/usr/local/bin`, including for the BB service. The role does not run Claude sessions, configure credentials, or modify user settings. To authenticate for BB, run `sudo -iu bb claude` and follow the login prompts. Reapply the role to update the system-wide package; Claude Code updates do not restart BB.

## Pi Web Access

Installs [pi-web-access](https://github.com/nicobailon/pi-web-access) with `pi install` as `bb`, under `/home/bb/.pi/agent/npm/`. Pi merges the package entry into the user's `settings.json`; other packages and preferences are preserved. The role resolves an exact version and skips installation when both the package and its declaration already match.

The package adds web search, source checking and URL fetching. The role does not configure a search provider, copy API keys or overwrite `web-search.json`. Upstream supports keyless Exa search by default; other providers can require separate configuration and credentials. Pi/package updates do not restart BB; use a new Pi session to load updated resources.

## BB account and service

BB runs as the dedicated `bb` user, with a locked login password and private home `/home/bb`. **This account has unrestricted passwordless sudo (`NOPASSWD: ALL`): its agents can obtain root. It is for trusted workloads, not a security sandbox.**

The `bb.service` unit lives in `/home/bb/.config/systemd/user/`. Linger is enabled so the user manager and BB start at boot without an SSH login, survive logout, and restart after failures. The system-wide installation is root-owned; BB's database, configuration and history live in `/home/bb/.bb`. Pi uses `/home/bb/.pi/agent/`. Existing state and provider credentials are not overwritten.

```bash
sudo -u bb env XDG_RUNTIME_DIR=/run/user/$(id -u bb) systemctl --user status bb.service
sudo -u bb env XDG_RUNTIME_DIR=/run/user/$(id -u bb) journalctl --user -u bb.service
```

BB listens only on `127.0.0.1:38886`. Its local API is unauthenticated: do not expose it directly to the internet. Provider login and BB Connect account pairing are manual and must be performed as `bb`; the role never copies credentials or pairs an account automatically. To sign this server in, run `sudo -iu bb bb account login` and approve it as a **new server**, not as a replacement for an existing BB instance.

In-app BB updates are disabled so Ansible controls the installed version. Reapplying the role upgrades BB when needed and restarts the user service on package or unit changes.

The local playbook does not apply other roles or launch agent jobs. For baseline-first provisioning, apply `andreygubarev.com.ubuntu2604` or `andreygubarev.com.debian13` separately before `andreygubarev.com.agents`.
