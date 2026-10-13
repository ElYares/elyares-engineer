#!/usr/bin/env bash
# Deshace install.sh: servicio, enlaces, hooks, los agentes de la familia y sus
# catálogos, la envoltura de la barra de estado y el bloque de ~/.bashrc. No
# toca los demás hooks; de los agentes, quita los que se llaman como los de
# agents/.
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
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/dev.elyares.Engineer.desktop" \
  "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/dev.elyares.Engineer.svg"
for f in elyares-hook elyares-ctl elyares-demo elyares-statusline elyares-guard; do
  rm -f "$HOME/.local/bin/$f"
done
rules_dir="$HOME/.claude/elyares/seguridad"
shopt -s nullglob
for f in "$here"/agents/elyares-*.md; do
  rm -f "$HOME/.claude/agents/$(basename "$f")"
done
if [ -L "$rules_dir" ]; then
  # Una instalación vieja lo dejó como enlace a rules/: se quita el enlace,
  # nunca lo que hay detrás.
  rm -f "$rules_dir"
else
  for f in "$here"/rules/seguridad/*.md; do
    rm -f "$rules_dir/$(basename "$f")"
  done
fi
shopt -u nullglob
rmdir "$rules_dir" "$HOME/.claude/elyares" "$HOME/.claude/agents" 2>/dev/null || true

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
