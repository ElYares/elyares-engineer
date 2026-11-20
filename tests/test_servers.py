import tempfile
import unittest
from unittest import mock

from elyares import servers

CONFIG = """
# mis servidores
Host github-work
    HostName github.com
    User git
    IdentityFile ~/.ssh/secreta

Host gitea-casa
    HostName 10.0.0.9
    User git

Host ionos-laravel-v2 ionos-laravel
    HostName 203.0.113.5
    User root

Host *
    ServerAliveInterval 30

Host ovh-*
    User admin

Host ovh-laravel-1
    HostName 198.51.100.7

Host -oProxyCommand=evil !nope pi.local
    HostName=192.0.2.1

Host ionos-laravel
    HostName 203.0.113.5

Match host algo
    HostName github.com

Host tras-match
    HostName 192.0.2.9
"""


class Leer(unittest.TestCase):
    def test_salen_solo_los_servidores_en_el_orden_del_archivo(self):
        self.assertEqual(servers.parse(CONFIG), ['ionos-laravel-v2', 'ionos-laravel', 'ovh-laravel-1', 'pi.local', 'tras-match'])

    def test_se_van_los_de_git_los_comodines_y_lo_que_parece_una_opcion(self):
        got = servers.parse(CONFIG)
        for bad in ('github-work', 'gitea-casa', '*', 'ovh-*', '-oProxyCommand=evil', '!nope'):
            self.assertNotIn(bad, got)

    def test_no_se_repiten_alias(self):
        self.assertEqual(servers.parse(CONFIG).count('ionos-laravel'), 1)

    def test_un_match_no_le_pone_su_hostname_al_host_anterior(self):
        self.assertIn('tras-match', servers.parse(CONFIG))

    def test_sin_archivo_la_lista_es_vacia(self):
        self.assertEqual(servers.hosts('/no/existe/config'), [])

    def test_hosts_lee_el_archivo_dado(self):
        with tempfile.NamedTemporaryFile('w', suffix='.conf') as fh:
            fh.write('Host uno\n  HostName a\n')
            fh.flush()
            self.assertEqual(servers.hosts(fh.name), ['uno'])


class Abrir(unittest.TestCase):
    def test_solo_abre_alias_que_estan_en_la_lista(self):
        with mock.patch.object(servers, 'hosts', return_value=['uno']), mock.patch('subprocess.Popen') as popen:
            self.assertFalse(servers.connect('otro'))
            self.assertFalse(servers.connect('-oProxyCommand=x'))
            popen.assert_not_called()

    def test_la_orden_va_en_su_scope_y_sin_shell(self):
        with mock.patch.object(servers, 'hosts', return_value=['uno']), mock.patch('subprocess.Popen') as popen:
            self.assertTrue(servers.connect('uno'))
            argv = popen.call_args.args[0]
            self.assertEqual(argv, ['systemd-run', '--user', '--scope', '--quiet', 'ghostty', '-e', 'ssh', 'uno'])
            self.assertNotIn('shell', popen.call_args.kwargs)

    def test_si_no_se_puede_lanzar_dice_que_no(self):
        with mock.patch.object(servers, 'hosts', return_value=['uno']), mock.patch('subprocess.Popen', side_effect=OSError):
            self.assertFalse(servers.connect('uno'))


if __name__ == '__main__':
    unittest.main()
