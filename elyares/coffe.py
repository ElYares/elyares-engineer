"""Sigue al pomodoro de `coffe` para no interrumpir en mitad de uno.

`coffe bar --watch` es lo mismo que lee Waybar: una línea de JSON por segundo
mientras el reloj corre, con la fase en `class`. De ahí salen dos cosas:

    foco    mientras hay pomodoro, la isla solo se abre sola para un permiso
    avisos  al empezar el descanso y al acabarse

Sin `coffe` instalado, o con su reloj apagado, no hace nada.
"""

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


def _notice(message):
    return {'event': 'alert', 'session_id': 'coffe', 'name': 'coffe', 'message': message,
            'tone': 'ok', 'ttl': NOTICE_SECS}


class Tracker:
    def __init__(self):
        self.phase = None

    def step(self, line):
        """Una línea de `coffe bar` -> los mensajes que tocan, solo al cambiar de fase."""
        try:
            data = json.loads(line)
        except ValueError:
            return []
        phase = data.get('class') if isinstance(data, dict) else None
        if not phase or phase == self.phase:
            return []
        before, self.phase = self.phase, phase
        msgs = [{'event': 'source', 'name': 'coffe', 'ok': phase != 'off',
                 'note': PHASE_TEXT.get(phase, '')}]
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
        emit({'event': 'source', 'name': 'coffe', 'ok': False, 'note': 'falta coffe'})
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
