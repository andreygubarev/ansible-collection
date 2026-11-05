"""Verify BB runs as a lingering systemd user service, not as root."""

import json

import pytest


def test_bb_account_is_locked_and_has_passwordless_sudo(host):
    user = host.user("bb")
    assert user.exists
    assert user.uid != 0
    assert user.group == "bb"
    assert user.home == "/home/bb"
    assert user.shell == "/bin/bash"
    assert host.check_output("passwd -S bb").split()[1] == "L"
    assert host.check_output("sudo -u bb -H sudo -n id -u") == "0"
    sudoers = host.file("/etc/sudoers.d/90-agents-bb")
    assert sudoers.user == "root"
    assert sudoers.mode == 0o440
    assert host.run("visudo -cf /etc/sudoers.d/90-agents-bb").rc == 0


@pytest.mark.parametrize("path", ("/home/bb", "/home/bb/.bb"))
def test_bb_state_directories_are_private(host, path):
    directory = host.file(path)
    assert directory.is_directory
    assert directory.user == "bb"
    assert directory.group == "bb"
    assert directory.mode == 0o700


BB_PACKAGE = "/usr/local/lib/node_modules/bb-app"


def test_bb_package_is_current_stable_and_root_owned(host):
    package = host.file(f"{BB_PACKAGE}/package.json")
    assert package.user == "root"
    metadata = json.loads(package.content_string)
    assert metadata["name"] == "bb-app"
    latest = json.loads(host.check_output("/usr/bin/npm view bb-app@latest version --json"))
    assert metadata["version"] == latest
    for command in ("bb", "bb-app"):
        cli = host.file(f"/usr/local/bin/{command}")
        assert cli.is_symlink
        assert cli.user == "root"
        assert cli.linked_to.startswith(f"{BB_PACKAGE}/")


def test_bb_native_addons_work_with_the_current_node_runtime(host):
    script = f"""
        const requireBB = require('node:module').createRequire('{BB_PACKAGE}/package.json');
        const db = new (requireBB('better-sqlite3'))(':memory:');
        require('node:assert/strict').equal(db.prepare('SELECT 1').pluck().get(), 1);
        db.close();
        requireBB('node-pty');
        requireBB('@parcel/watcher');
    """
    result = host.run("sudo -u bb -H /usr/bin/node -e %s", script)
    assert result.rc == 0, result.stderr


@pytest.fixture
def bb_systemctl(host):
    uid = host.user("bb").uid
    return (
        f"sudo -u bb env XDG_RUNTIME_DIR=/run/user/{uid} "
        f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus "
        "/usr/bin/systemctl --user"
    )


def test_bb_user_manager_runs_without_a_login(host):
    assert host.file("/var/lib/systemd/linger/bb").exists
    assert host.check_output("loginctl show-user bb --property=Linger --value") == "yes"
    assert host.service(f"user@{host.user('bb').uid}.service").is_running


@pytest.mark.parametrize("command, expected", (("is-enabled", "enabled"), ("is-active", "active")))
def test_bb_user_service_is_enabled_and_running(host, bb_systemctl, command, expected):
    assert host.check_output(f"{bb_systemctl} {command} bb.service") == expected


def test_bb_service_has_restart_policy_and_correct_owner(host, bb_systemctl):
    assert host.check_output(f"{bb_systemctl} show bb.service --property=Restart --value") == "on-failure"
    pid = int(host.check_output(f"{bb_systemctl} show bb.service --property=MainPID --value"))
    assert pid > 0
    assert host.check_output("ps -o user= -p %s", str(pid)).strip() == "bb"
    assert host.check_output("/proc/%s/exe --version", str(pid)) == host.check_output("/usr/bin/node --version")
    assert host.file("/home/bb/.config/systemd/user/bb.service").user == "bb"
    assert not host.file("/etc/systemd/system/bb.service").exists


def test_bb_web_interface_is_only_on_loopback(host):
    assert host.socket("tcp://127.0.0.1:38886").is_listening
    assert not host.socket("tcp://0.0.0.0:38886").is_listening
    assert not host.socket("tcp://:::38886").is_listening
    assert host.check_output(
        "curl --fail --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:38886/"
    ) == "200"


def test_bb_local_executor_is_running_and_state_is_persistent(host):
    assert host.socket("tcp://127.0.0.1:38887").is_listening
    database = host.file("/home/bb/.bb/bb.db")
    assert database.is_file
    assert database.user == "bb"
