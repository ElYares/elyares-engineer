"""Lo que elyares-engineer hace fuera de sí mismo: saltar al pane (o a la
sesión de tmux de un proyecto), correr el botón de una alerta y leer No
Molestar."""

import os
import shlex
import shutil
import subprocess

from . import state

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

    Una alerta no tiene pane: trae una URL y el clic la abre. Una sesión del
    chat de la isla tampoco (su Claude no corre en una terminal): va a la
    sesión de tmux de su proyecto.
    """
    if session and session.url:
        _run('xdg-open', session.url, timeout=5.0)
        return
    _run('hyprctl', 'dispatch', 'focuswindow', f'class:{TERM_CLASS}')
    pane = session.pane if session else ''
    sock = (session.tmux or '').split(',')[0] if session else ''
    if not shutil.which('tmux'):
        return
    if not pane:
        if session and getattr(session, 'cwd', ''):
            jump_project(session.cwd)
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


def jump_project(cwd):
    """Lleva tmux a la sesión del proyecto de esa carpeta: la que se abrió
    ahí. Si no hay, la crea con el nombre del proyecto. Mueve el cliente que
    se usó más recientemente; sin ninguna terminal con tmux, abre una."""
    root = state.project_root(cwd)
    tmux = ['tmux']
    sessions = [line.partition('\t')[::2] for line in
                _run(*tmux, 'list-sessions', '-F', '#{session_name}\t#{session_path}').splitlines()]
    name = next((name for name, path in sessions
                 if not name.startswith('_') and (path.rstrip('/') or '/') == root), '')
    if not name:
        # tmux no admite puntos ni dos puntos en el nombre de una sesión.
        name = (os.path.basename(root) or 'proyecto').replace('.', '_').replace(':', '_')
        if any(name == known for known, _ in sessions):
            name += '-isla'               # otra carpeta ya usa ese nombre
        _run(*tmux, 'new-session', '-d', '-s', name, '-c', root)
    clients = _real_clients(tmux)
    if any(sess == name for _, _, sess in clients):
        return
    if clients:
        _run(*tmux, 'switch-client', '-c', max(clients)[1], '-t', f'={name}')
    else:
        run({'cmd': ['tmux', 'attach', '-t', f'={name}'], 'term': True, 'label': name})


def run(action):
    """Lo que hace el botón de una alerta: abre su URL o corre su comando.

    Con `term` el comando corre en una terminal nueva, donde se ve lo que
    imprime; con `hold` la terminal espera una tecla al terminar. Sin `term`
    corre suelto y en silencio.
    """
    if action.get('url'):
        _run('xdg-open', action['url'], timeout=5.0)
        return
    cmd = action.get('cmd') or []
    if not cmd:
        return
    if action.get('term'):
        script = shlex.join(cmd)
        if action.get('hold'):
            # El trap deja que Ctrl-C corte el comando sin llevarse la terminal.
            script = f"trap : INT; {script}; echo; read -rsn1 -p 'Pulsa una tecla para cerrar'"
        cmd = ['xdg-terminal-exec', f'--title={action.get("label", "")}', '-e',
               'bash', '-c', script]
        if shutil.which('uwsm-app'):
            cmd = ['uwsm-app', '--'] + cmd
    try:
        # Se espera para no dejar un zombi: quien llama ya está en su propio hilo.
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True).wait()
    except OSError:
        pass


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


def proc_alive(proc):
    """¿Sigue ahí el proceso "pid:arranque" que anotó el hook? Con el pid solo
    no basta: el sistema lo vuelve a usar para otro proceso."""
    pid, _, start = proc.partition(':')
    try:
        with open(f'/proc/{int(pid)}/stat') as f:
            return f.read().rsplit(')', 1)[1].split()[19] == start
    except (OSError, ValueError, IndexError):
        return False


def do_not_disturb():
    if not shutil.which('swaync-client'):
        return False
    return _run('swaync-client', '-D', '-sw') == 'true'
