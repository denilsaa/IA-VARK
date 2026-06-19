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

    resumen_examenes = construir_resumen_examenes(examenes)

    return render(
        request,
        "examenes/lista.html",
        {
            "examenes": examenes,
            "resumen_examenes": resumen_examenes,
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

    analisis_resultado = construir_analisis_resultado(examen)

    return render(
        request,
        "examenes/resultado.html",
        {
            "examen": examen,
            "analisis_resultado": analisis_resultado,
        },
    )


def construir_resumen_examenes(examenes):
    examenes_lista = list(examenes)
    respondidos = [examen for examen in examenes_lista if examen.esta_respondido]
    pendientes = [examen for examen in examenes_lista if not examen.esta_respondido]

    if respondidos:
        promedio = round(
            sum(float(examen.porcentaje or 0) for examen in respondidos) / len(respondidos),
            1,
        )
        ultimo = respondidos[0]
    else:
        promedio = None
        ultimo = None

    return {
        "total": len(examenes_lista),
        "respondidos": len(respondidos),
        "pendientes": len(pendientes),
        "promedio": promedio,
        "ultimo": ultimo,
    }


def construir_analisis_resultado(examen):
    resultados = examen.resultados
    correctas = [resultado for resultado in resultados if resultado.get("es_correcta")]
    incorrectas = [resultado for resultado in resultados if not resultado.get("es_correcta")]

    conteo_temas = {}
    for resultado in resultados:
        tema = resultado.get("tema") or "Tema no especificado"
        if tema not in conteo_temas:
            conteo_temas[tema] = {"correctas": 0, "incorrectas": 0}
        if resultado.get("es_correcta"):
            conteo_temas[tema]["correctas"] += 1
        else:
            conteo_temas[tema]["incorrectas"] += 1

    temas_a_reforzar = [
        tema
        for tema, datos in conteo_temas.items()
        if datos["incorrectas"] > 0
    ][:5]

    temas_fuertes = [
        tema
        for tema, datos in conteo_temas.items()
        if datos["correctas"] >= datos["incorrectas"] and datos["correctas"] > 0
    ][:5]

    porcentaje = float(examen.porcentaje or 0)
    if porcentaje >= 85:
        nivel = "Dominio alto"
        recomendacion = "Mantén el ritmo y realiza un simulacro de mayor dificultad para confirmar dominio."
        tono = "success"
    elif porcentaje >= 60:
        nivel = "Dominio medio"
        recomendacion = "Revisa las preguntas falladas, vuelve a la ruta y repite un simulacro corto."
        tono = "warning"
    else:
        nivel = "Necesita refuerzo"
        recomendacion = "Conviene repasar los temas base antes de generar otro simulacro."
        tono = "danger"

    return {
        "correctas": len(correctas),
        "incorrectas": len(incorrectas),
        "temas_a_reforzar": temas_a_reforzar,
        "temas_fuertes": temas_fuertes,
        "nivel": nivel,
        "recomendacion": recomendacion,
        "tono": tono,
    }
