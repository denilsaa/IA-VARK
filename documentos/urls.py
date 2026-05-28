from django.urls import path

from . import views

app_name = "documentos"

urlpatterns = [
    path("subir/", views.subir, name="subir"),
    path("materiales/", views.lista, name="lista"),
]
