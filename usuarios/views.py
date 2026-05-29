from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse


def home(request):
    if request.user.is_authenticated:
        return redirect("usuarios:redireccion_post_login")

    return render(request, "home.html")


@login_required
def dashboard(request):
    resumen = {
        "estilo_vark": "Pendiente",
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
            "label": "Datos academicos",
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
        },
    )


@login_required
def redireccion_post_login(request):
    """
    Luego aqui conectaremos la logica real:

    1. Si no hizo el test VARK -> enviarlo al test.
    2. Si no registro datos academicos -> enviarlo a datos academicos.
    3. Si ya completo lo basico -> enviarlo al dashboard.
    """

    return redirect("usuarios:dashboard")


@login_required
def progreso(request):
    simulacros = []

    return render(
        request,
        "progreso/progreso.html",
        {
            "simulacros": simulacros,
            "fuertes": [],
            "debiles": [],
            "estilo_vark": "Pendiente",
            "recomendacion": "Todavia no hay resultados guardados. Realiza el test VARK y genera un primer simulacro para ver tu progreso.",
        },
    )