#!/usr/bin/env bash
# Publish website/ to https://ccmai.org/kai/ (served by Apache on this VPS, behind Cloudflare).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/website/"
DEST="/var/www/ccmai.org/kai/"

rsync -a --delete "$SRC" "$DEST"

# Cloudflare caches assets for hours: version their URLs so each deploy shows up at once.
VERSION="$(date +%s)"
sed -i -E "s/(href=\"(style\.css|favicon\.svg))\"/\1?v=$VERSION\"/g" "$DEST/index.html"

echo "Deployed to $DEST -> https://ccmai.org/kai/ (assets v=$VERSION)"
