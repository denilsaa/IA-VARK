import json
import os

from django.utils.text import Truncator

from .models import RutaAprendizaje


MAX_CARACTERES_CONTEXTO_MATERIAL = 24000
MAX_DIAS_PLAN = 21


def generar_ruta_aprendizaje(user, perfil_vark, datos_academicos, materiales):
    dias_hasta_examen = datos_academicos.dias_restantes
    dias_planificados = calcular_dias_planificados(dias_hasta_examen)

    contexto_materiales = construir_contexto_materiales(materiales)

    respuesta = generar_ruta_con_gemini(
        perfil_vark=perfil_vark,
        datos_academicos=datos_academicos,
        materiales=materiales,
        contexto_materiales=contexto_materiales,
        dias_hasta_examen=dias_hasta_examen,
        dias_planificados=dias_planificados,
    )

    if not respuesta:
        respuesta = generar_ruta_respaldo(
            perfil_vark=perfil_vark,
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

    contexto = "\n".join(partes)

    return Truncator(contexto).chars(MAX_CARACTERES_CONTEXTO_MATERIAL)


def generar_ruta_con_gemini(
    perfil_vark,
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

        prompt = f"""
Genera una ruta de aprendizaje personalizada para un estudiante de Anatomía I.

Datos del estudiante:
- Estilo VARK principal: {perfil_vark.estilo_display}
- Puntaje visual: {perfil_vark.puntaje_visual}
- Puntaje auditivo: {perfil_vark.puntaje_auditivo}
- Puntaje lectura/escritura: {perfil_vark.puntaje_lectura}
- Puntaje kinestésico: {perfil_vark.puntaje_kinestesico}

Datos académicos:
- Materia: {datos_academicos.materia}
- Tema actual: {datos_academicos.tema_actual}
- Fecha de examen: {datos_academicos.fecha_examen_formateada}
- Días hasta el examen: {dias_hasta_examen}
- Días que debes planificar ahora: {dias_planificados}
- Minutos disponibles por día: {datos_academicos.minutos_por_dia}
- Tipo de examen: {datos_academicos.get_tipo_examen_display()}
- Nivel de dificultad percibido: {datos_academicos.get_nivel_dificultad_display()}
- Temas difíciles: {datos_academicos.temas_dificiles or "No especificados"}
- Objetivo de estudio: {datos_academicos.objetivo_estudio or "No especificado"}

Temario específico del examen:
\"\"\"
{temario_unificado or "No se especificó temario."}
\"\"\"

Contexto del material subido y analizado:
\"\"\"
{contexto_materiales}
\"\"\"

Devuelve únicamente JSON válido con esta estructura exacta:

{{
  "titulo": "Título de la ruta",
  "resumen_general": "Resumen breve de la estrategia general de estudio.",
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
      "minutos": 60,
      "actividades": [
        "Actividad 1 adaptada al estilo VARK",
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

Reglas obligatorias:
- Escribe en español.
- El arreglo plan_diario debe tener exactamente {dias_planificados} elementos.
- Cada día debe usar como máximo {datos_academicos.minutos_por_dia} minutos.
- Enfoca la ruta en el temario del examen.
- Adapta actividades al estilo VARK principal.
- Si el estudiante es visual, usa mapas, esquemas, dibujos, tablas y colores.
- Si es auditivo, usa explicación oral, repetición en voz alta, preguntas orales y audios.
- Si es lectura/escritura, usa resúmenes, glosarios, listas, cuadros y reformulación escrita.
- Si es kinestésico, usa práctica, casos, identificación, simulacros y actividades aplicadas.
- Incluye repasos y autoevaluación.
- No inventes capítulos que no estén relacionados con el material.
- No uses markdown.
- No agregues texto fuera del JSON.
"""

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.4,
            ),
        )

        contenido = limpiar_json(response.text)
        data = json.loads(contenido)

        return validar_respuesta_ruta(data, dias_planificados)

    except Exception as error:
        print("Error generando ruta con Gemini:", error)
        return {}


def validar_respuesta_ruta(data, dias_planificados):
    if not isinstance(data, dict):
        return {}

    plan_diario = data.get("plan_diario", [])

    if not isinstance(plan_diario, list):
        plan_diario = []

    plan_limpio = []

    for index, dia in enumerate(plan_diario[:dias_planificados], start=1):
        if not isinstance(dia, dict):
            continue

        plan_limpio.append(
            {
                "dia": int(dia.get("dia") or index),
                "titulo": str(dia.get("titulo", f"Día {index}")).strip(),
                "tema_principal": str(dia.get("tema_principal", "")).strip(),
                "objetivo": str(dia.get("objetivo", "")).strip(),
                "minutos": int(dia.get("minutos") or 60),
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
    datos_academicos,
    dias_hasta_examen,
    dias_planificados,
):
    temas_base = []

    if datos_academicos.temas_dificiles:
        temas_base.extend(
            [
                tema.strip()
                for tema in datos_academicos.temas_dificiles.splitlines()
                if tema.strip()
            ]
        )

    if not temas_base:
        temas_base = [
            datos_academicos.tema_actual,
            "Repaso teórico",
            "Autoevaluación",
        ]

    actividades_por_estilo = {
        "visual": [
            "Crear un mapa conceptual del tema principal.",
            "Dibujar un esquema con relaciones anatómicas.",
            "Usar colores para diferenciar órganos, regiones y relaciones.",
        ],
        "auditivo": [
            "Explicar el tema en voz alta como si estuvieras enseñando.",
            "Grabar un audio corto con el resumen del tema.",
            "Responder preguntas oralmente sin mirar apuntes.",
        ],
        "lectura": [
            "Leer el tema y escribir un resumen breve.",
            "Crear un glosario con términos anatómicos importantes.",
            "Organizar la información en listas y cuadros comparativos.",
        ],
        "kinestesico": [
            "Resolver preguntas de identificación anatómica.",
            "Relacionar cada estructura con una función o ubicación.",
            "Hacer un simulacro corto del tema estudiado.",
        ],
    }

    actividades = actividades_por_estilo.get(
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
                "objetivo": f"Comprender y repasar el tema: {tema}.",
                "minutos": datos_academicos.minutos_por_dia,
                "actividades": actividades,
                "autoevaluacion": [
                    "Escribe tres ideas clave del tema.",
                    "Responde dos preguntas sin mirar el material.",
                    "Marca qué parte necesitas repasar de nuevo.",
                ],
                "producto_esperado": "Resumen breve y lista de dudas para repasar.",
            }
        )

    return {
        "titulo": "Ruta de aprendizaje personalizada",
        "resumen_general": (
            "Esta ruta organiza tu estudio según tus datos académicos y tu estilo VARK. "
            "Se prioriza avanzar de forma diaria con actividades breves, repaso y autoevaluación."
        ),
        "temas_priorizados": temas_base,
        "plan_diario": plan,
        "recomendaciones_finales": [
            "Estudia en bloques cortos y constantes.",
            "Realiza autoevaluación al final de cada sesión.",
            "Refuerza los temas que aparezcan como más difíciles.",
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