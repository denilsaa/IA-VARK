import json
import os

from django.utils.text import Truncator

from .models import ExamenGenerado


MAX_CARACTERES_CONTEXTO_EXAMEN = 30000


def generar_examen_personalizado(
    user,
    perfil_vark,
    datos_academicos,
    ruta,
    materiales,
    cantidad_preguntas=10,
    dificultad=ExamenGenerado.DIFICULTAD_MEDIA,
):
    cantidad_preguntas = normalizar_cantidad_preguntas(cantidad_preguntas)

    respuesta = generar_examen_con_gemini(
        perfil_vark=perfil_vark,
        datos_academicos=datos_academicos,
        ruta=ruta,
        materiales=materiales,
        cantidad_preguntas=cantidad_preguntas,
        dificultad=dificultad,
    )

    if not respuesta:
        respuesta = generar_examen_respaldo(
            ruta=ruta,
            datos_academicos=datos_academicos,
            cantidad_preguntas=cantidad_preguntas,
        )

    examen = ExamenGenerado.objects.create(
        user=user,
        ruta=ruta,
        titulo=respuesta.get("titulo", "Simulacro de Anatomía I"),
        instrucciones=respuesta.get(
            "instrucciones",
            "Responde cada pregunta seleccionando una alternativa.",
        ),
        dificultad=dificultad,
        cantidad_preguntas=cantidad_preguntas,
        preguntas_json=respuesta.get("preguntas", []),
        estado=ExamenGenerado.ESTADO_GENERADO,
    )

    return examen


def generar_examen_con_gemini(
    perfil_vark,
    datos_academicos,
    ruta,
    materiales,
    cantidad_preguntas,
    dificultad,
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

        contexto = construir_contexto_examen(
            ruta=ruta,
            materiales=materiales,
        )

        prompt = f"""
Genera un examen tipo simulacro para Anatomía I.

Libro base y dataset interno:
- Libro base: Rouvière y Delmas, Anatomía Humana descriptiva, topográfica y funcional. Tomo 2: Tronco.
- El tema actual y el punto difícil fueron seleccionados desde un dataset interno basado en el índice del libro.
- El examen debe centrarse en ese tema y en ese punto específico.

Datos del estudiante:
- Estilo VARK: {perfil_vark.estilo_display}
- Materia: {datos_academicos.materia}
- Tema actual: {datos_academicos.tema_actual}
- Tipo de examen real: {datos_academicos.get_tipo_examen_display()}
- Punto específico que le cuesta más: {datos_academicos.temas_dificiles or "No especificado"}
- Objetivo de estudio: {datos_academicos.objetivo_estudio or "No especificado"}

Ruta de aprendizaje:
- Título: {ruta.titulo}
- Resumen: {ruta.resumen_general}
- Temas priorizados:
{ruta.temas_priorizados}

Contexto del material analizado:
Usa únicamente este contexto y la ruta de aprendizaje. Si falta información, no inventes datos anatómicos.
\"\"\"
{contexto}
\"\"\"

Configura el examen así:
- Cantidad exacta de preguntas: {cantidad_preguntas}
- Dificultad: {dificultad}
- Formato: opción múltiple con 4 alternativas A, B, C y D.
- Enfócate en el temario y en los materiales analizados.

Devuelve únicamente JSON válido con esta estructura exacta:

{{
  "titulo": "Título del examen",
  "instrucciones": "Instrucciones breves para el estudiante.",
  "preguntas": [
    {{
      "id": 1,
      "tema": "Tema evaluado",
      "enunciado": "Pregunta aquí",
      "opciones": [
        {{"letra": "A", "texto": "Opción A"}},
        {{"letra": "B", "texto": "Opción B"}},
        {{"letra": "C", "texto": "Opción C"}},
        {{"letra": "D", "texto": "Opción D"}}
      ],
      "respuesta_correcta": "A",
      "explicacion": "Explicación breve de por qué esa respuesta es correcta."
    }}
  ]
}}

Reglas obligatorias:
- Escribe en español.
- No uses markdown.
- No agregues texto fuera del JSON.
- Cada pregunta debe tener exactamente 4 opciones.
- La respuesta correcta debe ser solo una letra: A, B, C o D.
- No repitas preguntas.
- No hagas preguntas demasiado obvias.
- No inventes datos fuera del material o del temario.
- Evalúa comprensión anatómica, relaciones topográficas, ubicación y función.
"""

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.45,
            ),
        )

        contenido = limpiar_json(response.text)
        data = json.loads(contenido)

        return validar_examen(data, cantidad_preguntas)

    except Exception as error:
        print("Error generando examen con Gemini:", error)
        return {}


def construir_contexto_examen(ruta, materiales):
    partes = []

    partes.append("RESUMEN DE LA RUTA:")
    partes.append(ruta.resumen_general or "")

    partes.append("TEMAS PRIORIZADOS:")
    partes.append(ruta.temas_priorizados or "")

    partes.append("PLAN DIARIO:")
    for dia in ruta.plan_diario:
        partes.append(f"Día {dia.get('dia')}: {dia.get('tema_principal')}")
        partes.append(f"Objetivo: {dia.get('objetivo')}")
        partes.append("Actividades:")
        partes.extend(dia.get("actividades", []))
        partes.append("---")

    for material in materiales:
        partes.append(f"MATERIAL: {material.titulo}")
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

        if material.texto_extraido:
            partes.append("Texto extraído parcial:")
            partes.append(Truncator(material.texto_extraido).chars(6000))

        partes.append("===")

    contexto = "\n".join(partes)

    return Truncator(contexto).chars(MAX_CARACTERES_CONTEXTO_EXAMEN)


def validar_examen(data, cantidad_preguntas):
    if not isinstance(data, dict):
        return {}

    preguntas = data.get("preguntas", [])

    if not isinstance(preguntas, list):
        return {}

    preguntas_limpias = []

    for index, pregunta in enumerate(preguntas[:cantidad_preguntas], start=1):
        if not isinstance(pregunta, dict):
            continue

        opciones = pregunta.get("opciones", [])

        if not isinstance(opciones, list):
            continue

        opciones_limpias = []
        letras_encontradas = set()

        for opcion in opciones:
            if not isinstance(opcion, dict):
                continue

            letra = str(opcion.get("letra", "")).strip().upper()
            texto = str(opcion.get("texto", "")).strip()

            if letra not in ["A", "B", "C", "D"]:
                continue

            if letra in letras_encontradas:
                continue

            if not texto:
                continue

            letras_encontradas.add(letra)
            opciones_limpias.append(
                {
                    "letra": letra,
                    "texto": texto,
                }
            )

        respuesta_correcta = str(
            pregunta.get("respuesta_correcta", "")
        ).strip().upper()

        if set(letras_encontradas) != {"A", "B", "C", "D"}:
            continue

        if respuesta_correcta not in letras_encontradas:
            continue

        preguntas_limpias.append(
            {
                "id": index,
                "tema": str(pregunta.get("tema", "")).strip(),
                "enunciado": str(pregunta.get("enunciado", "")).strip(),
                "opciones": sorted(opciones_limpias, key=lambda item: item["letra"]),
                "respuesta_correcta": respuesta_correcta,
                "explicacion": str(pregunta.get("explicacion", "")).strip(),
            }
        )

    if len(preguntas_limpias) < 3:
        return {}

    return {
        "titulo": str(data.get("titulo", "Simulacro de Anatomía I")).strip(),
        "instrucciones": str(
            data.get(
                "instrucciones",
                "Selecciona la respuesta correcta para cada pregunta.",
            )
        ).strip(),
        "preguntas": preguntas_limpias,
    }


def calificar_examen(examen, respuestas_usuario):
    preguntas = examen.preguntas
    respuestas_json = {}
    puntaje = 0

    for pregunta in preguntas:
        pregunta_id = str(pregunta.get("id"))
        respuesta_usuario = str(
            respuestas_usuario.get(pregunta_id, "")
        ).strip().upper()

        respuesta_correcta = str(
            pregunta.get("respuesta_correcta", "")
        ).strip().upper()

        es_correcta = respuesta_usuario == respuesta_correcta

        if es_correcta:
            puntaje += 1

        respuestas_json[pregunta_id] = {
            "respuesta_usuario": respuesta_usuario,
            "respuesta_correcta": respuesta_correcta,
            "es_correcta": es_correcta,
        }

    total = len(preguntas)

    if total > 0:
        porcentaje = round((puntaje / total) * 100, 2)
    else:
        porcentaje = 0

    examen.puntaje = puntaje
    examen.porcentaje = porcentaje
    examen.respuestas_json = respuestas_json
    examen.estado = ExamenGenerado.ESTADO_RESPONDIDO

    retroalimentacion = generar_retroalimentacion_con_gemini(examen)

    if retroalimentacion:
        examen.retroalimentacion_ia = retroalimentacion
    else:
        examen.retroalimentacion_ia = generar_retroalimentacion_respaldo(
            puntaje=puntaje,
            total=total,
            porcentaje=porcentaje,
        )

    examen.save(
        update_fields=[
            "puntaje",
            "porcentaje",
            "respuestas_json",
            "estado",
            "retroalimentacion_ia",
            "actualizado",
        ]
    )

    return examen


def generar_retroalimentacion_con_gemini(examen):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        return ""

    if os.getenv("LLM_PROVIDER", "gemini").strip().lower() != "gemini":
        return ""

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()

        resumen_resultados = []

        for resultado in examen.resultados:
            resumen_resultados.append(
                {
                    "tema": resultado["tema"],
                    "enunciado": resultado["enunciado"],
                    "respuesta_usuario": resultado["respuesta_usuario"],
                    "respuesta_correcta": resultado["respuesta_correcta"],
                    "es_correcta": resultado["es_correcta"],
                    "explicacion": resultado["explicacion"],
                }
            )

        prompt = f"""
Genera retroalimentación breve para un estudiante de Anatomía I.

Resultado:
- Puntaje: {examen.puntaje}/{examen.total_preguntas}
- Porcentaje: {examen.porcentaje}%

Preguntas y resultados:
{json.dumps(resumen_resultados, ensure_ascii=False)}

Instrucciones:
- Escribe en español.
- Máximo 160 palabras.
- Identifica fortalezas y debilidades.
- Recomienda cómo repasar.
- No uses markdown.
"""

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,
            ),
        )

        return response.text.strip()

    except Exception as error:
        print("Error generando retroalimentación con Gemini:", error)
        return ""


def generar_examen_respaldo(ruta, datos_academicos, cantidad_preguntas):
    temas = ruta.temas_priorizados_lista

    if not temas:
        temas = [
            datos_academicos.tema_actual,
            "Órganos del abdomen",
            "Pelvis menor",
            "Periné",
        ]

    preguntas = []

    for index in range(1, cantidad_preguntas + 1):
        tema = temas[(index - 1) % len(temas)]

        preguntas.append(
            {
                "id": index,
                "tema": tema,
                "enunciado": f"¿Cuál de las siguientes opciones se relaciona mejor con el tema: {tema}?",
                "opciones": [
                    {
                        "letra": "A",
                        "texto": "Una estructura, relación o función anatómica del tema estudiado.",
                    },
                    {
                        "letra": "B",
                        "texto": "Un concepto no relacionado con la anatomía del tronco.",
                    },
                    {
                        "letra": "C",
                        "texto": "Una descripción sin relación topográfica.",
                    },
                    {
                        "letra": "D",
                        "texto": "Una afirmación general sin utilidad anatómica.",
                    },
                ],
                "respuesta_correcta": "A",
                "explicacion": "La opción A es la más relacionada con el tema anatómico indicado.",
            }
        )

    return {
        "titulo": "Simulacro de Anatomía I",
        "instrucciones": "Selecciona la alternativa correcta para cada pregunta.",
        "preguntas": preguntas,
    }


def generar_retroalimentacion_respaldo(puntaje, total, porcentaje):
    if porcentaje >= 80:
        return (
            "Buen resultado. Mantén el ritmo de estudio y usa los errores como repaso fino. "
            "Refuerza los temas donde dudaste y realiza otro simulacro antes del examen."
        )

    if porcentaje >= 50:
        return (
            "Resultado intermedio. Hay una base de comprensión, pero necesitas repasar los temas "
            "fallados con más detalle. Revisa explicaciones, resume conceptos clave y repite el simulacro."
        )

    return (
        "Resultado bajo. Conviene volver a estudiar los temas principales desde la ruta de aprendizaje, "
        "hacer resúmenes breves y practicar con preguntas por tema antes de intentar otro simulacro."
    )


def normalizar_cantidad_preguntas(cantidad):
    try:
        cantidad = int(cantidad)
    except (TypeError, ValueError):
        cantidad = 10

    if cantidad < 5:
        return 5

    if cantidad > 20:
        return 20

    return cantidad


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
# FASE 5: Simulacros con mejor retroalimentación y evaluación más útil
# =========================================================

def generar_examen_con_gemini(
    perfil_vark,
    datos_academicos,
    ruta,
    materiales,
    cantidad_preguntas,
    dificultad,
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

        contexto = construir_contexto_examen(
            ruta=ruta,
            materiales=materiales,
        )

        prompt = f"""
Genera un simulacro de Anatomía I orientado a retroalimentación y mejora del aprendizaje.

Contexto académico:
- Libro base: Rouvière y Delmas, Anatomía Humana descriptiva, topográfica y funcional. Tomo 2: Tronco.
- Materia: {datos_academicos.materia}
- Tema actual: {datos_academicos.tema_actual}
- Punto específico difícil: {datos_academicos.temas_dificiles or "No especificado"}
- Tipo de examen real: {datos_academicos.get_tipo_examen_display()}
- Objetivo de estudio: {datos_academicos.objetivo_estudio or "No especificado"}

Personalización:
- Estilo VARK: {perfil_vark.estilo_display}
- Ruta generada: {ruta.titulo}
- Temas priorizados: {ruta.temas_priorizados}

Contexto disponible de ruta y materiales:
\"\"\"
{contexto}
\"\"\"

Configuración del simulacro:
- Cantidad exacta de preguntas: {cantidad_preguntas}
- Dificultad solicitada: {dificultad}
- Formato: opción múltiple con 4 alternativas A, B, C y D.

Devuelve únicamente JSON válido con esta estructura exacta:
{{
  "titulo": "Simulacro de Anatomía I - tema específico",
  "instrucciones": "Instrucciones breves y claras para el estudiante.",
  "preguntas": [
    {{
      "id": 1,
      "tema": "Tema evaluado",
      "habilidad_evaluada": "Ubicación anatómica / relación topográfica / función / identificación / aplicación clínica básica",
      "dificultad_cognitiva": "Recordar / Comprender / Aplicar / Analizar",
      "enunciado": "Pregunta clara y evaluable",
      "opciones": [
        {{"letra": "A", "texto": "Opción A"}},
        {{"letra": "B", "texto": "Opción B"}},
        {{"letra": "C", "texto": "Opción C"}},
        {{"letra": "D", "texto": "Opción D"}}
      ],
      "respuesta_correcta": "A",
      "explicacion": "Explicación didáctica de por qué la alternativa correcta es correcta.",
      "retroalimentacion_error": "Qué debería repasar el estudiante si falló esta pregunta.",
      "pista_estudio": "Consejo breve para estudiar este punto.",
      "repaso_recomendado": "Tema, recurso o actividad que debería revisar después."
    }}
  ]
}}

Reglas obligatorias:
- Escribe en español.
- No uses markdown.
- No agregues texto fuera del JSON.
- Cada pregunta debe tener exactamente 4 opciones.
- La respuesta correcta debe ser solo una letra: A, B, C o D.
- No repitas preguntas ni cambies el formato.
- No hagas preguntas demasiado obvias.
- No inventes datos fuera del contexto disponible.
- Mezcla tipos de pregunta: ubicación, relación topográfica, función, identificación y aplicación básica.
- Para dificultad baja: preguntas directas de ubicación y concepto.
- Para dificultad media: preguntas de relación anatómica y comparación.
- Para dificultad alta: preguntas de aplicación, relación topográfica y razonamiento.
- Cada explicación debe enseñar, no solo decir la respuesta.
"""

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.38,
            ),
        )

        contenido = limpiar_json(response.text)
        data = json.loads(contenido)

        return validar_examen(data, cantidad_preguntas)

    except Exception as error:
        print("Error generando examen con Gemini:", error)
        return {}


def validar_examen(data, cantidad_preguntas):
    if not isinstance(data, dict):
        return {}

    preguntas = data.get("preguntas", [])

    if not isinstance(preguntas, list):
        return {}

    preguntas_limpias = []

    for index, pregunta in enumerate(preguntas[:cantidad_preguntas], start=1):
        if not isinstance(pregunta, dict):
            continue

        opciones = pregunta.get("opciones", [])

        if not isinstance(opciones, list):
            continue

        opciones_limpias = []
        letras_encontradas = set()

        for opcion in opciones:
            if not isinstance(opcion, dict):
                continue

            letra = str(opcion.get("letra", "")).strip().upper()
            texto = str(opcion.get("texto", "")).strip()

            if letra not in ["A", "B", "C", "D"]:
                continue

            if letra in letras_encontradas:
                continue

            if not texto:
                continue

            letras_encontradas.add(letra)
            opciones_limpias.append({"letra": letra, "texto": texto})

        respuesta_correcta = str(pregunta.get("respuesta_correcta", "")).strip().upper()

        if set(letras_encontradas) != {"A", "B", "C", "D"}:
            continue

        if respuesta_correcta not in letras_encontradas:
            continue

        tema = str(pregunta.get("tema", "")).strip() or "Anatomía I"
        explicacion = str(pregunta.get("explicacion", "")).strip()
        if not explicacion:
            explicacion = "Revisa la relación anatómica evaluada y contrasta cada alternativa con el tema del día."

        preguntas_limpias.append(
            {
                "id": index,
                "tema": tema,
                "habilidad_evaluada": str(pregunta.get("habilidad_evaluada", "Comprensión anatómica")).strip(),
                "dificultad_cognitiva": str(pregunta.get("dificultad_cognitiva", "Comprender")).strip(),
                "enunciado": str(pregunta.get("enunciado", "")).strip(),
                "opciones": sorted(opciones_limpias, key=lambda item: item["letra"]),
                "respuesta_correcta": respuesta_correcta,
                "explicacion": explicacion,
                "retroalimentacion_error": str(
                    pregunta.get(
                        "retroalimentacion_error",
                        "Repasa el tema y vuelve a responder una pregunta similar antes de avanzar.",
                    )
                ).strip(),
                "pista_estudio": str(
                    pregunta.get(
                        "pista_estudio",
                        "Estudia el concepto con un esquema breve y una pregunta de autoevaluación.",
                    )
                ).strip(),
                "repaso_recomendado": str(
                    pregunta.get(
                        "repaso_recomendado",
                        f"Revisar {tema} en la ruta de aprendizaje.",
                    )
                ).strip(),
            }
        )

    if len(preguntas_limpias) < 3:
        return {}

    return {
        "titulo": str(data.get("titulo", "Simulacro de Anatomía I")).strip(),
        "instrucciones": str(
            data.get(
                "instrucciones",
                "Responde cada pregunta. Al finalizar recibirás puntaje, explicación y temas a reforzar.",
            )
        ).strip(),
        "preguntas": preguntas_limpias,
    }


def generar_examen_respaldo(ruta, datos_academicos, cantidad_preguntas):
    temas = ruta.temas_priorizados_lista

    if not temas:
        temas = [
            datos_academicos.tema_actual or "Anatomía del tronco",
            datos_academicos.temas_dificiles or "Relaciones anatómicas",
            "Ubicación anatómica",
            "Función y relaciones topográficas",
        ]

    bancos = [
        {
            "habilidad": "Ubicación anatómica",
            "nivel": "Comprender",
            "enunciado": "¿Qué aspecto deberías identificar primero para estudiar correctamente {tema}?",
            "correcta": "La ubicación y las relaciones anatómicas principales del tema.",
            "distractores": [
                "Solo el nombre del tema sin relacionarlo con estructuras vecinas.",
                "Un dato aislado que no permita ubicar la estructura.",
                "Una definición general sin aplicación anatómica.",
            ],
        },
        {
            "habilidad": "Relación topográfica",
            "nivel": "Aplicar",
            "enunciado": "Al repasar {tema}, ¿qué estrategia ayuda más a comprender relaciones topográficas?",
            "correcta": "Comparar qué estructuras se ubican anterior, posterior, medial o lateral.",
            "distractores": [
                "Memorizar solo palabras sin ubicar estructuras.",
                "Ignorar los límites anatómicos de la región.",
                "Estudiar el tema sin relacionarlo con el punto difícil.",
            ],
        },
        {
            "habilidad": "Aplicación básica",
            "nivel": "Analizar",
            "enunciado": "Si tienes dificultad con {tema}, ¿qué acción sería más útil antes del examen?",
            "correcta": "Resolver preguntas y revisar la explicación de los errores cometidos.",
            "distractores": [
                "Pasar al siguiente tema sin revisar fallos.",
                "Leer una sola vez sin autoevaluación.",
                "Repetir definiciones sin identificar relaciones.",
            ],
        },
    ]

    preguntas = []

    for index in range(1, cantidad_preguntas + 1):
        tema = temas[(index - 1) % len(temas)]
        plantilla = bancos[(index - 1) % len(bancos)]
        opciones = [
            {"letra": "A", "texto": plantilla["correcta"]},
            {"letra": "B", "texto": plantilla["distractores"][0]},
            {"letra": "C", "texto": plantilla["distractores"][1]},
            {"letra": "D", "texto": plantilla["distractores"][2]},
        ]
        preguntas.append(
            {
                "id": index,
                "tema": tema,
                "habilidad_evaluada": plantilla["habilidad"],
                "dificultad_cognitiva": plantilla["nivel"],
                "enunciado": plantilla["enunciado"].format(tema=tema),
                "opciones": opciones,
                "respuesta_correcta": "A",
                "explicacion": f"La alternativa A es correcta porque permite estudiar {tema} relacionando ubicación, función y estructuras vecinas.",
                "retroalimentacion_error": f"Repasa {tema} desde la ruta de aprendizaje y vuelve a responder una pregunta similar.",
                "pista_estudio": "Usa mapa mental, lámina anatómica y una pregunta oral para verificar comprensión.",
                "repaso_recomendado": f"Revisar el recurso diario relacionado con {tema}.",
            }
        )

    return {
        "titulo": "Simulacro de Anatomía I",
        "instrucciones": "Responde todas las preguntas. Al finalizar verás explicación, temas fuertes y temas a reforzar.",
        "preguntas": preguntas,
    }


def generar_retroalimentacion_con_gemini(examen):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        return ""

    if os.getenv("LLM_PROVIDER", "gemini").strip().lower() != "gemini":
        return ""

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()

        resumen_resultados = []
        for resultado in examen.resultados:
            resumen_resultados.append(
                {
                    "tema": resultado["tema"],
                    "habilidad": resultado.get("habilidad_evaluada", ""),
                    "respuesta_usuario": resultado["respuesta_usuario"],
                    "respuesta_correcta": resultado["respuesta_correcta"],
                    "es_correcta": resultado["es_correcta"],
                    "repaso": resultado.get("repaso_recomendado", ""),
                }
            )

        prompt = f"""
Genera retroalimentación útil y accionable para un estudiante de Anatomía I.

Resultado:
- Puntaje: {examen.puntaje}/{examen.total_preguntas}
- Porcentaje: {examen.porcentaje}%

Resultados por pregunta:
{json.dumps(resumen_resultados, ensure_ascii=False)}

Instrucciones:
- Escribe en español.
- Máximo 190 palabras.
- Divide la respuesta en un solo párrafo claro.
- Menciona fortalezas, temas a reforzar y siguiente acción.
- Sé concreto: qué debe repasar y cómo hacerlo.
- No uses markdown ni viñetas.
"""

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.45),
        )

        return response.text.strip()

    except Exception as error:
        print("Error generando retroalimentación con Gemini:", error)
        return ""


def generar_retroalimentacion_respaldo(puntaje, total, porcentaje):
    if porcentaje >= 85:
        return (
            "Tu resultado muestra dominio alto. Mantén el ritmo, revisa las explicaciones de las preguntas falladas y genera un simulacro de dificultad alta para confirmar que puedes aplicar el conocimiento en relaciones anatómicas y ubicación topográfica."
        )

    if porcentaje >= 60:
        return (
            "Tu resultado muestra dominio medio. Tienes una base útil, pero necesitas reforzar los temas donde fallaste. Revisa la ruta de aprendizaje, observa la lámina anatómica, convierte cada error en una pregunta y repite un simulacro corto."
        )

    return (
        "Tu resultado indica que conviene reforzar antes de avanzar. Revisa los temas base desde la ruta, estudia con mapas mentales o resúmenes, practica identificación de estructuras y luego realiza un simulacro de menor cantidad de preguntas."
    )
