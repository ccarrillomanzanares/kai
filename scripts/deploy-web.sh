#!/usr/bin/env bash
# Publish website/ to https://ccmai.org/kai/ (served by Apache on this VPS).
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)/website/"
DEST="/var/www/ccmai.org/kai/"

rsync -a --delete "$SRC" "$DEST"
echo "Deployed to $DEST -> https://ccmai.org/kai/"
