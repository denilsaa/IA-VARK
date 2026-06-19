from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from anatomia.models import DatosAcademicos
from documentos.models import MaterialEstudio
from rutas.models import RutaAprendizaje

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
        "descripcion": "Aprendes mejor cuando puedes observar, comparar, colorear y ubicar estructuras en el espacio.",
        "explicacion": (
            "Tu fortaleza está en transformar la información en imágenes mentales. En Anatomía I esto es muy útil porque muchas preguntas dependen de reconocer forma, ubicación, relación y orientación de las estructuras."
        ),
        "fortalezas": [
            "Reconocer estructuras en láminas, esquemas y atlas.",
            "Recordar relaciones espaciales como anterior, posterior, medial y lateral.",
            "Organizar temas complejos mediante colores, mapas y cuadros comparativos.",
        ],
        "estrategias": [
            "Usa atlas anatómicos y observa la misma estructura desde varias vistas.",
            "Crea mapas mentales por sistema anatómico antes de memorizar detalles.",
            "Usa colores distintos para huesos, vasos, nervios, músculos y órganos.",
            "Resume temas con diagramas y cuadros comparativos.",
        ],
        "ejemplos_anatomia": [
            "Para pelvis: dibuja o colorea ilion, isquion, pubis, sacro y sínfisis púbica.",
            "Para abdomen: usa una lámina y marca la posición de órganos y relaciones vecinas.",
            "Para músculos: identifica origen, inserción y acción con flechas o colores.",
        ],
        "evitar": [
            "Estudiar solo leyendo párrafos largos sin ver imágenes.",
            "Memorizar nombres sin ubicarlos en una lámina.",
            "Usar mapas mentales con demasiado texto y poca jerarquía visual.",
        ],
        "recursos_sistema": [
            "Mapas mentales",
            "Láminas anatómicas",
            "Marcadores visuales",
            "Ruta de aprendizaje",
        ],
        "plan_rapido": [
            "5 min: mira una lámina sin leer la explicación.",
            "7 min: identifica estructuras principales y relaciones.",
            "5 min: dibuja un esquema simple de memoria.",
            "3 min: responde un mini quiz de identificación.",
        ],
        "icono": "eye",
        "color": "#0f766e",
    },
    "auditivo": {
        "titulo": "Aprendizaje Auditivo",
        "descripcion": "Aprendes mejor cuando escuchas, explicas en voz alta y conviertes el contenido en conversación.",
        "explicacion": (
            "Tu fortaleza está en comprender la información cuando la escuchas o la verbalizas. En Anatomía I esto ayuda a fijar conceptos, relaciones y funciones mediante explicación oral, repetición y preguntas habladas."
        ),
        "fortalezas": [
            "Comprender conceptos cuando alguien los explica paso a paso.",
            "Recordar mejor al repetir ideas en voz alta.",
            "Detectar dudas cuando intentas explicar el tema a otra persona.",
        ],
        "estrategias": [
            "Escucha el guion del día antes de leer el resumen.",
            "Explica cada estructura como si estuvieras enseñando a un compañero.",
            "Graba audios cortos con tus propias palabras y repásalos antes del examen.",
            "Haz preguntas orales rápidas después de cada tema.",
        ],
        "ejemplos_anatomia": [
            "Para nervios: explica en voz alta el trayecto desde origen hasta destino.",
            "Para órganos: describe ubicación, función y relación con estructuras vecinas.",
            "Para músculos: di en voz alta origen, inserción, acción e inervación.",
        ],
        "evitar": [
            "Leer en silencio sin comprobar si puedes explicarlo.",
            "Memorizar listas largas sin convertirlas en explicación oral.",
            "Escuchar audios sin pausar para repetir los puntos clave.",
        ],
        "recursos_sistema": [
            "Audio o guion explicativo",
            "Preguntas orales",
            "Mini quizzes",
            "Ruta diaria",
        ],
        "plan_rapido": [
            "5 min: escucha el guion del día.",
            "7 min: explica el tema en voz alta sin mirar.",
            "5 min: responde preguntas orales o mini quiz.",
            "3 min: graba una conclusión breve del tema.",
        ],
        "icono": "volume-2",
        "color": "#3b82f6",
    },
    "lectura": {
        "titulo": "Lectura/Escritura",
        "descripcion": "Aprendes mejor leyendo, escribiendo, ordenando conceptos y creando resúmenes claros.",
        "explicacion": (
            "Tu fortaleza está en organizar la información mediante palabras, listas y resúmenes. En Anatomía I esto ayuda a dominar definiciones, clasificaciones, relaciones y detalles que suelen aparecer en evaluaciones teóricas."
        ),
        "fortalezas": [
            "Ordenar contenido complejo en apuntes claros.",
            "Recordar definiciones y listas anatómicas.",
            "Construir glosarios y cuadros de comparación.",
        ],
        "estrategias": [
            "Haz resúmenes por tema y subtema.",
            "Crea glosarios de términos anatómicos importantes.",
            "Transforma párrafos largos en listas o tablas.",
            "Reescribe con tus palabras las definiciones difíciles.",
        ],
        "ejemplos_anatomia": [
            "Para articulaciones: crea una tabla con tipo, superficies, ligamentos y movimientos.",
            "Para órganos: escribe ubicación, relaciones, irrigación e inervación.",
            "Para periné: separa límites, planos, músculos y funciones en listas cortas.",
        ],
        "evitar": [
            "Copiar texto sin resumirlo con tus palabras.",
            "Hacer apuntes muy largos que no puedas repasar rápido.",
            "Estudiar sin convertir el contenido en preguntas de examen.",
        ],
        "recursos_sistema": [
            "Resumen IA",
            "Glosario",
            "Preguntas sugeridas",
            "Materiales procesados",
        ],
        "plan_rapido": [
            "5 min: lee el resumen del tema.",
            "7 min: escribe una tabla con conceptos clave.",
            "5 min: crea 3 preguntas de examen.",
            "3 min: revisa errores y completa tu glosario.",
        ],
        "icono": "book-open",
        "color": "#f59e0b",
    },
    "kinestesico": {
        "titulo": "Aprendizaje Kinestésico",
        "descripcion": "Aprendes mejor practicando, resolviendo, identificando y aplicando los conceptos en ejercicios concretos.",
        "explicacion": (
            "Tu fortaleza está en aprender haciendo. En Anatomía I esto es valioso porque puedes fijar conceptos mediante identificación de estructuras, simulacros, ejercicios de relación y práctica activa."
        ),
        "fortalezas": [
            "Aprender mejor cuando resuelves ejercicios o casos.",
            "Recordar estructuras al identificarlas activamente.",
            "Conectar teoría con función, movimiento o aplicación clínica básica.",
        ],
        "estrategias": [
            "Practica con imágenes y trata de identificar estructuras sin mirar la respuesta.",
            "Resuelve mini quizzes después de cada tema.",
            "Relaciona estructuras con funciones, movimientos o límites anatómicos.",
            "Haz simulacros cortos y corrige tus errores inmediatamente.",
        ],
        "ejemplos_anatomia": [
            "Para huesos: señala accidentes anatómicos en una imagen y luego verifica.",
            "Para músculos: relaciona acción con movimiento real o simulado.",
            "Para vasos y nervios: sigue el trayecto con el dedo sobre una lámina.",
        ],
        "evitar": [
            "Solo leer teoría sin practicar identificación.",
            "Dejar los simulacros para el último día.",
            "Mirar respuestas antes de intentar resolver.",
        ],
        "recursos_sistema": [
            "Ejercicios prácticos",
            "Mini quizzes",
            "Láminas con marcadores",
            "Simulacros",
        ],
        "plan_rapido": [
            "5 min: observa una lámina y oculta las respuestas.",
            "7 min: identifica estructuras o relaciones.",
            "5 min: resuelve un mini quiz.",
            "3 min: repite solo las preguntas falladas.",
        ],
        "icono": "activity",
        "color": "#8b5cf6",
    },
}


def construir_siguiente_paso_resultado(user):
    if not DatosAcademicos.objects.filter(user=user).exists():
        return {
            "titulo": "Registra tus datos académicos",
            "descripcion": "Indica tu tema, fecha de examen, tiempo disponible y punto difícil para que la ruta sea personalizada.",
            "url": reverse("anatomia:datos_academicos"),
            "label": "Registrar datos académicos",
            "icono": "clipboard-list",
        }

    if not MaterialEstudio.objects.filter(user=user, estado=MaterialEstudio.ESTADO_PROCESADO).exists():
        return {
            "titulo": "Sube tu primer material",
            "descripcion": "Carga PDF, apuntes o imágenes para que la IA use tus contenidos reales al generar la ruta.",
            "url": reverse("documentos:subir"),
            "label": "Subir material",
            "icono": "upload-cloud",
        }

    if not RutaAprendizaje.objects.filter(user=user).exists():
        return {
            "titulo": "Genera tu ruta de aprendizaje",
            "descripcion": "Usa tu perfil VARK y tus materiales para crear un plan de estudio por días.",
            "url": reverse("rutas:ruta_aprendizaje"),
            "label": "Generar ruta",
            "icono": "route",
        }

    return {
        "titulo": "Continúa con tu ruta",
        "descripcion": "Ya tienes lo necesario para estudiar con recursos personalizados y comprobar tu avance.",
        "url": reverse("rutas:ruta_aprendizaje"),
        "label": "Ver mi ruta",
        "icono": "route",
    }


@login_required
def test_vark(request):
    if request.method == "POST":
        preguntas = request.session.get("preguntas_vark", [])

        if not preguntas:
            messages.error(
                request,
                "No se encontraron preguntas activas. Vuelve a intentar generar el test.",
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
                    "estado_llm": "ok",
                    "mensaje_llm": "",
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

    request.session["preguntas_vark"] = preguntas
    request.session.modified = True

    return render(
        request,
        "vark/test.html",
        {
            "preguntas": preguntas,
            "estado_llm": "ok" if resultado_generacion["ok"] else "error",
            "mensaje_llm": resultado_generacion["mensaje"],
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
            return render(request, "vark/desempate.html", {"pregunta": pregunta})

        puntajes[estilo_elegido] += 1
        guardar_perfil_vark(request.user, puntajes, estilo_elegido)
        limpiar_sesion_vark(request)
        return redirect("vark:resultado")

    pregunta = generar_pregunta_desempate(estilos_empatados)
    return render(request, "vark/desempate.html", {"pregunta": pregunta})


@login_required
def resultado_vark(request):
    try:
        perfil = request.user.perfil_vark
    except PerfilVARK.DoesNotExist:
        messages.warning(request, "Primero debes completar el test VARK.")
        return redirect("vark:test")

    recomendacion = RECOMENDACIONES.get(perfil.estilo_principal, RECOMENDACIONES["visual"])

    porcentajes = {
        "visual": perfil.obtener_porcentaje("visual"),
        "auditivo": perfil.obtener_porcentaje("auditivo"),
        "lectura": perfil.obtener_porcentaje("lectura"),
        "kinestesico": perfil.obtener_porcentaje("kinestesico"),
    }

    recomendacion_llm = generar_recomendacion_llm(perfil)

    resumen_estilos = [
        {
            "clave": "visual",
            "nombre": "Visual",
            "puntaje": perfil.puntaje_visual,
            "porcentaje": porcentajes["visual"],
            "icono": "eye",
            "color": RECOMENDACIONES["visual"]["color"],
        },
        {
            "clave": "auditivo",
            "nombre": "Auditivo",
            "puntaje": perfil.puntaje_auditivo,
            "porcentaje": porcentajes["auditivo"],
            "icono": "volume-2",
            "color": RECOMENDACIONES["auditivo"]["color"],
        },
        {
            "clave": "lectura",
            "nombre": "Lectura/Escritura",
            "puntaje": perfil.puntaje_lectura,
            "porcentaje": porcentajes["lectura"],
            "icono": "book-open",
            "color": RECOMENDACIONES["lectura"]["color"],
        },
        {
            "clave": "kinestesico",
            "nombre": "Kinestésico",
            "puntaje": perfil.puntaje_kinestesico,
            "porcentaje": porcentajes["kinestesico"],
            "icono": "activity",
            "color": RECOMENDACIONES["kinestesico"]["color"],
        },
    ]
    resumen_estilos = sorted(resumen_estilos, key=lambda item: item["puntaje"], reverse=True)

    estilo_secundario = resumen_estilos[1] if len(resumen_estilos) > 1 else None
    estilo_principal = resumen_estilos[0]

    return render(
        request,
        "vark/resultado.html",
        {
            "perfil": perfil,
            "recomendacion": recomendacion,
            "porcentajes": porcentajes,
            "recomendacion_llm": recomendacion_llm["texto"],
            "estado_ia": "ok" if recomendacion_llm["ok"] else "error",
            "mensaje_ia": recomendacion_llm["mensaje"],
            "resumen_estilos": resumen_estilos,
            "estilo_principal_info": estilo_principal,
            "estilo_secundario": estilo_secundario,
            "siguiente_paso": construir_siguiente_paso_resultado(request.user),
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
    for key in [
        "preguntas_vark",
        "origen_preguntas_vark",
        "puntajes_vark_pendientes",
        "estilos_empatados_vark",
    ]:
        request.session.pop(key, None)

    request.session.modified = True
