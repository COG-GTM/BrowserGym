# Contributing to BrowserGym

## Dev setup (uv, recommended)

BrowserGym is a monorepo of `browsergym-*` packages wired together as a
[uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) (see `[tool.uv.workspace]`
in the root `pyproject.toml`). Dependencies are pinned in `uv.lock`.

```sh
make sync                # uv sync: browsergym-core (editable) + lint/test tools into .venv
make sync PYTHON=3.13    # same, for a specific Python (3.10 - 3.13 are tested in CI)
make sync-all            # every browsergym package (pulls torch via visualwebarena)
make browsers            # playwright install chromium
```

Day to day:

```sh
make lint    # ruff check . && black --check .
make fmt     # ruff import sorting (--select I --fix) + black
make test    # offline test suite (tests/core); same as `make test-core`
```

Make targets use `uv run` when uv is installed; pass `RUN=` to use the active environment instead
(e.g. `make test-core RUN=`).

After changing dependencies in any `browsergym/*/requirements.txt`, run `uv lock` and commit
`uv.lock`.

## Dev setup (pip)

The pip install paths keep working:

```sh
make install                          # pip install -e every package + playwright chromium
pip install -r dev/requirements.txt   # what the non-core CI jobs use
```

Note: on Python 3.13, `playwright==1.44` pulls `greenlet==3.0.3`, which has no 3.13 wheel; the uv
workspace overrides it to `greenlet>=3.1.1`. With pip, `pip install "greenlet>=3.1.1"` first.

## Linting and formatting

- **black** (24.2.0) is the formatter. Do not reformat files you don't otherwise change.
- **ruff** is the linter (pyflakes, pycodestyle errors, isort). Pre-existing violations are
  baselined per file in `[tool.ruff.lint.per-file-ignores]`; when you clean up a file, delete its
  entry. New files must pass with no ignores.
- **pre-commit** runs ruff, black, blacken-docs and whitespace/YAML checks:

  ```sh
  uv run pre-commit install
  uv run pre-commit run --all-files
  ```

Keep the ruff/black versions in `.pre-commit-config.yaml` in sync with `[dependency-groups]`.

## CI

`.github/workflows/unit_tests.yml` runs `code-format` (black), `ruff`, and `browsergym-core` on a
Python 3.10 / 3.11 / 3.12 / 3.13 matrix with uv + caching. The benchmark jobs (miniwob, experiments,
webarena, visualwebarena, assistantbench) still install via `pip install -r dev/requirements.txt`.
