"""Exercise the installed nftables policy with isolated, real packet paths."""

import ipaddress
import json
from pathlib import Path
import select
import subprocess
from uuid import uuid4


PREFIX = "kfw-" + uuid4().hex[:8]
NODE, EXTERNAL, POD = (PREFIX + suffix for suffix in ("-n", "-e", "-p"))
PROTECTED = (2379, 2380, 2381, 6443, 10248, 10249, 10250, 10255, 10256, 10257, 10259)
settings = json.loads(Path("/etc/ansible/facts.d/kubernetes.fact").read_text())["cluster"]
network = ipaddress.IPv4Network(settings["pod_subnet"])
node_ip, pod_ip, spoof_ip = (str(network.network_address + number) for number in (1, 2, 3))


def run(*command, **kwargs):
    result = subprocess.run(command, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"{command}:\n{result.stdout}{result.stderr}")
    return result.stdout


def inside(namespace, *command, **kwargs):
    return run("ip", "netns", "exec", namespace, *command, **kwargs)


SERVER = r'''
import json, select, socket, sys
sockets = []
for family, address in ((socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::")):
    for kind, ports in ((socket.SOCK_STREAM, json.loads(sys.argv[1])), (socket.SOCK_DGRAM, (8472, 41641))):
        for port in ports:
            listener = socket.socket(family, kind)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if family == socket.AF_INET6:
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            listener.bind((address, port))
            if kind == socket.SOCK_STREAM:
                listener.listen()
            sockets.append(listener)
listeners = set(sockets)
print("ready", flush=True)
while True:
    for listener in select.select(sockets, [], [])[0]:
        if listener.type == socket.SOCK_DGRAM:
            message, address = listener.recvfrom(1024)
            listener.sendto(message, address)
        elif listener in listeners:
            connection, _ = listener.accept()
            connection.sendall(b"ok")
            sockets.append(connection)
        else:
            message = listener.recv(1024)
            if message:
                listener.sendall(message)
            else:
                sockets.remove(listener)
                listener.close()
'''

CLIENT = r'''
import json, socket, sys
for label, address, port, udp, expected, source in json.loads(sys.argv[1]):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    with socket.socket(family, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM) as connection:
        connection.settimeout(0.3)
        if source:
            connection.bind((source, 0))
        try:
            connection.connect((address, port))
            if udp:
                connection.send(b"ok")
            reachable = connection.recv(2) == b"ok"
        except (TimeoutError, ConnectionRefusedError):
            reachable = False
    assert reachable == expected, (label, address, port, reachable, expected)
'''

processes = []
created = []
try:
    for namespace in (NODE, EXTERNAL, POD):
        run("ip", "netns", "add", namespace)
        created.append(namespace)
        inside(namespace, "sysctl", "-qw", "net.ipv6.conf.all.disable_ipv6=0", "net.ipv6.conf.default.disable_ipv6=0")
        run("ip", "-n", namespace, "link", "set", "lo", "up")
    run("ip", "-n", NODE, "link", "add", "uplink", "type", "veth", "peer", "name", "eth0", "netns", EXTERNAL)
    run("ip", "-n", NODE, "link", "add", "cni0", "type", "veth", "peer", "name", "eth0", "netns", POD)
    for namespace, interface, ipv4, ipv6 in (
        (NODE, "uplink", "198.18.0.1/24", "fd42:6b66::1/64"),
        (EXTERNAL, "eth0", "198.18.0.2/24", "fd42:6b66::2/64"),
        (NODE, "cni0", f"{node_ip}/{network.prefixlen}", "fd42:6b67::1/64"),
        (POD, "eth0", f"{pod_ip}/{network.prefixlen}", "fd42:6b67::2/64"),
    ):
        run("ip", "-n", namespace, "address", "add", ipv4, "dev", interface)
        run("ip", "-n", namespace, "-6", "address", "add", ipv6, "dev", interface, "nodad")
        run("ip", "-n", namespace, "link", "set", interface, "up")
    inside(NODE, "sysctl", "-qw", "net.ipv4.ip_forward=1")
    run("ip", "-n", EXTERNAL, "route", "add", str(network), "via", "198.18.0.1")
    run("ip", "-n", POD, "route", "add", "default", "via", node_ip)
    # Make the spoofed source routable in both directions. Otherwise a routing
    # failure could falsely appear to prove that the firewall rejected it.
    run("ip", "-n", EXTERNAL, "address", "add", spoof_ip + "/32", "dev", "eth0")
    run("ip", "-n", NODE, "route", "add", spoof_ip + "/32", "dev", "uplink")
    for namespace in (NODE, EXTERNAL, POD):
        process = subprocess.Popen(
            ["ip", "netns", "exec", namespace, "python3", "-u", "-c", SERVER, json.dumps([*PROTECTED, 22, 8080])],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        processes.append(process)
        assert select.select([process.stdout], [], [], 10)[0], "listener startup timed out"
        assert process.stdout.readline().strip() == "ready", process.stderr.read()

    # An existing stateful manager activates conntrack before sessions open.
    foreign = (
        "table inet foreign {\n chain untouched {\n"
        "type filter hook input priority 0; policy accept;\n"
        "ct state established accept\n }\n}\n"
    )
    inside(NODE, "nft", "-f", "-", input=foreign)
    before = inside(NODE, "nft", "list", "table", "inet", "foreign")

    # Keep a control-plane connection open across policy installation/reload.
    session = subprocess.Popen(
        ["ip", "netns", "exec", EXTERNAL, "python3", "-u", "-c",
         'import socket, sys; s=socket.create_connection(("198.18.0.1", 6443), timeout=3); '
         'assert s.recv(2)==b"ok"; print("ready", flush=True); sys.stdin.readline(); '
         's.sendall(b"ok"); assert s.recv(2)==b"ok"; s.close()'],
        text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    processes.append(session)
    assert select.select([session.stdout], [], [], 10)[0], "session startup timed out"
    assert session.stdout.readline().strip() == "ready", session.stderr.read()

    for _ in range(2):
        inside(NODE, "nft", "-f", "/etc/nftables.d/kubernetes.nft")
        assert inside(NODE, "nft", "list", "table", "inet", "foreign") == before
    _, error = session.communicate("continue\n", timeout=10)
    assert session.returncode == 0, error
    inside(NODE, "nft", "-f", "-", input=(
        "table ip ingress { chain prerouting { type nat hook prerouting priority -100; "
        f"ip daddr 198.18.0.1 tcp dport 80 dnat to {pod_ip}:8080; "
        f"ip daddr 198.18.0.1 tcp dport 8081 dnat to {pod_ip}:10250; "
        "}\n}\n"
    ))

    external_checks = []
    for address in ("198.18.0.1", "fd42:6b66::1"):
        external_checks += [("protected", address, port, False, False, None) for port in PROTECTED]
        external_checks += [("other TCP", address, port, False, True, None) for port in (22, 8080)]
        external_checks += [("VXLAN", address, 8472, True, False, None), ("other UDP", address, 41641, True, True, None)]
    external_checks += [("spoofed pod", "198.18.0.1", port, False, False, spoof_ip) for port in (6443, 10250)]
    external_checks += [("spoof positive control", "198.18.0.1", 8080, False, True, spoof_ip)]
    external_checks += [("forwarded pod", pod_ip, 8080, False, True, None)]
    external_checks += [("DNAT ingress", "198.18.0.1", port, False, True, None) for port in (80, 8081)]
    inside(EXTERNAL, "python3", "-c", CLIENT, json.dumps(external_checks), timeout=40)

    local_checks = [("local", address, port, False, True, None)
                    for address in ("127.0.0.1", "::1") for port in PROTECTED]
    local_checks += [("local VXLAN", address, 8472, True, True, None) for address in ("127.0.0.1", "::1")]
    inside(NODE, "python3", "-c", CLIENT, json.dumps(local_checks), timeout=15)
    pod_checks = [("pod API/kubelet", node_ip, port, False, True, None) for port in (6443, 10250)]
    pod_checks += [("pod etcd", node_ip, port, False, False, None) for port in (2379, 2380)]
    pod_checks += [("outbound forwarding", "198.18.0.2", 8080, False, True, None)]
    inside(POD, "python3", "-c", CLIENT, json.dumps(pod_checks), timeout=15)
    print("firewall boundary checks passed")
finally:
    for process in processes:
        process.terminate()
        process.communicate(timeout=5)
    for namespace in reversed(created):
        run("ip", "netns", "delete", namespace)
