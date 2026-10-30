#!/usr/bin/env bash
# Install the kai diagnostics receiver on the VPS (needs sudo):
#  - systemd service kai-diag on 127.0.0.1:8092, reports saved in ~ccmai/kai-diag
#  - Apache route https://ccmai.org/kai-diag/ -> 127.0.0.1:8092 (backup of the vhost first)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONF=/etc/apache2/sites-available/ccmai.org-ssl.conf
ANCHOR="    ProxyPassReverse /aios-diag/ http://127.0.0.1:8091/aios-diag/"

mkdir -p /home/ccmai/kai-diag
sudo install -m 644 "$HERE/kai-diag.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kai-diag

if ! grep -q kai-diag "$CONF"; then
    sudo cp -p "$CONF" "$CONF.bak-$(date +%Y%m%d%H%M%S)"
    sudo sed -i "\|^$ANCHOR\$|a\\
\\
    # kai-diag: kai diagnostics uploads (kai repo, server/diag_server.py)\\
    ProxyPass        /kai-diag/ http://127.0.0.1:8092/kai-diag/\\
    ProxyPassReverse /kai-diag/ http://127.0.0.1:8092/kai-diag/" "$CONF"
    grep -q kai-diag "$CONF" || { echo "Anchor not found in $CONF, add the ProxyPass lines by hand"; exit 1; }
fi

sudo apache2ctl configtest
sudo systemctl reload apache2
sleep 1
curl -fsS https://ccmai.org/kai-diag/ && echo " <- kai-diag is live"
