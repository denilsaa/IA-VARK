from django.conf import settings
from django.db import models


class RutaAprendizaje(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ruta_aprendizaje",
    )

    materiales = models.ManyToManyField(
        "documentos.MaterialEstudio",
        blank=True,
        related_name="rutas_aprendizaje",
    )

    titulo = models.CharField(
        max_length=200,
        default="Ruta de aprendizaje personalizada",
    )

    resumen_general = models.TextField(blank=True)

    estilo_vark_usado = models.CharField(
        max_length=80,
        blank=True,
    )

    dias_hasta_examen = models.PositiveIntegerField(default=0)

    dias_planificados = models.PositiveIntegerField(default=0)

    minutos_por_dia = models.PositiveIntegerField(default=60)

    temas_priorizados = models.TextField(
        blank=True,
        help_text="Temas priorizados por Gemini.",
    )

    plan_json = models.JSONField(
        default=list,
        blank=True,
        help_text="Plan diario generado por Gemini.",
    )

    recomendaciones_finales = models.TextField(blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ruta de aprendizaje"
        verbose_name_plural = "Rutas de aprendizaje"

    def __str__(self):
        return f"Ruta de {self.user.username}"

    @property
    def plan_diario(self):
        if isinstance(self.plan_json, list):
            return self.plan_json

        return []

    @property
    def temas_priorizados_lista(self):
        return [
            linea.strip()
            for linea in self.temas_priorizados.splitlines()
            if linea.strip()
        ]

    @property
    def recomendaciones_lista(self):
        return [
            linea.strip()
            for linea in self.recomendaciones_finales.splitlines()
            if linea.strip()
        ]