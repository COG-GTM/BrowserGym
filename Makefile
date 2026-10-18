# Use `uv run` when uv is available (uv workspace, see `make sync`); otherwise run tools from the
# active environment (pip install path, see `make install`). Override with `make <target> RUN=`.
RUN ?= $(if $(shell command -v uv 2>/dev/null),uv run,)
# Optional Python version for uv, e.g. `make sync PYTHON=3.13`.
PYTHON ?=
UV_PYTHON_FLAG = $(if $(PYTHON),--python $(PYTHON),)

sync:
	@echo "--- 🔄 Syncing uv workspace (browsergym-core + dev tools) ---"
	uv sync $(UV_PYTHON_FLAG)

sync-all:
	@echo "--- 🔄 Syncing uv workspace (all browsergym packages + dev tools) ---"
	uv sync --all-packages $(UV_PYTHON_FLAG)

browsers:
	@echo "--- 🌐 Installing Playwright Chromium ---"
	$(RUN) playwright install chromium

lint:
	@echo "--- 🔍 Linting (ruff + black --check) ---"
	$(RUN) ruff check .
	$(RUN) black --check .

fmt:
	@echo "--- 🎨 Formatting (ruff isort fixes + black) ---"
	$(RUN) ruff check --select I --fix .
	$(RUN) black .

test: test-core

install:
	@echo "--- 🚀 Installing project dependencies ---"
	pip install -e ./browsergym/core -e ./browsergym/miniwob -e ./browsergym/webarena -e ./browsergym/webarenalite -e ./browsergym/visualwebarena/ -e ./browsergym/experiments -e ./browsergym/assistantbench -e ./browsergym/
	playwright install chromium

install-demo:
	@echo "--- 🚀 Installing demo dependencies ---"
	pip install -r demo_agent/requirements.txt
	playwright install chromium

demo:
	@echo "--- 🚀 Running demo agent ---"
	(set -x && cd demo_agent && python run_demo.py)

setup-miniwob:
	@echo "--- 🤖 Setting up MiniWoB++ ---"
	@if [ ! -d "miniwob-plusplus" ]; then \
		echo "Cloning MiniWoB++ repository..."; \
		git clone https://github.com/Farama-Foundation/miniwob-plusplus.git; \
	else \
		echo "MiniWoB++ repository already exists, skipping clone..."; \
	fi
	@echo "Resetting to specific commit for reproducibility..."
	git -C "./miniwob-plusplus" reset --hard 7fd85d71a4b60325c6585396ec4f48377d049838
	@echo "Adding MINIWOB_URL to .env file..."
	@echo "MINIWOB_URL=\"file://$(shell pwd)/miniwob-plusplus/miniwob/html/miniwob/\"" >> .env
	@echo "✅ MiniWoB++ setup complete!"
	@echo "💡 To use MiniWoB++, load the environment variables:"
	@echo "   source .env"

test-core:
	@echo "--- 🧪 Running tests ---"
	$(RUN) pytest -n auto ./tests/core

clean-miniwob:
	@echo "--- 🧹 Cleaning MiniWoB++ installation ---"
	rm -rf miniwob-plusplus
	@echo "✅ MiniWoB++ installation cleaned!"

help:
	@echo "Available targets:"
	@echo "  sync             - uv: install browsergym-core + dev tools (PYTHON=3.x optional)"
	@echo "  sync-all         - uv: install all browsergym packages + dev tools"
	@echo "  browsers         - Install Playwright Chromium"
	@echo "  lint             - Run ruff check + black --check"
	@echo "  fmt              - Apply ruff import sorting + black"
	@echo "  test             - Run the offline test suite (core tests)"
	@echo "  install          - pip: install project dependencies"
	@echo "  setup-miniwob    - Setup MiniWoB++ dependencies"
	@echo "  install-demo     - Install demo dependencies"
	@echo "  demo             - Run demo agent"
	@echo "  test-core        - Run core tests"
	@echo "  clean-miniwob    - Remove MiniWoB++ directory"
	@echo "  help             - Show this help message"

.PHONY: sync sync-all browsers lint fmt test install setup-miniwob install-demo demo test-core clean-miniwob help
