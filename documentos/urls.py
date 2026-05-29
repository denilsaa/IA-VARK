from django.urls import path

from . import views

app_name = "documentos"

urlpatterns = [
    path("subir/", views.subir_material, name="subir"),
    path("lista/", views.lista_materiales, name="lista"),
    path("<int:pk>/", views.detalle_material, name="detalle"),
    path("<int:pk>/eliminar/", views.eliminar_material, name="eliminar"),
]