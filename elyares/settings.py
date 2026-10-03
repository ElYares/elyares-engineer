"""Preferencias que sobreviven al reinicio del daemon.

Viven en `~/.config/elyares-engineer/settings.json`. Si el archivo no existe o
está roto se usan los valores por defecto.
"""

import json
import os

# `pinned_monitor`: el monitor en el que se fijó la isla, para que se quede ahí.
# `chat_model` y `chat_effort`: lo último elegido en el chat ('' deja lo de Claude).
# `position`: dónde va la isla a lo ancho de la pantalla, de 0 (izquierda) a 100
# (derecha); 50, su sitio de siempre, es el centro.
DEFAULTS = {'compact': True, 'glass': False, 'pinned': False, 'pinned_monitor': '', 'position': 50,
            'chat_model': '',
            'chat_effort': '', 'devherd': True,
            'flows_collapsed': False,
            'coffe': True, 'github': True, 'terminal': True, 'usage': True, 'github_accounts': []}


def path():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'elyares-engineer', 'settings.json')


def load():
    try:
        with open(path()) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **(data if isinstance(data, dict) else {})}


def save(values):
    p = path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p + '.tmp', 'w') as f:
            json.dump(values, f, indent=2)
        os.replace(p + '.tmp', p)
    except OSError:
        pass
