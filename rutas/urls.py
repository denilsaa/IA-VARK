from django.urls import path

from . import views

app_name = "rutas"

urlpatterns = [
    path("", views.ruta_aprendizaje, name="ruta_aprendizaje"),
    path("progreso/", views.actualizar_progreso_ruta, name="actualizar_progreso"),
]
