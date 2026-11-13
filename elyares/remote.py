"""Aviso al celular: manda a un webhook de Slack lo que una sesión lleva rato
esperando de ti (un permiso, que terminó, que te espera).

El webhook va en `~/.config/elyares-engineer/slack-webhook` (modo 600) o en
`ELYARES_SLACK_WEBHOOK`; sin ninguno de los dos no se manda nada. El mensaje
lleva el proyecto y el motivo, nunca el comando que pide el permiso.
"""

import json
import os
import sys
import threading
import urllib.request

from . import state

PREFIX = 'https://hooks.slack.com/'
ENV = 'ELYARES_SLACK_WEBHOOK'
DELAY = 120       # segundos sin que contestes antes de avisar
TIMEOUT = 5
TEXT = {'permission': 'pide permiso', 'done': 'terminó', 'waiting': 'te espera'}


def path():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'elyares-engineer', 'slack-webhook')


def webhook():
    """La URL del webhook, o '' si no hay o el archivo lo puede leer otro usuario."""
    url = os.environ.get(ENV, '').strip()
    if not url:
        try:
            if os.stat(path()).st_mode & 0o077:
                print(f'elyares: {path()} debe ser modo 600; no se avisa al celular',
                      file=sys.stderr)
                return ''
            with open(path()) as f:
                url = f.read().strip()
        except OSError:
            return ''
    return url if url.startswith(PREFIX) else ''


def post(url, text):
    req = urllib.request.Request(url, json.dumps({'text': text}).encode(),
                                 {'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT).close()
    except (OSError, ValueError) as e:
        print(f'elyares: no se pudo avisar a Slack: {e}', file=sys.stderr)


def escape(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def message(s):
    text = f'*{escape(state.project_name(s.cwd))}* {TEXT[s.state]}'
    if s.state != 'permission' and s.detail:
        text += f': {escape(state.short(s.detail, 80))}'
    return text


class Pager:
    """Vigila las sesiones y avisa una vez por cada estado que se alarga."""

    def __init__(self, get_url=webhook, send=post, delay=DELAY):
        self.get_url, self.send, self.delay = get_url, send, delay
        self.pending = {}     # sid -> (estado, cuándo se avisa)
        self.sent = {}        # sid -> estado del que ya se avisó

    def check(self, sessions, now, dnd=False):
        """Llamarlo tras cada evento y cada pocos segundos. Devuelve lo que mandó."""
        for sid in set(self.pending) | set(self.sent):
            if sid not in sessions:
                self.pending.pop(sid, None)
                self.sent.pop(sid, None)
        out = []
        for sid, s in sessions.items():
            if s.name or not s.cwd:
                continue                      # una alerta, no una sesión de Claude
            if s.state not in TEXT:
                self.pending.pop(sid, None)
                self.sent.pop(sid, None)
                continue
            if self.sent.get(sid) == s.state:
                continue
            due = self.pending.get(sid)
            if due is None or due[0] != s.state:
                self.pending[sid] = (s.state, now + self.delay)
            elif now >= due[1] and not dnd:
                url = self.get_url()
                if url:
                    text = message(s)
                    threading.Thread(target=self.send, args=(url, text), daemon=True).start()
                    out.append(text)
                del self.pending[sid]
                self.sent[sid] = s.state
        return out
