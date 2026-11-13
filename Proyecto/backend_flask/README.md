# API Flask de AgroAsesor

API REST en `/api/v1/` que corre **detrás de Django** y solo **lee** la base de datos. Django sigue siendo el
único sistema de cuentas: el navegador nunca habla directo con Flask.

```text
Navegador ──sesión Django──▶ Django /api/v1/… ──HTTP interno + firma HMAC──▶ Flask ──▶ /data/db.sqlite3 (solo lectura)
```

## Cómo funciona

- **Una sola autenticación**: la de Django. Flask no tiene login, contraseñas ni sesiones.
- **Firma**: Django envía las cabeceras `X-AgroAsesor-User/Staff/Timestamp/Signature`. La firma HMAC-SHA256
  cubre usuario, rol, hora, método, ruta y cuerpo, y caduca a los 60 segundos. Se arma en
  `core/api_gateway.py` y se verifica en `app/security/gateway.py`; las dos deben coincidir (hay una prueba
  con el mismo vector en cada lado).
- **Falla cerrada**: sin `AGROASESOR_INTERNAL_SECRET` (mínimo 32 caracteres) la API responde 503.
- **Solo lectura**: SQLite se abre con `mode=ro` y `PRAGMA query_only=ON`, y en Docker el volumen va con `:ro`.
- **Cada uno ve lo suyo**: cada consulta filtra por el usuario firmado; un recurso ajeno responde 404.

## Endpoints

Estado real al 11-11-2026 (la columna `x-estado` de `openapi.yaml` dice lo mismo para cada operación).
**La API no está completa:** 27 operaciones funcionan y 29 siguen respondiendo 501.

### Funcionan (27)

- Sistema: `GET /health`, `GET /openapi.json`.
- Datos del agricultor (requieren sesión de Django; cada uno ve solo lo suyo): `GET /usuarios/me`, `/predios`,
  `/predios/{id}`, `/predios/{id}/potreros`, `/potreros/{id}`, `/calculos`.
- Referencias de la base (requieren sesión): `GET /cultivos`, `/cultivos/{id}`, `/insumos`, `/insumos/{id}`, `/zonas`.
- Catálogo agrícola (público): `GET /catalogo/categorias`, `/catalogo/fuentes`, `/catalogo/productos`,
  `/catalogo/productos/{id}`, `/catalogo/referencias-siembra`, `POST /catalogo/calcular-sacos`.
- Fertilizantes (público): `GET /catalogo/fertilizantes` (filtros `nutriente`, `grupo`, `q`),
  `/catalogo/fertilizantes/{id}`, `/catalogo/fertilizantes/resumen`, `POST /catalogo/calcular-fertilizante`,
  `GET /catalogo/conversiones`, `/catalogo/convertir`, `/catalogo/normativa/contenidos-minimos`,
  `POST /catalogo/revisar-etiqueta`.
- Páginas de prueba (fuera de `/api/v1`): `/consola` (probar endpoints) y `/catalogo`.

### Pendientes: responden 501 (29)

- Cuentas: `POST /auth/registro`, `/auth/login`, `/auth/logout`, `PATCH /usuarios/me` (las cuentas siguen en Django).
- Escrituras de terreno: `POST /predios`, `PATCH|DELETE /predios/{id}`, `POST /predios/{id}/potreros`,
  `PATCH|DELETE /potreros/{id}`, `POST /potreros/{id}/confirmar-perimetro`.
- Temporadas (5), actividades (5), `GET /calendario`, `GET /reportes/resumen`,
  `GET /reportes/predios/{id}/historial`, `GET /admin/resumen`, `POST /predicciones/rendimiento`,
  `POST /calculos/semillas`, `/calculos/fertilizantes`, `/calculos/cobertura`.

Todas las rutas pendientes (salvo `/auth/*`) exigen la sesión de Django antes de responder 501.

### Fertilizantes: qué significa cada dato

- `composicion_referencial`: N, P2O5, K2O, MgO y S por separado. `informado_en_fuente: false` = la fuente imprime
  «-» (no es 0). MgO se calcula desde el Mg que informa FAO/IFA (× 1,6583) y lo indica en `origen: calculado`.
- `grado.texto` escribe los rangos con guion largo («N 0 · P2O5 16–20 · K2O 0») para no confundirlos.
- `calcular-fertilizante`: `producto_kg_ha = requerimiento × 100 / ley`. Si no se envía `ley_declarada_pct`, usa
  la composición referencial (`ley.tipo = referencial`) y, si es un rango, entrega mínimo y máximo.
- `revisar-etiqueta`: revisa solo los contenidos mínimos (y el biuret si se informa) de la categoría elegida;
  `cumple_contenidos_minimos` NO significa cumplimiento de toda la Resolución 8.651.

Fuentes (`data/fertilizantes.yaml`): FAO/IFA, *Los fertilizantes y su uso*, 4.ª ed., 2002 (Cuadros 2 y 3,
pp. 38-39; texto p. 39 y 45; Anexo p. 77) y Resolución SAG N° 8.651 exenta, Diario Oficial del 18-12-2024.
Los límites numéricos de sus Cuadros N° 1 a 11 no estaban en la versión de texto consultada y no se transcriben.

## Estructura

```text
backend_flask/
├── app/
│   ├── api/v1/        un archivo por área (rutas)
│   ├── services/      lectura de la base (terreno.py), catálogo YAML y unidades
│   ├── security/      verificación de la firma de Django
│   └── templates/     página de prueba del catálogo
├── data/              catalogo_agricola.yaml: fuentes (SAG, INIA, ODEPA) y referencias de siembra
├── tests/             pruebas con pytest
├── openapi.yaml       contrato de la API
└── run.py             arranque local
```

Cada referencia de `data/catalogo_agricola.yaml` indica si fue cotejada con su fuente o solo citada.
No contiene precios, stock ni formatos comerciales, y no afirma ningún aval de SAG, INIA u ODEPA.

## Ejecutar y probar (PowerShell)

```powershell
cd backend_flask
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe run.py
```

Escucha en http://127.0.0.1:5050. Sin la firma de Django responden `health`, `openapi.json` y el catálogo;
las rutas con datos de usuarios devuelven 503 (falta la clave interna) o 401 (firma ausente o inválida).

Con Docker se levanta junto a Django (ver el README de `Proyecto/`):

```powershell
docker compose -f docker-compose.yml -f docker-compose.api.yml up -d --build
```

Las pruebas de integración de Django con la API están en `core/tests/test_api.py`. GitHub Actions
(`.github/workflows/pruebas.yml`) ejecuta pytest de la API y las pruebas de Django en cada push.

Si cambias un endpoint, regenera los ejemplos de la documentación con `python scripts/completar_openapi.py`
(llama a la API con una base de prueba y copia las respuestas reales).

## Probar la API en GitHub Codespaces

```bash
cd /workspaces/PAGINARECTM/Proyecto/backend_flask
pip install -r requirements.txt
APP_HOST=0.0.0.0 python run.py
```

Luego, en la pestaña **Puertos**, abre el puerto **5050**: se verá la consola en `/consola`.
