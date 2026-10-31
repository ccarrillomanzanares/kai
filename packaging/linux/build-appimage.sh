#!/usr/bin/env bash
# Wrap dist/kai/ (from PyInstaller) into dist/kai-VERSION-x86_64.AppImage.
# Usage: packaging/linux/build-appimage.sh VERSION
set -euo pipefail
cd "$(dirname "$0")/../.."
VERSION="${1:?version}"
APPDIR=build/kai.AppDir
TOOL=build/appimagetool

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -a dist/kai "$APPDIR/usr/lib/kai"
cp build/icons/kai.png "$APPDIR/kai.png"
ln -s kai.png "$APPDIR/.DirIcon"
sed "s/@VERSION@/$VERSION/" packaging/linux/kai.desktop > "$APPDIR/kai.desktop"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/kai/kai" "$@"
RUN
chmod +x "$APPDIR/AppRun"

if [ ! -x "$TOOL" ]; then
  curl -fsSL -o "$TOOL" \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "dist/kai-$VERSION-x86_64.AppImage"
