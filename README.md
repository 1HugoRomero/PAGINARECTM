# AgroAsesor

Página web para que agricultores registren sus predios y potreros en un mapa, planifiquen labores y
calculen semillas e insumos usando solo datos con fuente verificada.

- **Django + SQLite**: toda la página (cuentas, predios, mapa, calendario, actividades, calculadoras,
  reportes y panel de administración).
- **`backend_flask/`**: API Flask de solo lectura que Django usa por detrás en `/api/v1/`.
  Ver [backend_flask/README.md](backend_flask/README.md).

## Estructura

```text
Proyecto/
├── AgroAsesor/          configuración de Django (settings, urls)
├── core/                la aplicación
│   ├── models.py        tablas: predios, potreros, temporadas, actividades, catálogo, cálculos
│   ├── views.py         páginas y respuestas JSON
│   ├── forms.py         formularios y validaciones
│   ├── validators.py    RUT, teléfono y otros datos de entrada
│   ├── agronomy.py      ventanas de siembra/cosecha y evaluación de fechas del calendario
│   ├── catalog.py       catálogo de cultivos e insumos para las páginas
│   ├── seasons.py       temporadas de cultivo de cada potrero
│   ├── geometry.py      área y perímetro de los polígonos del mapa
│   ├── auth.py          acceso con correo o usuario y manejo de sesión vencida
│   ├── api_gateway.py   puente firmado hacia la API Flask
│   ├── estadisticas.py  números del panel de administración
│   ├── dbutils.py       ruta de la base de datos y respaldos
│   ├── admin.py         Django Admin
│   ├── management/      comandos de consola (catálogo, base de datos, administradores)
│   ├── templates/       HTML
│   ├── static/          CSS, JS e imágenes
│   └── tests/           pruebas
├── data/                CSV del catálogo agrícola real
├── data_demo/           catálogo ficticio que usan las pruebas
└── backend_flask/       API Flask
```

## Ejecutar con Docker (forma oficial)

```powershell
cd Proyecto
docker compose up -d --build
```

Luego abre http://localhost:8000/.

La base de datos oficial es `/data/db.sqlite3`, dentro del volumen `agroasesor_hugo_agroasesor_data`.
Sobrevive a `docker compose down`, a reconstruir la imagen y a reiniciar el PC. **Nunca** uses
`docker compose down -v` ni borres ese volumen: se pierde la base. Cada vez que el contenedor arranca
hace un respaldo en `backups/` (guarda los últimos 20), aplica las migraciones y carga el catálogo de `data/`.

| Para qué | Comando |
|---|---|
| Ver qué base se usa y cuánto contiene | `docker exec agroasesor_hugo python manage.py estado_bd` |
| Hacer un respaldo ahora | `docker exec agroasesor_hugo python manage.py respaldar_bd` |
| Crear una cuenta de administrador | `docker exec -it agroasesor_hugo python manage.py createsuperuser` |
| Dar o quitar el rol de administrador | `docker exec agroasesor_hugo python manage.py administradores` |

Para levantar también la API Flask, define `AGROASESOR_INTERNAL_SECRET` en `.env` y usa:

```powershell
docker compose -f docker-compose.yml -f docker-compose.api.yml up -d --build
```

## Ejecutar sin Docker (desarrollo)

Requiere Python 3.12 o superior. Desde la carpeta del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r Proyecto/requirements.txt
Copy-Item Proyecto/.env.example Proyecto/.env   # solo la primera vez
.\.venv\Scripts\python.exe Proyecto/manage.py migrate
.\.venv\Scripts\python.exe Proyecto/manage.py createsuperuser
.\.venv\Scripts\python.exe Proyecto/manage.py runserver
```

Así se usa un `db.sqlite3` local, que **no** es la base oficial (Django lo avisa al arrancar).

## Variables de entorno

Se definen en `Proyecto/.env` (parte copiando `.env.example`). Ese archivo no se sube a Git.

| Variable | Para qué |
|---|---|
| `DJANGO_SECRET_KEY` | clave secreta; obligatoria con `DJANGO_DEBUG=False` |
| `DJANGO_DEBUG` | `True` en desarrollo, `False` en producción (activa cookies seguras) |
| `DJANGO_ALLOWED_HOSTS` | dominios permitidos, separados por coma |
| `MAP_TILE_URL`, `MAP_TILE_ATTRIBUTION` | proveedor de mapas (por defecto OpenStreetMap.de) |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | correo para recuperar la contraseña (en local se imprime en la consola) |
| `AGROASESOR_API_URL`, `AGROASESOR_INTERNAL_SECRET` | conexión con la API Flask; sin ellas `/api/v1/` responde 503 |

## Catálogo agrícola

Zonas, cultivos, problemas, insumos y referencias se cargan desde los CSV de `data/` o desde `/admin/`.
Ningún dato técnico se inventa: completa cada fila solo con valores de una fuente oficial
(SAG, ODEPA, INIA o la etiqueta del fabricante).

```powershell
python manage.py importar_catalogo --categorias                   # categorías de insumo (una vez)
python manage.py importar_catalogo data                           # solo valida, no guarda
python manage.py importar_catalogo data --aplicar                 # guarda
python manage.py importar_catalogo data --aplicar --actualizar    # además corrige registros existentes
```

- Separador `;` o `,`, UTF-8, decimales con coma o punto y fechas `AAAA-MM-DD`.
- Las listas (problemas, cultivos, objetivos de control) van separadas por `|`. Una celda vacía significa «sin dato».
- El orden de carga es zonas → cultivos → problemas → insumos → usos → calendario y rendimientos.
- Es seguro repetirlo: no duplica registros ni borra valores guardados.

## Pruebas

```powershell
.\.venv\Scripts\python.exe Proyecto/manage.py test core
```

Las pruebas de la API Flask están en `backend_flask/tests` (ver su README).
