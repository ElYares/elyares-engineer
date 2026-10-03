# elyares-engineer

Una isla que vive en el borde de arriba del monitor, debajo de Waybar, y
vigila a los agentes con los que trabajas: las sesiones de Claude Code y lo que
corre a su alrededor (pruebas, contenedores, PRs, el pomodoro). Dentro va
ElYares, su mascota: se asoma mientras un agente trabaja y se abre cuando pide
permiso, termina o se queda esperando. Abierta es un tablero: una pestaña por
sesión y, dentro, sus cuatro agentes, con los que trabajan al frente y sus
pasos a un clic. Un clic en la pestaña te lleva al pane de tmux de esa sesión,
y los permisos se pueden contestar ahí mismo con Permitir o Denegar.

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
- Sigue al monitor enfocado por el socket de eventos de Hyprland (fijada se
  queda en el suyo), y los ojos
  siguen al cursor con `cursorpos` del socket de pedidos (sin lanzar hyprctl).

| Hook de Claude Code | Evento | La mascota |
|---|---|---|
| `UserPromptSubmit` | `start` | se asoma trabajando ("Pensando…") |
| `PreToolUse` | `tool` | teclea y dice qué archivo o comando toca |
| `PostToolUse` | `tool-done` | baja la antena roja tras aprobar un permiso |
| `PostToolUseFailure` | `tool-fail` | si eran pruebas, dice cuáles fallaron |
| `PreCompact` | `compact` | sigue trabajando: "Compactando el contexto…" |
| `SubagentStart` | `agent-start` | apunta al subagente; si es de la familia, se vuelve él |
| `SubagentStop` | `agent-stop` | vuelve a la banca, y la mascota vuelve a ser el engineer |
| `PermissionRequest` | `ask` | antena roja con botones Permitir / Denegar |
| `Notification` · `permission_prompt` | `permission` | antena roja, isla abierta |
| `Notification` · `idle_prompt` | `idle` | confundida: lleva un rato esperándote |
| `Stop` | `stop` | saltito y "Listo en 3 min 12 s" |
| `StopFailure` | `failure` | confundida con el motivo |
| `SessionEnd` | `session-end` | olvida la sesión |

Con varias sesiones muestra la más urgente (permiso > esperando > terminó >
trabajando) y cuántas hay. Con el No molestar de swaync se duerme.

### El tablero

Al abrirla a mano (clic en la pastilla, `elyares-ctl open`, fijada o, en modo
normal, pasando el ratón) la isla es un tablero: **una pestaña por sesión** y,
de la elegida, **sus cuatro agentes**.

- **El frente:** los que trabajan, en grande, cada uno con su gesto, cuánto
  lleva y sus últimos pasos (el de ahora, resaltado). La tarjeta se tiñe con su
  color; en rojo si pide permiso, en verde si terminó y en amarillo si espera.
- **La banca:** los que están libres, en chiquito a la derecha. Cambian de
  sitio solos: el que empieza a trabajar sube al frente y el que termina vuelve.
- **El frente se parte** según cuántos trabajen: uno lo ocupa todo, dos lo
  comparten, tres van en columnas y con los cuatro son cuatro cuadros, sin
  banca. La isla mide lo mismo en todos los casos. Sin nadie trabajando, los
  cuatro salen en fila, apagados.
- **El desglose:** un clic en uno que trabaja abre todos sus pasos con lo que
  tardó cada uno (los últimos 8; arriba dice cuántos hubo antes). Los demás
  siguen a la vista en miniatura, y un clic en uno de ellos abre el suyo.
  "‹ volver" regresa al tablero e "ir al pane ›" lleva al pane de tmux.
- **Encargarle algo a uno de los tres:** un clic en el architect, el auditor
  o el reviewer, aunque esté libre, abre su desglose con un mini chat al pie.
  Escribes qué quieres que haga, Enter se lo manda y la isla vuelve al
  tablero, donde trabaja al lado de los demás: puedes poner a los tres a la
  vez mientras el engineer sigue con lo suyo. Más abajo, en [El chat](#el-chat).
- **Las pestañas** van por nombre, para que no cambien de sitio. Su punto es
  del color de quien trabaja ahí, rojo si pide permiso, amarillo si espera,
  verde si terminó y hueco en reposo. Un clic elige la sesión; un clic en la
  ya elegida lleva a su pane. La pestaña se va sola a la sesión que pide
  permiso o acaba de terminar.
- **El permiso** se contesta en la tarjeta del que lo pide: sale lo que quiere
  hacer, entero, con Permitir y Denegar. Solo se contesta el de la pestaña
  elegida, también con el teclado.
- **Debajo del tablero** van la vista previa de lo que edita la sesión elegida,
  las alertas (una fila cada una, hasta tres, con su ficha al abrirla) y las
  fuentes.

Quién está al frente sale de lo que cuenta Claude Code. Mientras la sesión
espera a un subagente de la familia que lanzó, el engineer está en la banca
("esperando"); si lo lanzó en segundo plano, trabajan los dos. Lo que hace un
subagente que no es de la familia (`Explore`, `general-purpose`…) cuenta como
trabajo del engineer. Los pasos de cada uno se recuerdan mientras dura su turno
(los últimos 40) y no se guardan entre reinicios.

Sin abrirla, la isla sigue como siempre: asomada con la mascota y, a su lado,
las caritas de los demás que trabajan (hasta cuatro); y cuando se abre sola
por un aviso, con la cabecera `agente | proyecto` y lo que pasa.

Las sesiones en reposo conservan su pestaña: son las que terminaron su turno
y están en el prompt. Sin ninguna sesión, la isla se abre con la cabecera
"Sin sesiones" y las fuentes. elyares-engineer solo conoce las sesiones que le
han mandado algún evento; al abrirla olvida las que tenían un pane de tmux
que ya no existe, o cuyo servidor de tmux ya no corre.

Dos pestañas con el mismo proyecto son dos sesiones de Claude Code distintas
en ese repo: la segunda lleva un "2". Una que corre en segundo plano (`/bg`, o
una conversación que se bifurcó a segundo plano) no tiene terminal: su pestaña
lleva el nombre que le puso Claude Code ("proyecto · nombre") o, si no tiene,
"2º plano". Para tener una a mano, Claude Code mantiene además una sesión de
repuesto que solo pinta su barra de estado: esa no sale ni se cuenta hasta que
hace algo. Una sesión se olvida cuando avisa de que termina, cuando su pane de
tmux ya no existe o, cada 15 s, cuando su proceso de Claude ya no existe (es
lo único que vale para las de segundo plano, que no tienen pane).

Las sesiones sobreviven al reinicio del servicio: se guardan en
`$XDG_RUNTIME_DIR/elyares-sessions.json` y al arrancar vuelven como estaban.
Un permiso pendiente vuelve sin botones (el hook que esperaba el clic se fue
con el servicio anterior) y se contesta en la terminal. Al apagar la máquina
el archivo se borra, igual que los panes de tmux.

El detalle se corta con "…" cuando la isla se abre sola por un aviso. Cuando
pide permiso lo muestra entero siempre, para ver el comando completo antes de
contestar. En el tablero, lo que no cabe en una tarjeta se lee en su desglose.

Un clic en la mascota la enoja; tres rápidos la marean.

### El chat

A Claude se le piden las cosas desde la isla, sin terminal: tmux se queda
para el editor, git y los comandos. `elyares-ctl chat` (o la pastilla
**Chat** del pie) abre el chat, listo para escribir; otra vez lo cierra, y la
conversación sigue ahí al volver a abrirlo.

**Se pide en el chat y se ve trabajar en el tablero.** Al mandar algo el chat
se cierra y la isla vuelve al tablero, en la pestaña de la conversación
(`proyecto · chat`), con el agente al frente y sus pasos. Si Claude pide
permiso se contesta en su tarjeta del tablero, como el de cualquier sesión.
Al terminar sale un aviso con el principio de la respuesta y el botón **Ver
respuesta**, que abre el chat para leerla entera.

- **Dónde trabaja:** en la carpeta del pane de tmux en el que estás al abrirlo
  (el del cliente de tmux que se usó al último). La cabecera la dice.
- **La caja:** crece con lo que escribes hasta seis líneas y luego hace
  scroll. Enter manda; Shift+Enter, otra línea. **Ctrl+V** pega texto y
  también imágenes: van en etiquetas encima de la caja (`imagen 1 ×`) y salen
  con el siguiente mensaje.
- **Comandos:** al escribir `/` salen tus skills y comandos (`/contexto`,
  `/bitacora`, `/commit`, `/pr`…) con su descripción; se eligen con las
  flechas y Tab o Enter. Los entiende Claude como en la terminal.
- **La conversación**, al estilo de OpenCode: lo tuyo en un bloque con una
  barra del color del agente; lo de Claude con su markdown (negritas,
  `código`, títulos, bloques de código y tablas alineadas); sus pasos en una
  línea tenue, y al acabar cada turno su pie: `▣ agente · modelo · tiempo`.
  La rueda del ratón la sube.
- **La línea de estado**, debajo de la caja: con quién hablas, el modelo, el
  esfuerzo y el modo plan, cada uno con su clic. El modelo y el plan cambian
  al momento; el esfuerzo, desde el siguiente turno (Claude solo lo toma al
  arrancar, así que la isla retoma la conversación con el nuevo).
  **Shift+Tab** prende o apaga el plan, como en la terminal. El modelo y el
  esfuerzo elegidos se guardan (`chat_model`, `chat_effort` en
  `settings.json`).
- **Un chat por agente:** un clic en el nombre del agente, en la línea de
  estado, elige con quién hablas: elyares-engineer o uno de la familia. Cada
  uno tiene su conversación; la de un agente corre como él (`claude -p
  --agent elyares-architect`), con su modelo, y en el tablero sale con su
  cara. También: `elyares-ctl chat architect` (o `auditor`, `reviewer`,
  `engineer`), **hablarle ›** en el desglose del engineer y **ver su chat ›**
  en el de cada uno de los tres.
- **El mini chat, para encargar sin abrir el panel:** en el tablero, un clic
  en uno de los tres (en su tarjeta, en la banca o en su carita de un
  desglose) abre su desglose con una caja al pie y el teclado listo. Enter
  se lo manda a su conversación y la isla vuelve al tablero; Shift+Enter es
  otra línea y Esc suelta el teclado. Trabaja en la carpeta de esa pestaña,
  y lo que hace no saca pestaña propia: se ve en su tarjeta de la pestaña
  desde la que se lo encargaste, al lado de los que ya trabajaban. Si pide
  permiso se contesta ahí mismo, y al terminar sale el aviso con **Ver
  respuesta**. La conversación de cada agente es una sola: si sigue ocupado
  en otro proyecto, su mini chat lo dice y no se le encarga nada hasta que
  acabe. Si la pestaña desde la que se lo encargaste se cierra, su sesión
  saca la suya. El engineer no tiene mini chat: a él se le habla en el chat.
- **Permisos:** el chat corre en bypass (`bypassPermissions`), así que casi
  nada pregunta. Lo que Claude sigue preguntando aun así (escribir en
  settings, git o la configuración de herramientas) se contesta en la
  tarjeta del tablero o, con el chat abierto, en la de encima de la caja.
- **Detener / Nuevo / Cerrar**, arriba a la derecha: cortar el turno (también
  Ctrl+C sin nada seleccionado), empezar otra conversación con el mismo
  agente en la carpeta del pane de ahora, y cerrar el panel.
- **El teclado:** mientras escribes, el chat lo toma entero. Esc lo suelta sin
  cerrar el chat y un clic en la caja lo vuelve a tomar; si pasan 90 s sin
  teclear, lo suelta solo.

Por debajo es `claude -p` con entrada y salida en `stream-json`: un proceso
por conversación, que la isla mantiene vivo turno tras turno y que le pasa
los permisos (`--permission-prompt-tool stdio`). Si el proceso se cierra, lo
siguiente que escribas lo vuelve a abrir con `--resume` (`elyares/chat.py`,
`elyares/chatview.py`).

### La familia

ElYares no trabaja solo. La sesión es el **engineer**, y hay tres subagentes de
Claude Code con su propio personaje: misma cara, mismas gafas y misma antena,
pero cada uno con su atuendo, lo que trae en las manos al trabajar y su color.

| Personaje | Subagente | Lleva | Al trabajar | Color |
|---|---|---|---|---|
| engineer | la sesión | gorra al revés | laptop | el acento del tema |
| architect | `elyares-architect` | casco de obra y lápiz en la oreja | un plano | cian |
| auditor | `elyares-auditor` | cachucha negra con `</>`, camisa y gafete | un clipboard con su checklist | morado |
| reviewer | `elyares-reviewer` | visera de editor y lápiz rojo | una lupa sobre el código | rosa |

Mientras trabaja un subagente de la familia, la mascota grande es ese
personaje, con todos sus gestos (la antena sigue en rojo al pedir permiso y en
verde al terminar); cuando termina, vuelve a ser el engineer. Con varios a la
vez manda el que arrancó al último.

Una sesión se nombra **agente | proyecto**: `elyares-engineer | tl-mas-server`.
El engineer está siempre; mientras trabaja un subagente de la familia, la
cabecera pasa a llevar su nombre (`elyares-auditor | tl-mas-server`), en su
color. Que una sesión pide permiso lo dicen la antena roja y la nota "pide
permiso" a la derecha.

En el tablero cada uno tiene su tarjeta (ver "El tablero").

La isla sabe cuál es cuál porque Claude Code manda `agent_id` y `agent_type`
en cada hook que se dispara dentro de un subagente. Los personajes están en
`elyares/mascot.py`, por capas (`HATS`, `BACK`, `FRONT`, `PROPS`, `ACCENTS`), y
qué subagente es cuál, en `AGENT_ROLES` de `elyares/state.py`. Un subagente que
se calla 20 min se da por terminado.

### Los agentes

Los tres subagentes están en `agents/` y `install.sh` los copia a
`~/.claude/agents/`, así que valen en cualquier proyecto. Son copias y no
enlaces: enlazados cambiarían solos con lo que hubiera en esta carpeta (otra
rama, un cambio a medias), y son instrucciones para todas las sesiones. Para
actualizarlos se vuelve a correr `install.sh`. Claude Code los lee al abrir una
sesión: una que ya estaba abierta no los ve hasta que se reinicia o se
recargan con `/agents`.

| Agente | Para qué | Herramientas | Reglas |
|---|---|---|---|
| `elyares-architect` | decidir, revisar o documentar una arquitectura; elige la que se acomoda al proyecto, no la que más se domina | lee, y escribe solo documentación | `E1`–`E7` y `T14` |
| `elyares-auditor` | seguridad de un diff, de un repo o de la configuración | solo lee | un núcleo de 28 reglas siempre, y los catálogos por demanda |
| `elyares-reviewer` | código limpio y mantenible: nombres, funciones, tests, textos de interfaz | solo lee | `C1`–`C11`, `T5`–`T13`, `P2`, `P4`, `P7`, `UX1`–`UX6` |

Se usan solo cuando se piden: por nombre ("usa elyares-auditor sobre este
diff") o con `@`. Su descripción le dice a la sesión que no los lance por
iniciativa propia. Los tres devuelven un informe con formato fijo, que siempre
dice qué no revisaron y qué quedó sin verificar.

Cada uno fija su modelo y su esfuerzo en su encabezado (`model`, `effort`): el
architect y el reviewer corren con Sonnet y el auditor con Opus, los tres en
`medium`. Sin esas líneas heredarían los de la sesión que los lanza.

- Las reglas `E`, `C`, `T`, `P` y `UX` son las de `docs/ESTANDARES-CORE.md`.
  Cada agente trae el enunciado, y si el proyecto tiene su propia copia o una
  regla propia, gana la del proyecto.
- Los catálogos del auditor son las 388 reglas de `rules/seguridad/` (su
  índice es `INDEX.md`), copiadas a `~/.claude/elyares/seguridad`. No van en
  `~/.claude/rules`: ahí Claude Code las cargaría enteras en cada sesión. El
  auditor nunca lee un catálogo entero: carga las áreas que toca el cambio.
- "Solo lee" quiere decir sin `Edit` ni `Write`. Con Bash todavía podrían
  escribir: lo impide su instrucción, no un candado.
- El auditor solo corre escáneres locales (`gitleaks`, `semgrep`,
  `osv-scanner`…) si ya están instalados; no instala nada, y los que mandan
  cargas de ataque (nuclei, ZAP, sqlmap) no los corre nunca.

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
suyas hay en la isla y qué hará el clic. Es un popover como los de macOS, con
la flecha hacia la pastilla, sombra y, en modo vidrio, fondo translúcido: sale
creciendo desde la flecha, se va encogiéndose y de una pastilla a la de al
lado se desliza. Sus textos van con los colores del tema de omarchy, avivados
para que no se pierdan sobre el vidrio, y cada cosa en el suyo: lo que hace
el clic, el título de cada bloque y, de un comando, el programa y lo que hay
que ponerle (`<tarea>`).

Arriba, junto al título, una etiqueta dice cómo está la fuente, en el color de
su punto. Debajo, lo que se sabe de ella en etiquetas (`parado`, `sin
alertas`; las alertas que tenga, en ámbar) y lo que trae ahora: sus cifras en
fichas, con el número en grande y su nombre debajo (`3 pomodoros hoy`), y lo
demás en frases con las cifras resaltadas y `en verde` / `en rojo` en su
color. Además:

- **GitHub:** cuántos PRs abiertos tienes y cómo van sus checks, cuántas
  revisiones te piden, qué cuentas respondieron y hace cuánto se consultó.
  Debajo, cada uno por su nombre (hasta cinco; de los demás dice cuántos): de
  qué proyecto es y su número, su título, de qué cuenta es y cómo van sus
  checks, en su color. Primero los tuyos y luego los que te piden revisar.
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
Después queda como una fila (punto rojo) debajo del tablero, hasta que el
problema se resuelve o pasan 10 min sin novedades. Un clic abre el panel de Observe y la descarta; descartada, no
vuelve a salir en 15 min. El contador "N sesiones" no cuenta las alertas.

Con el ratón encima, o abierta a mano, la alerta trae su ficha: el detalle y
sus botones. Un clic en su fila abre la ficha debajo del tablero.

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
| `elyares-ctl chat [quién]` | abre el chat con Claude, listo para escribir; otra vez lo cierra. Con `architect`, `auditor`, `reviewer` o `engineer`, el de ese agente |
| `elyares-ctl hide` | la esconde del todo (ni la ceja ni el hover); otra vez la muestra |
| `elyares-ctl compact` | prende o apaga el modo compacto, como el clic derecho |
| `elyares-ctl pin` | fija la isla abierta con todo a la vista; otra vez, la suelta. Como el clic central |
| `elyares-ctl tab` | pasa a la pestaña (la sesión) que sigue en el tablero |
| `elyares-ctl steps` | abre el desglose de uno de los cuatro; otra vez, el del que sigue, y al final vuelve al tablero |
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
bindd = SUPER ALT, I, Engineer: la pestaña que sigue, exec, elyares-ctl tab
bindd = SUPER ALT, O, Engineer: el desglose que sigue, exec, elyares-ctl steps
```

Fijada, la isla se queda abierta como cuando le pasas el ratón por encima (el
tablero, las alertas con su ficha y las fuentes), pero sin tener que dejar el
cursor ahí: no se cierra sola ni al irse el ratón,
ni en modo compacto. Arriba a la derecha dice "fijada". Se suelta con el mismo
atajo, con el clic central o con `elyares-ctl open`, y vuelve a asomarse y
esconderse como siempre. Fijada tampoco se cambia de monitor: se queda en el
que estaba al fijarla aunque enfoques otro, y solo se va si lo desconectas.
Suelta, vuelve al monitor enfocado. La preferencia (`pinned` y `pinned_monitor`
en `settings.json`) se guarda: tras reiniciar sigue fijada, en su monitor. Un permiso sigue mostrando sus botones, y
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
