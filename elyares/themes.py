"""Los temas de la isla y de la app.

Un tema es la base de todo lo que se pinta: el fondo, las tres superficies de
la ventana (ventana, tarjeta, tarjeta elevada), el texto, el gris apagado, el
acento y la paleta del texto resaltado (`paint.colors`). Los colores de aviso
(verde, rojo, ámbar) y los de los personajes no son del tema.

- `omarchy`: el de siempre; el acento y la paleta salen de `theme.py` (omarchy).
- `moonfly`: el del nvim de Yared (`bluz71/vim-moonfly-colors`).
- `undersea`: «Under The Sea», el de Ghostty y tmux de Yared.

Cada texto debe contrastar 4.5:1 o más con cada superficie (HU-005); una prueba
lo revisa para todos los temas.
"""

import re

from . import theme as omarchy

DEFAULT = 'omarchy'

THEMES = {
    'omarchy': {
        'label': 'Omarchy (sigue al sistema)',
        'island': '#050608',
        'surface': ('#050608', '#10131a', '#1a1f2b'),
        'ink': '#f2f5ff', 'muted': '#8f9ab8', 'accent': '#6ea8ff', 'danger': '#ff6b6b',
        'island_muted': (.44, .49, .63, 1), 'island_tired': (.78, .82, .92, 1), 'tired': '#c9d2ea',
        'popup': (.07, .08, .10), 'chat_ink': '#eef1f6',
        'palette': None,
    },
    'moonfly': {
        'label': 'Moonfly (el de nvim)',
        'island': '#09090e',
        'surface': ('#09090e', '#1a1a26', '#26263a'),
        'ink': '#ececf8', 'muted': '#a6a6c4', 'accent': '#80a0ff', 'danger': '#ff5454',
        'island_muted': (.65, .65, .77, 1), 'island_tired': (.84, .84, .93, 1), 'tired': '#d4d4ea',
        'popup': (.10, .10, .15), 'chat_ink': '#e0e0ee',
        'palette': {
            'accent': '#80a0ff', 'foreground': '#c6c6c6',
            'color9': '#de935f', 'color10': '#85dc85', 'color11': '#e3c78a',
            'color12': '#74b2ff', 'color13': '#cf87e8', 'color14': '#79dac8',
        },
    },
    'undersea': {
        'label': 'Under The Sea (Ghostty y tmux)',
        'island': '#011116',
        'surface': ('#011116', '#042229', '#0a3039'),
        'ink': '#f2fffc', 'muted': '#8fb8b3', 'accent': '#4afcd6', 'danger': '#ff5c5c',
        'island_muted': (.56, .72, .70, 1), 'island_tired': (.81, .91, .90, 1), 'tired': '#cfe8e4',
        'popup': (.02, .13, .16), 'chat_ink': '#e6f4f1',
        'palette': {
            'accent': '#4afcd6', 'foreground': '#e3f4f1',
            'color9': '#e0a070', 'color10': '#2aea5e', 'color11': '#8ed4fd',
            'color12': '#61d5ba', 'color13': '#5ab4ff', 'color14': '#98d028',
        },
    },
}

current = DEFAULT


def valid(name):
    return name if name in THEMES else DEFAULT


def use(name):
    """Deja `name` como el tema de ahora (o el de siempre si no existe) y lo devuelve."""
    global current
    current = valid(name)
    return current


def get():
    return THEMES[current]


def palette():
    """La paleta del tema: la fija, o la de omarchy cuando sigue al sistema."""
    fixed = get()['palette']
    return dict(fixed) if fixed else omarchy.palette()


def keys():
    return list(THEMES)


def label(name):
    return THEMES[valid(name)]['label']


def tuple_of(color):
    """`#rrggbb` -> (r, g, b) entre 0 y 1."""
    return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))


def rgb255(color):
    """`#rrggbb` -> (r, g, b) entre 0 y 255, para el CSS."""
    assert re.fullmatch(r'#[0-9a-fA-F]{6}', color), color
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
