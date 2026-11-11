#!/bin/sh
set -e

# Única base oficial: /data/db.sqlite3 (volumen persistente). Antes de tocarla se guarda un respaldo fechado en ./backups.
if [ -f "${DJANGO_DB_PATH:-/data/db.sqlite3}" ]; then
  python manage.py respaldar_bd --mantener 20 || echo "AVISO: no se pudo respaldar la base."
fi

# Crea/actualiza las tablas (idempotente).
python manage.py migrate --noinput

# Catálogo inicial desde data/*.csv (cultivos, zona Melipilla e insumos de referencia, con sus categorías).
# Carga CONTROLADA: solo importa si los CSV cambiaron desde la última carga registrada (tabla CargaCatalogo);
# un reinicio normal no importa nada. Nunca duplica, sobrescribe ni borra registros existentes.
# Si falla, la aplicación igual arranca y el aviso queda en el log.
python manage.py cargar_catalogo_inicial data || echo "AVISO: no se pudo cargar el catálogo inicial desde data/ (revisa los CSV)."

# Deja en el log qué base se está usando y cuánto contiene.
python manage.py estado_bd || true

exec "$@"
