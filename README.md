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
  "‹ volver" regresa al tablero e "ir al pane ›" lleva al pane de tmux. Una
  sesión del chat no tiene pane: su enlace es "ir a su tmux ›", que lleva a la
  sesión de tmux de ese proyecto (y si no tiene, se la crea en su carpeta).
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

### Empezar en un proyecto

No hace falta abrir `claude` en una terminal para que la isla vea trabajo en
un proyecto: se empieza desde ella.

- **El panel de proyectos:** la pastilla **+** del pie (o `elyares-ctl
  projects`) abre tus proyectos de `~/develop`, agrupados por workspace como
  en el sidebar de tmux (Alt+b) y con sus mismas marcas: un rombo donde estás
  en tmux, un punto lleno si el proyecto tiene sesión de tmux abierta y uno
  hueco si está cerrado. A la derecha de cada uno, cómo va su Claude si tiene
  (`trabaja`, `permiso`, `listo`, `chat`). Por defecto salen los abiertos;
  **todos ›** enseña también los cerrados, como ctrl-t en el sidebar. Un clic
  en un proyecto abre su chat, listo para escribir.
- **Donde estás:** si en tmux estás en un proyecto que no tiene ningún Claude,
  la isla te lo ofrece. En el tablero, con una pestaña fantasma al final de
  las pestañas (`+ proyecto`); sin ninguna sesión, en la cabecera («Estás en
  proyecto · empezar ›»). Un clic empieza ahí.
- Sigue las reglas del sidebar: no salen los workspaces que empiezan por `_`
  o `.`, ni los de `~/.config/tmux/workspaces.ignore`, y las sesiones de tmux
  de fuera de `~/develop` van al final, en «otras». La isla vuelve a mirar
  tmux y la carpeta cada tres segundos.

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

- **Un chat por proyecto:** cada proyecto tiene su conversación con cada
  agente, y pasar a otro no tira la del anterior. La cabecera dice en cuál
  estás (`agente | proyecto` y su carpeta).
- **Cada pestaña manda sobre su chat:** una pestaña del tablero es un
  proyecto. Con el tablero a la vista, la pastilla **Chat** (y `elyares-ctl
  chat`) abre el chat de la pestaña elegida: su conversación o, si la sesión
  es de una terminal, la del chat de ese proyecto. Lo mismo un clic en la
  pestaña ya elegida de una sesión del chat, «hablarle ›» en su desglose y
  «Ver respuesta» en su aviso. Los encargos a los demás de la familia
  desde una pestaña van a las conversaciones de ese proyecto y de ningún otro.
- **El proyecto de una pestaña** es aquel en el que se empezó su conversación,
  y así se llama, aunque Claude acabe trabajando en otra carpeta.
- **Sin tablero, sigue a tmux:** si no hay ninguna sesión a la vista, el chat
  se abre en el proyecto de la sesión de tmux en la que estás (y si no tiene,
  una conversación vacía ahí); sin tmux, en la última que tuviste a la vista.
  No hace falta abrir `claude` en una terminal para que la isla vea trabajo
  en un proyecto.
- **Elegir proyecto:** al escribir `#` salen tus proyectos de `~/develop`,
  los abiertos en tmux primero (el usado más recientemente arriba) y luego
  los cerrados, con su marca, su workspace, su carpeta y si ya tienen
  conversación; se filtra al seguir escribiendo (`#tl-`) y Enter pasa a ese
  proyecto, con lo demás que llevabas escrito. Un clic en la carpeta de la cabecera (`▾`) hace
  lo mismo. Desde tmux, sin adivinar: `elyares-ctl chat --dir <carpeta>`.
- **Las que no se usan duermen:** una conversación que lleva diez minutos sin
  usarse suelta su proceso de Claude; lo siguiente que le escribas la retoma.
- **La caja:** crece con lo que escribes hasta seis líneas y luego hace
  scroll. Enter manda; Shift+Enter, otra línea. **Ctrl+V** pega texto y
  también imágenes: van en etiquetas encima de la caja (`imagen 1 ×`) y salen
  con el siguiente mensaje.
- **Comandos:** al escribir `/` salen tus skills y comandos (`/contexto`,
  `/bitacora`, `/commit`, `/pr`…) con su descripción; se eligen con las
  flechas y Tab o Enter. Los entiende Claude como en la terminal.
- **Agentes y archivos:** al escribir `@` salen los agentes
  (`@elyares-reviewer`) y los archivos del proyecto, los que ve git
  (`@elyares/chat.py`).
- **En cualquier parte del texto:** las dos listas salen para la palabra en la
  que está el cursor, con texto antes o después («sube los cambios con /co»).
  Lo elegido entra en su sitio y lo demás se queda como estaba.
- **La conversación**, al estilo de OpenCode: lo tuyo en un bloque con una
  barra del color del agente; lo de Claude con su markdown y su jerarquía:
  títulos en su color, **negritas** más claras que el texto, *cursivas*,
  enlaces subrayados, `código` en el acento del tema, viñetas y números en el
  color de quien habla (sangradas por nivel), citas con su barra, la raya
  `---` como una línea suave, un respiro antes de cada título, y bloques de
  código y tablas alineadas, y al acabar cada
  turno su pie: `▣ agente · modelo · tiempo`. La rueda del ratón la sube.
  **Solo la respuesta:** lo que hace por el camino (sus herramientas y lo que
  va diciendo antes de seguir) no sale en el chat; para eso está el tablero.
- **El contexto:** al final de la línea de estado dice cuánto lleva lleno el
  de la conversación (`contexto 12% · 118k`), con el color que le toca según
  se llena. El mismo % sale en el tablero, a la derecha de las pestañas, y en
  la cabecera de la isla. Lo cuenta el propio Claude al acabar cada turno.
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
  respuesta**. Cada agente tiene una conversación por proyecto: ocupado
  en uno, se le puede encargar otra cosa desde la pestaña de otro, y trabaja
  en los dos a la vez. Si la pestaña desde la que se lo encargaste se cierra,
  su sesión saca la suya. El engineer no tiene mini chat: a él se le habla en
  el chat.
- **Permisos:** el chat corre en bypass (`bypassPermissions`), así que casi
  nada pregunta. Lo que Claude sigue preguntando aun así (escribir en
  settings, git o la configuración de herramientas) se contesta en la
  tarjeta del tablero o, con el chat abierto, en la de encima de la caja.
- **Copiar una respuesta:** la conversación va dibujada, no se selecciona
  con el ratón. El pie de cada respuesta trae **copiar**, que la deja entera
  y con su markdown en el portapapeles (con `wl-copy`).
- **Pasársela al engineer:** en el chat de uno de la familia, el pie trae
  además **al engineer ›**: abre el chat del engineer en ese proyecto con la
  respuesta en la caja. No se manda sola; Enter la manda, tal cual o con lo
  que le añadas.
- **Detener / Nuevo / Cerrar**, arriba a la derecha: cortar el turno (también
  Ctrl+C sin nada seleccionado), empezar otra conversación con el mismo
  agente en este proyecto (las de los demás no se tocan), y cerrar el panel.
- **Otra:** con el mismo agente y en el mismo proyecto, abre una conversación
  nueva sin tocar la que ya trabaja: sirve para pedirle algo más sin esperar a
  que acabe. Con más de una, debajo de la cabecera sale la fila de las del
  agente (`● ` si trabaja, `! ` si espera respuesta; un clic pasa a ella y la ×
  cierra las que no trabajan; **Nuevo** en una la empieza de cero en su lugar).
  Hasta 5. Solo los que no modifican el repo (architect, auditor, reviewer,
  designer, researcher): el engineer, el mobile y el devops tienen una sola por
  proyecto, porque dos suyas sobre la misma carpeta se pisarían
  (`chat.SINGLE_AGENTS`). Los workflows siguen usando la de siempre.
- **El teclado:** mientras escribes, el chat lo toma entero. Esc lo suelta sin
  cerrar el chat y un clic en la caja lo vuelve a tomar; si pasan 90 s sin
  teclear, lo suelta solo.

**Ver un cambio sin reinstalar.** Las conversaciones se guardan (junto a las
sesiones, en `$XDG_RUNTIME_DIR/elyares-chats.json`) y vuelven al arrancar la
isla, con el panel abierto si lo estaba; lo siguiente que escribas las retoma.
Por eso `elyares-ctl reload` basta para ver un cambio del código: la isla se
vuelve a arrancar y el chat sigue donde iba. Si quien lo pide es el propio
Claude del chat, espera a que acabe su turno, para no cortarlo. Antes
comprueba que el código arranca: con un error, la isla que corre se queda.
`./install.sh` solo hace falta para lo que se copia fuera de la carpeta: los
agentes, los catálogos, los hooks nuevos y el servicio.

Por debajo es `claude -p` con entrada y salida en `stream-json`: un proceso
por conversación, que la isla mantiene vivo turno tras turno y que le pasa
los permisos (`--permission-prompt-tool stdio`). Si el proceso se cierra, lo
siguiente que escribas lo vuelve a abrir con `--resume` (`elyares/chat.py`,
`elyares/chatview.py`).

### Los workflows

Un workflow es una cadena ordenada de agentes de la familia, guardada con
nombre, que se lanza sobre un proyecto: «el designer propone, el engineer lo
construye, el reviewer lo revisa». `elyares-ctl workflows` (o la pastilla
**Flujos** del pie) abre su panel; otra vez lo cierra.

**Es otra isla, junto a la de siempre.** Sale pegada a la izquierda de la
isla, con su misma forma, su fondo y su modo vidrio, y la sigue mientras se
mueve (`elyares-ctl move`) o cambia de tamaño. La isla de siempre no se
toca: el tablero y el chat siguen a lo suyo. Si la isla está corrida tan a la
izquierda que no cabe, la de los flujos sale a su **derecha**; si no cabe en
ningún lado, donde haya más sitio, sin salirse de la pantalla.

**Se puede colapsar.** «colapsar ›» (o «‹ colapsar» si sale a la derecha) la
deja en una pastilla con `Flujos` y cómo va lo que corre (`paso 2/3`, `falló`,
`terminó`); un clic en ella la abre otra vez, y se acuerda
(`flows_collapsed` en `settings.json`). Un aviso con **Ver workflow** la abre
si estaba colapsada.

- **La lista:** tus workflows guardados, cada uno con **lanzar ›**,
  **editar** y **borrar** (que pregunta antes: no se puede deshacer).
- **El editor:** nombre, proyecto y los pasos. El proyecto, por defecto, es
  **cualquiera**: el workflow corre en el que estés al lanzarlo (el de tu
  sesión de tmux o, sin tmux, el del chat que tenías a la vista), y la lista
  dice cuál es ahora (`donde estés (ahora tl-mas-server)`). También se puede fijar a uno. Cada paso es un agente y lo que se le pide; se ordenan
  con ↑ ↓ y se quitan con ✕. Abajo, qué pasa **si un paso falla**: parar ahí
  o seguir con el siguiente. **Guardar** lo deja en la lista y **Guardar y
  lanzar** además lo corre; si no se puede todavía, encima de los botones
  dice por qué. **Cancelar** con cambios sin guardar pregunta antes.
- **Escribir:** un clic en un campo pone ahí una caja de texto y la isla de los
  flujos toma el teclado, como el chat. Tab y Enter pasan al campo que sigue,
  Shift+Tab al anterior y Esc lo suelta. El agente de un paso y el proyecto
  se eligen en un menú, como el de «con quién hablas».
- **La ejecución:** los mismos pasos con cómo va cada uno (✓ ● ✗) y lo que
  tardó. Si uno falla dice cuál y por qué, con **Reintentar paso N** y **ver
  su chat ›**; mientras corre, **Detener** corta el turno y no sigue.
- **Cómo corre:** cada paso se le manda al chat de ese agente en el proyecto,
  como si se lo escribieras tú, y cuando ese turno acaba sale el siguiente
  con lo que contestó el anterior. Por eso se ve trabajar en el tablero como
  cualquier otro, y cada paso tiene los permisos de ese chat, ni más ni
  menos: un paso del engineer puede cambiar código; los de los demás, solo
  lo que deja su candado. Un agente ocupado con otro turno no empieza, y
  cuenta como paso fallido.
- **Un paso puede decir que no salió.** La isla solo ve que el turno del
  agente acabó, no si hizo lo que se le pedía. Por eso a cada paso se le
  añade cómo avisar: si no pudo, o lo que había que comprobar no se cumple,
  acaba su respuesta con una línea `PASO FALLIDO: <motivo>`, y el paso
  cuenta como fallido con ese motivo. Así un paso «verifica que develop esté
  al día» para la cadena cuando no lo está.
- **Con el panel cerrado**, al acabar (o al pararse en un paso) sale un aviso
  con **Ver workflow**.
- **Modo vidrio:** la isla de los flujos lo sigue como la de siempre: fondo translúcido
  con su filo claro, un menú abierto translúcido como las burbujas de las
  fuentes y, debajo de cada texto, su sombra, para que se lea sobre lo que haya
  detrás.

Corre un workflow a la vez, con diez pasos como mucho, y una ejecución no
sobrevive a un reinicio de la isla: los pasos ya hechos quedan en sus chats,
pero la cadena no sigue sola. Se guardan en
`~/.config/elyares-engineer/workflows.json` (`elyares/workflows.py`,
`elyares/workflowview.py`).

### Moverla

Su sitio de siempre es el centro, debajo de Waybar, pero se puede correr a lo
ancho de la pantalla: `elyares-ctl move left` y `elyares-ctl move right` la
llevan al siguiente sitio de ese lado (hay cinco: los dos bordes, el centro y
los dos puntos medios), `elyares-ctl move center` la devuelve a su sitio y
`elyares-ctl move 80` la pone en ese punto exacto, de 0 (izquierda) a 100
(derecha). También flota: `elyares-ctl move up` y `move down` la suben y la
bajan (80 px por vez), `move reset` la devuelve arriba al centro, y
**arrastrando con el botón del medio** la llevas a donde quieras, a lo ancho y a
lo alto (un clic con él, sin mover, la fija). **Alt + arrastrar** también vale,
pero Wayland solo le dice a la isla que Alt está pulsado si ella tiene el
teclado (mientras escribes en el chat), así que no es de fiar. SUPER no sirve:
Hyprland lo usa para mover ventanas. El arrastre sigue al ratón en la pantalla
(`hypr.cursor_pos`), no al gesto de la ventana, que va atrasada y se pasaba de
largo. El sitio se guarda
(`position` y `position_y` en `settings.json`) y vale en cualquier monitor: al pasar a otro
queda en el mismo punto de su ancho. Los atajos de mover ventanas de Hyprland
no sirven aquí, porque la isla es una capa y no una ventana.

### La familia

ElYares no trabaja solo. La sesión es el **engineer**, y hay siete subagentes de
Claude Code con su propio personaje: misma cara, mismas gafas y misma antena,
pero cada uno con su atuendo, lo que trae en las manos al trabajar y su color.

| Personaje | Subagente | Lleva | Al trabajar | Color |
|---|---|---|---|---|
| engineer | la sesión | gorra al revés | laptop | el acento del tema |
| architect | `elyares-architect` | casco de obra y lápiz en la oreja | un plano | cian |
| auditor | `elyares-auditor` | cachucha negra con `</>`, camisa y gafete | un clipboard con su checklist | morado |
| reviewer | `elyares-reviewer` | visera de editor y lápiz rojo | una lupa sobre el código | rosa |
| designer | `elyares-designer` | boina ladeada, flequillo teñido de colores, pincel en la oreja y pintura en el cachete | una paleta y el pincel | magenta |
| mobile | `elyares-mobile` | gorro de lana caído, barba, bigote de manubrio y gafas de pasta | un teléfono y su café | café con leche |
| devops | `elyares-devops` | capucha negra con `</>`, chamarra negra con sus cordones y código reflejado en las gafas | una terminal negra con el prompt esperando | lima |
| researcher | `elyares-researcher` | sombrero de explorador con su brújula y pañoleta al cuello | un cuaderno donde apunta lo que encuentra | naranja |

Mientras trabaja un subagente de la familia, la mascota grande es ese
personaje, con todos sus gestos (la antena sigue en rojo al pedir permiso y en
verde al terminar); cuando termina, vuelve a ser el engineer. Con varios a la
vez manda el que arrancó al último.

Una sesión se nombra **agente | proyecto**: `elyares-engineer | tl-mas-server`.
El engineer está siempre; mientras trabaja un subagente de la familia, la
cabecera pasa a llevar su nombre (`elyares-auditor | tl-mas-server`), en su
color. Que una sesión pide permiso lo dicen la antena roja y la nota "pide
permiso" a la derecha.

En el tablero cada uno tiene su tarjeta (ver "El tablero"). Con casi todos
en la banca las caras se achican, y en una tarjeta estrecha el nombre es el
del personaje (`designer`) en vez del del agente (`elyares-designer`). Con
todos trabajando van en dos filas de cuatro, y libres también, porque los ocho
ya no caben en una fila con su nombre. Con más de cinco en la banca, las caras
van en cuadrícula y el pie dice el nombre del que tiene el cursor encima.

La isla sabe cuál es cuál porque Claude Code manda `agent_id` y `agent_type`
en cada hook que se dispara dentro de un subagente. Los personajes están en
`elyares/mascot.py`, por capas (`HATS`, `BACK`, `FRONT`, `PROPS`, `ACCENTS`), y
qué subagente es cuál, en `AGENT_ROLES` de `elyares/state.py`. Un subagente que
se calla 20 min se da por terminado.

### Los agentes

Los siete subagentes están en `agents/` y `install.sh` los copia a
`~/.claude/agents/`, así que valen en cualquier proyecto. Son copias y no
enlaces: enlazados cambiarían solos con lo que hubiera en esta carpeta (otra
rama, un cambio a medias), y son instrucciones para todas las sesiones. Para
actualizarlos se vuelve a correr `install.sh`. Claude Code los lee al abrir una
sesión: una que ya estaba abierta no los ve hasta que se reinicia o se
recargan con `/agents`.

| Agente | Para qué | Herramientas | Reglas |
|---|---|---|---|
| `elyares-architect` | decidir, revisar o documentar una arquitectura; elige la que se acomoda al proyecto, no la que más se domina | lee, y escribe solo documentación | `E1`–`E7` y `T14` |
| `elyares-auditor` | seguridad de un diff, de un repo o de la configuración | lee, y escribe solo documentación cuando se le pide | un núcleo de 28 reglas siempre, y los catálogos por demanda |
| `elyares-reviewer` | código limpio y mantenible: nombres, funciones, tests, textos de interfaz | lee, y escribe solo documentación cuando se le pide | `C1`–`C11`, `T5`–`T13`, `P2`, `P4`, `P7`, `UX1`–`UX6` |
| `elyares-designer` | la interfaz: proponer una pantalla antes de construirla, revisar una ya hecha o inventariar el sistema de diseño del repo | lee, y escribe solo documentación cuando se le pide | `UI1`–`UI17`, `UX1`–`UX6`, `A1`–`A12` |
| `elyares-mobile` | Flutter y React Native: revisar un diff, diagnosticar un build, un permiso o una notificación, comprobar que un release está listo | lee, y escribe solo documentación cuando se le pide | `M1`–`M27` |
| `elyares-devops` | la operación: revisar un diff, un repo entero o un despliegue antes de hacerlo (CI, contenedores, `Makefile` y scripts de despliegue, migraciones, respaldos, colas) | lee, no entra a ningún servidor y, cuando se le pide, entrega un cambio ya hecho (commit, push y PR) y escribe documentación | `D1`–`D25` |
| `elyares-researcher` | investigar: una duda básica, un tema complejo, un repositorio ajeno, una comparación o una evaluación contra lo que ya tienes; y, cuando se le pide, documentarlo en la bitácora del proyecto en el vault | lee, busca en la web y escribe solo documentación | `R1`–`R14` |

Se usan solo cuando se piden: por nombre ("usa elyares-auditor sobre este
diff") o con `@`. Su descripción le dice a la sesión que no los lance por
iniciativa propia. Los siete devuelven un informe con formato fijo, que siempre
dice qué no revisaron y qué quedó sin verificar.

Cada uno fija su modelo y su esfuerzo en su encabezado (`model`, `effort`): el
auditor corre con Opus y los otros seis con Sonnet, los siete en `medium`.
Sin esas líneas heredarían los de la sesión que los lanza.

El researcher es el único que cambia de modelo según el encargo, porque su
trabajo va de una duda de una línea a una investigación de una tarde. La
sesión que lo lanza puede pasarle otro modelo, y eso gana sobre su
encabezado: Haiku para una consulta puntual, Sonnet para lo normal y Opus
cuando pides investigar a fondo o de la respuesta depende una decisión.
También puedes decirlo tú: "usa elyares-researcher con opus".

- Las reglas `E`, `C`, `T`, `P` y `UX` son las de `docs/ESTANDARES-CORE.md`.
  Cada agente trae el enunciado, y si el proyecto tiene su propia copia o una
  regla propia, gana la del proyecto.
- Las reglas `UI`, `A` y `M` no están en el estándar: solo existen en el
  designer y en el mobile. Cada una sale de algo que ya estaba escrito y sin
  número (los cuatro estados y los tokens de `07-frontend.md` de los starters,
  las skills de `ri-chip-delivery`, los `CLAUDE.md` de las apps, decisiones y
  bitácoras del vault). `A8`–`A12` y `M24`–`M27` son la excepción: vienen de
  [ECC](https://github.com/affaan-m/ECC) (su lista de WCAG 2.2, su revisor de
  Flutter y sus reglas de release de Expo), no de un incidente propio. Ninguna
  se ha corrido todavía contra un repo: la primera pasada dirá cuáles dan ruido.
- Las reglas `D` tampoco están en el estándar. Salen de incidentes propios:
  despliegues que quedaron a medias, un respaldo vacío que nadie notó, un
  worker ajeno reiniciado en un servidor compartido, pruebas en verde que no
  corrieron, una suite que borró la base de desarrollo. Están en las bitácoras
  y los runbooks de cada proyecto.
- Las reglas `R` salen de la Parte B del estándar (`G2`: no inventar;
  `G23`: no afirmar lo que no se verificó).
- El researcher documenta en el vault de Obsidian con el procedimiento de
  `/bitacora`: una entrada `learning` en la bitácora del mes del proyecto y,
  si la investigación es larga, una nota de referencia en la carpeta del
  proyecto a la que la entrada enlaza. No reescribe el Estado ni crea
  decisiones: eso sigue siendo de la sesión principal, que conoce el resto
  del trabajo. Sin proyecto no escribe: devuelve la investigación y lo dice.
- Los catálogos del auditor son las 388 reglas de `rules/seguridad/` (su
  índice es `INDEX.md`), copiadas a `~/.claude/elyares/seguridad`. No van en
  `~/.claude/rules`: ahí Claude Code las cargaría enteras en cada sesión. El
  auditor nunca lee un catálogo entero: carga las áreas que toca el cambio.
- Ninguno cambia código: su Bash va vigilado por un candado y su `Write`
  solo deja escribir documentación (ver abajo).
- Los cinco que revisan (auditor, reviewer, designer, mobile y devops)
  documentan cuando se les pide («documéntalo», «déjaselo al engineer»): un
  trabajo por hacer va al backlog del proyecto en el vault con el
  procedimiento de `/todo` (pasos 1 a 4; el Estado y el pomodoro siguen
  siendo de la sesión principal) y, sin proyecto en el vault, a un `.md` en
  `/tmp` cuya ruta dicen en su informe.
- El auditor solo corre escáneres locales (`gitleaks`, `semgrep`,
  `osv-scanner`…) si ya están instalados; no instala nada, y los que mandan
  cargas de ataque (nuclei, ZAP, sqlmap) no los corre nunca.

### El candado

`elyares-guard` es un hook `PreToolUse` (el código está en `elyares/guard.py`,
e `install.sh` lo copia a `~/.local/bin/elyares-guard`). Tiene cuatro modos:

| Modo | Dónde corre | Qué hace |
|---|---|---|
| `solo-lectura` | el Bash de los agentes (menos el devops), desde su encabezado | frena el comando que escribe: redirecciones fuera de `/tmp`, `rm`, `mv`, `sed -i`, cualquier `git` que no sea de lectura, instaladores (`npm install`, `composer install`, `flutter pub get`…), formateadores que reescriben, `--fix`, migraciones, `sudo`. Y el que sale de la máquina o toca lo desplegado: `ssh` y `scp`, un `make` que no sea de pruebas (sí deja `make -n`), un `gh` que no sea de consulta, y `kubectl`, `terraform`, `supervisorctl`, `crontab` o `certbot` cuando cambian algo. `git clone` solo pasa hacia `/tmp` |
| `entrega` | el Bash del devops, en vez de `solo-lectura` | lo mismo, y además deja entregar un cambio: `git add` por ruta, `git commit`, `git push`, una rama nueva, `git fetch`, `gh pr create` o `edit` y `gh auth token`, para usar en un solo comando la cuenta que ve el repositorio (`GH_TOKEN=$(gh auth token --user X) gh …`) sin cambiar la de la máquina. Sigue frenando `add -A`, `--amend`, `--no-verify`, el push forzado o que borra ramas, `merge`, `rebase`, `reset` y mergear o cerrar un PR |
| `solo-docs` | el `Edit` y el `Write` del architect y del researcher, y el `Write` de los otros cinco | solo deja escribir documentación (`.md`, `.mmd`, `.puml`, `.txt`…) |
| `config` | el `Edit` y el `Write` de cualquier sesión, desde `settings.json` | pregunta antes de tocar la configuración, ya existente, de lo que revisa el código: ESLint, Prettier, PHPStan y su baseline, Pint, PHPUnit, `analysis_options.yaml`, golangci, ruff, los workflows de GitHub |

Los tres primeros bloquean y le dicen al agente por qué; el cuarto no bloquea,
pregunta: relajar un linter para que algo pase es lo que el estándar prohíbe,
pero a veces el cambio es intencional y lo decide la persona.

- **Frena lo evidente, no es un sandbox.** Un `python -c`, un script propio o
  una herramienta que escribe sin decirlo pasan sin que los vea. Sirve contra
  el descuido (un formateador que reescribe, un `git checkout` de más), no
  contra un agente empeñado en saltárselo.
- **Si no está instalado, no frena nada.** Un hook que Claude Code no
  encuentra no bloquea: la llamada sigue. Por eso se instala como copia y no
  como enlace a esta carpeta.
- Escribir en `/tmp` sí se permite: ahí dejan los agentes los informes de sus
  herramientas. Una ruta que sale de `/tmp` con `..` no cuenta.
- Dos excepciones, para que el researcher pueda escribir la bitácora:
  `vaultdocs project <nombre> --write`, que crea el esqueleto del proyecto en
  el vault sin pisar nada, y el `sed -i` que inserta una entrada bajo el
  marcador `BITACORA:INSERT` de una bitácora de mes, con las dos rutas
  literales. Cualquier otro `sed -i` se frena.
- Las dos ideas vienen de [ECC](https://github.com/affaan-m/ECC) (`gateguard`
  y `config-protection`); el código es propio. Sus casos están en
  `tests/test_guard.py`.

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

La regla es por el nombre entero de la capa, así que la isla de los flujos usa el
mismo (`elyares`) y se desenfoca igual; con otro nombre se vería nítida.

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
| `elyares-ctl chat [quién] [--dir carpeta]` | abre el chat con Claude, listo para escribir; otra vez lo cierra. Con `architect`, `auditor`, `reviewer` o `engineer`, el de ese agente. Con `--dir`, en el proyecto de esa carpeta |
| `elyares-ctl projects` | abre el panel de proyectos, para empezar a trabajar en uno; otra vez lo cierra |
| `elyares-ctl workflows` | abre el panel de workflows: cadenas de agentes que se guardan y se lanzan sobre un proyecto; otra vez lo cierra |
| `elyares-ctl move <dónde>` | corre la isla a lo ancho de la pantalla: `left` y `right`, al siguiente sitio de ese lado; `center`, a su sitio de siempre; `up` y `down`, la suben y la bajan; `reset`, arriba al centro; o un número del 0 (izquierda) al 100 (derecha) |
| `elyares-ctl hide` | la esconde del todo (ni la ceja ni el hover); otra vez la muestra |
| `elyares-ctl compact` | prende o apaga el modo compacto, como el clic derecho |
| `elyares-ctl pin` | fija la isla abierta con todo a la vista; otra vez, la suelta. Como el clic central |
| `elyares-ctl tab` | pasa a la pestaña (la sesión) que sigue en el tablero |
| `elyares-ctl steps` | abre el desglose de uno de los cuatro; otra vez, el del que sigue, y al final vuelve al tablero |
| `elyares-ctl theme` | vuelve a leer el color de acento del tema (lo llama el hook de omarchy) |
| `elyares-ctl reload` | vuelve a arrancar la isla con el código de su carpeta, sin perder las sesiones ni los chats; con un turno en curso en algún chat, al acabar. Si el código no arranca, no lo hace y dice por qué |
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
bindd = SUPER ALT, H, Engineer: correr a la izquierda, exec, elyares-ctl move left
bindd = SUPER ALT, L, Engineer: correr a la derecha, exec, elyares-ctl move right
bindd = SUPER ALT, period, Engineer: volver al centro, exec, elyares-ctl move center
bindd = SUPER ALT, K, Engineer: subir, exec, elyares-ctl move up
bindd = SUPER ALT, J, Engineer: bajar, exec, elyares-ctl move down
bindd = SUPER ALT, comma, Engineer: volver arriba al centro, exec, elyares-ctl move reset
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
  En el chat de la isla, `AskUserQuestion` sí se contesta: el chat se abre en la
  pregunta con una fila por opción (un clic la elige; si admite varias, se marcan
  y **Listo** las manda; con varias preguntas van una a una). Lo que escribas en
  la caja y Enter es «otra respuesta», y **Omitir** la deniega.

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
