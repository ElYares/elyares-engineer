# Avisa a la mascota ElYares cuando un comando largo de la terminal termina.
# install.sh lo carga desde ~/.bashrc; solo hace algo en shells interactivas.
#
# PS0 anota la hora al lanzar cada comando y PROMPT_COMMAND la compara cuando
# vuelve el prompt. Si pasaron ELYARES_CMD_SECS segundos (30 si no se dice
# otra cosa), manda el comando, lo que tardó y su código de salida. Dentro de
# tmux manda además las últimas líneas del pane, para la ficha de la alerta.
#
# No avisa de programas en los que uno se queda a propósito (editores, ssh,
# tmux, claude...). Para sumar otros: ELYARES_CMD_SKIP="mi-tui otra-cosa".
#
# Las pruebas van aparte. Si el comando corre pruebas (pytest, pest, vitest,
# go test, make test...) y la shell está dentro de tmux, PS0 le pide a tmux
# que copie a un archivo lo que imprima el pane y avisa de que empiezan: la
# mascota lee ese archivo y va mostrando cuáles pasan y cuáles fallan. Al
# volver el prompt se cierra la copia y se avisa del final, tarde lo que tarde.

[[ $- == *i* ]] || return 0
[[ " ${PROMPT_COMMAND[*]} " == *__ely_precmd* ]] && return 0

# La aritmética dentro de ${...} corre en esta shell, no en una subshell: es la
# única forma de que PS0 deje una variable puesta. __ely_x tiene que existir,
# aunque sea vacía: con una variable sin definir bash no evalúa la aritmética.
__ely_x=
__ely_mark='${__ely_x:0:$((__ely_t0=EPOCHSECONDS,0))}$(__ely_start)'

# Qué comandos corren pruebas. El mismo patrón está en elyares/testrun.py
# (TEST), que decide para las que corre Claude.
__ely_test_re='(^|[[:space:]/;&|(])(pytest|py\.test|phpunit|pest|vitest|jest|tox|(artisan|sail|go|cargo|deno|bun|mvn|composer|make|just|npm|pnpm|yarn)( +run)? +test[[:alnum:]_:.-]*|-m +unittest)($|[[:space:];&|)])'

__ely_is_test() { [[ $1 =~ $__ely_test_re ]]; }

# El comando que se acaba de lanzar, como lo guardó el historial.
__ely_last() {
  local cmd
  cmd=$(HISTTIMEFORMAT='' builtin history 1)
  [[ $cmd =~ ^[[:space:]]*[0-9]+\*?[[:space:]]+(.*)$ ]] && cmd=${BASH_REMATCH[1]}
  printf '%s' "$cmd"
}

# Corre desde PS0, justo antes del comando y en una subshell: no puede dejar
# variables. Lo que deja es el archivo de la copia, y por él sabe
# __ely_precmd que hay una copia que cerrar.
__ely_start() {
  [[ -n $TMUX_PANE ]] || return 0
  local run="${XDG_RUNTIME_DIR:-/run/user/$UID}" cmd
  cmd=$(__ely_last)
  __ely_is_test "$cmd" || return 0
  local log="$run/elyares-tests-${TMUX_PANE#%}.log"
  rm -f "$log"
  [[ -S $run/elyares.sock ]] && command -v elyares-hook >/dev/null 2>&1 &&
    command -v jq >/dev/null 2>&1 || return 0
  # Si el pane ya se está copiando a otro sitio (un plugin de registro), no
  # se toca: tmux solo lleva una copia por pane.
  [[ $(tmux display-message -p -t "$TMUX_PANE" '#{pane_pipe}' 2>/dev/null) == 0 ]] || return 0
  : > "$log"
  tmux pipe-pane -t "$TMUX_PANE" "cat >> '$log'" 2>/dev/null || { rm -f "$log"; return 0; }
  (jq -nc --arg c "$cmd" --arg d "$PWD" --arg id "cmd:$TMUX_PANE" --arg at "${EPOCHREALTIME/,/.}" \
      '{session_id: $id, cwd: $d, command: $c, at: $at}' |
    elyares-hook cmd-start &) >/dev/null 2>&1
}

__ely_precmd() {
  local rc=$? t0=$__ely_t0
  __ely_t0=
  # oh-my-posh y otros prompts reescriben PS0: se vuelve a poner si falta.
  [[ $PS0 == *__ely_t0* ]] || PS0="$__ely_mark$PS0"
  [[ -n $t0 ]] || return "$rc"
  local secs=$((EPOCHSECONDS - t0)) at="${EPOCHREALTIME/,/.}" cmd tests=
  cmd=$(__ely_last)
  # Unas pruebas que se estaban copiando: se cierra la copia y se avisa
  # siempre, sin mirar cuánto tardaron ni la lista de abajo.
  if [[ -n $TMUX_PANE ]] && __ely_is_test "$cmd" &&
      [[ -e ${XDG_RUNTIME_DIR:-/run/user/$UID}/elyares-tests-${TMUX_PANE#%}.log ]]; then
    tmux pipe-pane -t "$TMUX_PANE" 2>/dev/null
    tests=1
  fi
  if [[ -z $tests ]]; then
    ((secs >= ${ELYARES_CMD_SECS:-30})) || return "$rc"
    local first=${cmd%% *}
    case " vim nvim vi nano hx emacs ssh mosh tmux claude less more man top htop btop \
watch tail fg lazygit lazydocker yazi psql mysql sqlite3 python python3 ipython node \
bash zsh sh ${ELYARES_CMD_SKIP:-} " in
      *" ${first##*/} "*) return "$rc" ;;
    esac
  fi

  command -v elyares-hook >/dev/null 2>&1 && command -v jq >/dev/null 2>&1 || return "$rc"
  # Lo último que imprimió el comando. Se copia ya, antes de que el prompt se
  # dibuje encima; solo dentro de tmux, que es quien guarda lo que hay en el pane.
  local out=
  [[ -n $TMUX_PANE ]] && out=$(tmux capture-pane -p -J -t "$TMUX_PANE" 2>/dev/null |
    grep -v '^[[:space:]]*$' | tail -n 8)
  # Una alerta por pane: el siguiente comando largo reemplaza a la anterior.
  (jq -nc --arg c "$cmd" --arg d "$PWD" --arg id "cmd:${TMUX_PANE:-$PWD}" --arg o "$out" \
      --argjson rc "$rc" --argjson s "$secs" --arg at "$at" \
      '{session_id: $id, cwd: $d, command: $c, exit_code: $rc, seconds: $s, at: $at,
        output: ($o | split("\n") | map(select(length > 0)))}' |
    elyares-hook cmd-done &) >/dev/null 2>&1
  # El prompt (starship, oh-my-posh) lee $? después: tiene que seguir siendo el del comando.
  return "$rc"
}

if [[ $(declare -p PROMPT_COMMAND 2>/dev/null) == 'declare -a'* ]]; then
  PROMPT_COMMAND=(__ely_precmd "${PROMPT_COMMAND[@]}")
else
  PROMPT_COMMAND="__ely_precmd${PROMPT_COMMAND:+; $PROMPT_COMMAND}"
fi
PS0="$__ely_mark$PS0"
