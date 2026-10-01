"""Lo que la mascota hace fuera de sí misma: saltar al pane y leer No Molestar."""

import shutil
import subprocess

TERM_CLASS = 'com.mitchellh.ghostty'


def _run(*cmd, timeout=1.0):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def _real_clients(tmux):
    """Clientes que son una terminal de verdad: [(actividad, tty, sesión)].

    Quedan fuera los anidados del panel SSH y de la terminal flotante: un
    `tmux attach` dentro de un popup (sesión oculta _*) o de un pane fijo (su
    tty es el de un pane). Mover uno de esos a la sesión que lo contiene deja
    a tmux mostrándose a sí mismo y la ventana se encoge hasta 3x1 (pasó el
    2026-09-30 con el panel SSH fijo).
    """
    panes = set(_run(*tmux, 'list-panes', '-a', '-F', '#{pane_tty}').split())
    out = _run(*tmux, 'list-clients', '-F', '#{client_activity}\t#{client_tty}\t#{client_session}')
    clients = []
    for line in out.splitlines():
        act, _, rest = line.partition('\t')
        tty, _, sess = rest.partition('\t')
        if sess.startswith('_') or tty in panes:
            continue
        clients.append((int(act) if act.isdigit() else 0, tty, sess))
    return clients


def jump(session):
    """Enfoca ghostty y lleva tmux a la sesión/ventana/pane de Claude.

    Es la misma lógica que jump() de claude-notify.sh. TMUX trae
    "socket,pid,índice": el daemon corre fuera de tmux y necesita el socket.
    """
    _run('hyprctl', 'dispatch', 'focuswindow', f'class:{TERM_CLASS}')
    pane = session.pane if session else ''
    sock = (session.tmux or '').split(',')[0] if session else ''
    if not pane or not shutil.which('tmux'):
        return
    tmux = ['tmux', '-S', sock] if sock else ['tmux']
    sess = _run(*tmux, 'display-message', '-p', '-t', pane, '#{session_name}')
    if not sess:
        return
    clients = _real_clients(tmux)
    if not any(s == sess for _, _, s in clients):
        # Ningún cliente en esa sesión: mueve el que se usó más recientemente.
        if clients:
            _run(*tmux, 'switch-client', '-c', max(clients)[1], '-t', sess)
    _run(*tmux, 'select-window', '-t', pane)
    _run(*tmux, 'select-pane', '-t', pane)


def live_panes(socks):
    """Panes de tmux que existen, por socket: {socket: {(pid del servidor, pane)}}.

    Un servidor que ya no corre sale sin panes. Un socket por el que no se
    pudo preguntar no sale. El pid distingue a un servidor nuevo en el mismo
    socket: los ids de pane empiezan otra vez en %0 y coincidirían con los de
    las sesiones viejas.
    """
    live = {}
    if not shutil.which('tmux'):
        return live
    for sock in socks:
        try:
            r = subprocess.run(['tmux', '-S', sock, 'list-panes', '-a', '-F', '#{pid} #{pane_id}'],
                               capture_output=True, text=True, timeout=1.0)
        except (OSError, subprocess.SubprocessError):
            continue
        # tmux contesta con error cuando no hay servidor en ese socket.
        lines = r.stdout.splitlines() if r.returncode == 0 else []
        live[sock] = {tuple(line.split()) for line in lines}
    return live


def do_not_disturb():
    if not shutil.which('swaync-client'):
        return False
    return _run('swaync-client', '-D', '-sw') == 'true'
