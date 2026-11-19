import os
import tempfile
import unittest
from unittest import mock

from elyares import spotify

S = spotify.SEP


def line(status='Playing', artist='Soda Stereo', title='De música ligera', album='Signos',
         art='https://i.scdn.co/image/abc', pos='65000000', length='187000000'):
    return S.join((status, artist, title, album, art, pos, length)) + '\n'


class Leer(unittest.TestCase):
    def test_una_linea_de_playerctl_sale_como_dict_con_segundos(self):
        got = spotify.parse(line())
        self.assertTrue(got['playing'])
        self.assertEqual((got['artist'], got['title'], got['album']), ('Soda Stereo', 'De música ligera', 'Signos'))
        self.assertEqual((got['position'], got['length']), (65.0, 187.0))

    def test_en_pausa_no_esta_sonando(self):
        self.assertFalse(spotify.parse(line(status='Paused'))['playing'])

    def test_una_salida_rota_o_vacia_es_none(self):
        for bad in ('', '\n', 'Playing\tuna sola columna', S.join(('', 'a', 'b', 'c', 'd', '1', '2'))):
            self.assertIsNone(spotify.parse(bad))

    def test_una_posicion_que_no_es_numero_cuenta_como_cero(self):
        got = spotify.parse(line(pos='', length='no'))
        self.assertEqual((got['position'], got['length']), (0.0, 0.0))

    def test_sin_spotify_abierto_snapshot_es_none(self):
        with mock.patch.object(spotify, '_run', return_value=None):
            self.assertIsNone(spotify.snapshot())


class Botones(unittest.TestCase):
    def test_cada_boton_manda_su_orden_a_playerctl(self):
        with mock.patch.object(spotify, '_run', return_value='') as run:
            for key, verb in (('play', 'play-pause'), ('next', 'next'), ('prev', 'previous')):
                self.assertTrue(spotify.control(key))
                run.assert_called_with([verb])

    def test_un_boton_desconocido_no_llama_a_nada(self):
        with mock.patch.object(spotify, '_run') as run:
            self.assertFalse(spotify.control('stop; rm -rf /'))
            run.assert_not_called()


class Portada(unittest.TestCase):
    def test_solo_baja_http_y_https_y_nunca_otra_cosa(self):
        with mock.patch('urllib.request.urlopen') as net:
            for url in ('ftp://x/y', 'javascript:alert(1)', '/etc/passwd', ''):
                self.assertIsNone(spotify.fetch_cover(url))
            net.assert_not_called()

    def test_el_nombre_en_disco_sale_del_hash_no_de_la_url(self):
        path = spotify.cover_path('https://i.scdn.co/image/../../etc/passwd')
        self.assertEqual(os.path.dirname(path), spotify.COVER_DIR)
        self.assertNotIn('..', os.path.basename(path))

    def test_baja_una_vez_y_la_segunda_sale_del_disco(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(spotify, 'COVER_DIR', tmp), \
                mock.patch('urllib.request.urlopen') as net:
            net.return_value.__enter__.return_value.read.return_value = b'jpg'
            first = spotify.fetch_cover('https://i.scdn.co/image/abc')
            with open(first, 'rb') as fh:
                self.assertEqual(fh.read(), b'jpg')
            self.assertEqual(spotify.fetch_cover('https://i.scdn.co/image/abc'), first)
            self.assertEqual(net.call_count, 1)

    def test_una_portada_enorme_se_descarta(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(spotify, 'COVER_DIR', tmp), \
                mock.patch('urllib.request.urlopen') as net:
            net.return_value.__enter__.return_value.read.return_value = b'x' * (spotify.COVER_MAX + 1)
            self.assertIsNone(spotify.fetch_cover('https://i.scdn.co/image/grande'))
            self.assertEqual(os.listdir(tmp), [])

    def test_file_url_solo_si_el_archivo_existe(self):
        with tempfile.NamedTemporaryFile() as fh:
            self.assertEqual(spotify.fetch_cover('file://' + fh.name), fh.name)
        self.assertIsNone(spotify.fetch_cover('file:///no/existe.jpg'))


if __name__ == '__main__':
    unittest.main()
