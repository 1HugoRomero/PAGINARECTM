def test_health_sin_base_configurada(client):
    """Sin base configurada el servicio no está listo: health responde 503 (así lo implementa health.py)."""
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    body = response.get_json()
    assert body["status"] == "error"
    assert body["base_datos"] == "no_configurada"


def test_health_con_base_solo_lectura(client_bd):
    assert client_bd.get("/api/v1/health").get_json()["base_datos"] == "conectada_solo_lectura"
