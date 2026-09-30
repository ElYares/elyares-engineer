"""Socket donde `elyares-hook` deja los eventos de Claude Code.

Una conexión = un mensaje JSON por línea. El hook no espera respuesta.
"""

import json
import os
import socket
import threading


def socket_path():
    base = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    return os.path.join(base, 'elyares.sock')


def serve(on_message):
    """Escucha en un hilo y llama a on_message(dict) por cada evento."""
    path = socket_path()
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    os.chmod(path, 0o600)
    srv.listen(32)

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                continue
            with conn:
                conn.settimeout(1)
                data = b''
                try:
                    while len(data) < 1 << 20:
                        b = conn.recv(65536)
                        if not b:
                            break
                        data += b
                except OSError:
                    pass
            for line in data.decode(errors='replace').splitlines():
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if isinstance(msg, dict):
                    on_message(msg)

    threading.Thread(target=loop, daemon=True, name='ipc').start()
    return path
