export PATH := $(HOME)/.local/bin:$(PATH)
export MLFLOW_DISABLE_AGENT_HINT := 1

.PHONY: install test lint scout serve mlflow-ui

install:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check src tests

scout:
	uv run gigscout scout -p profiles/example.yaml

serve:
	uv run gigscout serve

mlflow-ui:
	uv run mlflow ui --backend-store-uri sqlite:///data/mlflow.db --port 5000
