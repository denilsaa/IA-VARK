from django.conf import settings
from django.db import models


class ExamenGenerado(models.Model):
    ESTADO_GENERADO = "generado"
    ESTADO_RESPONDIDO = "respondido"

    ESTADO_CHOICES = [
        (ESTADO_GENERADO, "Generado"),
        (ESTADO_RESPONDIDO, "Respondido"),
    ]

    DIFICULTAD_BAJA = "baja"
    DIFICULTAD_MEDIA = "media"
    DIFICULTAD_ALTA = "alta"

    DIFICULTAD_CHOICES = [
        (DIFICULTAD_BAJA, "Baja"),
        (DIFICULTAD_MEDIA, "Media"),
        (DIFICULTAD_ALTA, "Alta"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="examenes_generados",
    )

    ruta = models.ForeignKey(
        "rutas.RutaAprendizaje",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="examenes",
    )

    titulo = models.CharField(
        max_length=220,
        default="Simulacro de Anatomía I",
    )

    instrucciones = models.TextField(blank=True)

    dificultad = models.CharField(
        max_length=20,
        choices=DIFICULTAD_CHOICES,
        default=DIFICULTAD_MEDIA,
    )

    cantidad_preguntas = models.PositiveIntegerField(default=10)

    preguntas_json = models.JSONField(
        default=list,
        blank=True,
        help_text="Preguntas generadas por Gemini.",
    )

    respuestas_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Respuestas del estudiante y corrección.",
    )

    puntaje = models.PositiveIntegerField(default=0)
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    retroalimentacion_ia = models.TextField(blank=True)

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_GENERADO,
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Examen generado"
        verbose_name_plural = "Exámenes generados"
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.titulo} - {self.user.username}"

    @property
    def preguntas(self):
        if isinstance(self.preguntas_json, list):
            return self.preguntas_json

        return []

    @property
    def total_preguntas(self):
        return len(self.preguntas)

    @property
    def esta_respondido(self):
        return self.estado == self.ESTADO_RESPONDIDO

    @property
    def resultados(self):
        respuestas = self.respuestas_json or {}
        resultados = []

        for pregunta in self.preguntas:
            pregunta_id = str(pregunta.get("id"))
            respuesta = respuestas.get(pregunta_id, {})

            resultados.append(
                {
                    "id": pregunta.get("id"),
                    "tema": pregunta.get("tema", ""),
                    "enunciado": pregunta.get("enunciado", ""),
                    "opciones": pregunta.get("opciones", []),
                    "respuesta_correcta": pregunta.get("respuesta_correcta", ""),
                    "respuesta_usuario": respuesta.get("respuesta_usuario", ""),
                    "es_correcta": respuesta.get("es_correcta", False),
                    "explicacion": pregunta.get("explicacion", ""),
                }
            )

        return resultados