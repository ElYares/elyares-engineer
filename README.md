# ElYares

Mascota que vive en el borde de arriba del monitor, debajo de Waybar, y vigila
las sesiones de Claude Code. Se asoma mientras Claude trabaja, se abre cuando
pide permiso, termina o se queda esperando, y un clic en el texto te lleva al
pane de tmux de esa sesión.

Está hecha para omarchy (Hyprland + Waybar + tmux + ghostty), pero no toca
nada de `~/.local/share/omarchy/`: es una capa de Wayland propia.

## Instalar

```bash
./install.sh     # enlaces en ~/.local/bin, servicio systemd de usuario y hooks
elyares-demo     # recorre los estados con eventos falsos
```

`install.sh` se puede correr las veces que sea. Respalda
`~/.claude/settings.json` antes de tocarlo, agrega sus hooks junto a los que ya
hay y no modifica los demás. `./uninstall.sh` lo deshace todo.

Requisitos (en omarchy ya vienen): `gtk4`, `gtk4-layer-shell`,
`python-gobject`, `python-cairo`, `jq`.

## Cómo funciona

```
Claude Code ──hook (async)──▶ elyares-hook ──socket──▶ elyares-mascota
                                              $XDG_RUNTIME_DIR/elyares.sock
```

- **`bin/elyares-hook <evento>`** lee el payload del hook, se queda con lo que
  hace falta y lo manda al socket. Si la mascota no está corriendo sale en
  silencio. Los hooks van con `async: true`: nunca frenan a Claude.
- **`elyares/`** es el daemon: una ventana GTK4 con gtk4-layer-shell anclada
  arriba y sin foco de teclado. La región de entrada sigue a la isla, así que
  fuera de ella los clics pasan a las ventanas de abajo.
- Sigue al monitor enfocado por el socket de eventos de Hyprland, y los ojos
  siguen al cursor con `cursorpos` del socket de pedidos (sin lanzar hyprctl).

| Hook de Claude Code | Evento | La mascota |
|---|---|---|
| `UserPromptSubmit` | `start` | se asoma trabajando ("Pensando…") |
| `PreToolUse` | `tool` | teclea y dice qué archivo o comando toca |
| `PostToolUse` | `tool-done` | baja la antena roja tras aprobar un permiso |
| `Notification` · `permission_prompt` | `permission` | antena roja, isla abierta |
| `Notification` · `idle_prompt` | `idle` | confundida: lleva un rato esperándote |
| `Stop` | `stop` | saltito y "Listo en 3 min 12 s" |
| `StopFailure` | `failure` | confundida con el motivo |
| `SessionEnd` | `session-end` | olvida la sesión |

Con varias sesiones muestra la más urgente (permiso > esperando > terminó >
trabajando) y cuántas hay. Con el No molestar de swaync se duerme.

Un clic en la mascota la enoja; tres rápidos la marean.

## Notas

- **Python del sistema.** El lanzador usa `/usr/bin/python3` a propósito: el
  de mise no trae PyGObject.
- **`LD_PRELOAD`.** gtk4-layer-shell tiene que cargarse antes que
  libwayland-client, y desde Python solo se logra así. Lo pone `bin/elyares-mascota`.
- **CPU.** Escondida no dibuja nada (0%). Asomada y quieta va a 12 fps, ~3% de
  un núcleo; solo las transiciones van a 60 fps.
- **Logs:** `journalctl --user -u elyares-mascota`.

## Pendiente

- Permitir / Denegar desde la isla (hook `PermissionRequest`).
- Sonidos con `pw-play`, color de acento del tema de omarchy, atajo de teclado
  para esconderla.
