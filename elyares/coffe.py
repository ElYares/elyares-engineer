"""Sigue al pomodoro de `coffe` para no interrumpir en mitad de uno.

`coffe bar --watch` es lo mismo que lee Waybar: una línea de JSON por segundo
mientras el reloj corre, con la fase en `class`. De ahí salen dos cosas:

    foco    mientras hay pomodoro, la isla solo se abre sola para un permiso
    avisos  al empezar el descanso y al acabarse

Además le cuenta a la isla, para la burbuja de su pastilla, lo que dice el
reloj: cuánto queda, la tarea en curso y cómo va el día. Si el reloj no
responde, la causa.

Sin `coffe` instalado, o con su reloj apagado, no hace nada.
"""

import html
import json
import shutil
import subprocess
import threading
import time

RETRY_SECS = 5
NOTICE_SECS = 20          # lo que dura en la isla el aviso de cambio de fase
FOCUS = ('focus', 'overlearning')
BREAK = ('break', 'break-long')
PHASE_TEXT = {'idle': 'parado', 'focus': 'en foco', 'overlearning': 'en foco',
              'break': 'descanso', 'break-long': 'descanso largo'}


def _tip(data):
    """Lo que dice el reloj, para la burbuja. El `tooltip` de `coffe bar` trae
    bloques separados por una línea vacía: el reloj ("Pomodoro · 12:40"), la
    tarea en curso (título y proyecto) si la hay, y cómo va el día."""
    blocks = [[html.unescape(line) for line in block.split('\n') if line]
              for block in (data.get('tooltip') or '').split('\n\n')]
    blocks = [b for b in blocks if b]
    if not blocks:
        return []
    tip = []
    clock = blocks[0][0].partition(' · ')[2].split(' ')[0]
    if clock:
        tip.append(f'Quedan {clock}')
    if len(blocks) > 2:
        tip.append(f'Tarea: {blocks[1][0]}')
    if len(blocks) > 1:
        tip.append(' · '.join(blocks[-1][:2]))
    return tip


def _notice(message):
    return {'event': 'alert', 'session_id': 'coffe', 'name': 'coffe', 'message': message,
            'tone': 'ok', 'ttl': NOTICE_SECS}


class Tracker:
    def __init__(self):
        self.phase = None
        self.tip = None

    def step(self, line):
        """Una línea de `coffe bar` -> los mensajes que tocan. Los avisos, solo
        al cambiar de fase; lo que dice la burbuja, cada vez que cambia."""
        try:
            data = json.loads(line)
        except ValueError:
            return []
        phase = data.get('class') if isinstance(data, dict) else None
        if not phase:
            return []
        tip = _tip(data) if phase != 'off' else []
        if phase == self.phase and tip == self.tip:
            return []
        before, self.phase, self.tip = self.phase, phase, tip
        source = {'event': 'source', 'name': 'coffe', 'ok': phase != 'off',
                  'note': PHASE_TEXT.get(phase, ''), 'tip': tip}
        if phase == 'off':
            # Con el reloj caído, `coffe bar` deja el error en el tooltip.
            why = html.unescape((data.get('tooltip') or '').split('\n')[0])
            source.update(why=why or 'El reloj de coffe no responde',
                          fix='Arráncalo con: systemctl --user start coffe')
        msgs = [source]
        if phase == before:
            return msgs
        if (phase in FOCUS) != (before in FOCUS):
            msgs.append({'event': 'focus', 'on': phase in FOCUS})
        # La primera línea solo dice cómo estaba: no es un cambio que anunciar.
        if before is None:
            return msgs
        if phase in BREAK and before in FOCUS:
            clock = (data.get('tooltip') or '').split('\n')[0]
            msgs.append(_notice(clock or 'Descanso'))
        elif before in BREAK and phase not in BREAK:
            msgs.append(_notice('Se acabó el descanso'))
        return msgs


def watch(emit):
    """Lee `coffe bar --watch` en un hilo y llama a emit(mensaje) en cada cambio."""
    if not shutil.which('coffe'):
        emit({'event': 'source', 'name': 'coffe', 'ok': False, 'note': 'falta coffe',
              'why': 'No está instalado coffe, el pomodoro',
              'fix': 'Instálalo y reinicia elyares-engineer'})
        return

    def loop():
        tracker = Tracker()
        while True:
            try:
                proc = subprocess.Popen(['coffe', 'bar', '--watch'], stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True)
                for line in proc.stdout:
                    for msg in tracker.step(line):
                        emit(msg)
                proc.wait()
            except (OSError, ValueError):
                pass
            # Se cortó: sin reloj no hay foco que respetar.
            for msg in tracker.step('{"class": "off"}'):
                emit(msg)
            time.sleep(RETRY_SECS)

    threading.Thread(target=loop, daemon=True, name='coffe').start()
