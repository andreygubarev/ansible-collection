"""Verify Pi and the persistent BB user service without model calls."""

import json
import re

import pytest


@pytest.mark.parametrize("package", ("acl", "nodejs"))
def test_runtime_package_is_installed(host, package):
    assert host.package(package).is_installed


def test_npm_is_available_system_wide(host):
    assert host.file("/usr/bin/npm").exists
    assert re.fullmatch(r"[0-9]+[.][0-9]+[.][0-9]+", host.check_output("/usr/bin/npm --version"))
    if host.system_info.distribution == "ubuntu":
        assert host.package("npm").is_installed
        assert not host.file("/etc/apt/sources.list.d/agents-nodejs.sources").exists
    else:
        assert host.check_output("/usr/bin/node --version").startswith("v24.")
        assert host.file("/etc/apt/sources.list.d/agents-nodejs.sources").contains(
            r"^Signed-By: /etc/apt/keyrings/agents-nodesource[.]asc$"
        )


def test_node_version_supports_pi(host):
    version = host.check_output("/usr/bin/node --version").lstrip("v")
    assert tuple(int(part) for part in version.split(".")) >= (22, 19, 0)


PI_PACKAGE = "/usr/local/lib/node_modules/@earendil-works/pi-coding-agent"


@pytest.fixture
def pi_metadata(host):
    return json.loads(host.file(f"{PI_PACKAGE}/package.json").content_string)


def test_pi_package_is_installed_system_wide(host, pi_metadata):
    package = host.file(f"{PI_PACKAGE}/package.json")
    assert package.is_file
    assert package.user == "root"
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


def test_pi_cli_is_available_without_shell_initialization(host, pi_metadata):
    cli = host.file("/usr/local/bin/pi")
    assert cli.is_symlink
    assert cli.user == "root"
    assert cli.linked_to.startswith(f"{PI_PACKAGE}/")
    result = host.run("sudo -u bb -H env PATH=/usr/local/bin:/usr/bin:/bin pi --version")
    assert result.rc == 0, result.stderr
    assert result.stdout.strip() == pi_metadata["version"]


def test_pi_exposes_rpc_mode(host):
    result = host.run("sudo -u bb -H /usr/local/bin/pi --help")
    assert result.rc == 0, result.stderr
    assert "rpc" in result.stdout


def test_smoke_checks_do_not_configure_provider_credentials(host):
    # Pi can initialize an empty auth file even for --help or --version.
    auth = host.file("/home/bb/.pi/agent/auth.json")
    if auth.exists:
        assert not json.loads(auth.content_string)
