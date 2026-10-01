# ElYares

Mascota que vive en el borde de arriba del monitor, debajo de Waybar, y vigila
las sesiones de Claude Code. Se asoma mientras Claude trabaja, se abre cuando
pide permiso, termina o se queda esperando, y un clic en el texto te lleva al
pane de tmux de esa sesión. Los permisos se pueden contestar ahí mismo con
Permitir o Denegar.

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
- **`elyares-hook ask`** es la excepción: es síncrono y se queda esperando en
  el socket a que pulses Permitir o Denegar (ver abajo).
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
| `PermissionRequest` | `ask` | antena roja con botones Permitir / Denegar |
| `Notification` · `permission_prompt` | `permission` | antena roja, isla abierta |
| `Notification` · `idle_prompt` | `idle` | confundida: lleva un rato esperándote |
| `Stop` | `stop` | saltito y "Listo en 3 min 12 s" |
| `StopFailure` | `failure` | confundida con el motivo |
| `SessionEnd` | `session-end` | olvida la sesión |

Con varias sesiones muestra la más urgente (permiso > esperando > terminó >
trabajando) y cuántas hay. Con el No molestar de swaync se duerme.

Al abrirla a mano (clic en la pastilla, `elyares-ctl open` o, en modo normal,
pasando el ratón) salen debajo las demás sesiones, una por fila: un punto con
el color del estado, el proyecto y lo que está haciendo. Un clic en la fila
lleva a su pane de tmux. Caben cuatro filas; si hay más, la última dice
cuántas faltan. Con los botones de Permitir / Denegar no hay lista.

La lista incluye las sesiones en reposo (aro gris hueco, "En reposo hace 12 min"):
las que terminaron su turno y están en el prompt. Si no hay ninguna activa, la
cabecera dice "Sin sesiones activas". La mascota solo conoce las sesiones que
le han mandado algún evento; al abrir la lista olvida las que tenían un pane
de tmux que ya no existe, o cuyo servidor de tmux ya no corre.

Las sesiones sobreviven al reinicio del servicio: se guardan en
`$XDG_RUNTIME_DIR/elyares-sessions.json` y al arrancar vuelven como estaban.
Un permiso pendiente vuelve sin botones (el hook que esperaba el clic se fue
con el servicio anterior) y se contesta en la terminal. Al apagar la máquina
el archivo se borra, igual que los panes de tmux.

El detalle se corta con "…" cuando la isla se abre sola. Para leerlo entero,
pasa el ratón por la isla o ábrela a mano: crece y lo muestra en hasta cuatro
líneas. Cuando pide permiso lo muestra entero siempre, para ver el comando
completo antes de contestar. Las filas de la lista siguen en una línea.

Un clic en la mascota la enoja; tres rápidos la marean.

### Alertas de DevHerd

Si corre [DevHerd](https://github.com/ElYares/devherd) Observe, la mascota le
pregunta cada 10 s a su API local (`127.0.0.1:9777`) y avisa de esto:

| Qué pasó | En la isla |
|---|---|
| Un problema de nivel error recibió eventos | "Error nuevo: …" o "Error otra vez (N): …" |
| Un contenedor vigilado se reinició solo | "queue se reinició", o "reinicia en bucle" desde 3 en 5 min |
| Un contenedor vigilado se cayó con error | "app se cayó (código 1)" o "(sin memoria)" |
| Observe dejó de responder (3 consultas) | "Observe no responde" |

Una alerta nueva abre la isla 8 s, con la mascota enojada y la antena roja.
Después queda como una fila más en la lista (punto rojo), debajo de las
sesiones activas de Claude, hasta que el problema se resuelve o pasan 10 min
sin novedades. Un clic abre el panel de Observe y la descarta; descartada, no
vuelve a salir en 15 min. El contador "N sesiones" no cuenta las alertas.

Al arrancar solo toma la foto: lo que ya estaba roto no se anuncia. Un
contenedor parado a mano (`docker stop`, `devherd down`) no avisa: solo cuenta
como caída una salida con código de error. Observe vigila únicamente los
proyectos conectados con `devherd observe attach`. Para apagar las alertas,
`"devherd": false` en `~/.config/elyares-mascota/settings.json`.

Las alertas son un evento más del socket (`alert` y `alert-clear`, con `name`,
`message` y `url`), así que cualquier otro programa puede mandar las suyas.

### Color de acento

En omarchy, la antena y el foco de la laptop mientras Claude trabaja, y el
punto de "trabajando" en la lista, toman el color de acento del tema activo
(`accent` en `~/.config/omarchy/current/theme/colors.toml`). Los demás estados
conservan su color: rojo para permiso, amarillo para esperando y verde para
terminó. `install.sh` deja un hook en `~/.config/omarchy/hooks/theme-set.d/`
que avisa a la mascota al cambiar de tema, así que el color cambia sin
reiniciar nada. Sin omarchy se queda con su azul.

### Modo vidrio

Viene apagado. Con `elyares-ctl glass` el fondo de la isla pasa de negro casi
opaco a translúcido, con un filo claro en el borde. La preferencia se guarda
en `~/.config/elyares-mascota/settings.json` (`"glass": true`).

El desenfoque de lo que queda detrás lo hace Hyprland, no la mascota. Sin
estas reglas el fondo queda translúcido pero nítido (`~/.config/hypr/looknfeel.conf`):

```
layerrule = blur on, match:namespace elyares
layerrule = ignore_alpha 0.20, match:namespace elyares
```

`ignore_alpha` deja sin desenfocar la parte transparente de la ventana. Sobre
fondos claros o muy coloridos el texto se lee peor que con el fondo negro.

### Modo compacto

Viene prendido. La isla se queda en una pastilla chiquita con la mascota en
miniatura, que sigue animada (teclea, salta al terminar, se confunde si
esperas). Un clic en la pastilla la abre con lo que está haciendo esa sesión, y
se vuelve a cerrar cuando el ratón sale. Un permiso sí se abre solo, porque hay
que contestarlo.

Clic derecho en la isla prende o apaga el modo compacto. Sin él, se asoma con
la mascota completa y se abre al pasar el ratón. La preferencia se guarda en
`~/.config/elyares-mascota/settings.json`.

### Atajos de teclado

`elyares-ctl` manda órdenes a la mascota por el mismo socket:

| Orden | Qué hace |
|---|---|
| `elyares-ctl open` | abre la isla con lo que hace Claude; se cierra sola a los 6 s o al repetir |
| `elyares-ctl hide` | la esconde del todo (ni la ceja ni el hover); otra vez la muestra |
| `elyares-ctl compact` | prende o apaga el modo compacto, como el clic derecho |
| `elyares-ctl theme` | vuelve a leer el color de acento del tema (lo llama el hook de omarchy) |
| `elyares-ctl glass` | prende o apaga el modo vidrio |

Escondida no muestra ni los permisos: se contestan en la terminal. El estado
de escondida no se guarda; al reiniciar el servicio vuelve a aparecer.

En Hyprland (`~/.config/hypr/bindings.conf`):

```
bindd = SUPER ALT, Y, Mascota: abrir la isla, exec, elyares-ctl open
bindd = SUPER SHIFT ALT, Y, Mascota: esconder o mostrar, exec, elyares-ctl hide
bindd = SUPER CTRL ALT, Y, Mascota: modo compacto, exec, elyares-ctl compact
```

### Permitir / Denegar

En modo interactivo Claude Code corre el hook `PermissionRequest` **a la par**
del prompt de la terminal y se queda con la primera respuesta. Por eso el hook
puede esperar tu clic sin bloquear nada: el prompt de la terminal sigue ahí.

- **Permitir o Denegar en la isla:** el hook imprime la decisión y el prompt de
  la terminal se cierra solo. Al denegar, Claude recibe "El usuario lo denegó
  desde la mascota ElYares." y el turno se corta, como con el No de la
  terminal: la decisión lleva `interrupt: true` y la isla pasa a "Esperando tu
  respuesta".
- **Contestas en la terminal:** con Sí llega `tool-done` y la isla suelta el
  hook; con No, Claude mata el hook y la isla pasa a "Esperando tu respuesta".
- **Headless (`claude -p`, SDK):** ahí el hook sí bloquearía, así que sale sin
  decidir si el proceso de Claude no tiene terminal.
- `AskUserQuestion` y `ExitPlanMode` no llevan botones: piden una respuesta, no
  un permiso.

## Notas

- **Python del sistema.** El lanzador usa `/usr/bin/python3` a propósito: el
  de mise no trae PyGObject.
- **`LD_PRELOAD`.** gtk4-layer-shell tiene que cargarse antes que
  libwayland-client, y desde Python solo se logra así. Lo pone `bin/elyares-mascota`.
- **CPU.** Escondida no dibuja nada (0%). Asomada y quieta va a 12 fps, ~3% de
  un núcleo; solo las transiciones van a 60 fps.
- **Logs:** `journalctl --user -u elyares-mascota`.

## Pendiente

- Información en la pastilla del modo compacto: punto de color y número de
  sesiones.
