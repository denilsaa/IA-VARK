from django.contrib import admin

from .models import DatosAcademicos


@admin.register(DatosAcademicos)
class DatosAcademicosAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "materia",
        "tema_actual",
        "fecha_examen",
        "minutos_por_dia",
        "tipo_examen",
        "nivel_dificultad",
        "actualizado",
    )
    search_fields = (
        "user__username",
        "user__email",
        "materia",
        "tema_actual",
    )
    list_filter = (
        "materia",
        "tipo_examen",
        "nivel_dificultad",
        "fecha_examen",
    )
    readonly_fields = (
        "creado",
        "actualizado",
    )