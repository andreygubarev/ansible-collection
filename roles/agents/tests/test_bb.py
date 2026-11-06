"""Verify BB runs as a lingering systemd user service, not as root."""

import json

import pytest


def test_agent_account_is_locked_and_has_passwordless_sudo(host, agents_user, agents_home):
    user = host.user(agents_user)
    assert user.exists
    assert user.uid != 0
    assert user.group == agents_user
    assert user.home == agents_home
    assert user.shell == "/bin/bash"
    assert host.check_output("passwd -S %s", agents_user).split()[1] == "L"
    assert host.check_output("sudo -u %s -H sudo -n id -u", agents_user) == "0"
    sudoers = host.file(f"/etc/sudoers.d/90-agents-{agents_user}")
    assert sudoers.user == "root"
    assert sudoers.mode == 0o440
    assert host.run("visudo -cf %s", sudoers.path).rc == 0


@pytest.mark.parametrize("path", ("", "/.bb", "/.local", "/.local/bin", "/.local/lib"))
def test_agent_application_directories_are_private(host, agents_user, agents_home, path):
    directory = host.file(f"{agents_home}{path}")
    assert directory.is_directory
    assert directory.user == agents_user
    assert directory.group == agents_user
    assert directory.mode == 0o700


@pytest.fixture
def bb_package(agents_home):
    return f"{agents_home}/.local/lib/node_modules/bb-app"


def test_bb_package_is_current_stable_and_user_owned(host, agents_user, agents_home, bb_package):
    package = host.file(f"{bb_package}/package.json")
    assert package.user == agents_user
    metadata = json.loads(package.content_string)
    assert metadata["name"] == "bb-app"
    latest = json.loads(host.check_output("/usr/bin/npm view bb-app@latest version --json"))
    assert metadata["version"] == latest
    for command in ("bb", "bb-app"):
        cli = host.file(f"{agents_home}/.local/bin/{command}")
        assert cli.is_symlink
        assert cli.user == agents_user
        assert cli.linked_to.startswith(f"{bb_package}/")


def test_bb_native_addons_work_with_the_current_node_runtime(host, agents_user, bb_package):
    script = f"""
        const requireBB = require('node:module').createRequire('{bb_package}/package.json');
        const db = new (requireBB('better-sqlite3'))(':memory:');
        require('node:assert/strict').equal(db.prepare('SELECT 1').pluck().get(), 1);
        db.close();
        requireBB('node-pty');
        requireBB('@parcel/watcher');
    """
    result = host.run("sudo -u %s -H /usr/bin/node -e %s", agents_user, script)
    assert result.rc == 0, result.stderr


@pytest.fixture
def bb_systemctl(host, agents_user):
    uid = host.user(agents_user).uid
    return (
        f"sudo -u {agents_user} env XDG_RUNTIME_DIR=/run/user/{uid} "
        f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus "
        "/usr/bin/systemctl --user"
    )


def test_bb_user_manager_runs_without_a_login(host, agents_user):
    assert host.file(f"/var/lib/systemd/linger/{agents_user}").exists
    assert host.check_output("loginctl show-user %s --property=Linger --value", agents_user) == "yes"
    assert host.service(f"user@{host.user(agents_user).uid}.service").is_running


@pytest.mark.parametrize("command, expected", (("is-enabled", "enabled"), ("is-active", "active")))
def test_bb_user_service_is_enabled_and_running(host, bb_systemctl, command, expected):
    assert host.check_output(f"{bb_systemctl} {command} bb.service") == expected


def test_bb_service_has_restart_policy_and_correct_owner(host, bb_systemctl, agents_user, agents_home):
    assert host.check_output(f"{bb_systemctl} show bb.service --property=Restart --value") == "on-failure"
    pid = int(host.check_output(f"{bb_systemctl} show bb.service --property=MainPID --value"))
    assert pid > 0
    assert host.check_output("ps -o user= -p %s", str(pid)).strip() == agents_user
    assert host.check_output("/proc/%s/exe --version", str(pid)) == host.check_output("/usr/bin/node --version")
    unit = host.file(f"{agents_home}/.config/systemd/user/bb.service")
    assert unit.user == agents_user
    assert not host.file("/etc/systemd/system/bb.service").exists
    environment = host.check_output(f"{bb_systemctl} show bb.service --property=Environment --value")
    assert f"PATH={agents_home}/.local/bin:/usr/local/bin:/usr/bin:/bin" in environment
    command = host.check_output(f"{bb_systemctl} show bb.service --property=ExecStart --value")
    assert f"{agents_home}/.local/bin/bb-app" in command


def test_bb_reports_in_app_updates_are_supported(host, agents_user):
    status = json.loads(host.check_output("sudo -iu %s bb updates app status --json", agents_user))
    assert status["support"]["kind"] == "supported"
    assert status["support"]["mode"] == "npm"


def test_bb_web_interface_is_only_on_loopback(host):
    assert host.socket("tcp://127.0.0.1:38886").is_listening
    assert not host.socket("tcp://0.0.0.0:38886").is_listening
    assert not host.socket("tcp://:::38886").is_listening
    assert host.check_output(
        "curl --fail --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:38886/"
    ) == "200"


def test_bb_local_executor_is_running_and_state_is_persistent(host, agents_user, agents_home):
    assert host.socket("tcp://127.0.0.1:38887").is_listening
    database = host.file(f"{agents_home}/.bb/bb.db")
    assert database.is_file
    assert database.user == agents_user
