from django.urls import path

from . import views

app_name = "vark"

urlpatterns = [
    path("test/", views.test, name="test"),
    path("resultado/", views.resultado, name="resultado"),
]
