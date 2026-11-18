"""Los hábitos: una casilla por día con su racha, en un archivo propio.

`~/.local/share/elyares-engineer/habits.json` guarda `{"habits": [{"name": ..., "done": ["AAAA-MM-DD", ...]}]}`.
No toca nada de `coffe`. La isla los muestra y marca el de hoy; se agregan y quitan con
`elyares-ctl habit add|rm|list`. Este módulo no importa gi: lo usa también `elyares-ctl`.
"""

import datetime
import json
import os

PATH = os.path.expanduser('~/.local/share/elyares-engineer/habits.json')
MAX_HABITS = 12


def today():
    return datetime.date.today().isoformat()


def load():
    """La lista guardada; un archivo ausente o roto es una lista vacía."""
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
    """[dict(name, done_today, streak)] en el orden en que se agregaron."""
    now = now or today()
    return [dict(name=h['name'], done_today=now in h.get('done', []), streak=streak(h.get('done', []), now))
            for h in load()]


def add(name):
    """(ok, texto). Un nombre vacío, repetido o de más de MAX_HABITS no se agrega."""
    name = ' '.join(str(name).split())[:40]
    habits = load()
    if not name:
        return False, 'Falta el nombre del hábito'
    if any(h['name'].lower() == name.lower() for h in habits):
        return False, f'Ya existe «{name}»'
    if len(habits) >= MAX_HABITS:
        return False, f'Máximo {MAX_HABITS} hábitos'
    save(habits + [dict(name=name, done=[])])
    return True, f'Agregado «{name}»'


def remove(name):
    habits = load()
    kept = [h for h in habits if h['name'].lower() != name.strip().lower()]
    if len(kept) == len(habits):
        return False, f'No existe «{name}»'
    save(kept)
    return True, f'Quitado «{name}»'


def toggle(name, now=None):
    """Marca o desmarca el hábito de hoy. Devuelve si quedó hecho."""
    now = now or today()
    habits = load()
    for h in habits:
        if h['name'] == name:
            done = [d for d in h.get('done', []) if d != now]
            if len(done) == len(h.get('done', [])):
                done.append(now)
            h['done'] = sorted(done)[-400:]
            save(habits)
            return now in h['done']
    return False
