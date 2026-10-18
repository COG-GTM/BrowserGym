#!/bin/sh
# Usage: select-src.sh <context-dir> <preferred-rel-path> <stub-rel-path> <dest>
# Copies the real app sources if present in the build context, otherwise the deploy/ stub,
# and records which one was used in <dest>/.side-source.
set -eu
ctx="$1"; preferred="$2"; stub="$3"; dest="$4"
if [ -d "$ctx/$preferred" ] && [ -n "$(ls -A "$ctx/$preferred" 2>/dev/null)" ]; then
  src="$preferred"
else
  echo "side-deploy: '$preferred' not found in build context, using stub '$stub'" >&2
  src="$stub"
fi
mkdir -p "$dest"
cp -a "$ctx/$src/." "$dest/"
echo "$src" > "$dest/.side-source"
echo "side-deploy: using sources from $src"
