"""Production verification for the debian13 role."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from ansible.plugins.filter.core import FilterModule
from ansible.plugins.test.core import TestModule as AnsibleTestModule
from jinja2 import Environment


def grep_literal(value: str) -> str:
    """Escape a literal for the POSIX grep regexes used by File.contains()."""
    return re.sub(r"([][\\.^$*])", r"\\\1", value)


def locale_a_name(locale: str) -> str:
    return re.sub(r"utf-?8$", "utf8", locale.lower())


# -----------------------------------------------------------------------------
# Breadcrumbs
# -----------------------------------------------------------------------------


ROLE_SOURCE_URL = "https://github.com/andreygubarev/ansible-collection"
EXPECTED_BREADCRUMBED_FILES = (
    "/etc/modules-load.d/99-debian13-container.conf",
    "/etc/sysctl.d/99-debian13.conf",
    "/etc/security/limits.d/60-debian13-container.conf",
    "/etc/systemd/system/transparent-hugepages-madvise.service",
    "/etc/systemd/system.conf.d/60-debian13-density.conf",
    "/etc/apt/sources.list.d/debian.sources",
    "/etc/apt/apt.conf.d/20auto-upgrades",
    "/etc/apt/apt.conf.d/52debian13-unattended-upgrades",
    "/etc/needrestart/conf.d/99-debian13-no-auto-restarts.conf",
    "/etc/systemd/journald.conf.d/60-debian13-log-pressure.conf",
    "/etc/ssh/sshd_config.d/00-debian13-hardening.conf",
    "/etc/locale.conf",
    "/etc/systemd/resolved.conf.d/60-debian13-fallback-dns.conf",
)


@pytest.mark.parametrize("path", EXPECTED_BREADCRUMBED_FILES)
def test_role_owned_text_file_has_source_breadcrumb(host, path):
    config = host.file(path)

    assert config.exists
    assert config.contains(grep_literal(ROLE_SOURCE_URL))


# -----------------------------------------------------------------------------
# Configuration and hostname
# -----------------------------------------------------------------------------


SETTINGS_FACT = "/etc/ansible/facts.d/debian13.fact"
HOSTNAME_CLOUD_CONFIG = "/etc/cloud/cloud.cfg.d/99-debian13-hostname.cfg"
DEFAULT_OPTIONAL_SETTINGS = {
    "disable_ipv6": True,
    "locale": "en_US.UTF-8",
    "timezone": "UTC",
    "ssh_allow_root_login": False,
    "ssh_allow_tcp_forwarding": False,
    "ssh_port": 22,
}


@pytest.fixture
def configuration_contract():
    role = Path(__file__).resolve().parents[1]
    block = yaml.safe_load((role / "tasks/01-configuration.yml").read_text())[0]
    defaults = yaml.safe_load((role / "defaults/main.yml").read_text())
    environment = Environment()
    filters = FilterModule().filters()
    environment.filters.update({name: filters[name] for name in ("bool", "combine", "to_nice_json")})
    environment.tests["match"] = AnsibleTestModule().tests()["match"]
    return {task["name"]: task for task in block["block"]}, defaults, environment


@pytest.mark.parametrize(
    "saved, overrides, expected",
    (
        ({}, {"debian13_hostname": "node-1"}, {**DEFAULT_OPTIONAL_SETTINGS, "hostname": "node-1"}),
        (
            {"hostname": "saved-host", "ssh_port": 22022, "disable_ipv6": False},
            {},
            {**DEFAULT_OPTIONAL_SETTINGS, "hostname": "saved-host", "ssh_port": 22022, "disable_ipv6": False},
        ),
        (
            {"hostname": "old-host", "other_setting": "keep", "ssh_port": 22022},
            {"debian13_hostname": "new-host", "debian13_ssh_port": "022", "debian13_disable_ipv6": "0"},
            {**DEFAULT_OPTIONAL_SETTINGS, "hostname": "new-host", "other_setting": "keep", "disable_ipv6": False},
        ),
    ),
)
def test_configuration_precedence_and_complete_snapshot(configuration_contract, saved, overrides, expected):
    tasks, defaults, environment = configuration_contract
    assert set(defaults) == {"debian13_" + key for key in ["hostname", *DEFAULT_OPTIONAL_SETTINGS]}
    context = {"debian13__facts": saved}
    context.update({
        name: environment.compile_expression(value[2:-2].strip())(**context)
        for name, value in defaults.items()
    })
    context.update(overrides)
    expression = tasks["Configuration | Prepare complete settings snapshot"]["ansible.builtin.set_fact"]["debian13__vars"]
    actual = environment.compile_expression(expression.strip()[2:-2].strip())(**context)
    assert actual == expected
    assert type(actual["ssh_port"]) is int
    assert type(actual["disable_ipv6"]) is bool
    copy = tasks["Configuration | Save complete desired settings"]["ansible.builtin.copy"]
    assert copy["dest"] == SETTINGS_FACT
    assert json.loads(environment.from_string(copy["content"]).render(debian13__vars=actual)) == expected


@pytest.mark.parametrize(
    "task, name, value, valid",
    (
        ("Validate required hostname", "hostname", "node-1.example.com", True),
        ("Validate required hostname", "hostname", "", False),
        ("Validate required hostname", "hostname", False, False),
        ("Validate required hostname", "hostname", "Node-1", False),
        ("Validate required hostname", "hostname", "node..example.com", False),
        ("Validate required hostname", "hostname", "x" * 65, False),
        ("Validate string settings", "locale", "C.UTF-8", True),
        ("Validate string settings", "locale", "", False),
        ("Validate string settings", "timezone", None, False),
        ("Validate boolean settings", "disable_ipv6", False, True),
        ("Validate boolean settings", "disable_ipv6", "false", True),
        ("Validate boolean settings", "ssh_allow_root_login", "0", True),
        ("Validate boolean settings", "ssh_allow_tcp_forwarding", "invalid", False),
        ("Validate boolean settings", "disable_ipv6", "", False),
        ("Validate SSH port", "ssh_port", 22022, True),
        ("Validate SSH port", "ssh_port", "022", True),
        ("Validate SSH port", "ssh_port", 0, False),
        ("Validate SSH port", "ssh_port", 65536, False),
        ("Validate SSH port", "ssh_port", True, False),
    ),
)
def test_configuration_validation(configuration_contract, task, name, value, valid):
    tasks, _defaults, environment = configuration_contract
    public_name = "debian13_" + name
    context = {public_name: value, "item": public_name}
    context["lookup"] = lambda _plugin, key: context[key]
    conditions = tasks["Configuration | " + task]["ansible.builtin.assert"]["that"]
    assert all(environment.compile_expression(condition)(**context) for condition in conditions) is valid


@pytest.fixture
def saved_settings(host):
    fact = host.file(SETTINGS_FACT)
    assert fact.exists
    assert fact.user == "root"
    assert fact.group == "root"
    assert fact.mode == 0o644
    settings = json.loads(fact.content_string)
    expected_types = {"hostname": str, **{key: type(value) for key, value in DEFAULT_OPTIONAL_SETTINGS.items()}}
    for key, expected_type in expected_types.items():
        assert type(settings[key]) is expected_type
    return settings


@pytest.fixture
def saved_hostname(saved_settings):
    return saved_settings["hostname"]


def test_configured_hostname_is_persistent(host, saved_hostname):
    assert host.file("/etc/hostname").content_string.strip() == saved_hostname
    assert host.check_output("hostname") == saved_hostname


def test_configured_hostname_resolves_locally(host, saved_hostname):
    expected = [saved_hostname]
    if "." in saved_hostname:
        expected.append(saved_hostname.split(".")[0])
    entries = host.file("/etc/hosts").content_string.splitlines()

    assert any(line.split() == ["127.0.1.1", *expected] for line in entries)


def test_cloud_init_preserves_configured_hostname(host, saved_hostname):
    if not host.file("/usr/bin/cloud-init").exists:
        pytest.skip("cloud-init is not installed")
    config = host.file(HOSTNAME_CLOUD_CONFIG)

    assert config.contains(r"^preserve_hostname: true$")
    assert config.contains(r"^manage_etc_hosts: false$")


# -----------------------------------------------------------------------------
# Kernel
# -----------------------------------------------------------------------------


KERNEL_MODULES_CONFIG = "/etc/modules-load.d/99-debian13-container.conf"
SYSCTL_CONFIG = "/etc/sysctl.d/99-debian13.conf"
PAM_LIMITS_CONFIG = "/etc/security/limits.d/60-debian13-container.conf"
EXPECTED_KERNEL_MODULES = (
    "br_netfilter",
    "nf_conntrack",
    "overlay",
)


@pytest.mark.parametrize("module", EXPECTED_KERNEL_MODULES)
def test_container_kernel_module_is_loaded(host, module):
    assert host.file(f"/sys/module/{module}").is_directory


@pytest.mark.parametrize("module", EXPECTED_KERNEL_MODULES)
def test_container_kernel_module_is_persistent(host, module):
    assert host.file(KERNEL_MODULES_CONFIG).contains(rf"^{module}$")


EXPECTED_SYSCTLS = {
    "net.bridge.bridge-nf-call-arptables": "1",
    "net.bridge.bridge-nf-call-ip6tables": "1",
    "net.bridge.bridge-nf-call-iptables": "1",
    "fs.file-max": "2097152",
    "fs.inotify.max_queued_events": "32768",
    "fs.inotify.max_user_instances": "512",
    "fs.inotify.max_user_watches": "524288",
    "fs.nr_open": "2097152",
    "kernel.panic": "10",
    "kernel.panic_on_oops": "1",
    "kernel.pid_max": "4194304",
    "kernel.task_delayacct": "1",
    "net.core.netdev_max_backlog": "65536",
    "net.core.somaxconn": "65536",
    "net.ipv4.ip_forward": "1",
    "net.ipv4.ip_local_port_range": "1024 65535",
    "net.ipv4.ip_unprivileged_port_start": "0",
    "net.ipv4.neigh.default.gc_thresh1": "2048",
    "net.ipv4.neigh.default.gc_thresh2": "4096",
    "net.ipv4.neigh.default.gc_thresh3": "8192",
    "net.ipv4.tcp_fin_timeout": "15",
    "net.ipv4.tcp_keepalive_intvl": "30",
    "net.ipv4.tcp_keepalive_probes": "5",
    "net.ipv4.tcp_keepalive_time": "600",
    "net.ipv4.tcp_max_syn_backlog": "65536",
    "net.ipv4.tcp_syncookies": "1",
    "net.ipv4.tcp_tw_reuse": "1",
    "net.netfilter.nf_conntrack_max": "1048576",
    "user.max_user_namespaces": "15000",
    "vm.max_map_count": "262144",
    "vm.min_free_kbytes": "131072",
    "vm.overcommit_memory": "1",
    "vm.panic_on_oom": "0",
    "vm.swappiness": "10",
}


@pytest.mark.parametrize("name, expected", EXPECTED_SYSCTLS.items())
def test_runtime_sysctl_value(host, name, expected):
    assert " ".join(str(host.sysctl(name)).split()) == expected


@pytest.mark.parametrize("name, expected", EXPECTED_SYSCTLS.items())
def test_sysctl_value_is_persistent(host, name, expected):
    pattern = (
        f"^[[:space:]]*{grep_literal(name)}[[:space:]]*="
        f"[[:space:]]*{grep_literal(expected)}[[:space:]]*$"
    )

    assert host.file(SYSCTL_CONFIG).contains(pattern)


@pytest.mark.parametrize(
    "name, enabled_value",
    (
        ("net.ipv6.conf.all.disable_ipv6", 0),
        ("net.ipv6.conf.default.disable_ipv6", 0),
        ("net.ipv6.conf.lo.disable_ipv6", 0),
        ("net.ipv6.conf.all.accept_ra", 2),
        ("net.ipv6.conf.default.accept_ra", 2),
        ("net.ipv6.conf.all.forwarding", 1),
        ("net.ipv6.conf.default.forwarding", 1),
    ),
)
def test_saved_ipv6_policy_is_applied(host, saved_settings, name, enabled_value):
    disabled = saved_settings["disable_ipv6"]
    if not name.endswith("disable_ipv6") and disabled:
        pytest.skip("IPv6 routing settings are only managed when IPv6 is enabled")
    expected = str(int(disabled) if name.endswith("disable_ipv6") else enabled_value)
    assert str(host.sysctl(name)) == expected
    pattern = rf"^{grep_literal(name)}[[:space:]]*=[[:space:]]*{expected}$"
    assert host.file(SYSCTL_CONFIG).contains(pattern)


EXPECTED_PAM_LIMITS = (
    ("soft", "nofile", "65536"),
    ("hard", "nofile", "65536"),
    ("soft", "nproc", "65536"),
    ("hard", "nproc", "65536"),
)


@pytest.mark.parametrize("limit_type, name, expected", EXPECTED_PAM_LIMITS)
def test_pam_limit_is_configured(host, limit_type, name, expected):
    pattern = (
        rf"^\*[[:space:]][[:space:]]*{limit_type}[[:space:]][[:space:]]*{name}"
        rf"[[:space:]][[:space:]]*{expected}[[:space:]]*$"
    )

    assert host.file(PAM_LIMITS_CONFIG).contains(pattern)


def test_transparent_hugepages_service_is_active_and_enabled(host):
    service = host.service("transparent-hugepages-madvise.service")

    assert service.exists
    assert service.is_running
    assert service.is_enabled


def test_transparent_hugepages_mode_is_madvise(host):
    assert host.file("/sys/kernel/mm/transparent_hugepage/enabled").contains(
        r"\[madvise\]"
    )


# -----------------------------------------------------------------------------
# Systemd
# -----------------------------------------------------------------------------


SYSTEMD_DENSITY_CONFIG = "/etc/systemd/system.conf.d/60-debian13-density.conf"
EXPECTED_SYSTEMD_MANAGER_SETTINGS = {
    "DefaultLimitNOFILE": "65536",
    "DefaultLimitNPROC": "65536",
    "DefaultTasksMax": "65536",
    "DefaultMemoryAccounting": "yes",
    "DefaultTasksAccounting": "yes",
}


@pytest.mark.parametrize("name, expected", EXPECTED_SYSTEMD_MANAGER_SETTINGS.items())
def test_systemd_manager_density_setting_is_persistent(host, name, expected):
    pattern = (
        f"^{grep_literal(name)}[[:space:]]*="
        f"[[:space:]]*{grep_literal(expected)}[[:space:]]*$"
    )

    assert host.file(SYSTEMD_DENSITY_CONFIG).contains(pattern)


@pytest.mark.parametrize("name, expected", EXPECTED_SYSTEMD_MANAGER_SETTINGS.items())
def test_systemd_manager_density_setting_is_effective(host, name, expected):
    assert host.check_output(f"systemctl show --property={name} --value") == expected


def test_systemd_density_config_avoids_deprecated_cpu_accounting_default(host):
    assert not host.file(SYSTEMD_DENSITY_CONFIG).contains(
        r"^[[:space:]]*DefaultCPUAccounting[[:space:]]="
    )


# -----------------------------------------------------------------------------
# Swap
# -----------------------------------------------------------------------------


def test_no_swap_is_active(host):
    assert host.file("/proc/swaps").content_string.splitlines()[1:] == []


def test_fstab_has_no_active_swap_entries(host):
    swap_entry = (
        r"^[[:space:]]*[^#[:space:]][^[:space:]]*[[:space:]][[:space:]]*"
        r"[^[:space:]][^[:space:]]*[[:space:]][[:space:]]*swap[[:space:]][[:space:]]*"
    )

    assert not host.file("/etc/fstab").contains(swap_entry)


# -----------------------------------------------------------------------------
# APT
# -----------------------------------------------------------------------------


APT_SOURCES = "/etc/apt/sources.list.d/debian.sources"
APT_CONTAINER_WORKER_REMOVED_PACKAGES = (
    "modemmanager",
    "fwupd",
    "udisks2",
    "bolt",
)


def test_package_cleanup_is_limited_to_explicit_contract():
    role = Path(__file__).resolve().parents[1]
    tasks = yaml.safe_load((role / "tasks/22-package-cleanup.yml").read_text())
    apt_tasks = [task["ansible.builtin.apt"] for task in tasks if "ansible.builtin.apt" in task]

    assert len(apt_tasks) == 1
    assert set(apt_tasks[0]["name"]) == set(APT_CONTAINER_WORKER_REMOVED_PACKAGES)


@pytest.mark.parametrize("tasks_file", ("22-package-cleanup.yml", "23-package-upgrade.yml"))
def test_package_maintenance_does_not_autoremove_image_packages(tasks_file):
    role = Path(__file__).resolve().parents[1]
    tasks = yaml.safe_load((role / "tasks" / tasks_file).read_text())
    apt_tasks = [task["ansible.builtin.apt"] for task in tasks if "ansible.builtin.apt" in task]

    assert apt_tasks
    assert all(not task.get("autoremove", False) for task in apt_tasks)


def test_apt_sources_use_provider_neutral_official_endpoints(host):
    sources = host.file(APT_SOURCES)

    assert sources.exists
    assert sources.contains(r"^Types: deb$")
    assert sources.contains(r"^URIs: https://deb\.debian\.org/debian$")
    assert sources.contains(r"^URIs: https://security\.debian\.org/debian-security$")
    assert sources.contains(r"^Suites: trixie trixie-updates$")
    assert sources.contains(r"^Suites: trixie-security$")
    assert sources.contains(r"^Components: main$")
    assert sources.contains(r"^Signed-By: /usr/share/keyrings/debian-archive-keyring\.gpg$")


@pytest.mark.parametrize("package", APT_CONTAINER_WORKER_REMOVED_PACKAGES)
def test_container_worker_irrelevant_package_is_removed(host, package):
    assert not host.package(package).is_installed


# -----------------------------------------------------------------------------
# Unattended upgrades
# -----------------------------------------------------------------------------


UNATTENDED_AUTO_UPGRADES = "/etc/apt/apt.conf.d/20auto-upgrades"
UNATTENDED_REBOOT_POLICY = "/etc/apt/apt.conf.d/52debian13-unattended-upgrades"
NEEDRESTART_POLICY = "/etc/needrestart/conf.d/99-debian13-no-auto-restarts.conf"
EXPECTED_UNATTENDED_AUTO_UPGRADES = {
    "APT::Periodic::Update-Package-Lists": "1",
    "APT::Periodic::Unattended-Upgrade": "1",
    "APT::Periodic::Download-Upgradeable-Packages": "1",
    "APT::Periodic::AutocleanInterval": "7",
}
EXPECTED_UNATTENDED_REBOOT_POLICY = {
    "Unattended-Upgrade::Automatic-Reboot": "false",
    "Unattended-Upgrade::Automatic-Reboot-WithUsers": "false",
    "Unattended-Upgrade::InstallOnShutdown": "false",
}
EXPECTED_UNATTENDED_TIMERS = (
    "apt-daily.timer",
    "apt-daily-upgrade.timer",
)


def test_unattended_upgrades_package_is_installed(host):
    assert host.package("unattended-upgrades").is_installed


@pytest.mark.parametrize("name, expected", EXPECTED_UNATTENDED_AUTO_UPGRADES.items())
def test_periodic_unattended_upgrade_setting_is_enabled(host, name, expected):
    pattern = (
        f"^{grep_literal(name)}[[:space:]][[:space:]]*"
        f'"{grep_literal(expected)}";[[:space:]]*$'
    )

    assert host.file(UNATTENDED_AUTO_UPGRADES).contains(pattern)


@pytest.mark.parametrize("name, expected", EXPECTED_UNATTENDED_REBOOT_POLICY.items())
def test_unattended_reboot_behavior_is_disabled(host, name, expected):
    pattern = (
        f"^{grep_literal(name)}[[:space:]][[:space:]]*"
        f'"{grep_literal(expected)}";[[:space:]]*$'
    )

    assert host.file(UNATTENDED_REBOOT_POLICY).contains(pattern)


def test_needrestart_is_configured_for_list_only_mode(host):
    assert host.file(NEEDRESTART_POLICY).contains(
        r"^\$nrconf{restart}[[:space:]]*=[[:space:]]*'l';$"
    )


@pytest.mark.parametrize("timer", EXPECTED_UNATTENDED_TIMERS)
def test_apt_maintenance_timer_is_active_and_enabled(host, timer):
    service = host.service(timer)

    assert service.exists
    assert service.is_enabled
    assert service.is_running


# -----------------------------------------------------------------------------
# Logs
# -----------------------------------------------------------------------------


JOURNALD_CONFIG = "/etc/systemd/journald.conf.d/60-debian13-log-pressure.conf"
EXPECTED_JOURNALD_SETTINGS = {
    "Storage": "persistent",
    "Compress": "yes",
    "SystemMaxUse": "1G",
    "SystemMaxFileSize": "128M",
    "MaxRetentionSec": "30day",
    "MaxFileSec": "1week",
    "SystemKeepFree": "2G",
    "RuntimeMaxUse": "256M",
    "RuntimeKeepFree": "512M",
}


@pytest.mark.parametrize("name, expected", EXPECTED_JOURNALD_SETTINGS.items())
def test_journald_pressure_setting_is_persistent(host, name, expected):
    pattern = (
        f"^{grep_literal(name)}[[:space:]]*="
        f"[[:space:]]*{grep_literal(expected)}[[:space:]]*$"
    )

    assert host.file(JOURNALD_CONFIG).contains(pattern)


def test_persistent_journal_directory_is_configured(host):
    journal_dir = host.file("/var/log/journal")

    assert journal_dir.is_directory
    assert journal_dir.user == "root"
    assert journal_dir.group == "systemd-journal"
    assert journal_dir.mode == 0o2755


def test_systemd_journald_service_is_running(host):
    service = host.service("systemd-journald")

    assert service.exists
    assert service.is_running


# -----------------------------------------------------------------------------
# Firewall
# -----------------------------------------------------------------------------


EXPECTED_FIREWALL_PACKAGES = (
    "conntrack",
    "iptables",
    "nftables",
)
EXPECTED_NFT_COMPAT_COMMANDS = (
    ("iptables", "nf_tables"),
    ("ip6tables", "nf_tables"),
    ("arptables", "nf_tables"),
    ("ebtables", "nf_tables"),
)


@pytest.mark.parametrize("package", EXPECTED_FIREWALL_PACKAGES)
def test_firewall_package_is_installed(host, package):
    assert host.package(package).is_installed


def test_nftables_service_is_active_and_enabled(host):
    service = host.service("nftables")

    assert service.exists
    assert service.is_running
    assert service.is_enabled


def test_nftables_loader_does_not_flush_other_owners_tables(host):
    assert not host.file("/etc/nftables.conf").contains(r"^[[:space:]]*flush[[:space:]][[:space:]]*ruleset")
    assert host.check_output("systemctl show nftables --property=ExecStop --value").strip() == ""
    dropin = host.file("/etc/systemd/system/nftables.service.d/10-preserve-tables.conf")
    assert dropin.user == "root" and dropin.mode == 0o644


def test_ufw_service_is_masked(host):
    link = host.file("/etc/systemd/system/ufw.service")

    assert link.is_symlink
    assert link.linked_to == "/dev/null"


@pytest.mark.parametrize("command, expected_backend", EXPECTED_NFT_COMPAT_COMMANDS)
def test_iptables_compatibility_command_uses_nft_backend(host, command, expected_backend):
    assert expected_backend in host.check_output(f"{command} --version")


# -----------------------------------------------------------------------------
# Packages
# -----------------------------------------------------------------------------


EXPECTED_OPERATION_PACKAGES = (
    "bind9-dnsutils",
    "curl",
    "exip",
    "htop",
    "iotop",
    "jq",
    "less",
    "lsof",
    "tcpdump",
    "tmux",
    "traceroute",
    "tree",
    "unzip",
    "wget",
)


@pytest.mark.parametrize("package", EXPECTED_OPERATION_PACKAGES)
def test_operation_package_is_installed(host, package):
    assert host.package(package).is_installed


# -----------------------------------------------------------------------------
# SSH
# -----------------------------------------------------------------------------


SSHD_CONFIG = "/etc/ssh/sshd_config"
SSHD_HARDENING_CONFIG = "/etc/ssh/sshd_config.d/00-debian13-hardening.conf"
EXPECTED_SSHD_HARDENING_SETTINGS = (
    ("LogLevel", "loglevel", "VERBOSE"),
    ("X11Forwarding", "x11forwarding", "no"),
    ("MaxAuthTries", "maxauthtries", "3"),
    ("IgnoreRhosts", "ignorerhosts", "yes"),
    ("HostbasedAuthentication", "hostbasedauthentication", "no"),
    ("PermitEmptyPasswords", "permitemptypasswords", "no"),
    ("PermitUserEnvironment", "permituserenvironment", "no"),
    ("ClientAliveInterval", "clientaliveinterval", "300"),
    ("ClientAliveCountMax", "clientalivecountmax", "3"),
    ("LoginGraceTime", "logingracetime", "60"),
    ("Banner", "banner", "none"),
    ("UsePAM", "usepam", "yes"),
    ("MaxStartups", "maxstartups", "10:30:60"),
    ("MaxSessions", "maxsessions", "3"),
    ("PubkeyAuthentication", "pubkeyauthentication", "yes"),
    ("PasswordAuthentication", "passwordauthentication", "no"),
)


def sshd_effective_config(host):
    return {
        line.split(None, 1)[0]: line.split(None, 1)[1]
        for line in host.check_output("sshd -T").splitlines()
        if line.strip()
    }


@pytest.mark.parametrize(
    "user, allow_root_login, expected",
    (
        ("root", False, "yes"),
        ("root", True, "yes"),
        ("root", "false", "yes"),
        ("ubuntu", False, "no"),
        ("ubuntu", True, "yes"),
        ("ubuntu", "false", "no"),
    ),
)
def test_root_ssh_login_policy_rendering(user, allow_root_login, expected):
    tasks_file = Path(__file__).resolve().parents[1] / "tasks/62-ssh-config.yml"
    tasks = yaml.safe_load(tasks_file.read_text())
    content = next(
        task["ansible.builtin.copy"]["content"]
        for task in tasks
        if task.get("ansible.builtin.copy", {}).get("dest") == SSHD_HARDENING_CONFIG
    )
    directive = next(
        line for line in content.splitlines() if line.startswith("PermitRootLogin ")
    )
    environment = Environment()
    environment.filters.update(FilterModule().filters())

    rendered = environment.from_string(directive).render(
        debian13__ssh_user=user,
        debian13_ssh_allow_root_login=allow_root_login,
    )

    assert rendered == f"PermitRootLogin {expected}"


def test_role_does_not_override_openssh_crypto_defaults():
    role = Path(__file__).resolve().parents[1]
    tasks = yaml.safe_load((role / "tasks/62-ssh-config.yml").read_text())
    content = next(
        task["ansible.builtin.copy"]["content"]
        for task in tasks
        if task.get("ansible.builtin.copy", {}).get("dest") == SSHD_HARDENING_CONFIG
    )
    directives = {line.split()[0].lower() for line in content.splitlines() if line.strip()}

    assert directives.isdisjoint({
        "kexalgorithms", "ciphers", "macs", "requiredrsasize", "hostkeyalgorithms",
        "casignaturealgorithms", "gssapikexalgorithms", "hostbasedacceptedalgorithms",
        "pubkeyacceptedalgorithms",
    })


@pytest.mark.parametrize(
    "setting, algorithms",
    (
        ("kexalgorithms", {"ecdh-sha2-nistp256", "ecdh-sha2-nistp384", "ecdh-sha2-nistp521"}),
        ("ciphers", {"aes128-ctr", "aes192-ctr", "aes256-ctr"}),
        ("macs", {"hmac-sha2-256", "hmac-sha2-512"}),
        ("hostkeyalgorithms", {"ecdsa-sha2-nistp256", "ssh-ed25519", "rsa-sha2-256", "rsa-sha2-512"}),
        ("pubkeyacceptedalgorithms", {"ecdsa-sha2-nistp256", "ssh-ed25519", "rsa-sha2-256", "rsa-sha2-512"}),
    ),
)
def test_sshd_crypto_policy_supports_existing_clients(host, setting, algorithms):
    assert algorithms <= set(sshd_effective_config(host)[setting].split(","))


def test_sshd_accepts_rsa_2048_without_sha1_signatures(host):
    config = sshd_effective_config(host)

    assert int(config["requiredrsasize"]) <= 2048
    assert "ssh-rsa" not in config["pubkeyacceptedalgorithms"].split(",")


def test_root_ssh_login_policy_is_effective(host):
    directive = re.search(
        r"^PermitRootLogin[ \t]+(yes|no)$",
        host.file(SSHD_HARDENING_CONFIG).content_string,
        re.MULTILINE,
    )

    assert directive is not None
    assert sshd_effective_config(host)["permitrootlogin"] == directive.group(1)


def test_openssh_server_package_is_installed(host):
    assert host.package("openssh-server").is_installed


def test_ssh_service_is_active_and_enabled(host):
    service = host.service("ssh")

    assert service.exists
    assert service.is_running
    assert service.is_enabled


def test_sshd_is_listening_on_saved_port(host, saved_settings):
    assert host.socket(f"tcp://0.0.0.0:{saved_settings['ssh_port']}").is_listening


def test_sshd_config_permissions(host):
    config = host.file(SSHD_CONFIG)

    assert config.exists
    assert config.user == "root"
    assert config.group == "root"
    assert config.mode == 0o600


def test_sshd_config_loads_dropins(host):
    assert host.file(SSHD_CONFIG).contains(
        r"^Include /etc/ssh/sshd_config\.d/\*\.conf$"
    )


def test_sshd_hardening_dropin_permissions(host):
    config = host.file(SSHD_HARDENING_CONFIG)

    assert config.exists
    assert config.user == "root"
    assert config.group == "root"
    assert config.mode == 0o644


def test_sshd_hardening_dropin_has_no_obsolete_protocol_directive(host):
    assert not host.file(SSHD_HARDENING_CONFIG).contains(
        r"^[[:space:]]*Protocol[[:space:]]"
    )


@pytest.mark.parametrize(
    "directive, _effective_key, expected", EXPECTED_SSHD_HARDENING_SETTINGS
)
def test_sshd_hardening_setting_is_persistent(host, directive, _effective_key, expected):
    pattern = rf"^{directive}[[:space:]][[:space:]]*{grep_literal(expected)}$"

    assert host.file(SSHD_HARDENING_CONFIG).contains(pattern)


@pytest.mark.parametrize(
    "_directive, effective_key, expected", EXPECTED_SSHD_HARDENING_SETTINGS
)
def test_sshd_hardening_setting_is_effective(host, _directive, effective_key, expected):
    assert sshd_effective_config(host)[effective_key] == expected


@pytest.mark.parametrize(
    "directive, effective_key, setting",
    (("Port", "port", "ssh_port"), ("AllowTcpForwarding", "allowtcpforwarding", "ssh_allow_tcp_forwarding")),
)
def test_saved_sshd_setting_is_applied(host, saved_settings, directive, effective_key, setting):
    value = saved_settings[setting]
    expected = ("yes" if value else "no") if isinstance(value, bool) else str(value)
    assert host.file(SSHD_HARDENING_CONFIG).contains(rf"^{directive}[[:space:]]*{expected}$")
    assert sshd_effective_config(host)[effective_key] == expected


EXPECTED_SSH_HOST_KEYS = (
    ("/etc/ssh/ssh_host_ed25519_key", "256", "(ED25519)"),
    ("/etc/ssh/ssh_host_ecdsa_key", "256", "(ECDSA)"),
    ("/etc/ssh/ssh_host_rsa_key", "4096", "(RSA)"),
)


@pytest.mark.parametrize("path, bits, key_type", EXPECTED_SSH_HOST_KEYS)
def test_ssh_host_key_type_and_size(host, path, bits, key_type):
    key = host.file(path)

    assert key.is_file
    details = host.check_output("ssh-keygen -lf %s", path).split()
    assert details[0] == bits
    assert details[-1] == key_type


def test_ssh_private_host_key_permissions(host):
    paths = host.check_output(
        "find /etc/ssh -maxdepth 1 -type f -name 'ssh_host_*_key' ! -name '*.pub' "
        "-print"
    ).splitlines()

    assert paths
    for path in paths:
        key = host.file(path)
        assert key.user == "root"
        assert key.group == "root"
        assert key.mode == 0o600


def test_ssh_public_host_key_permissions(host):
    paths = host.check_output(
        "find /etc/ssh -maxdepth 1 -type f -name 'ssh_host_*.pub' -print"
    ).splitlines()

    assert paths
    for path in paths:
        key = host.file(path)
        assert key.user == "root"
        assert key.group == "root"
        assert key.mode == 0o644


# -----------------------------------------------------------------------------
# Locale
# -----------------------------------------------------------------------------


def test_locales_package_is_installed(host):
    assert host.package("locales").is_installed


def test_configured_locale_is_generated(host, saved_settings):
    generated_locales = {
        locale_a_name(line) for line in host.check_output("locale -a").splitlines()
    }

    assert locale_a_name(saved_settings["locale"]) in generated_locales


def test_default_locale_is_configured(host, saved_settings):
    assert host.file("/etc/locale.conf").contains(
        f"^LANG={grep_literal(saved_settings['locale'])}$"
    )


# -----------------------------------------------------------------------------
# Time
# -----------------------------------------------------------------------------

def test_saved_timezone_is_applied(host, saved_settings):
    assert host.check_output("timedatectl show --property=Timezone --value").strip() == saved_settings["timezone"]


def test_chrony_package_is_installed(host):
    assert host.package("chrony").is_installed


def test_chrony_service_is_active_and_enabled(host):
    service = host.service("chrony")

    assert service.exists
    assert service.is_running
    assert service.is_enabled


# -----------------------------------------------------------------------------
# DNS
# -----------------------------------------------------------------------------

EXPECTED_FALLBACK_DNS = (
    "1.1.1.1",
    "1.0.0.1",
)


def test_systemd_resolved_is_active_and_enabled(host):
    service = host.service("systemd-resolved")

    assert service.exists
    assert service.is_running
    assert service.is_enabled


def test_resolv_conf_uses_systemd_stub(host):
    resolv = host.file("/etc/resolv.conf")

    assert resolv.is_symlink
    assert resolv.linked_to == "/run/systemd/resolve/stub-resolv.conf"


@pytest.mark.parametrize("address", EXPECTED_FALLBACK_DNS)
def test_fallback_dns_is_configured(host, address):
    dropin = host.file(
        "/etc/systemd/resolved.conf.d/60-debian13-fallback-dns.conf"
    )

    assert dropin.exists
    assert dropin.contains(
        rf"^FallbackDNS=.*\b{re.escape(address)}\b.*$"
    )


# -----------------------------------------------------------------------------
# MOTD
# -----------------------------------------------------------------------------

def test_update_motd_d_is_empty(host):
    d = host.file("/etc/update-motd.d")
    assert d.is_directory
    assert d.listdir() == []


def test_motd_is_empty(host):
    motd = host.file("/etc/motd")
    assert motd.exists
    assert motd.content_string == ""
