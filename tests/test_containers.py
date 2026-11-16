import json
import unittest

from elyares import containers as c
from elyares import containerview

PS = '\n'.join(json.dumps(row) for row in [
    {'ID': 'a1', 'Names': 'aang_web', 'State': 'running', 'Status': 'Up 4 hours',
     'Labels': 'com.docker.compose.service=web,com.docker.compose.project.working_dir=/w/aang,'
               'com.docker.compose.project.config_files=/w/aang/a.yaml,/w/aang/b.yaml'},
    {'ID': 'a2', 'Names': 'aang_db', 'State': 'exited', 'Status': 'Exited (255) 1 hour ago',
     'Labels': 'com.docker.compose.service=db,com.docker.compose.project.working_dir=/w/aang'},
    {'ID': 'b1', 'Names': 'lab_api', 'State': 'exited', 'Status': 'Exited (0) 2 days ago',
     'Labels': 'com.docker.compose.project.working_dir=/w/lab'},
]) + '\nno es json\n'
STATS = json.dumps({'Name': 'aang_web', 'CPUPerc': '4.50%', 'MemUsage': '11.2MiB / 31GiB',
                    'MemPerc': '0.04%', 'NetIO': '2.16MB / 378B'})


class ParseTest(unittest.TestCase):
    def test_ps_labels_with_commas(self):
        rows = c.parse_ps(PS)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['service'], 'web')
        self.assertEqual(rows[0]['path'], '/w/aang')

    def test_stats(self):
        s = c.parse_stats(STATS)['aang_web']
        self.assertAlmostEqual(s['cpu'], 4.5)
        self.assertAlmostEqual(s['mem'], 11.2 * 1024 ** 2)
        self.assertAlmostEqual(s['mem_limit'], 31 * 1024 ** 3)
        self.assertEqual(s['net_tx'], 378)

    def test_to_bytes_garbage(self):
        self.assertEqual(c.to_bytes('nada'), 0.0)
        self.assertEqual(c.to_bytes(''), 0.0)


class ColumnsTest(unittest.TestCase):
    def test_span(self):
        self.assertEqual(c.span('Up 8 hours (healthy)'), '8 h')
        self.assertEqual(c.span('About an hour ago'), '1 h')
        self.assertEqual(c.span('4 minutes ago'), '4 min')
        self.assertEqual(c.span('nada'), '')

    def test_ports_without_ipv6_duplicates(self):
        self.assertEqual(c.parse_ports('0.0.0.0:50515->80/tcp, [::]:50515->80/tcp, 9000/tcp'), ['50515→80'])
        self.assertEqual(c.parse_ports(''), [])

    def test_kind_and_state_text(self):
        up = dict(state='running', status='Up 3 hours', health='')
        bad = dict(state='exited', status='Exited (1) 2 hours ago')
        off = dict(state='exited', status='Exited (0) 2 hours ago')
        self.assertEqual([containerview.kind(b) for b in (up, bad, off)], ['up', 'failed', 'stopped'])
        self.assertEqual([containerview.state_text(b) for b in (up, bad, off)], ['Arriba 3 h', 'Falló', 'Parado'])


class IconsTest(unittest.TestCase):
    def test_find_by_image_or_service(self):
        from elyares import icons
        self.assertEqual(icons.find('postgres:16-alpine'), ('devicon', 'postgresql'))
        self.assertEqual(icons.find('opensearchproject/opensearch:2.11'), ('dashboard', 'opensearch'))
        self.assertEqual(icons.find('docker.io/library/rust:1'), ('devicon', 'rust'))
        self.assertEqual(icons.find('', 'redis'), ('devicon', 'redis'))
        self.assertIsNone(icons.find('miapp:latest', 'web'))

    def test_every_mapped_file_exists(self):
        import os
        from elyares import icons
        for _key, folder, stem in icons.BRANDS:
            self.assertTrue(os.path.exists(os.path.join(icons.DIR, folder, f'{stem}.svg')), (folder, stem))


class ResponsiveTest(unittest.TestCase):
    def test_modes_and_hysteresis(self):
        from elyares import responsive as r
        self.assertEqual([r.mode(w) for w in (400, 700, 1300)], [r.COMPACT, r.MEDIUM, r.WIDE])
        self.assertEqual(r.mode(570, r.COMPACT), r.COMPACT)      # a 10 px del corte: no cambia
        self.assertEqual(r.mode(600, r.COMPACT), r.MEDIUM)
        self.assertEqual(r.mode(1140, r.WIDE), r.WIDE)
        self.assertEqual(r.mode(700, scale=1.5), r.COMPACT)      # vista cansada: 700/1.5 = 466

    def test_subtitle_carries_hidden_columns(self):
        box = dict(name='n', service='s', image='nginx:1', state='running', status='Up 3 hours', ports=['80→80'], created='2 h')
        self.assertEqual(containerview.ContainersPanel._subtitle(box, ('ports', 'created')), 'nginx:1 · 80→80 · hace 2 h')
        self.assertEqual(containerview.ContainersPanel._subtitle(box, ()), 'nginx:1')


class WholeAppTest(unittest.TestCase):
    def test_signal_follows_theme_brightness(self):
        from elyares import themes
        old = themes.current
        try:
            themes.use('omarchy')
            dark = themes.signal()
            themes.use('papel')
            self.assertNotEqual(dark, themes.signal())
            self.assertEqual(themes.signal()[0], '#166534')
        finally:
            themes.use(old)

    def test_nav_overflow_only_names_real_views(self):
        from elyares import windowframe as wf, responsive as r
        keys = {k for k, _t in wf.VIEWS}
        for spill in wf.NAV_MORE.values():
            self.assertTrue(set(spill) <= keys)
        self.assertEqual(r.mode(1100, edges=wf.NAV_EDGES), r.MEDIUM)
        self.assertEqual(r.mode(900, edges=wf.NAV_EDGES), r.COMPACT)


class GroupTest(unittest.TestCase):
    def setUp(self):
        registered = [dict(name='aang', path='/w/aang'), dict(name='vacio', path='/w/vacio')]
        self.projects = c.group(registered, c.parse_ps(PS), c.parse_stats(STATS))

    def test_up_first_and_empty_project_listed(self):
        self.assertEqual([p['name'] for p in self.projects], ['aang', 'lab', 'vacio'])
        empty = self.projects[2]
        self.assertEqual((empty['running'], empty['total']), (0, 0))

    def test_unregistered_project_by_folder(self):
        lab = self.projects[1]
        self.assertEqual(lab['path'], '/w/lab')

    def test_running_sorted_first_and_sums(self):
        aang = self.projects[0]
        self.assertEqual([b['name'] for b in aang['containers']], ['aang_web', 'aang_db'])
        self.assertEqual((aang['running'], aang['total']), (1, 2))
        self.assertAlmostEqual(aang['cpu'], 4.5)

    def test_totals(self):
        t = c.totals(self.projects, 100.0)
        self.assertEqual((t['up'], t['total']), (1, 3))
        self.assertAlmostEqual(t['cpu'], 4.5)


class ViewTest(unittest.TestCase):
    def test_dot(self):
        self.assertEqual(containerview.dot(dict(state='running', status='Up', health='')), containerview.GREEN)
        self.assertEqual(containerview.dot(dict(state='running', status='Up', health='unhealthy')), containerview.RED)
        self.assertEqual(containerview.dot(dict(state='exited', status='Exited (0) 1h')), containerview.GREY)
        self.assertEqual(containerview.dot(dict(state='exited', status='Exited (255) 1h')), containerview.RED)

    def test_fmt_bytes(self):
        self.assertEqual(c.fmt_bytes(512), '512 B')
        self.assertEqual(c.fmt_bytes(1536), '1.5 KB')


class ActTest(unittest.TestCase):
    def test_unknown_order(self):
        self.assertFalse(c.act('borrar', 'x')[0])


if __name__ == '__main__':
    unittest.main()


class SafeCommandsTest(unittest.TestCase):
    """Parar nunca borra: ni `down`, ni `rm`, ni `-v` (volúmenes con la base de datos)."""

    def test_stop_commands_do_not_delete(self):
        from unittest import mock
        seen = []
        with mock.patch.object(c, '_run', side_effect=lambda cmd, timeout=0: seen.append(cmd) or (True, '')), \
                mock.patch.object(c, '_stream', side_effect=lambda cmd, on_line, timeout=0: seen.append(cmd) or (True, '')):
            for order in ('up', 'stop-project', 'stop', 'start'):
                c.act(order, '/x')
        self.assertEqual(len(seen), 4)
        for cmd in seen:
            for bad in ('down', 'rm', '-v', '--volumes', 'prune'):
                self.assertNotIn(bad, cmd)
