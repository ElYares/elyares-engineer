#!/usr/bin/env bash
# Deshace install.sh: servicio, enlaces y hooks. No toca los demás hooks.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
settings="$HOME/.claude/settings.json"

systemctl --user disable --now elyares-mascota.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/elyares-mascota.service"
systemctl --user daemon-reload
for f in elyares-mascota elyares-hook elyares-demo; do rm -f "$HOME/.local/bin/$f"; done

if [ -f "$settings" ]; then
  cp "$settings" "$settings.elyares-bak-$(date +%F-%H%M%S)"
  tmp=$(mktemp)
  jq --arg hook '$HOME/.local/bin/elyares-hook' --arg remove true -f "$here/hooks.jq" "$settings" > "$tmp"
  [ -s "$tmp" ] && mv "$tmp" "$settings"
fi
echo "✓ ElYares desinstalado"
