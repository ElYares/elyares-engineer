# Avisa a la mascota ElYares cuando un comando largo de la terminal termina.
# install.sh lo carga desde ~/.bashrc; solo hace algo en shells interactivas.
#
# PS0 anota la hora al lanzar cada comando y PROMPT_COMMAND la compara cuando
# vuelve el prompt. Si pasaron ELYARES_CMD_SECS segundos (30 si no se dice
# otra cosa), manda el comando, lo que tardó y su código de salida.
#
# No avisa de programas en los que uno se queda a propósito (editores, ssh,
# tmux, claude...). Para sumar otros: ELYARES_CMD_SKIP="mi-tui otra-cosa".

[[ $- == *i* ]] || return 0
[[ " ${PROMPT_COMMAND[*]} " == *__ely_precmd* ]] && return 0

# La aritmética dentro de ${...} corre en esta shell, no en una subshell: es la
# única forma de que PS0 deje una variable puesta. __ely_x tiene que existir,
# aunque sea vacía: con una variable sin definir bash no evalúa la aritmética.
__ely_x=
__ely_mark='${__ely_x:0:$((__ely_t0=EPOCHSECONDS,0))}'

__ely_precmd() {
  local rc=$? t0=$__ely_t0
  __ely_t0=
  # oh-my-posh y otros prompts reescriben PS0: se vuelve a poner si falta.
  [[ $PS0 == *__ely_t0* ]] || PS0="$__ely_mark$PS0"
  [[ -n $t0 ]] || return "$rc"
  local secs=$((EPOCHSECONDS - t0))
  ((secs >= ${ELYARES_CMD_SECS:-30})) || return "$rc"

  local cmd
  cmd=$(HISTTIMEFORMAT='' builtin history 1)
  [[ $cmd =~ ^[[:space:]]*[0-9]+\*?[[:space:]]+(.*)$ ]] && cmd=${BASH_REMATCH[1]}
  local first=${cmd%% *}
  case " vim nvim vi nano hx emacs ssh mosh tmux claude less more man top htop btop \
watch tail fg lazygit lazydocker yazi psql mysql sqlite3 python python3 ipython node \
bash zsh sh ${ELYARES_CMD_SKIP:-} " in
    *" ${first##*/} "*) return "$rc" ;;
  esac

  command -v elyares-hook >/dev/null 2>&1 && command -v jq >/dev/null 2>&1 || return "$rc"
  # Una alerta por pane: el siguiente comando largo reemplaza a la anterior.
  (jq -nc --arg c "$cmd" --arg d "$PWD" --arg id "cmd:${TMUX_PANE:-$PWD}" \
      --argjson rc "$rc" --argjson s "$secs" \
      '{session_id: $id, cwd: $d, command: $c, exit_code: $rc, seconds: $s}' |
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
