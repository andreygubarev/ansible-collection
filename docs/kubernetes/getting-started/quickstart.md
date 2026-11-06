# Kubernetes quickstart

## Requirements

Ubuntu 26.04 or Debian 13 on amd64 or arm64, ansible-core ≥ 2.20, root or sudo access, and a stable API address. See [network requirements](../reference/requirements.md).

## Run locally

```bash
ansible-galaxy collection install andreygubarev.com --upgrade
ansible-playbook andreygubarev.com.kubernetes -e kubernetes_cluster_name=my-cluster
```

No inventory or SSH transport is required. Add `-K` if sudo requires a password. Neither host baseline role is applied automatically.

A non-empty cluster name is required on the first run; there is no prompt. The complete validated configuration is saved before application, so later runs need no overrides:

```bash
ansible-playbook andreygubarev.com.kubernetes
```

Renaming or changing stored version/CIDRs is rejected before writing. Other desired settings can be changed with an explicit override. Invalid input leaves facts untouched; failed application retains desired settings for retry.

On first use, the API defaults to the host IPv4 address and kubeconfig owner defaults to the invoking user. Both choices are then remembered. Override either explicitly if needed:

```bash
ansible-playbook andreygubarev.com.kubernetes \
  -e kubernetes_cluster_name=my-cluster \
  -e kubernetes_advertise_address=203.0.113.10 \
  -e kubernetes_kubeconfig_user=ubuntu
```

Legacy INI identity facts are supported; repeat other previous custom settings once when upgrading. Configuration processing runs with `always`, even when selecting tags; do not skip it.

Choose the node hostname before initialization. Cluster name, Kubernetes minor version, and cluster CIDRs are immutable. Flannel does not enforce NetworkPolicy; metrics-server accepts self-signed kubelet certificates. Review [configuration](../reference/configuration.md) and [architecture](../concepts/architecture.md) before deployment.

## Verify

```bash
kubectl get nodes
kubectl get pods -A
```

For automated integration tests, run from a repository checkout on a machine with local Incus VM support:

```bash
make test
```

This tests all shared roles after the matching baseline in separate fresh Ubuntu and Debian VMs, including repeat application and persistence after reboot. It does not verify the host running the command. See [development](../../../README.md#integration-tests) for requirements and failure diagnostics.

## Remote provisioning

Use the role in your own `kubernetes.yml`:

```yaml
- name: Configure a single-node cluster
  hosts: kubernetes
  become: true
  roles:
    - andreygubarev.com.kubernetes
```

Set the SSH login user in inventory, for example `node1 ansible_user=ubuntu`, then run:

```bash
ansible-playbook -i inventory.ini kubernetes.yml -e kubernetes_cluster_name=my-cluster
```
