# Registro de cargas controladas del catálogo inicial (solo agrega una tabla; no toca datos existentes).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_agricultor_rut_opcional"),
    ]

    operations = [
        migrations.CreateModel(
            name="CargaCatalogo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("huella", models.CharField(db_index=True, max_length=64)),
                ("carpeta", models.CharField(max_length=255)),
                ("archivos", models.JSONField(default=list)),
                ("resumen", models.TextField(blank=True)),
                ("forzada", models.BooleanField(default=False)),
                ("aplicada", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "carga del catálogo inicial",
                "verbose_name_plural": "cargas del catálogo inicial",
                "ordering": ["-aplicada", "-pk"],
            },
        ),
    ]
