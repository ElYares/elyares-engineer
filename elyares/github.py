"""Avisa del CI de tus pull requests y de las revisiones que te piden.

Cada POLL_SECS le pregunta a GitHub con `gh`, una consulta por cuenta, y
compara con la vez anterior:

    checks   los de un PR tuyo pasaron a verde o a rojo
    revisión te pidieron revisar un PR

La primera consulta solo toma la foto. `gh` puede tener varias cuentas: se
consultan todas, o las que diga la preferencia `github_accounts`.
El token de cada una se le pide a `gh` y nunca se guarda ni se muestra.
"""

import json
import os
import shutil
import subprocess
import threading
import time

POLL_SECS = 120
GREEN = ('SUCCESS',)
RED = ('FAILURE', 'ERROR')

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


def snapshot(account):
    """PRs abiertos y revisiones pedidas de una cuenta, o None si no se pudo."""
    token = (_run(['gh', 'auth', 'token', '--user', account], timeout=5) or '').strip()
    if not token:
        return None
    out = _run(['gh', 'api', 'graphql', '-f', f'query={QUERY}'],
               env={**os.environ, 'GH_TOKEN': token})
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
    return {'url': pr['url'], 'number': pr['number'], 'title': pr['title'],
            'repo': pr['repository']['nameWithOwner'].split('/')[-1]}


def _alert(kind, pr, message, tone):
    return {'event': 'alert', 'session_id': f'gh:{kind}:{pr["url"]}', 'name': pr['repo'],
            'message': message, 'tone': tone, 'url': pr['url']}


class Watcher:
    def __init__(self):
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
                msgs.append(_alert('ci', pr, f'{label}: checks en rojo · {pr["title"]}', ''))
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
        emit({'event': 'source', 'name': 'github', 'ok': False, 'note': 'falta gh'})
        return

    def loop():
        watcher, state = None, None
        while True:
            if not enabled():
                watcher, state = None, None
                time.sleep(5)
                continue
            if watcher is None:
                watcher = Watcher()
            try:
                good = 0
                for account in only() or accounts():
                    snap = snapshot(account)
                    good += snap is not None
                    for msg in watcher.step(account, snap):
                        emit(msg)
                now = (good > 0, f'{good} cuenta' + ('' if good == 1 else 's'))
                if now != state:
                    state = now
                    emit({'event': 'source', 'name': 'github', 'ok': now[0], 'note': now[1]})
            except Exception:
                # Una respuesta con otra forma no debe matar al vigilante.
                pass
            # En trozos cortos, para notar pronto si la apagan o la prenden.
            for _ in range(POLL_SECS // 5):
                if not enabled():
                    break
                time.sleep(5)

    threading.Thread(target=loop, daemon=True, name='github').start()
