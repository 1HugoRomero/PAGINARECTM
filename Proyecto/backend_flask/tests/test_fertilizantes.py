"""Catálogo de fertilizantes: datos fieles a FAO/IFA 2002, cálculos exactos, conversiones y normativa SAG 8.651."""

import math

import pytest

from app.services import fertilizantes as svc

URL_CALC = "/api/v1/catalogo/calcular-fertilizante"
URL_ETIQUETA = "/api/v1/catalogo/revisar-etiqueta"

# Transcripción del Cuadro 2 (p. 38) y Cuadro 3 (p. 39) de FAO/IFA 2002, columna por columna.
# None = la fuente imprime «-» (no informado). Si alguien edita el YAML, esta prueba lo detecta.
ESPERADO = {
    "urea": {"N": (45, 46), "P2O5": (0, 0), "K2O": (0, 0), "Mg": None, "S": None},
    "sulfato-amonico": {"N": (21, 21), "P2O5": (0, 0), "K2O": (0, 0), "Mg": None, "S": (23, 23)},
    "nitrato-amonico": {"N": (33, 34.5), "P2O5": (0, 0), "K2O": (0, 0), "Mg": None, "S": None},
    "nitrato-amonico-calcico": {"N": (20.5, 26), "P2O5": (0, 0), "K2O": (0, 0), "Mg": None, "S": None},
    "nitrato-sodico": {"N": (16, 16), "P2O5": (0, 0), "K2O": (0, 0), "Mg": None, "S": None},
    "nitrosulfato-amonico": {"N": (26, 26), "P2O5": (0, 0), "K2O": (0, 0), "Mg": None, "S": (15, 15)},
    "superfosfato-simple": {"N": (0, 0), "P2O5": (16, 20), "K2O": (0, 0), "Mg": None, "S": (12, 12)},
    "superfosfato-triple": {"N": (0, 0), "P2O5": (46, 46), "K2O": (0, 0), "Mg": None, "S": None},
    "fosfato-roca": {"N": (0, 0), "P2O5": (20, 40), "K2O": (0, 0), "Mg": None, "S": None},
    "fosfato-dicalcico": {"N": (0, 0), "P2O5": (35, 42), "K2O": (0, 0), "Mg": None, "S": None},
    "escoria-thomas": {"N": (0, 0), "P2O5": (16, 20), "K2O": (0, 0), "Mg": (1, 3), "S": None},
    "cloruro-potasico": {"N": (0, 0), "P2O5": (0, 0), "K2O": (60, 60), "Mg": None, "S": None},
    "sulfato-potasico": {"N": (0, 0), "P2O5": (0, 0), "K2O": (50, 50), "Mg": None, "S": (18, 18)},
    "sulfato-potasico-magnesico": {"N": (0, 0), "P2O5": (0, 0), "K2O": (26, 30), "Mg": (5, 7), "S": (16, 22)},
    "kieserita": {"N": None, "P2O5": None, "K2O": None, "Mg": (16, 16), "S": (22, 22)},
    "kieserita-calcinada": {"N": None, "P2O5": None, "K2O": None, "Mg": (20, 20), "S": (27, 27)},
    "yeso": {"N": None, "P2O5": None, "K2O": None, "Mg": None, "S": (16, 18)},
    "fosfato-diamonico": {"N": (16, 18), "P2O5": (42, 48), "K2O": None, "Mg": None, "S": None},
    "fosfato-monoamonico": {"N": (11, 11), "P2O5": (52, 52), "K2O": None, "Mg": None, "S": None},
}


def _calc(client, **body):
    return client.post(URL_CALC, json=body)


# ---------------------------------------------------------------- datos y representación


def test_hay_19_fertilizantes_y_todos_tienen_fuente_ubicacion_y_estado(client):
    datos = client.get("/api/v1/catalogo/fertilizantes").get_json()
    assert datos["total"] == len(datos["resultados"]) == 19
    for f in datos["resultados"]:
        assert f["fuente"]["url"].startswith("https://")
        assert f["ubicacion_en_fuente"].startswith(("Cuadro", "Texto"))
        assert f["estado_verificacion"] in {"cotejada_con_fuente", "citada_sin_cotejar"}
        assert f["tipo_composicion"] == "referencial"
        assert "precio" not in str(f).lower() or "precio" in f["aviso"].lower()


@pytest.mark.parametrize("fert_id,columnas", sorted(ESPERADO.items()))
def test_cada_fertilizante_coincide_con_fao_ifa(client, fert_id, columnas):
    f = client.get(f"/api/v1/catalogo/fertilizantes/{fert_id}").get_json()
    comp = f["composicion_referencial"]
    assert list(comp) == ["N", "P2O5", "K2O", "MgO", "S"]
    for clave in ("N", "P2O5", "K2O", "S"):
        esperado = columnas[clave]
        if esperado is None:
            assert comp[clave]["informado_en_fuente"] is False and comp[clave]["min_pct"] is None
        else:
            assert (comp[clave]["min_pct"], comp[clave]["max_pct"]) == esperado
            assert comp[clave]["es_rango"] is (esperado[0] != esperado[1])
    mg = columnas["Mg"]
    if mg is None:
        assert comp["MgO"]["informado_en_fuente"] is False
    else:
        assert comp["MgO"]["origen"] == "calculado"
        assert comp["MgO"]["min_pct"] == round(mg[0] * 1.6583, 1)
        assert comp["MgO"]["max_pct"] == round(mg[1] * 1.6583, 1)


def test_superfosfato_simple_no_se_confunde_con_k2o(client):
    f = client.get("/api/v1/catalogo/fertilizantes/superfosfato-simple").get_json()
    assert f["grado"] == {"N": "0", "P2O5": "16–20", "K2O": "0", "texto": "N 0 · P2O5 16–20 · K2O 0"}
    assert f["composicion_referencial"]["K2O"]["max_pct"] == 0
    assert f["composicion_referencial"]["S"]["texto"] == "12 %"
    assert "0-16-20-0" not in str(f)


def test_cero_y_no_informado_son_distintos(client):
    dap = client.get("/api/v1/catalogo/fertilizantes/fosfato-diamonico").get_json()
    assert dap["composicion_referencial"]["K2O"]["informado_en_fuente"] is False
    assert dap["grado"]["K2O"] == "—"
    urea = client.get("/api/v1/catalogo/fertilizantes/urea").get_json()
    assert urea["composicion_referencial"]["K2O"] == {
        "informado_en_fuente": True, "min_pct": 0, "max_pct": 0, "es_rango": False, "texto": "0 %", "origen": "fuente",
    }


def test_formulas_solo_si_las_da_la_fuente(client):
    assert client.get("/api/v1/catalogo/fertilizantes/urea").get_json()["formula"] == "CO(NH2)2"
    dap = client.get("/api/v1/catalogo/fertilizantes/fosfato-diamonico").get_json()
    assert dap["formula"] is None and dap["formula_origen"] == "no_indicada_en_fuente"
    kie = client.get("/api/v1/catalogo/fertilizantes/kieserita").get_json()
    assert "Epsom" in kie["nota"]


def test_map_queda_marcado_sin_cotejar(client):
    assert client.get("/api/v1/catalogo/fertilizantes/fosfato-monoamonico").get_json()["estado_verificacion"] == "citada_sin_cotejar"


def test_filtros_y_404(client):
    azufre = client.get("/api/v1/catalogo/fertilizantes?nutriente=S").get_json()["resultados"]
    assert {f["id"] for f in azufre} == {k for k, v in ESPERADO.items() if v["S"]}
    mgo = client.get("/api/v1/catalogo/fertilizantes?nutriente=MgO").get_json()["resultados"]
    assert {f["id"] for f in mgo} == {"escoria-thomas", "sulfato-potasico-magnesico", "kieserita", "kieserita-calcinada"}
    assert client.get("/api/v1/catalogo/fertilizantes?grupo=potasicos").get_json()["total"] == 3
    assert client.get("/api/v1/catalogo/fertilizantes?q=salitre").get_json()["total"] == 1
    assert client.get("/api/v1/catalogo/fertilizantes?nutriente=Mg").status_code == 400
    assert client.get("/api/v1/catalogo/fertilizantes?grupo=x").status_code == 400
    assert client.get("/api/v1/catalogo/fertilizantes?q=" + "a" * 101).status_code == 400
    assert client.get("/api/v1/catalogo/fertilizantes/no-existe").status_code == 404


# ---------------------------------------------------------------- cálculos (verificados a mano)


def test_valor_unico_referencial_superfosfato_triple(client):
    # 92 kg P2O5/ha ÷ 0,46 = 200 kg/ha; × 2,5 ha = 500 kg; 500 / 25 = 20 sacos exactos.
    j = _calc(client, fertilizante_id="superfosfato-triple", nutriente="P2O5", requerimiento_kg_ha=92,
              superficie_ha=2.5, peso_saco_kg=25).get_json()
    assert j["ley"]["tipo"] == "referencial" and j["ley"]["valor_pct"] == "46"
    assert j["producto_kg_ha"] == {"min": 200.0, "max": 200.0}
    assert j["producto_total_kg"] == {"min": 500.0, "max": 500.0}
    assert j["sacos"]["cantidad"] == {"min": 20, "max": 20} and j["sacos"]["sobrante_kg"] == {"min": 0.0, "max": 0.0}
    assert any("REFERENCIAL" in a for a in j["advertencias"])


def test_rango_referencial_da_rango_de_producto(client):
    # Urea 45–46 % N: 92/0,46 = 200 y 92/0,45 = 204,444… kg/ha; × 2 ha = 400 y 408,89 kg.
    j = _calc(client, fertilizante_id="urea", nutriente="N", requerimiento_kg_ha=92, superficie_ha=2,
              peso_saco_kg=25).get_json()
    assert j["ley"] == {"tipo": "referencial", "valor_pct": "45–46", "min_pct": 45, "max_pct": 46}
    assert j["producto_kg_ha"] == {"min": 200.0, "max": 204.44}
    assert j["producto_total_kg"] == {"min": 400.0, "max": 408.89}
    assert j["sacos"]["cantidad"] == {"min": 16, "max": math.ceil(408.888 / 25)}
    assert j["sacos"]["sobrante_kg"] == {"min": 0.0, "max": 16.11}


def test_ley_de_etiqueta_reemplaza_la_referencia(client):
    j = _calc(client, fertilizante_id="urea", nutriente="N", requerimiento_kg_ha=92, superficie_ha=2,
              ley_declarada_pct=46).get_json()
    assert j["ley"] == {"tipo": "declarada_en_etiqueta", "valor_pct": 46, "referencia_fuente_pct": "45–46"}
    assert j["producto_kg_ha"] == {"min": 200.0, "max": 200.0}
    fuera = _calc(client, fertilizante_id="urea", nutriente="N", requerimiento_kg_ha=92, superficie_ha=2,
                  ley_declarada_pct=40).get_json()
    assert any("fuera del rango" in a for a in fuera["advertencias"])


def test_aportes_adicionales_con_rango(client):
    # Superfosfato simple, 40 kg P2O5/ha: 200–250 kg/ha de producto; S 12 % => 24–30 kg S/ha; N y K2O = 0.
    j = _calc(client, fertilizante_id="superfosfato-simple", nutriente="P2O5", requerimiento_kg_ha=40,
              superficie_m2=10000).get_json()
    assert j["producto_kg_ha"] == {"min": 200.0, "max": 250.0}
    aportes = {a["nutriente"]: (a["min"], a["max"]) for a in j["aportes_adicionales_kg_ha"]}
    assert aportes == {"N": (0.0, 0.0), "K2O": (0.0, 0.0), "S": (24.0, 30.0)}


def test_mgo_calculado_desde_mg(client):
    # Kieserita: Mg 16 % => MgO 26,5 %; 53 kg MgO/ha ÷ 0,265 = 200 kg/ha.
    j = _calc(client, fertilizante_id="kieserita", nutriente="MgO", requerimiento_kg_ha=53, superficie_ha=1).get_json()
    assert j["producto_kg_ha"] == {"min": 200.0, "max": 200.0}


@pytest.mark.parametrize(
    "cambio,mensaje",
    [
        ({"nutriente": "K2O"}, "no aporta K2O"),
        ({"nutriente": "Mg"}, "nutriente debe ser"),
        ({"requerimiento_kg_ha": -1}, "mayor que cero"),
        ({"requerimiento_kg_ha": 0}, "mayor que cero"),
        ({"requerimiento_kg_ha": 2001}, "no superar 2000"),
        ({"requerimiento_kg_ha": "46"}, "debe ser un número"),
        ({"requerimiento_kg_ha": True}, "debe ser un número"),
        ({"superficie_m2": 10}, "no ambas"),
        ({"peso_saco_kg": 0}, "peso_saco_kg"),
        ({"peso_saco_kg": 1001}, "no superar 1000"),
        ({"ley_declarada_pct": 101}, "no superar 100"),
        ({"fertilizante_id": "inventado"}, "desconocido"),
        ({"precio": 1000}, "no admitidos"),
    ],
)
def test_calculo_rechaza_datos_invalidos(client, cambio, mensaje):
    base = {"fertilizante_id": "superfosfato-triple", "nutriente": "P2O5", "requerimiento_kg_ha": 46, "superficie_ha": 1}
    r = _calc(client, **{**base, **cambio})
    assert r.status_code == 400
    assert mensaje in r.get_json()["error"]["mensaje"]


def test_calculo_exige_json(client):
    assert client.post(URL_CALC, data="texto").status_code == 415
    assert client.post(URL_CALC, json=[1, 2]).status_code == 400


def test_sin_superficie_falla(client):
    r = _calc(client, fertilizante_id="urea", nutriente="N", requerimiento_kg_ha=10)
    assert r.status_code == 400


# ---------------------------------------------------------------- conversiones


def test_conversiones_fao_p77(client):
    assert client.get("/api/v1/catalogo/convertir?de=P2O5&a=P&valor=100").get_json()["resultado"] == 43.64
    assert client.get("/api/v1/catalogo/convertir?de=P&a=P2O5&valor=10").get_json()["resultado"] == 22.914
    assert client.get("/api/v1/catalogo/convertir?de=K2O&a=K&valor=60").get_json()["resultado"] == 49.812
    assert client.get("/api/v1/catalogo/convertir?de=K&a=K2O&valor=10").get_json()["resultado"] == 12.046
    assert client.get("/api/v1/catalogo/convertir?de=N&a=P&valor=1").status_code == 400
    assert client.get("/api/v1/catalogo/convertir?de=K2O&a=K&valor=abc").status_code == 400
    assert client.get("/api/v1/catalogo/convertir?de=K2O&a=K&valor=-1").status_code == 400
    conv = client.get("/api/v1/catalogo/conversiones").get_json()
    assert conv["ubicacion"].endswith("p. 77") and len(conv["factores"]) == 4


def test_ida_y_vuelta_de_conversiones_es_consistente():
    for ida, vuelta in (("P2O5", "P"), ("K2O", "K")):
        x = svc.convertir(ida, vuelta, "100")["resultado"]
        y = svc.convertir(vuelta, ida, str(x))["resultado"]
        assert abs(y - 100) < 0.01


# ---------------------------------------------------------------- normativa SAG 8.651


def test_normativa_tiene_todas_las_categorias_y_avisa_cuadros(client):
    norma = client.get("/api/v1/catalogo/normativa/contenidos-minimos").get_json()
    ids = [c["id"] for c in norma["categorias"]]
    assert ids == ["organico", "inorganico", "organo_mineral", "enmienda_organica", "enmienda_inorganica",
                   "sustrato_enriquecido", "mezcla", "bioestimulante"]
    inorg = next(c for c in norma["categorias"] if c["id"] == "inorganico")
    assert inorg["un_macronutriente_pct"] == {"N": 5, "P2O5": 5, "K2O": 3, "MgO": 2, "CaO": 6, "SO3": 5, "Na2O": 1}
    assert inorg["varios_macronutrientes_pct"]["N"] == 1.5
    assert norma["biuret_maximo_pct"] == 1.2
    assert "Cuadros" in norma["aviso"] and "diariooficial" in norma["fuente"]["url"]


def test_inorganico_un_nutriente(client):
    j = client.post(URL_ETIQUETA, json={"categoria": "inorganico", "nutrientes": {"N": 46}}).get_json()
    assert j["cumple_contenidos_minimos"] is True and j["revisados"][0]["minimo_pct"] == 5
    assert j["alcance"] == "Solo contenidos mínimos de nutrientes"
    assert "NO acredita" in j["aviso"]
    assert j["no_revisado"]["contaminantes_a_declarar"]
    bajo = client.post(URL_ETIQUETA, json={"categoria": "inorganico", "nutrientes": {"K2O": 2}}).get_json()
    assert bajo["cumple_contenidos_minimos"] is False


def test_formato_abreviado_es_inorganico(client):
    j = client.post(URL_ETIQUETA, json={"N": 1, "P2O5": 10}).get_json()
    assert j["categoria"]["id"] == "inorganico"
    assert {r["dato"]: r["cumple"] for r in j["revisados"]} == {"N": False, "P2O5": True}


def test_biuret_en_productos_con_urea(client):
    ok = client.post(URL_ETIQUETA, json={"categoria": "inorganico", "nutrientes": {"N": 46}, "contiene_urea": True, "biuret_pct": 1.2}).get_json()
    assert ok["cumple_contenidos_minimos"] is True and ok["alcance"].endswith("y biuret")
    alto = client.post(URL_ETIQUETA, json={"categoria": "inorganico", "nutrientes": {"N": 46}, "contiene_urea": True, "biuret_pct": 1.3}).get_json()
    assert alto["cumple_contenidos_minimos"] is False
    falta = client.post(URL_ETIQUETA, json={"categoria": "mezcla", "nutrientes": {"N": 20}, "contiene_urea": True}).get_json()
    assert falta["cumple_contenidos_minimos"] is False


def test_organico_requiere_carbono_y_un_primario(client):
    sin_c = client.post(URL_ETIQUETA, json={"categoria": "organico", "nutrientes": {"N": 2}}).get_json()
    assert sin_c["cumple_contenidos_minimos"] is False
    ok = client.post(URL_ETIQUETA, json={"categoria": "organico", "nutrientes": {"N": 2}, "otros": {"carbono_organico": 6}}).get_json()
    assert ok["cumple_contenidos_minimos"] is True
    sin_primario = client.post(URL_ETIQUETA, json={"categoria": "organico", "nutrientes": {"N": 0.5}, "otros": {"carbono_organico": 6}}).get_json()
    assert sin_primario["cumple_contenidos_minimos"] is False


def test_enmiendas(client):
    solido = client.post(URL_ETIQUETA, json={"categoria": "enmienda_organica", "otros": {"carbono_organico": 6, "materia_seca_solidos": 15}}).get_json()
    assert solido["cumple_contenidos_minimos"] is False
    liquido = client.post(URL_ETIQUETA, json={"categoria": "enmienda_organica", "estado": "liquido", "otros": {"carbono_organico": 6}}).get_json()
    assert liquido["cumple_contenidos_minimos"] is True
    cal = client.post(URL_ETIQUETA, json={"categoria": "enmienda_inorganica", "nutrientes": {"CaO": 50}}).get_json()
    assert cal["cumple_contenidos_minimos"] is True
    assert any("70 %" in r for r in cal["no_revisado"]["requisitos_especiales"])


def test_bioestimulante_sin_minimos(client):
    j = client.post(URL_ETIQUETA, json={"categoria": "bioestimulante"}).get_json()
    assert j["cumple_contenidos_minimos"] is None and j["observaciones"]


@pytest.mark.parametrize(
    "body",
    [
        {"categoria": "inventada", "nutrientes": {"N": 5}},
        {"categoria": "inorganico", "nutrientes": {"S": 10}},
        {"categoria": "inorganico", "nutrientes": {"N": 0}},
        {"categoria": "inorganico", "nutrientes": {"N": "5"}},
        {"categoria": "inorganico", "nutrientes": {}},
        {"categoria": "mezcla", "nutrientes": {}},
        {"categoria": "organico", "otros": {"humedad": 5}},
        {"categoria": "inorganico", "nutrientes": {"N": 5}, "contiene_urea": "si"},
        {"categoria": "inorganico", "nutrientes": {"N": 5}, "extra": 1},
        {},
    ],
)
def test_revision_rechaza_datos_invalidos(client, body):
    assert client.post(URL_ETIQUETA, json=body).status_code == 400


def test_resumen_y_archivo():
    datos = svc.cargar()
    assert {f["id"] for f in datos["fuentes"]} == {"fao_ifa_2002", "sag_res_8651_2024"}
    assert svc.resumen()["total_fertilizantes"] == 19
