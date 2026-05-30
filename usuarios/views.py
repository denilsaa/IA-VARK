from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from anatomia.models import DatosAcademicos
from documentos.models import MaterialEstudio
from rutas.models import RutaAprendizaje
from vark.models import PerfilVARK


def home(request):
    if request.user.is_authenticated:
        return redirect("usuarios:redireccion_post_login")

    return render(request, "home.html")


@login_required
def dashboard(request):
    perfil_vark = PerfilVARK.objects.filter(user=request.user).first()
    datos_academicos = DatosAcademicos.objects.filter(user=request.user).first()
    cantidad_materiales = MaterialEstudio.objects.filter(user=request.user).count()
    ruta = RutaAprendizaje.objects.filter(user=request.user).first()

    if perfil_vark:
        estilo_vark = perfil_vark.estilo_display
    else:
        estilo_vark = "Pendiente"

    if datos_academicos:
        proximo_examen = datos_academicos.get_tipo_examen_display()
        fecha_examen = datos_academicos.fecha_examen_formateada
        tema_actual = datos_academicos.tema_actual
        dias_restantes = datos_academicos.dias_restantes
        tiempo_estudio = datos_academicos.tiempo_estudio_display
    else:
        proximo_examen = "Pendiente"
        fecha_examen = "Sin registrar"
        tema_actual = "Sin registrar"
        dias_restantes = "Sin registrar"
        tiempo_estudio = "Sin registrar"

    if ruta:
        ruta_activa = f"{ruta.dias_planificados} días planificados"
    else:
        ruta_activa = "Sin ruta activa"

    resumen = {
        "estilo_vark": estilo_vark,
        "tema_actual": tema_actual,
        "proximo_examen": proximo_examen,
        "fecha_examen": fecha_examen,
        "dias_restantes": dias_restantes,
        "tiempo_estudio": tiempo_estudio,
        "materiales": cantidad_materiales,
        "ruta_activa": ruta_activa,
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
            "label": "Ver materiales",
            "url": reverse("documentos:lista"),
            "icon": "folder-open",
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
            "datos_academicos": datos_academicos,
        },
    )


@login_required
def redireccion_post_login(request):
    tiene_vark = PerfilVARK.objects.filter(user=request.user).exists()

    if not tiene_vark:
        return redirect("vark:test")

    tiene_datos_academicos = DatosAcademicos.objects.filter(user=request.user).exists()

    if not tiene_datos_academicos:
        return redirect("anatomia:datos_academicos")

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