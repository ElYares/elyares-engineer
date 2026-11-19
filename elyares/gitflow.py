"""El flujo de ramas de un repositorio: de dónde nace la rama de ahora y a dónde sube.

Cada repo declara su cadena con una línea en su `CLAUDE.md`:

    Flujo de git: main ← develop ← v2 ← v2-<tema>

De izquierda a derecha, de la más estable a la que se trabaja; `v2-<tema>` es un patrón (todas las
ramas que empiezan con `v2-`). La rama de ahora tiene un **padre** (a donde sube con un PR) y un
**abuelo** (a donde sube el padre cuando está listo). Una rama de la cadena que no existe se pregunta
una vez («¿a qué rama va en vez de `develop`?») y la respuesta queda en `gitflow.json`.

Este módulo no dibuja nada: lee `git`/`gh` y corre las órdenes del flujo (subir, PR, merge). Nunca
fuerza un push, nunca borra una rama y nunca cambia de rama a quien está trabajando salvo con
`create_branch`, que pide el usuario.
"""

import json
import os
import re
import subprocess
from collections import namedtuple

from . import github, settings

ARROWS = re.compile(r'\s*(?:←|<-)\s*')
LINE = re.compile(r'flujo de git\W*:\s*(.+)$', re.I)
SIGNATURE = '🤖 Generated with [Claude Code](https://claude.com/claude-code)'

# La rama de ahora y dónde está en la cadena. `ask`: una rama de la cadena que no existe y todavía
# no se sabe a cuál sustituye; `options`: las que sí existen, para elegir. `declared`: la cadena
# salió del CLAUDE.md del repo (si no, es la de siempre: la rama principal y la de ahora).
Flow = namedtuple('Flow', 'root branch chain parent grand ask options declared', defaults=(None,) * 8)
# Un paso del flujo: `key` (lo que se manda a `act`), `label`, `state` ('done', 'todo', 'wait', 'na'),
# `note` (lo que lo explica) y `go` (el texto del botón, o '' si no hay botón).
Step = namedtuple('Step', 'key label state note go', defaults=('', 'todo', '', ''))


def _git(root, *args, timeout=15):
    """La salida de `git -C root …`, o None si falla."""
    try:
        out = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', root, *args], capture_output=True,
                             text=True, timeout=timeout, env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def _ok(root, *args, timeout=60):
    """(ok, texto): lo que dijo `git`, para mostrarlo si falló."""
    try:
        out = subprocess.run(['git', '-C', root, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as err:
        return False, str(err)
    return out.returncode == 0, (out.stderr or out.stdout).strip()


def parse_chain(text):
    """«main ← develop ← v2 ← v2-<tema>» -> ['main', 'develop', 'v2', 'v2-<tema>'], o [] si no hay flecha."""
    text = re.split(r'\s{2,}|\s\(', text.strip())[0]            # una nota al final («  (lo lee…)») no es una rama
    parts = [p.strip(' `*_') for p in ARROWS.split(text)]
    return [p for p in parts if p] if len(parts) >= 2 else []


def declared_chain(root):
    """La cadena que declara el CLAUDE.md del repo, o []."""
    try:
        with open(os.path.join(root, 'CLAUDE.md'), encoding='utf-8') as f:
            for line in f:
                found = LINE.search(line)
                if found and parse_chain(found.group(1)):
                    return parse_chain(found.group(1))
    except OSError:
        pass
    return []


def prefix_of(name):
    """«v2-<tema>» -> 'v2-' (todas las ramas que empiezan así); un nombre sin patrón -> None."""
    return name.split('<')[0] if '<' in name else None


def current_branch(root):
    return (_git(root, 'rev-parse', '--abbrev-ref', 'HEAD') or '').strip()


def exists(root, name):
    """¿La rama existe aquí o en origin?"""
    return any(_git(root, 'rev-parse', '--verify', '--quiet', ref) is not None
               for ref in (f'refs/heads/{name}', f'refs/remotes/origin/{name}'))


def config_path():
    """Donde se guardan las respuestas a «¿a qué rama va?», junto a los ajustes."""
    return os.path.join(os.path.dirname(settings.path()), 'gitflow.json')


def load_config():
    try:
        with open(config_path(), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def remember(root, missing, target):
    """Guarda que, en este repo, la rama que no existe (`develop`) se sustituye por otra (`main`)."""
    data = load_config()
    data.setdefault(os.path.realpath(root), {})[missing] = target
    os.makedirs(os.path.dirname(config_path()), exist_ok=True)
    with open(config_path(), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _ahead(root, base, head):
    """Cuántos commits tiene `head` que no tiene `base`; None si alguno no existe."""
    out = _git(root, 'rev-list', '--count', f'{base}..{head}')
    return int(out) if out and out.strip().isdigit() else None


def _tip(root, name):
    """La referencia de una rama: la de origin si existe (es lo que dicen los demás; la local puede ir
    atrasada), si no la local."""
    remote = f'refs/remotes/origin/{name}'
    return remote if _git(root, 'rev-parse', '--verify', '--quiet', remote) is not None else f'refs/heads/{name}'


def resolve(root, chain=None, branch=None, config=None):
    """Dónde está la rama de ahora en la cadena del repo: su padre, su abuelo y, si falta una rama de la
    cadena sin sustituto, cuál (`ask`)."""
    branch = branch or current_branch(root)
    declared = chain if chain is not None else declared_chain(root)
    if not declared:
        main = (_git(root, 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD') or 'origin/main').strip()
        declared = [main.removeprefix('origin/')]
    subst = (config if config is not None else load_config()).get(os.path.realpath(root), {})
    names = [n for n in declared if prefix_of(n) is None]
    # Dónde cuelga la rama de ahora: en su patrón, en su lugar de la cadena, o bajo la rama más cercana.
    patterns = [(i, prefix_of(n)) for i, n in enumerate(declared) if prefix_of(n) is not None]
    spot = next((i for i, pre in patterns if pre and branch.startswith(pre)), None)
    if spot is None and branch in declared:
        spot = declared.index(branch)
    if spot is None:
        real = [n for n in names if exists(root, n)]
        scored = [(a, -declared.index(n), n) for n in real if (a := _ahead(root, _tip(root, n), 'HEAD')) is not None]
        near = min(scored)[2] if scored else (real[-1] if real else None)
        spot = declared.index(near) + 1 if near else len(declared)
    ancestors, ask = [], None
    for name in reversed(declared[:spot]):
        if prefix_of(name) is not None or name == branch:
            continue
        if exists(root, name):
            ancestors.append(name)
        elif subst.get(name) and exists(root, subst[name]):
            if subst[name] not in ancestors:
                ancestors.append(subst[name])
        elif ask is None:
            ask = name
    options = [n for n in ancestors]
    return Flow(root, branch, declared, ancestors[0] if ancestors else None,
                ancestors[1] if len(ancestors) > 1 else None, ask, options, bool(chain or declared_chain(root)))


def changed(root):
    """Cuántos archivos tiene el árbol de trabajo sin commitear."""
    out = _git(root, 'status', '--porcelain')
    return len([line for line in (out or '').splitlines() if line.strip()])


def _slug(root):
    """«dueño/repo» del remoto origin, o ''."""
    url = (_git(root, 'remote', 'get-url', 'origin') or '').strip()
    found = re.search(r'[:/]([^/:\s]+/[^/\s]+?)(?:\.git)?/?$', url)       # también con un alias de ssh (`github-personal:dueño/repo`)
    return found.group(1) if found else ''


def account(root):
    """La cuenta de `gh` que es dueña del repo, o la primera con sesión."""
    owner = _slug(root).split('/')[0]
    have = github.accounts()
    return owner if owner in have else (have[0] if have else '')


def find_pr(root, acct, head, base):
    """El PR más reciente de `head` hacia `base`: {number, state, url} o None."""
    out = github._gh(acct, 'pr', 'list', '--repo', _slug(root), '--head', head, '--base', base, '--state', 'all',
                     '--limit', '1', '--json', 'number,state,url')
    try:
        found = json.loads(out or '[]')
    except ValueError:
        return None
    return found[0] if found else None


def status(root, flow):
    """Los pasos del flujo de la rama de ahora, con lo que ya está hecho. Habla con `git` y con `gh`."""
    parent, grand, branch = flow.parent, flow.grand, flow.branch
    acct = account(root)
    steps = []
    dirty = changed(root)
    steps.append(Step('commit', 'Commit', 'todo' if dirty else 'done',
                      f'{dirty} archivo{"s" * (dirty != 1)} sin commitear' if dirty else 'todo commiteado',
                      'Sugerir mensaje' if dirty else ''))
    upstream = (_git(root, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}') or '').strip()
    pending = _ahead(root, '@{u}', 'HEAD') if upstream else None
    pushed = bool(upstream) and pending == 0
    steps.append(Step('push', f'Subir {branch}', 'done' if pushed else 'todo',
                      'en origin' if pushed else f'{pending} commit{"s" * (pending != 1)} sin subir' if upstream else 'sin subir',
                      '' if pushed else 'Subir'))
    if not parent:
        return steps + [Step('', 'Sin rama padre', 'na', 'ver la pregunta de arriba')]
    ahead_up = _ahead(root, _tip(root, parent), 'HEAD')
    pr = find_pr(root, acct, branch, parent) if acct and pushed else None
    if pr and pr['state'] == 'MERGED' and ahead_up:
        pr = None                       # un PR viejo ya mergeado: lo que se hizo después necesita otro
    merged = bool(pr) and pr['state'] == 'MERGED'
    steps.append(Step('pr', f'PR a {parent}', 'done' if pr else 'todo' if pushed else 'wait',
                      f'#{pr["number"]} {pr["state"].lower()}' if pr else '' if pushed else 'primero sube la rama',
                      '' if pr else 'Abrir PR' if pushed else ''))
    steps.append(Step('merge', f'Merge en {parent}', 'done' if merged else 'todo' if pr else 'wait',
                      'mergeado' if merged else '' if pr else 'primero el PR', 'Mergear' if pr and not merged else ''))
    if grand:
        ahead = _ahead(root, _tip(root, grand), _tip(root, parent))
        gpr = find_pr(root, acct, parent, grand) if acct and ahead else None
        if gpr and gpr['state'] == 'MERGED':
            gpr = None                  # un PR viejo ya mergeado: el padre tiene commits nuevos y necesita otro
        gdone = bool(gpr) and gpr['state'] == 'MERGED'
        steps.append(Step('gpr', f'PR {parent} → {grand}', 'done' if gpr else 'todo' if ahead else 'na',
                          f'#{gpr["number"]} {gpr["state"].lower()}' if gpr else f'{ahead} commits por subir' if ahead else 'al día',
                          '' if gpr or not ahead else 'Abrir PR'))
        steps.append(Step('gmerge', f'Merge en {grand}', 'done' if gdone else 'todo' if gpr else 'wait' if ahead else 'na',
                          'mergeado' if gdone else '' if gpr else 'primero el PR' if ahead else 'al día',
                          'Mergear' if gpr and not gdone else ''))
    return steps


def _title_and_body(root, base, head):
    """Título y cuerpo de un PR sacados de sus commits: el asunto del primero (o de uno solo) y la lista."""
    log = (_git(root, 'log', '--reverse', '--format=%s', f'{_tip(root, base)}..{_tip(root, head)}') or '').splitlines()
    # Con un solo commit, su asunto; con varios, ninguno resume a los demás: la rama y cuántos trae.
    title = log[0] if len(log) == 1 else f'{head} → {base}' + (f' ({len(log)} commits)' if log else '')
    body = ('## Cambios\n\n' + '\n'.join(f'- {s}' for s in log) + '\n\n' if log else '') + SIGNATURE
    return title[:120], body


def act(root, flow, key):
    """Corre un paso del flujo y devuelve (ok, lo que dijo). Bloquea: va en un hilo."""
    branch, parent, grand = flow.branch, flow.parent, flow.grand
    acct = account(root)
    if key == 'push':
        return _ok(root, 'push', '-u', 'origin', branch)
    if not acct:
        return False, 'gh no tiene ninguna sesión iniciada'
    head, base = (branch, parent) if key in ('pr', 'merge') else (parent, grand)
    if not (head and base):
        return False, 'falta la rama de origen o de destino'
    if key in ('pr', 'gpr'):
        title, body = _title_and_body(root, base, head)
        out = github._gh(acct, 'pr', 'create', '--repo', _slug(root), '--base', base, '--head', head, '--title', title, '--body', body)
        return (True, (out or '').strip()) if out else (False, 'gh no pudo abrir el PR (¿ya existe, o sin cambios?)')
    if key in ('merge', 'gmerge'):
        pr = find_pr(root, acct, head, base)
        if not pr or pr['state'] != 'OPEN':
            return False, 'no hay un PR abierto para mergear'
        out = github._gh(acct, 'pr', 'merge', str(pr['number']), '--repo', _slug(root), '--merge')
        if out is None:
            return False, f'gh no pudo mergear el PR #{pr["number"]} (revisa el CI)'
        _ok(root, 'fetch', 'origin', timeout=60)          # solo trae lo nuevo; no cambia de rama ni toca el árbol
        # Y deja al día la rama de destino local si se puede sin tocar nada (solo avance rápido; si está
        # abierta en otra carpeta o no avanza limpio, git se niega y se deja como estaba).
        _ok(root, 'fetch', 'origin', f'{base}:{base}', timeout=60)
        return True, f'PR #{pr["number"]} mergeado'
    return False, f'paso desconocido: {key}'


def create_branch(root, name, parent):
    """Crea `name` desde `parent` y se cambia a ella (lleva consigo lo que haya sin commitear)."""
    if not re.fullmatch(r'[\w./-]+', name or ''):
        return False, 'nombre de rama no válido'
    return _ok(root, 'switch', '-c', name, _tip(root, parent).removeprefix('refs/heads/').removeprefix('refs/remotes/'), '--no-track')


def toplevel(path):
    """La carpeta raíz del repositorio que contiene `path`, o ''."""
    return (_git(path, 'rev-parse', '--show-toplevel') or '').strip() if path and os.path.isdir(path) else ''
