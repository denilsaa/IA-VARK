from django.contrib import admin

from .models import ExamenGenerado


@admin.register(ExamenGenerado)
class ExamenGeneradoAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "user",
        "dificultad",
        "cantidad_preguntas",
        "puntaje",
        "porcentaje",
        "estado",
        "creado",
    )

    search_fields = (
        "titulo",
        "user__username",
        "user__email",
        "instrucciones",
        "retroalimentacion_ia",
    )

    list_filter = (
        "estado",
        "dificultad",
        "creado",
    )

    readonly_fields = (
        "creado",
        "actualizado",
    )