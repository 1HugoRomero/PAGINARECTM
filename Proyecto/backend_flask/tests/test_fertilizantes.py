"""Catálogo de fertilizantes: datos con fuente, cálculo sin dosis inventadas, conversiones y normativa SAG."""

from app.services import fertilizantes as svc


def test_todos_los_fertilizantes_tienen_fuente_y_ubicacion(client):
    r = client.get('/api/v1/catalogo/fertilizantes')
    assert r.status_code == 200
    datos = r.get_json()
    assert datos['total'] == len(datos['resultados']) >= 15
    for f in datos['resultados']:
        assert f['fuente']['url'].startswith('https://')
        assert f['ubicacion_en_fuente']
        assert f['estado_verificacion'] in {'cotejada_con_fuente', 'citada_sin_cotejar'}
        assert 'precio' not in f and 'dosis' not in f


def test_valores_transcritos_de_fao_ifa(client):
    urea = client.get('/api/v1/catalogo/fertilizantes/urea').get_json()
    assert urea['composicion']['N'] == {'min_pct': 45, 'max_pct': 46, 'es_rango': True}
    tsp = client.get('/api/v1/catalogo/fertilizantes/superfosfato-triple').get_json()
    assert tsp['grado_npk'] == '0 / 46 / 0'
    kcl = client.get('/api/v1/catalogo/fertilizantes/cloruro-potasico').get_json()
    assert kcl['composicion']['K2O']['min_pct'] == 60
    nitrato = client.get('/api/v1/catalogo/fertilizantes/nitrato-amonico').get_json()
    assert nitrato['grado_npk'] == '33-34,5 / 0 / 0'
    assert client.get('/api/v1/catalogo/fertilizantes/no-existe').status_code == 404


def test_filtros(client):
    azufre = client.get('/api/v1/catalogo/fertilizantes?nutriente=S').get_json()['resultados']
    assert azufre and all('S' in f['composicion'] for f in azufre)
    assert client.get('/api/v1/catalogo/fertilizantes?grupo=potasicos').get_json()['total'] == 3
    assert client.get('/api/v1/catalogo/fertilizantes?q=salitre').get_json()['total'] == 1
    assert client.get('/api/v1/catalogo/fertilizantes?nutriente=Zn').status_code == 400


def test_calculo_con_valor_fijo_y_aportes_adicionales(client):
    r = client.post(
        '/api/v1/catalogo/calcular-fertilizante',
        json={'fertilizante_id': 'sulfato-potasico', 'nutriente': 'K2O', 'requerimiento_kg_ha': 100, 'superficie_m2': 5000},
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j['producto_kg_ha'] == 200.0  # 100 / 0,50
    assert j['producto_total_kg'] == 100.0  # 0,5 ha
    assert j['origen_ley'] == 'referencia_fuente'
    assert j['aportes_adicionales_kg_ha'] == [{'nutriente': 'S', 'min_kg_ha': 36.0, 'max_kg_ha': 36.0}]


def test_rango_exige_ley_de_la_etiqueta_y_calcula_sacos(client):
    base = {'fertilizante_id': 'urea', 'nutriente': 'N', 'requerimiento_kg_ha': 92, 'superficie_ha': 2}
    sin_ley = client.post('/api/v1/catalogo/calcular-fertilizante', json=base)
    assert sin_ley.status_code == 400 and 'ley_declarada_pct' in sin_ley.get_json()['error']['mensaje']
    r = client.post('/api/v1/catalogo/calcular-fertilizante', json={**base, 'ley_declarada_pct': 46, 'peso_saco_kg': 25})
    j = r.get_json()
    assert j['producto_kg_ha'] == 200.0 and j['producto_total_kg'] == 400.0
    assert j['sacos'] == {'peso_saco_kg': 25, 'cantidad': 16, 'sobrante_kg': 0.0}
    assert j['origen_ley'] == 'etiqueta_usuario'


def test_calculo_rechaza_datos_invalidos(client):
    url = '/api/v1/catalogo/calcular-fertilizante'
    ok = {'fertilizante_id': 'superfosfato-triple', 'nutriente': 'P2O5', 'requerimiento_kg_ha': 46, 'superficie_ha': 1}
    assert client.post(url, json=ok).status_code == 200
    assert client.post(url, json={**ok, 'nutriente': 'N'}).status_code == 400
    assert client.post(url, json={**ok, 'requerimiento_kg_ha': -1}).status_code == 400
    assert client.post(url, json={**ok, 'requerimiento_kg_ha': '46'}).status_code == 400
    assert client.post(url, json={**ok, 'superficie_m2': 10}).status_code == 400
    assert client.post(url, json={**ok, 'precio': 1}).status_code == 400
    assert client.post(url, data='texto').status_code == 415


def test_conversiones_fao(client):
    r = client.get('/api/v1/catalogo/convertir?de=P2O5&a=P&valor=100').get_json()
    assert r['factor'] == 0.4364 and r['resultado'] == 43.64
    assert client.get('/api/v1/catalogo/convertir?de=K&a=K2O&valor=10').get_json()['resultado'] == 12.046
    assert client.get('/api/v1/catalogo/convertir?de=N&a=P&valor=1').status_code == 400
    assert client.get('/api/v1/catalogo/convertir?de=K2O&a=K&valor=abc').status_code == 400
    assert len(client.get('/api/v1/catalogo/conversiones').get_json()['factores']) == 4


def test_revision_de_etiqueta_contra_res_sag_8651(client):
    simple = client.post('/api/v1/catalogo/revisar-etiqueta', json={'N': 46}).get_json()
    assert simple['tipo'] == 'un_macronutriente' and simple['cumple_todos'] is True
    bajo = client.post('/api/v1/catalogo/revisar-etiqueta', json={'K2O': 2}).get_json()
    assert bajo['cumple_todos'] is False and bajo['nutrientes'][0]['minimo_pct'] == 3
    mezcla = client.post('/api/v1/catalogo/revisar-etiqueta', json={'N': 1, 'P2O5': 10}).get_json()
    assert mezcla['tipo'] == 'varios_macronutrientes'
    assert {d['nutriente']: d['cumple'] for d in mezcla['nutrientes']} == {'N': False, 'P2O5': True}
    assert client.post('/api/v1/catalogo/revisar-etiqueta', json={'S': 10}).status_code == 400
    norma = client.get('/api/v1/catalogo/normativa/contenidos-minimos').get_json()
    assert norma['un_macronutriente']['minimos_pct']['N'] == 5
    assert 'diariooficial' in norma['fuente']['url']


def test_resumen_y_validacion_del_archivo():
    datos = svc.cargar()
    assert {f['id'] for f in datos['fuentes']} == {'fao_ifa_2002', 'sag_res_8651_2024'}
    assert svc.resumen()['total_fertilizantes'] == len(datos['fertilizantes'])
