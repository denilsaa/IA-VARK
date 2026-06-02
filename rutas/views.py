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
        # Los materiales ya NO son obligatorios. La ruta se genera con:
        # 1) resultado VARK,
        # 2) datos académicos,
        # 3) dataset de Anatomía I basado en el libro base.
        # Si existen materiales procesados, se usan solo como contexto adicional.
        ruta = generar_ruta_aprendizaje(
            user=request.user,
            perfil_vark=perfil_vark,
            datos_academicos=datos_academicos,
            materiales=materiales,
        )

        if materiales:
            messages.success(
                request,
                "Ruta generada usando tu VARK, tus datos académicos, el dataset de Anatomía I y tus materiales procesados.",
            )
        else:
            messages.success(
                request,
                "Ruta generada usando tu VARK, tus datos académicos y el dataset de Anatomía I. Puedes subir materiales después para enriquecerla.",
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
