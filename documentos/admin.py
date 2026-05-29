from django.contrib import admin

from .models import MaterialEstudio


@admin.register(MaterialEstudio)
class MaterialEstudioAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "user",
        "tipo",
        "tema",
        "estado",
        "creado",
    )
    search_fields = (
        "titulo",
        "tema",
        "descripcion",
        "user__username",
        "user__email",
    )
    list_filter = (
        "tipo",
        "estado",
        "creado",
    )
    readonly_fields = (
        "creado",
        "actualizado",
    )