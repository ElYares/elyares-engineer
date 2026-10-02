"""Avisa del CI de tus pull requests y de las revisiones que te piden.

Cada POLL_SECS le pregunta a GitHub con `gh`, una consulta por cuenta, y
compara con la vez anterior:

    checks   los de un PR tuyo pasaron a verde o a rojo
    revisión te pidieron revisar un PR

La primera consulta solo toma la foto. `gh` puede tener varias cuentas: se
consultan todas, o las que diga la preferencia `github_accounts`.

Un PR con los checks en rojo lleva su ficha: qué check falló, el final de su
log si es de GitHub Actions, y los botones Reintentar (`gh run rerun --failed`)
y Abrir PR. Eso se pregunta aparte y solo cuando un PR se pone en rojo.

Tras cada consulta le cuenta a la isla, para la burbuja de su pastilla, cómo
están las cosas ahora: cuántos PRs abiertos hay y sus checks, cuántas
revisiones pendientes y qué cuentas respondieron.
El token de cada una se le pide a `gh` y nunca se guarda ni se muestra.
"""

import json
import os
import re
import shutil
import subprocess
import threading
import time

POLL_SECS = 120
GREEN = ('SUCCESS',)
RED = ('FAILURE', 'ERROR')
RUNNING = ('PENDING', 'EXPECTED')
# Con estas conclusiones un check cuenta como caído. Uno cancelado o saltado no.
FAILED = ('FAILURE', 'ERROR', 'TIMED_OUT', 'STARTUP_FAILURE')
LOG_LINES = 8             # líneas de log que van en la ficha de un PR en rojo

QUERY = '''
{
  viewer {
    pullRequests(states: OPEN, first: 30, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        number title url
        repository { nameWithOwner }
        commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
      }
    }
  }
  search(query: "is:open is:pr review-requested:@me archived:false", type: ISSUE, first: 20) {
    nodes { ... on PullRequest { number title url repository { nameWithOwner } } }
  }
}
'''


CHECKS_QUERY = '''
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      commits(last: 1) { nodes { commit { statusCheckRollup { contexts(first: 50) { nodes {
        __typename
        ... on CheckRun { name conclusion checkSuite { workflowRun { databaseId } } }
        ... on StatusContext { context state }
      } } } } } }
    }
  }
}
'''

# `gh run view --log-failed` da "job<TAB>paso<TAB>fecha mensaje" por línea.
_STAMP = re.compile(r'^\ufeff?\d{4}-\d\d-\d\dT[\d:.]+Z ?')
_MARK = re.compile(r'^##\[(\w+)\]')


def _run(cmd, env=None, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def accounts():
    """Las cuentas de github.com con sesión iniciada en `gh`."""
    out = _run(['gh', 'auth', 'status', '--json', 'hosts'], timeout=5)
    try:
        hosts = json.loads(out or '{}').get('hosts', {}).get('github.com', [])
    except ValueError:
        return []
    return [h['login'] for h in hosts if h.get('login') and h.get('state') == 'success']


def _gh(account, *args):
    """Corre `gh` como una cuenta, sin cambiar la activa. None si no se pudo."""
    token = (_run(['gh', 'auth', 'token', '--user', account], timeout=5) or '').strip()
    if not token:
        return None
    return _run(['gh', *args], env={**os.environ, 'GH_TOKEN': token})


def snapshot(account):
    """PRs abiertos y revisiones pedidas de una cuenta, o None si no se pudo."""
    out = _gh(account, 'api', 'graphql', '-f', f'query={QUERY}')
    try:
        data = json.loads(out or '')['data']
        prs = {}
        for pr in data['viewer']['pullRequests']['nodes']:
            commits = pr['commits']['nodes']
            rollup = commits[0]['commit']['statusCheckRollup'] if commits else None
            prs[pr['url']] = {**_brief(pr), 'checks': rollup['state'] if rollup else None}
        reviews = {pr['url']: _brief(pr) for pr in data['search']['nodes'] if pr}
    except (ValueError, KeyError, TypeError, IndexError):
        return None
    return {'prs': prs, 'reviews': reviews}


def _brief(pr):
    slug = pr['repository']['nameWithOwner']
    return {'url': pr['url'], 'number': pr['number'], 'title': pr['title'],
            'repo': slug.split('/')[-1], 'slug': slug}


def failed_checks(account, pr):
    """Los checks caídos de un PR: [(nombre, id de su run de Actions o None)].

    Primero los de GitHub Actions, que son los que tienen log y se pueden
    reintentar. [] si no se pudo preguntar.
    """
    owner, _, name = pr['slug'].partition('/')
    out = _gh(account, 'api', 'graphql', '-f', f'query={CHECKS_QUERY}',
              '-f', f'owner={owner}', '-f', f'name={name}', '-F', f'number={pr["number"]}')
    try:
        commit = json.loads(out or '')['data']['repository']['pullRequest']['commits']['nodes'][0]
        nodes = commit['commit']['statusCheckRollup']['contexts']['nodes']
    except (ValueError, KeyError, TypeError, IndexError):
        return []
    checks = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get('__typename') == 'CheckRun' and node.get('conclusion') in FAILED:
            run = ((node.get('checkSuite') or {}).get('workflowRun') or {}).get('databaseId')
            checks.append((node.get('name') or 'check', run))
        elif node.get('__typename') == 'StatusContext' and node.get('state') in FAILED:
            checks.append((node.get('context') or 'check', None))
    return sorted(checks, key=lambda c: c[1] is None)


def clean_log(text):
    """Lo que imprimieron los pasos caídos de un run, sin job, paso ni fecha."""
    lines = []
    for line in (text or '').splitlines():
        line = _STAMP.sub('', line.split('\t', 2)[-1])
        mark = _MARK.match(line)
        if mark:
            # ##[group] y compañía son del visor de GitHub; el error sí se queda.
            if mark[1] != 'error':
                continue
            line = line[mark.end():]
        if line.strip():
            lines.append(line)
    return lines


def log_tail(account, pr, run, n=LOG_LINES):
    """Las últimas líneas del log de los pasos caídos de un run, o []."""
    out = _gh(account, 'run', 'view', str(run), '--repo', pr['slug'], '--log-failed')
    return clean_log(out)[-n:]


def card(account, pr, checks, lines):
    """La ficha de un PR en rojo: qué falló, el final del log y sus botones."""
    names = [name for name, _ in checks]
    run = next((r for _, r in checks if r), None)
    actions = [{'label': 'Abrir PR', 'url': pr['url'], 'after': 'dismiss'}]
    if run:
        # El token se pide al pulsar el botón: nunca queda guardado en la alerta.
        script = 'GH_TOKEN=$(gh auth token --user "$1") gh run rerun "$2" --failed --repo "$3"'
        actions.insert(0, {'label': 'Reintentar', 'term': True, 'hold': True, 'after': 'clear',
                           'cmd': ['bash', '-c', script, 'gh', account, str(run), pr['slug']]})
    where = names[0] + (f' y {len(names) - 1} más' if len(names) > 1 else '') if names else ''
    return {'where': where, 'note': _count(len(names), 'check caído', 'checks caídos') if names else '',
            # Sin log (un check que no es de Actions), los nombres de los demás.
            'lines': lines or names[1:], 'actions': actions}


def _alert(kind, pr, message, tone, **card):
    """card: la ficha de la alerta (where, note, lines, actions)."""
    return {'event': 'alert', 'session_id': f'gh:{kind}:{pr["url"]}', 'name': pr['repo'],
            'message': message, 'tone': tone, 'url': pr['url'], **card}


def _count(n, one, many):
    return f'{n} {one if n == 1 else many}'


def summary(snaps):
    """Cómo están las cosas ahora, para la burbuja: [líneas].

    snaps: cuenta -> su última foto, o None si no respondió. Un PR que ven
    dos cuentas se cuenta una vez.
    """
    good = {a: s for a, s in snaps.items() if s is not None}
    prs, reviews = {}, {}
    for snap in good.values():
        prs.update(snap['prs'])
        reviews.update(snap['reviews'])
    if not prs:
        lines = ['Sin PRs abiertos']
    else:
        checks = [pr['checks'] for pr in prs.values()]
        parts = [(sum(c in GREEN for c in checks), 'en verde'),
                 (sum(c in RED for c in checks), 'en rojo'),
                 (sum(c in RUNNING for c in checks), 'corriendo'),
                 (sum(c is None for c in checks), 'sin checks')]
        lines = [_count(len(prs), 'PR abierto', 'PRs abiertos') + ': '
                 + ', '.join(f'{n} {text}' for n, text in parts if n)]
    lines.append(_count(len(reviews), 'revisión pendiente', 'revisiones pendientes')
                 if reviews else 'Sin revisiones pendientes')
    bad = [a for a, s in snaps.items() if s is None]
    lines.append('Cuentas: ' + ', '.join(good) + (f' · no respondió {", ".join(bad)}' if bad else ''))
    return lines


class Watcher:
    def __init__(self, failed_checks=failed_checks, log_tail=log_tail):
        self.failed_checks, self.log_tail = failed_checks, log_tail
        self.before = {}          # cuenta -> foto anterior

    def step(self, account, snap):
        """Compara la foto de una cuenta con la anterior y devuelve los avisos."""
        if snap is None:
            return []
        before, self.before[account] = self.before.get(account), snap
        if before is None:
            return []
        msgs = []
        for url, pr in snap['prs'].items():
            was = before['prs'].get(url, {}).get('checks')
            now = pr['checks']
            if now == was or url not in before['prs']:
                continue
            label = f'PR #{pr["number"]}'
            if now in GREEN:
                msgs.append(_alert('ci', pr, f'{label}: checks en verde · {pr["title"]}', 'ok'))
            elif now in RED:
                checks = self.failed_checks(account, pr)
                run = next((r for _, r in checks if r), None)
                lines = self.log_tail(account, pr, run) if run else []
                msgs.append(_alert('ci', pr, f'{label}: checks en rojo · {pr["title"]}', '',
                                   **card(account, pr, checks, lines)))
        for url, pr in snap['reviews'].items():
            if url not in before['reviews']:
                msgs.append(_alert('review', pr,
                                   f'Te piden revisar el PR #{pr["number"]} · {pr["title"]}', 'info'))
        return msgs


def watch(emit, enabled=lambda: True, only=lambda: None):
    """Consulta GitHub en un hilo y llama a emit(mensaje) por cada aviso.

    only() da la lista de cuentas a consultar; sin ella, todas las de `gh`.
    Mientras enabled() sea falso no consulta, y al volver empieza de cero.
    """
    if not shutil.which('gh'):
        emit({'event': 'source', 'name': 'github', 'ok': False, 'note': 'falta gh',
              'why': 'No está instalado gh, el cliente de GitHub',
              'fix': 'Instálalo, entra con gh auth login y reinicia la mascota'})
        return

    def loop():
        watcher = None
        while True:
            if not enabled():
                watcher = None
                time.sleep(5)
                continue
            if watcher is None:
                watcher = Watcher()
            try:
                snaps = {}
                for account in only() or accounts():
                    snaps[account] = snapshot(account)
                    for msg in watcher.step(account, snaps[account]):
                        emit(msg)
                good = sum(s is not None for s in snaps.values())
                source = {'event': 'source', 'name': 'github', 'ok': good > 0, 'polled': True,
                          'note': _count(good, 'cuenta', 'cuentas')}
                if good:
                    source['tip'] = summary(snaps)
                elif snaps:
                    source.update(why='No respondió ninguna cuenta: ' + ', '.join(snaps),
                                  fix='Revisa la red y la sesión con: gh auth status')
                else:
                    source.update(why='gh no tiene ninguna cuenta con sesión iniciada',
                                  fix='Entra con: gh auth login')
                emit(source)
            except Exception:
                # Una respuesta con otra forma no debe matar al vigilante.
                pass
            # En trozos cortos, para notar pronto si la apagan o la prenden.
            for _ in range(POLL_SECS // 5):
                if not enabled():
                    break
                time.sleep(5)

    threading.Thread(target=loop, daemon=True, name='github').start()
