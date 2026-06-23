from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from anatomia.models import DatosAcademicos
from documentos.models import MaterialEstudio
from examenes.models import ExamenGenerado
from rutas.models import RutaAprendizaje, RutaDiaProgreso
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
    ultimo_examen = ExamenGenerado.objects.filter(
        user=request.user,
        estado=ExamenGenerado.ESTADO_RESPONDIDO,
    ).order_by("-actualizado").first()

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

    progreso_ruta = calcular_progreso_ruta(request.user, ruta)

    if ruta:
        ruta_activa = f"{progreso_ruta['porcentaje']}% completado"
    else:
        ruta_activa = "Sin ruta activa"

    if ultimo_examen:
        ultimo_puntaje = f"{ultimo_examen.porcentaje}%"
    else:
        ultimo_puntaje = "Sin simulacros"

    resumen = {
        "estilo_vark": estilo_vark,
        "tema_actual": tema_actual,
        "proximo_examen": proximo_examen,
        "fecha_examen": fecha_examen,
        "dias_restantes": dias_restantes,
        "tiempo_estudio": tiempo_estudio,
        "materiales": cantidad_materiales,
        "ruta_activa": ruta_activa,
        "ruta_progreso": progreso_ruta,
        "ultimo_puntaje": ultimo_puntaje,
    }

    onboarding = construir_onboarding_dashboard(
        perfil_vark=perfil_vark,
        datos_academicos=datos_academicos,
        cantidad_materiales=cantidad_materiales,
        ruta=ruta,
        progreso_ruta=progreso_ruta,
        ultimo_examen=ultimo_examen,
    )

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
            "onboarding": onboarding,
        },
    )


def construir_onboarding_dashboard(
    *,
    perfil_vark,
    datos_academicos,
    cantidad_materiales,
    ruta,
    progreso_ruta,
    ultimo_examen,
):
    pasos = [
        {
            "numero": 1,
            "titulo": "Test VARK",
            "descripcion": "Identifica tu estilo de aprendizaje para personalizar la ruta.",
            "icono": "scan-eye",
            "url": reverse("vark:resultado") if perfil_vark else reverse("vark:test"),
            "completado": bool(perfil_vark),
        },
        {
            "numero": 2,
            "titulo": "Datos académicos",
            "descripcion": "Registra tema, fecha de examen, dificultad y tiempo disponible.",
            "icono": "clipboard-list",
            "url": reverse("anatomia:datos_academicos"),
            "completado": bool(datos_academicos),
        },
        {
            "numero": 3,
            "titulo": "Materiales",
            "descripcion": "Sube PDFs, apuntes o imágenes para enriquecer el análisis de IA.",
            "icono": "folder-up",
            "url": reverse("documentos:lista") if cantidad_materiales else reverse("documentos:subir"),
            "completado": cantidad_materiales > 0,
        },
        {
            "numero": 4,
            "titulo": "Ruta",
            "descripcion": "Genera tu plan de estudio diario adaptado a tu perfil y temario.",
            "icono": "route",
            "url": reverse("rutas:ruta_aprendizaje"),
            "completado": bool(ruta),
        },
        {
            "numero": 5,
            "titulo": "Simulacro",
            "descripcion": "Practica con preguntas para comprobar si entendiste el tema.",
            "icono": "file-question",
            "url": reverse("examenes:lista") if ultimo_examen else reverse("examenes:generar"),
            "completado": bool(ultimo_examen),
        },
        {
            "numero": 6,
            "titulo": "Progreso",
            "descripcion": "Revisa avance, puntajes y temas que debes reforzar.",
            "icono": "trending-up",
            "url": reverse("usuarios:progreso"),
            "completado": bool((progreso_ruta or {}).get("porcentaje") or ultimo_examen),
        },
    ]

    siguiente = None
    for paso in pasos:
        if not paso["completado"]:
            siguiente = paso
            break

    if siguiente is None:
        siguiente = {
            "numero": 6,
            "titulo": "Ver progreso",
            "descripcion": "Todos los pasos base están listos. Revisa tu avance y continúa practicando.",
            "icono": "trending-up",
            "url": reverse("usuarios:progreso"),
            "completado": True,
        }

    for paso in pasos:
        if paso["completado"]:
            paso["estado"] = "completado"
        elif paso["numero"] == siguiente["numero"]:
            paso["estado"] = "actual"
        else:
            paso["estado"] = "pendiente"

    completados = sum(1 for paso in pasos if paso["completado"])
    porcentaje = round(completados * 100 / len(pasos))

    return {
        "pasos": pasos,
        "siguiente": siguiente,
        "completados": completados,
        "total": len(pasos),
        "porcentaje": porcentaje,
        "mensaje": obtener_mensaje_onboarding(siguiente, porcentaje),
    }


def obtener_mensaje_onboarding(siguiente, porcentaje):
    if porcentaje == 100:
        return "Tu flujo principal está completo. Ahora puedes medir tu avance, reforzar temas débiles y practicar con nuevos simulacros."

    numero = siguiente.get("numero")
    mensajes = {
        1: "Empieza completando el test VARK para que el sistema adapte los recursos a tu forma de aprender.",
        2: "Ahora registra tus datos académicos para que la IA conozca tu tema, fecha de examen y tiempo disponible.",
        3: "Sube tus apuntes, PDFs o imágenes para que la ruta se base en el material que realmente estudias.",
        4: "Con tu perfil y datos listos, genera una ruta personalizada para saber qué estudiar cada día.",
        5: "Después de estudiar la ruta, practica con un simulacro para comprobar tu comprensión.",
        6: "Revisa tu progreso para identificar avances, puntajes y temas que debes reforzar.",
    }
    return mensajes.get(numero, "Continúa con el siguiente paso para completar tu proceso de estudio.")


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

    ruta = RutaAprendizaje.objects.filter(user=request.user).first()
    progreso_ruta = calcular_progreso_ruta(request.user, ruta)

    simulacros = list(
        ExamenGenerado.objects.filter(
            user=request.user,
            estado=ExamenGenerado.ESTADO_RESPONDIDO,
        ).order_by("-actualizado")[:10]
    )

    fuertes, debiles = obtener_temas_fuertes_y_debiles(simulacros)

    if simulacros:
        recomendacion = (
            "Revisa los temas con respuestas incorrectas y genera nuevos simulacros "
            "después de repasar tu ruta de aprendizaje."
        )
    else:
        recomendacion = (
            "Todavía no hay resultados de exámenes guardados. Realiza un simulacro "
            "para ver tu progreso."
        )

    bonus_aprendizaje = construir_bonus_aprendizaje(
        user=request.user,
        perfil_vark=perfil_vark,
        ruta=ruta,
        progreso_ruta=progreso_ruta,
        simulacros=simulacros,
    )

    if request.GET.get("bonus_test") == "1":
        bonus_aprendizaje["desbloqueado"] = True
        bonus_aprendizaje["nivel"] = "Bonus de prueba"
        bonus_aprendizaje["motivo"] = "Modo prueba activado para validar el diseño del bonus."
        bonus_aprendizaje["razones"] = [
            "Esta vista permite comprobar cómo se verá el bonus cuando el estudiante lo desbloquee."
        ]
        bonus_aprendizaje["progreso_desbloqueo"] = 100

    return render(
        request,
        "progreso/progreso.html",
        {
            "simulacros": simulacros,
            "fuertes": fuertes,
            "debiles": debiles,
            "estilo_vark": estilo_vark,
            "recomendacion": recomendacion,
            "ruta": ruta,
            "progreso_ruta": progreso_ruta,
            "bonus_aprendizaje": bonus_aprendizaje,
        },
    )


def calcular_progreso_ruta(user, ruta):
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


def obtener_temas_fuertes_y_debiles(simulacros):
    conteo = {}

    for examen in simulacros:
        for resultado in examen.resultados:
            tema = resultado.get("tema") or "Tema no especificado"

            if tema not in conteo:
                conteo[tema] = {
                    "correctas": 0,
                    "incorrectas": 0,
                }

            if resultado.get("es_correcta"):
                conteo[tema]["correctas"] += 1
            else:
                conteo[tema]["incorrectas"] += 1

    fuertes = []
    debiles = []

    for tema, datos in conteo.items():
        if datos["correctas"] >= datos["incorrectas"]:
            fuertes.append(tema)
        else:
            debiles.append(tema)

    return fuertes[:5], debiles[:5]

def construir_bonus_aprendizaje(user, perfil_vark, ruta, progreso_ruta, simulacros):
    if perfil_vark:
        estilo = perfil_vark.estilo_principal
        estilo_display = perfil_vark.estilo_display
    else:
        estilo = "visual"
        estilo_display = "Visual"

    hoy = timezone.localdate()
    dias_completados_hoy = 0

    if ruta:
        dias_completados_hoy = RutaDiaProgreso.objects.filter(
            user=user,
            ruta=ruta,
            completado=True,
            actualizado__date=hoy,
        ).count()

    ultimo_simulacro = simulacros[0] if simulacros else None
    promedio_quiz = progreso_ruta.get("promedio_quiz")
    porcentaje_ruta = progreso_ruta.get("porcentaje", 0) or 0
    dias_completados = progreso_ruta.get("dias_completados", 0) or 0
    quizzes_resueltos = progreso_ruta.get("quizzes_resueltos", 0) or 0

    materiales_procesados = MaterialEstudio.objects.filter(
        user=user,
        estado=MaterialEstudio.ESTADO_PROCESADO,
    ).count()

    razones = []
    puntaje_bonus = 0

    if dias_completados_hoy >= 2:
        razones.append(f"Completaste {dias_completados_hoy} días de ruta hoy.")
        puntaje_bonus += 35

    if promedio_quiz is not None and promedio_quiz >= 85:
        razones.append(f"Tu promedio de mini quizzes es alto: {promedio_quiz}%.")
        puntaje_bonus += 35

    if ultimo_simulacro and float(ultimo_simulacro.porcentaje) >= 80:
        razones.append(f"Tu último simulacro tuvo un resultado destacado: {ultimo_simulacro.porcentaje}%.")
        puntaje_bonus += 30

    if porcentaje_ruta >= 50:
        razones.append(f"Ya completaste el {porcentaje_ruta}% de tu ruta.")
        puntaje_bonus += 25

    if dias_completados >= 3:
        razones.append(f"Llevas {dias_completados} días completados en tu ruta.")
        puntaje_bonus += 20

    if materiales_procesados > 0:
        razones.append("Tienes materiales procesados que pueden reforzar tu aprendizaje.")
        puntaje_bonus += 15

    if quizzes_resueltos >= 2:
        razones.append(f"Ya guardaste {quizzes_resueltos} resultados de mini quizzes.")
        puntaje_bonus += 15

    desbloqueado = bool(
        dias_completados_hoy >= 2
        or (promedio_quiz is not None and promedio_quiz >= 85)
        or (ultimo_simulacro and float(ultimo_simulacro.porcentaje) >= 80)
        or porcentaje_ruta >= 50
        or dias_completados >= 3
    )

    progreso_desbloqueo = min(puntaje_bonus, 100)

    if desbloqueado:
        nivel = "Bonus desbloqueado"
        motivo = razones[0] if razones else "Tu avance fue superior al esperado."
    else:
        nivel = "Bonus bloqueado"
        motivo = "Sigue avanzando para desbloquear un recurso especial adaptado a tu estilo VARK."
        if progreso_desbloqueo < 20:
            progreso_desbloqueo = 20

    bonus_por_estilo = {
        "visual": {
            "estilo": "visual",
            "color": "visual",
            "tipo": "Lámina visual anatómica",
            "titulo": "Lámina bonus para estudiar observando",
            "descripcion": "Recibe una imagen, mapa o lámina anatómica guiada para reforzar visualmente el tema que estás estudiando.",
            "icono": "image",
            "accion": "Ir a mi ruta visual",
            "accion_url": reverse("rutas:ruta_aprendizaje"),
            "recursos": [
                "Lámina anatómica guiada",
                "Mapa visual del tema",
                "Marcadores de estructuras importantes",
            ],
            "texto_audio": "Bonus visual desbloqueado. Repasa el tema usando una lámina anatómica, observa las estructuras principales y conviértelas en preguntas de estudio.",
        },
        "auditivo": {
            "estilo": "auditivo",
            "color": "auditivo",
            "tipo": "Mini podcast educativo",
            "titulo": "Audio bonus para repasar escuchando",
            "descripcion": "Recibe una explicación breve tipo podcast para reforzar el tema principal mediante escucha activa.",
            "icono": "headphones",
            "accion": "Escuchar mini podcast",
            "accion_url": reverse("rutas:ruta_aprendizaje"),
            "recursos": [
                "Mini podcast de repaso",
                "Explicación narrada",
                "Preguntas orales para recordar",
            ],
            "texto_audio": "Bonus auditivo desbloqueado. Escucha esta mini clase de repaso. Primero identifica el tema principal, luego recuerda sus estructuras importantes y finalmente responde una pregunta clave con tus propias palabras.",
        },
        "lectura": {
            "estilo": "lectura",
            "color": "lectura",
            "tipo": "Ficha de estudio premium",
            "titulo": "Resumen bonus para estudiar leyendo y escribiendo",
            "descripcion": "Recibe una ficha rápida con resumen, glosario, conceptos clave y preguntas para repasar antes del examen.",
            "icono": "book-open",
            "accion": "Ver mis materiales",
            "accion_url": reverse("documentos:lista"),
            "recursos": [
                "Resumen premium",
                "Glosario rápido",
                "Checklist de repaso",
            ],
            "texto_audio": "Bonus de lectura y escritura desbloqueado. Crea una ficha rápida con definiciones, ideas clave y preguntas de repaso para convertir el contenido en conocimiento organizado.",
        },
        "kinestesico": {
            "estilo": "kinestesico",
            "color": "kinestesico",
            "tipo": "Reto práctico 3D",
            "titulo": "Reto bonus para aprender haciendo",
            "descripcion": "Recibe una actividad práctica, reto de identificación o modelo 3D para reforzar el tema mediante interacción.",
            "icono": "box",
            "accion": "Abrir reto práctico",
            "accion_url": reverse("rutas:ruta_aprendizaje"),
            "recursos": [
                "Modelo 3D o reto práctico",
                "Actividad de armado o identificación",
                "Repaso mediante interacción",
            ],
            "texto_audio": "Bonus kinestésico desbloqueado. Refuerza el tema manipulando, identificando o armando una estructura anatómica como si fuera un reto práctico.",
        },
    }

    bonus = bonus_por_estilo.get(estilo, bonus_por_estilo["visual"])

    pasos_para_desbloquear = [
        "Completa al menos 2 días de ruta.",
        "Guarda resultados de mini quizzes.",
        "Responde un simulacro y busca superar el 80%.",
        "Sube materiales para que el sistema pueda reforzar tu estudio.",
    ]

    bonus.update(
        {
            "desbloqueado": desbloqueado,
            "nivel": nivel,
            "motivo": motivo,
            "razones": razones[:4],
            "progreso_desbloqueo": progreso_desbloqueo,
            "estilo_display": estilo_display,
            "pasos_para_desbloquear": pasos_para_desbloquear,
        }
    )

    return bonus

def pagina_no_encontrada(request, exception=None):
    return render(request, "404.html", status=404)
