"""Google Maps JavaScript API como mapa base de predios y potreros.

La clave se lee de variables de entorno y llega a la página solo dentro de la configuración del mapa. Las
herramientas de dibujo siguen siendo las propias (no la Drawing Library de Google, retirada).
"""

import json
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import Predio

CORE = Path(__file__).resolve().parent.parent
RAIZ = CORE.parent
GEOJSON = {
    'type': 'Polygon',
    'coordinates': [[[-71.22, -33.69], [-71.21, -33.69], [-71.21, -33.68], [-71.22, -33.68], [-71.22, -33.69]]],
}


def fuente(*partes):
    return (CORE / 'static').joinpath(*partes).read_text(encoding='utf-8').replace('\r\n', '\n')


def config_del_mapa(response):
    bloque = re.search(r'<script id="maps-config" type="application/json">(.*?)</script>', response.content.decode(), re.S)
    return json.loads(bloque.group(1))


class GoogleMapsConfigTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('ana', email='ana@example.com', password='Campo-Seguro-2026!')
        self.predio = Predio.objects.create(
            propietario=self.user, nombre='Campo', ubicacion='Melipilla', superficie_ha=5, geojson=GEOJSON
        )
        self.client.force_login(self.user)
        self.paginas = ('/predios/', '/predios/nuevo/', f'/predios/{self.predio.pk}/', f'/predios/{self.predio.pk}/editar/')

    @override_settings(GOOGLE_MAPS_API_KEY='clave-de-prueba-123')
    def test_la_clave_llega_a_las_pantallas_de_predios_dentro_de_la_configuracion(self):
        for url in self.paginas:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertEqual(config_del_mapa(r)['google_maps_key'], 'clave-de-prueba-123', url)
            self.assertContains(r, 'js/agro-basemap.js', msg_prefix=url)
            html = r.content.decode()
            self.assertLess(html.index('leaflet.js'), html.index('js/agro-basemap.js'), url)
            self.assertEqual(html.count('clave-de-prueba-123'), 1, url)  # solo en la configuración del mapa

    @override_settings(GOOGLE_MAPS_API_KEY='')
    def test_sin_clave_la_configuracion_queda_vacia_y_conserva_el_mapa_de_respaldo(self):
        config = config_del_mapa(self.client.get('/predios/'))
        self.assertEqual(config['google_maps_key'], '')
        self.assertTrue(config['tile_url'].startswith('https://'))

    @override_settings(GOOGLE_MAPS_API_KEY='clave-de-prueba-123')
    def test_la_clave_no_aparece_en_otros_modulos(self):
        for url in ('/', '/calendario/', '/decisiones/', '/productos/'):
            self.assertNotContains(self.client.get(url), 'clave-de-prueba-123', msg_prefix=url)

    def test_la_clave_no_esta_escrita_en_el_codigo_ni_en_el_ejemplo_de_entorno(self):
        settings_src = (RAIZ / 'AgroAsesor' / 'settings.py').read_text(encoding='utf-8')
        self.assertIn("os.getenv('GOOGLE_MAPS_API_KEY') or os.getenv('VITE_GOOGLE_MAPS_API_KEY')", settings_src)
        self.assertRegex((RAIZ / '.env.example').read_text(encoding='utf-8'), r'(?m)^GOOGLE_MAPS_API_KEY=$')
        self.assertIn('GOOGLE_MAPS_API_KEY: ${GOOGLE_MAPS_API_KEY:-', (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8'))
        for archivo in (('js', 'agro-basemap.js'), ('js', 'predios-map.js'), ('js', 'predio-detail.js')):
            self.assertNotRegex(fuente(*archivo), r'AIza[0-9A-Za-z_\-]{20,}')  # formato de las claves de Google


class GoogleMapsScriptTests(TestCase):
    def test_usa_maps_javascript_api_sin_la_drawing_library(self):
        js = fuente('js', 'agro-basemap.js')
        self.assertIn('https://maps.googleapis.com/maps/api/js?key=', js)
        self.assertIn('encodeURIComponent(key)', js)
        self.assertIn('loading=async', js)
        self.assertIn("{ normal: 'roadmap', satellite: 'hybrid' }", js)
        for origen in (js, fuente('js', 'predios-map.js'), fuente('js', 'predio-detail.js')):
            self.assertNotIn('libraries=drawing', origen)
            self.assertNotIn('DrawingManager', origen)

    def test_los_errores_de_google_se_avisan_y_no_se_ocultan(self):
        js = fuente('js', 'agro-basemap.js')
        self.assertIn('window.gm_authFailure', js)
        self.assertIn('Google Maps rechazó la clave de API', js)
        self.assertIn('falta GOOGLE_MAPS_API_KEY', js)
        self.assertIn("box.className = 'map-base-notice'", js)

    def test_las_pantallas_usan_el_mapa_base_comun(self):
        for archivo in ('predios-map.js', 'predio-detail.js'):
            js = fuente('js', archivo)
            self.assertIn('window.AgroBasemap.create(map, config', js)
            self.assertNotIn('arcgisonline', js)  # el respaldo vive solo en agro-basemap.js

    def test_modos_mover_y_dibujar_para_pantallas_tactiles(self):
        js = fuente('js', 'predios-map.js')
        self.assertIn("['Dibujar', 'draw']", js)
        self.assertIn("['Mover mapa', 'pan']", js)
        self.assertIn('if (panMode) return;', js)
        css = fuente('css', 'mapa-google.css')
        regla = re.search(r'\.map-draw-mode button \{(.*?)\}', css, re.S).group(1)
        self.assertIn('min-height: 48px;', regla)
        self.assertIn('@media (pointer: coarse)', css)
        self.assertIn('.agro-google-base', css)

    def test_google_maneja_los_gestos_y_leaflet_solo_lo_sigue(self):
        js = fuente('js', 'agro-basemap.js')
        self.assertIn("gestureHandling: 'greedy'", js)  # gestos oficiales de Google
        self.assertIn('zoomControl: true,', js)  # botones + y − de Google
        self.assertIn("const GESTURES = ['dragging', 'touchZoom', 'doubleClickZoom', 'boxZoom', 'keyboard'];", js)
        self.assertIn('GESTURES.forEach((name) => map[name] && map[name].disable());', js)  # sin doble proceso
        self.assertIn("if (isGoogleActive()) return; // la rueda la maneja Google", js)
        self.assertIn("state.gmap.addListener('center_changed', followGoogle);", js)
        self.assertIn("map.setView([center.lat(), center.lng()], zoom, { animate: false });", js)
        self.assertIn('fromGoogle: true,', js)
        self.assertIn('if (map.agroGoogleMaster && !event.fromGoogle) return;', fuente('js', 'predios-map.js'))
        for archivo in ('predios-map.js', 'predio-detail.js'):
            self.assertIn('window.AgroBasemap.MAP_OPTIONS', fuente('js', archivo))
