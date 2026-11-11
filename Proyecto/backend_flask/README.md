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

Funcionan:

- `GET /api/v1/health` y `GET /api/v1/openapi.json`
- `GET /api/v1/usuarios/me`, `/predios`, `/predios/{id}`, `/predios/{id}/potreros`, `/potreros/{id}` y `/calculos`
- `GET /api/v1/cultivos`, `/cultivos/{id}`, `/insumos`, `/insumos/{id}` y `/zonas`
- Catálogo: `GET /api/v1/catalogo/categorias`, `/catalogo/fuentes`, `/catalogo/productos`,
  `/catalogo/productos/{id}`, `/catalogo/referencias-siembra` y `POST /api/v1/catalogo/calcular-sacos`
- Página de prueba del catálogo: `GET /catalogo`
- **Fertilizantes** (públicos, sin sesión):
  - `GET /api/v1/catalogo/fertilizantes` (filtros `nutriente`, `grupo`, `q`), `/catalogo/fertilizantes/{id}` y
    `/catalogo/fertilizantes/resumen`: 19 fertilizantes con su composición en % de N, P2O5, K2O, Mg y S, el cuadro
    y la página de la fuente y si el valor fue cotejado.
  - `POST /api/v1/catalogo/calcular-fertilizante`: kilos de producto para cubrir el requerimiento de nutriente que
    indica el usuario (no recomienda dosis). Si la fuente da un rango, pide la ley que declara la etiqueta.
  - `GET /api/v1/catalogo/conversiones` y `/catalogo/convertir?de=P2O5&a=P&valor=46`: factores P2O5↔P y K2O↔K.
  - `GET /api/v1/catalogo/normativa/contenidos-minimos` y `POST /api/v1/catalogo/revisar-etiqueta`: contenidos
    mínimos de nutrientes de la Resolución SAG N° 8.651 exenta de 2024.
- Consola para probar la API y ver las respuestas: `GET /consola` (la raíz `/` redirige ahí)

Fuentes de los fertilizantes (`data/fertilizantes.yaml`): FAO/IFA, *Los fertilizantes y su uso*, 4.ª ed., 2002
(Cuadros 2 y 3, pp. 38-39; Anexo de conversiones, p. 77) y Resolución SAG N° 8.651 exenta, Diario Oficial del
18-12-2024 (numeral 3.1.2, Grupo 2). Revisadas el 11-11-2026.

El resto de las rutas de `openapi.yaml` (registro y login, escrituras, actividades, temporadas, calendario,
predicciones, reportes, administración y cálculos de semillas, fertilizantes y cobertura) responde **501**:
están definidas pero todavía no tienen lógica.

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
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe run.py
```

Escucha en http://127.0.0.1:5050. Sin la firma de Django responden `health`, `openapi.json` y el catálogo;
las rutas con datos de usuarios devuelven 503 (falta la clave interna) o 401 (firma ausente o inválida).

Con Docker se levanta junto a Django (ver el README de `Proyecto/`):

```powershell
docker compose -f docker-compose.yml -f docker-compose.api.yml up -d --build
```

Las pruebas de integración de Django con la API están en `core/tests/test_api.py`.

## Probar la API en GitHub Codespaces

```bash
cd /workspaces/PAGINARECTM/Proyecto/backend_flask
pip install -r requirements.txt
APP_HOST=0.0.0.0 python run.py
```

Luego, en la pestaña **Puertos**, abre el puerto **5050**: se verá la consola en `/consola`.
