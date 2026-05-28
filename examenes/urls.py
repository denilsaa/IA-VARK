from django.urls import path

from . import views

app_name = "examenes"

urlpatterns = [
    path("generar/", views.generar, name="generar"),
    path("resolver/", views.resolver, name="resolver"),
    path("resultado/", views.resultado, name="resultado"),
]
