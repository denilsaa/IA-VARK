from django.conf import settings
from django.db import models


class PerfilVARK(models.Model):
    ESTILO_VISUAL = "visual"
    ESTILO_AUDITIVO = "auditivo"
    ESTILO_LECTURA = "lectura"
    ESTILO_KINESTESICO = "kinestesico"

    ESTILOS = [
        (ESTILO_VISUAL, "Visual"),
        (ESTILO_AUDITIVO, "Auditivo"),
        (ESTILO_LECTURA, "Lectura/Escritura"),
        (ESTILO_KINESTESICO, "Kinestésico"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_vark",
    )

    puntaje_visual = models.PositiveIntegerField(default=0)
    puntaje_auditivo = models.PositiveIntegerField(default=0)
    puntaje_lectura = models.PositiveIntegerField(default=0)
    puntaje_kinestesico = models.PositiveIntegerField(default=0)

    estilo_principal = models.CharField(
        max_length=20,
        choices=ESTILOS,
        default=ESTILO_VISUAL,
    )

    fecha_realizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Perfil VARK"
        verbose_name_plural = "Perfiles VARK"

    def __str__(self):
        return f"{self.user.username} - {self.get_estilo_principal_display()}"

    @property
    def total_puntaje(self):
        return (
            self.puntaje_visual
            + self.puntaje_auditivo
            + self.puntaje_lectura
            + self.puntaje_kinestesico
        )

    @property
    def estilo_display(self):
        return self.get_estilo_principal_display()

    def obtener_porcentaje(self, estilo):
        total = self.total_puntaje

        if total == 0:
            return 0

        puntajes = {
            self.ESTILO_VISUAL: self.puntaje_visual,
            self.ESTILO_AUDITIVO: self.puntaje_auditivo,
            self.ESTILO_LECTURA: self.puntaje_lectura,
            self.ESTILO_KINESTESICO: self.puntaje_kinestesico,
        }

        return round((puntajes.get(estilo, 0) / total) * 100)