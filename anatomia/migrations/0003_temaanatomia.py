# Generated manually for Render deployment.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("anatomia", "0002_remove_datosacademicos_horas_por_dia_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="TemaAnatomia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.SlugField(max_length=120, unique=True)),
                ("nombre", models.CharField(max_length=180)),
                ("descripcion", models.TextField(blank=True)),
                ("pagina_inicio", models.PositiveIntegerField(blank=True, null=True)),
                ("pagina_fin", models.PositiveIntegerField(blank=True, null=True)),
                ("orden", models.PositiveIntegerField(default=0)),
                ("activo", models.BooleanField(default=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                (
                    "tema_padre",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subtemas",
                        to="anatomia.temaanatomia",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tema de Anatomía I",
                "verbose_name_plural": "Temas de Anatomía I",
                "ordering": ["tema_padre__orden", "orden", "nombre"],
            },
        ),
    ]
