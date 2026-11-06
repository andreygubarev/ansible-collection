#!/usr/bin/env bash
set -euo pipefail

command -v incus >/dev/null || { echo 'make test requires Incus.' >&2; exit 1; }
incus --force-local version

baseline=${1:-ubuntu2604}
case "$baseline" in
    ubuntu2604) image=images:ubuntu/26.04/cloud ;;
    debian13) image=images:debian/13/cloud ;;
    *) echo "Unsupported test distribution: $baseline" >&2; exit 1 ;;
esac

mkdir -p .cache
workdir=$(mktemp -d "$PWD/.cache/incus-$baseline.XXXXXX")
vm="ansible-test-$baseline-$(date +%s)-$$"
created=false
exec > >(tee "$workdir/run.log") 2>&1

cleanup() {
    status=$?
    if (( status == 0 )); then
        incus --force-local delete "$vm" --force || return $?
        rm -rf "$workdir"
    else
        echo "Test failed; diagnostics and SSH key retained in $workdir"
        if [[ "$created" == true ]]; then
            echo "VM retained: $vm"
            echo "Inspect: incus --force-local exec $vm -- bash"
            echo "Remove: incus --force-local delete $vm --force"
        fi
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

read -r -a playbook <<< "$ANSIBLE_PLAYBOOK"
read -r -a pytest <<< "$TESTINFRA_PYTEST"
export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_NOCOLOR=True
export ANSIBLE_STDOUT_CALLBACK=default

ssh-keygen -q -t ed25519 -N '' -f "$workdir/id_ed25519"
public_key=$(<"$workdir/id_ed25519.pub")

# Do not inherit site profiles or expose host directories to these destructive roles.
incus --force-local init "$image" "$vm" --vm --no-profiles \
    --storage "$INCUS_STORAGE_POOL" --network "$INCUS_NETWORK" \
    --device root,size=30GiB --config limits.cpu=4 --config limits.memory=6GiB
created=true
# Do not set ssh_pwauth before OpenSSH is installed: cloud-init would create a
# partial sshd_config instead of letting the package provide its PAM/drop-in defaults.
# The bootstrap user has a locked password; the baseline later enforces key-only SSH.
incus --force-local config set "$vm" cloud-init.user-data - <<EOF
#cloud-config
users:
  - name: ansible
    groups: sudo
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    lock_passwd: true
    ssh_authorized_keys:
      - $public_key
package_update: true
packages:
  - openssh-server
  - python3
  - python3-apt
EOF
incus --force-local start "$vm"

echo "Waiting for the VM agent: $vm"
deadline=$((SECONDS + 300))
until timeout 10 incus --force-local exec "$vm" -T -- true 2>/dev/null; do
    if (( SECONDS >= deadline )); then
        echo 'VM agent did not become ready within 300 seconds.' >&2
        exit 1
    fi
    sleep 2
done
incus --force-local exec "$vm" -T -- timeout 1800 cloud-init status --wait
address=$(incus --force-local exec "$vm" -T -- hostname -I | awk '{ print $1 }')
[[ -n "$address" ]] || { echo 'VM has no IP address.' >&2; exit 1; }

cat > "$workdir/inventory.yml" <<EOF
incus_test:
  hosts:
    testvm:
      ansible_host: "$address"
      ansible_user: ansible
      ansible_port: 22
      ansible_python_interpreter: /usr/bin/python3
      incus_test_baseline: "$baseline"
      ansible_ssh_private_key_file: "$workdir/id_ed25519"
      ansible_ssh_common_args: >-
        -o IdentitiesOnly=yes -o IdentityAgent=none
        -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no
EOF

apply() {
    "${playbook[@]}" -i "$workdir/inventory.yml" tests/playbooks/converge.yml "$@"
}

verify() {
    "${pytest[@]}" -n "$TESTINFRA_WORKERS" --dist=worksteal \
        --hosts='ansible://testvm?controlpersist=300&timeout=30' \
        --ansible-inventory="$workdir/inventory.yml" --sudo \
        "roles/$baseline/tests" roles/kubernetes/tests roles/terraform/tests roles/gitops/tests roles/agents/tests
}

echo "Applying $baseline, Kubernetes, Terraform tooling, GitOps, and agents to the fresh VM"
apply -e "${baseline}_hostname=$vm" -e "kubernetes_cluster_name=$vm" \
    -e gitops_git_user_name=Incus -e gitops_git_user_email=incus@example.invalid
verify

echo 'Checking a non-default administrative SSH port without replacing host identity'
ssh_keys=$(incus --force-local exec "$vm" -T -- sh -c 'sha256sum /etc/ssh/ssh_host_*_key.pub')
"${playbook[@]}" -i "$workdir/inventory.yml" tests/playbooks/ssh-port.yml \
    --tags ssh -e "${baseline}_ssh_port=22022"
python3 - "$workdir/inventory.yml" "$address" <<'PY'
from pathlib import Path
import socket
import sys
inventory = Path(sys.argv[1])
content = inventory.read_text()
assert content.count("      ansible_port: 22\n") == 1
inventory.write_text(content.replace("      ansible_port: 22\n", "      ansible_port: 22022\n"))
with socket.create_connection((sys.argv[2], 22022), timeout=3) as connection:
    assert connection.recv(256).startswith(b"SSH-2.0-")
try:
    with socket.create_connection((sys.argv[2], 22), timeout=1):
        raise AssertionError("The old SSH port must no longer accept new connections")
except (ConnectionRefusedError, TimeoutError):
    pass
PY
[[ "$(incus --force-local exec "$vm" -T -- sh -c 'sha256sum /etc/ssh/ssh_host_*_key.pub')" == "$ssh_keys" ]]

echo 'Checking firewall repair and preservation of independently managed rules'
incus --force-local exec "$vm" -T -- nft -f - <<'EOF'
table inet collection_test {
    chain untouched {
        tcp dport 12345 accept
    }
}
EOF
foreign_rules=$(incus --force-local exec "$vm" -T -- nft list table inet collection_test)
"${playbook[@]}" -i "$workdir/inventory.yml" tests/playbooks/firewall-upgrade.yml
[[ "$(incus --force-local exec "$vm" -T -- nft list table inet collection_test)" == "$foreign_rules" ]]
incus --force-local exec "$vm" -T -- systemctl reload nftables
incus --force-local exec "$vm" -T -- systemctl restart nftables
[[ "$(incus --force-local exec "$vm" -T -- nft list table inet collection_test)" == "$foreign_rules" ]]
# An existing table can be incomplete even when its config file is unchanged.
# Verify repair both for missing rules and for a completely missing table.
for damage in 'flush chain inet andreygubarev_kubernetes input' 'delete table inet andreygubarev_kubernetes'; do
    read -r -a nft_damage <<< "$damage"
    incus --force-local exec "$vm" -T -- nft "${nft_damage[@]}"
    # Positive control: the same external probe must reach the unfiltered API.
    python3 - "$address" <<'PY'
import socket
import sys
with socket.create_connection((sys.argv[1], 6443), timeout=3):
    pass
PY
    apply --tags firewall
    [[ "$(incus --force-local exec "$vm" -T -- nft list table inet collection_test)" == "$foreign_rules" ]]
done
verify

echo 'Checking idempotence and saved configuration without first-run overrides'
apply | tee "$workdir/idempotence.log"
if ! grep -Eq '^testvm[[:space:]]*:.*changed=0[[:space:]]' "$workdir/idempotence.log"; then
    echo 'The second application must report changed=0.' >&2
    exit 1
fi

echo 'Checking persistence after reboot'
"${playbook[@]}" -i "$workdir/inventory.yml" tests/playbooks/reboot.yml
verify

echo 'Checking an overridden agent account and user-local updates'
"${playbook[@]}" -i "$workdir/inventory.yml" tests/playbooks/agents-user.yml
verify_agents() {
    "${pytest[@]}" -n "$TESTINFRA_WORKERS" --dist=worksteal \
        --hosts='ansible://testvm?controlpersist=300&timeout=30' \
        --ansible-inventory="$workdir/inventory.yml" --sudo --agents-user=worker roles/agents/tests
}
verify_agents

echo 'Checking explicit BB version pins disable in-app updates'
bb_version=$(incus --force-local exec "$vm" -T -- /usr/bin/node -p \
    'require("/home/worker/.local/lib/node_modules/bb-app/package.json").version')
"${playbook[@]}" -i "$workdir/inventory.yml" tests/playbooks/agents-user.yml -e "agents_bb_version=$bb_version"
incus --force-local exec "$vm" -T -- sudo -iu worker bb updates app status --json | \
    python3 -c 'import json, sys; status = json.load(sys.stdin); assert status["support"]["kind"] != "supported"; assert status["current"]["version"] == sys.argv[1]' "$bb_version"
"${playbook[@]}" -i "$workdir/inventory.yml" tests/playbooks/agents-user.yml
verify_agents

"${playbook[@]}" -i "$workdir/inventory.yml" tests/playbooks/agents-user.yml | tee "$workdir/agents-user-idempotence.log"
if ! grep -Eq '^testvm[[:space:]]*:.*changed=0[[:space:]]' "$workdir/agents-user-idempotence.log"; then
    echo 'The overridden account must also report changed=0 on repeat application.' >&2
    exit 1
fi
"${playbook[@]}" -i "$workdir/inventory.yml" tests/playbooks/reboot.yml
verify_agents
