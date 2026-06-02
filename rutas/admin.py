from django.contrib import admin

from .models import RutaAprendizaje, RutaDiaProgreso


@admin.register(RutaAprendizaje)
class RutaAprendizajeAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "titulo",
        "estilo_vark_usado",
        "dias_hasta_examen",
        "dias_planificados",
        "minutos_por_dia",
        "actualizado",
    )
    search_fields = (
        "user__username",
        "user__email",
        "titulo",
        "resumen_general",
        "temas_priorizados",
    )
    readonly_fields = (
        "creado",
        "actualizado",
    )


@admin.register(RutaDiaProgreso)
class RutaDiaProgresoAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "ruta",
        "dia",
        "completado",
        "quiz_puntaje",
        "quiz_total",
        "actualizado",
    )
    list_filter = ("completado", "actualizado")
    search_fields = ("user__username", "user__email", "ruta__titulo", "notas")
    readonly_fields = ("creado", "actualizado")
