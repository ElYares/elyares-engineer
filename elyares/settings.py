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
# `position_y`: cuántos px baja desde el borde de arriba; 0 es su sitio de siempre.
# `window`: la app estaba en ventana (y no en isla) al apagarse o recargarse.
# `font`: la letra de la app (ver `fonts.CHOICES`); 'Sans' es la del sistema.
# `theme`: el tema de la isla y la app (ver `themes.THEMES`).
# `chat_tech`: el chat con bloques de borde fino y títulos en mayúsculas.
# `tired_eyes`: vista cansada: letra más grande y gruesa, textos apagados más claros.
# `tech_style`: estilo técnico: esquinas rectas, bordes de 1 px y toda la letra monoespaciada.
# `tired_scale`: cuánto agranda la vista cansada, en %: 125, 150 o 200.
# `adhd`: las respuestas del chat siguen `rules/estilo/respuesta-adhd.md`.
# `files_collapsed`: la lista de archivos del Editor y del Taller, plegada (nvim ocupa todo el ancho).
# `window_size`: [ancho, alto] que Yared le dejó a la ventana; [] hasta que la estira.
DEFAULTS = {'compact': True, 'glass': False, 'pinned': False, 'pinned_monitor': '', 'position': 50, 'position_y': 0, 'window': False, 'window_size': [], 'font': 'Sans', 'theme': 'omarchy', 'chat_tech': False, 'tired_eyes': False, 'tech_style': False, 'tired_scale': 125, 'adhd': True,
            'chat_model': '',
            'chat_effort': '', 'devherd': True,
            'flows_collapsed': False, 'files_collapsed': False,
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
