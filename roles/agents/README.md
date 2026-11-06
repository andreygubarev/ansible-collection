# Agents

Installs the [Pi coding-agent harness](https://pi.dev/docs/latest/quickstart), [Claude Code](https://code.claude.com/docs/en/setup#install-with-npm), and the [BB server](https://github.com/get-bb/bb/blob/main/packages/bb-app/README.md) on Ubuntu 26.04 or Debian 13 with systemd. Applications belong to `agents_user`, which defaults to `agent`, and use its private npm prefix at `/home/agent/.local`. The role configures the login shell and BB service to prefer `/home/agent/.local/bin`. Applications can update without `sudo`.

Both distributions use NodeSource's signed Node.js 24 LTS package with bundled npm. Only the runtime and build prerequisites are system-wide. Archive keys are checksum-verified and scoped with `Signed-By`; no vendor setup scripts run. Use normal APT maintenance for runtime updates.

```bash
ansible-playbook andreygubarev.com.agents
sudo -iu agent pi --version
sudo -iu agent claude --version
```

## Account

Set `agents_user` to choose another account. The role creates its matching primary group, locked-password account, private `/home/<user>` directory, and Bash login shell. All application paths follow that account.

**The account has unrestricted passwordless sudo (`NOPASSWD: ALL`). Its agents can obtain root. It is for trusted workloads, not a security sandbox.** Application updates do not need those privileges.

## Versions and updates

- `agents_pi_version` defaults to `1.x`, selecting the newest stable Pi 1.x. An exact stable `1.x.y` version pins the npm installation.
- `agents_claude_code_version` defaults to `latest`. An exact stable version pins the npm installation.
- `agents_bb_version` defaults to `latest`. An exact stable version also disables in-app updates and forces the bundled launcher version.
- `agents_pi_web_access_version` defaults to `latest`. An exact stable version pins the Pi Web Access package.

Reapplying the role reconciles npm installations with these selectors. Unchanged versions are not reinstalled. Manual updates between applications are allowed, but a later application can replace them with the selected versions. npm registry access is required to resolve moving selectors. These npm installations do not lock transitive dependencies.

As the agent account, run `pi update` to update Pi, or `npm install --global --ignore-scripts '@earendil-works/pi-coding-agent@1'` to stay on 1.x. Use `npm install --global @anthropic-ai/claude-code@latest` for Claude Code. The account's `.npmrc` sets its private prefix and allows the native install scripts required by BB and Claude Code, preserving unrelated npm settings. Pi's lifecycle scripts are disabled during role installation.

BB's in-app updates are enabled with the default version selector. Use **Settings → Updates** or `bb updates app apply` as the agent account. BB stores these releases in `~/.bb/app-versions/` and selects them on subsequent starts. A pinned `agents_bb_version` bypasses those releases without deleting them.

BB package, unit, and runtime changes restart its service. Pi, Claude Code, and extension changes do not restart BB. Start a new Pi session to load updated resources.

## Authentication and Pi Web Access

The role does not authenticate providers or copy credentials. To authenticate Claude Code for BB, run `sudo -iu agent claude` and follow the login prompts. Pi uses `/home/agent/.pi/agent/`; its existing settings and credentials are preserved.

Installs [pi-web-access](https://github.com/nicobailon/pi-web-access) with `pi install` as the selected account, under `~/.pi/agent/npm/`. Pi merges the package entry into `settings.json`, preserving other packages and preferences. The role skips installation when both the package and its declaration already match.

The package adds web search, source checking, and URL fetching. The role does not configure a search provider, copy API keys, or overwrite `web-search.json`. Upstream supports keyless Exa search by default. Other providers can require configuration and credentials.

## BB service

The `bb.service` unit lives in `/home/agent/.config/systemd/user/`. Linger starts the user manager and BB at boot without an SSH login. BB survives logout and restarts after failures. Its database, configuration, and history live in `/home/agent/.bb`.

```bash
sudo -u agent env XDG_RUNTIME_DIR=/run/user/$(id -u agent) systemctl --user status bb.service
sudo -u agent env XDG_RUNTIME_DIR=/run/user/$(id -u agent) journalctl --user -u bb.service
```

BB listens only on `127.0.0.1:38886`. Its local API is unauthenticated. Do not expose it directly to the internet. Provider login and BB Connect account pairing are manual and must use the selected account. To sign this server in, run `sudo -iu agent bb account login` and approve it as a new server, not as a replacement for an existing BB instance.

The local playbook does not apply other roles or launch agent jobs. Apply `andreygubarev.com.ubuntu2604` or `andreygubarev.com.debian13` separately for baseline-first provisioning.
