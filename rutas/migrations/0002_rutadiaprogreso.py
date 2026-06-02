# Generated manually for RutaDiaProgreso

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("rutas", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RutaDiaProgreso",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dia", models.PositiveIntegerField()),
                ("completado", models.BooleanField(default=False)),
                ("quiz_puntaje", models.PositiveIntegerField(blank=True, null=True)),
                ("quiz_total", models.PositiveIntegerField(blank=True, null=True)),
                ("notas", models.TextField(blank=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                ("ruta", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="progresos_dias", to="rutas.rutaaprendizaje")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="progresos_ruta", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Progreso diario de ruta",
                "verbose_name_plural": "Progresos diarios de ruta",
                "ordering": ["dia"],
                "unique_together": {("user", "ruta", "dia")},
            },
        ),
    ]
