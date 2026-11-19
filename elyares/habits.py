"""Los hábitos: tu lista en un archivo `.md` y, aparte, qué días los hiciste.

La lista es de ti: `~/.config/elyares-engineer/habitos.md` (o la ruta del ajuste `habits_file`,
por ejemplo una nota de tu vault de Obsidian). Un hábito por línea, con guion, número o casilla:

    - Leer 20 min
    - [ ] Caminar
    1. Estirar

Lo demás (títulos, texto, comentarios) se ignora. Quitar una línea oculta el hábito sin perder su
historial. Qué días se hizo cada uno va en `~/.local/share/elyares-engineer/habits.json`, que sí
escribe la isla. Este módulo no importa gi: lo usa también `elyares-ctl`.
"""

import datetime
import json
import os
import re
import subprocess

_CONFIG = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), 'elyares-engineer')
_DATA = os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share'), 'elyares-engineer')
PATH = os.path.join(_DATA, 'habits.json')               # los días hechos
LIST_PATH = os.path.join(_CONFIG, 'habitos.md')         # tu lista por defecto
SETTINGS = os.path.join(_CONFIG, 'settings.json')       # el mismo que `settings.path()`
MAX_HABITS = 20
LINE = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]?\]\s+)?(\S.*?)\s*$')
BOX_ONLY = re.compile(r'^\[[ xX]?\]$')                  # «- [ ]» sin texto: una casilla vacía, no un hábito
TEMPLATE = """# Mis hábitos

<!-- Un hábito por línea, con guion: "- Leer 20 min". Quita una línea para dejar de verlo;
     su historial se conserva. Se lee solo: no hace falta reiniciar nada. -->
"""
_cache = {}
_error = {'text': ''}


def today():
    return datetime.date.today().isoformat()


def list_path():
    """El archivo de la lista: el del ajuste `habits_file` si hay, y si no el de siempre."""
    try:
        with open(SETTINGS) as fh:
            custom = json.load(fh).get('habits_file')
    except (OSError, ValueError, AttributeError):
        custom = ''
    return os.path.expanduser(custom) if isinstance(custom, str) and custom.strip() else LIST_PATH


def _line_name(line):
    """El hábito de una línea de la lista, o '' si la línea no es un hábito."""
    m = LINE.match(line)
    if not m:
        return ''
    name = ' '.join(m.group(1).split())[:40]
    return '' if BOX_ONLY.match(name) else name


def parse_list(text):
    """Los nombres de la lista: una línea de viñeta cada uno, sin repetidos, de a lo más 40 letras."""
    names, seen = [], set()
    for line in text.splitlines():
        name = _line_name(line)
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names[:MAX_HABITS]


def load():
    """Lo hecho: [{name, done}]; un archivo ausente o roto es una lista vacía."""
    try:
        with open(PATH) as fh:
            habits = json.load(fh).get('habits', [])
    except (OSError, ValueError, AttributeError):
        return []
    return [h for h in habits if isinstance(h, dict) and isinstance(h.get('name'), str)]


def save(habits):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + '.tmp'
    with open(tmp, 'w') as fh:
        json.dump({'habits': habits}, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def _first_text():
    """La lista de la primera vez: la plantilla con lo que ya había en el historial, si había."""
    return TEMPLATE + ''.join(f'- {h["name"]}\n' for h in load())


def _write(path, text):
    """Escribe la lista entera sin dejarla a medias (tmp + replace): puede ser una nota de tu vault."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(text)
    os.replace(tmp, path)


def _read_list():
    """El texto de la lista. Si no existe aún, el de la primera vez, sin escribir nada: esto se llama al
    pintar, y ahí ni se escribe ni se crea nada. Lanza OSError/UnicodeDecodeError si no se puede leer."""
    path = list_path()
    try:
        stamp = os.stat(path)
    except FileNotFoundError:
        return _first_text()
    key = (path, stamp.st_mtime_ns, stamp.st_size)
    if _cache.get('key') != key:
        with open(path, encoding='utf-8') as fh:
            _cache.update(key=key, text=fh.read())
    return _cache['text']


def _ensure_list():
    """La ruta de la lista, creándola con el texto de la primera vez si no existe (solo al escribir)."""
    path = list_path()
    if not os.path.exists(path):
        _write(path, _first_text())
    return path


def _why(exc):
    return f'No se pudo leer ni escribir {list_path()}: {getattr(exc, "strerror", None) or exc}'


def last_error():
    """Por qué la última lectura de la lista falló ('' si salió bien), para decirlo en el vacío."""
    return _error['text']


def names():
    """Los hábitos de tu lista; si el archivo no se puede leer, ninguno (y `last_error()` dice por qué)."""
    try:
        text = _read_list()
    except (OSError, UnicodeDecodeError) as exc:
        _error['text'] = _why(exc)
        return []
    _error['text'] = ''
    return parse_list(text)


def streak(done, now=None):
    """Días seguidos hasta hoy; si hoy aún no se marca, cuenta desde ayer (la racha sigue viva)."""
    days = set(done)
    day = datetime.date.fromisoformat(now) if now else datetime.date.today()
    if day.isoformat() not in days:
        day -= datetime.timedelta(days=1)
    count = 0
    while day.isoformat() in days:
        count += 1
        day -= datetime.timedelta(days=1)
    return count


def items(now=None):
    """[dict(name, done_today, streak)] en el orden de tu lista."""
    now = now or today()
    done = {}
    for h in load():                        # sin distinguir mayúsculas, como la lista
        done.setdefault(h['name'].casefold(), []).extend(h.get('done', []))
    return [dict(name=n, done_today=now in done.get(n.casefold(), []), streak=streak(done.get(n.casefold(), []), now))
            for n in names()]


def add(name):
    """(ok, texto). Agrega una línea al final de tu lista. Vacío, repetido o de más no se agrega."""
    name = ' '.join(str(name).split())[:40]
    if not name:
        return False, 'Falta el nombre del hábito'
    current = names()
    if last_error():
        return False, last_error()
    if any(n.lower() == name.lower() for n in current):
        return False, f'Ya existe «{name}»'
    if len(current) >= MAX_HABITS:
        return False, f'Máximo {MAX_HABITS} hábitos'
    try:
        text = _read_list()
        _write(list_path(), text + ('' if text.endswith('\n') else '\n') + f'- {name}\n')
    except (OSError, UnicodeDecodeError) as exc:
        return False, _why(exc)
    return True, f'Agregado «{name}»'


def remove(name):
    """Quita la línea de tu lista; el historial de ese hábito se queda."""
    wanted = name.strip().lower()
    try:
        lines = _read_list().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return False, _why(exc)
    kept, found = [], False
    for line in lines:
        if _line_name(line).lower() == wanted and wanted:
            found = True
            continue
        kept.append(line)
    if not found:
        return False, f'No existe «{name}»'
    try:
        _write(list_path(), '\n'.join(kept) + '\n')
    except OSError as exc:
        return False, _why(exc)
    return True, f'Quitado «{name}»'


def toggle(name, now=None):
    """Marca o desmarca el hábito de hoy. Devuelve si quedó hecho."""
    now = now or today()
    habits = load()
    entry = next((h for h in habits if h['name'].casefold() == name.casefold()), None)
    if entry is None:
        entry = dict(name=name, done=[])
        habits.append(entry)
    done = [d for d in entry.get('done', []) if d != now]
    if len(done) == len(entry.get('done', [])):
        done.append(now)
    entry['done'] = sorted(done)[-400:]
    save(habits)
    return now in entry['done']


def edit():
    """Abre tu lista en el editor de siempre (el de omarchy, o el de la sesión).
    Devuelve (ok, ruta): ok es False si no se pudo crear la lista o no hay editor que abrirla."""
    try:
        path = _ensure_list()
    except OSError:
        return False, list_path()
    for cmd in (['omarchy-launch-editor', path], ['xdg-open', path]):
        try:
            subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, path
        except OSError:
            continue
    return False, path
