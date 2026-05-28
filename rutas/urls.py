from django.urls import path

from . import views

app_name = "rutas"

urlpatterns = [
    path("ruta-aprendizaje/", views.ruta_aprendizaje, name="ruta_aprendizaje"),
]
