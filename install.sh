#!/usr/bin/env bash
# Instala ElYares: enlaces en ~/.local/bin, servicio systemd de usuario, hooks
# de Claude Code y, en omarchy, el hook de cambio de tema. Se puede correr las
# veces que sea: reemplaza lo suyo y no toca los demás hooks.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
bin_dir="$HOME/.local/bin"
unit_dir="$HOME/.config/systemd/user"
settings="$HOME/.claude/settings.json"
hook='$HOME/.local/bin/elyares-hook'   # literal: lo expande la shell de Claude

for dep in /usr/lib/libgtk4-layer-shell.so jq; do
  command -v "$dep" >/dev/null 2>&1 || [ -e "$dep" ] || { echo "Falta $dep" >&2; exit 1; }
done
/usr/bin/python3 -c 'import gi, cairo; gi.require_version("Gtk4LayerShell", "1.0")' \
  || { echo "Falta python-gobject, python-cairo o gtk4-layer-shell" >&2; exit 1; }

mkdir -p "$bin_dir" "$unit_dir"
for f in elyares-mascota elyares-hook elyares-ctl elyares-demo; do
  ln -sfn "$here/bin/$f" "$bin_dir/$f"
done
# Copia y no enlace: systemctl enable trata distinto a las units enlazadas.
install -m 644 "$here/systemd/elyares-mascota.service" "$unit_dir/"
echo "✓ binarios en $bin_dir y servicio en $unit_dir"

# En omarchy: al cambiar de tema, la mascota vuelve a leer el color de acento.
omarchy_hooks="$HOME/.config/omarchy/hooks"
if [ -d "$omarchy_hooks" ]; then
  mkdir -p "$omarchy_hooks/theme-set.d"
  ln -sfn "$here/omarchy/theme-set" "$omarchy_hooks/theme-set.d/elyares-mascota"
  echo "✓ hook de tema en $omarchy_hooks/theme-set.d"
fi

if [ -f "$settings" ]; then
  backup="$settings.elyares-bak-$(date +%F-%H%M%S)"
  cp "$settings" "$backup"
  tmp=$(mktemp)
  jq --arg hook "$hook" -f "$here/hooks.jq" "$settings" > "$tmp"
  [ -s "$tmp" ] && jq -e . "$tmp" >/dev/null
  mv "$tmp" "$settings"
  echo "✓ hooks registrados en $settings (respaldo: $backup)"
else
  echo "! no existe $settings: los hooks no se registraron" >&2
fi

systemctl --user daemon-reload
systemctl --user enable --now elyares-mascota.service
systemctl --user restart elyares-mascota.service
echo "✓ servicio activo. Prueba: elyares-demo"
