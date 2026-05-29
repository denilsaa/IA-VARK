import os

from django.conf import settings
from django.db import models


def ruta_material_usuario(instance, filename):
    nombre_base, extension = os.path.splitext(filename)
    extension = extension.lower()
    return f"materiales/usuario_{instance.user.id}/{nombre_base}{extension}"


class MaterialEstudio(models.Model):
    TIPO_PDF = "pdf"
    TIPO_WORD = "word"
    TIPO_IMAGEN = "imagen"
    TIPO_TEXTO = "texto"
    TIPO_OTRO = "otro"

    TIPO_CHOICES = [
        (TIPO_PDF, "PDF"),
        (TIPO_WORD, "Word"),
        (TIPO_IMAGEN, "Imagen"),
        (TIPO_TEXTO, "Texto manual"),
        (TIPO_OTRO, "Otro"),
    ]

    ESTADO_PENDIENTE = "pendiente"
    ESTADO_PROCESANDO = "procesando"
    ESTADO_PROCESADO = "procesado"
    ESTADO_ERROR = "error"

    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_PROCESANDO, "Procesando"),
        (ESTADO_PROCESADO, "Procesado"),
        (ESTADO_ERROR, "Error"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="materiales_estudio",
    )

    titulo = models.CharField(max_length=180)

    tema = models.CharField(
        max_length=180,
        blank=True,
        help_text="Tema general relacionado con el material.",
    )

    temario_examen = models.TextField(
        blank=True,
        default="",
        help_text="Temas específicos que entrarán al examen.",
    )

    descripcion = models.TextField(blank=True)

    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default=TIPO_OTRO,
    )

    archivo = models.FileField(
        upload_to=ruta_material_usuario,
        null=True,
        blank=True,
    )

    texto_manual = models.TextField(
        blank=True,
        help_text="Campo conservado para materiales antiguos.",
    )

    texto_extraido = models.TextField(
        blank=True,
        help_text="Texto extraído del archivo.",
    )

    resumen_ia = models.TextField(
        blank=True,
        help_text="Resumen generado por Gemini.",
    )

    temas_clave_ia = models.TextField(
        blank=True,
        help_text="Temas clave detectados por Gemini.",
    )

    preguntas_sugeridas_ia = models.TextField(
        blank=True,
        help_text="Preguntas sugeridas por Gemini.",
    )

    recomendacion_ia = models.TextField(
        blank=True,
        help_text="Recomendación generada por Gemini.",
    )

    error_procesamiento = models.TextField(
        blank=True,
        help_text="Mensaje de error si el procesamiento falla.",
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE,
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Material de estudio"
        verbose_name_plural = "Materiales de estudio"
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.titulo} - {self.user.username}"

    @property
    def nombre_archivo(self):
        if not self.archivo:
            return "Sin archivo"

        return os.path.basename(self.archivo.name)

    @property
    def tiene_contenido(self):
        return bool(self.archivo or self.texto_manual)

    @property
    def tiene_analisis_ia(self):
        return bool(
            self.resumen_ia
            or self.temas_clave_ia
            or self.preguntas_sugeridas_ia
            or self.recomendacion_ia
        )

    @property
    def tipo_icono(self):
        iconos = {
            self.TIPO_PDF: "file-text",
            self.TIPO_WORD: "file-type",
            self.TIPO_IMAGEN: "image",
            self.TIPO_TEXTO: "align-left",
            self.TIPO_OTRO: "file",
        }

        return iconos.get(self.tipo, "file")