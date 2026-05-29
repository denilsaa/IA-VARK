from django.contrib import admin

from .models import PerfilVARK


@admin.register(PerfilVARK)
class PerfilVARKAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "estilo_principal",
        "puntaje_visual",
        "puntaje_auditivo",
        "puntaje_lectura",
        "puntaje_kinestesico",
        "fecha_realizacion",
    )
    search_fields = ("user__username", "user__email")
    list_filter = ("estilo_principal", "fecha_realizacion")
    readonly_fields = ("fecha_realizacion",)