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
STEP_TITLE = re.compile(r'\s*\*\*((?:(?!\*\*).)+)\*\*\s*')
ITALIC = re.compile(r'(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])|(?<![\w])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w])')
LINK = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')
CODE = re.compile(r'`([^`]+)`')
DIVIDER_WIDTH = 28
URL = re.compile(r'https?://[^\s<>"\'`)\]]+')


def urls(text):
    """Los enlaces de un texto, sin repetir y en orden, sin la puntuación que
    les pega una frase («...abc.», «...abc,»)."""
    out = []
    for m in URL.finditer(text or ''):
        url = m.group().rstrip('.,;:!?*')
        if url not in out:
            out.append(url)
    return out


def markdown(text, code='#c0caf5', head='#ffffff', bold=None, dim=None, accent=None,
             ink=None, shade=None, blocks=None, tables=None, caps=False):
    """Lo que escribe Claude (markdown) como marcado de Pango, con lo justo
    para leerlo en la isla: negritas, `código` y títulos, viñetas, y los
    bloques de código y las tablas en monoespaciado, para que no se
    desalineen. `code` y `head` son los colores del código y de los títulos.

    Con `bold`, `dim` y `accent` se lee mejor, con jerarquía: las negritas en
    su color (más claro que el texto), las cursivas y los enlaces, las
    viñetas y los números en el acento, las listas con su sangría, las citas
    con su barra, la raya `---` como una línea suave, y un respiro antes de
    cada título. Sin ellos sale como siempre.

    Con `ink` y `shade` (un #rrggbb de fondo), los bloques de código salen
    resaltados según su lenguaje, con los colores de moonfly (el tema de
    nvim), y sobre ese fondo; el código inline lleva el fondo también. `blocks` recibe [(lenguaje, texto)] de cada bloque,
    en orden. Cada bloque va entre dos líneas de respiro que llevan CODE_MARK
    y CODE_END: con ellas la isla sabe dónde pintar su fondo.

    Con `caps`, los títulos salen chicos, en mayúsculas y con espacio entre letras.

    Con `tables` (una lista), una tabla no va en el texto: deja en su sitio
    una línea con TABLE_MARK y se apunta ahí como (filas, alineación, con
    cabecera), para que la dibuje la isla, que es quien sabe cuánto mide cada
    celda. Sin `tables` sale en monoespaciado, alineada con espacios."""
    rich = bool(bold or dim or accent)
    mono = f'<span font_family="monospace" foreground="{code}">'
    out, fenced, table, lang, body = [], False, [], '', []
    shaded = f'<span font_family="monospace" foreground="{code}" background="{shade}">' if shade else mono

    def inline(line):
        return _inline(line, shaded, bold, rich)

    def grid(lines):
        if tables is None:
            return _table(lines, mono)
        found = _grid(lines, inline, head)
        if found:
            tables.append(found)
        return [TABLE_MARK] if found else []

    for line in (text or '').replace(TABLE_MARK, '').split('\n'):
        if line.lstrip().startswith('|') and not fenced:
            table.append(line)
            continue
        if table:
            out += grid(table)
            table = []
        if FENCE.match(line):
            fenced = not fenced
            if fenced:
                lang, body = line.strip()[3:].strip().lower(), []
                if shade and ink:
                    out.append(f'{mono} {CODE_MARK}</span>')       # el borde de arriba: lleva el «copiar»
            else:
                if blocks is not None and body:
                    blocks.append((lang, '\n'.join(body)))
                if shade and ink:
                    out.append(f'<span size="small"> {CODE_END}</span>')
            continue
        if fenced:
            if shade and ink:
                out.append(_code_line(line, lang, mono))
            else:
                out.append(f'{mono}{html.escape(line, quote=False)}</span>')
            body.append(line)
            continue
        if rich and not line.strip():
            if out and out[-1] != '':
                out.append('')          # una sola línea en blanco, por muchas que haya
            continue
        m = HEADING.fullmatch(line)
        if m:
            size = ' size="large"' if len(m[1]) <= 2 else ''
            if caps:
                size = ' size="small" letter_spacing="1200"'
            if rich and out and out[-1] != '':
                out.append('')          # un respiro antes de un título
            out.append(f'<span foreground="{head}" weight="bold"{size}>{inline(m[2].upper() if caps else m[2])}</span>')
            continue
        m = STEP_TITLE.fullmatch(line) if rich else None
        if m:
            # Una línea toda en negrita («**A. Paso**») es el título de un paso:
            # va en el color de los títulos para que se vea dónde empieza.
            if out and out[-1] != '':
                out.append('')
            out.append(f'<span foreground="{head}" weight="bold">{inline(m[1])}</span>')
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
        out += grid(table)
    if fenced:                                      # un bloque que aún se está escribiendo
        if blocks is not None and body:
            blocks.append((lang, '\n'.join(body)))
        if shade and ink:
            out.append(f'<span size="small"> {CODE_END}</span>')
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out)


COMMENT = {'python': '#', 'yaml': '#', 'js': '//', 'sql': '--', 'json': '//'}
CODE_MARK = '\u2063'         # invisible: la línea de arriba de un bloque de código
CODE_END = '\u2064'          # invisible: la de abajo
TABLE_MARK = '\ufffc'        # el hueco de una tabla: la isla la dibuja ahí
KEYWORDS = {
    'python': 'and as assert async await break class continue def del elif else except finally for from global if '
              'import in is lambda None nonlocal not or pass raise return self True False try while with yield',
    'js': 'async await break case catch class const continue default delete do else export extends false finally for '
          'from function if import in instanceof let new null of return static super switch this throw true try '
          'typeof undefined var void while yield interface type enum implements public private readonly',
    'sql': 'select from where insert into update delete create table join left right inner on group by order limit '
           'and or not null as set values',
}
LANGS = {'py': 'python', 'python': 'python', 'js': 'js', 'javascript': 'js', 'ts': 'js', 'typescript': 'js',
         'jsx': 'js', 'tsx': 'js', 'json': 'json', 'yaml': 'yaml', 'yml': 'yaml', 'toml': 'yaml',
         'sql': 'sql', 'bash': 'shell', 'sh': 'shell', 'shell': 'shell', 'zsh': 'shell', 'console': 'shell', '': 'shell'}
CODE_TOKEN = re.compile(r'(?P<com>#.*|//.*|--.*)|(?P<str>"(?:[^"\\]|\\.)*"?|\'(?:[^\'\\]|\\.)*\'?|`[^`]*`?)'
                        r'|(?P<num>\b\d[\d._]*\b)|(?P<word>[A-Za-z_][\w-]*)|(?P<other>.)', re.S)


def highlight(lang, line):
    """Una línea de código como [(texto, papel)]: comentarios, textos, cifras
    y palabras clave. Sin el lenguaje, o si es shell, se lee como un comando."""
    kind = LANGS.get((lang or '').split()[0] if lang else '', None)
    if kind in (None, 'shell'):
        return _shell(line[2:] if line.startswith('$ ') else line) if kind == 'shell' else [(line, 'cmd')]
    words = set(KEYWORDS.get(kind, '').split())
    out = []
    for m in CODE_TOKEN.finditer(line):
        tok, role = m.group(), m.lastgroup
        if role == 'com' and not tok.startswith(COMMENT[kind]):
            role = 'other'
        out.append((tok, {'com': 'dim', 'str': 'str', 'num': 'num', 'other': 'arg',
                          'word': 'flag' if tok in words or tok.lower() in words and kind == 'sql' else 'arg'}[role]))
    if kind in ('json', 'yaml'):
        out = [(t, 'cmd' if r == 'arg' and re.fullmatch(r'[\w-]+', t) and kind == 'yaml' else r) for t, r in out]
    return out


# Los colores de los bloques de código son los de moonfly, el tema de nvim.
MOONFLY = {
    'white': '#c6c6c6', 'comment': '#949494', 'keyword': '#cf87e8', 'const': '#ff5189', 'string': '#c6c684',
    'number': '#de935f', 'func': '#74b2ff', 'type': '#36c692', 'macro': '#79dac8', 'prop': '#adadf3',
    'self': '#8cc85f', 'op': '#e65e72', 'path': '#e196a2', 'add': '#85dc85', 'del': '#ff5d5d',
}
_C_KEYWORDS = ('if else for while do switch case default break continue return goto in as is new delete throw try '
               'catch finally await async yield import export from package use mod pub crate super where impl trait '
               'struct enum union class interface extends implements static const let mut var val fn func function def '
               'type typeof instanceof void unsafe extern ref move dyn loop match fun override abstract final '
               'public private protected namespace using lambda with pass raise except elif and or not del global '
               'nonlocal assert select from where insert into update delete create table join left right inner on '
               'group by order limit set values end then local repeat until function readonly declare').split()
_C_TYPES = ('i8 i16 i32 i64 i128 isize u8 u16 u32 u64 u128 usize f32 f64 bool char str int float double long short '
            'string number boolean any never object byte rune error uint int32 int64 uint8 dynamic String Vec Option '
            'Result Box').split()
_COMMENTS = {'c': r'//.*|/\*.*?(?:\*/|$)', 'hash': r'#.*', 'dash': r'--.*'}
_KIND = {'rust': 'c', 'rs': 'c', 'go': 'c', 'golang': 'c', 'c': 'c', 'cpp': 'c', 'c++': 'c', 'h': 'c', 'java': 'c',
         'kotlin': 'c', 'dart': 'c', 'php': 'c', 'js': 'c', 'javascript': 'c', 'ts': 'c', 'typescript': 'c',
         'jsx': 'c', 'tsx': 'c', 'json': 'c', 'jsonc': 'c', 'python': 'hash', 'py': 'hash', 'yaml': 'hash',
         'yml': 'hash', 'toml': 'hash', 'sql': 'dash', 'lua': 'dash'}
_CONSTS = {'true', 'false', 'True', 'False', 'None', 'null', 'nil', 'undefined', 'NULL'}
_SELF = {'self', 'Self', 'this', 'super'}
_NAMING = {'struct', 'enum', 'class', 'trait', 'impl', 'interface', 'type', 'union', 'new', 'as', 'extends',
           'implements'}
_CODE_RE = {}


def _code_re(kind, rust):
    if kind not in _CODE_RE:
        char = r"|'(?:\\.|[^'\\])'" if rust else r"|'(?:[^'\\]|\\.)*'?"
        _CODE_RE[kind, rust] = re.compile(
            rf'(?P<com>{_COMMENTS[kind]})|(?P<str>"(?:[^"\\]|\\.)*"?{char}|`[^`]*`?)'
            r'|(?P<attr>#!?\[[^\]]*\]|@[A-Za-z_][\w.]*)'
            r'|(?P<num>\b0x[\da-fA-F_]+\b|\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?(?:[iuf]\d+|usize|isize)?\b)'
            r'|(?P<word>[A-Za-z_$][\w$]*)|(?P<op>[-+*/%=<>!&|^~?:]+)|(?P<other>.)', re.S)
    return _CODE_RE[kind, rust]


def code_colors(lang, line):
    """Una línea de un bloque de código como [(texto, color, cursiva)], con los
    colores de moonfly. Sin lenguaje conocido va en blanco; `diff` colorea por
    el signo de cada línea y el shell se lee como un comando."""
    name = (lang or '').split()[0] if lang else ''
    white = MOONFLY['white']
    if name == 'diff':
        color = {'+': 'add', '-': 'del', '@': 'func'}.get(line[:1])
        return [(line, MOONFLY.get(color, white), False)]
    if LANGS.get(name) == 'shell' and name not in _KIND:
        if line.lstrip().startswith('#'):
            return [(line, MOONFLY['comment'], True)]
        roles = {'cmd': 'func', 'flag': 'number', 'str': 'string', 'var': 'macro', 'path': 'path', 'num': 'number',
                 'dim': 'op', 'arg': 'white'}
        return [(t, MOONFLY[roles[r]], False) for t, r in _shell(line[2:] if line.startswith('$ ') else line)]
    kind = _KIND.get(name)
    if not kind:
        return [(line, white, False)]
    keyed = name in ('json', 'jsonc', 'yaml', 'yml', 'toml')
    out, last = [], ''
    for m in _code_re(kind, name in ('rust', 'rs')).finditer(line):
        tok, role, rest = m.group(), m.lastgroup, line[m.end():]
        ahead = rest.lstrip()[:1]
        color, italic = white, False
        if role == 'com':
            color, italic = MOONFLY['comment'], True
        elif role == 'str':
            color = MOONFLY['prop'] if keyed and re.match(r'\s*:', rest) else MOONFLY['string']
        elif role == 'attr':
            color = MOONFLY['func']
        elif role == 'num':
            color = MOONFLY['number']
        elif role == 'op':
            color = MOONFLY['op']
        elif role == 'word':
            color = _word_color(tok, line[:m.start()], ahead, last, keyed and re.match(r'\s*[:=]', rest))
            last = tok
        out.append((tok, color, italic))
    return out


def _word_color(tok, before, ahead, last, key):
    """El color de una palabra de código: por lo que es y por lo que la rodea."""
    if key:
        return MOONFLY['prop']
    if tok in _CONSTS:
        return MOONFLY['const']
    if tok in _SELF:
        return MOONFLY['self']
    if tok in _C_KEYWORDS:
        return MOONFLY['keyword']
    if tok in _C_TYPES or last in _NAMING:
        return MOONFLY['type']
    if ahead == '!' and not before.endswith('!'):
        return MOONFLY['macro']
    if ahead == '(':
        return MOONFLY['func']
    if before.endswith('.'):
        return MOONFLY['prop']
    if tok[0].isupper():
        return MOONFLY['number'] if tok.isupper() and len(tok) > 1 else MOONFLY['type']
    return MOONFLY['white']


def _code_line(line, lang, mono):
    """Una línea de un bloque de código, resaltada. El fondo del bloque lo
    pinta la isla detrás de todas sus líneas."""
    body = ''.join(f'<span foreground="{color}"{' style="italic"' if italic else ''}>'
                   f'{html.escape(text, quote=False)}</span>' for text, color, italic in code_colors(lang, line))
    return f'{mono} {body} </span>'


RULE = re.compile(r'[\s|:-]+')
PIPE = re.compile(r'(?<!\\)\|(?=(?:[^`]*`[^`]*`)*[^`]*$)')
TAG = re.compile(r'<[^>]+>')


def plain(markup):
    """Un marcado de Pango sin sus etiquetas: solo su texto, todavía escapado."""
    return TAG.sub('', markup)


def _cells(line):
    """Las celdas de una fila. Un `|` escapado (\\|) o dentro de `código` no
    parte la celda."""
    body = line.strip()[1:]
    if body.endswith('|') and not body.endswith('\\|'):
        body = body[:-1]
    return [cell.strip().replace('\\|', '|') for cell in PIPE.split(body)]


def _rows(lines):
    """Las filas de una tabla, todas con las mismas celdas y sin la fila de
    guiones."""
    rows = [_cells(line) for line in lines if not RULE.fullmatch(line)]
    cols = max((len(row) for row in rows), default=0)
    return [row + [''] * (cols - len(row)) for row in rows]


def _grid(lines, inline, head):
    """Una tabla de markdown para dibujarla: (filas, alineación, con
    cabecera). Cada celda va ya en marcado de Pango, las de la cabecera en
    negrita y en el color de los títulos; la alineación es, de cada columna,
    0, .5 o 1 (izquierda, centro, derecha), según los `:` de la fila de
    guiones. Sin ninguna fila no hay tabla."""
    rows = _rows(lines)
    if not rows:
        return None
    rule = next((line for line in lines if RULE.fullmatch(line)), '')
    marks = [mark.strip() for mark in rule.strip().strip('|').split('|')]
    align = [.5 if mark.startswith(':') and mark.endswith(':') and len(mark) > 1 else float(mark.endswith(':'))
             for mark in marks]
    align = (align + [0.0] * len(rows[0]))[:len(rows[0])]
    headed = bool(rule) or len(rows) > 1
    cells = [[inline(cell) for cell in row] for row in rows]
    if headed:
        cells[0] = [f'<span foreground="{head}" weight="bold">{cell}</span>' for cell in cells[0]]
    return cells, align, headed


def _table(lines, mono):
    """Una tabla de markdown, con sus columnas alineadas en monoespaciado:
    sin la fila de guiones y con la cabecera en negrita."""
    rows = _rows(lines)
    if not rows:
        return []
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    out = []
    for n, row in enumerate(rows):
        text = html.escape('  '.join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip(), quote=False)
        out.append(f'{mono}<b>{text}</b></span>' if n == 0 and len(rows) > 1 else f'{mono}{text}</span>')
    return out


def _inline(line, mono, bold=None, rich=False):
    """Negritas, `código` y, si `rich`, cursivas y enlaces dentro de una línea.
    Lo que va entre acentos graves se queda como está: ahí un `**` o un `_`
    son del código."""
    # El código se aparta con una marca para que una negrita pueda envolverlo:
    # «**la carpeta de `main`**» tiene sus dos ** a cada lado del acento grave.
    spans = []

    def stash(m):
        spans.append(f'{mono}{html.escape(m[1], quote=False)}</span>')
        return f'{len(spans) - 1}'

    part = html.escape(CODE.sub(stash, re.sub('[]', '', line)), quote=False)
    if rich:
        part = LINK.sub(r'<u>\1</u>', part)
        part = ITALIC.sub(lambda m: f'<i>{m[1] or m[2]}</i>', part)
    tag = f'<span weight="bold" foreground="{bold}">\\1</span>' if bold else r'<b>\1</b>'
    part = BOLD.sub(tag, part)
    return re.sub('(\\d+)', lambda m: spans[int(m[1])], part)


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
