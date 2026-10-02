# elyares-engineer

Una isla que vive en el borde de arriba del monitor, debajo de Waybar, y
vigila a los agentes con los que trabajas: las sesiones de Claude Code y lo que
corre a su alrededor (pruebas, contenedores, PRs, el pomodoro). Dentro va
ElYares, su mascota: se asoma mientras un agente trabaja, se abre cuando pide
permiso, termina o se queda esperando, y un clic en el texto te lleva al pane
de tmux de esa sesión. Los permisos se pueden contestar ahí mismo con Permitir
o Denegar.

Antes se llamaba `elyares-mascota`. `install.sh` quita lo que dejó con ese
nombre (servicio, enlace, bloque de `~/.bashrc`) y pasa sus preferencias a
`~/.config/elyares-engineer`.

Está hecha para omarchy (Hyprland + Waybar + tmux + ghostty), pero no toca
nada de `~/.local/share/omarchy/`: es una capa de Wayland propia.

## Instalar

```bash
./install.sh     # enlaces, servicio systemd de usuario, hooks, barra de estado y ~/.bashrc
elyares-demo     # recorre los estados con eventos falsos
```

`install.sh` se puede correr las veces que sea. Respalda
`~/.claude/settings.json` antes de tocarlo, agrega sus hooks junto a los que ya
hay y no modifica los demás. También envuelve la barra de estado de Claude y
agrega un bloque marcado a `~/.bashrc` (con respaldo la primera vez); ver "Uso
de Claude" y "Comandos largos" abajo. `./uninstall.sh` lo deshace todo.

Requisitos (en omarchy ya vienen): `gtk4`, `gtk4-layer-shell`,
`python-gobject`, `python-cairo`, `jq`.

## Cómo funciona

```
Claude Code ──hook (async)──▶ elyares-hook ──socket──▶ elyares-engineer
                                              $XDG_RUNTIME_DIR/elyares.sock
```

- **`bin/elyares-hook <evento>`** lee el payload del hook, se queda con lo que
  hace falta y lo manda al socket. Si elyares-engineer no está corriendo sale en
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
| `PostToolUseFailure` | `tool-fail` | si eran pruebas, dice cuáles fallaron |
| `PreCompact` | `compact` | sigue trabajando: "Compactando el contexto…" |
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
cabecera dice "Sin sesiones activas". elyares-engineer solo conoce las sesiones que
le han mandado algún evento; al abrir la lista olvida las que tenían un pane
de tmux que ya no existe, o cuyo servidor de tmux ya no corre.

Dos filas con el mismo proyecto son dos sesiones de Claude Code distintas en
ese repo. Una que corre en segundo plano (`/bg`, o una conversación que se
bifurcó a segundo plano) no tiene terminal: su fila lleva la marca "2º plano"
y, cuando pasa a la cabecera, el nombre que le puso Claude Code ("proyecto ·
nombre"). Para tener una a mano, Claude Code mantiene además una sesión de
repuesto que solo pinta su barra de estado: esa no sale ni se cuenta hasta que
hace algo. Una sesión se olvida cuando avisa de que termina, cuando su pane de
tmux ya no existe o, cada 15 s, cuando su proceso de Claude ya no existe (es
lo único que vale para las de segundo plano, que no tienen pane).

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

### Fuentes

Abierta a mano (con el atajo, un clic en la pastilla compacta o el ratón
encima), la isla lleva al pie una pastilla por fuente: Claude, devherd, coffe,
GitHub, terminal y uso. El punto dice cómo está:

| Punto | Significa |
|---|---|
| verde | conectada: responde, o su enganche está instalado |
| rojo | prendida pero con problemas: no responde o falta instalarla |
| gris | prendida, todavía sin datos |
| aro hueco | apagada |

Un clic en la pastilla prende o apaga la fuente, sin reiniciar nada; al
apagarla se van sus alertas y deja de consultarse. Claude no se apaga desde
ahí. La preferencia se guarda en `settings.json` con la clave de la fuente
(`devherd`, `coffe`, `github`, `terminal`, `usage`).

Con el cursor sobre una pastilla, sin hacer clic, sale debajo de la isla una
burbuja con lo que se sabe de esa fuente: qué trae, cómo está, cuántas alertas
suyas hay en la isla y qué hará el clic. Además:

- **GitHub:** cuántos PRs abiertos tienes y cómo van sus checks, cuántas
  revisiones te piden, qué cuentas respondieron y hace cuánto se consultó.
- **coffe:** cuánto queda del pomodoro o del descanso, la tarea en curso,
  cómo va el día y cuántos avisos esperan al descanso.
- **Punto rojo:** por qué (Observe no responde, el reloj de coffe está caído,
  falta `gh` o un enganche de `install.sh`), desde cuándo y qué hacer.

### Comandos y atajos, para consultar

La burbuja de una fuente trae además sus comandos, en dos columnas: el comando
y qué hace. La de devherd, los de `devherd`; la de coffe, los de `coffe`. Al
otro extremo de la franja, la pastilla **?** trae los del propio elyares-engineer:

- **Teclado:** los atajos que hay en Hyprland. No están escritos en ningún
  lado: se leen de `hyprctl binds` (los `bindd` cuya descripción empieza con
  "Engineer:"), así que siempre son los de verdad.
- **Ratón:** lo que hace cada clic.
- **Terminal:** las órdenes de `elyares-ctl`.

Es solo para mirar: nada de ahí se ejecuta ni se copia.

Los comandos salen de `elyares/commands.toml`. Para cambiarlos sin tocar el
repo, copia las secciones que quieras a
`~/.config/elyares-engineer/commands.toml`: una sección de ahí reemplaza a la
del repo y una vacía la quita. Cada sección lleva la clave de su pastilla
(`devherd`, `coffe`, `github`, `terminal`, `usage`, `claude`), y `raton` y
`engineer` son las de la pastilla **?**. Se relee cada vez que sale la burbuja.

```toml
[devherd]
"devherd serve" = "Levanta el proyecto, aplica el proxy y lo abre"

[github]
"gh pr checks" = "Los checks del PR de esta rama"
```

Lo mismo desde la terminal:

```
$ elyares-ctl status
Claude    conectada      3 sesiones
devherd   conectada
coffe     conectada      parado
GitHub    conectada      2 cuentas
terminal  conectada
uso       conectada
$ elyares-ctl toggle github
```

Con el atajo, la isla se abre aunque no haya ninguna sesión: es donde están
las fuentes.

### Alertas de DevHerd

Si corre [DevHerd](https://github.com/ElYares/devherd) Observe, elyares-engineer le
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

Con el ratón encima, o abierta a mano, la alerta trae su ficha: el detalle y
sus botones. Si está en la lista, un clic en su fila la sube a la cabecera.

| Alerta | Detalle | Botones |
|---|---|---|
| Error | archivo y línea donde revienta, servicio, eventos y la petición | Descartar · Timeline · Abrir |
| Contenedor reiniciado | sus últimas 8 líneas de log | Descartar · Logs |
| Contenedor caído | sus últimas 8 líneas de log | Descartar · Logs · Levantar |
| Observe no responde | | Descartar · Iniciar |

Timeline (`devherd observe timeline`), Logs (`docker logs -f`) y Levantar
(`devherd up`) abren una terminal nueva. Abrir lleva al panel de Observe e
Iniciar arranca el colector. Descartar quita la alerta sin abrir nada, y no
vuelve en 15 min; tras Levantar o Iniciar sí puede volver enseguida.

Al arrancar solo toma la foto: lo que ya estaba roto no se anuncia. Un
contenedor parado a mano (`docker stop`, `devherd down`) no avisa: solo cuenta
como caída una salida con código de error. Observe vigila únicamente los
proyectos conectados con `devherd observe attach`.

Las alertas son un evento más del socket (`alert` y `alert-clear`, con `name`,
`message` y `url`), así que cualquier otro programa puede mandar las suyas.
Con `tone` cambia el aspecto: sin él es un problema (punto rojo, mascota
enojada), `ok` es una buena noticia (verde, saltito) e `info` un aviso
(amarillo, confundida). Con `ttl` dura esos segundos en vez de 10 min.

También pueden traer ficha: `lines` (una lista con hasta 10 líneas de detalle;
una que empieza con `✓ `, `✗ ` u `○ ` lleva la marca a color),
`where` y `note` (el encabezado, a la izquierda y a la derecha) y `actions`
(hasta dos botones `{"label": "...", "url": "..."}`, o con `"jump": true` en
vez de la URL para que lleve al `pane` de la alerta). Por el socket un botón
no puede correr un comando: esos los ponen los vigilantes del propio elyares-engineer.

### Pomodoro (`coffe`)

Si está instalado [coffe](https://github.com/ElYares/omarchy-coffe-pomo),
elyares-engineer lee `coffe bar --watch`, lo mismo que Waybar. Mientras corre un
pomodoro la isla solo se abre sola para un permiso: "terminó", "esperando" y
las alertas se quedan asomadas (la mascota sí cambia de gesto, y con el ratón
encima se abre como siempre). Al empezar el descanso avisa, y si algo se quedó
esperando abre la lista. También avisa cuando el descanso se acaba.

### Uso de Claude

`install.sh` envuelve la barra de estado de Claude Code (`bin/elyares-statusline`
corre la que ya tenías y guarda su comando en
`~/.config/elyares-engineer/statusline.cmd`). Es el único sitio donde Claude
dice cuánto contexto lleva una sesión y cuánto del límite de 5 h. Con eso:

- Junto a cada sesión sale el porcentaje de contexto que lleva usado: gris,
  en amarillo desde el 70 % y en rojo desde el 90 %.
- Avisa cuando una sesión pasa del 90 % ("se va a compactar pronto"; el clic
  lleva a su pane) y cuando el límite de 5 h pasa del 80 % y del 95 %.
- Los dos avisos traen ficha. El del contexto dice qué sesión es (su carpeta
  y lo que hacía al llegar al 90 %), con el botón Ir al pane. El del límite
  lista las sesiones abiertas, con el contexto de cada una y lo que hace.
- Mientras Claude compacta, la sesión dice "Compactando el contexto…".

Sin barra de estado configurada no hay envoltura y esto no se ve.

### Comandos largos de la terminal

`install.sh` agrega a `~/.bashrc` una línea que carga `shell/elyares.bash`. Un
comando que tarda 30 s o más avisa al terminar: "Terminó en 2 min 05 s: make
test" (verde, se va a los 2 min) o "Falló (código 2) en 45 s: …" (rojo). El
clic lleva al pane donde corrió. Vale para las terminales que abras después
de instalar, y solo en bash.

Dentro de tmux la alerta trae ficha: la carpeta, el código de salida y lo que
tardó, las últimas 8 líneas que había en el pane al terminar y el botón Ir al
pane. Si el comando corría pruebas, la ficha es la de [Pruebas](#pruebas). Fuera de tmux no hay de dónde copiar lo que imprimió, ni pane al que ir.

No avisa de programas en los que uno se queda a propósito (editores, `ssh`,
`tmux`, `claude`, `less`…). El umbral se cambia con `ELYARES_CMD_SECS` y la
lista se amplía con `ELYARES_CMD_SKIP="mi-tui otra"`, los dos antes de la
línea de `~/.bashrc`. No hay estado de "trabajando" mientras corre: para eso
bash tendría que avisar al empezar cada comando.

### Pruebas

Cuando corren las pruebas de un proyecto, la isla muestra la lista: cuáles
pasaron (✓ verde), cuáles fallaron (✗ rojo, siempre arriba) y cuáles se
saltaron (○), con el total a la derecha ("12 ✓ · 1 ✗ · 2 ○"). Caben diez
líneas: primero las que fallaron y luego las últimas que corrieron.

- **En una terminal, en vivo.** Dentro de tmux, al lanzar un comando de
  pruebas la isla se abre con "Corriendo pruebas" y se queda abierta mientras
  corren, con la lista llenándose. Al terminar dice "Pruebas en verde: 13
  pasaron en 12 s" o "Pruebas en rojo: 1 falló, 12 pasaron en 12 s" y vuelve
  a portarse como cualquier alerta (8 s abierta; en verde se va a los 2 min).
  Descartar la quita aunque sigan corriendo; la siguiente corrida vuelve a
  salir. En un pomodoro, o en modo compacto, no se abre sola.
- **Las que corre Claude, al terminar.** Claude Code solo entrega lo que
  imprimió un comando cuando acaba, así que no hay lista en vivo: al terminar
  sale la misma alerta con el resultado, sobre la sesión que sigue trabajando.

Cuenta como pruebas un comando con `pytest`, `phpunit`, `pest`, `vitest`,
`jest`, `tox`, `-m unittest`, o `test` después de `artisan`, `sail`, `go`,
`cargo`, `deno`, `bun`, `mvn`, `composer`, `make`, `just`, `npm`, `pnpm` o
`yarn` (también `make test-unit`, `npm run test:e2e`…). Da igual lo que lleve
delante: `docker compose exec app php artisan test` vale.

Lo que se ve depende de lo que el programa imprime:

| Programa | Lista de pruebas |
|---|---|
| pest, `artisan test`, `cargo test`, `pytest -v`, `go test -v`, `unittest -v`, `vitest --reporter=verbose`, `jest --verbose` | una línea por prueba, mientras corren |
| vitest y jest sin más | una línea por archivo, y las pruebas que fallan |
| `pytest`, unittest y phpunit sin `-v` | solo cuántas van; las que fallan salen con su nombre al final |
| `go test` sin `-v` | las que fallan, y los paquetes que pasan |

Para seguirlas en vivo, `shell/elyares.bash` le pide a tmux que copie lo que
imprime el pane a `$XDG_RUNTIME_DIR/elyares-tests-<pane>.log` (`pipe-pane`)
mientras dura el comando; elyares-engineer lo relee cada medio segundo y lo borra al
terminar. tmux lleva una sola copia por pane: si el pane ya se está copiando a
otro sitio (un plugin de registro), no se toca y esas pruebas avisan solo al
final, como un comando largo. Fuera de tmux, lo mismo.

### GitHub

Con `gh` instalado, cada 2 min pregunta por tus pull requests abiertos y
avisa cuando los checks de uno pasan a verde o a rojo, y cuando te piden
revisar un PR. El clic abre el PR. Consulta todas las cuentas de `gh`; para
elegir, `"github_accounts": ["Cuenta"]` en `settings.json`. El token se le
pide a `gh` en cada consulta y no se guarda.

Un PR en rojo trae ficha: el check que se cayó (y cuántos más), las últimas 8
líneas del log de sus pasos caídos y los botones Reintentar y Abrir PR.
Reintentar abre una terminal con `gh run rerun --failed`, con la cuenta que
vio el PR, y quita la alerta; el siguiente cambio de los checks vuelve a
avisar. El log y Reintentar son solo para checks de GitHub Actions, y GitHub
borra los logs a los 90 días: sin log, la ficha lista los demás checks caídos.

### Vista previa del código

Cuando la sesión principal edita un archivo (`Edit`, `MultiEdit`, `Write`,
`NotebookEdit`), la isla puede mostrar el fragmento que cambia: se ensancha y
enseña un diff de hasta 12 líneas, con lo quitado en rojo y lo agregado en
verde, el nombre del archivo, la línea donde cae el cambio y cuántas líneas
suben y bajan.

- **Abierta a mano** (atajo, clic en la pastilla compacta o ratón encima)
  sale mientras dura esa edición; la siguiente herramienta la quita. Con el
  atajo se queda 20 s en vez de 6, para dar tiempo a leer.
- **Al pedir permiso** para editar o escribir un archivo sale siempre, encima
  de Permitir / Denegar: se ve el cambio antes de contestar.

Es solo para mirar: no se puede editar ni aceptar por trozos. De un
`MultiEdit` enseña el primer cambio y dice cuántos son. El fragmento viaja por
el socket local y vive en memoria: no se guarda entre reinicios. Solo se ve el
de la sesión principal, no el de las filas de la lista.

### Colores del texto

El detalle de una sesión casi siempre es código, así que va resaltado
(`elyares/paint.py`): el verbo ("Ejecutando", "Leyendo") apagado, y después
cada trozo con su color.

| Trozo | Ejemplo | Color del tema |
|---|---|---|
| programa | `docker`, `make` | `accent` |
| opción | `-f`, `--force-recreate` | `color13` |
| cadena o patrón | `"salida final.log"` | `color10` |
| ruta o archivo | `/tmp/out.txt`, `Auth.php` | `color14` |
| variable | `FOO=1`, `$HOME` | `color11` |
| número | `30` | `color9` |
| lo demás | `compose`, `up` | `foreground` |

En una ruta, la carpeta va apagada y el nombre del archivo a color. Un detalle
que no es código ("Pensando…", "Listo en 3 min") va en un gris del tema.

El porcentaje de contexto tiene su propia escala: verde hasta el 50 %, arena
hasta el 70 %, ámbar hasta el 90 % y rojo desde ahí. El ámbar y el rojo son
fijos y no salen del tema, para que un aviso parezca un aviso con cualquiera.

Los colores salen de `colors.toml` del tema de omarchy, un poco aclarados para
que se lean sobre la isla, y cambian con él. Sin omarchy hay una paleta fija.

### Color de acento

En omarchy, la antena y el foco de la laptop mientras Claude trabaja, y el
punto de "trabajando" en la lista, toman el color de acento del tema activo
(`accent` en `~/.config/omarchy/current/theme/colors.toml`). Los demás estados
conservan su color: rojo para permiso, amarillo para esperando y verde para
terminó. `install.sh` deja un hook en `~/.config/omarchy/hooks/theme-set.d/`
que avisa a elyares-engineer al cambiar de tema, así que el color cambia sin
reiniciar nada. Sin omarchy se queda con su azul.

### Modo vidrio

Viene apagado. Con `elyares-ctl glass` el fondo de la isla pasa de negro casi
opaco a translúcido, con un filo claro en el borde. La preferencia se guarda
en `~/.config/elyares-engineer/settings.json` (`"glass": true`).

El desenfoque de lo que queda detrás lo hace Hyprland, no elyares-engineer. Sin
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
`~/.config/elyares-engineer/settings.json`.

### Atajos de teclado

`elyares-ctl` manda órdenes a elyares-engineer por el mismo socket:

| Orden | Qué hace |
|---|---|
| `elyares-ctl open` | abre la isla con lo que hace Claude; se cierra sola a los 6 s o al repetir |
| `elyares-ctl hide` | la esconde del todo (ni la ceja ni el hover); otra vez la muestra |
| `elyares-ctl compact` | prende o apaga el modo compacto, como el clic derecho |
| `elyares-ctl pin` | fija la isla abierta con todo a la vista; otra vez, la suelta. Como el clic central |
| `elyares-ctl theme` | vuelve a leer el color de acento del tema (lo llama el hook de omarchy) |
| `elyares-ctl glass` | prende o apaga el modo vidrio |
| `elyares-ctl allow` | permite lo que pide el permiso que la isla tiene a la vista |
| `elyares-ctl deny` | lo deniega y corta el turno, como el botón Denegar |
| `elyares-ctl status` | lista las fuentes y cómo está cada una |
| `elyares-ctl toggle <fuente>` | prende o apaga una fuente |

Escondida no muestra ni los permisos: se contestan en la terminal. El estado
de escondida no se guarda; al reiniciar el servicio vuelve a aparecer.

En Hyprland (`~/.config/hypr/bindings.conf`):

```
bindd = SUPER ALT, Y, Engineer: abrir la isla, exec, elyares-ctl open
bindd = SUPER SHIFT ALT, Y, Engineer: esconder o mostrar, exec, elyares-ctl hide
bindd = SUPER CTRL ALT, Y, Engineer: modo compacto, exec, elyares-ctl compact
bindd = SUPER ALT, U, Engineer: fijar o soltar, exec, elyares-ctl pin
```

Fijada, la isla se queda abierta como cuando le pasas el ratón por encima (el
detalle entero, la lista de sesiones, la ficha de una alerta y las fuentes),
pero sin tener que dejar el cursor ahí: no se cierra sola ni al irse el ratón,
ni en modo compacto. Arriba a la derecha dice "fijada". Se suelta con el mismo
atajo, con el clic central o con `elyares-ctl open`, y vuelve a asomarse y
esconderse como siempre. La preferencia (`pinned` en `settings.json`) se guarda:
tras reiniciar sigue fijada. Un permiso sigue mostrando sus botones, y
`elyares-ctl hide` la esconde igual.

Para contestar un permiso sin soltar el teclado:

```
bindd = SUPER ALT, A, Engineer: permitir, exec, elyares-ctl allow
bindd = SUPER ALT, BackSpace, Engineer: denegar, exec, elyares-ctl deny
```

### Permitir / Denegar

En modo interactivo Claude Code corre el hook `PermissionRequest` **a la par**
del prompt de la terminal y se queda con la primera respuesta. Por eso el hook
puede esperar tu clic sin bloquear nada: el prompt de la terminal sigue ahí.

- **Permitir o Denegar en la isla:** el hook imprime la decisión y el prompt de
  la terminal se cierra solo. Al denegar, Claude recibe "El usuario lo denegó
  desde elyares-engineer." y el turno se corta, como con el No de la
  terminal: la decisión lleva `interrupt: true` y la isla pasa a "Esperando tu
  respuesta".
- **Con el teclado:** `elyares-ctl allow` y `elyares-ctl deny` hacen lo mismo
  que los botones, y solo con el permiso que se ve en la cabecera: ni uno
  tapado por otra sesión, ni con la isla escondida, ni uno que salió hace
  menos de 0.6 s (no dio tiempo de leerlo). Si no contestan, dicen por qué y
  salen con 1. `allow` no vale desde un proceso lanzado por Claude: con un
  comando en segundo plano se aprobaría a sí mismo. El socket mira quién
  manda la orden (`SO_PEERCRED` y sus procesos padre) y la rechaza si entre
  ellos está `claude`, o si ya no se puede saber. `deny` vale desde donde sea.
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
  libwayland-client, y desde Python solo se logra así. Lo pone `bin/elyares-engineer`.
- **CPU.** Escondida no dibuja nada (0%). Asomada y quieta va a 12 fps, ~3% de
  un núcleo; solo las transiciones van a 60 fps.
- **Logs:** `journalctl --user -u elyares-engineer`.
- **Pruebas.** `make test` corre `tests/` con `unittest` y el python del
  sistema. No abren ninguna ventana ni llaman a nada de fuera: los vigilantes
  reciben fotos inventadas, el socket corre en una carpeta temporal con
  `elyares-hook` y `elyares-ctl` de verdad, y la isla se arma sin pantalla y
  se dibuja sobre una superficie de cairo. Con un python sin PyGObject las de
  la isla se saltan.

## Pendiente

- Información en la pastilla del modo compacto: punto de color y número de
  sesiones.
