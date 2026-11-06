"""Los temas de la isla y de la app.

Un tema es la base de todo lo que se pinta: el fondo, las tres superficies de
la ventana (ventana, tarjeta, tarjeta elevada), el texto, el gris apagado, el
acento y la paleta del texto resaltado (`paint.colors`). Los colores de aviso
(verde, rojo, ámbar) y los de los personajes no son del tema.

- `omarchy`: el de siempre; el acento y la paleta salen de `theme.py` (omarchy).
- `moonfly`: el del nvim de Yared (`bluz71/vim-moonfly-colors`).
- `undersea`: «Under The Sea», el de Ghostty y tmux de Yared.
- `navidad`: de temporada; la base oscura de `omarchy` con acento dorado y paleta roja, verde y dorada.

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
    'navidad': {
        'label': 'Navidad (rojo, verde y dorado)',
        'island': '#050608',
        'surface': ('#050608', '#10131a', '#1a1f2b'),
        'ink': '#f2f5ff', 'muted': '#8f9ab8', 'accent': '#f5c542', 'danger': '#ff6b6b',
        'island_muted': (.44, .49, .63, 1), 'island_tired': (.78, .82, .92, 1), 'tired': '#c9d2ea',
        'popup': (.07, .08, .10), 'chat_ink': '#eef1f6',
        'palette': {
            'accent': '#f5c542', 'foreground': '#eef1f6',
            'color9': '#ff6b6b', 'color10': '#5fd68a', 'color11': '#f5c542',
            'color12': '#7fd0ff', 'color13': '#ff8fb1', 'color14': '#b8f0d8',
        },
    },
    'brasa': {
        'label': 'Brasa (marrón cálido)',
        'island': '#140c08',
        'surface': ('#140c08', '#241610', '#33211a'),
        'ink': '#fbeee6', 'muted': '#c0a698', 'accent': '#ff9a7a', 'danger': '#ff6464',
        'island_muted': (.75, .65, .60, 1), 'island_tired': (.91, .82, .78, 1), 'tired': '#e8d2c6',
        'popup': (.11, .07, .05), 'chat_ink': '#f3e6dd',
        'palette': {
            'accent': '#ff9a7a', 'foreground': '#e8d2c6',
            'color9': '#ff8fa3', 'color10': '#c9a0ff', 'color11': '#f2b8a0',
            'color12': '#8ab4ff', 'color13': '#e58fd0', 'color14': '#7fd6e0',
        },
    },
    'orquidea': {
        'label': 'Orquídea (ciruela)',
        'island': '#0e0612',
        'surface': ('#0e0612', '#1e0f26', '#2e1a3a'),
        'ink': '#f8eefc', 'muted': '#b9a0c6', 'accent': '#f08ad0', 'danger': '#ff6b7a',
        'island_muted': (.73, .63, .78, 1), 'island_tired': (.89, .81, .92, 1), 'tired': '#e2cfeb',
        'popup': (.09, .05, .12), 'chat_ink': '#efe3f4',
        'palette': {
            'accent': '#f08ad0', 'foreground': '#e2cfeb',
            'color9': '#ff9ec0', 'color10': '#b69cff', 'color11': '#e8b4f0',
            'color12': '#7fb2ff', 'color13': '#d98af0', 'color14': '#6fd8e8',
        },
    },
    'grafito': {
        'label': 'Grafito (gris neutro)',
        'island': '#0b0b0c',
        'surface': ('#0b0b0c', '#1b1b1d', '#2a2a2d'),
        'ink': '#f4f4f2', 'muted': '#a4a4a8', 'accent': '#c8b6ff', 'danger': '#ff6b6b',
        'island_muted': (.64, .64, .66, 1), 'island_tired': (.84, .84, .85, 1), 'tired': '#d6d6d8',
        'popup': (.09, .09, .10), 'chat_ink': '#e8e8e6',
        'palette': {
            'accent': '#c8b6ff', 'foreground': '#d6d6d8',
            'color9': '#ff9eb5', 'color10': '#b9a4ff', 'color11': '#e0c8ff',
            'color12': '#8fb8ff', 'color13': '#e29af0', 'color14': '#86d8e6',
        },
    },
    'papel': {
        'label': 'Papel (claro suave)',
        'island': '#f4efe6',
        'surface': ('#f4efe6', '#e8e1d3', '#dbd2c0'),
        'ink': '#1c1a17', 'muted': '#4f493f', 'accent': '#174f9e', 'danger': '#a8201a',
        'island_muted': (.31, .29, .25, 1), 'island_tired': (.18, .16, .14, 1), 'tired': '#2e2a24',
        'popup': (.93, .91, .87), 'chat_ink': '#25221d',
        'palette': {
            'accent': '#174f9e', 'foreground': '#2e2a24',
            'color9': '#a8326e', 'color10': '#5b3fa8', 'color11': '#8a4a9e',
            'color12': '#1f5fbf', 'color13': '#7a3a9a', 'color14': '#0f6f86',
        },
    },
    'hueso': {
        'label': 'Hueso (blanco hueso suave)',
        'island': '#ebe6dc',
        'surface': ('#ebe6dc', '#e1dbcf', '#d7d0c2'),
        'ink': '#3b3832', 'muted': '#58544b', 'accent': '#375886', 'danger': '#a24a45',
        'island_muted': (0.35, 0.33, 0.29, 1), 'island_tired': (0.27, 0.26, 0.23, 1), 'tired': '#46423a',
        'popup': (0.91, 0.89, 0.85), 'chat_ink': '#403d36',
        'palette': {
            'accent': '#375886', 'foreground': '#46423a',
            'color9': '#9a4a6e', 'color10': '#6a4f9a', 'color11': '#85509a',
            'color12': '#4a64a0', 'color13': '#8a4f9a', 'color14': '#2f6f80',
        },
    },
    'perla': {
        'label': 'Perla (gris perla suave)',
        'island': '#e4e5e7',
        'surface': ('#e4e5e7', '#d9dbde', '#cdd0d4'),
        'ink': '#34373c', 'muted': '#4a4e55', 'accent': '#44566f', 'danger': '#9a4a4e',
        'island_muted': (0.29, 0.31, 0.33, 1), 'island_tired': (0.24, 0.25, 0.27, 1), 'tired': '#3d4046',
        'popup': (0.89, 0.9, 0.91), 'chat_ink': '#383b40',
        'palette': {
            'accent': '#44566f', 'foreground': '#3d4046',
            'color9': '#8c4a68', 'color10': '#5f4f94', 'color11': '#7c4f92',
            'color12': '#3f5f96', 'color13': '#7d4c92', 'color14': '#2f6677',
        },
    },
    'niebla': {
        'label': 'Niebla (blanco azulado suave)',
        'island': '#e3e9ee',
        'surface': ('#e3e9ee', '#d8e0e7', '#cdd7e0'),
        'ink': '#2f3a45', 'muted': '#47535f', 'accent': '#2d5a94', 'danger': '#9a4650',
        'island_muted': (0.28, 0.33, 0.37, 1), 'island_tired': (0.22, 0.27, 0.31, 1), 'tired': '#394450',
        'popup': (0.89, 0.91, 0.93), 'chat_ink': '#33404b',
        'palette': {
            'accent': '#2d5a94', 'foreground': '#394450',
            'color9': '#8a4668', 'color10': '#5c4c96', 'color11': '#78509a',
            'color12': '#2f62a0', 'color13': '#7a4a96', 'color14': '#26697c',
        },
    },
    'salvia': {
        'label': 'Salvia (blanco verdoso suave)',
        'island': '#e5e9e0',
        'surface': ('#e5e9e0', '#dbe0d5', '#d0d6c9'),
        'ink': '#363c34', 'muted': '#4c5448', 'accent': '#43587f', 'danger': '#9a4a46',
        'island_muted': (0.3, 0.33, 0.28, 1), 'island_tired': (0.25, 0.27, 0.24, 1), 'tired': '#3f463c',
        'popup': (0.9, 0.91, 0.88), 'chat_ink': '#3a4037',
        'palette': {
            'accent': '#43587f', 'foreground': '#3f463c',
            'color9': '#8a4a68', 'color10': '#6a4f94', 'color11': '#7d509a',
            'color12': '#44609a', 'color13': '#80509a', 'color14': '#2f6a76',
        },
    },
    'arena': {
        'label': 'Arena (blanco rosado suave)',
        'island': '#efe5e0',
        'surface': ('#efe5e0', '#e6dbd4', '#dccfc7'),
        'ink': '#40363a', 'muted': '#5a4d52', 'accent': '#6a4a82', 'danger': '#9c4040',
        'island_muted': (0.35, 0.3, 0.32, 1), 'island_tired': (0.29, 0.25, 0.27, 1), 'tired': '#4a4046',
        'popup': (0.93, 0.9, 0.88), 'chat_ink': '#443a3e',
        'palette': {
            'accent': '#6a4a82', 'foreground': '#4a4046',
            'color9': '#9a4468', 'color10': '#64509a', 'color11': '#85508f',
            'color12': '#40609c', 'color13': '#8a4f94', 'color14': '#2f6c7a',
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


def is_light():
    """¿Un tema de fondo claro? Todo lo que se aclara sobre oscuro ahí se oscurece."""
    r, g, b = tuple_of(get()['island'])
    return .2126 * r + .7152 * g + .0722 * b > .5


def glow():
    """El color de los velos y filos sobre una superficie: blanco en oscuro, negro en claro."""
    return (0, 0, 0) if is_light() else (1, 1, 1)


def hot():
    """El color del texto o del velo que se enciende (pasar el ratón, lo elegido): blanco en oscuro, la tinta en claro."""
    return tuple_of(get()['ink']) if is_light() else (1, 1, 1)


def sink():
    """El color de lo que se hunde bajo un bloque (el fondo de un código): negro en oscuro, blanco en claro."""
    return (1, 1, 1) if is_light() else (0, 0, 0)


def strong():
    """El extremo con más contraste contra el fondo, para aclarar u oscurecer un color."""
    return '#000000' if is_light() else '#ffffff'


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
