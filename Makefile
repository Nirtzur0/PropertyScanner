PYTHON ?= python3
PYTEST ?= $(PYTHON) -m pytest
PYTEST_ENV = PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

.PHONY: build-package test-offline test-integration test-e2e smoke-api

build-package:
	$(PYTHON) -m build

test-offline:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTEST) -m "not integration and not e2e and not live" -q

test-integration:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTEST) --run-integration -m integration -q

test-e2e:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTEST) --run-e2e -m e2e -q

smoke-api:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) scripts/smoke_api.py
