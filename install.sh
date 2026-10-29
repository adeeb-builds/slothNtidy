#!/usr/bin/env bash
# slothNtidy installer for Mac / Linux. Run in Terminal:
#   curl -fsSL https://raw.githubusercontent.com/adeeb-builds/slothNtidy/main/install.sh | bash
set -e
DEST="$HOME/slothNtidy"
echo "Installing slothNtidy into $DEST (needs internet once, about 600 MB)..."
TMP=$(mktemp -d)
curl -fsSL https://github.com/adeeb-builds/slothNtidy/archive/refs/heads/main.zip -o "$TMP/s.zip"
rm -rf "$DEST"
unzip -q "$TMP/s.zip" -d "$TMP"
mv "$TMP/slothNtidy-main" "$DEST"
rm -rf "$TMP"
cd "$DEST"
chmod +x setup.sh run.sh
./setup.sh
echo
echo "Done! Start slothNtidy any time with:  ~/slothNtidy/run.sh"
