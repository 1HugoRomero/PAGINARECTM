#!/bin/sh
set -e

# Única base oficial: /data/db.sqlite3 (volumen persistente). Antes de tocarla se guarda un respaldo fechado en ./backups.
if [ -f "${DJANGO_DB_PATH:-/data/db.sqlite3}" ]; then
  python manage.py respaldar_bd --mantener 20 || echo "AVISO: no se pudo respaldar la base."
fi

# Crea/actualiza las tablas y asegura las categorías base de insumos (ambos pasos son idempotentes).
python manage.py migrate --noinput
python manage.py importar_catalogo --categorias

# Catálogo inicial desde data/*.csv: cultivos y zona Melipilla (solo nombres; sin densidades, dosis ni fuentes inventadas).
# Es idempotente: lo que ya existe no se modifica. Si falla, la aplicación igual arranca y el aviso queda en el log.
python manage.py importar_catalogo data --aplicar || echo "AVISO: no se pudo importar el catálogo inicial desde data/ (revisa los CSV)."

# Deja en el log qué base se está usando y cuánto contiene.
python manage.py estado_bd || true

exec "$@"
