from django.contrib import admin

from .models import DatosAcademicos, TemaAnatomia


@admin.register(TemaAnatomia)
class TemaAnatomiaAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "tema_padre",
        "orden",
        "pagina_inicio",
        "pagina_fin",
        "activo",
    )
    list_filter = ("activo", "tema_padre")
    search_fields = ("nombre", "codigo", "descripcion")
    prepopulated_fields = {"codigo": ("nombre",)}
    ordering = ("tema_padre__orden", "orden", "nombre")


@admin.register(DatosAcademicos)
class DatosAcademicosAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "materia",
        "tema_actual",
        "fecha_examen",
        "minutos_por_dia",
        "tipo_examen",
        "actualizado",
    )
    search_fields = (
        "user__username",
        "user__email",
        "materia",
        "tema_actual",
        "temas_dificiles",
    )
    list_filter = (
        "materia",
        "tipo_examen",
        "fecha_examen",
    )
    readonly_fields = (
        "creado",
        "actualizado",
    )
