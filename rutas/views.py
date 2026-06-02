from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from anatomia.models import DatosAcademicos
from documentos.models import MaterialEstudio
from vark.models import PerfilVARK

from .models import RutaAprendizaje, RutaDiaProgreso
from .services import generar_ruta_aprendizaje


@login_required
def ruta_aprendizaje(request):
    perfil_vark = PerfilVARK.objects.filter(user=request.user).first()

    if not perfil_vark:
        messages.warning(request, "Primero debes completar el test VARK.")
        return redirect("vark:test")

    datos_academicos = DatosAcademicos.objects.filter(user=request.user).first()

    if not datos_academicos:
        messages.warning(request, "Primero debes registrar tus datos académicos.")
        return redirect("anatomia:datos_academicos")

    materiales = list(
        MaterialEstudio.objects.filter(
            user=request.user,
            estado=MaterialEstudio.ESTADO_PROCESADO,
        ).order_by("-actualizado")[:5]
    )

    ruta = RutaAprendizaje.objects.filter(user=request.user).first()

    if request.method == "POST":
        ruta = generar_ruta_aprendizaje(
            user=request.user,
            perfil_vark=perfil_vark,
            datos_academicos=datos_academicos,
            materiales=materiales,
        )

        # Al regenerar la ruta, reiniciamos el avance porque el plan diario puede cambiar.
        RutaDiaProgreso.objects.filter(user=request.user, ruta=ruta).delete()

        if materiales:
            messages.success(
                request,
                "Ruta regenerada usando VARK, dataset de Anatomía I y tus materiales procesados.",
            )
        else:
            messages.success(
                request,
                "Ruta regenerada usando VARK y el dataset de Anatomía I. Puedes subir materiales después para enriquecerla.",
            )

        return redirect("rutas:ruta_aprendizaje")

    dias_ruta = construir_dias_con_progreso(request.user, ruta)
    progreso_general = calcular_progreso_general(request.user, ruta)

    return render(
        request,
        "rutas/ruta_aprendizaje.html",
        {
            "ruta": ruta,
            "dias_ruta": dias_ruta,
            "progreso_general": progreso_general,
            "perfil_vark": perfil_vark,
            "datos_academicos": datos_academicos,
            "materiales": materiales,
        },
    )


@login_required
@require_POST
def actualizar_progreso_ruta(request):
    ruta = RutaAprendizaje.objects.filter(user=request.user).first()

    if not ruta:
        messages.error(request, "Primero genera una ruta de aprendizaje.")
        return redirect("rutas:ruta_aprendizaje")

    try:
        dia = int(request.POST.get("dia", "0"))
    except ValueError:
        dia = 0

    if dia <= 0:
        messages.error(request, "Día inválido.")
        return redirect("rutas:ruta_aprendizaje")

    accion = request.POST.get("accion", "").strip()

    progreso, _ = RutaDiaProgreso.objects.get_or_create(
        user=request.user,
        ruta=ruta,
        dia=dia,
    )

    if accion == "completar":
        progreso.completado = True
        messages.success(request, f"Día {dia} marcado como completado.")

    elif accion == "pendiente":
        progreso.completado = False
        messages.info(request, f"Día {dia} volvió a quedar pendiente.")

    elif accion == "guardar_quiz":
        try:
            puntaje = int(request.POST.get("quiz_puntaje", "0"))
            total = int(request.POST.get("quiz_total", "0"))
        except ValueError:
            puntaje = 0
            total = 0

        puntaje = max(0, puntaje)
        total = max(0, total)

        if total > 0:
            progreso.quiz_puntaje = min(puntaje, total)
            progreso.quiz_total = total
            messages.success(
                request,
                f"Resultado del mini quiz del día {dia} guardado: {progreso.quiz_puntaje}/{progreso.quiz_total}.",
            )
        else:
            messages.warning(request, "Primero califica el mini quiz antes de guardar.")

    elif accion == "guardar_notas":
        progreso.notas = request.POST.get("notas", "").strip()
        messages.success(request, f"Notas del día {dia} guardadas.")

    else:
        messages.warning(request, "Acción no reconocida.")

    progreso.save()
    return redirect("rutas:ruta_aprendizaje")


def construir_dias_con_progreso(user, ruta):
    if not ruta:
        return []

    progresos = {
        progreso.dia: progreso
        for progreso in RutaDiaProgreso.objects.filter(user=user, ruta=ruta)
    }

    dias = []

    for dia in ruta.plan_diario:
        if not isinstance(dia, dict):
            continue

        dia_numero = int(dia.get("dia") or len(dias) + 1)
        copia = dict(dia)
        copia["progreso"] = progresos.get(dia_numero)
        dias.append(copia)

    return dias


def calcular_progreso_general(user, ruta):
    if not ruta:
        return {
            "total_dias": 0,
            "dias_completados": 0,
            "porcentaje": 0,
            "quizzes_resueltos": 0,
            "promedio_quiz": None,
        }

    total_dias = len(ruta.plan_diario)
    progresos = list(RutaDiaProgreso.objects.filter(user=user, ruta=ruta))
    dias_completados = sum(1 for progreso in progresos if progreso.completado)

    quizzes = [
        progreso
        for progreso in progresos
        if progreso.quiz_total and progreso.quiz_total > 0
    ]

    if quizzes:
        promedio_quiz = round(
            sum((progreso.quiz_puntaje or 0) * 100 / progreso.quiz_total for progreso in quizzes)
            / len(quizzes)
        )
    else:
        promedio_quiz = None

    porcentaje = round((dias_completados * 100 / total_dias)) if total_dias else 0

    return {
        "total_dias": total_dias,
        "dias_completados": dias_completados,
        "porcentaje": porcentaje,
        "quizzes_resueltos": len(quizzes),
        "promedio_quiz": promedio_quiz,
    }
