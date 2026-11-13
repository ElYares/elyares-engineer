"""El aviso al celular: cuándo se manda, qué lleva y cuándo se calla."""

import os
import tempfile
import threading
import unittest
from unittest import mock

from elyares import remote
from elyares.state import Session

URL = 'https://hooks.slack.com/services/T/B/x'


def pager(sent):
    # Los hilos de envío son reales; `send` apunta a una lista, no a internet.
    return remote.Pager(get_url=lambda: URL, send=lambda url, text: sent.append((url, text)), delay=120)


def sesion(state, detail='', cwd='/tmp/proy'):
    return Session('s1', cwd=cwd, state=state, detail=detail)


class Aviso(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.p = pager(self.sent)

    def check(self, s, now, dnd=False):
        out = self.p.check({'s1': s} if s else {}, now, dnd)
        for t in threading.enumerate():
            if t.daemon and t is not threading.current_thread():
                t.join(1)
        return out

    def test_no_avisa_antes_del_retraso(self):
        s = sesion('permission')
        self.assertEqual(self.check(s, 0), [])
        self.assertEqual(self.check(s, 119), [])
        self.assertEqual(self.sent, [])

    def test_avisa_una_vez_pasado_el_retraso(self):
        s = sesion('done', 'Listo en 3 min')
        self.check(s, 0)
        self.assertEqual(self.check(s, 121), ['*proy* terminó: Listo en 3 min'])
        self.assertEqual(self.check(s, 400), [])
        self.assertEqual(self.sent, [(URL, '*proy* terminó: Listo en 3 min')])

    def test_si_contestas_antes_no_avisa(self):
        self.check(sesion('permission'), 0)
        self.check(sesion('working'), 60)
        self.assertEqual(self.check(sesion('working'), 200), [])
        self.assertEqual(self.sent, [])

    def test_el_permiso_no_lleva_el_comando(self):
        s = sesion('permission', 'Bash: rm -rf /secreto')
        self.check(s, 0)
        self.assertEqual(self.check(s, 130), ['*proy* pide permiso'])

    def test_no_molestar_pospone_el_aviso(self):
        s = sesion('waiting', 'Esperando tu respuesta')
        self.check(s, 0)
        self.assertEqual(self.check(s, 130, dnd=True), [])
        self.assertEqual(self.check(s, 140), ['*proy* te espera: Esperando tu respuesta'])

    def test_otro_turno_vuelve_a_avisar(self):
        s = sesion('done')
        self.check(s, 0)
        self.check(s, 130)
        self.check(sesion('working'), 140)
        self.check(s, 150)
        self.assertEqual(self.check(s, 280), ['*proy* terminó'])

    def test_una_alerta_no_avisa(self):
        s = Session('a1', name='devherd', state='done')
        self.check(s, 0)
        self.assertEqual(self.check(s, 500), [])

    def test_sin_webhook_no_manda(self):
        p = remote.Pager(get_url=lambda: '', send=lambda *a: self.sent.append(a), delay=0)
        s = sesion('done')
        p.check({'s1': s}, 0)
        self.assertEqual(p.check({'s1': s}, 1), [])
        self.assertEqual(self.sent, [])

    def test_escapa_el_nombre(self):
        self.assertEqual(remote.message(sesion('done', cwd='/tmp/a<b>&c')), '*a&lt;b&gt;&amp;c* terminó')


class Webhook(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        env = {'XDG_CONFIG_HOME': self.dir.name}
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop(remote.ENV, None)
        os.makedirs(os.path.dirname(remote.path()))

    def escribe(self, text, mode):
        with open(remote.path(), 'w') as f:
            f.write(text)
        os.chmod(remote.path(), mode)

    def test_sin_archivo(self):
        self.assertEqual(remote.webhook(), '')

    def test_lee_el_archivo_modo_600(self):
        self.escribe(URL + '\n', 0o600)
        self.assertEqual(remote.webhook(), URL)

    def test_rechaza_un_archivo_legible_por_otros(self):
        self.escribe(URL, 0o644)
        self.assertEqual(remote.webhook(), '')

    def test_rechaza_una_url_que_no_es_de_slack(self):
        self.escribe('https://ejemplo.com/hook', 0o600)
        self.assertEqual(remote.webhook(), '')

    def test_la_variable_de_entorno_gana(self):
        self.escribe('https://hooks.slack.com/services/otro', 0o600)
        with mock.patch.dict(os.environ, {remote.ENV: URL}):
            self.assertEqual(remote.webhook(), URL)


if __name__ == '__main__':
    unittest.main()
