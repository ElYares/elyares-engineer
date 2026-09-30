# Quita los hooks de ElYares (si los hay) y los vuelve a poner.
# Con --arg remove true solo los quita (lo usa uninstall.sh).
def ours: (.hooks // []) | length > 0 and all((.command // "") | startswith($hook));
def entry($ev; $matcher):
  {hooks: [{type: "command", command: ($hook + " " + $ev), timeout: 2, async: true}]}
  + (if $matcher then {matcher: $matcher} else {} end);

.hooks //= {}
| .hooks |= with_entries(.value |= map(select(ours | not)))
| .hooks |= with_entries(select(.value | length > 0))
| if ($ARGS.named.remove // "") == "true" then . else
    .hooks.UserPromptSubmit += [entry("start"; null)]
  | .hooks.PreToolUse       += [entry("tool"; null)]
  | .hooks.PostToolUse      += [entry("tool-done"; null)]
  | .hooks.Notification     += [entry("permission"; "permission_prompt"), entry("idle"; "idle_prompt")]
  | .hooks.Stop             += [entry("stop"; null)]
  | .hooks.StopFailure      += [entry("failure"; null)]
  | .hooks.SessionEnd       += [entry("session-end"; null)]
  end
