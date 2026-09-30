"""Hyprland por sus sockets, sin lanzar procesos de hyprctl.

.socket.sock  pedidos (monitores, posición del cursor)
.socket2.sock eventos en vivo (cambio de monitor enfocado)
"""

import json
import os
import socket
import threading
import time


def _path(name):
    base = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    sig = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    return os.path.join(base, 'hypr', sig, name)


def request(cmd):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        s.connect(_path('.socket.sock'))
        s.sendall(cmd.encode())
        chunks = []
        while True:
            b = s.recv(65536)
            if not b:
                break
            chunks.append(b)
    return b''.join(chunks).decode(errors='replace')


def monitors():
    try:
        return json.loads(request('j/monitors'))
    except (OSError, ValueError):
        return []


def focused_monitor():
    for m in monitors():
        if m.get('focused'):
            return m
    return None


def cursor_pos():
    try:
        x, y = request('cursorpos').split(',')
        return float(x), float(y)
    except (OSError, ValueError):
        return None


def listen(on_focused_monitor):
    """Llama a on_focused_monitor(nombre) desde un hilo cada vez que cambia el foco."""
    def loop():
        while True:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.connect(_path('.socket2.sock'))
                    buf = b''
                    while True:
                        b = s.recv(4096)
                        if not b:
                            break
                        buf += b
                        while b'\n' in buf:
                            line, buf = buf.split(b'\n', 1)
                            ev, _, data = line.decode(errors='replace').partition('>>')
                            if ev == 'focusedmon':
                                on_focused_monitor(data.split(',')[0])
            except OSError:
                pass
            time.sleep(2)  # Hyprland se reinició o aún no arranca

    threading.Thread(target=loop, daemon=True, name='hypr-events').start()
