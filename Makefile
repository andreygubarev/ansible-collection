.DEFAULT_GOAL := help

# Ansible
ANSIBLE_BUILD_DIR ?= $(CURDIR)/dist
ANSIBLE_COLLECTIONS_PATH ?= $(CURDIR)/.ansible/collections
ANSIBLE_COLLECTION_VERSION := $(shell awk '/^version:/ { print $$2 }' galaxy.yml)
ANSIBLE_GALAXY ?= uvx --from ansible-core ansible-galaxy
ANSIBLE_LINT ?= uvx --from ansible-lint ansible-lint
ANSIBLE_PLAYBOOK ?= uvx --from ansible-core ansible-playbook

# Incus
INCUS_NETWORK ?= incusbr0
INCUS_STORAGE_POOL ?= default
INCUS_DISTRIBUTIONS ?= ubuntu2604 debian13

# Testinfra
TESTINFRA_PYTEST ?= uvx --from pytest --with pytest-testinfra --with pytest-xdist --with ansible-core pytest
TESTINFRA_WORKERS ?= 8

.PHONY: help
help: ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_-]+:.*##/ {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: check
check: lint syntax ## Run all checks

.PHONY: deps
deps: ## Install the local collection and its dependencies
	ANSIBLE_COLLECTIONS_PATH=$(ANSIBLE_COLLECTIONS_PATH) $(ANSIBLE_GALAXY) collection install . --force -p $(ANSIBLE_COLLECTIONS_PATH)

.PHONY: build
build: ## Build the collection artifact
	$(ANSIBLE_GALAXY) collection build --force --output-path $(ANSIBLE_BUILD_DIR)

.PHONY: publish
publish: check build ## Check, build, and publish the collection to Ansible Galaxy
	$(ANSIBLE_GALAXY) collection publish "$(ANSIBLE_BUILD_DIR)/andreygubarev-com-$(ANSIBLE_COLLECTION_VERSION).tar.gz"

.PHONY: lint
lint: deps ## Run ansible-lint against the collection
	ANSIBLE_COLLECTIONS_PATH=$(ANSIBLE_COLLECTIONS_PATH) $(ANSIBLE_LINT) .

.PHONY: syntax
syntax: deps ## Check the installed collection playbooks syntax
	ANSIBLE_COLLECTIONS_PATH=$(ANSIBLE_COLLECTIONS_PATH) $(ANSIBLE_PLAYBOOK) --syntax-check andreygubarev.com.ubuntu2604 andreygubarev.com.debian13 andreygubarev.com.kubernetes andreygubarev.com.terraform andreygubarev.com.gitops andreygubarev.com.agents

.PHONY: test
test: deps ## Test all roles in fresh Ubuntu and Debian Incus VMs
	@set -e; for distribution in $(INCUS_DISTRIBUTIONS); do \
		ANSIBLE_COLLECTIONS_PATH="$(ANSIBLE_COLLECTIONS_PATH)" \
		ANSIBLE_PLAYBOOK="$(ANSIBLE_PLAYBOOK)" \
		INCUS_NETWORK="$(INCUS_NETWORK)" INCUS_STORAGE_POOL="$(INCUS_STORAGE_POOL)" \
		TESTINFRA_PYTEST="$(TESTINFRA_PYTEST)" TESTINFRA_WORKERS="$(TESTINFRA_WORKERS)" \
		bash tests/incus.sh "$$distribution"; \
	done
