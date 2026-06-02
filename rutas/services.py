import json
import os

from django.utils.text import Truncator

from .models import RutaAprendizaje


MAX_CARACTERES_CONTEXTO_MATERIAL = 24000
MAX_DIAS_PLAN = 21


MODALIDADES_VARK = {
    "visual": "Visual",
    "auditivo": "Auditivo",
    "lectura": "Lectura/Escritura",
    "kinestesico": "Kinestésico",
}


REGLAS_VARK = {
    "visual": [
        "mapas conceptuales",
        "esquemas jerárquicos",
        "tablas comparativas",
        "diagramas textuales",
        "relaciones espaciales",
        "identificación visual de estructuras",
    ],
    "auditivo": [
        "explicaciones conversacionales",
        "repaso en voz alta",
        "guiones para audio",
        "preguntas orales",
        "explicación tipo tutor",
        "resúmenes para escuchar",
    ],
    "lectura": [
        "resúmenes detallados",
        "glosarios",
        "listas ordenadas",
        "cuadros conceptuales escritos",
        "preguntas de desarrollo",
        "reformulación con palabras propias",
    ],
    "kinestesico": [
        "casos aplicados",
        "identificación de estructuras",
        "ejercicios prácticos",
        "actividades paso a paso",
        "preguntas de ubicación y función",
        "simulacros cortos",
    ],
}


def generar_ruta_aprendizaje(user, perfil_vark, datos_academicos, materiales):
    dias_hasta_examen = datos_academicos.dias_restantes
    dias_planificados = calcular_dias_planificados(dias_hasta_examen)

    contexto_materiales = construir_contexto_materiales(materiales)
    perfil_vark_detalle = construir_detalle_vark(perfil_vark)

    respuesta = generar_ruta_con_gemini(
        perfil_vark=perfil_vark,
        perfil_vark_detalle=perfil_vark_detalle,
        datos_academicos=datos_academicos,
        materiales=materiales,
        contexto_materiales=contexto_materiales,
        dias_hasta_examen=dias_hasta_examen,
        dias_planificados=dias_planificados,
    )

    if not respuesta:
        respuesta = generar_ruta_respaldo(
            perfil_vark=perfil_vark,
            perfil_vark_detalle=perfil_vark_detalle,
            datos_academicos=datos_academicos,
            dias_hasta_examen=dias_hasta_examen,
            dias_planificados=dias_planificados,
        )

    ruta, _ = RutaAprendizaje.objects.update_or_create(
        user=user,
        defaults={
            "titulo": respuesta.get("titulo", "Ruta de aprendizaje personalizada"),
            "resumen_general": respuesta.get("resumen_general", ""),
            "estilo_vark_usado": perfil_vark.estilo_display,
            "dias_hasta_examen": dias_hasta_examen,
            "dias_planificados": dias_planificados,
            "minutos_por_dia": datos_academicos.minutos_por_dia,
            "temas_priorizados": "\n".join(respuesta.get("temas_priorizados", [])),
            "plan_json": respuesta.get("plan_diario", []),
            "recomendaciones_finales": "\n".join(
                respuesta.get("recomendaciones_finales", [])
            ),
        },
    )

    ruta.materiales.set(materiales)

    return ruta


def calcular_dias_planificados(dias_hasta_examen):
    if dias_hasta_examen <= 0:
        return 1

    if dias_hasta_examen > MAX_DIAS_PLAN:
        return MAX_DIAS_PLAN

    return dias_hasta_examen


def construir_detalle_vark(perfil_vark):
    puntajes = {
        "visual": perfil_vark.puntaje_visual,
        "auditivo": perfil_vark.puntaje_auditivo,
        "lectura": perfil_vark.puntaje_lectura,
        "kinestesico": perfil_vark.puntaje_kinestesico,
    }
    total = sum(puntajes.values()) or 1

    modalidades = []
    for clave, puntaje in puntajes.items():
        porcentaje = round((puntaje / total) * 100)
        modalidades.append(
            {
                "clave": clave,
                "nombre": MODALIDADES_VARK[clave],
                "puntaje": puntaje,
                "porcentaje": porcentaje,
                "reglas": REGLAS_VARK[clave],
            }
        )

    modalidades_ordenadas = sorted(
        modalidades,
        key=lambda item: item["puntaje"],
        reverse=True,
    )

    dominantes = [item for item in modalidades_ordenadas if item["puntaje"] > 0]
    dominante = MODALIDADES_VARK.get(perfil_vark.estilo_principal, perfil_vark.estilo_display)
    secundarias = [
        item for item in dominantes
        if item["clave"] != perfil_vark.estilo_principal
    ]

    mezcla = ", ".join(
        f"{item['nombre']} {item['porcentaje']}%"
        for item in modalidades_ordenadas
        if item["puntaje"] > 0
    )

    if not mezcla:
        mezcla = f"{dominante} como perfil principal"

    reglas_activas = []
    for item in dominantes:
        reglas_activas.append(
            f"{item['nombre']} ({item['porcentaje']}%): " + ", ".join(item["reglas"][:4])
        )

    return {
        "puntajes": puntajes,
        "modalidades": modalidades_ordenadas,
        "dominante": dominante,
        "secundarias": secundarias,
        "mezcla": mezcla,
        "reglas_activas": reglas_activas,
    }


def construir_contexto_materiales(materiales):
    partes = []

    for material in materiales:
        partes.append(f"Material: {material.titulo}")
        partes.append(f"Tema general: {material.tema or 'No especificado'}")

        if material.temario_examen:
            partes.append("Temario del examen:")
            partes.append(material.temario_examen)

        if material.resumen_ia:
            partes.append("Resumen IA:")
            partes.append(material.resumen_ia)

        if material.temas_clave_ia:
            partes.append("Temas clave IA:")
            partes.append(material.temas_clave_ia)

        if material.preguntas_sugeridas_ia:
            partes.append("Preguntas sugeridas IA:")
            partes.append(material.preguntas_sugeridas_ia)

        if material.recomendacion_ia:
            partes.append("Recomendación IA:")
            partes.append(material.recomendacion_ia)

        if material.texto_extraido:
            texto_recortado = Truncator(material.texto_extraido).chars(9000)
            partes.append("Texto extraído parcial:")
            partes.append(texto_recortado)

        partes.append("\n---\n")

    contexto = "\n".join(partes).strip()

    return Truncator(contexto).chars(MAX_CARACTERES_CONTEXTO_MATERIAL)


def generar_ruta_con_gemini(
    perfil_vark,
    perfil_vark_detalle,
    datos_academicos,
    materiales,
    contexto_materiales,
    dias_hasta_examen,
    dias_planificados,
):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        return {}

    if os.getenv("LLM_PROVIDER", "gemini").strip().lower() != "gemini":
        return {}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()

        temarios = []

        for material in materiales:
            if material.temario_examen:
                temarios.append(material.temario_examen)

        temario_unificado = "\n".join(temarios).strip()
        hay_materiales = bool(materiales)
        origen_contexto = (
            "dataset interno de Anatomía I + materiales procesados del estudiante"
            if hay_materiales
            else "dataset interno de Anatomía I sin materiales adicionales"
        )

        reglas_vark_texto = "\n".join(
            f"- {regla}" for regla in perfil_vark_detalle["reglas_activas"]
        )

        prompt = f"""
Actúa como tutor académico de Anatomía I y genera una ruta de aprendizaje personalizada.

BASE OBLIGATORIA DEL SISTEMA:
- Libro base del dataset: Rouvière y Delmas, Anatomía Humana descriptiva, topográfica y funcional. Tomo 2: Tronco.
- El tema y el punto específico fueron seleccionados desde un dataset interno basado en el índice del libro.
- La ruta debe generarse aunque el estudiante todavía no haya subido materiales.
- Los materiales subidos NO son requisito; solo enriquecen el contexto del LLM cuando existen.
- Origen del contexto disponible ahora: {origen_contexto}.

DATOS DEL ESTUDIANTE:
- Estilo VARK principal: {perfil_vark.estilo_display}
- Distribución VARK real: {perfil_vark_detalle['mezcla']}
- Puntaje visual: {perfil_vark.puntaje_visual}
- Puntaje auditivo: {perfil_vark.puntaje_auditivo}
- Puntaje lectura/escritura: {perfil_vark.puntaje_lectura}
- Puntaje kinestésico: {perfil_vark.puntaje_kinestesico}

REGLAS DE ADAPTACIÓN VARK:
{reglas_vark_texto}

Instrucción importante de VARK:
- No uses solo el estilo principal si existen otros puntajes positivos.
- Prioriza el estilo principal, pero combina proporcionalmente las modalidades que también tuvieron puntaje.
- Si una modalidad tiene 0 puntos, no la priorices.
- Ejemplo: si Auditivo tiene 50%, Visual 30% y Kinestésico 20%, la ruta debe ser principalmente auditiva, con apoyo visual y actividades prácticas.

DATOS ACADÉMICOS:
- Materia: {datos_academicos.materia}
- Tema actual seleccionado: {datos_academicos.tema_actual}
- Punto específico que le cuesta más: {datos_academicos.temas_dificiles or 'No especificado'}
- Fecha de examen: {datos_academicos.fecha_examen_formateada}
- Días hasta el examen: {dias_hasta_examen}
- Días que debes planificar ahora: {dias_planificados}
- Minutos disponibles por día: {datos_academicos.minutos_por_dia}
- Tipo de examen: {datos_academicos.get_tipo_examen_display()}
- Objetivo de estudio: {datos_academicos.objetivo_estudio or 'No especificado'}

TEMARIO ESPECÍFICO DEL EXAMEN EXTRAÍDO DE MATERIALES, SI EXISTE:
\"\"\"
{temario_unificado or 'No hay temario adicional cargado por materiales.'}
\"\"\"

CONTEXTO DE MATERIALES SUBIDOS Y ANALIZADOS, SI EXISTE:
\"\"\"
{contexto_materiales or 'No hay materiales subidos. Genera la ruta con el dataset interno, el tema seleccionado, el punto específico y el resultado VARK.'}
\"\"\"

Devuelve únicamente JSON válido con esta estructura exacta:

{{
  "titulo": "Título de la ruta",
  "resumen_general": "Resumen breve de la estrategia general de estudio, indicando que se usa VARK + dataset de Anatomía I + materiales si existen.",
  "temas_priorizados": [
    "Tema 1",
    "Tema 2",
    "Tema 3"
  ],
  "plan_diario": [
    {{
      "dia": 1,
      "titulo": "Título del día",
      "tema_principal": "Tema principal del día",
      "objetivo": "Objetivo concreto del día",
      "minutos": 15,
      "enfoque_vark": "Cómo se adapta este día al resultado VARK del estudiante",
      "recurso_vark": "Recurso principal recomendado según VARK, por ejemplo guion oral, mapa, glosario, caso práctico",
      "uso_materiales": "Indica si este día usa dataset base o también material subido",
      "actividades": [
        "Actividad 1 adaptada al estilo VARK y al tema seleccionado",
        "Actividad 2",
        "Actividad 3"
      ],
      "autoevaluacion": [
        "Pregunta o tarea de autoevaluación 1",
        "Pregunta o tarea de autoevaluación 2"
      ],
      "producto_esperado": "Qué debe lograr o producir el estudiante al final del día"
    }}
  ],
  "recomendaciones_finales": [
    "Recomendación 1",
    "Recomendación 2",
    "Recomendación 3"
  ]
}}

REGLAS OBLIGATORIAS:
- Escribe en español.
- El arreglo plan_diario debe tener exactamente {dias_planificados} elementos.
- Cada día debe usar como máximo {datos_academicos.minutos_por_dia} minutos.
- Enfoca la ruta en el tema actual y el punto específico difícil.
- La ruta debe reflejar claramente el resultado VARK y sus puntajes, no solo decir el nombre del estilo.
- Si no hay materiales subidos, no bloquees la ruta: usa el dataset base y recomienda subir material como mejora opcional.
- Si hay materiales subidos, úsalos como contexto adicional para enriquecer actividades y autoevaluación.
- No inventes información anatómica específica que no esté en el contexto; si falta contenido, formula actividades de estudio centradas en revisar el libro base.
- No uses markdown.
- No agregues texto fuera del JSON.
"""

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.35,
            ),
        )

        contenido = limpiar_json(response.text)
        data = json.loads(contenido)

        return validar_respuesta_ruta(data, dias_planificados, datos_academicos.minutos_por_dia)

    except Exception as error:
        print("Error generando ruta con Gemini:", error)
        return {}


def validar_respuesta_ruta(data, dias_planificados, minutos_maximos):
    if not isinstance(data, dict):
        return {}

    plan_diario = data.get("plan_diario", [])

    if not isinstance(plan_diario, list):
        plan_diario = []

    plan_limpio = []

    for index, dia in enumerate(plan_diario[:dias_planificados], start=1):
        if not isinstance(dia, dict):
            continue

        minutos = int(dia.get("minutos") or minutos_maximos)
        minutos = max(5, min(minutos, minutos_maximos))

        plan_limpio.append(
            {
                "dia": int(dia.get("dia") or index),
                "titulo": str(dia.get("titulo", f"Día {index}")).strip(),
                "tema_principal": str(dia.get("tema_principal", "")).strip(),
                "objetivo": str(dia.get("objetivo", "")).strip(),
                "minutos": minutos,
                "enfoque_vark": str(dia.get("enfoque_vark", "")).strip(),
                "recurso_vark": str(dia.get("recurso_vark", "")).strip(),
                "uso_materiales": str(dia.get("uso_materiales", "")).strip(),
                "actividades": normalizar_lista(dia.get("actividades", [])),
                "autoevaluacion": normalizar_lista(dia.get("autoevaluacion", [])),
                "producto_esperado": str(dia.get("producto_esperado", "")).strip(),
            }
        )

    if not plan_limpio:
        return {}

    return {
        "titulo": str(
            data.get("titulo", "Ruta de aprendizaje personalizada")
        ).strip(),
        "resumen_general": str(data.get("resumen_general", "")).strip(),
        "temas_priorizados": normalizar_lista(data.get("temas_priorizados", [])),
        "plan_diario": plan_limpio,
        "recomendaciones_finales": normalizar_lista(
            data.get("recomendaciones_finales", [])
        ),
    }


def generar_ruta_respaldo(
    perfil_vark,
    perfil_vark_detalle,
    datos_academicos,
    dias_hasta_examen,
    dias_planificados,
):
    temas_base = []

    if datos_academicos.tema_actual:
        temas_base.append(datos_academicos.tema_actual)

    if datos_academicos.temas_dificiles:
        temas_base.append(datos_academicos.temas_dificiles)

    temas_base.extend(["Repaso guiado", "Autoevaluación", "Refuerzo final"])

    actividades_por_estilo = {
        "visual": [
            "Crea un mapa conceptual del tema seleccionado.",
            "Dibuja un esquema simple con relaciones anatómicas y usa colores para diferenciar partes.",
            "Convierte el punto difícil en una tabla visual de ubicación, relación y función.",
        ],
        "auditivo": [
            "Explica el tema en voz alta como si enseñaras a un compañero.",
            "Graba un audio de 2 a 3 minutos con tu resumen del tema.",
            "Responde preguntas oralmente sin mirar apuntes y corrige tus dudas al final.",
        ],
        "lectura": [
            "Lee el tema y escribe un resumen breve con subtítulos.",
            "Crea un glosario con términos anatómicos importantes.",
            "Reformula con tus palabras el punto específico que te cuesta más.",
        ],
        "kinestesico": [
            "Resuelve una actividad de identificación anatómica sobre el tema.",
            "Relaciona cada estructura con su ubicación, función o relación anatómica.",
            "Realiza un mini simulacro práctico con preguntas de reconocimiento.",
        ],
    }

    actividades_mixtas = []
    for item in perfil_vark_detalle["modalidades"]:
        if item["puntaje"] <= 0:
            continue
        actividades_mixtas.extend(actividades_por_estilo[item["clave"]][:1])

    if not actividades_mixtas:
        actividades_mixtas = actividades_por_estilo.get(
            perfil_vark.estilo_principal,
            actividades_por_estilo["lectura"],
        )

    plan = []

    for dia in range(1, dias_planificados + 1):
        tema = temas_base[(dia - 1) % len(temas_base)]

        plan.append(
            {
                "dia": dia,
                "titulo": f"Día {dia}: {tema}",
                "tema_principal": tema,
                "objetivo": f"Comprender y repasar el tema: {tema} usando tu distribución VARK.",
                "minutos": datos_academicos.minutos_por_dia,
                "enfoque_vark": f"Ruta adaptada a {perfil_vark_detalle['mezcla']}.",
                "recurso_vark": "Actividad combinada según tus puntajes VARK.",
                "uso_materiales": "Dataset base de Anatomía I. Puedes subir materiales para enriquecer esta ruta.",
                "actividades": actividades_mixtas[:4],
                "autoevaluacion": [
                    "Explica qué aprendiste sin mirar el material.",
                    "Escribe o responde oralmente dos preguntas sobre el punto difícil.",
                    "Marca qué parte necesitas repasar de nuevo.",
                ],
                "producto_esperado": "Evidencia breve de estudio: audio, esquema, glosario o ejercicio según tu VARK.",
            }
        )

    return {
        "titulo": "Ruta de aprendizaje personalizada con VARK y dataset de Anatomía I",
        "resumen_general": (
            "Esta ruta se genera con tus datos académicos, tu distribución VARK y el dataset interno de Anatomía I. "
            "Los materiales subidos son opcionales y sirven para enriquecer el contexto del LLM."
        ),
        "temas_priorizados": temas_base[:5],
        "plan_diario": plan,
        "recomendaciones_finales": [
            "Regenera la ruta después de subir materiales procesados para que Gemini tenga más contexto.",
            "Respeta el tiempo diario seleccionado y cierra cada sesión con autoevaluación.",
            "Prioriza el punto específico que marcaste como difícil.",
        ],
    }


def normalizar_lista(valor):
    if isinstance(valor, list):
        return [str(item).strip() for item in valor if str(item).strip()]

    if isinstance(valor, str):
        return [linea.strip() for linea in valor.splitlines() if linea.strip()]

    return []


def limpiar_json(texto):
    texto = str(texto or "").strip()

    if texto.startswith("```json"):
        texto = texto.replace("```json", "", 1).strip()

    if texto.startswith("```"):
        texto = texto.replace("```", "", 1).strip()

    if texto.endswith("```"):
        texto = texto[:-3].strip()

    return texto
