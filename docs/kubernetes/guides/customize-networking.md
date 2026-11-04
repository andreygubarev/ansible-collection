# Kubernetes networking

Choose API and cluster network addresses before initialization:

```yaml
kubernetes_cluster_name: my-cluster
kubernetes_advertise_address: 203.0.113.10
kubernetes_pod_subnet: 10.244.0.0/16
kubernetes_service_subnet: 10.96.0.0/16
```

The API address initially defaults to the host's IPv4 address, then is remembered. It controls the advertise address, endpoint, bind address, and certificate SAN. The role's endpoint firewall blocks new remote API connections while preserving access from the node and its pod network. Changing an initialized cluster's address may require a separate certificate/network migration; the role does not renew certificates automatically.

The default pod CIDR matches Flannel v0.28.10. For another CIDR, set `kubernetes_flannel_manifest_url` to a manifest with a matching `net-conf.json` `Network`. The role does not rewrite the manifest or upgrade an existing Flannel installation.

## Constraints

- Cluster name, Kubernetes minor version, and both CIDRs are immutable and stored in `/etc/ansible/facts.d/kubernetes.fact`.
- All public settings are reused automatically. Explicit changes to immutable identity are rejected; version/CIDR defaults from newer role releases cannot reset existing choices.
- The API must be outside valid, non-overlapping IPv4 pod and service networks; validation precedes persistence.
- Existing clusters are not reinitialized. Back up and rebuild, or use a separate migration procedure, to change identity or CIDRs.
- Calico-to-Flannel migration is not automated. Flannel does not enforce NetworkPolicy.

[Configuration](../reference/configuration.md) · [Architecture](../concepts/architecture.md)
