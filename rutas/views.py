from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from anatomia.models import DatosAcademicos
from documentos.models import MaterialEstudio
from vark.models import PerfilVARK

from .models import RutaAprendizaje
from .services import generar_ruta_aprendizaje


@login_required
def ruta_aprendizaje(request):
    perfil_vark = PerfilVARK.objects.filter(user=request.user).first()

    if not perfil_vark:
        messages.warning(
            request,
            "Primero debes completar el test VARK.",
        )
        return redirect("vark:test")

    datos_academicos = DatosAcademicos.objects.filter(user=request.user).first()

    if not datos_academicos:
        messages.warning(
            request,
            "Primero debes registrar tus datos académicos.",
        )
        return redirect("anatomia:datos_academicos")

    materiales = list(
        MaterialEstudio.objects.filter(
            user=request.user,
            estado=MaterialEstudio.ESTADO_PROCESADO,
        ).order_by("-actualizado")[:5]
    )

    ruta = RutaAprendizaje.objects.filter(user=request.user).first()

    if request.method == "POST":
        if not materiales:
            messages.warning(
                request,
                "Primero debes subir y procesar al menos un material de estudio.",
            )
            return redirect("documentos:subir")

        ruta = generar_ruta_aprendizaje(
            user=request.user,
            perfil_vark=perfil_vark,
            datos_academicos=datos_academicos,
            materiales=materiales,
        )

        messages.success(
            request,
            "Ruta de aprendizaje generada correctamente.",
        )

        return redirect("rutas:ruta_aprendizaje")

    return render(
        request,
        "rutas/ruta_aprendizaje.html",
        {
            "ruta": ruta,
            "perfil_vark": perfil_vark,
            "datos_academicos": datos_academicos,
            "materiales": materiales,
        },
    )