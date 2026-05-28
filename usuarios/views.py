from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.shortcuts import redirect, render


def home(request):
    if request.user.is_authenticated:
        return redirect("usuarios:redireccion_post_login")
    return render(request, "home.html")


@login_required
def dashboard(request):
    resumen = {
        "estilo_vark": "Visual",
        "proximo_examen": "Anatomia I - Sistema oseo",
        "fecha_examen": "2026-06-12",
        "materiales": 8,
        "ruta_activa": "Plan de 5 dias",
        "ultimo_puntaje": "82%",
    }
    accesos = [
        {"label": "Test VARK", "url": reverse("vark:test"), "icon": "scan-eye"},
        {"label": "Datos academicos", "url": reverse("anatomia:datos_academicos"), "icon": "clipboard-list"},
        {"label": "Subir material", "url": reverse("documentos:subir"), "icon": "upload-cloud"},
        {"label": "Ver ruta", "url": reverse("rutas:ruta_aprendizaje"), "icon": "route"},
        {"label": "Generar examen", "url": reverse("examenes:generar"), "icon": "file-question"},
        {"label": "Ver progreso", "url": reverse("usuarios:progreso"), "icon": "trending-up"},
    ]
    return render(request, "dashboard.html", {"resumen": resumen, "accesos": accesos})


@login_required
def redireccion_post_login(request):
    """
    Mas adelante aqui validaremos:
    - Si el estudiante ya hizo el test VARK.
    - Si ya registro datos academicos.
    - Si debe ir al panel principal.
    """
    return redirect("usuarios:dashboard")


@login_required
def progreso(request):
    simulacros = [
        {"nombre": "Sistema oseo", "fecha": "2026-05-18", "puntaje": 78},
        {"nombre": "Craneo y vertebras", "fecha": "2026-05-22", "puntaje": 84},
        {"nombre": "Articulaciones", "fecha": "2026-05-26", "puntaje": 88},
    ]
    return render(
        request,
        "progreso/progreso.html",
        {
            "simulacros": simulacros,
            "fuertes": ["Huesos largos", "Planos anatomicos", "Terminologia basica"],
            "debiles": ["Foramenes del craneo", "Inserciones musculares", "Vertebras cervicales"],
            "estilo_vark": "Visual",
            "recomendacion": "Refuerza los temas debiles con mapas, laminas rotuladas y mini simulacros cada dos dias.",
        },
    )
