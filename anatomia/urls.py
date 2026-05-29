from django.urls import path

from . import views

app_name = "anatomia"

urlpatterns = [
    path("datos-academicos/", views.datos_academicos, name="datos_academicos"),
]