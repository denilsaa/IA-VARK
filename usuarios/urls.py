from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("progreso/", views.progreso, name="progreso"),
    path("redireccion/", views.redireccion_post_login, name="redireccion_post_login"),
]
