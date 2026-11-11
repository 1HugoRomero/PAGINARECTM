"""Carga CONTROLADA del catálogo inicial desde data/*.csv (cultivos, zona, insumos…).

Uso:
    python manage.py cargar_catalogo_inicial            # carga data/ solo si los CSV cambiaron
    python manage.py cargar_catalogo_inicial --simular  # muestra qué haría, sin guardar
    python manage.py cargar_catalogo_inicial --forzar   # vuelve a pasar por los CSV aunque no hayan cambiado

Cómo decide:
- Calcula la huella SHA-256 de los CSV reconocidos. Si ya hay una carga registrada con esa misma huella
  (tabla CargaCatalogo), no hace nada: reiniciar Django o el contenedor no vuelve a importar.
- Si la huella es nueva, ejecuta ``importar_catalogo <carpeta> --aplicar`` (atómico) y registra la carga.

Garantías (las da importar_catalogo sin --actualizar):
- No duplica: un registro con el mismo nombre (y tipo, en insumos) se deja como está.
- No sobrescribe: los registros existentes, incluidos los editados o creados por personas, no se modifican.
- No elimina nada.
"""

import hashlib
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.management.commands.importar_catalogo import CSV_SECTIONS
from core.models import CargaCatalogo


def archivos_catalogo(carpeta):
    return sorted(p for p in Path(carpeta).glob('*.csv') if p.stem.casefold() in CSV_SECTIONS)


def huella_catalogo(archivos):
    """SHA-256 del nombre y el contenido de cada CSV (en orden): cambia si cambia cualquier archivo."""
    h = hashlib.sha256()
    for path in archivos:
        h.update(path.name.encode('utf-8') + b'\0')
        h.update(path.read_bytes().replace(b'\r\n', b'\n') + b'\0')
    return h.hexdigest()


class Command(BaseCommand):
    help = 'Carga el catálogo inicial (data/*.csv) solo si cambió desde la última carga registrada.'

    def add_arguments(self, parser):
        parser.add_argument('carpeta', nargs='?', default=str(Path(settings.BASE_DIR) / 'data'))
        parser.add_argument('--forzar', action='store_true', help='Vuelve a importar aunque la huella no haya cambiado.')
        parser.add_argument('--simular', action='store_true', help='Valida y muestra el resultado sin guardar nada.')

    def handle(self, *args, **options):
        carpeta = Path(options['carpeta'])
        if not carpeta.is_dir():
            raise CommandError(f'No existe la carpeta {carpeta}.')
        archivos = archivos_catalogo(carpeta)
        if not archivos:
            raise CommandError(f'La carpeta {carpeta} no contiene CSV reconocidos.')
        huella = huella_catalogo(archivos)
        ya_cargada = CargaCatalogo.objects.filter(huella=huella).exists()
        if ya_cargada and not options['forzar']:
            self.stdout.write(f'Catálogo inicial sin cambios (huella {huella[:12]}): no se importa nada.')
            return

        salida = StringIO()
        argumentos = [str(carpeta)] + ([] if options['simular'] else ['--aplicar'])
        with transaction.atomic():
            call_command('importar_catalogo', *argumentos, stdout=salida)
            if not options['simular']:
                CargaCatalogo.objects.create(
                    huella=huella,
                    carpeta=carpeta.name,
                    archivos=[p.name for p in archivos],
                    resumen=salida.getvalue().strip(),
                    forzada=bool(options['forzar'] and ya_cargada),
                )
        self.stdout.write(salida.getvalue().rstrip())
        if options['simular']:
            self.stdout.write(self.style.WARNING('Simulación: no se guardó nada.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Catálogo inicial cargado y registrado (huella {huella[:12]}).'))
