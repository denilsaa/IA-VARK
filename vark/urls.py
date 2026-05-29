from django.urls import path

from . import views

app_name = "vark"

urlpatterns = [
    path("test/", views.test_vark, name="test"),
    path("desempate/", views.desempate_vark, name="desempate"),
    path("resultado/", views.resultado_vark, name="resultado"),
]