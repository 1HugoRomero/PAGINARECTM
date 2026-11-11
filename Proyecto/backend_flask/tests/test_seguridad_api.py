"""Seguridad transversal: CORS, cabeceras, autenticación antes de cualquier dato y aislamiento entre agricultores."""

from tests.helpers import pedir


def test_sin_cors_para_otros_origenes(client):
    r = client.get("/api/v1/catalogo/fertilizantes", headers={"Origin": "https://sitio-ajeno.example"})
    assert "Access-Control-Allow-Origin" not in r.headers
    pre = client.open("/api/v1/catalogo/calcular-fertilizante", method="OPTIONS",
                      headers={"Origin": "https://sitio-ajeno.example", "Access-Control-Request-Method": "POST"})
    assert "Access-Control-Allow-Origin" not in pre.headers


def test_cabeceras_defensivas(client):
    r = client.get("/api/v1/catalogo/fertilizantes")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "no-referrer"


def test_datos_de_agricultor_no_se_guardan_en_cache(client_bd):
    r = pedir(client_bd, "/api/v1/predios")
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"


def test_ningun_dato_privado_sin_firma(client_bd):
    for ruta in ("/api/v1/predios", "/api/v1/predios/1", "/api/v1/predios/1/potreros", "/api/v1/potreros/1",
                 "/api/v1/calculos", "/api/v1/usuarios/me", "/api/v1/cultivos", "/api/v1/insumos", "/api/v1/zonas"):
        assert client_bd.get(ruta).status_code == 401, ruta


def test_aislamiento_entre_agricultores(client_bd):
    # Ana (1) no ve nada de Luis (2) y viceversa, por ningún camino.
    assert pedir(client_bd, "/api/v1/predios/2", usuario=1).status_code == 404
    assert pedir(client_bd, "/api/v1/predios/2/potreros", usuario=1).status_code == 404
    assert pedir(client_bd, "/api/v1/potreros/2", usuario=1).status_code == 404
    assert pedir(client_bd, "/api/v1/predios/1", usuario=2).status_code == 404
    historial = pedir(client_bd, "/api/v1/calculos?potrero_id=2", usuario=1).get_json()["calculos"]
    assert historial == []
    nombres = [p["nombre"] for p in pedir(client_bd, "/api/v1/predios", usuario=2).get_json()["predios"]]
    assert nombres == ["Predio Luis"]


def test_admin_requerido_en_resumen_admin(client_bd):
    assert pedir(client_bd, "/api/v1/admin/resumen", usuario=1).status_code == 403
    assert pedir(client_bd, "/api/v1/admin/resumen", usuario=3, admin=True).status_code == 501


def test_cuerpo_demasiado_grande(client):
    r = client.post("/api/v1/catalogo/calcular-fertilizante", data="x" * (65 * 1024), content_type="application/json")
    assert r.status_code == 413
    assert r.get_json()["error"]["codigo"] == "HTTP_413"


def test_errores_internos_no_filtran_detalles(client, monkeypatch):
    from app.services import fertilizantes

    def falla(*a, **k):
        raise RuntimeError("detalle interno secreto")

    monkeypatch.setattr(fertilizantes, "listar", falla)
    r = client.get("/api/v1/catalogo/fertilizantes")
    assert r.status_code == 500
    assert "secreto" not in r.get_data(as_text=True)
