from django.urls import path

from . import views

app_name = "examenes"

urlpatterns = [
    path("", views.lista_examenes, name="lista"),
    path("generar/", views.generar_examen, name="generar"),
    path("<int:pk>/rendir/", views.rendir_examen, name="rendir"),
    path("<int:pk>/resultado/", views.resultado_examen, name="resultado"),
]