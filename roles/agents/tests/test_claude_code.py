"""Verify user-local Claude Code without credentials or model calls."""

import json
import re

import pytest


@pytest.fixture
def claude_code_package(agents_home):
    return f"{agents_home}/.local/lib/node_modules/@anthropic-ai/claude-code"


@pytest.fixture
def claude_code_metadata(host, claude_code_package):
    return json.loads(host.file(f"{claude_code_package}/package.json").content_string)


def test_claude_code_package_is_owned_by_the_agent(host, agents_user, claude_code_package, claude_code_metadata):
    package = host.file(f"{claude_code_package}/package.json")
    assert package.is_file
    assert package.user == agents_user
    assert claude_code_metadata["name"] == "@anthropic-ai/claude-code"
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", claude_code_metadata["version"])


def test_claude_code_is_latest_stable(host, claude_code_metadata):
    latest = json.loads(
        host.check_output("/usr/bin/npm view @anthropic-ai/claude-code@latest version --json")
    )
    assert claude_code_metadata["version"] == latest


def test_claude_code_cli_is_available_without_shell_initialization(
    host, agents_user, agents_home, claude_code_package, claude_code_metadata,
):
    cli = host.file(f"{agents_home}/.local/bin/claude")
    assert cli.is_symlink
    assert cli.user == agents_user
    assert cli.linked_to.startswith(f"{claude_code_package}/")
    result = host.run(
        "sudo -u %s -H env PATH=%s/.local/bin:/usr/local/bin:/usr/bin:/bin claude --version",
        agents_user, agents_home,
    )
    assert result.rc == 0, result.stderr
    assert result.stdout.strip() == f"{claude_code_metadata['version']} (Claude Code)"


def test_claude_code_smoke_checks_do_not_configure_credentials(host, agents_home):
    assert not host.file(f"{agents_home}/.claude/.credentials.json").exists
