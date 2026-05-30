from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from anatomia.models import DatosAcademicos
from documentos.models import MaterialEstudio
from rutas.models import RutaAprendizaje
from vark.models import PerfilVARK

from .models import ExamenGenerado
from .services import calificar_examen, generar_examen_personalizado


@login_required
def lista_examenes(request):
    examenes = ExamenGenerado.objects.filter(user=request.user)

    return render(
        request,
        "examenes/lista.html",
        {
            "examenes": examenes,
        },
    )


@login_required
def generar_examen(request):
    perfil_vark = PerfilVARK.objects.filter(user=request.user).first()

    if not perfil_vark:
        messages.warning(request, "Primero debes completar el test VARK.")
        return redirect("vark:test")

    datos_academicos = DatosAcademicos.objects.filter(user=request.user).first()

    if not datos_academicos:
        messages.warning(request, "Primero debes registrar tus datos académicos.")
        return redirect("anatomia:datos_academicos")

    ruta = RutaAprendizaje.objects.filter(user=request.user).first()

    if not ruta:
        messages.warning(request, "Primero debes generar tu ruta de aprendizaje.")
        return redirect("rutas:ruta_aprendizaje")

    materiales = list(
        MaterialEstudio.objects.filter(
            user=request.user,
            estado=MaterialEstudio.ESTADO_PROCESADO,
        ).order_by("-actualizado")[:5]
    )

    if request.method == "POST":
        cantidad_preguntas = request.POST.get("cantidad_preguntas", 10)
        dificultad = request.POST.get(
            "dificultad",
            ExamenGenerado.DIFICULTAD_MEDIA,
        )

        if dificultad not in [
            ExamenGenerado.DIFICULTAD_BAJA,
            ExamenGenerado.DIFICULTAD_MEDIA,
            ExamenGenerado.DIFICULTAD_ALTA,
        ]:
            dificultad = ExamenGenerado.DIFICULTAD_MEDIA

        examen = generar_examen_personalizado(
            user=request.user,
            perfil_vark=perfil_vark,
            datos_academicos=datos_academicos,
            ruta=ruta,
            materiales=materiales,
            cantidad_preguntas=cantidad_preguntas,
            dificultad=dificultad,
        )

        messages.success(
            request,
            "Examen generado correctamente.",
        )

        return redirect("examenes:rendir", pk=examen.pk)

    examenes_recientes = ExamenGenerado.objects.filter(
        user=request.user,
    ).order_by("-creado")[:5]

    return render(
        request,
        "examenes/generar.html",
        {
            "perfil_vark": perfil_vark,
            "datos_academicos": datos_academicos,
            "ruta": ruta,
            "materiales": materiales,
            "examenes_recientes": examenes_recientes,
        },
    )


@login_required
def rendir_examen(request, pk):
    examen = get_object_or_404(
        ExamenGenerado,
        pk=pk,
        user=request.user,
    )

    if examen.esta_respondido:
        return redirect("examenes:resultado", pk=examen.pk)

    if request.method == "POST":
        respuestas = {}

        for pregunta in examen.preguntas:
            pregunta_id = str(pregunta.get("id"))
            respuestas[pregunta_id] = request.POST.get(
                f"pregunta_{pregunta_id}",
                "",
            )

        preguntas_sin_responder = [
            pregunta_id
            for pregunta_id, respuesta in respuestas.items()
            if not respuesta
        ]

        if preguntas_sin_responder:
            messages.error(
                request,
                "Debes responder todas las preguntas antes de finalizar.",
            )

            return render(
                request,
                "examenes/rendir.html",
                {
                    "examen": examen,
                },
            )

        calificar_examen(examen, respuestas)

        messages.success(
            request,
            "Examen calificado correctamente.",
        )

        return redirect("examenes:resultado", pk=examen.pk)

    return render(
        request,
        "examenes/rendir.html",
        {
            "examen": examen,
        },
    )


@login_required
def resultado_examen(request, pk):
    examen = get_object_or_404(
        ExamenGenerado,
        pk=pk,
        user=request.user,
    )

    return render(
        request,
        "examenes/resultado.html",
        {
            "examen": examen,
        },
    )