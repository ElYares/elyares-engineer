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
