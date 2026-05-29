from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from vark.models import PerfilVARK


def home(request):
    if request.user.is_authenticated:
        return redirect("usuarios:redireccion_post_login")

    return render(request, "home.html")


@login_required
def dashboard(request):
    perfil_vark = PerfilVARK.objects.filter(user=request.user).first()

    if perfil_vark:
        estilo_vark = perfil_vark.estilo_display
    else:
        estilo_vark = "Pendiente"

    resumen = {
        "estilo_vark": estilo_vark,
        "proximo_examen": "Pendiente",
        "fecha_examen": "Sin registrar",
        "materiales": 0,
        "ruta_activa": "Sin ruta activa",
        "ultimo_puntaje": "Sin simulacros",
    }

    accesos = [
        {
            "label": "Test VARK",
            "url": reverse("vark:test"),
            "icon": "scan-eye",
        },
        {
            "label": "Datos académicos",
            "url": reverse("anatomia:datos_academicos"),
            "icon": "clipboard-list",
        },
        {
            "label": "Subir material",
            "url": reverse("documentos:subir"),
            "icon": "upload-cloud",
        },
        {
            "label": "Ver ruta",
            "url": reverse("rutas:ruta_aprendizaje"),
            "icon": "route",
        },
        {
            "label": "Generar examen",
            "url": reverse("examenes:generar"),
            "icon": "file-question",
        },
        {
            "label": "Ver progreso",
            "url": reverse("usuarios:progreso"),
            "icon": "trending-up",
        },
    ]

    return render(
        request,
        "dashboard.html",
        {
            "resumen": resumen,
            "accesos": accesos,
            "perfil_vark": perfil_vark,
        },
    )


@login_required
def redireccion_post_login(request):
    tiene_vark = PerfilVARK.objects.filter(user=request.user).exists()

    if not tiene_vark:
        return redirect("vark:test")

    return redirect("usuarios:dashboard")


@login_required
def progreso(request):
    perfil_vark = PerfilVARK.objects.filter(user=request.user).first()

    if perfil_vark:
        estilo_vark = perfil_vark.estilo_display
    else:
        estilo_vark = "Pendiente"

    simulacros = []

    return render(
        request,
        "progreso/progreso.html",
        {
            "simulacros": simulacros,
            "fuertes": [],
            "debiles": [],
            "estilo_vark": estilo_vark,
            "recomendacion": "Todavía no hay resultados de exámenes guardados. Realiza un simulacro para ver tu progreso.",
        },
    )