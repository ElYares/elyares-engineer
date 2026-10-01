"""Preferencias que sobreviven al reinicio del daemon.

Viven en `~/.config/elyares-mascota/settings.json`. Si el archivo no existe o
está roto se usan los valores por defecto.
"""

import json
import os

DEFAULTS = {'compact': True, 'glass': False, 'devherd': True, 'coffe': True, 'github': True,
            'terminal': True, 'usage': True, 'github_accounts': []}


def path():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'elyares-mascota', 'settings.json')


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
