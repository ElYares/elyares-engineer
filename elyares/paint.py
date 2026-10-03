"""Colores del texto de la isla: el detalle con resaltado y el porcentaje de contexto.

El detalle de una sesión casi siempre es código: un comando, una ruta, un
patrón de búsqueda. `segments()` lo parte en trozos con un papel (comando,
opción, cadena, ruta...) y `colors()` le da un color a cada papel, sacado del
tema de omarchy cuando hay uno. No colorea como un editor: solo lo bastante
para que de un vistazo se distinga el comando de sus argumentos.

Los colores de aviso (ámbar, rojo y el verde de unas pruebas que pasaron) son
fijos y no salen del tema: son semánticos, y en algunos temas el "amarillo" de
la paleta es un azul grisáceo y el "verde", un gris.
"""

import colorsys
import html
import re

ISLAND = '#050608'
AMBER, RED, GREEN = '#e0a02e', '#e05252', '#35d07f'

# Papel -> (clave del tema, color si no hay tema).
ROLES = {
    'cmd': ('accent', '#7aa2f7'),      # el programa que se ejecuta
    'flag': ('color13', '#bb9af7'),    # -x, --opción
    'str': ('color10', '#9ece6a'),     # "cadenas" y patrones
    'path': ('color14', '#7dcfff'),    # rutas y el nombre de un archivo
    'var': ('color11', '#e0af68'),     # VAR=valor, $VAR
    'num': ('color9', '#ff9e64'),      # números sueltos
    'arg': ('foreground', '#c0caf5'),  # el resto de los argumentos
    'head': ('color12', '#7aa2f7'),    # el título de un bloque, en la burbuja de una fuente
}
VERBS = ('Ejecutando', 'Leyendo', 'Editando', 'Escribiendo', 'Buscando')
DONE = re.compile(r'(Terminó|Falló \(código \d+\))( en .+?: )(.*)', re.S)
TESTS = re.compile(r'(Pruebas en verde|Pruebas en rojo|Corriendo pruebas)(: .*)', re.S)
TEST_ROLES = {'Pruebas en verde': 'pass', 'Pruebas en rojo': 'bad', 'Corriendo pruebas': 'cmd'}
TOKEN = re.compile(r'''(?P<ws>\s+)|(?P<str>"(?:[^"\\]|\\.)*"?|'[^']*'?)'''
                   r'''|(?P<op>&&|\|\||[|;<>&]+|\$\(|[()])|(?P<word>[^\s|;&<>()"']+)''')


def _hex(value):
    return value if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else None


def mix(a, b, w):
    """Mezcla dos #rrggbb; w es cuánto pesa b, de 0 a 1."""
    pa, pb = (int(a[i:i + 2], 16) for i in (1, 3, 5)), (int(b[i:i + 2], 16) for i in (1, 3, 5))
    return '#' + ''.join(f'{round(x * (1 - w) + y * w):02x}' for x, y in zip(pa, pb))


def vivid(color, sat, light):
    """Un #rrggbb con el mismo tono, más saturado (`sat` veces) y al menos así
    de claro: para que un tema apagado no se pierda sobre un fondo translúcido."""
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    rgb = colorsys.hls_to_rgb(h, max(l, light), min(1.0, s * sat))
    return '#' + ''.join(f'{round(c * 255):02x}' for c in rgb)


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
        'pass': GREEN,
        # Contexto usado: verde, arena, ámbar, rojo.
        'pct0': mix(_hex(palette.get('color10')) or '#35d07f', '#ffffff', .12),
        'pct1': mix(_hex(palette.get('color11')) or '#e0af68', '#ffffff', .12),
        'pct2': AMBER,
        'pct3': RED,
    })
    return out


def command(text):
    """Un comando para consultar, como [(texto, papel)]: el programa, lo que
    se le pide, sus opciones y lo que hay que poner (`<tarea>`, `[ruta]`)."""
    out = []
    for tok in re.split(r'(\s+)', text or ''):
        if not tok:
            continue
        if tok.isspace() or not out:
            role = 'arg' if out else 'cmd'
        else:
            role = 'var' if tok[0] in '<[' else 'flag' if tok[0] == '-' else 'arg'
        out.append((tok, role))
    return out


# Una cifra con su nombre ("3 pomodoros hoy", "Quedan 12:40") o un rato ("1 h 15 min").
NUMBER = r'\d[\d:.,]*%?'
SPAN = r'\d+ h(?: \d+ min)?|\d+ min'
STAT = re.compile(rf'(?P<span>{SPAN})|(?P<value>{NUMBER})\s+(?P<label>\D.*)|(?P<name>\D+?)\s+(?P<last>{NUMBER})')
STAT_LABEL = 28           # un nombre más largo que esto ya no es el de una cifra: es una frase
NOTE = re.compile(rf'(?P<num>{SPAN}|{NUMBER})|(?P<pass>en verde)|(?P<bad>en rojo|no respondió)'
                  r'|(?P<pct2>corriendo)')


def stats(line):
    """Una línea de datos como [(cifra, su nombre)] si toda ella son cifras
    con su nombre, separadas por " · "; None si no, y entonces es una frase."""
    out = []
    for part in (line or '').split(' · '):
        m = STAT.fullmatch(part.strip())
        if not m:
            return None
        if m['span']:
            value, label = m['span'], ''
        elif m['value']:
            value, label = m['value'], m['label']
        else:
            value, label = m['last'], m['name'].lower()
        if len(label) > STAT_LABEL or ':' in label:
            return None
        out.append((value, label))
    return out


def note(text):
    """Una frase de datos como [(texto, papel)]: su nombre ("Tarea:") más
    suave, las cifras resaltadas, y en su color lo que va bien o mal."""
    key, sep, rest = (text or '').partition(': ')
    out = []
    for chunk, base in ((key + sep, 'text'), (rest, 'arg')) if sep else ((text or '', 'arg'),):
        pos = 0
        for m in NOTE.finditer(chunk):
            if m.start() > pos:
                out.append((chunk[pos:m.start()], base))
            out.append((m.group(), m.lastgroup))
            pos = m.end()
        if pos < len(chunk):
            out.append((chunk[pos:], base))
    return out


FENCE = re.compile(r'\s*```')
HEADING = re.compile(r'(#{1,6})\s+(.*)')
BULLET = re.compile(r'(\s*)[-*]\s+(.*)')
NUMBERED = re.compile(r'(\s*)(\d+)[.)]\s+(.*)')
QUOTE = re.compile(r'\s*>\s?(.*)')
DIVIDER = re.compile(r'\s*([-*_])(\s*\1){2,}\s*')
BOLD = re.compile(r'\*\*(.+?)\*\*')
ITALIC = re.compile(r'(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])|(?<![\w])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w])')
LINK = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')
CODE = re.compile(r'`([^`]+)`')
DIVIDER_WIDTH = 28


def markdown(text, code='#c0caf5', head='#ffffff', bold=None, dim=None, accent=None):
    """Lo que escribe Claude (markdown) como marcado de Pango, con lo justo
    para leerlo en la isla: negritas, `código` y títulos, viñetas, y los
    bloques de código y las tablas en monoespaciado, para que no se
    desalineen. `code` y `head` son los colores del código y de los títulos.

    Con `bold`, `dim` y `accent` se lee mejor, con jerarquía: las negritas en
    su color (más claro que el texto), las cursivas y los enlaces, las
    viñetas y los números en el acento, las listas con su sangría, las citas
    con su barra, la raya `---` como una línea suave, y un respiro antes de
    cada título. Sin ellos sale como siempre."""
    rich = bool(bold or dim or accent)
    mono = f'<span font_family="monospace" foreground="{code}">'
    out, fenced, table = [], False, []

    def inline(line):
        return _inline(line, mono, bold, rich)

    for line in (text or '').split('\n'):
        if line.lstrip().startswith('|') and not fenced:
            table.append(line)
            continue
        if table:
            out += _table(table, mono)
            table = []
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            out.append(f'{mono}{html.escape(line, quote=False)}</span>')
            continue
        if rich and not line.strip():
            if out and out[-1] != '':
                out.append('')          # una sola línea en blanco, por muchas que haya
            continue
        m = HEADING.fullmatch(line)
        if m:
            size = ' size="large"' if len(m[1]) <= 2 else ''
            if rich and out and out[-1] != '':
                out.append('')          # un respiro antes de un título
            out.append(f'<span foreground="{head}" weight="bold"{size}>{inline(m[2])}</span>')
            continue
        if rich and DIVIDER.fullmatch(line):
            out.append(f'<span foreground="{dim or head}">{"─" * DIVIDER_WIDTH}</span>')
            continue
        m = BULLET.fullmatch(line)
        if m:
            if rich:
                mark = '•' if len(m[1]) < 2 else '◦'
                out.append(f'{m[1]}<span foreground="{accent or head}">{mark}</span> {inline(m[2])}')
            else:
                out.append(_inline(f'{m[1]}• {m[2]}', mono))
            continue
        m = NUMBERED.fullmatch(line) if rich else None
        if m:
            out.append(f'{m[1]}<span foreground="{accent or head}" weight="bold">{m[2]}.</span> {inline(m[3])}')
            continue
        m = QUOTE.fullmatch(line) if rich else None
        if m:
            out.append(f'<span foreground="{accent or dim}">▎</span> <span foreground="{dim or head}">{inline(m[1])}</span>')
            continue
        out.append(inline(line))
    if table:
        out += _table(table, mono)
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out)


RULE = re.compile(r'[\s|:-]+')


def _table(lines, mono):
    """Una tabla de markdown, con sus columnas alineadas en monoespaciado:
    sin la fila de guiones y con la cabecera en negrita."""
    rows = [[cell.strip() for cell in line.strip().strip('|').split('|')]
            for line in lines if not RULE.fullmatch(line)]
    cols = max(len(row) for row in rows)
    rows = [row + [''] * (cols - len(row)) for row in rows]
    widths = [max(len(row[i]) for row in rows) for i in range(cols)]
    out = []
    for n, row in enumerate(rows):
        text = html.escape('  '.join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip(), quote=False)
        out.append(f'{mono}<b>{text}</b></span>' if n == 0 and len(rows) > 1 else f'{mono}{text}</span>')
    return out


def _inline(line, mono, bold=None, rich=False):
    """Negritas, `código` y, si `rich`, cursivas y enlaces dentro de una línea.
    Lo que va entre acentos graves se queda como está: ahí un `**` o un `_`
    son del código."""
    out = []
    for part in re.split(r'(`[^`]+`)', line):
        if len(part) > 2 and part.startswith('`') and part.endswith('`'):
            out.append(f'{mono}{html.escape(part[1:-1], quote=False)}</span>')
            continue
        part = html.escape(part, quote=False)
        if rich:
            part = LINK.sub(r'<u>\1</u>', part)
            part = ITALIC.sub(lambda m: f'<i>{m[1] or m[2]}</i>', part)
        tag = f'<span weight="bold" foreground="{bold}">\\1</span>' if bold else r'<b>\1</b>'
        out.append(BOLD.sub(tag, part))
    return ''.join(out)


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
    m = TESTS.fullmatch(detail)
    if m:
        return [(m[1], TEST_ROLES[m[1]]), (m[2], 'text')]
    return [(detail, 'text')]
