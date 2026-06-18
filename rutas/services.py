import base64
import json
import os
import re
import time
from pathlib import Path

import requests

from django.conf import settings
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

    respuesta = enriquecer_plan_con_imagenes_ia(
        respuesta=respuesta,
        user=user,
        datos_academicos=datos_academicos,
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

    modalidades_ordenadas = sorted(modalidades, key=lambda item: item["puntaje"], reverse=True)
    dominante = MODALIDADES_VARK.get(perfil_vark.estilo_principal, perfil_vark.estilo_display)
    activas = [item for item in modalidades_ordenadas if item["puntaje"] > 0]
    secundarias = [item for item in activas if item["clave"] != perfil_vark.estilo_principal]

    mezcla = ", ".join(
        f"{item['nombre']} {item['porcentaje']}%" for item in activas
    ) or f"{dominante} como perfil principal"

    reglas_activas = [
        f"{item['nombre']} ({item['porcentaje']}%): " + ", ".join(item["reglas"][:4])
        for item in activas
    ]

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

        temarios = [material.temario_examen for material in materiales if material.temario_examen]
        temario_unificado = "\n".join(temarios).strip()
        origen_contexto = (
            "dataset interno de Anatomía I + materiales procesados del estudiante"
            if materiales else
            "dataset interno de Anatomía I sin materiales adicionales"
        )
        reglas_vark_texto = "\n".join(f"- {regla}" for regla in perfil_vark_detalle["reglas_activas"])

        prompt = f'''
Actúa como tutor experto de Anatomía I. Debes generar una ruta multirecurso, concreta y muy accionable.

OBJETIVO CENTRAL:
La ruta debe ayudar a aprender de verdad. No debe ser solo texto. Cada día debe incluir recursos concretos que el estudiante pueda usar directamente: audio, mapa mental, ejercicio práctico e imagen anatómica guiada cuando aplique.

BASE OBLIGATORIA:
- Libro base del dataset: Rouvière y Delmas, Anatomía Humana descriptiva, topográfica y funcional. Tomo 2: Tronco.
- El tema y el punto específico fueron seleccionados desde un dataset interno del libro.
- La ruta debe generarse incluso si no hay materiales subidos.
- Los materiales subidos son opcionales y solo enriquecen el contexto.
- Origen del contexto actual: {origen_contexto}.

DATOS DEL ESTUDIANTE:
- Estilo VARK principal: {perfil_vark.estilo_display}
- Distribución VARK real: {perfil_vark_detalle['mezcla']}
- Puntaje visual: {perfil_vark.puntaje_visual}
- Puntaje auditivo: {perfil_vark.puntaje_auditivo}
- Puntaje lectura/escritura: {perfil_vark.puntaje_lectura}
- Puntaje kinestésico: {perfil_vark.puntaje_kinestesico}

REGLAS DE ADAPTACIÓN VARK:
{reglas_vark_texto}

INTERPRETACIÓN OBLIGATORIA DEL PERFIL:
- No basta con nombrar el estilo principal.
- Convierte la distribución VARK en recursos reales.
- Si Auditivo tiene el mayor puntaje, cada día debe incluir un guion de audio breve, natural, conversacional y escuchable; no debe parecer un texto académico largo. Debe sonar como una explicación docente clara y motivadora.
- Si Visual tiene puntaje positivo, cada día debe incluir un recurso visual y una imagen anatómica guiada o señalada.
- Si Kinestésico tiene puntaje positivo, cada día debe incluir un ejercicio práctico de identificación o aplicación.
- Si Lectura/Escritura tiene puntaje positivo, incluye un resumen o glosario.
- Si una modalidad tiene 0 puntos, no la priorices.
- Ejemplo: Auditivo 50%, Visual 30%, Kinestésico 20%, Lectura 0% debe producir una ruta principalmente auditiva, con apoyo visual, imagen anatómica guiada y práctica kinestésica.

DATOS ACADÉMICOS:
- Materia: {datos_academicos.materia}
- Tema actual seleccionado: {datos_academicos.tema_actual}
- Punto específico difícil: {datos_academicos.temas_dificiles or 'No especificado'}
- Fecha de examen: {datos_academicos.fecha_examen_formateada}
- Días hasta el examen: {dias_hasta_examen}
- Días a planificar ahora: {dias_planificados}
- Minutos por día: {datos_academicos.minutos_por_dia}
- Tipo de examen: {datos_academicos.get_tipo_examen_display()}
- Objetivo de estudio: {datos_academicos.objetivo_estudio or 'No especificado'}

TEMARIO EXTRAÍDO DE MATERIALES SI EXISTE:
"""
{temario_unificado or 'No hay temario adicional cargado por materiales.'}
"""

CONTEXTO DE MATERIALES ANALIZADOS SI EXISTE:
"""
{contexto_materiales or 'No hay materiales subidos. Usa el dataset interno y el tema seleccionado para crear la ruta.'}
"""

Devuelve únicamente JSON válido con esta estructura exacta:
{{
  "titulo": "Título de la ruta",
  "resumen_general": "Resumen breve de la estrategia",
  "temas_priorizados": ["Tema 1", "Tema 2", "Tema 3"],
  "plan_diario": [
    {{
      "dia": 1,
      "titulo": "Título del día",
      "tema_principal": "Tema del día",
      "objetivo": "Objetivo concreto",
      "minutos": 15,
      "enfoque_vark": "Cómo se mezcla VARK hoy",
      "recurso_vark": "Recurso dominante del día",
      "uso_materiales": "Dataset base o dataset + materiales",
      "actividades": ["Actividad 1", "Actividad 2", "Actividad 3"],
      "autoevaluacion": ["Pregunta 1", "Pregunta 2"],
      "producto_esperado": "Resultado esperado del día",
      "mini_quiz": [
        {{
          "pregunta": "Pregunta evaluable del día",
          "opciones": ["Opción A", "Opción B", "Opción C", "Opción D"],
          "respuesta_correcta": "Opción A",
          "explicacion": "Explicación breve de por qué esa respuesta es correcta"
        }}
      ],
      "recursos": {{
        "audio": {{
          "habilitado": true,
          "titulo": "Audio del día",
          "guion": "Guion claro para ser escuchado en voz alta, de 90 a 180 palabras",
          "pasos_clave": ["Punto 1", "Punto 2", "Punto 3"]
        }},
        "visual": {{
          "habilitado": true,
          "titulo": "Mapa mental del tema",
          "tipo": "mapa_mental_html",
          "descripcion": "Descripción breve del mapa mental",
          "nodo_central": "Tema central en máximo 4 palabras",
          "ramas": [
            {{"titulo": "Rama 1", "detalle": "Explicación breve", "subpuntos": ["Subpunto 1", "Subpunto 2"]}},
            {{"titulo": "Rama 2", "detalle": "Explicación breve", "subpuntos": ["Subpunto 1", "Subpunto 2"]}},
            {{"titulo": "Rama 3", "detalle": "Explicación breve", "subpuntos": ["Subpunto 1", "Subpunto 2"]}},
            {{"titulo": "Rama 4", "detalle": "Explicación breve", "subpuntos": ["Subpunto 1", "Subpunto 2"]}}
          ],
          "apoyo_visual": ["Idea visual 1", "Idea visual 2", "Idea visual 3"]
        }},
        "kinestesico": {{
          "habilitado": true,
          "titulo": "Ejercicio práctico",
          "instrucciones": "Instrucciones del ejercicio práctico",
          "preguntas": ["Pregunta práctica 1", "Pregunta práctica 2"]
        }},
        "lectura": {{
          "habilitado": false,
          "titulo": "Resumen de lectura",
          "resumen": "Resumen corto si esta modalidad tiene puntaje positivo",
          "glosario": ["Término: definición breve"]
        }},
        "imagen_anatomica": {{
          "habilitado": true,
          "titulo": "Lámina anatómica generada por IA",
          "tipo_vista": "superior/anterior/lateral según corresponda",
          "descripcion": "Descripción breve de la lámina anatómica que debe observar el estudiante",
          "prompt_imagen": "Prompt detallado en español para crear una ilustración anatómica educativa estilo atlas médico sobre el tema del día",
          "preguntas": ["¿Qué estructura principal observas?", "¿Qué relación anatómica debes identificar?"],
          "modo_practica": "Primero observar la imagen sin leer respuestas y luego responder las preguntas"
        }}
      }}
    }}
  ],
  "recomendaciones_finales": ["Recomendación 1", "Recomendación 2", "Recomendación 3"]
}}

REGLAS OBLIGATORIAS:
- Escribe en español.
- plan_diario debe tener exactamente {dias_planificados} elementos.
- Cada día debe usar como máximo {datos_academicos.minutos_por_dia} minutos.
- Enfoca la ruta en el tema actual y el punto específico difícil.
- Si Auditivo > 0, genera audio.habilitado=true.
- Si Visual > 0, genera visual.habilitado=true. Debe incluir nodo_central y exactamente 4 ramas. Cada rama debe tener titulo, detalle y 2 o 3 subpuntos. NO generes imagen para el mapa mental; el sistema lo dibujará como HTML/SVG limpio.
- Si Visual > 0 o Kinestésico > 0, genera imagen_anatomica.habilitado=true. Debe incluir descripcion, preguntas, modo_practica y, si es posible, marcadores sugeridos con nombre, pista y detalle. El sistema construirá un prompt visual controlado por tema.
- No uses Mermaid como recurso principal.
- No uses texto dentro de imágenes generadas. El sistema añadirá textos, preguntas y marcadores fuera o encima de la imagen.
- Si Kinestésico > 0, genera kinestesico.habilitado=true.
- Si Lectura/Escritura > 0, genera lectura.habilitado=true; si es 0, puede quedar false.
- No inventes detalles anatómicos ultraespecíficos fuera del contexto; si falta precisión, enfoca la lámina en relaciones generales del tema y subtema, priorizando una vista anatómica realista y coherente.
- Cada día debe incluir mini_quiz con 3 preguntas evaluables.
- Cada pregunta del mini_quiz debe tener exactamente 4 opciones y una respuesta_correcta que coincida exactamente con una opción.
- Las preguntas deben evaluar el tema del día, la lámina, el audio o el ejercicio práctico.
- No uses markdown fuera del string mermaid.
- No agregues texto fuera del JSON.
'''

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
        recursos = dia.get("recursos") if isinstance(dia.get("recursos"), dict) else {}

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
                "mini_quiz": normalizar_mini_quiz(dia.get("mini_quiz", [])),
                "recursos": {
                    "audio": normalizar_audio(recursos.get("audio", {})),
                    "visual": normalizar_visual(recursos.get("visual", {})),
                    "kinestesico": normalizar_kinestesico(recursos.get("kinestesico", {})),
                    "lectura": normalizar_lectura(recursos.get("lectura", {})),
                    "imagen_anatomica": normalizar_imagen_anatomica(recursos.get("imagen_anatomica", {})),
                },
            }
        )

    if not plan_limpio:
        return {}

    return {
        "titulo": str(data.get("titulo", "Ruta de aprendizaje personalizada")).strip(),
        "resumen_general": str(data.get("resumen_general", "")).strip(),
        "temas_priorizados": normalizar_lista(data.get("temas_priorizados", [])),
        "plan_diario": plan_limpio,
        "recomendaciones_finales": normalizar_lista(data.get("recomendaciones_finales", [])),
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

    mezcla = perfil_vark_detalle["mezcla"]
    tiene_visual = perfil_vark.puntaje_visual > 0
    tiene_audio = perfil_vark.puntaje_auditivo > 0
    tiene_lectura = perfil_vark.puntaje_lectura > 0
    tiene_kin = perfil_vark.puntaje_kinestesico > 0

    plan = []
    for dia in range(1, dias_planificados + 1):
        tema = temas_base[(dia - 1) % len(temas_base)]
        audio_habilitado = tiene_audio
        visual_habilitado = tiene_visual
        kin_habilitado = tiene_kin
        lectura_habilitada = tiene_lectura
        imagen_habilitada = tiene_visual or tiene_kin

        mermaid = (
            f"mindmap\n"
            f"  root(({tema}))\n"
            f"    Definición\n"
            f"    Ubicación\n"
            f"    Relaciones\n"
            f"    Punto difícil\n"
            f"      {datos_academicos.temas_dificiles or 'Repasar'}"
        )

        marcadores = [
            {
                "id": 1,
                "nombre": tema,
                "x": 50,
                "y": 28,
                "pista": "Ubica la región o estructura principal del tema.",
                "detalle": f"Reconoce la idea principal relacionada con {tema}.",
            },
            {
                "id": 2,
                "nombre": datos_academicos.temas_dificiles or "Punto difícil",
                "x": 52,
                "y": 60,
                "pista": "Este es el punto específico que debes reforzar.",
                "detalle": "Relaciónalo con el tema principal del día.",
            },
        ]

        plan.append(
            {
                "dia": dia,
                "titulo": f"Día {dia}: {tema}",
                "tema_principal": tema,
                "objetivo": f"Comprender y repasar {tema} usando una mezcla VARK adaptada a {mezcla}.",
                "minutos": datos_academicos.minutos_por_dia,
                "enfoque_vark": (
                    f"Se prioriza {perfil_vark.estilo_display}. También se incorporan apoyos de {mezcla}."
                ),
                "recurso_vark": "Ruta multirecurso con audio, mapa, lámina anatómica y ejercicio práctico.",
                "uso_materiales": "Dataset base de Anatomía I. Puedes subir materiales para enriquecer esta ruta.",
                "actividades": [
                    f"Repasa el tema {tema} durante 5 minutos.",
                    "Escucha el guion generado y repítelo en voz alta.",
                    "Observa el mapa mental y la lámina anatómica con marcadores.",
                    "Resuelve el ejercicio práctico de identificación.",
                ],
                "autoevaluacion": [
                    f"Explica con tus palabras qué es {tema}.",
                    "Menciona dos relaciones anatómicas importantes.",
                    "Identifica el marcador 1 y el marcador 2 antes de revelar la respuesta.",
                ],
                "producto_esperado": "Un repaso activo con audio, esquema visual, lámina señalada, ejercicio práctico y mini quiz completado.",
                "mini_quiz": [
                    {
                        "pregunta": f"¿Cuál es el tema principal del día {dia}?",
                        "opciones": [tema, "Sistema nervioso central", "Miembro superior", "Neurocráneo"],
                        "respuesta_correcta": tema,
                        "explicacion": f"El día {dia} está centrado en {tema}, seleccionado desde tus datos académicos o el dataset.",
                    },
                    {
                        "pregunta": "¿Qué debes hacer primero en la lámina anatómica guiada?",
                        "opciones": [
                            "Identificar los marcadores antes de revelar la respuesta",
                            "Copiar todo el texto sin observar la imagen",
                            "Ignorar el punto difícil",
                            "Saltar directamente al examen final",
                        ],
                        "respuesta_correcta": "Identificar los marcadores antes de revelar la respuesta",
                        "explicacion": "La práctica visual y kinestésica mejora cuando intentas reconocer primero y luego verificas.",
                    },
                    {
                        "pregunta": f"¿Qué punto debes priorizar durante el repaso de {tema}?",
                        "opciones": [
                            datos_academicos.temas_dificiles or "El punto difícil seleccionado",
                            "Un tema no relacionado",
                            "Solo la decoración del mapa",
                            "Ningún punto específico",
                        ],
                        "respuesta_correcta": datos_academicos.temas_dificiles or "El punto difícil seleccionado",
                        "explicacion": "La ruta prioriza el punto específico que marcaste como más difícil.",
                    },
                ],
                "recursos": {
                    "audio": {
                        "habilitado": audio_habilitado,
                        "titulo": f"Audio: resumen de {tema}",
                        "guion": (
                            f"Hoy estudiarás {tema}. Primero comprende su idea general, su ubicación anatómica y su relación con "
                            f"el punto que más te cuesta: {datos_academicos.temas_dificiles or 'el subtema seleccionado'}. "
                            f"Repite en voz alta las ideas principales y trata de explicarlas como si enseñaras a otra persona."
                        ),
                        "pasos_clave": [
                            "Definir el tema con una frase clara.",
                            "Ubicarlo dentro del tronco.",
                            "Relacionarlo con el punto difícil seleccionado.",
                        ],
                    },
                    "visual": {
                        "habilitado": visual_habilitado,
                        "titulo": f"Mapa mental de {tema}",
                        "tipo": "mapa_mental",
                        "nodo_central": tema,
                        "ramas": [
                            {
                                "titulo": "Definición",
                                "detalle": f"Idea central de {tema} explicada con palabras simples.",
                                "subpuntos": ["Concepto base", "Función o importancia"],
                            },
                            {
                                "titulo": "Ubicación",
                                "detalle": "Dónde se reconoce dentro del tema anatómico seleccionado.",
                                "subpuntos": ["Región principal", "Referencia espacial"],
                            },
                            {
                                "titulo": "Relaciones",
                                "detalle": "Estructuras o conceptos que debes conectar para comprenderlo mejor.",
                                "subpuntos": ["Relación cercana", "Límite o conexión"],
                            },
                            {
                                "titulo": "Punto difícil",
                                "detalle": datos_academicos.temas_dificiles or "Subtema que debes reforzar durante el repaso.",
                                "subpuntos": ["Identificar", "Explicar sin mirar"],
                            },
                        ],
                        "mermaid": mermaid,
                        "apoyo_visual": [
                            "Ubicación general",
                            "Relaciones anatómicas",
                            datos_academicos.temas_dificiles or "Punto difícil",
                        ],
                    },
                    "kinestesico": {
                        "habilitado": kin_habilitado,
                        "titulo": f"Ejercicio práctico sobre {tema}",
                        "instrucciones": (
                            f"Sin mirar tus apuntes, identifica tres ideas principales de {tema} y compáralas con el punto difícil seleccionado."
                        ),
                        "preguntas": [
                            f"¿Cómo se relaciona {tema} con {datos_academicos.temas_dificiles or 'el punto difícil'}?",
                            f"¿Qué estructura o concepto debes reconocer primero en {tema}?",
                            "¿Qué volverías a practicar para fijar mejor el aprendizaje?",
                        ],
                    },
                    "lectura": {
                        "habilitado": lectura_habilitada,
                        "titulo": f"Resumen escrito de {tema}",
                        "resumen": (
                            f"Resume {tema} en 4 o 5 líneas, enfocándote en definición, ubicación, relaciones y el punto difícil elegido."
                        ),
                        "glosario": [
                            f"{tema}: concepto principal del día.",
                            f"{datos_academicos.temas_dificiles or 'Punto difícil'}: subtema a reforzar.",
                        ],
                    },
                    "imagen_anatomica": {
                        "habilitado": imagen_habilitada,
                        "titulo": f"Lámina anatómica guiada de {tema}",
                        "tipo_vista": "superior",
                        "descripcion": (
                            f"Observa la silueta del tronco y trata de identificar primero el tema principal y luego el punto difícil: "
                            f"{datos_academicos.temas_dificiles or 'subtema seleccionado'}."
                        ),
                        "marcadores": marcadores,
                        "preguntas": [
                            "¿Qué estructura representa el marcador 1?",
                            "¿Qué representa el marcador 2 y cómo se relaciona con el tema principal?",
                        ],
                        "modo_practica": "Primero intenta identificar sin ver la respuesta y luego revela el nombre de cada marcador.",
                    },
                },
            }
        )

    return {
        "titulo": "Ruta de aprendizaje 10/10 con VARK, láminas y ejercicios",
        "resumen_general": (
            "Esta ruta combina tu distribución VARK con el dataset interno de Anatomía I. "
            "Cada día puede incluir audio, mapa mental, lámina anatómica guiada, ejercicio práctico y apoyo de lectura según tus puntajes."
        ),
        "temas_priorizados": temas_base[:5],
        "plan_diario": plan,
        "recomendaciones_finales": [
            "Escucha el audio de cada día al menos dos veces.",
            "Usa la lámina anatómica para identificar sin mirar primero y revelar después.",
            "Si subes materiales, regenera la ruta para obtener actividades y marcadores más precisos.",
        ],
    }



def detectar_categoria_tema(tema: str, punto_dificil: str = "") -> str:
    t = f"{tema or ''} {punto_dificil or ''}".strip().lower()

    # Primero casos específicos para evitar mala clasificación.
    if (
        "linfático" in t or "linfatico" in t or
        "linfáticos" in t or "linfaticos" in t or
        "nódulo" in t or "nodulo" in t or "linfa" in t
    ):
        return "linfatico"

    if "periné" in t or "perine" in t:
        return "perine"

    if "articulacion" in t or "articulación" in t or "articulaciones" in t or "ligamento" in t:
        return "articular"

    if "nervio" in t or "nervios" in t or "plexo" in t:
        return "nervioso"

    if (
        "vaso" in t or "vasos" in t or
        "arteria" in t or "arterias" in t or
        "vena" in t or "venas" in t or
        "corazón" in t or "corazon" in t
    ):
        return "vascular"

    if (
        "músculo" in t or "musculo" in t or
        "músculos" in t or "musculos" in t or
        "diafragma" in t
    ):
        return "muscular"

    if (
        "órgano" in t or "organo" in t or
        "órganos" in t or "organos" in t or
        "abdomen" in t or
        "víscera" in t or "viscera" in t or
        "vejiga" in t or "recto" in t or "útero" in t or "utero" in t
    ):
        if "pelvis" in t or "pelvis menor" in t:
            return "pelvis_visceral"
        return "visceral"

    if (
        "pelvis" in t or
        "esqueleto" in t or "hueso" in t or "óseo" in t or "oseo" in t or
        "columna vertebral" in t or "columna" in t or
        "tórax" in t or "torax" in t
    ):
        return "pelvis_osea" if "pelvis" in t else "oseo"

    return "general"

def construir_prompt_visual_controlado(tema: str, datos_academicos=None, anatomica=None) -> tuple[str, str, str]:
    """Devuelve (prompt_positivo, prompt_negativo, categoria) para ComfyUI.
    Evita prompts libres del LLM porque generan cráneos, pósters, texto falso o anatomía incoherente.
    """
    anatomica = anatomica or {}
    punto = ""
    if datos_academicos is not None:
        punto = getattr(datos_academicos, "temas_dificiles", "") or ""
    if not punto and isinstance(anatomica, dict):
        punto = anatomica.get("descripcion", "") or anatomica.get("titulo", "") or ""

    categoria = detectar_categoria_tema(tema, punto)
    contexto = f"Topic: {tema}. Focus: {punto or 'general anatomy review'}. "

    negative_base = (
        "text, labels, letters, words, watermark, logo, blurry, low quality, low resolution, "
        "bad anatomy, deformed anatomy, malformed structures, extra bones, wrong body part, "
        "messy composition, vintage poster, old paper, infographic, fake writing, unreadable text, "
        "surgery, blood, gore"
    )

    if categoria == "pelvis_osea":
        positive = (
            contexto +
            "professional medical atlas illustration of the HUMAN BONY PELVIS ONLY, isolated pelvis bone, "
            "front anterior view or slight superior view, clearly visible iliac bones, sacrum, coccyx, pubis, ischium, pubic symphysis, "
            "realistic bone texture, clean white background, centered composition, textbook anatomy plate, high detail, no text, no labels"
        )
        negative = negative_base + ", skull, cranium, head, face, teeth, jaw, mandible, eyes, nose, ribs, chest, full skeleton, full body, skin, muscles, organs"
    elif categoria == "pelvis_visceral":
        positive = (
            contexto +
            "educational medical atlas cutaway illustration of the pelvis minor with internal pelvic organs, "
            "clear pelvic cavity, bladder, rectum, uterus and vagina when female anatomy applies, spatial relationships visible, "
            "clean modern medical teaching style, centered composition, high detail, no text, no labels"
        )
        negative = negative_base + ", skull, head, face, erotic, sexualized, explicit nudity, full body glamour, poster, random torso, unrelated limbs"
    elif categoria == "oseo":
        positive = (
            contexto +
            "professional medical atlas illustration focused on the selected bony anatomical region only, "
            "isolated skeletal structure, realistic bone texture, clean white background, textbook style, high detail, no text, no labels"
        )
        negative = negative_base + ", skull if not requested, face, skin, muscles, organs, full body"
    elif categoria == "articular":
        positive = (
            contexto +
            "professional medical atlas illustration focused on joints and ligaments, close-up anatomical view, "
            "clear articulation surfaces and stabilizing ligaments, clean white background, high detail, no text, no labels"
        )
        negative = negative_base + ", face, full body, unrelated organs, fashion pose"
    elif categoria == "muscular":
        positive = (
            contexto +
            "professional medical atlas illustration focused on muscular anatomy, clear layered muscle groups, "
            "teaching anatomy plate, neutral background, centered composition, high detail, no text, no labels"
        )
        negative = negative_base + ", bones only, organs only, glamour, erotic, face closeup"
    elif categoria == "visceral":
        positive = (
            contexto +
            "professional medical atlas cutaway illustration focused on internal organs, clear anatomical relationships, "
            "clean educational medical style, centered composition, high detail, no text, no labels"
        )
        negative = negative_base + ", erotic, sexualized, glamour, unrelated limbs, full body poster"
    elif categoria == "nervioso":
        positive = (
            contexto +
            "professional medical atlas illustration focused on nerves and nerve pathways, clear anatomical course, "
            "clean white background, high detail, no text, no labels"
        )
        negative = negative_base + ", random colors, organs emphasis only, poster"
    elif categoria == "vascular":
        positive = (
            contexto +
            "professional medical atlas illustration focused on arteries and veins, heart and major vessels if relevant, "
            "clear vascular pathways, clean educational composition, high detail, no text, no labels"
        )
        negative = negative_base + ", nerves only, muscles only, lymph nodes only, poster, fake labels"
    elif categoria == "linfatico":
        positive = (
            contexto +
            "professional medical atlas illustration focused on lymph nodes and lymphatic vessels, clear lymphatic drainage pathways, "
            "lymph node chains, clean educational anatomical composition, high detail, no text, no labels"
        )
        negative = negative_base + ", arteries only, veins only, unrelated muscles, full body glamour, random infographic, fake text"
    elif categoria == "perine":
        positive = (
            contexto +
            "professional educational anatomical cutaway illustration of the perineal region, respectful medical presentation, "
            "clear anatomical relationships, clean background, high detail, no text, no labels"
        )
        negative = negative_base + ", erotic, sexualized, glamour, explicit sexual content, fake labels"
    else:
        positive = (
            contexto +
            "professional educational medical atlas illustration of the selected anatomy topic, clean composition, "
            "white background, centered, high detail, no text, no labels"
        )
        negative = negative_base

    return positive, negative, categoria

def marcadores_sugeridos_por_categoria(categoria: str):
    if categoria == "pelvis_osea":
        return [
            {"id": 1, "nombre": "Sacro", "x": 50, "y": 24, "pista": "Estructura posterior central.", "detalle": "Forma la pared posterior de la pelvis ósea."},
            {"id": 2, "nombre": "Ilion", "x": 24, "y": 43, "pista": "Ala ósea amplia lateral.", "detalle": "Contribuye a la cintura pélvica y al límite lateral."},
            {"id": 3, "nombre": "Pubis", "x": 50, "y": 75, "pista": "Región anterior inferior.", "detalle": "Participa en la sínfisis púbica y el arco púbico."},
            {"id": 4, "nombre": "Isquion", "x": 74, "y": 68, "pista": "Porción posteroinferior del coxal.", "detalle": "Relacionado con la tuberosidad isquiática."},
        ]
    if categoria == "pelvis_visceral":
        return [
            {"id": 1, "nombre": "Vejiga", "x": 50, "y": 42, "pista": "Órgano anterior de la pelvis menor.", "detalle": "Se ubica por delante del recto."},
            {"id": 2, "nombre": "Útero / región reproductora", "x": 50, "y": 55, "pista": "Estructura central si aplica anatomía femenina.", "detalle": "Se relaciona con vejiga anteriormente y recto posteriormente."},
            {"id": 3, "nombre": "Recto", "x": 50, "y": 70, "pista": "Estructura posterior.", "detalle": "Ocupa la región posterior de la pelvis menor."},
            {"id": 4, "nombre": "Pared pélvica", "x": 25, "y": 52, "pista": "Límite lateral de la cavidad.", "detalle": "Sirve como referencia espacial para órganos y vasos."},
        ]
    return [
        {"id": 1, "nombre": "Estructura clave", "x": 50, "y": 35, "pista": "Observa el elemento central.", "detalle": "Relaciona esta estructura con el objetivo del día."},
        {"id": 2, "nombre": "Relación anatómica", "x": 32, "y": 55, "pista": "Compara posición y vecindad.", "detalle": "Describe qué estructura está medial, lateral, anterior o posterior."},
        {"id": 3, "nombre": "Límite o referencia", "x": 68, "y": 55, "pista": "Busca el borde o zona de transición.", "detalle": "Úsalo para ubicar el tema en el cuerpo."},
    ]


def mejorar_visual_para_mapa_html(visual: dict, tema: str):
    if not isinstance(visual, dict):
        return visual
    visual["image_url"] = ""
    visual["image_error"] = ""
    visual["tipo"] = "mapa_mental_html"
    visual.setdefault("nodo_central", tema)
    ramas = visual.get("ramas") or []
    apoyo = visual.get("apoyo_visual") or []
    if not ramas and apoyo:
        ramas = []
        for idx, item in enumerate(apoyo[:4], start=1):
            texto = str(item)
            if ":" in texto:
                titulo, detalle = texto.split(":", 1)
            else:
                titulo, detalle = texto, "Idea clave del tema."
            ramas.append({"titulo": titulo.strip(), "detalle": detalle.strip(), "subpuntos": []})
    visual["ramas"] = ramas[:4]
    return visual

def imagen_necesita_regeneracion(image_url):
    """
    True si la imagen no está guardada como base64.

    Motivo: si se guarda como /media/... o como URL de Cloudflare,
    se rompe cuando Render reinicia o cuando apagas tu PC/túnel.
    Las nuevas imágenes deben quedar como data:image/...;base64,... dentro del plan_json.
    """
    image_url = str(image_url or "").strip()
    if not image_url:
        return True
    if image_url.startswith("data:image/"):
        return False
    return True


def imagen_bytes_a_data_url(content, content_type="image/png"):
    """Convierte bytes de imagen a data URL para persistirla en plan_json/PostgreSQL."""
    content_type = str(content_type or "image/png").split(";")[0].strip()
    if "image" not in content_type:
        content_type = "image/png"
    encoded = base64.b64encode(content).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


def enriquecer_plan_con_imagenes_ia(respuesta, user, datos_academicos):
    """Genera SOLO las láminas anatómicas con ComfyUI/Gemini.
    El mapa mental se mantiene como HTML limpio para evitar texto falso o imágenes incoherentes.
    """
    if not isinstance(respuesta, dict):
        return respuesta

    plan = respuesta.get("plan_diario", [])
    if not isinstance(plan, list):
        return respuesta

    try:
        max_imagenes = int(os.getenv("MAX_IMAGENES_RUTA", "2"))
    except ValueError:
        max_imagenes = 2

    generar_imagenes = os.getenv("GENERAR_IMAGENES_RUTA", "true").strip().lower() in ["1", "true", "yes", "si", "sí"]
    imagenes_generadas = 0

    for dia in plan:
        if not isinstance(dia, dict):
            continue

        recursos = dia.get("recursos", {})
        if not isinstance(recursos, dict):
            continue

        numero_dia = dia.get("dia") or 1
        tema = dia.get("tema_principal") or datos_academicos.tema_actual or "Anatomía I"

        visual = recursos.get("visual", {})
        if isinstance(visual, dict) and visual.get("habilitado"):
            recursos["visual"] = mejorar_visual_para_mapa_html(visual, tema)

        anatomica = recursos.get("imagen_anatomica", {})
        if not (isinstance(anatomica, dict) and anatomica.get("habilitado")):
            continue

        prompt_controlado, negative_controlado, categoria = construir_prompt_visual_controlado(
            tema=tema,
            datos_academicos=datos_academicos,
            anatomica=anatomica,
        )
        anatomica["prompt_imagen"] = prompt_controlado
        anatomica["negative_prompt"] = negative_controlado
        anatomica["categoria_visual"] = categoria

        if not anatomica.get("marcadores"):
            anatomica["marcadores"] = marcadores_sugeridos_por_categoria(categoria)

        if generar_imagenes and imagenes_generadas < max_imagenes and imagen_necesita_regeneracion(anatomica.get("image_url")):
            image_url, image_error = generar_y_guardar_imagen_gemini(
                prompt=prompt_controlado,
                carpeta="laminas",
                nombre_archivo=f"user_{user.id}_dia_{numero_dia}_lamina.png",
                aspect_ratio="4:3",
                negative_prompt=negative_controlado,
            )
            if image_url:
                anatomica["image_url"] = image_url
                anatomica["image_error"] = ""
                anatomica["historial_generacion"] = {
                    "proveedor": os.getenv("IMAGE_PROVIDER", "local"),
                    "persistencia": "base64_en_plan_json",
                    "categoria": categoria,
                    "estado": "ok",
                }
                imagenes_generadas += 1
            elif image_error:
                anatomica["image_error"] = image_error
                anatomica["historial_generacion"] = {
                    "proveedor": os.getenv("IMAGE_PROVIDER", "local"),
                    "persistencia": "sin_imagen",
                    "categoria": categoria,
                    "estado": "error",
                    "detalle": image_error,
                }

    return respuesta


def construir_prompt_mapa_mental(tema, datos_academicos, visual):
    apoyo = visual.get("apoyo_visual", [])
    if isinstance(apoyo, list):
        apoyo_texto = ", ".join(str(item) for item in apoyo[:6])
    else:
        apoyo_texto = str(apoyo or "")

    return f"""
Crea una imagen educativa tipo mapa mental premium sobre Anatomía I.

Tema central: {tema}
Materia: {datos_academicos.materia}
Punto específico difícil: {datos_academicos.temas_dificiles or "No especificado"}
Ideas de apoyo: {apoyo_texto}

Requisitos visuales obligatorios:
- Formato horizontal 16:9.
- Estilo moderno, limpio, universitario y profesional.
- Fondo claro, con colores suaves tipo médico/anatómico.
- Nodo central grande, legible y centrado.
- 4 ramas principales bien distribuidas alrededor del nodo central.
- Cada rama debe tener texto corto en español.
- Usar conectores visuales claros.
- Debe verse como un recurso de estudio, no como decoración.
- Evitar errores ortográficos.
- Evitar exceso de texto.
- No usar logotipos, marcas de agua ni nombres de instituciones.
""".strip()


def construir_prompt_lamina_anatomica(tema, datos_academicos, anatomica):
    descripcion = anatomica.get("descripcion", "")

    return f"""
Crea una ilustración anatómica educativa estilo atlas médico para estudiantes universitarios.

Tema anatómico: {tema}
Materia: {datos_academicos.materia}
Punto específico difícil: {datos_academicos.temas_dificiles or "No especificado"}
Descripción didáctica: {descripcion}

Requisitos visuales obligatorios:
- Imagen anatómica clara, detallada y educativa.
- Estilo lámina de estudio universitario, no fotografía quirúrgica.
- Fondo claro.
- Vista anatómica coherente con el tema.
- Estructuras principales visibles y diferenciadas con colores suaves.
- Incluir etiquetas breves en español cuando ayuden a estudiar.
- Debe parecer una lámina anatómica real de repaso.
- No mostrar sangre, heridas, cirugía ni contenido gráfico.
- No usar marcas de agua, logotipos ni nombres de instituciones.
- Evitar texto excesivo.
""".strip()


def generar_y_guardar_imagen_gemini(prompt, carpeta, nombre_archivo, aspect_ratio="1:1", negative_prompt=None):
    """
    Punto único de generación de imágenes.
    - Si IMAGE_PROVIDER=local: usa tu PC por Cloudflare Tunnel + ComfyUI.
    - Si no: intenta Gemini Image como respaldo.
    Devuelve una tupla: (image_url, image_error)
    """
    provider = os.getenv("IMAGE_PROVIDER", "gemini").strip().lower()
    if provider == "local":
        return generar_y_guardar_imagen_local(prompt, carpeta, nombre_archivo, aspect_ratio, negative_prompt=negative_prompt)
    return generar_y_guardar_imagen_gemini_api(prompt, carpeta, nombre_archivo, aspect_ratio)


def generar_y_guardar_imagen_local(prompt, carpeta, nombre_archivo, aspect_ratio="1:1", negative_prompt=None):
    """
    Llama al servidor local de imágenes expuesto con Cloudflare Tunnel.
    Devuelve data:image/...;base64,... para que la imagen quede persistida en plan_json.

    Variables necesarias en Render:
    IMAGE_PROVIDER=local
    LOCAL_IMAGE_API_URL=https://TU-TUNEL.trycloudflare.com/generate-anatomy
    LOCAL_IMAGE_JOB_BASE_URL=https://TU-TUNEL.trycloudflare.com
    """
    api_url = os.getenv("LOCAL_IMAGE_API_URL", "").strip().rstrip("/")
    job_base_url = os.getenv("LOCAL_IMAGE_JOB_BASE_URL", "").strip().rstrip("/")

    if not api_url:
        return "", "Falta LOCAL_IMAGE_API_URL en Render."
    if not job_base_url:
        # Si no lo pusiste, lo inferimos quitando /generate-anatomy.
        job_base_url = api_url.replace("/generate-anatomy", "").rstrip("/")

    ruta_relativa = f"rutas_generadas/{carpeta}/{limpiar_nombre_archivo(nombre_archivo)}"
    ruta_absoluta = Path(settings.MEDIA_ROOT) / ruta_relativa
    ruta_absoluta.parent.mkdir(parents=True, exist_ok=True)

    # Ajustes de tamaño. Para demo conviene 1024x1024 o 1024x768.
    if aspect_ratio == "16:9":
        width, height = 1024, 768
    elif aspect_ratio == "4:3":
        width, height = 1024, 768
    else:
        width, height = 1024, 1024

    if not negative_prompt:
        negative_prompt = (
            "text, labels, letters, words, watermark, logo, blurry, low quality, "
            "distorted anatomy, deformed structures, extra bones, malformed bones, blood, gore, "
            "surgery, cartoon, messy composition, bad proportions, skull, head, face, teeth"
        )

    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
    }

    try:
        start_response = requests.post(
            api_url,
            json=payload,
            timeout=int(os.getenv("LOCAL_IMAGE_START_TIMEOUT", "30")),
        )
        start_response.raise_for_status()
        start_data = start_response.json()
        job_id = start_data.get("job_id")

        if not job_id:
            return "", f"La API local no devolvió job_id. Respuesta: {start_data}"

        max_wait = int(os.getenv("LOCAL_IMAGE_MAX_WAIT", "150"))
        poll_interval = int(os.getenv("LOCAL_IMAGE_POLL_INTERVAL", "5"))
        deadline = time.time() + max_wait
        last_status = "queued"
        last_error = ""

        while time.time() < deadline:
            time.sleep(poll_interval)
            job_response = requests.get(
                f"{job_base_url}/job/{job_id}",
                timeout=int(os.getenv("LOCAL_IMAGE_JOB_TIMEOUT", "30")),
            )
            job_response.raise_for_status()
            job_data = job_response.json()
            last_status = job_data.get("status", "")
            last_error = job_data.get("error", "")

            if last_status == "done":
                download_url = job_data.get("download_url")
                if not download_url:
                    return "", f"Job terminado, pero sin download_url. Respuesta: {job_data}"

                if download_url.startswith("http"):
                    image_url = download_url
                else:
                    image_url = f"{job_base_url}{download_url}"

                image_response = requests.get(image_url, timeout=90)
                image_response.raise_for_status()

                # Guardado clave para la demo:
                # La imagen se convierte a Base64 y se guarda dentro del plan_json.
                # Así no depende del túnel de Cloudflare ni del filesystem efímero de Render.
                data_url = imagen_bytes_a_data_url(
                    image_response.content,
                    image_response.headers.get("content-type", "image/png"),
                )

                # Copia local opcional solo para depuración cuando MEDIA_ROOT exista.
                try:
                    ruta_absoluta.write_bytes(image_response.content)
                except Exception:
                    pass

                return data_url, ""

            if last_status == "error":
                return "", f"La API local devolvió error: {last_error or job_data}"

        return "", f"Timeout esperando imagen local. Último estado: {last_status}. Último error: {last_error}"

    except Exception as error:
        return "", f"Error llamando API local de imágenes: {error}"


def generar_y_guardar_imagen_gemini_api(prompt, carpeta, nombre_archivo, aspect_ratio="1:1"):
    """
    Genera una imagen con Gemini Image y la guarda en media/rutas_generadas/.
    Devuelve una tupla: (image_url, image_error)
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return "", "Falta la variable GEMINI_API_KEY en Render."

    try:
        from google import genai
        from google.genai import types
    except Exception as error:
        return "", f"No se pudo importar google-genai: {error}"

    model_candidates = []
    env_model = os.getenv("GEMINI_IMAGE_MODEL", "").strip()
    if env_model:
        model_candidates.append(env_model)
    # Fallbacks seguros
    for candidate in ["gemini-3.1-flash-image", "gemini-2.5-flash-image", "gemini-3-pro-image"]:
        if candidate not in model_candidates:
            model_candidates.append(candidate)

    image_size = os.getenv("GEMINI_IMAGE_SIZE", "1K").strip() or "1K"
    last_error = ""

    try:
        client = genai.Client(api_key=api_key)
    except Exception as error:
        return "", f"No se pudo crear el cliente Gemini: {error}"

    ruta_relativa = f"rutas_generadas/{carpeta}/{limpiar_nombre_archivo(nombre_archivo)}"
    ruta_absoluta = Path(settings.MEDIA_ROOT) / ruta_relativa
    ruta_absoluta.parent.mkdir(parents=True, exist_ok=True)

    for model in model_candidates:
        try:
            config = types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                ),
            )
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )

            for part in obtener_partes_respuesta(response):
                if guardar_parte_imagen(part, ruta_absoluta):
                    return settings.MEDIA_URL + ruta_relativa.replace("\\", "/"), ""

            # Segundo intento simple, sin config, por compatibilidad SDK/modelo
            response = client.models.generate_content(
                model=model,
                contents=[prompt],
            )
            for part in obtener_partes_respuesta(response):
                if guardar_parte_imagen(part, ruta_absoluta):
                    return settings.MEDIA_URL + ruta_relativa.replace("\\", "/"), ""

            last_error = f"El modelo {model} respondió, pero no devolvió imagen utilizable."

        except Exception as error:
            last_error = f"{model}: {error}"
            print("Error generando imagen con Gemini:", last_error)
            continue

    return "", last_error or "No fue posible generar la imagen con Gemini."


def obtener_partes_respuesta(response):
    partes = []

    direct_parts = getattr(response, "parts", None)
    if direct_parts:
        partes.extend(direct_parts)

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        candidate_parts = getattr(content, "parts", None) if content else None
        if candidate_parts:
            partes.extend(candidate_parts)

    return partes


def guardar_parte_imagen(part, ruta_absoluta):
    """
    Soporta respuestas de imagen como:
    - part.as_image()
    - part.inline_data.data en base64
    - part.inline_data.data como bytes
    """
    try:
        if hasattr(part, "as_image"):
            image = part.as_image()
            if image:
                image.save(ruta_absoluta)
                return True
    except Exception:
        pass

    inline_data = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
    if not inline_data:
        return False

    data = getattr(inline_data, "data", None)
    if not data:
        return False

    try:
        if isinstance(data, bytes):
            ruta_absoluta.write_bytes(data)
        else:
            ruta_absoluta.write_bytes(base64.b64decode(data))
        return True
    except Exception as error:
        print("No se pudo guardar la imagen generada:", error)
        return False


def limpiar_nombre_archivo(nombre):
    nombre = str(nombre or "imagen.png").strip()
    nombre = re.sub(r"[^a-zA-Z0-9_.-]", "_", nombre)
    if not nombre.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        nombre += ".png"
    return nombre


def normalizar_mini_quiz(valor):
    if not isinstance(valor, list):
        return []

    preguntas_limpias = []
    for item in valor[:5]:
        if not isinstance(item, dict):
            continue

        opciones = normalizar_lista(item.get("opciones", []))[:4]
        if len(opciones) < 2:
            continue

        respuesta_correcta = str(item.get("respuesta_correcta", "")).strip()
        if respuesta_correcta not in opciones:
            respuesta_correcta = opciones[0]

        preguntas_limpias.append(
            {
                "pregunta": str(item.get("pregunta", "")).strip(),
                "opciones": opciones,
                "respuesta_correcta": respuesta_correcta,
                "explicacion": str(item.get("explicacion", "")).strip(),
            }
        )

    return preguntas_limpias


def normalizar_audio(valor):
    if not isinstance(valor, dict):
        valor = {}
    return {
        "habilitado": bool(valor.get("habilitado")),
        "titulo": str(valor.get("titulo", "Audio de estudio")).strip(),
        "guion": str(valor.get("guion", "")).strip(),
        "pasos_clave": normalizar_lista(valor.get("pasos_clave", [])),
    }



def normalizar_visual(valor):
    if not isinstance(valor, dict):
        valor = {}

    apoyo_visual = normalizar_lista(valor.get("apoyo_visual", []))
    ramas = []
    valor_ramas = valor.get("ramas", [])

    if isinstance(valor_ramas, list):
        for rama in valor_ramas[:4]:
            if not isinstance(rama, dict):
                continue

            titulo = str(rama.get("titulo", "")).strip()
            detalle = str(rama.get("detalle", "")).strip()
            subpuntos = normalizar_lista(rama.get("subpuntos", []))[:3]

            if titulo or detalle or subpuntos:
                ramas.append({
                    "titulo": titulo or "Idea clave",
                    "detalle": detalle,
                    "subpuntos": subpuntos,
                })

    if not ramas and apoyo_visual:
        for item in apoyo_visual[:4]:
            texto = str(item).strip()
            if not texto:
                continue

            if ":" in texto:
                titulo, detalle = texto.split(":", 1)
                titulo = titulo.strip()
                detalle = detalle.strip()
            else:
                titulo = texto
                detalle = "Concepto clave para conectar con el tema central."

            ramas.append({
                "titulo": titulo or "Idea clave",
                "detalle": detalle,
                "subpuntos": [],
            })

    return {
        "habilitado": bool(valor.get("habilitado")),
        "titulo": str(valor.get("titulo", "Mapa visual generado por IA")).strip(),
        "tipo": str(valor.get("tipo", "mapa_mental")).strip(),
        "descripcion": str(valor.get("descripcion", "")).strip(),
        "nodo_central": str(valor.get("nodo_central", "Tema central")).strip(),
        "ramas": ramas,
        "mermaid": str(valor.get("mermaid", "")).strip(),
        "apoyo_visual": apoyo_visual,
        "prompt_imagen": str(valor.get("prompt_imagen", "")).strip(),
        "negative_prompt": str(valor.get("negative_prompt", "")).strip(),
        "categoria_visual": str(valor.get("categoria_visual", "")).strip(),
        "image_url": str(valor.get("image_url", "")).strip(),
        "image_error": str(valor.get("image_error", "")).strip(),
    }


def normalizar_kinestesico(valor):
    if not isinstance(valor, dict):
        valor = {}
    return {
        "habilitado": bool(valor.get("habilitado")),
        "titulo": str(valor.get("titulo", "Ejercicio práctico")).strip(),
        "instrucciones": str(valor.get("instrucciones", "")).strip(),
        "preguntas": normalizar_lista(valor.get("preguntas", [])),
    }


def normalizar_lectura(valor):
    if not isinstance(valor, dict):
        valor = {}
    return {
        "habilitado": bool(valor.get("habilitado")),
        "titulo": str(valor.get("titulo", "Apoyo de lectura")).strip(),
        "resumen": str(valor.get("resumen", "")).strip(),
        "glosario": normalizar_lista(valor.get("glosario", [])),
    }




def normalizar_preguntas_guiadas(valor, preguntas_base=None, marcadores=None):
    """Convierte preguntas del LLM en tarjetas de práctica con pista y respuesta.
    Si el LLM no devuelve objetos, crea respuestas sugeridas usando los marcadores.
    """
    preguntas_base = preguntas_base or []
    marcadores = marcadores or []
    preguntas_guiadas = []

    if isinstance(valor, list):
        for idx, item in enumerate(valor, start=1):
            if isinstance(item, dict):
                pregunta = str(item.get("pregunta", "")).strip()
                pista = str(item.get("pista", "")).strip()
                respuesta = str(item.get("respuesta", item.get("respuesta_esperada", ""))).strip()
            else:
                pregunta = str(item).strip()
                pista = ""
                respuesta = ""

            if not pregunta:
                continue

            marcador = marcadores[(idx - 1) % len(marcadores)] if marcadores else {}
            if not pista:
                pista = marcador.get("pista") or "Observa la lámina y relaciona la pregunta con los marcadores numerados."
            if not respuesta:
                nombre = marcador.get("nombre") or "la estructura anatómica correspondiente"
                detalle = marcador.get("detalle") or "Relaciona su ubicación, función y estructuras vecinas."
                respuesta = f"Respuesta esperada: identificar {nombre}. {detalle}"

            preguntas_guiadas.append({
                "id": idx,
                "pregunta": pregunta,
                "pista": pista,
                "respuesta": respuesta,
            })

    if not preguntas_guiadas:
        for idx, pregunta in enumerate(preguntas_base[:4], start=1):
            marcador = marcadores[(idx - 1) % len(marcadores)] if marcadores else {}
            nombre = marcador.get("nombre") or "estructura clave"
            preguntas_guiadas.append({
                "id": idx,
                "pregunta": str(pregunta).strip(),
                "pista": marcador.get("pista") or "Usa la posición de los marcadores para orientar tu respuesta.",
                "respuesta": marcador.get("detalle") or f"Identifica {nombre} y explica su relación anatómica con el tema del día.",
            })

    return preguntas_guiadas[:5]

def normalizar_imagen_anatomica(valor):
    if not isinstance(valor, dict):
        valor = {}

    marcadores = valor.get("marcadores", [])
    marcadores_limpios = []

    if isinstance(marcadores, list):
        for idx, item in enumerate(marcadores, start=1):
            if not isinstance(item, dict):
                continue

            try:
                x = max(10, min(int(item.get("x") or 50), 90))
                y = max(10, min(int(item.get("y") or 50), 90))
            except (TypeError, ValueError):
                x = 50
                y = 50

            marcadores_limpios.append(
                {
                    "id": int(item.get("id") or idx),
                    "nombre": str(item.get("nombre", f"Estructura {idx}")).strip(),
                    "x": x,
                    "y": y,
                    "pista": str(item.get("pista", "")).strip(),
                    "detalle": str(item.get("detalle", "")).strip(),
                }
            )

    return {
        "habilitado": bool(valor.get("habilitado")),
        "titulo": str(valor.get("titulo", "Lámina anatómica generada por IA")).strip(),
        "tipo_vista": str(valor.get("tipo_vista", "superior")).strip(),
        "descripcion": str(valor.get("descripcion", "")).strip(),
        "marcadores": marcadores_limpios,
        "preguntas": normalizar_lista(valor.get("preguntas", [])),
        "preguntas_guiadas": normalizar_preguntas_guiadas(
            valor.get("preguntas_guiadas", valor.get("preguntas_detalladas", [])),
            preguntas_base=normalizar_lista(valor.get("preguntas", [])),
            marcadores=marcadores_limpios,
        ),
        "modo_practica": str(valor.get("modo_practica", "")).strip(),
        "prompt_imagen": str(valor.get("prompt_imagen", "")).strip(),
        "negative_prompt": str(valor.get("negative_prompt", "")).strip(),
        "categoria_visual": str(valor.get("categoria_visual", "")).strip(),
        "image_url": str(valor.get("image_url", "")).strip(),
        "image_error": str(valor.get("image_error", "")).strip(),
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
