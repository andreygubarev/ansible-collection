"""Verify user-local agents and updates without model calls."""

import json
import re

import pytest


@pytest.mark.parametrize("package", ("acl", "nodejs"))
def test_runtime_package_is_installed(host, package):
    assert host.package(package).is_installed


def test_npm_is_available_system_wide(host):
    assert host.file("/usr/bin/npm").exists
    assert re.fullmatch(r"[0-9]+[.][0-9]+[.][0-9]+", host.check_output("/usr/bin/npm --version"))
    assert not host.package("npm").is_installed


def test_node_24_lts_uses_the_scoped_nodesource_repository(host):
    assert host.check_output("/usr/bin/node --version").startswith("v24.")
    assert "nodesource" in host.package("nodejs").version
    source = host.file("/etc/apt/sources.list.d/agents-nodejs.sources")
    assert source.contains(r"^URIs: https://deb[.]nodesource[.]com/node_24[.]x$")
    assert source.contains(r"^Signed-By: /etc/apt/keyrings/agents-nodesource[.]asc$")


@pytest.fixture
def pi_package(agents_home):
    return f"{agents_home}/.local/lib/node_modules/@earendil-works/pi-coding-agent"


@pytest.fixture
def pi_metadata(host, pi_package):
    return json.loads(host.file(f"{pi_package}/package.json").content_string)


def test_pi_package_is_owned_by_the_agent(host, agents_user, pi_package, pi_metadata):
    package = host.file(f"{pi_package}/package.json")
    assert package.is_file
    assert package.user == agents_user
    assert pi_metadata["name"] == "@earendil-works/pi-coding-agent"
    assert re.fullmatch(r"1\.[0-9]+\.[0-9]+", pi_metadata["version"])


def test_pi_is_latest_stable_1x(host, pi_metadata):
    output = host.check_output(
        "/usr/bin/npm view '@earendil-works/pi-coding-agent@>=1.0.0 <2.0.0' version --json"
    )
    releases = json.loads(output)
    if isinstance(releases, str):
        releases = [releases]
    stable = [version for version in releases if re.fullmatch(r"1\.[0-9]+\.[0-9]+", version)]
    latest = max(stable, key=lambda version: tuple(int(part) for part in version.split(".")))
    assert pi_metadata["version"] == latest


def test_pi_cli_is_available_without_shell_initialization(host, agents_user, agents_home, pi_package, pi_metadata):
    cli = host.file(f"{agents_home}/.local/bin/pi")
    assert cli.is_symlink
    assert cli.user == agents_user
    assert cli.linked_to.startswith(f"{pi_package}/")
    result = host.run(
        "sudo -u %s -H env PATH=%s/.local/bin:/usr/local/bin:/usr/bin:/bin pi --version",
        agents_user, agents_home,
    )
    assert result.rc == 0, result.stderr
    assert result.stdout.strip() == pi_metadata["version"]


def test_pi_exposes_rpc_mode(host, agents_user, agents_home):
    result = host.run("sudo -u %s -H %s/.local/bin/pi --help", agents_user, agents_home)
    assert result.rc == 0, result.stderr
    assert "rpc" in result.stdout


def test_login_shell_prefers_user_local_commands(host, agents_user, agents_home):
    for command in ("pi", "claude", "bb", "bb-app"):
        assert host.check_output("sudo -iu %s command -v %s", agents_user, command) == f"{agents_home}/.local/bin/{command}"
    assert host.check_output("sudo -iu %s /usr/bin/npm prefix --global", agents_user) == f"{agents_home}/.local"
    npmrc = host.file(f"{agents_home}/.npmrc")
    assert npmrc.user == agents_user
    assert npmrc.mode == 0o600
    assert npmrc.contains(r"^allow-scripts=better-sqlite3,node-pty,@parcel/watcher,@anthropic-ai/claude-code$")


def test_agent_can_install_and_update_a_global_npm_command_without_sudo(host, agents_user):
    # Use real npm tarballs so the second install replaces files in the prefix,
    # rather than updating a symlink to a local source directory.
    script = r'''
        export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
        cd "$HOME"
        test "$(id -u)" -ne 0
        test "$(npm prefix --global)" = "$HOME/.local"
        workdir=$(mktemp -d)
        trap 'npm uninstall --global --ignore-scripts agents-update-smoke >/dev/null; rm -rf "$workdir"' EXIT
        mkdir "$workdir/package"
        for version in 1.0.0 1.0.1; do
            printf '{"name":"agents-update-smoke","version":"%s","bin":{"agents-update-smoke":"cli.sh"}}\n' \
                "$version" > "$workdir/package/package.json"
            printf '#!/bin/sh\nprintf "%%s\\n" "%s"\n' "$version" > "$workdir/package/cli.sh"
            chmod +x "$workdir/package/cli.sh"
            npm pack "$workdir/package" --pack-destination "$workdir" --silent >/dev/null
            npm install --global --ignore-scripts --no-audit --no-fund \
                "$workdir/agents-update-smoke-$version.tgz" >/dev/null
            test "$(agents-update-smoke)" = "$version"
        done
    '''
    result = host.run("sudo -u %s -H /bin/sh -eu -c %s", agents_user, script)
    assert result.rc == 0, result.stderr


def test_smoke_checks_do_not_configure_provider_credentials(host, agents_home):
    # Pi can initialize an empty auth file even for --help or --version.
    auth = host.file(f"{agents_home}/.pi/agent/auth.json")
    if auth.exists:
        assert not json.loads(auth.content_string)
