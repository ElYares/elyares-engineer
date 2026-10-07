# elyares-engineer

Isla de Wayland (GTK4 + gtk4-layer-shell) que vigila a Claude Code y a sus
subagentes. El README explica el producto; aquí va lo que hay que saber para
trabajar en el repo.

## Comandos

- `make test` — pruebas (`unittest`, ~440). Corren con `/usr/bin/python3`.
- `elyares-ctl reload` — ver un cambio de código en la isla que corre.
- `elyares-ctl status` · `elyares-demo` — fuentes y eventos falsos, sin Claude.
- Servicio: `systemctl --user status elyares-engineer` · logs
  `journalctl --user -u elyares-engineer`.

## Reglas que se rompen fácil

- **`/usr/bin/python3`, no `python3`:** el de mise no trae `gi`, y sin él las
  pruebas de la isla se saltan.
- **Recargar, no reinstalar.** Tras cambiar código: `elyares-ctl reload` (espera
  a que los chats acaben su turno). `./install.sh` solo para lo que se copia
  fuera de la carpeta: `agents/` → `~/.claude/agents/`, `elyares/guard.py` →
  `~/.local/bin/elyares-guard`, `rules/seguridad/` → `~/.claude/elyares/seguridad/`.
  Y programado, para no cortar un chat: `systemd-run --user --on-active=45
  --unit=elyares-reinstall <carpeta>/install.sh`.
- **Un agente cambiado no lo ve una conversación abierta:** darle **Nuevo**.
- **Un error dentro de `draw` deja la isla entera en blanco:** mira el journal.
- **Los catálogos del auditor no van en `~/.claude/rules`** (pesan 390 KB y se
  cargarían en cada sesión).
- **El candado (`guard.py`) no es un sandbox:** `python -c` pasa. Modos:
  `solo-lectura`, `entrega` (solo devops), `solo-docs`, `config`.
- **Subagente es lo que trae `agent_id`;** `agent_type` sin él es una sesión
  entera. Todo lo que no es una sesión de Claude es una alerta.
- **El desenfoque es de Hyprland y por nombre de capa:** toda ventana de la isla
  se llama `elyares`; con otro nombre se ve nítida.
- **Los colores de aviso (verde, rojo, ámbar) no son del tema** y los de los
  personajes no pueden ser ninguno de esos tres. El texto de los flujos usa
  `wf_ink`, no `ink`.
- **`Artifact` no existe en el CLI `-p`:** los «artifacts» son documentos de
  `mcp__claude_ai_Claude_Docs__*`, y un agente los usa si están en su `tools:`.
- **Probar sin tocar la isla que corre:** proceso aparte con `Gtk.Application`
  de otro id, o dibujar a PNG con el fixture de `tests/test_island.py`. Nunca
  `typing=True` (le quita el teclado al usuario).
- **Dos chats sobre la misma carpeta se pisan:** cada uno en su `git worktree`.

## Flujo de git

- Rama `feat/…` desde `v2`, PR contra `v2`; a `main` (PR `v2` → `main`) cuando
  el usuario lo pida. Commit, PR y merge solo cuando se piden. No borrar
  carpetas, ramas ni preferencias.
- `gh` tiene otra cuenta activa: `GH_TOKEN=$(gh auth token --user ElYares) gh …`.
  Nunca `gh auth switch`. La base es `v2`, no `main`.
- Mensajes en español, Conventional Commits (`feat:`, `fix:`).

## Contexto del proyecto

Estado, decisiones e historia en el vault:
`~/develop/docs/obsidean-vault-personal/10 Projects/elyares-mascota/`
(el proyecto del vault conserva el nombre viejo). Cargar con `/contexto`;
`vaultdocs detect` no reconoce esta carpeta, usa
`vaultdocs detect --cwd ~/develop/personal/elyares-mascota`.
