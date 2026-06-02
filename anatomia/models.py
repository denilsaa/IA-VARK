from django.conf import settings
from django.db import models
from django.utils import timezone


class TemaAnatomia(models.Model):
    """
    Dataset interno de temas de Anatomía I.
    Los temas principales y subtemas están basados en el índice del libro base
    Rouvière y Delmas, Anatomía Humana. Tomo 2: Tronco.
    """

    codigo = models.SlugField(max_length=120, unique=True)
    nombre = models.CharField(max_length=180)
    tema_padre = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="subtemas",
    )
    descripcion = models.TextField(blank=True)
    pagina_inicio = models.PositiveIntegerField(null=True, blank=True)
    pagina_fin = models.PositiveIntegerField(null=True, blank=True)
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tema de Anatomía I"
        verbose_name_plural = "Temas de Anatomía I"
        ordering = ["tema_padre__orden", "orden", "nombre"]

    def __str__(self):
        if self.tema_padre:
            return f"{self.tema_padre.nombre} > {self.nombre}"
        return self.nombre

    @property
    def es_tema_principal(self):
        return self.tema_padre_id is None

    @property
    def referencia_paginas(self):
        if self.pagina_inicio and self.pagina_fin:
            return f"págs. {self.pagina_inicio}-{self.pagina_fin}"
        if self.pagina_inicio:
            return f"pág. {self.pagina_inicio}"
        return "Sin referencia de página"

    @classmethod
    def temas_principales(cls):
        return cls.objects.filter(tema_padre__isnull=True, activo=True).order_by("orden", "nombre")


class DatosAcademicos(models.Model):
    TIPO_EXAMEN_CHOICES = [
        ("opcion_multiple", "Opción múltiple"),
        ("oral", "Oral"),
        ("escrito", "Escrito"),
        ("practico", "Práctico"),
        ("mixto", "Mixto"),
    ]

    # Se mantiene en BD para no romper datos anteriores, pero ya no se muestra ni se usa.
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
        help_text="Tema principal seleccionado desde el dataset de Anatomía I.",
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
        default=30,
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
        help_text="Subtema o punto específico que más le cuesta al estudiante.",
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
