#!/bin/sh
# Usage: pip-install-app.sh <dir>
# Installs a Python app directory: pyproject.toml/setup.py -> pip install <dir>,
# else requirements.txt -> pip install -r. The dir is also put on PYTHONPATH by the image.
set -eu
dir="$1"
if [ -f "$dir/pyproject.toml" ] || [ -f "$dir/setup.py" ]; then
  pip install --no-cache-dir "$dir"
elif [ -f "$dir/requirements.txt" ]; then
  pip install --no-cache-dir -r "$dir/requirements.txt"
else
  echo "side-deploy: no pyproject.toml/setup.py/requirements.txt in $dir, nothing to install" >&2
fi
