from django.conf import settings
from django.db import models
from django.utils import timezone


class DatosAcademicos(models.Model):
    TIPO_EXAMEN_CHOICES = [
        ("opcion_multiple", "Opción múltiple"),
        ("oral", "Oral"),
        ("escrito", "Escrito"),
        ("practico", "Práctico"),
        ("mixto", "Mixto"),
    ]

    DIFICULTAD_CHOICES = [
        ("baja", "Baja"),
        ("media", "Media"),
        ("alta", "Alta"),
        ("muy_alta", "Muy alta"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="datos_academicos",
    )

    materia = models.CharField(
        max_length=120,
        default="Anatomía I",
    )

    tema_actual = models.CharField(
        max_length=180,
        help_text="Ejemplo: Sistema óseo, cráneo, músculos del miembro superior.",
    )

    fecha_inicio = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha desde la que empezará a estudiar.",
    )

    fecha_examen = models.DateField(
        help_text="Fecha del próximo examen.",
    )

    minutos_por_dia = models.PositiveIntegerField(
        default=60,
        help_text="Minutos disponibles para estudiar por día.",
    )

    tipo_examen = models.CharField(
        max_length=30,
        choices=TIPO_EXAMEN_CHOICES,
        default="mixto",
    )

    nivel_dificultad = models.CharField(
        max_length=20,
        choices=DIFICULTAD_CHOICES,
        default="media",
    )

    temas_dificiles = models.TextField(
        blank=True,
        help_text="Temas que más le cuestan al estudiante.",
    )

    objetivo_estudio = models.TextField(
        blank=True,
        help_text="Meta del estudiante para este periodo de estudio.",
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Datos académicos"
        verbose_name_plural = "Datos académicos"

    def __str__(self):
        return f"{self.user.username} - {self.materia}"

    @property
    def dias_restantes(self):
        hoy = timezone.localdate()

        if self.fecha_examen < hoy:
            return 0

        return (self.fecha_examen - hoy).days

    @property
    def fecha_examen_formateada(self):
        return self.fecha_examen.strftime("%d/%m/%Y")

    @property
    def tiempo_estudio_display(self):
        if self.minutos_por_dia < 60:
            return f"{self.minutos_por_dia} min"

        horas = self.minutos_por_dia // 60
        minutos = self.minutos_por_dia % 60

        if minutos == 0:
            return f"{horas} h"

        return f"{horas} h {minutos} min"