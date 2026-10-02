# Quita los hooks de ElYares (si los hay) y los vuelve a poner.
# Con --arg remove true solo los quita (lo usa uninstall.sh).
def ours: (.hooks // []) | length > 0 and all((.command // "") | startswith($hook));
def entry($ev; $matcher):
  {hooks: [{type: "command", command: ($hook + " " + $ev), timeout: 2, async: true}]}
  + (if $matcher then {matcher: $matcher} else {} end);
# Síncrono para poder contestar; corre a la par del prompt de la terminal, así
# que esperar no bloquea a Claude. 600 = ASK_TIMEOUT en elyares/state.py.
def ask: {hooks: [{type: "command", command: ($hook + " ask"), timeout: 600}]};

.hooks //= {}
| .hooks |= with_entries(.value |= map(select(ours | not)))
| .hooks |= with_entries(select(.value | length > 0))
| if ($ARGS.named.remove // "") == "true" then . else
    .hooks.UserPromptSubmit += [entry("start"; null)]
  | .hooks.PreToolUse       += [entry("tool"; null)]
  | .hooks.PostToolUse      += [entry("tool-done"; null)]
  | .hooks.PostToolUseFailure += [entry("tool-fail"; null)]
  | .hooks.PermissionRequest += [ask]
  | .hooks.Notification     += [entry("permission"; "permission_prompt"), entry("idle"; "idle_prompt")]
  | .hooks.Stop             += [entry("stop"; null)]
  | .hooks.PreCompact       += [entry("compact"; null)]
  | .hooks.StopFailure      += [entry("failure"; null)]
  | .hooks.SessionEnd       += [entry("session-end"; null)]
  end
