"""Socket donde `elyares-hook` deja los eventos de Claude Code.

Una conexión = un mensaje JSON por línea. Casi todos los eventos son de una
sola vía: el hook escribe y cierra. Los que traen `"reply": true` (el permiso)
dejan la conexión abierta hasta que la isla contesta con una línea JSON.

Una orden de `elyares-ctl` (`control`) llega además con `peer`: quién la mandó,
como los nombres del proceso al otro lado y de sus padres. La isla lo mira
antes de dejar que una orden conteste un permiso.
"""

import json
import os
import socket
import struct
import threading
import time


def socket_path():
    base = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    return os.path.join(base, 'elyares.sock')


def peer_names(conn, depth=8):
    """Los nombres (`comm`) del proceso al otro lado del socket y de sus padres,
    del más cercano al más lejano. [] si ya no está o no se pudo saber."""
    try:
        cred = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
        pid = struct.unpack('3i', cred)[0]
    except OSError:
        return []
    names = []
    for _ in range(depth):
        if pid <= 1:
            break
        try:
            with open(f'/proc/{pid}/comm') as f:
                names.append(f.read().strip())
            with open(f'/proc/{pid}/stat') as f:
                pid = int(f.read().rsplit(')', 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return names


class Request:
    """Un hook esperando respuesta. Se contesta una sola vez."""

    def __init__(self, conn, on_gone):
        self.conn = conn
        self.done = False
        self.born = time.time()
        self._lock = threading.Lock()
        self._on_gone = on_gone

    def start(self):
        # Después de entregar el mensaje: así on_gone nunca llega antes.
        threading.Thread(target=self._watch, daemon=True, name='ipc-wait').start()

    def reply(self, answer):
        """answer: dict que el hook imprime, o None para no decidir."""
        with self._lock:
            if self.done:
                return
            self.done = True
        try:
            self.conn.sendall((json.dumps(answer or {}) + '\n').encode())
        except OSError:
            pass
        self._close()

    def _watch(self):
        # El hook no manda nada más: recv solo regresa cuando se va (Claude lo
        # mata al contestar No en la terminal, o se le acabó el timeout) o
        # cuando reply() cierra el socket.
        try:
            self.conn.settimeout(None)
            self.conn.recv(1)
        except OSError:
            pass
        with self._lock:
            if self.done:
                return
            self.done = True
        self._close()
        self._on_gone(self)

    def _close(self):
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.conn.close()


def serve(on_message, on_gone):
    """Escucha en un hilo y llama a on_message(dict, Request | None) por evento.

    on_gone(Request) avisa que un hook que esperaba respuesta se fue sin ella.
    """
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
            conn.settimeout(1)
            data = b''
            try:
                while len(data) < 1 << 20:
                    b = conn.recv(65536)
                    if not b:
                        break
                    data += b
                    # Un mensaje por conexión: el que espera respuesta no
                    # cierra su lado, así que no llega EOF.
                    if b'\n' in b:
                        break
            except OSError:
                pass
            req = None
            for line in data.decode(errors='replace').splitlines():
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                if 'control' in msg:
                    # Aquí y no después: quien lo mandó puede irse enseguida.
                    msg['peer'] = peer_names(conn)
                if msg.get('reply') and req is None:
                    req = Request(conn, on_gone)
                    on_message(msg, req)
                    req.start()
                else:
                    on_message(msg, None)
            if req is None:
                conn.close()

    threading.Thread(target=loop, daemon=True, name='ipc').start()
    return path
