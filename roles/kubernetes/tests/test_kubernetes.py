"""Production verification for the kubernetes role."""

from __future__ import annotations

import json
import re
import socket
import time
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from ansible.plugins.filter.core import FilterModule
from ansible.plugins.test.core import TestModule as AnsibleTestModule
from jinja2 import Environment


def grep_literal(value: str) -> str:
    """Escape a literal for the POSIX grep regexes used by File.contains()."""
    return re.sub(r"([][\\.^$*])", r"\\\1", value)


# -----------------------------------------------------------------------------
# Supported platforms
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("role", ("ubuntu2604", "debian13", "kubernetes", "terraform", "agents"))
@pytest.mark.parametrize("distribution, version, major, allowed", (
    ("Ubuntu", "26.04", "26", {"ubuntu2604", "kubernetes", "terraform", "agents"}),
    ("Debian", "13", "13", {"debian13", "kubernetes", "terraform", "agents"}),
    ("Debian", "13.7", "13", {"debian13", "kubernetes", "terraform", "agents"}),
    ("Ubuntu", "24.04", "24", set()),
    ("Debian", "12.9", "12", set()),
))
def test_platform_preflight_contract(role, distribution, version, major, allowed):
    path = Path(__file__).resolve().parents[2] / role / "tasks/00-prerequisites.yml"
    conditions = yaml.safe_load(path.read_text())[0]["ansible.builtin.assert"]["that"]
    facts = {"distribution": distribution, "distribution_version": version, "distribution_major_version": major}
    environment = Environment()
    actual = all(environment.compile_expression(condition)(ansible_facts=facts) for condition in conditions)
    assert actual is (role in allowed)


@pytest.mark.parametrize("packages, accepted", (
    ({}, True), ({"containerd.io": [{}]}, True), ({"containerd": [{}]}, False), ({"runc": [{}]}, False),
))
def test_debian_runtime_conflicts_require_explicit_migration(packages, accepted):
    path = Path(__file__).resolve().parents[1] / "tasks/00-prerequisites.yml"
    block = next(task["block"] for task in yaml.safe_load(path.read_text()) if "block" in task)
    conditions = block[-1]["ansible.builtin.assert"]["that"]
    environment = Environment()
    actual = all(environment.compile_expression(condition)(ansible_facts={"packages": packages}) for condition in conditions)
    assert actual is accepted


# -----------------------------------------------------------------------------
# Configuration and local facts
# -----------------------------------------------------------------------------


SETTINGS_FACT = "/etc/ansible/facts.d/kubernetes.fact"
DEFAULT_CLUSTER_SETTINGS = {
    "cluster_name": "my-cluster",
    "kubernetes_version": "1.37",
    "advertise_address": "10.0.0.10",
    "pod_subnet": "10.244.0.0/16",
    "service_subnet": "10.96.0.0/16",
    "kubeconfig_user": "ubuntu",
    "apiserver_gogc": "50",
    "apiserver_gomemlimit": "",
    "flannel_manifest_url": "https://github.com/flannel-io/flannel/releases/download/v0.28.10/kube-flannel.yml",
    "metrics_server_version": "v0.9.1",
    "k9s_version": "0.51.0",
    "coredns_rewrites": {},
}


@pytest.fixture
def configuration_contract():
    role = Path(__file__).resolve().parents[1]
    tasks = yaml.safe_load((role / "tasks/01-configuration.yml").read_text())[0]["block"]
    defaults = yaml.safe_load((role / "defaults/main.yml").read_text())
    environment = Environment()
    filters = FilterModule().filters()
    environment.filters.update({
        name: filters[name]
        for name in ("combine", "to_nice_json", "from_json", "to_json", "regex_findall", "regex_replace", "regex_search")
    })
    environment.tests["match"] = AnsibleTestModule().tests()["match"]

    def resolve(saved, overrides):
        context = {
            "kubernetes__facts": saved,
            "ansible_facts": {"default_ipv4": {"address": "10.0.0.10"}},
            "ansible_user": "ubuntu",
        }
        context.update({
            name: environment.compile_expression(value.strip()[2:-2].strip())(**context)
            for name, value in defaults.items()
        })
        context.update(overrides)
        return context

    return role, tasks, {task["name"]: task for task in tasks}, environment, resolve


@pytest.mark.parametrize(
    "saved_name, overrides, expected, accepted",
    (
        (None, {}, "", False),
        (None, {"kubernetes_cluster_name": "my-cluster"}, "my-cluster", True),
        ("my-cluster", {}, "my-cluster", True),
        ("kubernetes", {}, "kubernetes", True),
        ("my-cluster", {"kubernetes_cluster_name": "my-cluster"}, "my-cluster", True),
        ("my-cluster", {"kubernetes_cluster_name": "other-cluster"}, "other-cluster", False),
        ("my-cluster", {"kubernetes_cluster_name": ""}, "", False),
        (None, {"kubernetes_cluster_name": "   "}, "   ", False),
        (None, {"kubernetes_cluster_name": False}, False, False),
        (None, {"kubernetes_cluster_name": 0}, 0, False),
        (None, {"kubernetes_cluster_name": None}, None, False),
    ),
)
def test_cluster_name_required_and_immutable_policy(
    configuration_contract, saved_name, overrides, expected, accepted
):
    _role, _ordered, tasks, environment, resolve = configuration_contract
    saved = {} if saved_name is None else {
        "cluster_name": saved_name,
        "kubernetes_version": "1.37",
        "pod_subnet": "10.244.0.0/16",
        "service_subnet": "10.96.0.0/16",
    }
    context = resolve(saved, overrides)
    assert context["kubernetes_cluster_name"] == expected
    assert type(context["kubernetes_cluster_name"]) is type(expected)
    conditions = tasks["Configuration | Validate required cluster name"]["ansible.builtin.assert"]["that"]
    valid = all(environment.compile_expression(condition)(**context) for condition in conditions)
    if valid and saved:
        conditions = tasks["Configuration | Assert immutable cluster identity matches stored facts"]["ansible.builtin.assert"]["that"]
        valid = all(environment.compile_expression(condition)(**context) for condition in conditions)
    assert valid is accepted


def test_complete_settings_snapshot_and_validation_order(configuration_contract):
    role, ordered, tasks, environment, resolve = configuration_contract
    saved = {"cluster_name": "my-cluster", "kubernetes_version": "1.36", "other_setting": "keep"}
    context = resolve(saved, {"kubernetes_apiserver_gogc": "", "kubernetes_k9s_version": "0.50.9"})
    expected = {**DEFAULT_CLUSTER_SETTINGS, **saved, "apiserver_gogc": "", "k9s_version": "0.50.9"}
    expression = tasks["Configuration | Prepare complete settings snapshot"]["ansible.builtin.set_fact"]["kubernetes__vars"]
    actual = environment.compile_expression(expression.strip()[2:-2].strip())(**context)
    assert actual == expected
    names = [task["name"] for task in ordered]
    for check in (
        "Configuration | Validate required cluster name",
        "Configuration | Assert immutable cluster identity matches stored facts",
        "Configuration | Validate k9s version",
        "Configuration | Validate CoreDNS rewrites mapping",
        "Configuration | Validate CoreDNS rewrite names",
        "Configuration | Validate IPv4 cluster networking",
        "Configuration | Read kubeconfig owner account",
    ):
        assert names.index(check) < names.index("Configuration | Ensure local facts directory exists")
    copy = tasks["Configuration | Save complete desired settings"]["ansible.builtin.copy"]
    assert copy["dest"] == SETTINGS_FACT
    content = environment.from_string(copy["content"]).render(
        ansible_facts={"ansible_local": {"kubernetes": {"other_section": {"keep": True}}}},
        kubernetes__vars=actual,
    )
    assert json.loads(content) == {
        "cluster": expected,
        "_source": "https://github.com/andreygubarev/ansible-collection",
        "other_section": {"keep": True},
    }
    defaults = yaml.safe_load((role / "defaults/main.yml").read_text())
    assert len(defaults) == 12 and "kubernetes_cluster_name" in defaults


@pytest.mark.parametrize(
    "version, accepted",
    (("0.51.0", True), ("0.50.9", True), ("v0.51.0", False), ("latest", False),
     ("0.51", False), ("0.51.0-rc1", False), ("", False), (False, False)),
)
def test_k9s_version_validation(configuration_contract, version, accepted):
    _role, _ordered, tasks, environment, resolve = configuration_contract
    context = resolve({}, {"kubernetes_k9s_version": version})
    context["item"] = "kubernetes_k9s_version"
    context["lookup"] = lambda _plugin, key: context[key]
    required = tasks["Configuration | Validate required string settings"]["ansible.builtin.assert"]["that"]
    exact = tasks["Configuration | Validate k9s version"]["ansible.builtin.assert"]["that"]
    assert all(environment.compile_expression(condition)(**context) for condition in required + exact) is accepted


@pytest.mark.parametrize("rewrites, accepted", (({}, True), ([], False), ("", False), (None, False), (False, False)))
def test_coredns_rewrites_require_mapping(configuration_contract, rewrites, accepted):
    _role, _ordered, tasks, environment, resolve = configuration_contract
    context = resolve({}, {"kubernetes_coredns_rewrites": rewrites})
    conditions = tasks["Configuration | Validate CoreDNS rewrites mapping"]["ansible.builtin.assert"]["that"]
    assert all(environment.compile_expression(condition)(**context) for condition in conditions) is accepted


@pytest.mark.parametrize(
    "source, target, accepted",
    (
        ("git.example.com", "gateway.edge.svc.cluster.local", True),
        ("git-1.example.com", "gateway-1.edge.svc.cluster.local", True),
        ("git.example.com.", "gateway.edge.svc.cluster.local", False),
        ("Git.example.com", "gateway.edge.svc.cluster.local", False),
        ("git.example.com", "gateway.edge.svc.cluster.local\n", False),
        ("git.example.com\n", "gateway.edge.svc.cluster.local", False),
        ("*.example.com", "gateway.edge.svc.cluster.local", False),
        ("git.example.com", "10.96.0.10", False),
        ("git.example.com", "https://gateway.edge.svc.cluster.local", False),
        ("git.example.com", "git.example.com", False),
        ("git.example.com", "gateway.edge.svc.cluster.local }", False),
        ("a" * 64 + ".example.com", "gateway.edge.svc.cluster.local", False),
        ("git.example.com", None, False),
        (False, "gateway.edge.svc.cluster.local", False),
    ),
)
def test_coredns_rewrite_name_validation(configuration_contract, source, target, accepted):
    _role, _ordered, tasks, environment, resolve = configuration_contract
    context = resolve({}, {})
    task = tasks["Configuration | Validate CoreDNS rewrite names"]
    context.update(task["vars"])
    context["item"] = {"key": source, "value": target}
    conditions = task["ansible.builtin.assert"]["that"]
    assert all(environment.compile_expression(condition)(**context) for condition in conditions) is accepted


@pytest.mark.parametrize("override", (None, {}, {"new.example.com": "new.edge.svc.cluster.local"}))
def test_coredns_saved_rewrites_and_explicit_replacement(configuration_contract, override):
    _role, _ordered, tasks, environment, resolve = configuration_contract
    saved = {"coredns_rewrites": {"old.example.com": "old.edge.svc.cluster.local"}}
    overrides = {} if override is None else {"kubernetes_coredns_rewrites": override}
    context = resolve(saved, overrides)
    expected = saved["coredns_rewrites"] if override is None else override
    assert context["kubernetes_coredns_rewrites"] == expected
    expression = tasks["Configuration | Prepare complete settings snapshot"]["ansible.builtin.set_fact"]["kubernetes__vars"]
    snapshot = environment.compile_expression(expression.strip()[2:-2].strip())(**context)
    assert snapshot["coredns_rewrites"] == expected


@pytest.mark.parametrize("gogc, limit", (("50", ""), ("", ""), ("", "1536MiB"), ("0", "off")))
def test_optional_gc_settings_are_preserved(configuration_contract, gogc, limit):
    role, _ordered, _tasks, environment, resolve = configuration_contract
    context = resolve(
        {**DEFAULT_CLUSTER_SETTINGS, "apiserver_gogc": gogc, "apiserver_gomemlimit": limit}, {}
    )
    context["kubernetes__kubeadm_version"] = {"stdout": "v1.37.1"}
    tasks = yaml.safe_load((role / "tasks/50-kubeadm-config.yml").read_text())
    template = next(task["ansible.builtin.copy"]["content"] for task in tasks if "ansible.builtin.copy" in task)
    documents = yaml.safe_load_all(environment.from_string(template).render(**context))
    cluster = next(document for document in documents if document["kind"] == "ClusterConfiguration")
    expected = {name: value for name, value in (("GOGC", gogc), ("GOMEMLIMIT", limit)) if value != ""}
    actual = {item["name"]: item["value"] for item in cluster["apiServer"].get("extraEnvs", [])}
    assert actual == expected
    assert cluster["clusterName"] == "my-cluster"


@pytest.fixture
def saved_settings(host):
    fact = host.file(SETTINGS_FACT)
    assert fact.exists
    assert fact.user == "root" and fact.group == "root"
    assert fact.mode == 0o644
    settings = json.loads(fact.content_string)["cluster"]
    assert isinstance(settings["coredns_rewrites"], dict)
    for key in DEFAULT_CLUSTER_SETTINGS.keys() - {"coredns_rewrites"}:
        assert isinstance(settings[key], str)
        if key not in ("apiserver_gogc", "apiserver_gomemlimit"):
            assert settings[key]
    return settings


# -----------------------------------------------------------------------------
# Breadcrumbs
# -----------------------------------------------------------------------------


ROLE_SOURCE_URL = "https://github.com/andreygubarev/ansible-collection"
EXPECTED_BREADCRUMBED_FILES = (
    "/etc/ansible/facts.d/kubernetes.fact",
    "/etc/modules-load.d/99-kubernetes.conf",
    "/etc/sysctl.d/99-kubernetes.conf",
    "/etc/containerd/config.toml",
    "/etc/containerd/conf.d/99-kubernetes.toml",
    "/etc/apt/sources.list.d/kubernetes.sources",
    "/etc/kubernetes/kubeadm-config.yaml",
    "/etc/nftables.d/kubernetes.nft",
    "/etc/systemd/system/kubernetes-firewall.service",
)


@pytest.mark.parametrize("path", EXPECTED_BREADCRUMBED_FILES)
def test_role_owned_text_file_has_source_breadcrumb(host, path):
    config = host.file(path)

    assert config.exists
    assert config.contains(grep_literal(ROLE_SOURCE_URL))


# -----------------------------------------------------------------------------
# Kubernetes endpoint protection
# -----------------------------------------------------------------------------


EXTERNAL_BLOCKED_TCP_PORTS = (2379, 2380, 6443, 10250, 10256)


def test_firewall_service_is_active_and_enabled(host, saved_settings):
    assert host.package("nftables").is_installed
    service = host.service("kubernetes-firewall")
    assert service.is_running and service.is_enabled
    assert host.socket(f"tcp://{saved_settings['advertise_address']}:6443").is_listening


@pytest.mark.parametrize("port", EXTERNAL_BLOCKED_TCP_PORTS)
def test_node_internal_ports_are_unreachable_from_test_runner(host, saved_settings, port):
    # This socket runs on the pytest runner, not through host.run() on the node.
    with pytest.raises((TimeoutError, ConnectionRefusedError)):
        socket.create_connection((saved_settings["advertise_address"], port), timeout=1).close()


def test_new_external_ssh_connection_is_preserved(host, saved_settings):
    baseline = {"ubuntu": "ubuntu2604", "debian": "debian13"}[host.system_info.distribution]
    settings = json.loads(host.file(f"/etc/ansible/facts.d/{baseline}.fact").content_string)
    with socket.create_connection((saved_settings["advertise_address"], settings["ssh_port"]), timeout=3) as connection:
        assert connection.recv(256).startswith(b"SSH-2.0-")


def test_pods_retain_api_dns_and_kubelet_access(host, saved_settings):
    name = "firewall-probe-" + uuid4().hex[:12]
    kubectl = "kubectl --kubeconfig /etc/kubernetes/admin.conf"
    script = (
        'token=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token); '
        'test "$(curl --max-time 15 --silent --show-error '
        '--cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt '
        '-H "Authorization: Bearer $token" -o /dev/null -w "%{http_code}" '
        'https://kubernetes.default.svc/version)" = 200; '
        'test "$(curl --max-time 15 --silent --show-error --insecure '
        '-o /dev/null -w "%{http_code}" '
        f'https://{saved_settings["advertise_address"]}:10250/healthz)" = 401'
    )
    try:
        host.check_output(
            kubectl + " run %s --image=curlimages/curl:8.23.0 --restart=Never --command -- sh -ec %s",
            name, script,
        )
        result = host.run(kubectl + " wait --for=jsonpath='{.status.phase}'=Succeeded pod/%s --timeout=180s", name)
        assert result.rc == 0, host.run(kubectl + " logs %s", name).stdout + result.stderr
    finally:
        host.run(kubectl + " delete pod %s --ignore-not-found --wait=false", name)


def test_metrics_collection_reaches_the_kubelet(host):
    for _ in range(30):
        result = host.run("kubectl --kubeconfig /etc/kubernetes/admin.conf top nodes --no-headers")
        if result.rc == 0:
            assert result.stdout.strip() and "<unknown>" not in result.stdout
            return
        time.sleep(2)
    pytest.fail(result.stderr)


def test_firewall_ipv6_udp_spoofing_and_forwarding(host):
    # Run real listeners and clients in disposable namespaces, using the installed
    # rules file. No cluster service has to be stopped to test an occupied port.
    probe = Path(__file__).with_name("probe_firewall.py").read_text()
    result = host.run("python3 -c %s", probe)
    assert result.rc == 0, result.stdout + result.stderr
    assert "firewall boundary checks passed" in result.stdout


# -----------------------------------------------------------------------------
# Kernel and swap
# -----------------------------------------------------------------------------


KERNEL_MODULES_CONFIG = "/etc/modules-load.d/99-kubernetes.conf"
SYSCTL_CONFIG = "/etc/sysctl.d/99-kubernetes.conf"
EXPECTED_KERNEL_MODULES = (
    "overlay",
    "br_netfilter",
)
EXPECTED_SYSCTLS = {
    "net.bridge.bridge-nf-call-iptables": "1",
    "net.bridge.bridge-nf-call-ip6tables": "1",
    "net.ipv4.ip_forward": "1",
}


@pytest.mark.parametrize("module", EXPECTED_KERNEL_MODULES)
def test_kubernetes_kernel_module_is_loaded(host, module):
    assert host.file(f"/sys/module/{module}").is_directory


@pytest.mark.parametrize("module", EXPECTED_KERNEL_MODULES)
def test_kubernetes_kernel_module_is_persistent(host, module):
    assert host.file(KERNEL_MODULES_CONFIG).contains(rf"^{module}$")


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


def test_no_swap_is_active(host):
    assert host.file("/proc/swaps").content_string.splitlines()[1:] == []


def test_fstab_has_no_active_swap_entries(host):
    swap_entry = (
        r"^[[:space:]]*[^#[:space:]][^[:space:]]*[[:space:]][[:space:]]*"
        r"[^[:space:]][^[:space:]]*[[:space:]][[:space:]]*swap[[:space:]][[:space:]]*"
    )

    assert not host.file("/etc/fstab").contains(swap_entry)


# -----------------------------------------------------------------------------
# Containerd
# -----------------------------------------------------------------------------


EXPECTED_CONTAINERD_PACKAGES = (
    "containernetworking-plugins",
)


@pytest.mark.parametrize("package", EXPECTED_CONTAINERD_PACKAGES)
def test_containerd_package_is_installed(host, package):
    assert host.package(package).is_installed


def test_containerd_package_and_version_match_platform_contract(host):
    debian = host.system_info.distribution == "debian"
    assert host.package("containerd.io" if debian else "containerd").is_installed
    assert re.search(r" v?2[.]", host.check_output("containerd --version"))
    if debian:
        assert not host.package("containerd").is_installed
        assert not host.package("runc").is_installed
        assert not host.package("docker-ce").is_installed
        source = host.file("/etc/apt/sources.list.d/kubernetes-containerd.sources")
        assert source.contains(r"^Signed-By: /etc/apt/keyrings/kubernetes-docker[.]asc$")
        assert source.contains(r"^Suites: trixie$")
        assert host.file("/etc/apt/preferences.d/90-kubernetes-containerd").contains(r"^Pin: version 2[.][*]$")
    else:
        assert not host.file("/etc/apt/sources.list.d/kubernetes-containerd.sources").exists


def test_containerd_service_is_active_and_enabled(host):
    service = host.service("containerd")

    assert service.exists
    assert service.is_running
    assert service.is_enabled


def test_containerd_imports_role_dropins(host):
    config = host.file("/etc/containerd/config.toml")

    assert config.contains(r"^version[[:space:]]*=[[:space:]]*3$")
    assert config.contains(
        r'^imports[[:space:]]*=[[:space:]]*\["/etc/containerd/conf\.d/\*\.toml"\]$'
    )


def test_containerd_uses_systemd_cgroups(host):
    config = host.file("/etc/containerd/conf.d/99-kubernetes.toml")

    assert config.contains(r"^[[:space:]]*SystemdCgroup[[:space:]]*=[[:space:]]*true$")


def test_containerd_uses_kubernetes_pause_image(host):
    config = host.file("/etc/containerd/conf.d/99-kubernetes.toml")

    assert config.contains(
        r'^[[:space:]]*sandbox[[:space:]]*=[[:space:]]*"registry\.k8s\.io/pause:3\.10\.2"$'
    )


# -----------------------------------------------------------------------------
# Kubernetes packages
# -----------------------------------------------------------------------------


EXPECTED_KUBERNETES_PACKAGES = (
    "kubeadm",
    "kubectl",
    "kubelet",
)


@pytest.mark.parametrize("package", EXPECTED_KUBERNETES_PACKAGES)
def test_kubernetes_package_is_installed(host, package):
    assert host.package(package).is_installed


@pytest.mark.parametrize("package", EXPECTED_KUBERNETES_PACKAGES)
def test_kubernetes_package_is_held(host, package):
    assert package in host.check_output("apt-mark showhold").splitlines()


def test_kubernetes_repository_is_configured(host):
    source = host.file("/etc/apt/sources.list.d/kubernetes.sources")

    assert source.exists
    assert source.contains(r"^Types: deb$")
    # BRE-safe quantifiers: testinfra contains() runs plain grep, where + is literal.
    assert source.contains(r"^URIs: https://pkgs\.k8s\.io/core:/stable:/v[0-9][0-9]*\.[0-9][0-9]*/deb/$")
    assert source.contains(r"^Suites: /$")
    assert source.contains(r"^Signed-By: /etc/apt/keyrings/kubernetes\.asc$")


# -----------------------------------------------------------------------------
# K9s
# -----------------------------------------------------------------------------


def test_k9s_package_matches_saved_version(host, saved_settings):
    package = host.package("k9s")
    assert package.is_installed
    assert package.version == saved_settings["k9s_version"]
    binary = host.file("/usr/bin/k9s")
    assert binary.is_file
    assert binary.user == "root" and binary.group == "root"
    assert binary.mode == 0o755


def test_k9s_reports_saved_version(host, saved_settings):
    assert "v" + saved_settings["k9s_version"] in host.check_output("/usr/bin/k9s version --short")


# -----------------------------------------------------------------------------
# Cluster
# -----------------------------------------------------------------------------


KUBEADM_CONFIG = "/etc/kubernetes/kubeadm-config.yaml"


def kubeadm_cluster_configuration(host):
    return next(
        document for document in yaml.safe_load_all(host.file(KUBEADM_CONFIG).content_string)
        if document["kind"] == "ClusterConfiguration"
    )


def test_kubeadm_admin_config_exists(host):
    config = host.file("/etc/kubernetes/admin.conf")

    assert config.exists
    assert config.user == "root"
    assert config.group == "root"


def test_kubeadm_config_uses_systemd_cgroups(host):
    assert host.file(KUBEADM_CONFIG).contains(r"^cgroupDriver: systemd$")


def test_kubeadm_config_records_saved_cluster_identity(host, saved_settings):
    config = kubeadm_cluster_configuration(host)
    assert config["clusterName"] == saved_settings["cluster_name"]
    assert config["controlPlaneEndpoint"] == saved_settings["advertise_address"] + ":6443"
    assert config["networking"]["podSubnet"] == saved_settings["pod_subnet"]
    assert config["networking"]["serviceSubnet"] == saved_settings["service_subnet"]


def test_kube_proxy_preserves_host_conntrack_limit(host):
    desired = next(
        document for document in yaml.safe_load_all(host.file(KUBEADM_CONFIG).content_string)
        if document["kind"] == "KubeProxyConfiguration"
    )
    assert desired["conntrack"]["maxPerCore"] == 0

    deployed = yaml.safe_load(host.check_output(
        "kubectl --kubeconfig /etc/kubernetes/admin.conf "
        "get configmap kube-proxy -n kube-system -o jsonpath='{.data.config\\.conf}'"
    ))
    assert deployed["conntrack"]["maxPerCore"] == 0


def test_kubeadm_config_pins_kubernetes_version(host):
    assert host.file(KUBEADM_CONFIG).contains(
        r'^kubernetesVersion: "v[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*"$'
    )


@pytest.mark.parametrize("name, setting", (("GOGC", "apiserver_gogc"), ("GOMEMLIMIT", "apiserver_gomemlimit")))
def test_saved_apiserver_gc_settings_are_applied(host, saved_settings, name, setting):
    expected = saved_settings[setting] or None
    config = kubeadm_cluster_configuration(host)
    configured = {item["name"]: item["value"] for item in config["apiServer"].get("extraEnvs", [])}
    assert configured.get(name) == expected

    manifest = yaml.safe_load(host.file("/etc/kubernetes/manifests/kube-apiserver.yaml").content_string)
    static = {item["name"]: item.get("value") for item in manifest["spec"]["containers"][0].get("env", [])}
    assert static.get(name) == expected

    pods = json.loads(host.check_output(
        "kubectl --kubeconfig /etc/kubernetes/admin.conf "
        "get pods -n kube-system -l component=kube-apiserver -o json"
    ))
    running = {item["name"]: item.get("value") for item in pods["items"][0]["spec"]["containers"][0].get("env", [])}
    assert running.get(name) == expected

    uploaded = yaml.safe_load(host.check_output(
        "kubectl --kubeconfig /etc/kubernetes/admin.conf "
        "get configmap kubeadm-config -n kube-system -o jsonpath='{.data.ClusterConfiguration}'"
    ))
    stored = {item["name"]: item["value"] for item in uploaded["apiServer"].get("extraEnvs", [])}
    assert stored.get(name) == expected


def test_kubelet_service_is_active_and_enabled(host):
    service = host.service("kubelet")

    assert service.exists
    assert service.is_running
    assert service.is_enabled


def test_control_plane_taint_is_removed(host):
    taints = host.check_output(
        "kubectl --kubeconfig /etc/kubernetes/admin.conf "
        "get nodes -o jsonpath='{range .items[*]}{.spec.taints}{end}'"
    )

    assert "node-role.kubernetes.io/control-plane" not in taints


# -----------------------------------------------------------------------------
# CoreDNS
# -----------------------------------------------------------------------------


COREDNS_BEGIN = "    # BEGIN ANSIBLE MANAGED COREDNS REWRITES\n"
COREDNS_END = "    # END ANSIBLE MANAGED COREDNS REWRITES\n"
SAMPLE_COREFILE = """# Existing site configuration
.:53 {
    errors
    health {
        lameduck 5s
    }
    ready
    kubernetes cluster.local in-addr.arpa ip6.arpa {
        pods insecure
        fallthrough in-addr.arpa ip6.arpa
        ttl 30
    }
    forward . /etc/resolv.conf {
        max_concurrent 1000
    }
    cache 30
    reload
}
example.net:53 {
    forward . 192.0.2.53
}
"""


@pytest.fixture
def coredns_contract(configuration_contract):
    role, _ordered, _tasks, environment, _resolve = configuration_contract
    environment = environment.overlay(trim_blocks=True, keep_trailing_newline=True)
    ordered = yaml.safe_load((role / "tasks/72-coredns.yml").read_text())[0]["block"]
    tasks = {task["name"]: task for task in ordered}

    def prepare(corefile, rewrites):
        context = {
            "kubernetes__coredns_config": {"stdout": json.dumps({
                "metadata": {"resourceVersion": "123"}, "data": {"Corefile": corefile},
            })},
            "kubernetes_coredns_rewrites": rewrites,
        }
        context["lookup"] = lambda _plugin, path: environment.from_string(
            (role / "templates" / path).read_text()
        ).render(**context)
        task = tasks["CoreDNS | Prepare managed rewrite block"]
        for name, expression in task["vars"].items():
            context[name] = environment.compile_expression(expression.strip()[2:-2].strip())(**context)
        expression = task["ansible.builtin.set_fact"]["kubernetes__coredns_corefile"]
        context["kubernetes__coredns_corefile"] = environment.compile_expression(expression.strip()[2:-2].strip())(**context)
        return context

    return tasks, environment, prepare


@pytest.mark.parametrize("rewrites", ({}, {"git.example.com": "gateway.edge.svc.cluster.local"}))
def test_coredns_preserves_other_configuration_and_is_idempotent(coredns_contract, rewrites):
    tasks, environment, prepare = coredns_contract
    context = prepare(SAMPLE_COREFILE, rewrites)
    desired = context["kubernetes__coredns_corefile"]
    block = COREDNS_BEGIN + "    rewrite name exact git.example.com gateway.edge.svc.cluster.local\n" + COREDNS_END
    expected = SAMPLE_COREFILE.replace(".:53 {\n", ".:53 {\n" + block) if rewrites else SAMPLE_COREFILE
    assert desired == expected
    condition = tasks["CoreDNS | Apply configuration when changed"]["when"]
    assert bool(environment.compile_expression(condition)(**context)) is bool(rewrites)
    repeated = prepare(desired, rewrites)
    assert repeated["kubernetes__coredns_corefile"] == desired
    assert environment.compile_expression(condition)(**repeated) is False


@pytest.mark.parametrize("rewrites", ({}, {"new.example.com": "new.edge.svc.cluster.local"}))
def test_coredns_rewrites_can_be_replaced_or_removed(coredns_contract, rewrites):
    _tasks, _environment, prepare = coredns_contract
    original = prepare(SAMPLE_COREFILE, {"old.example.com": "old.edge.svc.cluster.local"})["kubernetes__coredns_corefile"]
    desired = prepare(original, rewrites)["kubernetes__coredns_corefile"]
    assert "old.example.com" not in desired
    if rewrites:
        block = COREDNS_BEGIN + "    rewrite name exact new.example.com new.edge.svc.cluster.local\n" + COREDNS_END
        assert desired == SAMPLE_COREFILE.replace(".:53 {\n", ".:53 {\n" + block)
    else:
        assert desired == SAMPLE_COREFILE


def test_coredns_rewrites_are_sorted_and_patch_only_corefile(coredns_contract):
    tasks, environment, prepare = coredns_contract
    context = prepare(SAMPLE_COREFILE, {
        "z.example.com": "z.edge.svc.cluster.local", "a.example.com": "a.edge.svc.cluster.local",
    })
    desired = context["kubernetes__coredns_corefile"]
    assert desired.index("a.example.com") < desired.index("z.example.com")
    patch = tasks["CoreDNS | Apply configuration when changed"]["ansible.builtin.command"]["argv"][-1]
    assert json.loads(environment.from_string(patch).render(**context)) == {
        "metadata": {"resourceVersion": "123"}, "data": {"Corefile": desired},
    }


@pytest.mark.parametrize("corefile, accepted", ((SAMPLE_COREFILE, True), ("example.net:53 {\n}\n", False), (".:53 {\n}\n.:53 {\n}\n", False)))
def test_coredns_requires_one_root_server_block(coredns_contract, corefile, accepted):
    tasks, environment, prepare = coredns_contract
    context = prepare(corefile, {})
    conditions = tasks["CoreDNS | Require the kubeadm root server block"]["ansible.builtin.assert"]["that"]
    assert all(environment.compile_expression(condition)(**context) for condition in conditions) is accepted


def test_coredns_saved_rewrites_are_applied(host, saved_settings):
    config = json.loads(host.check_output(
        "kubectl --kubeconfig /etc/kubernetes/admin.conf get configmap coredns -n kube-system -o json"
    ))
    corefile = config["data"]["Corefile"]
    rewrites = saved_settings["coredns_rewrites"]
    assert corefile.count(COREDNS_BEGIN) == corefile.count(COREDNS_END) == bool(rewrites)
    if rewrites:
        managed = corefile.split(COREDNS_BEGIN)[1].split(COREDNS_END)[0]
        assert managed.splitlines() == [
            f"    rewrite name exact {source} {target}" for source, target in sorted(rewrites.items())
        ]
    assert re.search(r"(?m)^\s*reload\s*$", corefile)


# -----------------------------------------------------------------------------
# CNI (Flannel)
# -----------------------------------------------------------------------------


def test_flannel_daemonset_exists(host):
    assert "daemonset.apps/kube-flannel-ds" in host.check_output(
        "kubectl --kubeconfig /etc/kubernetes/admin.conf "
        "get daemonset kube-flannel-ds -n kube-flannel -o name"
    )


def test_metrics_server_image_matches_saved_version(host, saved_settings):
    image = host.check_output(
        "kubectl --kubeconfig /etc/kubernetes/admin.conf "
        "get deployment metrics-server -n kube-system "
        "-o jsonpath='{.spec.template.spec.containers[0].image}'"
    )

    assert image == "registry.k8s.io/metrics-server/metrics-server:" + saved_settings["metrics_server_version"]


def test_metrics_server_deployment_exists(host):
    assert "deployment.apps/metrics-server" in host.check_output(
        "kubectl --kubeconfig /etc/kubernetes/admin.conf "
        "get deployment metrics-server -n kube-system -o name"
    )


def test_metrics_server_allows_self_signed_kubelet_certificates(host):
    args = host.check_output(
        "kubectl --kubeconfig /etc/kubernetes/admin.conf "
        "get deployment metrics-server -n kube-system "
        "-o jsonpath='{.spec.template.spec.containers[0].args}'"
    )

    assert "--kubelet-insecure-tls" in args
