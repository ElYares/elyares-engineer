#!/usr/bin/env bash
# Instala elyares-engineer: enlaces en ~/.local/bin, servicio systemd de usuario, hooks
# de Claude Code, los agentes de la familia y su candado, la envoltura de su barra de
# estado, el aviso de comandos largos en ~/.bashrc y, en omarchy, el hook de
# cambio de tema. Se puede correr las veces que sea: reemplaza lo suyo y no
# toca lo demás.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
bin_dir="$HOME/.local/bin"
unit_dir="$HOME/.config/systemd/user"
settings="$HOME/.claude/settings.json"
hook='$HOME/.local/bin/elyares-hook'   # literal: lo expande la shell de Claude
statusline='$HOME/.local/bin/elyares-statusline'
conf_dir="${XDG_CONFIG_HOME:-$HOME/.config}/elyares-engineer"
bashrc="$HOME/.bashrc"

for dep in /usr/lib/libgtk4-layer-shell.so jq; do
  command -v "$dep" >/dev/null 2>&1 || [ -e "$dep" ] || { echo "Falta $dep" >&2; exit 1; }
done
/usr/bin/python3 -c 'import gi, cairo; gi.require_version("Gtk4LayerShell", "1.0")' \
  || { echo "Falta python-gobject, python-cairo o gtk4-layer-shell" >&2; exit 1; }

# Antes se llamaba elyares-mascota. Se quita lo que dejó con ese nombre, para
# que no corran los dos a la vez, y sus preferencias pasan al nombre nuevo.
old=elyares-mascota
old_conf="${XDG_CONFIG_HOME:-$HOME/.config}/$old"
if [ -e "$unit_dir/$old.service" ] || [ -L "$bin_dir/$old" ] || [ -d "$old_conf" ]; then
  systemctl --user disable --now "$old.service" 2>/dev/null || true
  rm -f "$unit_dir/$old.service" "$bin_dir/$old" "$HOME/.config/omarchy/hooks/theme-set.d/$old"
  [ -d "$old_conf" ] && [ ! -e "$conf_dir" ] && mv "$old_conf" "$conf_dir"
  [ -f "$bashrc" ] \
    && sed -i --follow-symlinks "/^# >>> $old >>>/,/^# <<< $old <<</d" "$bashrc"
  echo "✓ se quitó lo que quedaba de $old"
fi

mkdir -p "$bin_dir" "$unit_dir"
for f in elyares-engineer elyares-hook elyares-ctl elyares-demo elyares-statusline; do
  ln -sfn "$here/bin/$f" "$bin_dir/$f"
done
# Copia y no enlace: systemctl enable trata distinto a las units enlazadas.
install -m 644 "$here/systemd/elyares-engineer.service" "$unit_dir/"
echo "✓ binarios en $bin_dir y servicio en $unit_dir"

# Las letras que se eligen en Ajustes (fonts/): se copian a las del usuario.
font_dir="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/elyares-engineer"
mkdir -p "$font_dir"
find "$here/fonts" -type f \( -name '*.ttf' -o -name '*.otf' \) -exec cp -f {} "$font_dir/" \;
fc-cache -f "$font_dir" 2>/dev/null || true
echo "✓ letras en $font_dir"

# La app en ventana: su entrada para el lanzador (Walker) y su ícono. Se
# copian, no se enlazan; el `Exec` lleva la ruta de este equipo.
apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons_dir="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
mkdir -p "$apps_dir" "$icons_dir"
sed "s|@BIN@|$bin_dir|" "$here/share/dev.elyares.Engineer.desktop" > "$apps_dir/dev.elyares.Engineer.desktop"
install -m 644 "$here/share/dev.elyares.Engineer.svg" "$icons_dir/"
echo "✓ entrada «Elyares Engineer» en $apps_dir"

# En omarchy: al cambiar de tema, elyares-engineer vuelve a leer el color de acento.
omarchy_hooks="$HOME/.config/omarchy/hooks"
if [ -d "$omarchy_hooks" ]; then
  mkdir -p "$omarchy_hooks/theme-set.d"
  ln -sfn "$here/omarchy/theme-set" "$omarchy_hooks/theme-set.d/elyares-engineer"
  echo "✓ hook de tema en $omarchy_hooks/theme-set.d"
fi

# Los agentes de la familia. Claude Code los lee de ~/.claude/agents al abrir
# una sesión, y el auditor busca sus catálogos en ~/.claude/elyares/seguridad
# (no en ~/.claude/rules: ahí se cargarían enteros en cada sesión). Las de
# proceso (PSP) van en ~/.claude/elyares/proceso por lo mismo.
# Copia y no enlace: son instrucciones para todas las sesiones, y enlazados
# cambiarían solos con lo que haya en esta carpeta (otra rama, un cambio a
# medias). Para actualizarlos se vuelve a correr install.sh. Son suyos por el
# nombre: pisa los `elyares-*.md` que se llamen como los de agents/.
agents_dir="$HOME/.claude/agents"
rules_dir="$HOME/.claude/elyares/seguridad"
process_dir="$HOME/.claude/elyares/proceso"
shopt -s nullglob
agents=("$here"/agents/elyares-*.md)
rules=("$here"/rules/seguridad/*.md)
process=("$here"/rules/proceso/*.md)
shopt -u nullglob
if [ ${#agents[@]} -gt 0 ]; then
  mkdir -p "$agents_dir"
  for f in "${agents[@]}"; do
    rm -f "$agents_dir/$(basename "$f")"      # si era un enlace, no se escribe a través de él
    install -m 644 "$f" "$agents_dir/"
  done
  echo "✓ ${#agents[@]} agentes en $agents_dir (valen para las sesiones nuevas de Claude)"
  # Su candado: el hook que frena lo que escribe un agente que solo lee. Copia
  # y no enlace, como ellos: un hook que no se encuentra no frena nada, y un
  # enlace a esta carpeta se rompe con otra rama.
  rm -f "$bin_dir/elyares-guard"
  install -m 755 "$here/elyares/guard.py" "$bin_dir/elyares-guard"
  echo "✓ candado de los agentes en $bin_dir/elyares-guard"
fi
if [ ${#rules[@]} -gt 0 ]; then
  [ -L "$rules_dir" ] && rm -f "$rules_dir"
  mkdir -p "$rules_dir"
  install -m 644 "${rules[@]}" "$rules_dir/"
  echo "✓ catálogos del auditor en $rules_dir"
fi
if [ ${#process[@]} -gt 0 ]; then
  [ -L "$process_dir" ] && rm -f "$process_dir"
  mkdir -p "$process_dir"
  install -m 644 "${process[@]}" "$process_dir/"
  echo "✓ reglas de proceso (PSP) en $process_dir"
fi

if [ -f "$settings" ]; then
  backup="$settings.elyares-bak-$(date +%F-%H%M%S)"
  cp "$settings" "$backup"
  tmp=$(mktemp)
  jq --arg hook "$hook" -f "$here/hooks.jq" "$settings" > "$tmp"
  [ -s "$tmp" ] && jq -e . "$tmp" >/dev/null
  mv "$tmp" "$settings"
  echo "✓ hooks registrados en $settings (respaldo: $backup)"

  # Barra de estado: se envuelve la que haya. Es el único sitio donde Claude
  # Code dice cuánto contexto lleva la sesión y cuánto del límite de 5 h.
  current=$(jq -r '.statusLine.command // empty' "$settings")
  if [ -z "$current" ]; then
    echo "! no hay barra de estado en $settings: elyares-engineer no verá el uso de Claude" >&2
  elif [ "$current" != "$statusline" ]; then
    mkdir -p "$conf_dir"
    printf '%s' "$current" > "$conf_dir/statusline.cmd"
    tmp=$(mktemp)
    jq --arg c "$statusline" '.statusLine.command = $c' "$settings" > "$tmp"
    [ -s "$tmp" ] && jq -e . "$tmp" >/dev/null
    mv "$tmp" "$settings"
    echo "✓ barra de estado envuelta (la original quedó en $conf_dir/statusline.cmd)"
  fi
else
  echo "! no existe $settings: los hooks no se registraron" >&2
fi

# Comandos largos de la terminal: bash avisa a elyares-engineer cuando terminan.
if [ -f "$bashrc" ]; then
  grep -q '^# >>> elyares-engineer >>>' "$bashrc" \
    || cp "$bashrc" "$bashrc.elyares-bak-$(date +%F-%H%M%S)"
  sed -i --follow-symlinks '/^# >>> elyares-engineer >>>/,/^# <<< elyares-engineer <<</d' "$bashrc"
  printf '%s\n' '# >>> elyares-engineer >>>' \
    "[ -r \"$here/shell/elyares.bash\" ] && . \"$here/shell/elyares.bash\"" \
    '# <<< elyares-engineer <<<' >> "$bashrc"
  echo "✓ aviso de comandos largos en $bashrc (vale para las terminales nuevas)"
fi

systemctl --user daemon-reload
systemctl --user enable --now elyares-engineer.service
systemctl --user restart elyares-engineer.service
echo "✓ servicio activo. Prueba: elyares-demo"
