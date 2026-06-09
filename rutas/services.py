import base64
import json
import os
import re
import time
import unicodedata
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
          "titulo": "Mapa mental limpio del día",
          "tipo": "mapa_mental_limpio",
          "descripcion": "Descripción breve del mapa mental",
          "nodo_central": "Concepto central del día",
          "ramas": [
            {{"titulo": "Rama 1", "detalle": "Idea principal", "subpuntos": ["Subpunto 1", "Subpunto 2"]}},
            {{"titulo": "Rama 2", "detalle": "Idea principal", "subpuntos": ["Subpunto 1", "Subpunto 2"]}},
            {{"titulo": "Rama 3", "detalle": "Idea principal", "subpuntos": ["Subpunto 1", "Subpunto 2"]}},
            {{"titulo": "Rama 4", "detalle": "Idea principal", "subpuntos": ["Subpunto 1", "Subpunto 2"]}}
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
          "titulo": "Lámina anatómica para modo práctica",
          "tipo_vista": "superior/anterior/lateral según corresponda",
          "descripcion": "Descripción breve de la lámina anatómica que debe observar el estudiante",
          "preguntas": ["¿Qué estructura principal observas?", "¿Qué relación anatómica debes identificar?"],
          "preguntas_guiadas": [
            {{"pregunta": "Pregunta de observación", "pista": "Pista breve", "respuesta": "Respuesta esperada breve"}},
            {{"pregunta": "Pregunta de relación", "pista": "Pista breve", "respuesta": "Respuesta esperada breve"}}
          ],
          "modo_practica": "Observa la imagen sin leer respuestas, responde las preguntas y luego revela pistas y respuestas."
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
- Si Visual > 0, genera visual.habilitado=true. Debe incluir nodo_central y 4 ramas con titulo, detalle y subpuntos. El mapa mental NO será imagen libre; será renderizado por el sistema en HTML/SVG para que el texto sea perfecto.
- Si Visual > 0 o Kinestésico > 0, genera imagen_anatomica.habilitado=true. Debe incluir descripcion, preguntas, preguntas_guiadas y modo_practica. No pongas texto dentro de la imagen; las preguntas, pistas, respuestas y etiquetas se muestran fuera o encima por el sistema.
- No dependas de Mermaid como recurso principal.
- No generes mapas mentales con imágenes de IA, porque el texto debe ser legible y académico.
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


def enriquecer_plan_con_imagenes_ia(respuesta, user, datos_academicos):
    """
    Versión 100/10:
    - El mapa mental NO se manda a ComfyUI. Se deja como estructura limpia para HTML/SVG.
    - La lámina anatómica y el modo práctica SÍ usan ComfyUI/local, con prompts controlados por tema.
    - Guarda historial técnico dentro del JSON del día para defensa del proyecto.
    """
    if not isinstance(respuesta, dict):
        return respuesta

    plan = respuesta.get("plan_diario", [])
    if not isinstance(plan, list):
        return respuesta

    generar_imagenes = os.getenv("GENERAR_IMAGENES_RUTA", "true").strip().lower() in ["1", "true", "yes", "si", "sí"]

    try:
        max_imagenes = int(os.getenv("MAX_IMAGENES_RUTA", "2"))
    except ValueError:
        max_imagenes = 2

    imagenes_generadas = 0

    for dia in plan:
        if not isinstance(dia, dict):
            continue

        recursos = dia.get("recursos", {})
        if not isinstance(recursos, dict):
            continue

        numero_dia = dia.get("dia") or 1
        tema = dia.get("tema_principal") or datos_academicos.tema_actual or "Anatomía I"
        tema_base = datos_academicos.tema_actual or tema
        punto_dificil = datos_academicos.temas_dificiles or ""
        categoria = detectar_categoria_tema(tema_base, punto_dificil)

        # MAPA MENTAL: estructura limpia, NO imagen IA.
        visual = recursos.get("visual", {})
        if isinstance(visual, dict) and visual.get("habilitado"):
            preparar_mapa_mental_limpio(visual, tema=tema, tema_base=tema_base, punto_dificil=punto_dificil)

        # LÁMINA / MODO PRÁCTICA: imagen IA local con prompt controlado por categoría.
        anatomica = recursos.get("imagen_anatomica", {})
        if isinstance(anatomica, dict) and anatomica.get("habilitado"):
            prompt, negative_prompt = construir_prompt_anatomia_controlado(
                tema=tema_base,
                subtema=tema,
                punto_dificil=punto_dificil,
                categoria=categoria,
                descripcion=anatomica.get("descripcion", ""),
            )

            anatomica["categoria_tema"] = categoria
            anatomica["prompt_imagen"] = prompt
            anatomica["negative_prompt"] = negative_prompt
            anatomica["marcadores"] = anatomica.get("marcadores") or construir_marcadores_categoria(categoria)
            anatomica["preguntas_guiadas"] = construir_preguntas_guiadas(
                categoria=categoria,
                tema=tema_base,
                punto_dificil=punto_dificil,
                preguntas_base=anatomica.get("preguntas", []),
            )
            anatomica["historial_generacion"] = anatomica.get("historial_generacion") or []

            if generar_imagenes and imagenes_generadas < max_imagenes and not anatomica.get("image_url"):
                image_url, image_error = generar_y_guardar_imagen_gemini(
                    prompt=prompt,
                    carpeta="laminas",
                    nombre_archivo=f"user_{user.id}_dia_{numero_dia}_{categoria}_lamina.png",
                    aspect_ratio="4:3",
                    negative_prompt=negative_prompt,
                )

                registro = {
                    "tipo": "lamina_anatomica_modo_practica",
                    "proveedor": os.getenv("IMAGE_PROVIDER", "gemini"),
                    "categoria": categoria,
                    "tema": tema_base,
                    "subtema": tema,
                    "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "resultado": "ok" if image_url else "error",
                    "detalle": image_error or "Imagen generada correctamente",
                }

                anatomica["historial_generacion"].append(registro)

                if image_url:
                    anatomica["image_url"] = image_url
                    anatomica["image_error"] = ""
                    imagenes_generadas += 1
                elif image_error:
                    anatomica["image_error"] = image_error

    return respuesta


def texto_normalizado(valor):
    valor = str(valor or "").strip().lower()
    valor = unicodedata.normalize("NFD", valor)
    valor = "".join(ch for ch in valor if unicodedata.category(ch) != "Mn")
    return valor


def detectar_categoria_tema(tema: str, punto_dificil: str = "") -> str:
    t = texto_normalizado(f"{tema} {punto_dificil}")

    if "linf" in t:
        return "linfatico"
    if "nervio" in t or "plexo" in t:
        return "nervioso"
    if "vaso" in t or "arteria" in t or "vena" in t or "corazon" in t:
        return "vascular"
    if "organo" in t or "viscera" in t or "abdomen" in t or "toracico" in t:
        return "visceral"
    if "musculo" in t or "diafragma" in t:
        return "muscular"
    if "articul" in t or "ligamento" in t:
        return "articular"
    if "perine" in t:
        return "perine"
    if "esqueleto" in t or "columna" in t or "torax" in t or "pelvis" in t or "ose" in t:
        return "oseo"
    return "general"


def preparar_mapa_mental_limpio(visual: dict, tema: str, tema_base: str, punto_dificil: str):
    visual["tipo"] = "mapa_mental_limpio"
    visual["image_url"] = ""
    visual["image_error"] = ""
    visual["prompt_imagen"] = ""
    visual["nodo_central"] = visual.get("nodo_central") or tema or tema_base or "Tema central"

    ramas = visual.get("ramas")
    if isinstance(ramas, list) and len(ramas) >= 3:
        return visual

    apoyo = normalizar_lista(visual.get("apoyo_visual", []))
    visual["ramas"] = construir_ramas_mapa_por_tema(tema_base or tema, punto_dificil, apoyo)
    return visual


def construir_ramas_mapa_por_tema(tema: str, punto_dificil: str = "", apoyo=None):
    categoria = detectar_categoria_tema(tema, punto_dificil)
    enfoque = punto_dificil or "relaciones anatómicas principales"

    plantillas = {
        "oseo": [
            ("Estructuras principales", f"Identifica los huesos o partes óseas centrales del tema: {tema}.", ["Ubicación", "Forma", "Relación con cavidades"]),
            ("Límites y referencias", f"Reconoce los límites anatómicos y puntos de referencia relacionados con {enfoque}.", ["Borde superior", "Borde inferior", "Relieves óseos"]),
            ("Relaciones", "Conecta cada estructura con órganos, músculos, vasos o nervios vecinos.", ["Anterior", "Posterior", "Lateral"]),
            ("Importancia clínica", "Comprende por qué esta zona es importante para exploración, postura o protección.", ["Protección", "Soporte", "Movimiento"]),
        ],
        "muscular": [
            ("Grupos musculares", f"Ordena los músculos principales relacionados con {tema}.", ["Plano superficial", "Plano profundo", "Dirección de fibras"]),
            ("Origen e inserción", f"Relaciona inserciones con el punto difícil: {enfoque}.", ["Origen", "Inserción", "Acción"]),
            ("Función", "Explica qué movimiento o estabilización produce cada grupo.", ["Movimiento", "Respiración", "Postura"]),
            ("Relaciones", "Ubica vasos, nervios y órganos cercanos.", ["Nervios", "Vasos", "Fascias"]),
        ],
        "visceral": [
            ("Órganos", f"Identifica órganos principales dentro de {tema}.", ["Anterior", "Medio", "Posterior"]),
            ("Relaciones espaciales", "Describe qué estructura está delante, detrás, arriba o abajo.", ["Anterior", "Posterior", "Superior"]),
            ("Irrigación e inervación", "Ubica de forma general vasos y nervios relevantes.", ["Arterias", "Venas", "Nervios"]),
            ("Modo práctica", "Observa la lámina y responde con relaciones, no solo nombres.", ["Identificar", "Comparar", "Explicar"]),
        ],
        "nervioso": [
            ("Trayecto", f"Sigue el recorrido de los nervios relacionados con {tema}.", ["Origen", "Ramas", "Destino"]),
            ("Relaciones", "Conecta nervios con músculos, vasos y órganos cercanos.", ["Músculos", "Vasos", "Órganos"]),
            ("Función", "Distingue sensibilidad, motricidad o función autónoma.", ["Sensitivo", "Motor", "Autónomo"]),
            ("Aplicación", "Usa casos de lesión o dolor referido para recordar.", ["Lesión", "Síntomas", "Exploración"]),
        ],
        "vascular": [
            ("Vasos principales", f"Identifica arterias, venas o vasos del tema: {tema}.", ["Origen", "Trayecto", "Ramas"]),
            ("Distribución", "Relaciona vasos con regiones u órganos irrigados.", ["Territorio", "Drenaje", "Anastomosis"]),
            ("Relaciones", "Ubica vasos respecto a huesos, músculos y órganos.", ["Anterior", "Posterior", "Medial"]),
            ("Importancia", "Conecta el contenido con pulsos, sangrado o drenaje.", ["Pulso", "Hemorragia", "Retorno"]),
        ],
    }

    base = plantillas.get(categoria) or [
        ("Concepto central", f"Comprende el tema principal: {tema}.", ["Definición", "Ubicación", "Función"]),
        ("Partes", "Divide el tema en estructuras o componentes principales.", ["Componente 1", "Componente 2", "Componente 3"]),
        ("Relaciones", "Conecta el tema con estructuras vecinas.", ["Anterior", "Posterior", "Lateral"]),
        ("Práctica", "Aplica el tema con preguntas y observación guiada.", ["Identificar", "Comparar", "Explicar"]),
    ]

    ramas = []
    for titulo, detalle, subpuntos in base[:4]:
        ramas.append({"titulo": titulo, "detalle": detalle, "subpuntos": subpuntos})

    if apoyo:
        for idx, item in enumerate(apoyo[:4]):
            if idx < len(ramas) and item:
                ramas[idx]["detalle"] = str(item)
    return ramas


def construir_prompt_anatomia_controlado(tema: str, subtema: str, punto_dificil: str, categoria: str, descripcion: str = ""):
    contexto = f"Main anatomy topic: {tema}. Daily focus: {subtema}. "
    if punto_dificil:
        contexto += f"Specific difficult point to emphasize: {punto_dificil}. "
    if descripcion:
        contexto += f"Teaching intent: {descripcion}. "

    negativo_base = (
        "text, labels, letters, words, watermark, logo, blurry, low quality, jpeg artifacts, "
        "bad anatomy, deformed structures, malformed proportions, extra limbs, full body poster, "
        "vintage document, old paper, infographic, unreadable writing, random typography"
    )

    if categoria == "oseo":
        positivo = (
            contexto +
            "Professional educational medical atlas illustration, isolated bony anatomical structure only, "
            "clean white background, realistic bone texture, centered composition, high detail, precise skeletal anatomy, "
            "no skin, no organs, no muscles, no text, no labels. "
            "If the topic involves pelvis, show the bony pelvis clearly in superior or frontal view, sacrum, coccyx, ilium, ischium and pubis visible."
        )
        negativo = negativo_base + ", skin, organs, muscles, torso, face, breasts, external body"
    elif categoria == "articular":
        positivo = (
            contexto +
            "Professional educational medical atlas illustration focused on joints and ligaments, close-up anatomical view, "
            "clear articulation surfaces, stabilizing ligaments visible, clean white background, high detail, no text, no labels."
        )
        negativo = negativo_base + ", full body, face, skin focus, unrelated organs"
    elif categoria == "muscular":
        positivo = (
            contexto +
            "Professional educational anatomy illustration focused on muscles, layered muscular anatomy, clear muscle groups, "
            "medical atlas style, clean neutral background, high detail, no text, no labels."
        )
        negativo = negativo_base + ", erotic, glamour, organs only, bones only, fashion pose"
    elif categoria == "visceral":
        positivo = (
            contexto +
            "Professional educational medical atlas illustration focused on internal organs, clean anatomical cutaway view, "
            "organs spatially organized inside the anatomical region, medical teaching style, high detail, no text, no labels. "
            "For pelvic organs, show a respectful non-sexual cutaway view with bladder, rectum and uterus/vagina if applicable, clearly organized."
        )
        negativo = negativo_base + ", explicit nudity, erotic, glamour, face, full body poster, unrelated limbs"
    elif categoria == "nervioso":
        positivo = (
            contexto +
            "Professional educational medical atlas illustration focused on nerves and nerve pathways, clear anatomical course, "
            "clean neutral background, teaching style, high detail, no text, no labels."
        )
        negativo = negativo_base + ", random colorful poster, organs emphasis only, full body glamour"
    elif categoria == "vascular":
        positivo = (
            contexto +
            "Professional educational medical atlas illustration focused on arteries and veins, clear vascular pathways, "
            "anatomical textbook style, clean background, high detail, no text, no labels."
        )
        negativo = negativo_base + ", nerves only, muscles only, infographic text, full body glamour"
    elif categoria == "linfatico":
        positivo = (
            contexto +
            "Professional educational medical atlas illustration focused on lymph nodes and lymphatic vessels, clear pathways, "
            "clean medical teaching style, high detail, no text, no labels."
        )
        negativo = negativo_base + ", random text blocks, poster, full body glamour"
    elif categoria == "perine":
        positivo = (
            contexto +
            "Professional educational anatomical atlas illustration of the perineal region, respectful non-sexual medical cutaway view, "
            "clear anatomical relationships, clean background, high detail, no text, no labels."
        )
        negativo = negativo_base + ", explicit sexualized content, erotic, glamour, pornography, face"
    else:
        positivo = (
            contexto +
            "Professional educational anatomical atlas illustration, clean composition, white background, high detail, no text, no labels."
        )
        negativo = negativo_base

    estilo = " modern high quality medical illustration, observation based practice image, large central focus, clean lighting"
    return positivo + estilo, negativo


def construir_marcadores_categoria(categoria: str):
    if categoria == "oseo":
        return [
            {"id": 1, "nombre": "Sacro", "x": 50, "y": 26, "pista": "Busca la estructura posterior central.", "detalle": "El sacro forma la pared posterior de la pelvis."},
            {"id": 2, "nombre": "Ilion", "x": 25, "y": 42, "pista": "Observa las alas óseas laterales.", "detalle": "El ilion forma la porción superior y lateral del hueso coxal."},
            {"id": 3, "nombre": "Pubis", "x": 50, "y": 72, "pista": "Busca la unión anterior inferior.", "detalle": "El pubis participa en la sínfisis púbica."},
            {"id": 4, "nombre": "Isquion", "x": 72, "y": 66, "pista": "Ubícalo en la región inferior posterior del coxal.", "detalle": "El isquion contribuye al borde inferior de la pelvis."},
        ]
    if categoria == "visceral":
        return [
            {"id": 1, "nombre": "Vejiga", "x": 50, "y": 45, "pista": "Suele ubicarse anterior en la pelvis menor.", "detalle": "La vejiga se relaciona con la pared anterior pélvica."},
            {"id": 2, "nombre": "Recto", "x": 50, "y": 67, "pista": "Busca la estructura más posterior del eje visceral.", "detalle": "El recto ocupa la región posterior de la pelvis menor."},
            {"id": 3, "nombre": "Útero/Vagina si aplica", "x": 50, "y": 56, "pista": "En anatomía femenina se interpone entre vejiga y recto.", "detalle": "El útero y la vagina se relacionan con vejiga por delante y recto por detrás."},
        ]
    return [
        {"id": 1, "nombre": "Estructura principal", "x": 50, "y": 40, "pista": "Identifica la estructura más destacada.", "detalle": "Estructura central del tema."},
        {"id": 2, "nombre": "Relación anatómica", "x": 35, "y": 60, "pista": "Observa qué tiene alrededor.", "detalle": "Relación espacial importante."},
        {"id": 3, "nombre": "Punto difícil", "x": 65, "y": 60, "pista": "Conecta con el subtema elegido.", "detalle": "Punto de refuerzo para el estudio."},
    ]


def construir_preguntas_guiadas(categoria: str, tema: str, punto_dificil: str, preguntas_base=None):
    enfoque = punto_dificil or tema
    if categoria == "oseo":
        preguntas = [
            {"pregunta": "¿Qué estructura ósea se ubica en la línea media posterior?", "pista": "Observa el marcador cercano al eje posterior.", "respuesta": "El sacro, acompañado inferiormente por el cóccix."},
            {"pregunta": "¿Qué huesos forman la porción lateral de la pelvis?", "pista": "Busca las alas amplias a ambos lados.", "respuesta": "Principalmente los huesos coxales, con ilion, isquion y pubis."},
            {"pregunta": f"¿Cómo se relaciona la imagen con {enfoque}?", "pista": "Piensa en límites, bordes y cavidad pélvica.", "respuesta": "Permite ubicar límites óseos y referencias anatómicas de la pelvis menor."},
        ]
    elif categoria == "visceral":
        preguntas = [
            {"pregunta": "¿Qué órgano suele ubicarse más anterior en la pelvis menor?", "pista": "Busca la estructura delante del eje visceral.", "respuesta": "La vejiga urinaria."},
            {"pregunta": "¿Qué estructura se ubica posterior respecto a la vejiga?", "pista": "Observa la relación hacia atrás.", "respuesta": "El recto; en anatomía femenina, útero/vagina se interponen entre vejiga y recto."},
            {"pregunta": f"¿Qué relación espacial debes explicar sobre {enfoque}?", "pista": "No memorices solo nombres; describe delante/detrás/arriba/abajo.", "respuesta": "Debes describir la disposición de los órganos y su relación con paredes pélvicas."},
        ]
    elif categoria == "muscular":
        preguntas = [
            {"pregunta": "¿Qué grupo muscular domina visualmente la lámina?", "pista": "Observa el conjunto más amplio o profundo.", "respuesta": "El grupo muscular principal del tema seleccionado."},
            {"pregunta": "¿Qué acción o estabilización produce este grupo?", "pista": "Relaciona dirección de fibras con movimiento.", "respuesta": "Depende del músculo, pero debe vincularse con movimiento, postura o soporte."},
            {"pregunta": f"¿Cómo conectarías la lámina con {enfoque}?", "pista": "Busca origen, inserción o relación funcional.", "respuesta": "Relacionando el músculo con sus inserciones y estructuras vecinas."},
        ]
    else:
        preguntas = [
            {"pregunta": "¿Cuál es la estructura principal que reconoces primero?", "pista": "Observa el centro de la imagen.", "respuesta": "La estructura dominante del tema del día."},
            {"pregunta": "¿Qué relaciones anatómicas puedes describir?", "pista": "Usa términos como anterior, posterior, superior, inferior, medial o lateral.", "respuesta": "Relaciones espaciales entre la estructura principal y sus vecinas."},
            {"pregunta": f"¿Qué parte se relaciona con {enfoque}?", "pista": "Conecta la imagen con el punto difícil elegido.", "respuesta": "El punto difícil debe ubicarse dentro del contexto visual del tema."},
        ]

    if preguntas_base:
        base = normalizar_lista(preguntas_base)
        for idx, pregunta in enumerate(base[:2]):
            if idx < len(preguntas):
                preguntas[idx]["pregunta"] = pregunta
    return preguntas


def construir_prompt_mapa_mental(tema, datos_academicos, visual):
    # Se mantiene por compatibilidad, pero ya no se usa para ComfyUI.
    return ""


def construir_prompt_lamina_anatomica(tema, datos_academicos, anatomica):
    categoria = detectar_categoria_tema(tema, datos_academicos.temas_dificiles or "")
    prompt, _ = construir_prompt_anatomia_controlado(
        tema=datos_academicos.tema_actual or tema,
        subtema=tema,
        punto_dificil=datos_academicos.temas_dificiles or "",
        categoria=categoria,
        descripcion=anatomica.get("descripcion", ""),
    )
    return prompt


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
    return generar_y_guardar_imagen_gemini_api(prompt, carpeta, nombre_archivo, aspect_ratio, negative_prompt=negative_prompt)


def generar_y_guardar_imagen_local(prompt, carpeta, nombre_archivo, aspect_ratio="1:1", negative_prompt=None):
    """
    Llama al servidor local de imágenes expuesto con Cloudflare Tunnel.
    """
    api_url = os.getenv("LOCAL_IMAGE_API_URL", "").strip().rstrip("/")
    job_base_url = os.getenv("LOCAL_IMAGE_JOB_BASE_URL", "").strip().rstrip("/")

    if not api_url:
        return "", "Falta LOCAL_IMAGE_API_URL en Render."
    if not job_base_url:
        job_base_url = api_url.replace("/generate-anatomy", "").rstrip("/")

    ruta_relativa = f"rutas_generadas/{carpeta}/{limpiar_nombre_archivo(nombre_archivo)}"
    ruta_absoluta = Path(settings.MEDIA_ROOT) / ruta_relativa
    ruta_absoluta.parent.mkdir(parents=True, exist_ok=True)

    if aspect_ratio in ["16:9", "4:3"]:
        width, height = 1024, 768
    else:
        width, height = 1024, 1024

    if not negative_prompt:
        negative_prompt = (
            "text, labels, letters, words, watermark, logo, blurry, low quality, "
            "distorted anatomy, deformed structures, extra bones, malformed anatomy, blood, gore, "
            "surgery, cartoon, messy composition, bad proportions"
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

                image_url = download_url if download_url.startswith("http") else f"{job_base_url}{download_url}"
                image_response = requests.get(image_url, timeout=90)
                image_response.raise_for_status()
                ruta_absoluta.write_bytes(image_response.content)

                return settings.MEDIA_URL + ruta_relativa.replace("\\", "/"), ""

            if last_status == "error":
                return "", f"La API local devolvió error: {last_error or job_data}"

        return "", f"Timeout esperando imagen local. Último estado: {last_status}. Último error: {last_error}"

    except Exception as error:
        return "", f"Error llamando API local de imágenes: {error}"


def generar_y_guardar_imagen_gemini_api(prompt, carpeta, nombre_archivo, aspect_ratio="1:1", negative_prompt=None):
    """
    Respaldo con Gemini Image. En tu demo normalmente no se usa porque IMAGE_PROVIDER=local.
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
    for candidate in ["gemini-3.1-flash-image", "gemini-2.5-flash-image"]:
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

    if negative_prompt:
        prompt = f"{prompt}\n\nNegative prompt: {negative_prompt}"

    for model in model_candidates:
        try:
            config = types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(aspect_ratio=aspect_ratio, image_size=image_size),
            )
            response = client.models.generate_content(model=model, contents=prompt, config=config)
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
        "preguntas_guiadas": normalizar_preguntas_guiadas(valor.get("preguntas_guiadas", [])),
        "modo_practica": str(valor.get("modo_practica", "")).strip(),
        "categoria_tema": str(valor.get("categoria_tema", "")).strip(),
        "prompt_imagen": str(valor.get("prompt_imagen", "")).strip(),
        "negative_prompt": str(valor.get("negative_prompt", "")).strip(),
        "image_url": str(valor.get("image_url", "")).strip(),
        "image_error": str(valor.get("image_error", "")).strip(),
        "historial_generacion": normalizar_historial_imagenes(valor.get("historial_generacion", [])),
    }


def normalizar_preguntas_guiadas(valor):
    if not isinstance(valor, list):
        return []
    limpias = []
    for item in valor[:5]:
        if isinstance(item, dict):
            pregunta = str(item.get("pregunta", "")).strip()
            pista = str(item.get("pista", "")).strip()
            respuesta = str(item.get("respuesta", "")).strip()
        else:
            pregunta = str(item).strip()
            pista = "Observa la imagen y relaciona la estructura con el tema del día."
            respuesta = "Respuesta esperada según el contenido del día."
        if pregunta:
            limpias.append({"pregunta": pregunta, "pista": pista, "respuesta": respuesta})
    return limpias


def normalizar_historial_imagenes(valor):
    if not isinstance(valor, list):
        return []
    historial = []
    for item in valor[-8:]:
        if not isinstance(item, dict):
            continue
        historial.append({
            "tipo": str(item.get("tipo", "")).strip(),
            "proveedor": str(item.get("proveedor", "")).strip(),
            "categoria": str(item.get("categoria", "")).strip(),
            "tema": str(item.get("tema", "")).strip(),
            "subtema": str(item.get("subtema", "")).strip(),
            "fecha": str(item.get("fecha", "")).strip(),
            "resultado": str(item.get("resultado", "")).strip(),
            "detalle": str(item.get("detalle", "")).strip(),
        })
    return historial


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
