"""Verification for the GitOps workspace role."""

import re
import shlex
from pathlib import Path

import pytest
import yaml
from ansible.plugins.test.core import TestModule as AnsibleTestModule
from jinja2 import Environment


# -----------------------------------------------------------------------------
# Repository identity
# -----------------------------------------------------------------------------


@pytest.fixture
def git_identity_contract():
    role = Path(__file__).resolve().parents[1]
    ordered = yaml.safe_load((role / "tasks/20-git-init.yml").read_text())
    tasks = {task["name"]: task for task in ordered}
    defaults = yaml.safe_load((role / "defaults/main.yml").read_text())
    environment = Environment()
    environment.tests["match"] = AnsibleTestModule().tests()["match"]

    def resolve(saved_name, saved_email, overrides):
        context = {"gitops__git_identity": {"results": [
            {"stdout": saved_name or ""}, {"stdout": saved_email or ""},
        ]}}
        for name in ("gitops_git_user_name", "gitops_git_user_email"):
            expression = defaults[name].strip()[2:-2].strip()
            context[name] = environment.compile_expression(expression)(**context)
        context.update(overrides)
        context["lookup"] = lambda _plugin, name: context[name]
        return context

    return role, ordered, tasks, environment, resolve


@pytest.mark.parametrize("saved_name, saved_email, overrides, accepted", (
    (None, None, {}, False),
    (None, None, {"gitops_git_user_name": "Operator", "gitops_git_user_email": "operator@example.com"}, True),
    ("Operator", None, {}, False),
    (None, "operator@example.com", {}, False),
    ("Operator", "operator@example.com", {}, True),
    ("Operator", "operator@example.com", {"gitops_git_user_name": "Other Operator"}, True),
    ("Operator", "operator@example.com", {"gitops_git_user_name": ""}, False),
    ("Operator", "operator@example.com", {"gitops_git_user_name": "   "}, False),
    ("Operator", "operator@example.com", {"gitops_git_user_name": False}, False),
    ("Operator", "operator@example.com", {"gitops_git_user_email": None}, False),
    ("Operator", "operator@example.com", {"gitops_git_user_email": "invalid"}, False),
    ("Operator", "operator@example.com", {"gitops_git_user_email": "operator@example.com\n"}, False),
    ("Operator", "operator@example.com", {"gitops_git_user_email": "<operator@example.com>"}, False),
))
def test_git_identity_is_required_and_reuses_local_values(
    git_identity_contract, saved_name, saved_email, overrides, accepted,
):
    _role, _ordered, tasks, environment, resolve = git_identity_contract
    context = resolve(saved_name, saved_email, overrides)
    task = tasks["Git | Validate required repository identity"]
    valid = True
    for name in task["loop"]:
        context["item"] = name
        valid = valid and all(
            environment.compile_expression(condition)(**context)
            for condition in task["ansible.builtin.assert"]["that"]
        )
    if valid:
        email = tasks["Git | Validate repository email"]
        context.update(email["vars"])
        valid = all(environment.compile_expression(condition)(**context) for condition in email["ansible.builtin.assert"]["that"])
    assert bool(valid) is accepted
    assert context["gitops_git_user_name"] == overrides.get("gitops_git_user_name", saved_name or "")
    assert context["gitops_git_user_email"] == overrides.get("gitops_git_user_email", saved_email or "")


def test_git_identity_is_validated_before_initialization_and_scoped_to_repo(git_identity_contract):
    role, ordered, tasks, _environment, _resolve = git_identity_contract
    names = [task["name"] for task in ordered]
    assert names.index("Git | Validate required repository identity") < names.index("Git | Initialize the workspace repository")
    assert names.index("Git | Validate repository email") < names.index("Git | Initialize the workspace repository")
    read = tasks["Git | Read saved repository identity"]["ansible.builtin.command"]["argv"]
    assert "--file" in read and read[read.index("--file") + 1].endswith("/gitops/.git/config")
    config = tasks["Git | Configure repository identity"]["community.general.git_config"]
    assert config["scope"] == "file" and config["file"].endswith("/gitops/.git/config")
    baseline = yaml.safe_load((role / "tasks/40-git-baseline.yml").read_text())[0]["block"]
    commit = next(task["ansible.builtin.command"]["argv"] for task in baseline if task["name"] == "Git | Commit the initial workspace")
    assert "-c" not in commit and "--no-gpg-sign" in commit


@pytest.fixture
def workspace(host):
    variables = host.ansible.get_variables()
    user = host.user(variables.get("gitops_user", variables["ansible_user"]))
    return user, user.home + "/gitops"


def git_command(host, workspace, *arguments):
    user, directory = workspace
    with host.sudo(user.name):
        return host.run(shlex.join([
            "env", f"HOME={user.home}", "/usr/bin/git", "-C", directory, *arguments,
        ]))


def test_git_is_installed(host):
    assert host.package("git").is_installed


def test_helm_is_system_wide_and_usable_by_workspace_owner(host, workspace):
    link = host.file("/usr/local/bin/helm")
    assert link.is_symlink
    version = re.fullmatch(r"/usr/local/lib/helm/(3\.[0-9]+\.[0-9]+)/helm", link.linked_to)
    assert version
    binary = host.file(link.linked_to)
    assert binary.is_file
    assert binary.user == "root" and binary.group == "root"
    assert binary.mode == 0o755
    user, _directory = workspace
    with host.sudo(user.name):
        assert host.check_output("/usr/local/bin/helm version --short").startswith("v" + version.group(1) + "+")


def test_workspace_is_private_and_user_owned(host, workspace):
    user, directory = workspace
    folder = host.file(directory)
    assert folder.is_directory
    assert folder.user == user.name
    assert folder.gid == user.gid
    assert folder.mode == 0o700


@pytest.mark.parametrize("name", (
    "13-istio-gateway", "20-cert-manager", "21-letsencrypt", "30-openebs", "31-cnpg",
    "32-k8up", "40-forgejo", "41-forgejo-runner", "42-forgejo-backup",
))
def test_workload_directory_is_private_and_user_owned(host, workspace, name):
    user, directory = workspace
    folder = host.file(f"{directory}/{name}")
    assert folder.is_directory
    assert folder.user == user.name
    assert folder.gid == user.gid
    assert folder.mode == 0o700


@pytest.mark.parametrize("name", (
    ".envrc", ".gitignore", ".sops.yaml", "root.hcl", ".opentofu-version", ".terragrunt-version",
    "20-cert-manager/terraform.tf", "20-cert-manager/terraform.tfvars.yaml",
    "20-cert-manager/terragrunt.hcl",
    "30-openebs/terraform.tf", "30-openebs/terraform.tfvars.yaml",
    "30-openebs/terragrunt.hcl",
    "31-cnpg/terraform.tf", "31-cnpg/terraform.tfvars.yaml", "31-cnpg/terragrunt.hcl",
    "32-k8up/terraform.tf", "32-k8up/terraform.tfvars.yaml", "32-k8up/terragrunt.hcl",
    "13-istio-gateway/terraform.tf", "13-istio-gateway/terraform.tfvars.yaml", "13-istio-gateway/terragrunt.hcl",
    "21-letsencrypt/terraform.tf", "21-letsencrypt/terraform.tfvars.yaml", "21-letsencrypt/terragrunt.hcl",
    "40-forgejo/terraform.tf", "40-forgejo/terraform.tfvars.yaml", "40-forgejo/terragrunt.hcl",
    "41-forgejo-runner/terraform.tf", "41-forgejo-runner/terraform.tfvars.yaml", "41-forgejo-runner/terragrunt.hcl",
    "42-forgejo-backup/terraform.tf", "42-forgejo-backup/terraform.tfvars.yaml", "42-forgejo-backup/terragrunt.hcl",
))
def test_scaffold_file_is_user_owned(host, workspace, name):
    user, directory = workspace
    item = host.file(f"{directory}/{name}")
    assert item.is_file
    assert item.user == user.name
    assert item.gid == user.gid
    assert item.mode == 0o644


@pytest.mark.parametrize("name, version", ((".opentofu-version", "1.12.12"), (".terragrunt-version", "1.1.6")))
def test_project_version_is_pinned(host, workspace, name, version):
    _user, directory = workspace
    assert host.file(f"{directory}/{name}").content_string.strip() == version


def test_repository_identity_is_saved_locally(host, workspace):
    for name in ("user.name", "user.email"):
        result = git_command(host, workspace, "config", "--local", "--get", name)
        assert result.rc == 0
        assert result.stdout.strip()
    email = git_command(host, workspace, "config", "--local", "--get", "user.email").stdout.strip()
    assert re.fullmatch(r"[^\s@<>]+@[^\s@<>]+", email)


def test_repository_has_a_baseline_commit(host, workspace):
    user, directory = workspace
    repository = host.file(directory + "/.git")
    assert repository.is_directory
    assert repository.user == user.name
    result = git_command(host, workspace, "rev-parse", "--verify", "HEAD")
    assert result.rc == 0
    assert re.fullmatch(r"[0-9a-f]{40}\n", result.stdout)


IGNORED_PATHS = (
    ".terraform/provider",
    ".terragrunt-cache/module",
    "backend.tf",
    "terraform.tfstate",
    "terraform.tfstate.backup",
)


def test_runtime_state_and_caches_are_ignored(host, workspace):
    result = git_command(host, workspace, "check-ignore", "--no-index", *IGNORED_PATHS)
    assert result.rc == 0
    assert result.stdout.splitlines() == list(IGNORED_PATHS)


def test_provider_lock_file_is_ignored(host, workspace):
    assert git_command(host, workspace, "check-ignore", "--no-index", ".terraform.lock.hcl").rc == 0


# -----------------------------------------------------------------------------
# Durable local state
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("cached_paths, accepted", (
    ([], True),
    (["/home/operator/gitops/.terragrunt-cache/unit/.terraform/terraform.tfstate"], True),
    (["/home/operator/gitops/.terragrunt-cache/unit/terraform.tfstate"], False),
    (["/home/operator/gitops/.terragrunt-cache/unit/terraform.tfstate.backup"], False),
    (["/home/operator/gitops/.terragrunt-cache/unit/terraform.tfstate.d/staging/terraform.tfstate"], False),
))
def test_legacy_state_guard_distinguishes_resource_state_from_backend_metadata(cached_paths, accepted):
    role = Path(__file__).resolve().parents[1]
    tasks = yaml.safe_load((role / "tasks/11-state.yml").read_text())[0]["block"]
    guard = next(task for task in tasks if task["name"] == "State | Require explicit migration of legacy state")
    environment = Environment()
    environment.tests["search"] = AnsibleTestModule().tests()["search"]
    context = {"gitops__cached_states": {"files": [{"path": path} for path in cached_paths]}}
    conditions = guard["ansible.builtin.assert"]["that"]
    assert all(environment.compile_expression(condition)(**context) for condition in conditions) is accepted
    ordered = yaml.safe_load((role / "tasks/main.yml").read_text())
    imports = [task["ansible.builtin.import_tasks"] for task in ordered]
    assert imports.index("11-state.yml") < imports.index("30-files.yml")
    directories = next(task for task in tasks if task["name"] == "State | Create private permanent state directories")
    assert directories["ansible.builtin.file"]["mode"] == "0700"
    assert "/.local/state/gitops/" in directories["ansible.builtin.file"]["path"]


WORKLOADS = (
    "10-gateway-api", "11-istio-base", "12-istiod", "13-istio-gateway", "20-cert-manager",
    "21-letsencrypt", "30-openebs", "31-cnpg", "32-k8up", "40-forgejo", "41-forgejo-runner", "42-forgejo-backup",
)


@pytest.mark.parametrize("name", WORKLOADS)
def test_state_directories_are_private_and_outside_checkout(host, workspace, name):
    user, _directory = workspace
    base = user.home + "/.local/state/gitops"
    for path in (base, base + "/" + name, base + "/" + name + "/workspaces"):
        item = host.file(path)
        assert item.is_directory
        assert item.user == user.name and item.gid == user.gid
        assert item.mode == 0o700
    state = host.file(base + "/" + name + "/terraform.tfstate")
    if state.exists:
        assert state.is_file
        assert state.user == user.name and state.gid == user.gid
        assert state.mode == 0o600


@pytest.mark.parametrize("name", WORKLOADS)
def test_workload_inherits_absolute_state_backend(name):
    root = Path(__file__).resolve().parents[1] / "files/gitops"
    hcl = (root / name / "terragrunt.hcl").read_text()
    assert 'include "root"' in hcl and 'find_in_parent_folders("root.hcl")' in hcl
    assert 'backend "local"' not in (root / name / "terraform.tf").read_text()
    shared = (root / "root.hcl").read_text()
    assert re.search(r'backend\s*=\s*"local"', shared)
    assert '${get_env("HOME")}/.local/state/gitops/${path_relative_to_include()}/terraform.tfstate' in shared
    assert '${get_env("HOME")}/.local/state/gitops/${path_relative_to_include()}/workspaces' in shared


# -----------------------------------------------------------------------------
# K8up
# -----------------------------------------------------------------------------


def test_k8up_uses_matching_crds_and_secret_backed_credentials():
    text = (Path(__file__).resolve().parents[1] / "files/gitops/32-k8up/terraform.tf").read_text()
    assert 'default     = "4.10.1"' in text
    assert 'k8up-${var.k8up_version}/k8up-crd.yaml' in text
    assert 'version      = var.k8up_version' in text
    assert 'skipWithoutAnnotation = true' in text
    assert '"checksum/credentials" = nonsensitive(sha256(jsonencode(local.credentials)))' in text
    assert 'depends_on = [kustomization_resource.crds, kustomization_resource.credentials]' in text
    assert '"helm.sh/hook"' in text
    for priority in range(3):
        assert f'setsubtract(data.kustomization_overlay.this.ids_prio[{priority}], local.helm_hooks)' in text
    for variable, environment, key in (
        ("b2_access_key_id", "BACKUP_GLOBALACCESSKEYID", "access-key-id"),
        ("b2_secret_access_key", "BACKUP_GLOBALSECRETACCESSKEY", "secret-access-key"),
        ("k8up_repo_password", "BACKUP_GLOBALREPOPASSWORD", "repo-password"),
    ):
        block = re.search(r'variable "' + variable + r'" \{(.*?)^\}', text, re.M | re.S).group(1)
        assert re.search(r'sensitive\s*=\s*true', block)
        assert not re.search(r'\bvalue\s*=\s*var\.' + variable, text)
        assert re.search(
            r'name\s*=\s*"' + environment + r'"\s+valueFrom\s*=\s*\{\s+secretKeyRef\s*=\s*'
            + r'\{\s*name\s*=\s*"k8up-credentials",\s*key\s*=\s*"' + key + r'"', text,
        )


# -----------------------------------------------------------------------------
# Forgejo PVC backups
# -----------------------------------------------------------------------------


def test_forgejo_backup_targets_only_the_app_pvc_without_hooks_or_pruning():
    root = Path(__file__).resolve().parents[1] / "files/gitops"
    text = (root / "42-forgejo-backup/terraform.tf").read_text()
    owner = (root / "40-forgejo/terraform.tf").read_text()
    dependencies = (root / "42-forgejo-backup/terragrunt.hcl").read_text()
    assert 'default     = "CRON_TZ=UTC 0 3 * * *"' in text
    assert 'kind       = "Schedule"' in text and 'namespace = "forgejo"' in text
    assert 'variable "b2_bucket"' in text
    assert 'backend = { s3 = { bucket = var.b2_bucket } }' in text
    assert 'labelSelectors = [{' in text
    for resource in (text, owner):
        assert '"app.kubernetes.io/component" = "forgejo-data"' in resource
    assert '"k8up.io/backup" = "true"' in owner
    assert 'runAsUser  = 0' in text
    assert 'runAsGroup = 0' in text
    assert not re.search(r'^\s*(prune|check|restore|archive)\s*=', text, re.M)
    assert 'PersistentVolumeClaim' not in text and 'PreBackupPod' not in text
    assert 'postgresql.cnpg.io' not in text
    assert 'paths = ["../32-k8up", "../40-forgejo"]' in dependencies


# -----------------------------------------------------------------------------
# SOPS inputs
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("name", WORKLOADS)
def test_nonsecret_inputs_are_not_ignored(host, workspace, name):
    assert git_command(host, workspace, "check-ignore", "--no-index", f"{name}/terraform.tfvars.yaml").rc == 1


@pytest.mark.parametrize("name", WORKLOADS)
def test_encrypted_inputs_are_user_owned_decryptable_and_not_ignored(host, workspace, name):
    user, directory = workspace
    relative = f"{name}/terraform.tfvars.sops.yaml"
    item = host.file(f"{directory}/{relative}")
    assert item.is_file
    assert item.user == user.name and item.gid == user.gid
    assert item.mode == 0o644
    assert "sops" in yaml.safe_load(item.content_string)
    assert git_command(host, workspace, "check-ignore", "--no-index", relative).rc == 1
    with host.sudo(user.name):
        result = host.run(shlex.join([
            "env", f"HOME={user.home}", f"SOPS_AGE_KEY_FILE={user.home}/.config/sops/age/keys.txt",
            "/usr/local/bin/sops", "--decrypt", "--output", "/dev/null", f"{directory}/{relative}",
        ]))
    assert result.rc == 0


@pytest.mark.parametrize("name", WORKLOADS)
def test_workload_merges_sops_inputs_last(name):
    path = Path(__file__).resolve().parents[1] / "files/gitops" / name / "terragrunt.hcl"
    text = path.read_text()
    assert 'inputs = merge(' in text
    assert text.index('yamldecode(file("terraform.tfvars.yaml"))') < text.index(
        'yamldecode(sops_decrypt_file("terraform.tfvars.sops.yaml"))'
    )


def test_sops_policy_and_encrypted_files_are_seeded_only_once():
    role = Path(__file__).resolve().parents[1]
    policy = yaml.safe_load((role / "tasks/22-sops.yml").read_text())
    copy = next(task["ansible.builtin.copy"] for task in policy if "ansible.builtin.copy" in task)
    assert copy["force"] is False
    assert "gitops__age_recipient.stdout_lines" in copy["content"]
    assert "AGE-SECRET-KEY" not in copy["content"]
    inputs = yaml.safe_load((role / "tasks/31-sops-files.yml").read_text())[0]["ansible.builtin.command"]
    assert inputs["creates"].endswith("/terraform.tfvars.sops.yaml")
    assert inputs["stdin"] == "{}"
    assert "--output" in inputs["argv"]
    assert inputs["argv"][-1] == "/dev/stdin"
