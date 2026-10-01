"""Colores del texto de la isla: el detalle con resaltado y el porcentaje de contexto.

El detalle de una sesión casi siempre es código: un comando, una ruta, un
patrón de búsqueda. `segments()` lo parte en trozos con un papel (comando,
opción, cadena, ruta...) y `colors()` le da un color a cada papel, sacado del
tema de omarchy cuando hay uno. No colorea como un editor: solo lo bastante
para que de un vistazo se distinga el comando de sus argumentos.

Los colores de aviso (ámbar y rojo) son fijos y no salen del tema: son
semánticos, y en algunos temas el "amarillo" de la paleta es un azul grisáceo.
"""

import re

ISLAND = '#050608'
AMBER, RED = '#e0a02e', '#e05252'

# Papel -> (clave del tema, color si no hay tema).
ROLES = {
    'cmd': ('accent', '#7aa2f7'),      # el programa que se ejecuta
    'flag': ('color13', '#bb9af7'),    # -x, --opción
    'str': ('color10', '#9ece6a'),     # "cadenas" y patrones
    'path': ('color14', '#7dcfff'),    # rutas y el nombre de un archivo
    'var': ('color11', '#e0af68'),     # VAR=valor, $VAR
    'num': ('color9', '#ff9e64'),      # números sueltos
    'arg': ('foreground', '#c0caf5'),  # el resto de los argumentos
}
VERBS = ('Ejecutando', 'Leyendo', 'Editando', 'Escribiendo', 'Buscando')
DONE = re.compile(r'(Terminó|Falló \(código \d+\))( en .+?: )(.*)', re.S)
TOKEN = re.compile(r'''(?P<ws>\s+)|(?P<str>"(?:[^"\\]|\\.)*"?|'[^']*'?)'''
                   r'''|(?P<op>&&|\|\||[|;<>&]+|\$\(|[()])|(?P<word>[^\s|;&<>()"']+)''')


def _hex(value):
    return value if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else None


def mix(a, b, w):
    """Mezcla dos #rrggbb; w es cuánto pesa b, de 0 a 1."""
    pa, pb = (int(a[i:i + 2], 16) for i in (1, 3, 5)), (int(b[i:i + 2], 16) for i in (1, 3, 5))
    return '#' + ''.join(f'{round(x * (1 - w) + y * w):02x}' for x, y in zip(pa, pb))


def colors(palette=None):
    """Papel -> #rrggbb. `palette` es lo que trae colors.toml del tema, o nada."""
    palette = palette or {}
    out = {role: _hex(palette.get(key)) or fallback for role, (key, fallback) in ROLES.items()}
    fg = out['arg']
    # Los temas apagados se pierden sobre la isla negra: se aclaran un poco.
    out = {role: mix(c, '#ffffff', .12) for role, c in out.items()}
    out.update({
        'text': mix(ISLAND, fg, .78),      # un detalle que no es código
        'dim': mix(ISLAND, fg, .48),       # verbos, operadores, la carpeta de una ruta
        'ok': mix(_hex(palette.get('color10')) or '#35d07f', '#ffffff', .12),
        'bad': RED,
        # Contexto usado: verde, arena, ámbar, rojo.
        'pct0': mix(_hex(palette.get('color10')) or '#35d07f', '#ffffff', .12),
        'pct1': mix(_hex(palette.get('color11')) or '#e0af68', '#ffffff', .12),
        'pct2': AMBER,
        'pct3': RED,
    })
    return out


def context_role(pct):
    """El papel del porcentaje de contexto, según lo lleno que va."""
    return 'pct3' if pct >= 90 else 'pct2' if pct >= 70 else 'pct1' if pct >= 50 else 'pct0'


def _shell(text):
    """Un comando de shell, trozo a trozo."""
    out, at_command = [], True
    for m in TOKEN.finditer(text):
        kind, tok = m.lastgroup, m.group()
        if kind == 'ws':
            out.append((tok, 'arg'))
        elif kind == 'str':
            out.append((tok, 'str'))
        elif kind == 'op':
            out.append((tok, 'dim'))
            # Tras | && ; $( empieza otro comando; tras > viene un archivo.
            at_command = tok in ('&&', '||', '|', ';', '$(', '(')
        elif at_command and re.match(r'\w+=', tok):
            out.append((tok, 'var'))
        elif at_command:
            out.append((tok, 'cmd'))
            at_command = False
        elif tok.startswith('-'):
            out.append((tok, 'flag'))
        elif tok.startswith('$') or re.match(r'\w+=', tok):
            out.append((tok, 'var'))
        elif '/' in tok or tok.startswith(('~', '.')):
            out.append((tok, 'path'))
        elif re.fullmatch(r'\d[\d.,:]*', tok):
            out.append((tok, 'num'))
        else:
            out.append((tok, 'arg'))
    return out


def _path(text):
    """Una ruta: la carpeta apagada y el nombre del archivo a color."""
    head, sep, name = text.rpartition('/')
    return [(head + sep, 'dim'), (name, 'path')] if sep else [(text, 'path')]


def segments(detail):
    """El detalle de una sesión como [(texto, papel)], en orden."""
    detail = detail or ''
    for verb in VERBS:
        if detail.startswith(verb + ' '):
            rest = detail[len(verb) + 1:]
            body = (_shell(rest) if verb == 'Ejecutando'
                    else [(rest, 'str')] if verb == 'Buscando' else _path(rest))
            return [(verb + ' ', 'dim')] + body
    m = DONE.fullmatch(detail)
    if m:
        # Un comando largo de la terminal que terminó.
        return [(m[1], 'ok' if m[1] == 'Terminó' else 'bad'), (m[2], 'dim')] + _shell(m[3])
    return [(detail, 'text')]
