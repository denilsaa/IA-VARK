import base64
import json
import os
import re
import time
from pathlib import Path

import requests

from django.conf import settings
from django.utils import timezone
from django.utils.text import Truncator

from .models import RutaAprendizaje
from anatomia.models import TemaAnatomia


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



def obtener_subtemas_dataset_ruta(tema_actual):
    """Obtiene los subtemas reales del tema elegido en el formulario.

    La ruta no debe repetir el tema principal todos los días. Si el estudiante
    elige, por ejemplo, "Corazón y vasos del tronco", los días deben avanzar por
    sus puntos específicos: desarrollo del corazón, cavidades, aurículas,
    ventrículos, válvulas, pericardio, aorta, venas, circulación, etc.
    """
    tema_actual = str(tema_actual or "").strip()
    if not tema_actual:
        return []

    subtemas = []
    try:
        tema = TemaAnatomia.objects.filter(
            nombre=tema_actual,
            tema_padre__isnull=True,
            activo=True,
        ).first()
        if tema:
            subtemas = list(
                TemaAnatomia.objects.filter(
                    tema_padre=tema,
                    activo=True,
                ).order_by("orden", "nombre").values_list("nombre", flat=True)
            )
    except Exception:
        subtemas = []

    # Respaldo por si la base todavía no fue poblada o se ejecuta fuera de Django.
    if not subtemas:
        try:
            from anatomia.dataset_anatomia import ANATOMIA_I_DATASET
            for item in ANATOMIA_I_DATASET:
                if item.get("nombre") == tema_actual:
                    subtemas = list(item.get("subtemas") or [])
                    break
        except Exception:
            subtemas = []

    return [str(nombre).strip() for nombre in subtemas if str(nombre).strip()]


def ordenar_subtemas_por_prioridad(subtemas, punto_dificil=""):
    """Prioriza el punto difícil sin perder el resto del temario."""
    subtemas = [str(s or "").strip() for s in subtemas if str(s or "").strip()]
    punto = str(punto_dificil or "").strip()
    if punto and punto in subtemas:
        return [punto] + [s for s in subtemas if s != punto]
    return subtemas


def _limpiar_titulo_agenda(texto):
    texto = re.sub(r"\s+", " ", str(texto or "").strip())
    texto = re.sub(r"^D[ií]a\s*\d+\s*:\s*", "", texto, flags=re.IGNORECASE)
    return texto[:120]


def construir_agenda_dias(datos_academicos, dias_planificados):
    """Construye la secuencia obligatoria 1-21 usando subtemas del dataset.

    Esta agenda es la fuente de verdad. Gemini puede redactar recursos, pero no
    decidir que todos los días sean el mismo tema. Cuando hay más días que
    subtemas, se agregan días de integración, comparación y práctica de examen
    sin repetir exactamente el mismo título.
    """
    tema_actual = str(getattr(datos_academicos, "tema_actual", "") or "Anatomía I").strip()
    punto_dificil = str(getattr(datos_academicos, "temas_dificiles", "") or "").strip()
    subtemas = obtener_subtemas_dataset_ruta(tema_actual)
    base = ordenar_subtemas_por_prioridad(subtemas, punto_dificil)

    if not base:
        base = [punto_dificil or tema_actual]

    agenda = []
    usados = set()

    def agregar(nombre, tipo="subtema", foco=""):
        nombre = _limpiar_titulo_agenda(nombre)
        if not nombre:
            return
        clave = nombre.lower()
        if clave in usados:
            return
        usados.add(clave)
        agenda.append(
            {
                "tema": nombre,
                "tema_padre": tema_actual,
                "tipo": tipo,
                "punto_refuerzo": foco or punto_dificil or nombre,
                "objetivo": f"Aprender {nombre} dentro de {tema_actual}, ubicando definición, relaciones e importancia para el examen.",
            }
        )

    # Primero se recorren subtemas reales del dataset.
    for subtema in base:
        agregar(subtema, tipo="subtema", foco=punto_dificil or subtema)
        if len(agenda) >= dias_planificados:
            break

    # Si el plan tiene más días que subtemas, se completan con días distintos.
    modos = [
        "Integración anatómica",
        "Relaciones y límites",
        "Cuadro comparativo",
        "Preguntas tipo examen",
        "Repaso activo",
        "Caso aplicado",
        "Mapa escrito final",
    ]
    cursor = 0
    while len(agenda) < dias_planificados:
        a = base[cursor % len(base)]
        b = base[(cursor + 1) % len(base)] if len(base) > 1 else tema_actual
        modo = modos[cursor % len(modos)]
        if modo in ["Integración anatómica", "Cuadro comparativo"] and a != b:
            nombre = f"{modo}: {a} y {b}"
        elif modo == "Mapa escrito final":
            nombre = f"{modo}: {tema_actual}"
        else:
            nombre = f"{modo}: {a}"
        agregar(nombre, tipo="integracion", foco=a)
        cursor += 1
        # Protección extra contra bucles si la lista es muy corta.
        if cursor > 200:
            agregar(f"Repaso final personalizado {len(agenda) + 1}: {tema_actual}", tipo="integracion", foco=punto_dificil or tema_actual)

    for index, item in enumerate(agenda[:dias_planificados], start=1):
        item["dia"] = index
        item["titulo"] = f"Día {index}: {item['tema']}"

    return agenda[:dias_planificados]


def formatear_agenda_para_prompt(agenda_dias):
    lineas = []
    for item in agenda_dias:
        lineas.append(
            f"Día {item['dia']}: tema_principal='{item['tema']}' | tema_padre='{item['tema_padre']}' | tipo='{item['tipo']}' | foco='{item['punto_refuerzo']}'"
        )
    return "\n".join(lineas)

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
        agenda_dias = construir_agenda_dias(datos_academicos, dias_planificados)
        agenda_texto = formatear_agenda_para_prompt(agenda_dias)

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
- Si Lectura/Escritura tiene puntaje positivo, no hagas solo un resumen. Debe convertirse en un recurso útil de estudio escrito: lectura guiada, cuadro de estudio, glosario, fichas de memoria y actividad de escritura activa.
- El bloque Lectura/Escritura debe ayudar al estudiante a leer, subrayar, ordenar, escribir y autoevaluarse; debe parecer una guía de cuaderno de estudio, no un párrafo decorativo.
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

AGENDA OBLIGATORIA DE LA RUTA, TOMADA DEL DATASET INTERNO:
{agenda_texto}

REGLAS DE VARIACIÓN DIARIA:
- Usa exactamente esta agenda para plan_diario. No cambies el orden.
- Cada día debe tener un tema_principal diferente según la agenda.
- No repitas "{datos_academicos.tema_actual}" como tema_principal de todos los días; ese es el tema padre, no el tema de cada día.
- El punto específico difícil se prioriza, pero no debe bloquear el avance por los demás subtemas.
- Si hay 1 día, enfoca el punto más importante. Si hay 2 a 21 días, reparte los subtemas y días de integración según la agenda.
- En Lectura/Escritura, escribe contenido anatómico del tema_principal de ese día, no instrucciones genéricas.

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
          "titulo": "Guía de lectura y escritura desarrollada",
          "resumen": "Resumen académico desarrollado de 120 a 180 palabras sobre el tema del día. Debe explicar definición, ubicación, relaciones anatómicas e importancia para el examen.",
          "lectura_profunda": [
            {{"subtitulo": "1. Concepto central", "contenido": "Párrafo completo de 4 a 6 líneas que explique qué es el tema, para qué sirve y por qué debe estudiarse."}},
            {{"subtitulo": "2. Ubicación anatómica", "contenido": "Párrafo completo de 4 a 6 líneas que explique dónde se localiza y con qué regiones o estructuras se relaciona."}},
            {{"subtitulo": "3. Relaciones e importancia", "contenido": "Párrafo completo de 4 a 6 líneas que explique relaciones anatómicas, función e importancia clínica o funcional general."}}
          ],
          "conceptos_clave": [
            {{"termino": "Término anatómico", "explicacion": "Definición clara en 1 o 2 oraciones", "como_usarlo": "Cómo usar este término en una respuesta de examen"}}
          ],
          "esquema_escrito": [
            {{"seccion": "Definición", "desarrollo": "Contenido ya redactado para que el estudiante lo copie o adapte."}},
            {{"seccion": "Ubicación", "desarrollo": "Contenido ya redactado con ubicación anatómica."}},
            {{"seccion": "Relaciones", "desarrollo": "Contenido ya redactado con estructuras relacionadas."}},
            {{"seccion": "Importancia", "desarrollo": "Contenido ya redactado con función o utilidad."}}
          ],
          "cuadro_cornell": [
            {{"pregunta_guia": "Pregunta de estudio", "apuntes": "Apunte desarrollado que responde la pregunta", "clave_memoria": "Palabra o frase para recordar"}}
          ],
          "glosario_detallado": [
            {{"termino": "Término", "definicion": "Definición breve", "relacion": "Relación con el tema principal"}}
          ],
          "fichas_memoria": [
            {{"anverso": "Pregunta corta para recordar", "reverso": "Respuesta breve pero completa"}}
          ],
          "pregunta_tipo_examen": "Pregunta escrita tipo examen sobre el tema del día",
          "respuesta_corta": "Respuesta breve de 3 a 4 líneas para memorizar lo esencial.",
          "respuesta_modelo": "Respuesta tipo examen de 8 a 12 líneas, redactada en estilo académico, sobre el tema y el punto difícil.",
          "puntos_memorizacion": ["Idea mínima 1", "Idea mínima 2", "Idea mínima 3", "Idea mínima 4"],
          "actividad_escritura": {{
            "titulo": "Producción escrita del día",
            "consigna": "Consigna clara de escritura activa",
            "instrucciones": "Qué debe escribir el estudiante en su cuaderno",
            "plantilla": ["Definición:", "Ubicación anatómica:", "Relaciones:", "Importancia funcional o clínica:", "Cierre personal:"],
            "ejemplo_respuesta": "Ejemplo desarrollado de cómo debería empezar la respuesta"
          }},
          "errores_comunes": [
            {{"error": "Error frecuente al estudiar el tema", "correccion": "Cómo corregirlo en una respuesta escrita"}}
          ],
          "preguntas_autoverificacion": ["Pregunta escrita 1", "Pregunta escrita 2", "Pregunta escrita 3"],
          "producto_esperado": "Producto concreto: apunte desarrollado, cuadro Cornell, glosario y respuesta tipo examen"
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
- El elemento 1 de plan_diario debe corresponder al Día 1 de la agenda, el elemento 2 al Día 2, y así sucesivamente.
- Enfoca cada día en su subtema de agenda y usa el tema actual solo como tema padre.
- No entregues los mismos títulos, objetivos, resúmenes ni respuestas modelo para todos los días.
- Si Auditivo > 0, genera audio.habilitado=true.
- Si Visual > 0, genera visual.habilitado=true. Debe incluir nodo_central y exactamente 4 ramas. Cada rama debe tener titulo, detalle y 2 o 3 subpuntos. NO generes imagen para el mapa mental; el sistema lo dibujará como HTML/SVG limpio.
- Si Visual > 0 o Kinestésico > 0, genera imagen_anatomica.habilitado=true. Debe incluir descripcion, preguntas, modo_practica y, si es posible, marcadores sugeridos con nombre, pista y detalle. El sistema construirá un prompt visual controlado por tema.
- No uses Mermaid como recurso principal.
- No uses texto dentro de imágenes generadas. El sistema añadirá textos, preguntas y marcadores fuera o encima de la imagen.
- Si Kinestésico > 0, genera kinestesico.habilitado=true.
- Si Lectura/Escritura > 0, genera lectura.habilitado=true; si es 0, puede quedar false.
- Cuando lectura.habilitado=true, NO entregues solo instrucciones; genera contenido académico ya redactado para leer y copiar.
- lectura.resumen debe tener 120 a 180 palabras.
- lectura.lectura_profunda debe tener 3 o 4 bloques con subtitulo y contenido desarrollado; cada contenido debe tener 4 a 6 líneas.
- lectura.conceptos_clave debe tener 4 a 6 términos con explicación y cómo usarlo en examen.
- lectura.esquema_escrito debe tener definición, ubicación, relaciones e importancia ya redactadas.
- lectura.cuadro_cornell debe tener 3 a 5 filas con pregunta_guia, apuntes y clave_memoria.
- lectura.glosario_detallado debe tener 4 a 6 términos con definición y relación.
- lectura.pregunta_tipo_examen debe plantear una pregunta abierta clara sobre el tema.
- lectura.respuesta_corta debe resumir en 3 o 4 líneas lo mínimo que el estudiante debe memorizar.
- lectura.respuesta_modelo debe ser una respuesta tipo examen de 8 a 12 líneas, no una frase genérica.
- lectura.puntos_memorizacion debe tener 4 ideas concretas del tema, no etiquetas generales.
- lectura.errores_comunes debe tener 3 errores frecuentes y su corrección.
- Evita frases vacías como "resume el tema" o "lee el tema". Entrega contenido útil, escrito y listo para estudiar.
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
        return validar_respuesta_ruta(data, dias_planificados, datos_academicos.minutos_por_dia, datos_academicos)

    except Exception as error:
        print("Error generando ruta con Gemini:", error)
        return {}




def es_etiqueta_generica_estudio(texto: str) -> bool:
    """Detecta textos que NO deben usarse como tema principal.

    Gemini a veces devuelve etiquetas como "Repaso guiado", "Autoevaluación" o
    "Contenido central" en lugar del tema elegido por el estudiante. Esas frases
    sirven como títulos internos, pero destruyen la modalidad Lectura/Escritura
    porque generan apuntes vacíos. Esta función las bloquea.
    """
    t = re.sub(r"\s+", " ", str(texto or "").strip().lower())
    if not t:
        return True
    genericos = [
        "repaso guiado",
        "autoevaluación",
        "autoevaluacion",
        "contenido central",
        "tema principal",
        "lectura guiada",
        "lectura desarrollada",
        "guía de estudio",
        "guia de estudio",
        "definición",
        "definicion",
        "ubicación anatómica",
        "ubicacion anatomica",
        "relaciones anatómicas",
        "relaciones anatomicas",
        "respuesta tipo examen",
        "producción escrita",
        "produccion escrita",
        "práctica escrita",
        "practica escrita",
    ]
    return t in genericos or any(t.startswith(g + ":") for g in genericos)


def obtener_tema_canonico_estudio(tema_seleccionado="", tema_llm="", titulo_llm="", punto_dificil="") -> str:
    """Devuelve el tema real que debe guiar la ruta y la lectura.

    Prioridad:
    1. Tema elegido en el formulario académico.
    2. Tema devuelto por Gemini, solo si no es etiqueta genérica.
    3. Título del día limpio.
    4. Punto difícil seleccionado.
    """
    candidatos = [tema_seleccionado, tema_llm]

    # Si el título viene como "Día 1: Corazón y vasos del tronco", extraemos la parte útil.
    titulo = str(titulo_llm or "").strip()
    if ":" in titulo:
        candidatos.append(titulo.split(":", 1)[1].strip())
    candidatos.append(titulo)
    candidatos.append(punto_dificil)

    for candidato in candidatos:
        c = re.sub(r"^D[ií]a\s*\d+\s*:\s*", "", str(candidato or "").strip(), flags=re.IGNORECASE)
        if c and not es_etiqueta_generica_estudio(c):
            return c
    return "Anatomía I"

def validar_respuesta_ruta(data, dias_planificados, minutos_maximos, datos_academicos=None):
    if not isinstance(data, dict):
        return {}

    plan_diario = data.get("plan_diario", [])
    if not isinstance(plan_diario, list):
        plan_diario = []

    agenda_dias = construir_agenda_dias(datos_academicos, dias_planificados) if datos_academicos is not None else []

    plan_limpio = []
    for index, dia in enumerate(plan_diario[:dias_planificados], start=1):
        if not isinstance(dia, dict):
            continue

        minutos = int(dia.get("minutos") or minutos_maximos)
        minutos = max(5, min(minutos, minutos_maximos))
        recursos = dia.get("recursos") if isinstance(dia.get("recursos"), dict) else {}

        tema_seleccionado = str(getattr(datos_academicos, "tema_actual", "") or "").strip()
        punto_dificil = str(getattr(datos_academicos, "temas_dificiles", "") or "").strip()
        agenda = agenda_dias[index - 1] if index - 1 < len(agenda_dias) else {}

        if agenda:
            tema_dia = agenda.get("tema") or tema_seleccionado or "Anatomía I"
            tema_padre = agenda.get("tema_padre") or tema_seleccionado or tema_dia
            punto_refuerzo = agenda.get("punto_refuerzo") or punto_dificil or tema_dia
            titulo_dia = agenda.get("titulo") or f"Día {index}: {tema_dia}"
            tipo_dia = agenda.get("tipo") or "subtema"
            objetivo_base = agenda.get("objetivo") or f"Aprender {tema_dia} dentro de {tema_padre}."
        else:
            tema_llm = str(dia.get("tema_principal", "") or "").strip()
            titulo_llm = str(dia.get("titulo", "") or "").strip()
            tema_dia = obtener_tema_canonico_estudio(
                tema_seleccionado="",
                tema_llm=tema_llm,
                titulo_llm=titulo_llm,
                punto_dificil=punto_dificil or tema_seleccionado,
            )
            tema_padre = tema_seleccionado or tema_dia
            punto_refuerzo = punto_dificil or tema_dia
            titulo_dia = str(dia.get("titulo", f"Día {index}: {tema_dia}")).strip()
            tipo_dia = "subtema"
            objetivo_base = f"Aprender {tema_dia} dentro de {tema_padre}."

        objetivo_llm = str(dia.get("objetivo", "") or "").strip()
        objetivo = objetivo_llm if objetivo_llm and tema_dia.lower() in objetivo_llm.lower() else objetivo_base

        plan_limpio.append(
            {
                "dia": index,
                "titulo": titulo_dia,
                "tema_principal": tema_dia,
                "tema_padre": tema_padre,
                "subtema_dia": tema_dia,
                "tipo_dia": tipo_dia,
                "punto_refuerzo": punto_refuerzo,
                "objetivo": objetivo,
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
                    "lectura": normalizar_lectura(recursos.get("lectura", {}), tema=tema_dia, punto_dificil=punto_refuerzo),
                    "imagen_anatomica": normalizar_imagen_anatomica(recursos.get("imagen_anatomica", {})),
                },
            }
        )

    # Si Gemini devolvió menos días, completamos con respaldo usando la misma agenda.
    if len(plan_limpio) < dias_planificados and datos_academicos is not None:
        respaldo = generar_ruta_respaldo(
            perfil_vark=type("PerfilTemporal", (), {
                "puntaje_visual": 1,
                "puntaje_auditivo": 1,
                "puntaje_lectura": 1,
                "puntaje_kinestesico": 1,
                "estilo_display": "VARK",
            })(),
            perfil_vark_detalle={"mezcla": "VARK"},
            datos_academicos=datos_academicos,
            dias_hasta_examen=dias_planificados,
            dias_planificados=dias_planificados,
        ).get("plan_diario", [])
        for dia in respaldo[len(plan_limpio):dias_planificados]:
            plan_limpio.append(dia)

    if not plan_limpio:
        return {}

    temas_priorizados = [item.get("tema") for item in agenda_dias[:min(8, len(agenda_dias))] if item.get("tema")]
    if not temas_priorizados:
        temas_priorizados = normalizar_lista(data.get("temas_priorizados", []))

    return {
        "titulo": str(data.get("titulo", "Ruta de aprendizaje personalizada por subtemas")).strip(),
        "resumen_general": str(data.get("resumen_general", "")).strip(),
        "temas_priorizados": temas_priorizados,
        "plan_diario": plan_limpio[:dias_planificados],
        "recomendaciones_finales": normalizar_lista(data.get("recomendaciones_finales", [])),
    }

def generar_ruta_respaldo(
    perfil_vark,
    perfil_vark_detalle,
    datos_academicos,
    dias_hasta_examen,
    dias_planificados,
):
    """Ruta local de respaldo basada en subtemas reales del dataset.

    Antes el respaldo alternaba entre tema_actual, temas_dificiles, "Repaso guiado"
    y "Refuerzo final". Eso hacía que la ruta se repitiera y que Lectura/Escritura
    sonara como instrucciones. Ahora cada día sale de la agenda de subtemas 1-21.
    """
    agenda_dias = construir_agenda_dias(datos_academicos, dias_planificados)
    tema_padre = str(getattr(datos_academicos, "tema_actual", "") or "Anatomía I").strip()
    mezcla = perfil_vark_detalle.get("mezcla", "VARK") if isinstance(perfil_vark_detalle, dict) else "VARK"

    tiene_visual = getattr(perfil_vark, "puntaje_visual", 0) > 0
    tiene_audio = getattr(perfil_vark, "puntaje_auditivo", 0) > 0
    tiene_lectura = getattr(perfil_vark, "puntaje_lectura", 0) > 0
    tiene_kin = getattr(perfil_vark, "puntaje_kinestesico", 0) > 0

    plan = []
    for item in agenda_dias:
        dia = item["dia"]
        tema = item["tema"]
        punto = item.get("punto_refuerzo") or tema
        tipo_dia = item.get("tipo", "subtema")
        audio_habilitado = tiene_audio
        visual_habilitado = tiene_visual
        kin_habilitado = tiene_kin
        lectura_habilitada = tiene_lectura
        imagen_habilitada = tiene_visual or tiene_kin

        lectura_real = construir_lectura_escritura_real(tema, punto)
        lectura_real["habilitado"] = lectura_habilitada
        lectura_real["titulo"] = f"Guía desarrollada de lectura y escritura: {tema}"

        marcadores = [
            {
                "id": 1,
                "nombre": tema,
                "x": 50,
                "y": 30,
                "pista": "Ubica el subtema central del día.",
                "detalle": f"Reconoce {tema} dentro de {tema_padre}.",
            },
            {
                "id": 2,
                "nombre": tema_padre,
                "x": 34,
                "y": 58,
                "pista": "Relaciona el subtema con el tema padre.",
                "detalle": f"El tema padre organiza el estudio de {tema}.",
            },
            {
                "id": 3,
                "nombre": punto,
                "x": 66,
                "y": 58,
                "pista": "Punto que debes reforzar al escribir o explicar.",
                "detalle": "Debe aparecer en tu respuesta tipo examen.",
            },
        ]

        plan.append(
            {
                "dia": dia,
                "titulo": item.get("titulo") or f"Día {dia}: {tema}",
                "tema_principal": tema,
                "tema_padre": tema_padre,
                "subtema_dia": tema,
                "tipo_dia": tipo_dia,
                "punto_refuerzo": punto,
                "objetivo": item.get("objetivo") or f"Aprender {tema} dentro de {tema_padre}.",
                "minutos": datos_academicos.minutos_por_dia,
                "enfoque_vark": f"Se adapta a {getattr(perfil_vark, 'estilo_display', 'VARK')} con distribución {mezcla}.",
                "recurso_vark": "Ruta diaria con subtema específico, lectura real, mapa, audio, práctica y mini quiz.",
                "uso_materiales": "Dataset interno de Anatomía I; los materiales subidos enriquecen el contenido cuando existen.",
                "actividades": [
                    f"Lee el bloque desarrollado de {tema} y subraya definición, ubicación y relaciones.",
                    f"Construye un mapa de cuatro ramas conectando {tema} con {tema_padre}.",
                    "Responde primero sin mirar la respuesta modelo y luego corrige tus errores.",
                    f"Cierra el día explicando en voz alta por qué {tema} es importante para el examen.",
                ],
                "autoevaluacion": [
                    f"¿Puedo definir {tema} sin copiar?",
                    f"¿Puedo ubicar {tema} dentro de {tema_padre}?",
                    "¿Mi respuesta menciona relaciones anatómicas y no solo nombres?",
                ],
                "producto_esperado": f"Apunte de una página sobre {tema}: definición, ubicación, relaciones, glosario y respuesta tipo examen.",
                "mini_quiz": [
                    {
                        "pregunta": f"¿Cuál es el subtema específico del día {dia}?",
                        "opciones": [tema, tema_padre, "Repaso guiado", "Refuerzo final"],
                        "respuesta_correcta": tema,
                        "explicacion": f"El día {dia} se centra específicamente en {tema}; {tema_padre} funciona como tema padre.",
                    },
                    {
                        "pregunta": "¿Qué debe incluir una respuesta escrita completa?",
                        "opciones": [
                            "Definición, ubicación, relaciones e importancia",
                            "Solo una lista de nombres",
                            "Únicamente una imagen",
                            "Solo el título del tema",
                        ],
                        "respuesta_correcta": "Definición, ubicación, relaciones e importancia",
                        "explicacion": "Esa estructura demuestra comprensión anatómica y sirve para preguntas abiertas.",
                    },
                    {
                        "pregunta": f"¿Cómo se debe estudiar {tema} dentro de la ruta?",
                        "opciones": [
                            "Como subtema del día conectado con el tema padre",
                            "Como tema repetido igual todos los días",
                            "Como contenido sin relación anatómica",
                            "Como actividad sin evaluación",
                        ],
                        "respuesta_correcta": "Como subtema del día conectado con el tema padre",
                        "explicacion": "La ruta avanza por subtemas reales y cada día conecta el punto específico con el tema principal.",
                    },
                ],
                "recursos": {
                    "audio": {
                        "habilitado": audio_habilitado,
                        "titulo": f"Audio del día: {tema}",
                        "guion": (
                            f"Hoy no vas a estudiar todo {tema_padre} de golpe. El foco es {tema}. "
                            f"Primero di con tus palabras qué es. Después ubícalo dentro de {tema_padre}. "
                            "Luego menciona una relación anatómica importante y termina explicando por qué sirve para el examen. "
                            "La meta es que puedas decirlo sin leer, como si se lo explicaras a un compañero."
                        ),
                        "pasos_clave": [
                            f"Definir {tema}.",
                            f"Ubicarlo dentro de {tema_padre}.",
                            "Relacionarlo con una estructura, función o límite.",
                        ],
                    },
                    "visual": {
                        "habilitado": visual_habilitado,
                        "titulo": f"Mapa mental de {tema}",
                        "tipo": "mapa_mental_html",
                        "descripcion": f"Mapa para separar {tema} del tema padre y estudiar sus relaciones.",
                        "nodo_central": tema,
                        "ramas": [
                            {"titulo": "Definición", "detalle": f"Qué es {tema}.", "subpuntos": ["Concepto", "Función o papel"]},
                            {"titulo": "Ubicación", "detalle": f"Dónde se reconoce dentro de {tema_padre}.", "subpuntos": ["Región", "Referencia espacial"]},
                            {"titulo": "Relaciones", "detalle": "Conexiones anatómicas principales.", "subpuntos": ["Estructuras vecinas", "Continuidad o límites"]},
                            {"titulo": "Examen", "detalle": "Cómo convertirlo en respuesta escrita.", "subpuntos": ["Pregunta abierta", "Respuesta modelo"]},
                        ],
                        "apoyo_visual": [f"Nodo central: {tema}", f"Tema padre: {tema_padre}", "Relaciones anatómicas", "Respuesta tipo examen"],
                    },
                    "kinestesico": {
                        "habilitado": kin_habilitado,
                        "titulo": f"Práctica activa sobre {tema}",
                        "instrucciones": (
                            f"En una hoja, dibuja un esquema simple de {tema}. Marca dónde se ubica, escribe dos relaciones y tapa la respuesta modelo antes de contestar."
                        ),
                        "preguntas": [
                            f"¿Qué parte de {tema} identificarías primero?",
                            f"¿Con qué estructura o función se relaciona {tema}?",
                            "¿Qué error corregiste al comparar con la respuesta modelo?",
                        ],
                    },
                    "lectura": lectura_real,
                    "imagen_anatomica": {
                        "habilitado": imagen_habilitada,
                        "titulo": f"Lámina anatómica guiada de {tema}",
                        "tipo_vista": "vista anatómica didáctica",
                        "descripcion": f"Observa una lámina centrada en {tema} y relaciónala con {tema_padre}.",
                        "marcadores": marcadores,
                        "preguntas": [
                            f"¿Dónde ubicarías {tema}?",
                            f"¿Qué relación anatómica ayuda a comprender {tema}?",
                            "¿Cómo lo explicarías en una pregunta abierta?",
                        ],
                        "modo_practica": "Primero intenta responder sin mirar pistas; luego revela marcadores y corrige tu explicación.",
                    },
                },
            }
        )

    return {
        "titulo": f"Ruta de aprendizaje por subtemas: {tema_padre}",
        "resumen_general": (
            f"Esta ruta reparte {tema_padre} en subtemas diarios reales del dataset. "
            "Cada día cambia el foco para evitar repeticiones y producir un apunte útil para estudiar."
        ),
        "temas_priorizados": [item["tema"] for item in agenda_dias[:8]],
        "plan_diario": plan,
        "recomendaciones_finales": [
            "Regenera la ruta después de cambiar el tema o el punto específico para que la agenda se actualice.",
            "No estudies solo el título del día: completa definición, ubicación, relaciones e importancia.",
            "Usa la respuesta modelo como comparación, no como copia literal.",
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



def crear_historial_generacion_visual(
    *,
    estado,
    tema,
    numero_dia,
    categoria,
    prompt,
    negative_prompt,
    image_url="",
    detalle="",
):
    """Registra evidencia técnica de la generación visual dentro del plan_json.

    Este historial sirve para defensa y pruebas: demuestra que la imagen fue generada por
    el pipeline IA y que quedó persistida como base64 dentro de la ruta.
    """
    provider = os.getenv("IMAGE_PROVIDER", "local").strip().lower() or "local"
    if provider == "local":
        motor = "ComfyUI local + RTX 3080 Ti"
        endpoint = os.getenv("LOCAL_IMAGE_API_URL", "").strip()
    else:
        motor = "Gemini Image"
        endpoint = os.getenv("GEMINI_IMAGE_MODEL", "").strip()

    image_url = str(image_url or "")
    if image_url.startswith("data:image/"):
        persistencia = "base64_en_plan_json"
        dependencia_runtime = "No depende de Cloudflare ni de la PC después de generarse"
    elif image_url.startswith("http"):
        persistencia = "url_externa_temporal"
        dependencia_runtime = "Depende de que la URL externa siga activa"
    elif image_url:
        persistencia = "archivo_media"
        dependencia_runtime = "Depende del almacenamiento del servidor"
    else:
        persistencia = "sin_imagen"
        dependencia_runtime = "No se generó imagen"

    return {
        "estado": estado,
        "tipo_recurso": "lamina_anatomica",
        "tema": str(tema or ""),
        "dia": numero_dia,
        "categoria": categoria,
        "proveedor": provider,
        "motor": motor,
        "endpoint": endpoint,
        "persistencia": persistencia,
        "dependencia_runtime": dependencia_runtime,
        "generado_en": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        "prompt_resumen": Truncator(str(prompt or "")).chars(260),
        "negative_prompt_resumen": Truncator(str(negative_prompt or "")).chars(180),
        "detalle": str(detalle or ""),
    }

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
                anatomica["historial_generacion"] = crear_historial_generacion_visual(
                    estado="ok",
                    tema=tema,
                    numero_dia=numero_dia,
                    categoria=categoria,
                    prompt=prompt_controlado,
                    negative_prompt=negative_controlado,
                    image_url=image_url,
                    detalle="Imagen generada correctamente y guardada dentro del plan_json.",
                )
                imagenes_generadas += 1
            elif image_error:
                anatomica["image_error"] = image_error
                anatomica["historial_generacion"] = crear_historial_generacion_visual(
                    estado="error",
                    tema=tema,
                    numero_dia=numero_dia,
                    categoria=categoria,
                    prompt=prompt_controlado,
                    negative_prompt=negative_controlado,
                    image_url="",
                    detalle=image_error,
                )

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
    api_url = os.getenv("LOCAL_IMAGE_API_URL", "").replace("\ufeff", "").strip().rstrip("/")
    job_base_url = os.getenv("LOCAL_IMAGE_JOB_BASE_URL", "").replace("\ufeff", "").strip().rstrip("/")

    # Fix de producción: si Render no expone LOCAL_IMAGE_API_URL por cualquier motivo,
    # pero sí existe LOCAL_IMAGE_JOB_BASE_URL, se arma automáticamente el endpoint.
    if not api_url and job_base_url:
        api_url = f"{job_base_url}/generate-anatomy"

    if not job_base_url and api_url:
        # Si no lo pusiste, lo inferimos quitando /generate-anatomy.
        job_base_url = api_url.replace("/generate-anatomy", "").rstrip("/")

    if not api_url:
        return "", "Falta LOCAL_IMAGE_API_URL o LOCAL_IMAGE_JOB_BASE_URL en Render."

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


def _normalizar_lista_dict(valor, claves, max_items=6):
    """Normaliza listas de diccionarios sin romper si el LLM manda strings."""
    resultado = []

    if isinstance(valor, list):
        for item in valor[:max_items]:
            if isinstance(item, dict):
                limpio = {}
                for clave in claves:
                    limpio[clave] = str(item.get(clave, "")).strip()
                if any(limpio.values()):
                    resultado.append(limpio)
            else:
                texto = str(item).strip()
                if texto:
                    limpio = {clave: "" for clave in claves}
                    limpio[claves[0]] = texto
                    resultado.append(limpio)

    return resultado


def _normalizar_actividad_escritura(valor):
    if not isinstance(valor, dict):
        valor = {}

    plantilla = normalizar_lista(valor.get("plantilla", []))
    if not plantilla:
        plantilla = [
            "Definición:",
            "Ubicación anatómica:",
            "Relaciones principales:",
            "Importancia funcional o clínica:",
            "Cierre con mis palabras:",
        ]

    return {
        "titulo": str(valor.get("titulo", "Producción escrita del día")).strip(),
        "consigna": str(valor.get("consigna", "Redacta una respuesta breve usando tus propias palabras.")).strip(),
        "instrucciones": str(
            valor.get(
                "instrucciones",
                "Completa la plantilla en tu cuaderno y compara tu respuesta con el modelo para corregir lo que falte.",
            )
        ).strip(),
        "plantilla": plantilla[:8],
        "ejemplo_respuesta": str(valor.get("ejemplo_respuesta", "")).strip(),
    }



def texto_es_generico_lectura(*partes):
    texto = " ".join(str(p or "") for p in partes).lower()
    senales_genericas = [
        "autoevaluación",
        "autoevaluacion",
        "concepto principal que debe",
        "contenido que requiere mayor práctica",
        "explicación breve y precisa de una estructura",
        "estructuras cercanas o conexiones anatómicas",
        "escribe una definición",
        "anota la región anatómica",
        "define",
        "ubicar",
        "relacionar",
        "tema principal del día",
        "debe poder definirse",
        "usa este término para iniciar",
    ]
    return sum(1 for patron in senales_genericas if patron in texto) >= 2 or len(texto.strip()) < 700


def construir_lectura_escritura_real(tema, punto_dificil=""):
    """Construye contenido real para Lectura/Escritura cuando el LLM devuelve relleno.

    No reemplaza al LLM: funciona como corrector pedagógico para que la modalidad
    Lectura/Escritura siempre entregue material que se pueda leer, copiar y usar
    para responder en examen.
    """
    tema = str(tema or "el tema seleccionado").strip()
    punto = str(punto_dificil or "el punto difícil seleccionado").strip()
    t = f"{tema} {punto}".lower()
    categoria = detectar_categoria_tema(tema, punto)

    if "corazón" in t or "corazon" in t or "vasos" in t or "card" in t:
        resumen = (
            "El corazón y los vasos del tronco deben estudiarse como un sistema de conducción y distribución de la sangre. "
            "El corazón funciona como una bomba muscular ubicada en el mediastino medio, protegida por el pericardio y relacionada con los pulmones, el diafragma, el esternón y los grandes vasos. "
            "Para escribir una buena respuesta se debe ordenar la información en cuatro partes: definición, ubicación, relaciones anatómicas e importancia funcional. "
            "El punto clave no es memorizar nombres aislados, sino explicar cómo el corazón recibe sangre por las venas, la impulsa hacia pulmones y cuerpo, y se conecta con vasos como la aorta, el tronco pulmonar, las venas cavas y las venas pulmonares."
        )
        lectura_profunda = [
            {
                "subtitulo": "1. Concepto central",
                "contenido": (
                    "El corazón es un órgano muscular hueco que actúa como bomba impulsora de la sangre. "
                    "Trabaja de forma continua para enviar sangre hacia los pulmones y hacia el resto del cuerpo. "
                    "En Anatomía I se estudia junto con los vasos porque no funciona de manera aislada: recibe sangre, la conduce por sus cavidades y la expulsa por grandes arterias. "
                    "Por eso, al leer este tema conviene unir órgano, cavidades, vasos y circulación."
                ),
            },
            {
                "subtitulo": "2. Ubicación anatómica",
                "contenido": (
                    "El corazón se localiza en el mediastino medio, dentro de la cavidad torácica, entre ambos pulmones. "
                    "Se ubica detrás del esternón y por encima del diafragma. Su base mira principalmente hacia atrás, arriba y a la derecha, mientras que el vértice se dirige hacia abajo, adelante y a la izquierda. "
                    "Esta ubicación permite relacionarlo con estructuras torácicas importantes y ayuda a responder preguntas de localización."
                ),
            },
            {
                "subtitulo": "3. Relaciones principales",
                "contenido": (
                    "El corazón se relaciona superiormente con los grandes vasos, como la aorta, el tronco pulmonar y las venas cavas. "
                    "Lateralmente se aproxima a los pulmones y pleuras; inferiormente se apoya sobre el diafragma; anteriormente se proyecta hacia el esternón. "
                    "Estas relaciones son importantes porque permiten explicar su posición real dentro del tórax y no solo nombrarlo como una bomba."
                ),
            },
            {
                "subtitulo": "4. Idea para escribir en examen",
                "contenido": (
                    "Una respuesta completa debe iniciar definiendo el corazón, luego ubicarlo en el mediastino medio y finalmente relacionarlo con sus vasos principales. "
                    "También debe mencionarse su importancia funcional: impulsar la sangre hacia la circulación pulmonar y sistémica. "
                    f"Si el punto difícil es {punto}, intégralo como parte de la explicación para demostrar comprensión específica."
                ),
            },
        ]
        conceptos = [
            {"termino": "Corazón", "explicacion": "Órgano muscular hueco que impulsa la sangre por el sistema circulatorio.", "como_usarlo": "Empieza una respuesta diciendo: 'El corazón es un órgano muscular hueco...'"},
            {"termino": "Mediastino medio", "explicacion": "Región del tórax donde se ubica el corazón, entre ambos pulmones.", "como_usarlo": "Úsalo para responder ubicación: 'Se localiza en el mediastino medio'."},
            {"termino": "Pericardio", "explicacion": "Membrana que rodea y protege al corazón, ayudando a fijarlo en su posición.", "como_usarlo": "Menciónalo al hablar de envolturas y relaciones del corazón."},
            {"termino": "Aorta", "explicacion": "Arteria principal que sale del ventrículo izquierdo y distribuye sangre oxigenada.", "como_usarlo": "Úsala como ejemplo de gran vaso relacionado con el corazón."},
            {"termino": "Tronco pulmonar", "explicacion": "Vaso que sale del ventrículo derecho y conduce sangre hacia los pulmones.", "como_usarlo": "Sirve para explicar la circulación pulmonar."},
            {"termino": "Venas cavas", "explicacion": "Vasos que llevan sangre venosa hacia la aurícula derecha.", "como_usarlo": "Inclúyelas al explicar entrada de sangre al corazón."},
        ]
        esquema = [
            {"seccion": "Definición", "desarrollo": "El corazón es un órgano muscular hueco que actúa como bomba del sistema circulatorio."},
            {"seccion": "Ubicación", "desarrollo": "Se localiza en el mediastino medio, entre los pulmones, detrás del esternón y sobre el diafragma."},
            {"seccion": "Relaciones", "desarrollo": "Se relaciona con el pericardio, pulmones, diafragma, esternón y grandes vasos como aorta, tronco pulmonar, venas cavas y venas pulmonares."},
            {"seccion": "Importancia", "desarrollo": "Su función es impulsar la sangre hacia la circulación pulmonar y sistémica, manteniendo el transporte de oxígeno y nutrientes."},
        ]
        cornell = [
            {"pregunta_guia": "¿Qué es el corazón?", "apuntes": "Órgano muscular hueco que funciona como bomba central de la circulación.", "clave_memoria": "Bomba"},
            {"pregunta_guia": "¿Dónde se ubica?", "apuntes": "En el mediastino medio, entre ambos pulmones, detrás del esternón y apoyado sobre el diafragma.", "clave_memoria": "Mediastino"},
            {"pregunta_guia": "¿Qué vasos principales se relacionan?", "apuntes": "Aorta, tronco pulmonar, venas cavas y venas pulmonares.", "clave_memoria": "Grandes vasos"},
            {"pregunta_guia": "¿Cómo responder en examen?", "apuntes": "Definición + ubicación + relaciones + función circulatoria.", "clave_memoria": "DURF"},
        ]
        glosario = [
            {"termino": "Aurícula", "definicion": "Cavidad superior del corazón que recibe sangre.", "relacion": "Ayuda a explicar la entrada de sangre al corazón."},
            {"termino": "Ventrículo", "definicion": "Cavidad inferior que impulsa sangre hacia arterias principales.", "relacion": "Permite explicar la salida de sangre hacia pulmones o cuerpo."},
            {"termino": "Aorta", "definicion": "Arteria principal que nace del ventrículo izquierdo.", "relacion": "Conecta el corazón con la circulación sistémica."},
            {"termino": "Tronco pulmonar", "definicion": "Vaso que sale del ventrículo derecho hacia los pulmones.", "relacion": "Conecta el corazón con la circulación pulmonar."},
            {"termino": "Pericardio", "definicion": "Envoltura fibroserosa que rodea al corazón.", "relacion": "Protege y fija el corazón dentro del mediastino."},
        ]
        respuesta_modelo = (
            "El corazón es un órgano muscular hueco que actúa como bomba central del sistema circulatorio. "
            "Se localiza en el mediastino medio, entre ambos pulmones, detrás del esternón y sobre el diafragma. "
            "Está rodeado por el pericardio y se relaciona superiormente con los grandes vasos. "
            "Entre estos vasos se encuentran la aorta, el tronco pulmonar, las venas cavas y las venas pulmonares. "
            "Funcionalmente, recibe sangre venosa, la envía hacia los pulmones para oxigenarse y luego impulsa sangre oxigenada hacia el cuerpo. "
            "Por eso, para estudiar corazón y vasos del tronco se deben relacionar ubicación, cavidades, vasos y circulación."
        )
        respuesta_corta = "El corazón es una bomba muscular ubicada en el mediastino medio; se relaciona con el pericardio, pulmones, diafragma y grandes vasos, y su función es impulsar la sangre hacia pulmones y cuerpo."
        pregunta_examen = "Describa el corazón y sus vasos principales considerando definición, ubicación, relaciones anatómicas e importancia funcional."
        puntos = ["Corazón = bomba muscular", "Ubicación = mediastino medio", "Relaciones = pulmones, diafragma, esternón y pericardio", "Vasos clave = aorta, tronco pulmonar, venas cavas y venas pulmonares"]
        errores = [
            {"error": "Responder solo que el corazón bombea sangre", "correccion": "Agrega ubicación y relaciones anatómicas para que la respuesta sea completa."},
            {"error": "Confundir vasos de entrada y salida", "correccion": "Recuerda: venas llegan al corazón; arterias salen del corazón."},
            {"error": "Olvidar el mediastino", "correccion": "Incluye la frase 'se localiza en el mediastino medio'."},
        ]
    else:
        categoria_nombre = {
            "pelvis_osea": "estructuras óseas y límites anatómicos",
            "articular": "superficies articulares, ligamentos y estabilidad",
            "muscular": "origen, inserción, acción y relaciones musculares",
            "nervioso": "trayectos nerviosos, distribución e inervación",
            "vascular": "trayectos vasculares, ramas y relaciones",
            "linfatico": "cadenas ganglionares, vasos linfáticos y drenaje",
            "visceral": "órganos, ubicación y relaciones viscerales",
            "perine": "límites, planos y relaciones del periné",
        }.get(categoria, "definición, ubicación, relaciones e importancia")
        resumen = (
            f"{tema} debe estudiarse de forma escrita identificando {categoria_nombre}. "
            f"La lectura debe transformarse en un apunte organizado: primero se define el tema, luego se ubica, después se relaciona con {punto} y finalmente se explica su importancia para el examen. "
            "Esta modalidad no busca copiar párrafos largos, sino producir una explicación clara que el estudiante pueda leer, memorizar y responder con sus propias palabras."
        )
        lectura_profunda = [
            {"subtitulo": "1. Qué debo entender", "contenido": f"El tema {tema} debe comenzar con una definición clara. La definición no debe ser una lista de palabras, sino una frase que explique qué estructura, región o sistema se está estudiando y por qué forma parte de Anatomía I."},
            {"subtitulo": "2. Dónde se ubica", "contenido": f"Después de definirlo, se debe ubicar {tema} dentro de la región anatómica correspondiente. Usa referencias espaciales como anterior, posterior, superior, inferior, medial o lateral cuando sean necesarias."},
            {"subtitulo": "3. Con qué se relaciona", "contenido": f"Relaciona {tema} con {punto}. También agrega estructuras cercanas, límites, función o conexiones relevantes según el tipo de tema. Esta parte demuestra comprensión y no solo memoria."},
            {"subtitulo": "4. Cómo escribirlo en examen", "contenido": "La respuesta debe seguir este orden: definición, ubicación, relaciones e importancia. Si puedes escribir esos cuatro elementos sin mirar, el tema ya está listo para practicar con preguntas."},
        ]
        conceptos = [
            {"termino": tema, "explicacion": f"Tema principal que debe definirse, ubicarse y relacionarse con {punto}.", "como_usarlo": f"Inicia la respuesta con: '{tema} se entiende como...'"},
            {"termino": punto, "explicacion": "Punto específico que debe reforzarse en la ruta personalizada.", "como_usarlo": "Inclúyelo después de la definición para demostrar estudio dirigido."},
            {"termino": "Ubicación anatómica", "explicacion": "Región o posición donde se reconoce una estructura.", "como_usarlo": "Escribe: 'Se localiza en...' y agrega una referencia espacial."},
            {"termino": "Relación anatómica", "explicacion": "Vínculo con estructuras cercanas, límites, función o continuidad.", "como_usarlo": "Escribe: 'Se relaciona con...' para completar la respuesta."},
        ]
        esquema = [
            {"seccion": "Definición", "desarrollo": f"{tema} debe definirse con una frase clara que indique qué se estudia."},
            {"seccion": "Ubicación", "desarrollo": "Debe indicarse la región anatómica y referencias espaciales principales."},
            {"seccion": "Relaciones", "desarrollo": f"Debe conectarse con {punto} y con estructuras vecinas o funciones asociadas."},
            {"seccion": "Importancia", "desarrollo": "Permite responder preguntas de identificación, relación y explicación anatómica."},
        ]
        cornell = [
            {"pregunta_guia": f"¿Qué es {tema}?", "apuntes": f"Escribe una definición clara de {tema} con tus palabras.", "clave_memoria": "Definir"},
            {"pregunta_guia": "¿Dónde se ubica?", "apuntes": "Anota región, límites o referencias espaciales.", "clave_memoria": "Ubicar"},
            {"pregunta_guia": f"¿Cómo se relaciona con {punto}?", "apuntes": "Agrega conexiones anatómicas o funcionales relevantes.", "clave_memoria": "Relacionar"},
            {"pregunta_guia": "¿Cómo lo respondería?", "apuntes": "Redacta definición + ubicación + relaciones + importancia.", "clave_memoria": "Responder"},
        ]
        glosario = [
            {"termino": tema, "definicion": "Tema central que debe dominarse en la sesión.", "relacion": f"Se conecta con {punto} y con el objetivo del día."},
            {"termino": punto, "definicion": "Subtema marcado como dificultad principal.", "relacion": "Debe aparecer en la respuesta escrita."},
            {"termino": "Definición", "definicion": "Explicación precisa de qué es una estructura o región.", "relacion": "Es el inicio de una respuesta académica."},
            {"termino": "Relaciones", "definicion": "Estructuras cercanas o conexiones anatómicas relevantes.", "relacion": "Demuestran comprensión y no solo memoria."},
        ]
        respuesta_modelo = (
            f"{tema} es el contenido central de esta sesión y debe explicarse de manera ordenada. "
            f"Primero se define qué se estudia y luego se ubica dentro de la región anatómica correspondiente. "
            f"Después se relaciona con {punto} y con las estructuras vecinas o funciones que correspondan. "
            "Una respuesta completa no debe limitarse a nombrar estructuras; debe explicar ubicación, relaciones e importancia. "
            "Esta forma de redacción permite responder mejor preguntas abiertas, de identificación y de relación anatómica."
        )
        respuesta_corta = f"{tema} debe explicarse con definición, ubicación, relación con {punto} e importancia anatómica para responder correctamente en examen."
        pregunta_examen = f"Explique {tema} considerando definición, ubicación, relaciones e importancia anatómica."
        puntos = [f"Tema central: {tema}", f"Punto difícil: {punto}", "Responder con definición + ubicación + relaciones", "Evitar copiar; redactar con palabras propias"]
        errores = [
            {"error": "Hacer una lista sin explicación", "correccion": "Convierte cada punto en una oración completa."},
            {"error": "No mencionar ubicación", "correccion": "Agrega una referencia anatómica clara."},
            {"error": "No conectar con el punto difícil", "correccion": f"Incluye explícitamente {punto} en la respuesta."},
        ]

    actividad = {
        "titulo": "Producción escrita guiada",
        "consigna": pregunta_examen,
        "instrucciones": "Escribe primero la respuesta corta y luego desarrolla la respuesta completa. Revisa si incluiste definición, ubicación, relaciones e importancia.",
        "plantilla": ["Definición:", "Ubicación anatómica:", "Relaciones principales:", "Importancia:", "Respuesta final con mis palabras:"],
        "ejemplo_respuesta": respuesta_corta,
    }
    fichas = [
        {"anverso": "¿Qué debo decir primero?", "reverso": "La definición clara del tema, sin copiar literalmente."},
        {"anverso": "¿Qué no puede faltar?", "reverso": "Ubicación anatómica y al menos una relación importante."},
        {"anverso": "¿Cómo sé que está completo?", "reverso": "Si mi respuesta tiene definición, ubicación, relaciones e importancia."},
    ]
    preguntas = [
        "¿Puedo explicar el tema en 4 líneas sin mirar?",
        "¿Incluí ubicación anatómica precisa?",
        "¿Mencioné relaciones anatómicas o funcionales?",
        "¿Mi respuesta parece de examen o solo una lista?",
    ]
    lectura_guiada = [
        "Lee la lectura desarrollada una vez completa sin copiar.",
        "Subraya definición, ubicación, relaciones e importancia.",
        "Copia el cuadro Cornell en tu cuaderno y completa una frase propia por fila.",
        "Redacta la respuesta modelo con tus palabras y compárala con la propuesta del sistema.",
    ]
    return {
        "titulo": f"Guía real de lectura y escritura: {tema}",
        "resumen": resumen,
        "lectura_guiada": lectura_guiada,
        "lectura_profunda": lectura_profunda,
        "conceptos_clave": conceptos,
        "esquema_escrito": esquema,
        "cuadro_cornell": cornell,
        "glosario_detallado": glosario,
        "fichas_memoria": fichas,
        "respuesta_modelo": respuesta_modelo,
        "respuesta_corta": respuesta_corta,
        "pregunta_tipo_examen": pregunta_examen,
        "puntos_memorizacion": puntos,
        "actividad_escritura": actividad,
        "errores_comunes": errores,
        "preguntas_autoverificacion": preguntas,
        "producto_esperado": "Apunte completo: lectura desarrollada, glosario, cuadro Cornell, respuesta corta y respuesta tipo examen.",
    }

def normalizar_lectura(valor, tema="", punto_dificil=""):
    """Normaliza el recurso Lectura/Escritura como una guía escrita REAL.

    La idea es que esta modalidad no muestre solo instrucciones genéricas, sino
    contenido ya desarrollado: lectura profunda, conceptos, cuadro Cornell,
    glosario, respuesta modelo y errores frecuentes.
    """
    if not isinstance(valor, dict):
        valor = {}

    titulo = str(valor.get("titulo", "Guía desarrollada de lectura y escritura")).strip()
    resumen = str(valor.get("resumen", "")).strip()

    lectura_guiada = normalizar_lista(valor.get("lectura_guiada", []))
    preguntas_autoverificacion = normalizar_lista(valor.get("preguntas_autoverificacion", []))
    glosario_simple = normalizar_lista(valor.get("glosario", []))

    lectura_profunda = _normalizar_lista_dict(
        valor.get("lectura_profunda", []),
        ["subtitulo", "contenido"],
        max_items=4,
    )
    conceptos_clave = _normalizar_lista_dict(
        valor.get("conceptos_clave", []),
        ["termino", "explicacion", "como_usarlo"],
        max_items=6,
    )
    esquema_escrito = _normalizar_lista_dict(
        valor.get("esquema_escrito", []),
        ["seccion", "desarrollo"],
        max_items=6,
    )
    cuadro_cornell = _normalizar_lista_dict(
        valor.get("cuadro_cornell", []),
        ["pregunta_guia", "apuntes", "clave_memoria"],
        max_items=6,
    )
    cuadro_estudio = _normalizar_lista_dict(
        valor.get("cuadro_estudio", []),
        ["concepto", "explicacion"],
        max_items=6,
    )
    glosario_detallado = _normalizar_lista_dict(
        valor.get("glosario_detallado", []),
        ["termino", "definicion", "relacion"],
        max_items=8,
    )
    fichas_memoria = _normalizar_lista_dict(
        valor.get("fichas_memoria", []),
        ["anverso", "reverso"],
        max_items=6,
    )
    errores_comunes = _normalizar_lista_dict(
        valor.get("errores_comunes", []),
        ["error", "correccion"],
        max_items=5,
    )
    actividad_escritura = _normalizar_actividad_escritura(valor.get("actividad_escritura", {}))
    respuesta_modelo = str(valor.get("respuesta_modelo", "")).strip()
    respuesta_corta = str(valor.get("respuesta_corta", "")).strip()
    pregunta_tipo_examen = str(valor.get("pregunta_tipo_examen", "")).strip()
    puntos_memorizacion = normalizar_lista(valor.get("puntos_memorizacion", []))

    contenido_revisar = " ".join([
        titulo, resumen, respuesta_modelo,
        " ".join(item.get("contenido", "") for item in lectura_profunda),
        " ".join(item.get("explicacion", "") for item in conceptos_clave),
        " ".join(item.get("desarrollo", "") for item in esquema_escrito),
        " ".join(item.get("apuntes", "") for item in cuadro_cornell),
        " ".join(item.get("definicion", "") for item in glosario_detallado),
    ])
    if tema and texto_es_generico_lectura(contenido_revisar):
        real = construir_lectura_escritura_real(tema, punto_dificil)
        titulo = real["titulo"]
        resumen = real["resumen"]
        lectura_guiada = real["lectura_guiada"]
        lectura_profunda = real["lectura_profunda"]
        conceptos_clave = real["conceptos_clave"]
        esquema_escrito = real["esquema_escrito"]
        cuadro_cornell = real["cuadro_cornell"]
        glosario_detallado = real["glosario_detallado"]
        fichas_memoria = real["fichas_memoria"]
        respuesta_modelo = real["respuesta_modelo"]
        respuesta_corta = real["respuesta_corta"]
        pregunta_tipo_examen = real["pregunta_tipo_examen"]
        puntos_memorizacion = real["puntos_memorizacion"]
        actividad_escritura = real["actividad_escritura"]
        errores_comunes = real["errores_comunes"]
        preguntas_autoverificacion = real["preguntas_autoverificacion"]
        valor["producto_esperado"] = real["producto_esperado"]

    # Compatibilidad: si el LLM antiguo solo mandó cuadro_estudio, lo usamos como esquema.
    if not esquema_escrito and cuadro_estudio:
        esquema_escrito = [
            {"seccion": item.get("concepto", "Idea"), "desarrollo": item.get("explicacion", "")}
            for item in cuadro_estudio
        ]

    # Compatibilidad: si solo llegó glosario simple, lo convertimos en glosario detallado.
    if not glosario_detallado and glosario_simple:
        for item in glosario_simple[:8]:
            texto = str(item).strip()
            if not texto:
                continue
            if ":" in texto:
                termino, definicion = texto.split(":", 1)
            else:
                termino, definicion = texto, "Concepto clave para repasar."
            glosario_detallado.append({
                "termino": termino.strip(),
                "definicion": definicion.strip(),
                "relacion": "Úsalo para completar tu respuesta escrita.",
            })

    # Fallback inteligente: nunca mostrar una sección vacía o inútil.
    if not resumen:
        resumen = (
            "Este recurso transforma la lectura en una guía escrita activa. "
            "Primero se revisa la idea central, luego se organiza la ubicación anatómica, "
            "las relaciones y la importancia del tema. Finalmente, el estudiante redacta "
            "una respuesta tipo examen y verifica si incluyó los elementos principales."
        )

    if not lectura_profunda:
        lectura_profunda = [
            {
                "subtitulo": "1. Lectura comprensiva",
                "contenido": "Lee el tema para identificar la idea principal. No copies todo el texto: busca definición, ubicación, relaciones e importancia. Convierte cada parte en una frase propia para que el apunte sea útil al repasar.",
            },
            {
                "subtitulo": "2. Organización escrita",
                "contenido": "Después de leer, ordena la información en bloques. Primero escribe qué es el tema, luego dónde se ubica, después con qué se relaciona y finalmente por qué es importante para el examen.",
            },
            {
                "subtitulo": "3. Respuesta tipo examen",
                "contenido": "Cierra el estudio escribiendo una respuesta breve sin mirar tus apuntes. Compara tu respuesta con el modelo y corrige si falta definición, ubicación, relaciones o importancia.",
            },
        ]

    if not lectura_guiada:
        lectura_guiada = [
            "Lee el resumen desarrollado y subraya definición, ubicación y relaciones.",
            "Copia el esquema escrito en tu cuaderno usando tus propias palabras.",
            "Completa el cuadro Cornell y convierte cada pregunta guía en una respuesta corta.",
            "Redacta la respuesta tipo examen sin mirar y luego compárala con el modelo.",
        ]

    if not conceptos_clave:
        conceptos_clave = [
            {"termino": "Definición", "explicacion": "Explica qué es el tema o estructura.", "como_usarlo": "Empieza tu respuesta con una frase clara y directa."},
            {"termino": "Ubicación", "explicacion": "Indica dónde se encuentra o dónde se estudia.", "como_usarlo": "Usa expresiones como se localiza en, se relaciona con o se observa en."},
            {"termino": "Relaciones", "explicacion": "Conecta el tema con estructuras cercanas.", "como_usarlo": "Agrega al menos una relación anatómica para que la respuesta sea completa."},
            {"termino": "Importancia", "explicacion": "Explica por qué el contenido sirve para comprender el tema o resolver preguntas.", "como_usarlo": "Cierra tu respuesta con una función, utilidad o idea de repaso."},
        ]

    if not esquema_escrito:
        esquema_escrito = [
            {"seccion": "Definición", "desarrollo": "Escribe una definición breve del tema usando tus propias palabras."},
            {"seccion": "Ubicación anatómica", "desarrollo": "Señala la región o estructura donde se localiza el tema estudiado."},
            {"seccion": "Relaciones", "desarrollo": "Menciona estructuras vecinas, conexiones o límites importantes."},
            {"seccion": "Importancia", "desarrollo": "Explica por qué este contenido ayuda a responder preguntas de examen."},
        ]

    if not cuadro_cornell:
        cuadro_cornell = [
            {"pregunta_guia": "¿Qué es?", "apuntes": "Definición clara del tema.", "clave_memoria": "Definir"},
            {"pregunta_guia": "¿Dónde se ubica?", "apuntes": "Región anatómica y referencias espaciales.", "clave_memoria": "Ubicar"},
            {"pregunta_guia": "¿Con qué se relaciona?", "apuntes": "Estructuras vecinas, función o conexión anatómica.", "clave_memoria": "Relacionar"},
        ]

    if not glosario_detallado:
        glosario_detallado = [
            {"termino": "Concepto clave", "definicion": "Idea principal que debe memorizarse.", "relacion": "Sirve para iniciar la respuesta escrita."},
            {"termino": "Ubicación anatómica", "definicion": "Lugar o región donde se encuentra una estructura.", "relacion": "Permite responder preguntas de localización."},
            {"termino": "Relación anatómica", "definicion": "Conexión entre estructuras cercanas.", "relacion": "Ayuda a explicar el tema con mayor profundidad."},
        ]

    if not fichas_memoria:
        fichas_memoria = [
            {"anverso": "¿Qué debo definir?", "reverso": "El concepto principal del tema del día."},
            {"anverso": "¿Qué debo ubicar?", "reverso": "La región anatómica y sus relaciones más importantes."},
            {"anverso": "¿Cómo sé que entendí?", "reverso": "Si puedo escribir una respuesta breve sin mirar apuntes."},
        ]

    if not respuesta_modelo:
        respuesta_modelo = (
            "Una respuesta completa debe iniciar con la definición del tema, continuar con su ubicación anatómica y explicar al menos una relación importante. "
            "Luego debe agregar su importancia funcional, clínica o académica según corresponda. "
            "Para terminar, conviene cerrar con una frase propia que conecte el contenido con el objetivo de estudio del día."
        )

    if not respuesta_corta:
        respuesta_corta = "Respuesta corta: define el tema, ubícalo anatómicamente y menciona una relación importante."

    if not pregunta_tipo_examen:
        pregunta_tipo_examen = "Explique el tema considerando definición, ubicación, relaciones e importancia."

    if not puntos_memorizacion:
        puntos_memorizacion = [
            "Definición clara del tema",
            "Ubicación anatómica principal",
            "Relación con estructuras cercanas",
            "Importancia para responder en examen",
        ]

    if not errores_comunes:
        errores_comunes = [
            {"error": "Copiar sin comprender", "correccion": "Reescribe cada idea con tus propias palabras."},
            {"error": "Olvidar la ubicación", "correccion": "Incluye siempre una frase de localización anatómica."},
            {"error": "No mencionar relaciones", "correccion": "Agrega al menos una estructura vecina o función asociada."},
        ]

    if not preguntas_autoverificacion:
        preguntas_autoverificacion = [
            "¿Mi respuesta tiene definición, ubicación y relaciones?",
            "¿Puedo explicar el tema sin copiar literalmente?",
            "¿Qué concepto del glosario todavía debo reforzar?",
            "¿Mi respuesta parece una explicación de examen o solo una lista?",
        ]

    return {
        "habilitado": bool(valor.get("habilitado")),
        "titulo": titulo,
        "resumen": resumen,
        "lectura_guiada": lectura_guiada[:6],
        "lectura_profunda": lectura_profunda[:4],
        "conceptos_clave": conceptos_clave[:6],
        "esquema_escrito": esquema_escrito[:6],
        "cuadro_estudio": cuadro_estudio[:6],
        "cuadro_cornell": cuadro_cornell[:6],
        "glosario": glosario_simple[:8],
        "glosario_detallado": glosario_detallado[:8],
        "fichas_memoria": fichas_memoria[:6],
        "actividad_escritura": actividad_escritura,
        "respuesta_modelo": respuesta_modelo,
        "respuesta_corta": respuesta_corta,
        "pregunta_tipo_examen": pregunta_tipo_examen,
        "puntos_memorizacion": puntos_memorizacion[:6],
        "errores_comunes": errores_comunes[:5],
        "preguntas_autoverificacion": preguntas_autoverificacion[:6],
        "producto_esperado": str(
            valor.get(
                "producto_esperado",
                "Apunte desarrollado con lectura profunda, conceptos clave, cuadro Cornell, glosario, respuesta tipo examen y correcciones.",
            )
        ).strip(),
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



# =========================================================
# MEJORAS SENIOR: generación visual anatómica + mapas mentales premium
# Estas funciones redefinen las anteriores sin cambiar modelos ni migraciones.
# =========================================================

def limpiar_texto_visual(texto, max_chars=70):
    texto = str(texto or "").strip()
    texto = re.sub(r"\s+", " ", texto)
    texto = texto.replace("**", "").replace("__", "")
    if len(texto) > max_chars:
        texto = texto[: max_chars - 1].rstrip() + "…"
    return texto


def detectar_categoria_tema(tema: str, punto_dificil: str = "") -> str:
    t = f"{tema or ''} {punto_dificil or ''}".strip().lower()

    if any(p in t for p in ["linfático", "linfatico", "linfáticos", "linfaticos", "linfa", "ganglio", "nódulo", "nodulo"]):
        return "linfatico"

    if any(p in t for p in ["periné", "perine", "triángulo urogenital", "triangulo urogenital", "diafragma pélvico", "diafragma pelvico"]):
        return "perine"

    if any(p in t for p in ["plexo", "nervio", "nervios", "raíz nerviosa", "raiz nerviosa", "simpático", "parasimpático"]):
        return "nervioso"

    if any(p in t for p in ["arteria", "arterias", "vena", "venas", "vascular", "vaso", "vasos", "aorta", "cava", "porta"]):
        return "vascular"

    if any(p in t for p in ["articulación", "articulacion", "articulaciones", "ligamento", "ligamentos", "sínfisis", "sinfisis"]):
        return "articular"

    if any(p in t for p in ["músculo", "musculo", "músculos", "musculos", "diafragma", "pared abdominal", "suelo pélvico", "suelo pelvico"]):
        return "muscular"

    if "pelvis" in t and any(p in t for p in ["vejiga", "recto", "útero", "utero", "ovario", "próstata", "prostata", "pelvis menor", "órganos", "organos"]):
        return "pelvis_visceral"

    if "pelvis" in t or any(p in t for p in ["coxal", "sacro", "isquion", "ilion", "pubis"]):
        return "pelvis_osea"

    if any(p in t for p in ["abdomen", "abdominal", "peritoneo", "mesenterio", "estómago", "estomago", "intestino", "hígado", "higado", "bazo", "páncreas", "pancreas", "riñón", "rinon", "renal"]):
        return "abdominal"

    if any(p in t for p in ["tórax", "torax", "costilla", "costillas", "esternón", "esternon", "mediastino", "pulmón", "pulmon", "corazón", "corazon"]):
        return "toracico"

    if any(p in t for p in ["hueso", "huesos", "óseo", "oseo", "esqueleto", "columna", "vértebra", "vertebra"]):
        return "oseo"

    if any(p in t for p in ["órgano", "organo", "órganos", "organos", "víscera", "viscera", "visceral"]):
        return "visceral"

    return "general"


def construir_prompt_visual_controlado(tema: str, datos_academicos=None, anatomica=None) -> tuple[str, str, str]:
    """Prompt más controlado para evitar imágenes raras, texto falso y anatomía incoherente."""
    anatomica = anatomica or {}
    punto = ""
    materia = "Anatomía I"

    if datos_academicos is not None:
        punto = getattr(datos_academicos, "temas_dificiles", "") or ""
        materia = getattr(datos_academicos, "materia", "Anatomía I") or "Anatomía I"

    if not punto and isinstance(anatomica, dict):
        punto = anatomica.get("descripcion", "") or anatomica.get("titulo", "") or ""

    categoria = detectar_categoria_tema(tema, punto)
    descripcion = limpiar_texto_visual(anatomica.get("descripcion", ""), 220)

    base = (
        "Create a clean professional medical atlas illustration for university anatomy study. "
        f"Subject: {tema}. Focus: {punto or 'general review'}. Course: {materia}. "
        f"Didactic purpose: {descripcion or 'identify the main anatomical relationships'}. "
        "Use a realistic educational anatomy plate style, centered composition, white or very light background, "
        "soft anatomical colors, high detail, correct proportions, clear spatial relationships, marker-ready empty areas, "
        "NO embedded text, NO labels, NO letters, NO numbers, NO watermark. "
    )

    negative_base = (
        "text, labels, letters, numbers, typography, watermark, logo, signature, fake writing, infographic text, "
        "low quality, blurry, noisy, distorted anatomy, malformed structures, wrong body part, extra limbs, extra bones, "
        "messy composition, cropped anatomy, dark background, vintage poster, horror, surgery, blood, gore"
    )

    especificaciones = {
        "pelvis_osea": (
            "Show the human bony pelvis only, anterior view with slight superior perspective, iliac bones, sacrum, coccyx, pubis, ischium and pubic symphysis visible. "
            "Isolated bone structure, no organs, no muscles, no full skeleton.",
            "skull, cranium, face, full body, ribs, skin, organs, muscles"
        ),
        "pelvis_visceral": (
            "Show a respectful educational cutaway of the pelvis minor with pelvic cavity relationships, bladder, rectum and reproductive region when relevant. "
            "Use a neutral medical section view, not explicit, not sexualized.",
            "erotic, sexualized, glamour, explicit nudity, face, full body pose"
        ),
        "abdominal": (
            "Show abdominal region or organs in a clean didactic cutaway, emphasizing position, layers and neighboring relationships. "
            "Use a textbook abdominal anatomy plate, not a surgical scene.",
            "surgery, open wound, blood, full body glamour, random limbs"
        ),
        "toracico": (
            "Show thoracic anatomy in a clean atlas view, rib cage or mediastinal relationships only if relevant, clear depth and orientation.",
            "skull, pelvis, random abdomen, surgery, blood"
        ),
        "oseo": (
            "Show the selected skeletal region only, realistic bone texture, isolated anatomical structure, no skin and no organs.",
            "skin, organs, face, full body, muscles if not relevant"
        ),
        "articular": (
            "Show a close-up of the selected joint and ligaments, clear articular surfaces and stabilizing elements, educational atlas style.",
            "organs, face, full body fashion pose, unrelated muscles"
        ),
        "muscular": (
            "Show layered muscular anatomy of the selected region, fiber direction and neighboring muscle groups, clean neutral view.",
            "organs only, bones only, erotic, glamour, face closeup"
        ),
        "visceral": (
            "Show internal organs and anatomical relationships in a clean non-graphic medical cutaway, educational atlas plate.",
            "erotic, sexualized, unrelated limbs, full body poster, surgery, blood"
        ),
        "nervioso": (
            "Show nerves or plexus pathways as clean anatomical lines over a subtle anatomical base, clear course and branching, no text.",
            "random colorful infographic, labels, organs only, poster"
        ),
        "vascular": (
            "Show arteries and veins of the selected region, clean vascular pathways with anatomical context, no text.",
            "nerves only, muscles only, fake labels, text"
        ),
        "linfatico": (
            "Show lymph node chains and lymphatic drainage pathways in the selected anatomical region, clean educational composition.",
            "arteries only, veins only, fake labels, random infographic"
        ),
        "perine": (
            "Show a respectful educational anatomical cutaway of the perineal region with muscles and spaces simplified for study, medical style only.",
            "erotic, sexualized, explicit sexual content, glamour, fake text"
        ),
        "general": (
            "Show the selected anatomy topic as a clear educational medical plate, simplified enough for student study but anatomically coherent.",
            "unrelated body region, face, random full body"
        ),
    }

    positivo_extra, negativo_extra = especificaciones.get(categoria, especificaciones["general"])
    positive = base + positivo_extra + " High resolution, crisp edges, balanced lighting, 4:3 composition."
    negative = f"{negative_base}, {negativo_extra}"

    return positive, negative, categoria


def marcadores_sugeridos_por_categoria(categoria: str):
    mapas = {
        "pelvis_osea": [
            {"id": 1, "nombre": "Sacro", "x": 50, "y": 24, "pista": "Estructura posterior central.", "detalle": "Forma la pared posterior de la pelvis ósea y articula con los coxales."},
            {"id": 2, "nombre": "Ilion", "x": 24, "y": 42, "pista": "Ala ósea amplia lateral.", "detalle": "Es la porción superior y lateral del hueso coxal."},
            {"id": 3, "nombre": "Pubis", "x": 50, "y": 75, "pista": "Región anterior inferior.", "detalle": "Participa en la sínfisis púbica y en el límite anterior de la pelvis."},
            {"id": 4, "nombre": "Isquion", "x": 73, "y": 68, "pista": "Porción posteroinferior del coxal.", "detalle": "Se relaciona con la tuberosidad isquiática y el apoyo sentado."},
        ],
        "pelvis_visceral": [
            {"id": 1, "nombre": "Vejiga", "x": 50, "y": 42, "pista": "Órgano anterior de la pelvis menor.", "detalle": "Se ubica por delante del recto y sirve como referencia anterior."},
            {"id": 2, "nombre": "Región reproductora", "x": 50, "y": 56, "pista": "Estructura central según el sexo anatómico representado.", "detalle": "Permite estudiar relaciones con vejiga y recto."},
            {"id": 3, "nombre": "Recto", "x": 50, "y": 72, "pista": "Estructura posterior.", "detalle": "Ocupa la región posterior de la pelvis menor."},
            {"id": 4, "nombre": "Pared pélvica", "x": 27, "y": 54, "pista": "Límite lateral de la cavidad.", "detalle": "Ayuda a comprender el espacio disponible para órganos y vasos."},
        ],
        "abdominal": [
            {"id": 1, "nombre": "Región superior abdominal", "x": 50, "y": 30, "pista": "Zona relacionada con órganos supramesocólicos.", "detalle": "Úsala para ubicar hígado, estómago o bazo según el tema."},
            {"id": 2, "nombre": "Plano medio", "x": 50, "y": 50, "pista": "Referencia para relaciones derecha-izquierda.", "detalle": "Ayuda a ordenar estructuras por posición."},
            {"id": 3, "nombre": "Región inferior abdominal", "x": 50, "y": 70, "pista": "Zona cercana a pelvis o intestino.", "detalle": "Conecta el abdomen con la pelvis menor si corresponde."},
            {"id": 4, "nombre": "Relación lateral", "x": 72, "y": 52, "pista": "Compara estructuras vecinas.", "detalle": "Describe qué queda medial, lateral, anterior o posterior."},
        ],
        "toracico": [
            {"id": 1, "nombre": "Línea media torácica", "x": 50, "y": 35, "pista": "Referencia central.", "detalle": "Sirve para ubicar esternón, mediastino o corazón."},
            {"id": 2, "nombre": "Región costal", "x": 30, "y": 50, "pista": "Referencia lateral.", "detalle": "Relaciona costillas, pleura o límites torácicos."},
            {"id": 3, "nombre": "Mediastino", "x": 50, "y": 55, "pista": "Zona central del tórax.", "detalle": "Contiene estructuras vitales y relaciones vasculares."},
            {"id": 4, "nombre": "Base torácica", "x": 50, "y": 72, "pista": "Límite inferior.", "detalle": "Relaciona el tórax con diafragma y abdomen."},
        ],
        "nervioso": [
            {"id": 1, "nombre": "Trayecto principal", "x": 45, "y": 35, "pista": "Sigue el recorrido desde origen a destino.", "detalle": "Identifica cómo se distribuye el nervio o plexo."},
            {"id": 2, "nombre": "Rama secundaria", "x": 62, "y": 48, "pista": "Observa una división del trayecto.", "detalle": "Relaciona cada rama con función o territorio."},
            {"id": 3, "nombre": "Zona de inervación", "x": 55, "y": 68, "pista": "Área final del recorrido.", "detalle": "Permite conectar anatomía con función."},
        ],
        "vascular": [
            {"id": 1, "nombre": "Vaso principal", "x": 50, "y": 35, "pista": "Estructura de mayor calibre.", "detalle": "Úsala como referencia para ramas o drenaje."},
            {"id": 2, "nombre": "Rama vascular", "x": 38, "y": 52, "pista": "Trayecto secundario.", "detalle": "Identifica hacia qué región se dirige."},
            {"id": 3, "nombre": "Relación vecina", "x": 62, "y": 58, "pista": "Compara con órganos, nervios o músculos.", "detalle": "La relación espacial ayuda a memorizar el recorrido."},
        ],
    }

    return mapas.get(categoria, [
        {"id": 1, "nombre": "Estructura principal", "x": 50, "y": 35, "pista": "Observa el elemento central.", "detalle": "Relaciona esta estructura con el objetivo del día."},
        {"id": 2, "nombre": "Relación anatómica", "x": 32, "y": 55, "pista": "Compara posición y vecindad.", "detalle": "Describe qué queda medial, lateral, anterior o posterior."},
        {"id": 3, "nombre": "Referencia espacial", "x": 68, "y": 55, "pista": "Busca el borde, límite o zona de transición.", "detalle": "Úsalo para ubicar el tema en el cuerpo."},
        {"id": 4, "nombre": "Punto difícil", "x": 50, "y": 72, "pista": "Conecta con el subtema que más debes reforzar.", "detalle": "Explica este punto con tus propias palabras."},
    ])


def construir_ramas_mapa_premium(visual: dict, tema: str):
    ramas = []
    existentes = visual.get("ramas") if isinstance(visual.get("ramas"), list) else []

    for rama in existentes[:4]:
        if not isinstance(rama, dict):
            continue
        titulo = limpiar_texto_visual(rama.get("titulo") or "Idea clave", 34)
        detalle = limpiar_texto_visual(rama.get("detalle") or "Relación importante del tema.", 110)
        subpuntos = [limpiar_texto_visual(item, 42) for item in normalizar_lista(rama.get("subpuntos", []))[:3]]
        if len(subpuntos) < 2:
            subpuntos += ["Ubicar en la lámina", "Explicar con tus palabras"]
        ramas.append({
            "titulo": titulo,
            "detalle": detalle,
            "subpuntos": subpuntos[:3],
            "estudio_activo": limpiar_texto_visual(rama.get("estudio_activo") or f"Convierte {titulo.lower()} en una pregunta oral.", 95),
        })

    apoyo = normalizar_lista(visual.get("apoyo_visual", []))
    plantillas = [
        ("Concepto", f"Define {tema} con una frase clara.", ["Definición simple", "Función o importancia"], "Explícalo sin mirar tus apuntes."),
        ("Ubicación", "Reconoce dónde se encuentra dentro del cuerpo o región.", ["Región anatómica", "Referencia espacial"], "Señala la ubicación en la lámina."),
        ("Relaciones", "Conecta el tema con estructuras vecinas.", ["Anterior/posterior", "Medial/lateral"], "Di qué estructuras lo rodean."),
        ("Punto difícil", "Prioriza el subtema que más cuesta.", apoyo[:2] or ["Duda principal", "Repaso final"], "Haz una pregunta de examen sobre este punto."),
    ]

    while len(ramas) < 4:
        titulo, detalle, subpuntos, accion = plantillas[len(ramas)]
        ramas.append({
            "titulo": titulo,
            "detalle": detalle,
            "subpuntos": subpuntos[:3],
            "estudio_activo": accion,
        })

    return ramas[:4]


def mejorar_visual_para_mapa_html(visual: dict, tema: str):
    if not isinstance(visual, dict):
        visual = {}

    nodo = limpiar_texto_visual(visual.get("nodo_central") or tema or "Tema central", 34)
    ramas = construir_ramas_mapa_premium(visual, tema)

    apoyo_visual = normalizar_lista(visual.get("apoyo_visual", []))
    if not apoyo_visual:
        apoyo_visual = [rama["titulo"] for rama in ramas]

    visual.update({
        "habilitado": bool(visual.get("habilitado", True)),
        "titulo": limpiar_texto_visual(visual.get("titulo") or f"Mapa mental de {tema}", 70),
        "tipo": "mapa_mental_html_premium",
        "descripcion": limpiar_texto_visual(
            visual.get("descripcion") or "Mapa mental estructurado para repasar el tema sin depender de texto generado dentro de una imagen.",
            180
        ),
        "nodo_central": nodo,
        "ramas": ramas,
        "apoyo_visual": apoyo_visual[:6],
        "image_url": "",
        "image_error": "",
        "prompt_imagen": "",
        "negative_prompt": "",
        "categoria_visual": "mapa_html",
        "instruccion_estudio": "Lee el nodo central, recorre las cuatro ramas y convierte cada subpunto en una pregunta de repaso.",
    })

    return visual


def normalizar_visual(valor):
    if not isinstance(valor, dict):
        valor = {}

    visual = {
        "habilitado": bool(valor.get("habilitado")),
        "titulo": str(valor.get("titulo", "Mapa mental generado por IA")).strip(),
        "tipo": str(valor.get("tipo", "mapa_mental_html_premium")).strip(),
        "descripcion": str(valor.get("descripcion", "")).strip(),
        "nodo_central": str(valor.get("nodo_central", "Tema central")).strip(),
        "ramas": valor.get("ramas", []),
        "mermaid": str(valor.get("mermaid", "")).strip(),
        "apoyo_visual": normalizar_lista(valor.get("apoyo_visual", [])),
        "prompt_imagen": "",
        "negative_prompt": "",
        "categoria_visual": "mapa_html",
        "image_url": "",
        "image_error": "",
        "instruccion_estudio": str(valor.get("instruccion_estudio", "")).strip(),
    }

    tema = visual["nodo_central"] or "Tema central"
    return mejorar_visual_para_mapa_html(visual, tema)


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
                x = max(8, min(int(item.get("x") or 50), 92))
                y = max(8, min(int(item.get("y") or 50), 92))
            except (TypeError, ValueError):
                x = 50
                y = 50

            nombre = limpiar_texto_visual(item.get("nombre", f"Estructura {idx}"), 38)
            pista = limpiar_texto_visual(item.get("pista", ""), 90)
            detalle = limpiar_texto_visual(item.get("detalle", ""), 150)

            marcadores_limpios.append({
                "id": int(item.get("id") or idx),
                "nombre": nombre,
                "x": x,
                "y": y,
                "pista": pista,
                "detalle": detalle,
            })

    return {
        "habilitado": bool(valor.get("habilitado")),
        "titulo": limpiar_texto_visual(valor.get("titulo", "Lámina anatómica guiada"), 75),
        "tipo_vista": limpiar_texto_visual(valor.get("tipo_vista", "vista anatómica didáctica"), 45),
        "descripcion": limpiar_texto_visual(valor.get("descripcion", ""), 220),
        "marcadores": marcadores_limpios[:5],
        "preguntas": normalizar_lista(valor.get("preguntas", []))[:5],
        "preguntas_guiadas": normalizar_preguntas_guiadas(
            valor.get("preguntas_guiadas", valor.get("preguntas_detalladas", [])),
            preguntas_base=normalizar_lista(valor.get("preguntas", [])),
            marcadores=marcadores_limpios[:5],
        ),
        "modo_practica": str(valor.get("modo_practica", "Observa primero, responde sin ayuda y luego revela pistas y respuestas.")).strip(),
        "prompt_imagen": str(valor.get("prompt_imagen", "")).strip(),
        "negative_prompt": str(valor.get("negative_prompt", "")).strip(),
        "categoria_visual": str(valor.get("categoria_visual", "")).strip(),
        "image_url": str(valor.get("image_url", "")).strip(),
        "image_error": str(valor.get("image_error", "")).strip(),
        "calidad_didactica": "Prompt controlado + marcadores externos + práctica guiada",
    }


def enriquecer_plan_con_imagenes_ia(respuesta, user, datos_academicos):
    """Enriquece mapa mental HTML y lámina anatómica con prompt controlado, marcadores y práctica."""
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
            recursos = {}
            dia["recursos"] = recursos

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
        anatomica["calidad_didactica"] = "Prompt controlado, sin texto dentro de imagen, marcadores HTML externos."

        marcadores = anatomica.get("marcadores", [])
        if not isinstance(marcadores, list) or len(marcadores) < 3:
            anatomica["marcadores"] = marcadores_sugeridos_por_categoria(categoria)

        anatomica["preguntas_guiadas"] = normalizar_preguntas_guiadas(
            anatomica.get("preguntas_guiadas", anatomica.get("preguntas", [])),
            preguntas_base=normalizar_lista(anatomica.get("preguntas", [])),
            marcadores=anatomica.get("marcadores", []),
        )

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
                anatomica["historial_generacion"] = crear_historial_generacion_visual(
                    estado="ok",
                    tema=tema,
                    numero_dia=numero_dia,
                    categoria=categoria,
                    prompt=prompt_controlado,
                    negative_prompt=negative_controlado,
                    image_url=image_url,
                    detalle="Lámina generada con prompt controlado y guardada dentro del plan_json/base64 cuando el proveedor lo permite.",
                )
                imagenes_generadas += 1
            else:
                anatomica["image_error"] = image_error or "El proveedor de imagen no devolvió una imagen utilizable."
                anatomica["historial_generacion"] = crear_historial_generacion_visual(
                    estado="error",
                    tema=tema,
                    numero_dia=numero_dia,
                    categoria=categoria,
                    prompt=prompt_controlado,
                    negative_prompt=negative_controlado,
                    image_url="",
                    detalle=anatomica["image_error"],
                )

    return respuesta


def generar_y_guardar_imagen_gemini(prompt, carpeta, nombre_archivo, aspect_ratio="1:1", negative_prompt=None):
    provider = os.getenv("IMAGE_PROVIDER", "gemini").strip().lower()
    if provider == "local":
        return generar_y_guardar_imagen_local(prompt, carpeta, nombre_archivo, aspect_ratio, negative_prompt=negative_prompt)
    return generar_y_guardar_imagen_gemini_api(prompt, carpeta, nombre_archivo, aspect_ratio, negative_prompt=negative_prompt)


def generar_y_guardar_imagen_gemini_api(prompt, carpeta, nombre_archivo, aspect_ratio="1:1", negative_prompt=None):
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
    for candidate in ["gemini-2.5-flash-image-preview", "gemini-2.5-flash-image", "gemini-3-pro-image", "gemini-3.1-flash-image"]:
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

    prompt_final = str(prompt or "").strip()
    if negative_prompt:
        prompt_final += (
            "\n\nStrict negative constraints: "
            + str(negative_prompt)
            + ". Do not render any text, labels, letters, numbers or watermark inside the image."
        )

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
                contents=prompt_final,
                config=config,
            )

            for part in obtener_partes_respuesta(response):
                if guardar_parte_imagen(part, ruta_absoluta):
                    return settings.MEDIA_URL + ruta_relativa.replace("\\", "/"), ""

            response = client.models.generate_content(
                model=model,
                contents=[prompt_final],
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

# =========================================================
# HOTFIX FINAL: contenido diario distinto por subtema
# Colocar al final de rutas/services.py.
# No toca otros servicios. Sobrescribe solo la generación/normalización
# de contenido de la ruta para que cada día tenga contenido propio.
# =========================================================

import unicodedata


def _normalizar_clave_subtema(texto):
    texto = str(texto or "").strip().lower()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _perfil_anatomico_por_subtema(tema, tema_padre="", punto_dificil=""):
    """Devuelve contenido anatómico base diferente para cada subtema.

    La clave de esta función es que NO usa la misma explicación para todos
    los días. Si el tema del día es "Aurículas", el contenido se centra en
    aurículas; si es "Aorta", se centra en aorta, etc.
    """
    tema = str(tema or "Tema anatómico").strip()
    tema_padre = str(tema_padre or "Anatomía I").strip()
    punto = str(punto_dificil or tema).strip()
    k = _normalizar_clave_subtema(f"{tema} {punto}")

    base = {
        "tema": tema,
        "tema_padre": tema_padre,
        "definicion": (
            f"{tema} es un subtema de {tema_padre} que debe estudiarse identificando "
            "su definición, ubicación anatómica, relaciones principales e importancia para el examen."
        ),
        "ubicacion": (
            f"Se estudia dentro de la región anatómica correspondiente a {tema_padre}. "
            "Debe ubicarse usando referencias como anterior, posterior, superior, inferior, medial o lateral según corresponda."
        ),
        "relaciones": (
            f"Debe relacionarse con {punto} y con las estructuras vecinas que permitan explicar continuidad, límites o función."
        ),
        "importancia": (
            "Es importante porque permite responder preguntas de identificación, relación anatómica y explicación funcional."
        ),
        "terminos": [
            (tema, f"Concepto central del día dentro de {tema_padre}.", "Úsalo como inicio de tu respuesta escrita."),
            ("Ubicación anatómica", "Lugar o región donde se reconoce la estructura.", "Incluye una frase que empiece con: se localiza en..."),
            ("Relación anatómica", "Conexión con estructuras vecinas, límites o funciones.", "Agrega al menos una relación para demostrar comprensión."),
            ("Importancia", "Razón por la que el contenido sirve para comprender el tema.", "Cierra la respuesta explicando su utilidad."),
        ],
        "vista": "vista anatómica didáctica",
    }

    perfiles = {
        "desarrollo del corazon": {
            "definicion": "El desarrollo del corazón estudia cómo se forma el corazón durante la etapa embrionaria a partir de estructuras primitivas que se remodelan hasta originar cavidades, tabiques y grandes vasos.",
            "ubicacion": "Se analiza como un proceso embrionario relacionado con la región cardiogénica y el futuro mediastino. No se estudia solo como órgano adulto, sino como una secuencia de formación y organización.",
            "relaciones": "Se relaciona con la formación de aurículas, ventrículos, tabiques y grandes vasos. Comprenderlo ayuda a explicar por qué la anatomía adulta del corazón tiene cavidades separadas y circulación ordenada.",
            "importancia": "Es importante porque conecta la anatomía descriptiva con el origen de las cavidades cardíacas y permite comprender malformaciones o alteraciones de la organización cardíaca.",
            "terminos": [
                ("Desarrollo cardíaco", "Proceso de formación embrionaria del corazón.", "Úsalo para explicar el origen del órgano, no solo su forma adulta."),
                ("Tabicación", "Proceso de separación progresiva de cavidades.", "Sirve para explicar la organización de aurículas y ventrículos."),
                ("Tubo cardíaco", "Estructura inicial que se transforma durante el desarrollo.", "Menciónalo como punto de partida embriológico."),
                ("Grandes vasos", "Vasos conectados al corazón durante su organización.", "Relaciona desarrollo con aorta, tronco pulmonar y venas."),
            ],
            "vista": "esquema embrionario didáctico",
        },
        "anatomia del corazon": {
            "definicion": "La anatomía del corazón estudia la forma, posición, cavidades, caras, bordes y relaciones del órgano cardíaco como bomba central del sistema circulatorio.",
            "ubicacion": "El corazón se localiza en el mediastino medio, entre ambos pulmones, detrás del esternón y por encima del diafragma.",
            "relaciones": "Se relaciona con el pericardio, los pulmones, las pleuras, el diafragma, el esternón y los grandes vasos que entran y salen de sus cavidades.",
            "importancia": "Es importante porque permite integrar cavidades, vasos y circulación en una explicación anatómica completa, útil para preguntas abiertas y de identificación.",
            "terminos": [
                ("Corazón", "Órgano muscular hueco que impulsa la sangre.", "Inicia la respuesta con una definición clara."),
                ("Mediastino medio", "Región central del tórax donde se ubica el corazón.", "Úsalo para responder ubicación."),
                ("Pericardio", "Envoltura que rodea y fija el corazón.", "Inclúyelo al explicar relaciones."),
                ("Grandes vasos", "Vasos principales conectados al corazón.", "Relaciona corazón con circulación."),
            ],
            "vista": "vista anterior del corazón en el mediastino",
        },
        "cavidades cardiacas": {
            "definicion": "Las cavidades cardíacas son los espacios internos del corazón encargados de recibir y expulsar sangre de forma ordenada.",
            "ubicacion": "Se encuentran dentro del corazón y se organizan en dos cavidades superiores, llamadas aurículas, y dos cavidades inferiores, llamadas ventrículos.",
            "relaciones": "Las aurículas reciben sangre venosa o pulmonar, mientras que los ventrículos la impulsan hacia el tronco pulmonar o la aorta. Las válvulas regulan el paso entre cavidades.",
            "importancia": "Son importantes porque explican el recorrido interno de la sangre y permiten diferenciar entrada, paso y salida dentro del corazón.",
            "terminos": [
                ("Aurícula", "Cavidad superior que recibe sangre.", "Úsala para explicar la entrada de sangre."),
                ("Ventrículo", "Cavidad inferior que impulsa sangre.", "Úsalo para explicar la salida de sangre."),
                ("Válvula", "Estructura que dirige el flujo en un solo sentido.", "Relaciona cavidades con circulación."),
                ("Flujo sanguíneo", "Recorrido de la sangre por cavidades y vasos.", "Sirve para ordenar la respuesta."),
            ],
            "vista": "corte del corazón mostrando cuatro cavidades",
        },
        "auriculas": {
            "definicion": "Las aurículas son las cavidades superiores del corazón encargadas principalmente de recibir la sangre que llega al órgano.",
            "ubicacion": "Se ubican en la parte superior del corazón. La aurícula derecha recibe sangre de las venas cavas, y la aurícula izquierda recibe sangre de las venas pulmonares.",
            "relaciones": "Se relacionan inferiormente con los ventrículos a través de las válvulas auriculoventriculares. También se conectan con los vasos venosos que llegan al corazón.",
            "importancia": "Son importantes porque representan la zona de entrada de sangre al corazón y permiten entender el inicio del recorrido intracardíaco.",
            "terminos": [
                ("Aurícula derecha", "Cavidad que recibe sangre venosa sistémica.", "Relaciona con vena cava superior e inferior."),
                ("Aurícula izquierda", "Cavidad que recibe sangre oxigenada pulmonar.", "Relaciona con venas pulmonares."),
                ("Válvula auriculoventricular", "Comunica aurícula con ventrículo.", "Explica el paso controlado de sangre."),
                ("Entrada venosa", "Llegada de sangre al corazón.", "Úsalo para diferenciar aurículas de ventrículos."),
            ],
            "vista": "vista superior de aurículas y entrada venosa",
        },
        "ventriculos": {
            "definicion": "Los ventrículos son las cavidades inferiores del corazón encargadas de impulsar la sangre hacia los grandes vasos.",
            "ubicacion": "Se ubican debajo de las aurículas. El ventrículo derecho se relaciona con el tronco pulmonar y el ventrículo izquierdo con la aorta.",
            "relaciones": "Se relacionan superiormente con las aurículas mediante válvulas auriculoventriculares y con los vasos de salida mediante válvulas semilunares.",
            "importancia": "Son importantes porque generan la fuerza principal de expulsión de la sangre hacia la circulación pulmonar y sistémica.",
            "terminos": [
                ("Ventrículo derecho", "Cavidad que impulsa sangre al tronco pulmonar.", "Úsalo para explicar circulación pulmonar."),
                ("Ventrículo izquierdo", "Cavidad que impulsa sangre hacia la aorta.", "Úsalo para explicar circulación mayor."),
                ("Sístole", "Fase de contracción cardíaca.", "Relaciona ventrículos con expulsión."),
                ("Tabique interventricular", "Separación entre ambos ventrículos.", "Menciónalo para ubicar cavidades."),
            ],
            "vista": "corte ventricular del corazón",
        },
        "valvulas cardiacas": {
            "definicion": "Las válvulas cardíacas son estructuras que regulan el paso de la sangre dentro del corazón y evitan el retroceso del flujo.",
            "ubicacion": "Se encuentran entre aurículas y ventrículos, y también en la salida de los ventrículos hacia el tronco pulmonar y la aorta.",
            "relaciones": "Las válvulas auriculoventriculares controlan el paso hacia los ventrículos; las válvulas semilunares controlan la salida hacia los grandes vasos.",
            "importancia": "Son importantes porque mantienen un flujo unidireccional y permiten explicar la secuencia normal de circulación intracardíaca.",
            "terminos": [
                ("Tricúspide", "Válvula entre aurícula derecha y ventrículo derecho.", "Relaciona lado derecho con circulación pulmonar."),
                ("Mitral", "Válvula entre aurícula izquierda y ventrículo izquierdo.", "Relaciona lado izquierdo con circulación sistémica."),
                ("Semilunar pulmonar", "Válvula de salida hacia el tronco pulmonar.", "Úsala para explicar salida derecha."),
                ("Semilunar aórtica", "Válvula de salida hacia la aorta.", "Úsala para explicar salida izquierda."),
            ],
            "vista": "vista superior del plano valvular cardíaco",
        },
        "pericardio": {
            "definicion": "El pericardio es la envoltura fibroserosa que rodea al corazón y contribuye a protegerlo, fijarlo y permitir su movimiento controlado.",
            "ubicacion": "Se ubica alrededor del corazón dentro del mediastino medio, formando una especie de saco que lo separa de estructuras vecinas.",
            "relaciones": "Se relaciona con el diafragma inferiormente, con el esternón anteriormente, con pulmones y pleuras lateralmente, y con grandes vasos superiormente.",
            "importancia": "Es importante porque ayuda a explicar la posición del corazón, sus medios de fijación y sus relaciones dentro del tórax.",
            "terminos": [
                ("Pericardio fibroso", "Capa externa resistente del saco pericárdico.", "Úsalo para explicar fijación."),
                ("Pericardio seroso", "Capa relacionada con la superficie cardíaca.", "Sirve para explicar deslizamiento."),
                ("Mediastino medio", "Lugar donde se encuentra el corazón y su pericardio.", "Inclúyelo en ubicación."),
                ("Diafragma", "Relación inferior del pericardio.", "Sirve como referencia anatómica."),
            ],
            "vista": "corazón cubierto por pericardio en el mediastino",
        },
        "tronco pulmonar": {
            "definicion": "El tronco pulmonar es el gran vaso arterial que sale del ventrículo derecho y conduce sangre hacia los pulmones.",
            "ubicacion": "Nace en la salida del ventrículo derecho y asciende antes de dividirse en arterias pulmonares derecha e izquierda.",
            "relaciones": "Se relaciona con la válvula pulmonar, el ventrículo derecho, la aorta ascendente y los vasos pulmonares que llevan sangre a los pulmones.",
            "importancia": "Es importante porque inicia la circulación pulmonar, donde la sangre se dirige a los pulmones para oxigenarse.",
            "terminos": [
                ("Tronco pulmonar", "Vaso que sale del ventrículo derecho.", "Úsalo para explicar salida hacia pulmones."),
                ("Arterias pulmonares", "Ramas que llevan sangre a cada pulmón.", "Relaciona bifurcación con pulmones."),
                ("Válvula pulmonar", "Regula la salida del ventrículo derecho.", "Menciónala en flujo unidireccional."),
                ("Circulación menor", "Recorrido corazón-pulmón-corazón.", "Conecta el vaso con su función."),
            ],
            "vista": "salida del ventrículo derecho hacia tronco pulmonar",
        },
        "aorta": {
            "definicion": "La aorta es la arteria principal de la circulación sistémica y nace del ventrículo izquierdo.",
            "ubicacion": "Se origina en la salida del ventrículo izquierdo, asciende, forma el arco aórtico y continúa como aorta descendente hacia el tórax y abdomen.",
            "relaciones": "Se relaciona con la válvula aórtica, el ventrículo izquierdo, el arco aórtico, ramas principales y estructuras del mediastino.",
            "importancia": "Es importante porque distribuye sangre oxigenada desde el corazón hacia todo el cuerpo, iniciando la circulación mayor.",
            "terminos": [
                ("Aorta ascendente", "Primer segmento que nace del ventrículo izquierdo.", "Úsalo para iniciar el recorrido."),
                ("Arco aórtico", "Curvatura superior de la aorta.", "Relaciona con ramas principales."),
                ("Aorta descendente", "Continuación hacia tórax y abdomen.", "Explica distribución corporal."),
                ("Circulación mayor", "Recorrido sistémico de sangre oxigenada.", "Conecta aorta con función."),
            ],
            "vista": "aorta saliendo del ventrículo izquierdo y arco aórtico",
        },
        "venas pulmonares": {
            "definicion": "Las venas pulmonares son vasos que llevan sangre oxigenada desde los pulmones hacia la aurícula izquierda.",
            "ubicacion": "Llegan a la aurícula izquierda desde ambos pulmones, generalmente como venas pulmonares derechas e izquierdas.",
            "relaciones": "Se relacionan con los hilios pulmonares, la aurícula izquierda y el retorno de sangre oxigenada después del intercambio gaseoso.",
            "importancia": "Son importantes porque completan la circulación pulmonar y llevan la sangre ya oxigenada al corazón izquierdo.",
            "terminos": [
                ("Vena pulmonar derecha", "Retorna sangre oxigenada desde el pulmón derecho.", "Úsala para explicar llegada a aurícula izquierda."),
                ("Vena pulmonar izquierda", "Retorna sangre oxigenada desde el pulmón izquierdo.", "Relaciona pulmones con corazón izquierdo."),
                ("Aurícula izquierda", "Cavidad que recibe las venas pulmonares.", "Clave para ubicar su desembocadura."),
                ("Retorno pulmonar", "Vuelta de sangre oxigenada al corazón.", "Úsalo para explicar función."),
            ],
            "vista": "venas pulmonares entrando a aurícula izquierda",
        },
        "vena cava superior": {
            "definicion": "La vena cava superior es un gran vaso venoso que lleva sangre desoxigenada desde la cabeza, cuello, miembros superiores y parte superior del tórax hacia la aurícula derecha.",
            "ubicacion": "Se ubica en el mediastino superior y desemboca en la aurícula derecha.",
            "relaciones": "Se relaciona con el retorno venoso sistémico superior, la aurícula derecha y vasos venosos que confluyen hacia ella.",
            "importancia": "Es importante porque permite comprender cómo la sangre venosa de la mitad superior del cuerpo regresa al corazón.",
            "terminos": [
                ("Vena cava superior", "Retorna sangre de la región superior del cuerpo.", "Inclúyela al hablar de aurícula derecha."),
                ("Aurícula derecha", "Cavidad donde desemboca.", "Clave para ubicación final."),
                ("Retorno venoso", "Regreso de sangre al corazón.", "Conecta vaso con función."),
                ("Mediastino superior", "Región por donde se ubica su trayecto.", "Sirve para localizarla."),
            ],
            "vista": "vena cava superior desembocando en aurícula derecha",
        },
        "vena cava inferior": {
            "definicion": "La vena cava inferior es el gran vaso venoso que lleva sangre desoxigenada desde abdomen, pelvis y miembros inferiores hacia la aurícula derecha.",
            "ubicacion": "Asciende por el abdomen, atraviesa el diafragma y llega a la aurícula derecha.",
            "relaciones": "Se relaciona con el diafragma, el retorno venoso abdominal y pélvico, y la aurícula derecha.",
            "importancia": "Es importante porque explica el retorno venoso de la mitad inferior del cuerpo hacia el corazón.",
            "terminos": [
                ("Vena cava inferior", "Retorna sangre desde la mitad inferior del cuerpo.", "Úsala para explicar retorno sistémico inferior."),
                ("Diafragma", "Estructura que atraviesa antes de llegar al tórax.", "Sirve como referencia anatómica."),
                ("Aurícula derecha", "Lugar de desembocadura.", "Clave para cerrar el recorrido."),
                ("Retorno venoso inferior", "Vuelta de sangre desde abdomen, pelvis y piernas.", "Explica función."),
            ],
            "vista": "vena cava inferior atravesando diafragma hacia aurícula derecha",
        },
        "sistema acigos": {
            "definicion": "El sistema ácigos es una red venosa del tronco que drena principalmente la pared torácica y conecta territorios venosos con la vena cava superior.",
            "ubicacion": "Se ubica en la región posterior del tórax, cerca de la columna vertebral y del mediastino posterior.",
            "relaciones": "Se relaciona con venas intercostales, columna vertebral, mediastino posterior y vena cava superior.",
            "importancia": "Es importante porque funciona como vía de drenaje y comunicación venosa dentro del tronco.",
            "terminos": [
                ("Vena ácigos", "Vena principal del sistema ácigos.", "Úsala como estructura central."),
                ("Venas intercostales", "Drenan la pared torácica.", "Relaciona con pared del tórax."),
                ("Mediastino posterior", "Región donde se ubica el sistema.", "Sirve para ubicarlo."),
                ("Vena cava superior", "Recibe drenaje del sistema ácigos.", "Conecta el sistema con retorno venoso."),
            ],
            "vista": "sistema venoso ácigos en mediastino posterior",
        },
        "circulacion menor": {
            "definicion": "La circulación menor o pulmonar es el recorrido de la sangre desde el corazón derecho hacia los pulmones y de regreso al corazón izquierdo.",
            "ubicacion": "Inicia en el ventrículo derecho, continúa por el tronco pulmonar y arterias pulmonares, pasa por los pulmones y retorna por venas pulmonares a la aurícula izquierda.",
            "relaciones": "Relaciona ventrículo derecho, tronco pulmonar, pulmones, venas pulmonares y aurícula izquierda.",
            "importancia": "Es importante porque permite oxigenar la sangre antes de que pase a la circulación sistémica.",
            "terminos": [
                ("Ventrículo derecho", "Punto de salida hacia pulmones.", "Úsalo como inicio del circuito."),
                ("Tronco pulmonar", "Conduce sangre hacia pulmones.", "Relaciona salida con arterias pulmonares."),
                ("Venas pulmonares", "Retornan sangre oxigenada.", "Cierran el circuito en aurícula izquierda."),
                ("Oxigenación", "Proceso funcional de la circulación pulmonar.", "Explica importancia."),
            ],
            "vista": "esquema corazón pulmón de circulación pulmonar",
        },
        "circulacion mayor": {
            "definicion": "La circulación mayor o sistémica es el recorrido de la sangre desde el corazón izquierdo hacia el cuerpo y su retorno al corazón derecho.",
            "ubicacion": "Inicia en el ventrículo izquierdo, continúa por la aorta y sus ramas, llega a los tejidos y retorna por venas sistémicas hacia las venas cavas y la aurícula derecha.",
            "relaciones": "Relaciona ventrículo izquierdo, aorta, ramas sistémicas, venas cavas y aurícula derecha.",
            "importancia": "Es importante porque distribuye oxígeno y nutrientes a los tejidos y permite el retorno venoso al corazón.",
            "terminos": [
                ("Ventrículo izquierdo", "Punto de salida de sangre sistémica.", "Úsalo para iniciar el recorrido."),
                ("Aorta", "Arteria principal de distribución.", "Relaciona corazón con cuerpo."),
                ("Venas cavas", "Retornan sangre a aurícula derecha.", "Cierran el circuito sistémico."),
                ("Tejidos", "Destino de la sangre oxigenada.", "Explica la función final."),
            ],
            "vista": "esquema corazón cuerpo de circulación sistémica",
        },
    }

    for clave, perfil in perfiles.items():
        if clave in k:
            base.update(perfil)
            break

    return base


def _crear_lectura_desarrollada_desde_perfil(perfil, punto_dificil=""):
    tema = perfil["tema"]
    punto = str(punto_dificil or tema).strip()
    definicion = perfil["definicion"]
    ubicacion = perfil["ubicacion"]
    relaciones = perfil["relaciones"]
    importancia = perfil["importancia"]
    terminos = perfil.get("terminos", [])[:6]

    resumen = (
        f"{definicion} {ubicacion} {relaciones} {importancia} "
        f"Para estudiar {tema}, el estudiante debe convertir estas ideas en un apunte ordenado: "
        "primero una definición clara, luego una ubicación anatómica, después relaciones y por último la importancia funcional."
    )

    lectura_profunda = [
        {
            "subtitulo": "1. Concepto central",
            "contenido": (
                f"{definicion} Este punto no debe memorizarse como una palabra aislada. "
                f"Debe entenderse como una parte específica del tema del día: {tema}. "
                "Al escribirlo, comienza con una frase directa que explique qué es y qué papel cumple dentro de la anatomía del tronco."
            ),
        },
        {
            "subtitulo": "2. Ubicación anatómica",
            "contenido": (
                f"{ubicacion} Esta ubicación debe expresarse con referencias anatómicas claras. "
                "Evita decir solamente 'está en el tórax' o 'está en el corazón'; agrega una referencia espacial o una cavidad relacionada."
            ),
        },
        {
            "subtitulo": "3. Relaciones principales",
            "contenido": (
                f"{relaciones} Las relaciones son la parte que demuestra comprensión. "
                "En examen, menciona al menos una estructura vecina, un vaso, una cavidad, una válvula o una función conectada con el subtema."
            ),
        },
        {
            "subtitulo": "4. Importancia para el examen",
            "contenido": (
                f"{importancia} Para responder mejor, cierra tu explicación conectando el subtema con el recorrido de la sangre, "
                "la organización del corazón o la relación anatómica principal que corresponda."
            ),
        },
    ]

    conceptos_clave = [
        {"termino": t, "explicacion": e, "como_usarlo": u}
        for t, e, u in terminos
    ]

    esquema_escrito = [
        {"seccion": "Definición", "desarrollo": definicion},
        {"seccion": "Ubicación", "desarrollo": ubicacion},
        {"seccion": "Relaciones", "desarrollo": relaciones},
        {"seccion": "Importancia", "desarrollo": importancia},
    ]

    cuadro_cornell = [
        {"pregunta_guia": f"¿Qué es {tema}?", "apuntes": definicion, "clave_memoria": "Definir"},
        {"pregunta_guia": f"¿Dónde se ubica {tema}?", "apuntes": ubicacion, "clave_memoria": "Ubicar"},
        {"pregunta_guia": f"¿Con qué se relaciona {tema}?", "apuntes": relaciones, "clave_memoria": "Relacionar"},
        {"pregunta_guia": "¿Por qué importa?", "apuntes": importancia, "clave_memoria": "Explicar"},
    ]

    glosario = [
        {"termino": t, "definicion": e, "relacion": u}
        for t, e, u in terminos
    ]

    respuesta_corta = f"{definicion} {ubicacion} {importancia}"
    respuesta_modelo = (
        f"{tema} debe explicarse como un contenido anatómico específico. {definicion} "
        f"Respecto a su localización, {ubicacion.lower()} "
        f"Además, {relaciones.lower()} "
        f"Su importancia se comprende porque {importancia.lower()} "
        f"Por eso, una respuesta correcta sobre {tema} no debe limitarse a nombrarlo, "
        "sino integrar definición, ubicación, relaciones y función."
    )

    return {
        "habilitado": True,
        "titulo": f"Guía desarrollada de lectura y escritura: {tema}",
        "resumen": resumen,
        "lectura_guiada": [
            f"Lee la explicación de {tema} y subraya definición, ubicación, relaciones e importancia.",
            "Copia el esquema escrito en tu cuaderno usando tus propias palabras.",
            "Convierte el cuadro Cornell en preguntas de repaso oral o escrito.",
            "Redacta la respuesta modelo sin mirar y luego compara.",
        ],
        "lectura_profunda": lectura_profunda,
        "conceptos_clave": conceptos_clave,
        "esquema_escrito": esquema_escrito,
        "cuadro_estudio": [],
        "cuadro_cornell": cuadro_cornell,
        "glosario": [],
        "glosario_detallado": glosario,
        "fichas_memoria": [
            {"anverso": f"¿Qué es {tema}?", "reverso": definicion},
            {"anverso": f"¿Dónde se ubica {tema}?", "reverso": ubicacion},
            {"anverso": f"¿Qué relación no debo olvidar?", "reverso": relaciones},
        ],
        "actividad_escritura": {
            "titulo": f"Producción escrita sobre {tema}",
            "consigna": f"Explique {tema} considerando definición, ubicación, relaciones e importancia anatómica.",
            "instrucciones": "Completa la plantilla y luego escribe una respuesta corrida de 8 a 12 líneas.",
            "plantilla": ["Definición:", "Ubicación anatómica:", "Relaciones principales:", "Importancia:", "Cierre con mis palabras:"],
            "ejemplo_respuesta": respuesta_corta,
        },
        "respuesta_modelo": respuesta_modelo,
        "respuesta_corta": respuesta_corta,
        "pregunta_tipo_examen": f"Explique {tema} considerando definición, ubicación, relaciones e importancia anatómica.",
        "puntos_memorizacion": [
            definicion[:140],
            ubicacion[:140],
            relaciones[:140],
            importancia[:140],
        ],
        "errores_comunes": [
            {"error": f"Responder {tema} solo con una palabra o lista.", "correccion": "Transforma la lista en una explicación con definición y ubicación."},
            {"error": "Olvidar la relación anatómica principal.", "correccion": "Agrega una estructura, cavidad, vaso o función relacionada."},
            {"error": "Confundir el tema padre con el subtema del día.", "correccion": f"El foco de hoy es {tema}, no todo el bloque completo."},
        ],
        "preguntas_autoverificacion": [
            f"¿Puedo definir {tema} sin mirar mis apuntes?",
            f"¿Puedo ubicar {tema} anatómicamente?",
            "¿Mencioné una relación anatómica concreta?",
            "¿Mi respuesta parece explicación de examen y no solo lista?",
        ],
        "producto_esperado": f"Apunte completo sobre {tema}: resumen, esquema, cuadro Cornell, glosario y respuesta tipo examen.",
    }


def construir_lectura_escritura_real(tema, punto_dificil=""):
    """Versión final: siempre construye lectura diferente según el subtema del día."""
    tema = str(tema or "Tema anatómico").strip()
    perfil = _perfil_anatomico_por_subtema(tema, tema_padre="", punto_dificil=punto_dificil)
    return _crear_lectura_desarrollada_desde_perfil(perfil, punto_dificil=punto_dificil)


def normalizar_lectura(valor, tema="", punto_dificil=""):
    """Fuerza Lectura/Escritura a usar contenido del subtema del día.

    Esto evita que todos los días hereden el mismo resumen del tema padre
    o el mismo texto genérico producido por el LLM.
    """
    habilitado = False
    if isinstance(valor, dict):
        habilitado = bool(valor.get("habilitado"))
    real = construir_lectura_escritura_real(tema or "Tema anatómico", punto_dificil)
    real["habilitado"] = habilitado
    return real


def _mini_quiz_desde_perfil(perfil):
    tema = perfil["tema"]
    definicion = perfil["definicion"]
    ubicacion = perfil["ubicacion"]
    relaciones = perfil["relaciones"]
    importancia = perfil["importancia"]

    return [
        {
            "pregunta": f"¿Cuál es la idea central de {tema}?",
            "opciones": [
                definicion[:120],
                "Es un repaso general sin estructura anatómica.",
                "Es solo una actividad de lectura sin contenido.",
                "Es un tema que no requiere ubicación anatómica.",
            ],
            "respuesta_correcta": definicion[:120],
            "explicacion": f"El día se centra en comprender específicamente {tema}, no en repetir el tema padre.",
        },
        {
            "pregunta": f"¿Qué debe mencionarse al ubicar {tema}?",
            "opciones": [
                ubicacion[:120],
                "Solo el nombre del tema.",
                "Únicamente una imagen sin explicación.",
                "Una definición copiada sin relaciones.",
            ],
            "respuesta_correcta": ubicacion[:120],
            "explicacion": "La ubicación anatómica permite diferenciar el subtema y responder con precisión.",
        },
        {
            "pregunta": f"¿Por qué es importante estudiar {tema}?",
            "opciones": [
                importancia[:120],
                "Porque todos los días deben tener el mismo contenido.",
                "Porque reemplaza la necesidad de practicar.",
                "Porque evita mencionar relaciones anatómicas.",
            ],
            "respuesta_correcta": importancia[:120],
            "explicacion": "La importancia conecta el subtema con función, recorrido, relación anatómica o examen.",
        },
    ]


def _aplicar_contenido_diferente_a_dia(dia, datos_academicos=None):
    if not isinstance(dia, dict):
        return dia

    tema = str(dia.get("tema_principal") or dia.get("subtema_dia") or "").strip()
    if not tema and datos_academicos is not None:
        tema = str(getattr(datos_academicos, "tema_actual", "") or "Anatomía I").strip()

    tema_padre = str(
        dia.get("tema_padre")
        or (getattr(datos_academicos, "tema_actual", "") if datos_academicos is not None else "")
        or "Anatomía I"
    ).strip()

    punto = str(dia.get("punto_refuerzo") or dia.get("subtema_dia") or tema).strip()
    numero = int(dia.get("dia") or 1)
    perfil = _perfil_anatomico_por_subtema(tema, tema_padre=tema_padre, punto_dificil=punto)
    lectura = _crear_lectura_desarrollada_desde_perfil(perfil, punto_dificil=punto)

    recursos = dia.get("recursos") if isinstance(dia.get("recursos"), dict) else {}
    audio = recursos.get("audio") if isinstance(recursos.get("audio"), dict) else {}
    visual = recursos.get("visual") if isinstance(recursos.get("visual"), dict) else {}
    kin = recursos.get("kinestesico") if isinstance(recursos.get("kinestesico"), dict) else {}
    imagen = recursos.get("imagen_anatomica") if isinstance(recursos.get("imagen_anatomica"), dict) else {}

    dia["titulo"] = f"Día {numero}: {tema}"
    dia["tema_principal"] = tema
    dia["tema_padre"] = tema_padre
    dia["subtema_dia"] = tema
    dia["objetivo"] = (
        f"Comprender {tema} dentro de {tema_padre}, explicando definición, ubicación, "
        "relaciones anatómicas e importancia para el examen."
    )
    dia["actividades"] = [
        f"Leer la explicación específica de {tema} y subrayar definición, ubicación y relaciones.",
        f"Completar un cuadro Cornell solo sobre {tema}, sin repetir todo {tema_padre}.",
        f"Dibujar o revisar una lámina de {tema} y marcar la estructura o relación principal.",
        f"Responder una pregunta tipo examen sobre {tema} con tus propias palabras.",
    ]
    dia["autoevaluacion"] = [
        f"¿Puedo definir {tema} sin mirar?",
        f"¿Puedo ubicar {tema} dentro de {tema_padre}?",
        "¿Incluí una relación anatómica concreta?",
        "¿Mi respuesta del día es diferente a la de los otros días?",
    ]
    dia["producto_esperado"] = f"Apunte desarrollado y respuesta tipo examen sobre {tema}."
    dia["mini_quiz"] = _mini_quiz_desde_perfil(perfil)

    recursos["audio"] = {
        "habilitado": bool(audio.get("habilitado")),
        "titulo": f"Audio del día {numero}: {tema}",
        "guion": (
            f"Hoy el foco es {tema}, no todo el bloque de {tema_padre}. "
            f"Primero recuerda esta idea: {perfil['definicion']} "
            f"Luego ubícalo: {perfil['ubicacion']} "
            f"Finalmente conéctalo: {perfil['relaciones']} "
            "Si puedes explicarlo en ese orden, ya tienes una respuesta de examen clara."
        ),
        "pasos_clave": [
            f"Definir {tema}.",
            f"Ubicar {tema} anatómicamente.",
            "Mencionar una relación o función importante.",
        ],
    }

    recursos["visual"] = mejorar_visual_para_mapa_html({
        "habilitado": bool(visual.get("habilitado")),
        "titulo": f"Mapa mental de {tema}",
        "tipo": "mapa_mental_html_premium",
        "descripcion": f"Mapa del día centrado únicamente en {tema}.",
        "nodo_central": tema,
        "ramas": [
            {"titulo": "Definición", "detalle": perfil["definicion"], "subpuntos": ["Qué es", "Papel principal"]},
            {"titulo": "Ubicación", "detalle": perfil["ubicacion"], "subpuntos": ["Región", "Referencia anatómica"]},
            {"titulo": "Relaciones", "detalle": perfil["relaciones"], "subpuntos": ["Estructuras vecinas", "Conexiones"]},
            {"titulo": "Importancia", "detalle": perfil["importancia"], "subpuntos": ["Función", "Examen"]},
        ],
        "apoyo_visual": [tema, "Ubicación", "Relaciones", "Importancia"],
    }, tema)

    recursos["kinestesico"] = {
        "habilitado": bool(kin.get("habilitado")),
        "titulo": f"Práctica activa: {tema}",
        "instrucciones": (
            f"En una hoja, escribe {tema} al centro. Alrededor coloca cuatro recuadros: definición, ubicación, relaciones e importancia. "
            "Después intenta explicar el esquema sin leer la respuesta modelo."
        ),
        "preguntas": [
            f"¿Qué estructura o idea representa mejor {tema}?",
            f"¿Dónde ubicarías {tema} en una lámina anatómica?",
            f"¿Qué relación anatómica usarías para defender tu respuesta?",
        ],
    }

    lectura["habilitado"] = bool((recursos.get("lectura") or {}).get("habilitado", True))
    recursos["lectura"] = lectura

    recursos["imagen_anatomica"] = {
        "habilitado": bool(imagen.get("habilitado")),
        "titulo": f"Lámina anatómica guiada de {tema}",
        "tipo_vista": perfil.get("vista", "vista anatómica didáctica"),
        "descripcion": (
            f"Lámina centrada en {tema}. Debe ayudar a reconocer ubicación, relaciones e importancia dentro de {tema_padre}."
        ),
        "marcadores": imagen.get("marcadores", []),
        "preguntas": [
            f"¿Dónde se identifica {tema}?",
            f"¿Qué relación anatómica se observa o se debe recordar?",
            "¿Cómo lo escribirías en una respuesta de examen?",
        ],
        "preguntas_guiadas": [],
        "modo_practica": "Observa la lámina, responde primero sin ayuda y luego compara con la lectura desarrollada.",
        "prompt_imagen": imagen.get("prompt_imagen", ""),
        "negative_prompt": imagen.get("negative_prompt", ""),
        "categoria_visual": imagen.get("categoria_visual", ""),
        "image_url": imagen.get("image_url", ""),
        "image_error": imagen.get("image_error", ""),
    }

    dia["recursos"] = recursos
    return dia


def aplicar_variacion_contenido_diario(respuesta, datos_academicos=None):
    """Aplica contenido distinto a cada día ya validado por la ruta."""
    if not isinstance(respuesta, dict):
        return respuesta

    plan = respuesta.get("plan_diario", [])
    if not isinstance(plan, list):
        return respuesta

    respuesta["plan_diario"] = [
        _aplicar_contenido_diferente_a_dia(dia, datos_academicos=datos_academicos)
        for dia in plan
        if isinstance(dia, dict)
    ]

    temas = [
        str(d.get("tema_principal", "")).strip()
        for d in respuesta["plan_diario"]
        if str(d.get("tema_principal", "")).strip()
    ]
    if temas:
        respuesta["temas_priorizados"] = temas[:8]

    return respuesta


def generar_ruta_aprendizaje(user, perfil_vark, datos_academicos, materiales):
    """Versión final de la ruta.

    Mantiene tu flujo actual, pero antes de guardar fuerza contenido distinto
    para cada día usando el subtema de agenda.
    """
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

    # Esta es la parte importante: aunque el LLM devuelva contenido repetido,
    # se reemplaza el contenido interno por material propio del subtema del día.
    respuesta = aplicar_variacion_contenido_diario(respuesta, datos_academicos=datos_academicos)

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
