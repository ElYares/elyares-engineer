#!/usr/bin/env bash
# Deshace install.sh: servicio, enlaces, hooks, la envoltura de la barra de
# estado y el bloque de ~/.bashrc. No toca los demás hooks.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
settings="$HOME/.claude/settings.json"
statusline='$HOME/.local/bin/elyares-statusline'
conf_dir="${XDG_CONFIG_HOME:-$HOME/.config}/elyares-engineer"
bashrc="$HOME/.bashrc"

# También lo que haya quedado del nombre anterior, elyares-mascota.
for name in elyares-engineer elyares-mascota; do
  systemctl --user disable --now "$name.service" 2>/dev/null || true
  rm -f "$HOME/.config/systemd/user/$name.service" "$HOME/.local/bin/$name" \
    "$HOME/.config/omarchy/hooks/theme-set.d/$name"
  [ -f "$bashrc" ] \
    && sed -i --follow-symlinks "/^# >>> $name >>>/,/^# <<< $name <<</d" "$bashrc"
done
systemctl --user daemon-reload
for f in elyares-hook elyares-ctl elyares-demo elyares-statusline; do
  rm -f "$HOME/.local/bin/$f"
done

if [ -f "$settings" ]; then
  cp "$settings" "$settings.elyares-bak-$(date +%F-%H%M%S)"
  tmp=$(mktemp)
  jq --arg hook '$HOME/.local/bin/elyares-hook' --arg remove true -f "$here/hooks.jq" "$settings" > "$tmp"
  [ -s "$tmp" ] && mv "$tmp" "$settings"

  # La barra de estado vuelve a ser la de antes.
  orig="$conf_dir/statusline.cmd"
  if [ "$(jq -r '.statusLine.command // empty' "$settings")" = "$statusline" ] && [ -s "$orig" ]; then
    tmp=$(mktemp)
    jq --arg c "$(cat "$orig")" '.statusLine.command = $c' "$settings" > "$tmp"
    [ -s "$tmp" ] && mv "$tmp" "$settings"
    rm -f "$orig"
  fi
fi
echo "✓ elyares-engineer desinstalado"
