from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import PerfilVARK
from .services import (
    generar_pregunta_desempate,
    generar_preguntas_vark,
    generar_recomendacion_llm,
    obtener_estilos_ganadores,
)


RECOMENDACIONES = {
    "visual": {
        "titulo": "Aprendizaje Visual",
        "descripcion": "Aprendes mejor usando imágenes, esquemas, mapas conceptuales, colores, tablas y organización espacial.",
        "estrategias": [
            "Usa atlas anatómicos con imágenes claras.",
            "Crea mapas conceptuales por sistema anatómico.",
            "Utiliza colores para diferenciar estructuras.",
            "Resume temas con diagramas y cuadros comparativos.",
        ],
    },
    "auditivo": {
        "titulo": "Aprendizaje Auditivo",
        "descripcion": "Aprendes mejor escuchando explicaciones, hablando del tema y repasando en voz alta.",
        "estrategias": [
            "Explica los temas en voz alta como si enseñaras.",
            "Graba audios cortos con tus propios resúmenes.",
            "Estudia con compañeros mediante preguntas orales.",
            "Usa explicaciones conversacionales para temas difíciles.",
        ],
    },
    "lectura": {
        "titulo": "Lectura/Escritura",
        "descripcion": "Aprendes mejor leyendo, escribiendo, ordenando conceptos y creando resúmenes estructurados.",
        "estrategias": [
            "Haz resúmenes por tema y subtema.",
            "Crea glosarios de términos anatómicos.",
            "Usa listas para clasificar estructuras.",
            "Reescribe con tus palabras las definiciones importantes.",
        ],
    },
    "kinestesico": {
        "titulo": "Aprendizaje Kinestésico",
        "descripcion": "Aprendes mejor practicando, resolviendo ejercicios, identificando estructuras y aplicando los conceptos.",
        "estrategias": [
            "Practica con modelos anatómicos o imágenes interactivas.",
            "Resuelve preguntas de identificación.",
            "Relaciona estructuras con movimientos o funciones.",
            "Haz simulacros y casos aplicados.",
        ],
    },
}


@login_required
def test_vark(request):
    if request.method == "POST":
        preguntas = request.session.get("preguntas_vark", [])
        origen_preguntas = request.session.get("origen_preguntas_vark", "respaldo")

        if not preguntas:
            messages.error(
                request,
                "No se encontraron preguntas activas. Genera el test nuevamente.",
            )
            return redirect("vark:test")

        puntajes = {
            "visual": 0,
            "auditivo": 0,
            "lectura": 0,
            "kinestesico": 0,
        }

        preguntas_sin_responder = []

        for pregunta in preguntas:
            respuesta = request.POST.get(f"pregunta_{pregunta['id']}")

            if not respuesta:
                preguntas_sin_responder.append(pregunta["id"])
                continue

            if respuesta in puntajes:
                puntajes[respuesta] += 1

        if preguntas_sin_responder:
            messages.error(
                request,
                "Debes responder todas las preguntas antes de continuar.",
            )
            return render(
                request,
                "vark/test.html",
                {
                    "preguntas": preguntas,
                    "origen_preguntas": origen_preguntas,
                },
            )

        estilos_ganadores = obtener_estilos_ganadores(puntajes)

        if len(estilos_ganadores) > 1:
            request.session["puntajes_vark_pendientes"] = puntajes
            request.session["estilos_empatados_vark"] = estilos_ganadores
            request.session.modified = True

            return redirect("vark:desempate")

        estilo_principal = estilos_ganadores[0]
        guardar_perfil_vark(request.user, puntajes, estilo_principal)
        limpiar_sesion_vark(request)

        return redirect("vark:resultado")

    resultado_generacion = generar_preguntas_vark()
    preguntas = resultado_generacion["preguntas"]
    origen_preguntas = resultado_generacion["origen"]

    request.session["preguntas_vark"] = preguntas
    request.session["origen_preguntas_vark"] = origen_preguntas
    request.session.modified = True

    return render(
        request,
        "vark/test.html",
        {
            "preguntas": preguntas,
            "origen_preguntas": origen_preguntas,
        },
    )


@login_required
def desempate_vark(request):
    puntajes = request.session.get("puntajes_vark_pendientes")
    estilos_empatados = request.session.get("estilos_empatados_vark")

    if not puntajes or not estilos_empatados:
        return redirect("vark:test")

    if request.method == "POST":
        estilo_elegido = request.POST.get("estilo_desempate")

        if estilo_elegido not in estilos_empatados:
            messages.error(
                request,
                "Debes elegir una opción para definir tu estilo principal.",
            )
            pregunta = generar_pregunta_desempate(estilos_empatados)

            return render(
                request,
                "vark/desempate.html",
                {
                    "pregunta": pregunta,
                },
            )

        puntajes[estilo_elegido] += 1

        guardar_perfil_vark(request.user, puntajes, estilo_elegido)
        limpiar_sesion_vark(request)

        return redirect("vark:resultado")

    pregunta = generar_pregunta_desempate(estilos_empatados)

    return render(
        request,
        "vark/desempate.html",
        {
            "pregunta": pregunta,
        },
    )


@login_required
def resultado_vark(request):
    try:
        perfil = request.user.perfil_vark
    except PerfilVARK.DoesNotExist:
        messages.warning(request, "Primero debes completar el test VARK.")
        return redirect("vark:test")

    recomendacion = RECOMENDACIONES.get(
        perfil.estilo_principal,
        RECOMENDACIONES["visual"],
    )

    porcentajes = {
        "visual": perfil.obtener_porcentaje("visual"),
        "auditivo": perfil.obtener_porcentaje("auditivo"),
        "lectura": perfil.obtener_porcentaje("lectura"),
        "kinestesico": perfil.obtener_porcentaje("kinestesico"),
    }

    recomendacion_llm = generar_recomendacion_llm(perfil)

    return render(
        request,
        "vark/resultado.html",
        {
            "perfil": perfil,
            "recomendacion": recomendacion,
            "porcentajes": porcentajes,
            "recomendacion_llm": recomendacion_llm,
        },
    )


def guardar_perfil_vark(user, puntajes, estilo_principal):
    PerfilVARK.objects.update_or_create(
        user=user,
        defaults={
            "puntaje_visual": puntajes["visual"],
            "puntaje_auditivo": puntajes["auditivo"],
            "puntaje_lectura": puntajes["lectura"],
            "puntaje_kinestesico": puntajes["kinestesico"],
            "estilo_principal": estilo_principal,
        },
    )


def limpiar_sesion_vark(request):
    claves = [
        "preguntas_vark",
        "origen_preguntas_vark",
        "puntajes_vark_pendientes",
        "estilos_empatados_vark",
    ]

    for clave in claves:
        if clave in request.session:
            del request.session[clave]

    request.session.modified = True