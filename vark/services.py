import json
import os
import random


ESTILOS_VALIDOS = ["visual", "auditivo", "lectura", "kinestesico"]


PREGUNTAS_RESPALDO = [
    {
        "id": 1,
        "texto": "Cuando necesitas aprender algo nuevo, ¿qué te ayuda más?",
        "opciones": [
            {"valor": "visual", "texto": "Ver imágenes, esquemas, mapas o gráficos."},
            {"valor": "auditivo", "texto": "Escuchar una explicación o hablar con alguien sobre el tema."},
            {"valor": "lectura", "texto": "Leer instrucciones, apuntes o resúmenes escritos."},
            {"valor": "kinestesico", "texto": "Practicar directamente o hacer una actividad relacionada."},
        ],
    },
    {
        "id": 2,
        "texto": "Si tienes que llegar a un lugar desconocido, prefieres:",
        "opciones": [
            {"valor": "visual", "texto": "Ver un mapa o una imagen de la ruta."},
            {"valor": "auditivo", "texto": "Que alguien te explique verbalmente cómo llegar."},
            {"valor": "lectura", "texto": "Leer instrucciones paso a paso."},
            {"valor": "kinestesico", "texto": "Ir probando el camino mientras avanzas."},
        ],
    },
    {
        "id": 3,
        "texto": "Cuando compras un aparato nuevo y quieres usarlo, normalmente:",
        "opciones": [
            {"valor": "visual", "texto": "Miras dibujos, diagramas o videos demostrativos."},
            {"valor": "auditivo", "texto": "Pides que alguien te explique cómo funciona."},
            {"valor": "lectura", "texto": "Lees el manual o las instrucciones."},
            {"valor": "kinestesico", "texto": "Empiezas a probarlo hasta entenderlo."},
        ],
    },
    {
        "id": 4,
        "texto": "Si tienes que recordar una información importante, te resulta más fácil:",
        "opciones": [
            {"valor": "visual", "texto": "Recordar cómo se veía: colores, ubicación o imagen."},
            {"valor": "auditivo", "texto": "Recordar lo que escuchaste o repetiste en voz alta."},
            {"valor": "lectura", "texto": "Recordar lo que leíste o escribiste."},
            {"valor": "kinestesico", "texto": "Recordar lo que hiciste o practicaste."},
        ],
    },
    {
        "id": 5,
        "texto": "Cuando estudias para una evaluación, prefieres:",
        "opciones": [
            {"valor": "visual", "texto": "Usar mapas conceptuales, colores, cuadros o dibujos."},
            {"valor": "auditivo", "texto": "Explicar el tema en voz alta o escuchar explicaciones."},
            {"valor": "lectura", "texto": "Leer, subrayar y escribir resúmenes."},
            {"valor": "kinestesico", "texto": "Resolver ejercicios, practicar o hacer simulacros."},
        ],
    },
    {
        "id": 6,
        "texto": "Cuando alguien te da una explicación complicada, entiendes mejor si:",
        "opciones": [
            {"valor": "visual", "texto": "Te muestra un dibujo, esquema o ejemplo visual."},
            {"valor": "auditivo", "texto": "Te lo explica hablando con calma."},
            {"valor": "lectura", "texto": "Te da una explicación escrita para leerla."},
            {"valor": "kinestesico", "texto": "Te deja intentarlo o practicarlo tú mismo."},
        ],
    },
    {
        "id": 7,
        "texto": "Si tienes que preparar una presentación, primero prefieres:",
        "opciones": [
            {"valor": "visual", "texto": "Diseñar diapositivas, imágenes o una estructura visual."},
            {"valor": "auditivo", "texto": "Ensayar lo que vas a decir en voz alta."},
            {"valor": "lectura", "texto": "Escribir el contenido completo o un guion."},
            {"valor": "kinestesico", "texto": "Practicar la presentación como si ya estuvieras exponiendo."},
        ],
    },
    {
        "id": 8,
        "texto": "Cuando aprendes una receta nueva, prefieres:",
        "opciones": [
            {"valor": "visual", "texto": "Ver fotos o videos del proceso."},
            {"valor": "auditivo", "texto": "Que alguien te explique los pasos verbalmente."},
            {"valor": "lectura", "texto": "Leer la receta escrita paso a paso."},
            {"valor": "kinestesico", "texto": "Prepararla tú mismo mientras aprendes."},
        ],
    },
    {
        "id": 9,
        "texto": "Cuando trabajas en grupo, aprendes mejor si:",
        "opciones": [
            {"valor": "visual", "texto": "Usan una pizarra, gráficos o esquemas."},
            {"valor": "auditivo", "texto": "Conversan y explican las ideas entre todos."},
            {"valor": "lectura", "texto": "Comparten apuntes, documentos o listas."},
            {"valor": "kinestesico", "texto": "Hacen una actividad práctica o resuelven problemas juntos."},
        ],
    },
    {
        "id": 10,
        "texto": "Cuando cometes un error, te ayuda más:",
        "opciones": [
            {"valor": "visual", "texto": "Ver marcado dónde estuvo el error."},
            {"valor": "auditivo", "texto": "Escuchar una explicación de por qué estuvo mal."},
            {"valor": "lectura", "texto": "Leer la corrección o escribir la respuesta correcta."},
            {"valor": "kinestesico", "texto": "Intentarlo otra vez con un ejercicio parecido."},
        ],
    },
]


def generar_preguntas_vark():
    proveedor = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

    if proveedor == "gemini":
        preguntas = generar_preguntas_con_gemini()

        if preguntas:
            return {
                "origen": "gemini",
                "preguntas": preparar_preguntas(preguntas),
            }

    return {
        "origen": "respaldo",
        "preguntas": preparar_preguntas(PREGUNTAS_RESPALDO),
    }


def generar_preguntas_con_gemini():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        return []

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()

        prompt = """
Genera un test VARK de 10 preguntas cotidianas en español.

Reglas obligatorias:
- No menciones medicina, anatomía, universidad ni exámenes médicos.
- Cada pregunta debe tratar situaciones comunes de la vida diaria.
- Cada pregunta debe tener exactamente 4 opciones.
- Cada opción debe representar exactamente uno de estos estilos:
  visual, auditivo, lectura, kinestesico.
- En cada pregunta debe haber una opción visual, una auditiva, una de lectura y una kinestésica.
- Usa lenguaje claro para estudiantes.
- No repitas situaciones.
- No incluyas explicación adicional.
- Devuelve únicamente JSON válido.

Formato exacto:
{
  "preguntas": [
    {
      "id": 1,
      "texto": "Pregunta cotidiana aquí",
      "opciones": [
        {"valor": "visual", "texto": "Opción visual aquí"},
        {"valor": "auditivo", "texto": "Opción auditiva aquí"},
        {"valor": "lectura", "texto": "Opción lectura/escritura aquí"},
        {"valor": "kinestesico", "texto": "Opción kinestésica aquí"}
      ]
    }
  ]
}
"""

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.9,
            ),
        )

        contenido = limpiar_json(response.text)
        data = json.loads(contenido)

        preguntas = data.get("preguntas", [])
        preguntas_validadas = validar_preguntas(preguntas)

        if len(preguntas_validadas) != 10:
            print("Gemini respondió, pero no generó 10 preguntas válidas.")
            return []

        return preguntas_validadas

    except Exception as error:
        print("Error generando preguntas con Gemini:", error)
        return []


def generar_recomendacion_llm(perfil):
    proveedor = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

    if proveedor == "gemini":
        recomendacion = generar_recomendacion_con_gemini(perfil)

        if recomendacion:
            return recomendacion

    return ""


def generar_recomendacion_con_gemini(perfil):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        return ""

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()

        prompt = f"""
Genera una recomendación breve y personalizada para un estudiante de Anatomía I.

Datos del estudiante:
- Estilo principal: {perfil.estilo_display}
- Puntaje visual: {perfil.puntaje_visual}
- Puntaje auditivo: {perfil.puntaje_auditivo}
- Puntaje lectura/escritura: {perfil.puntaje_lectura}
- Puntaje kinestésico: {perfil.puntaje_kinestesico}

Instrucciones:
- Escribe en español.
- Máximo 120 palabras.
- Da consejos prácticos para estudiar Anatomía I.
- Adapta los consejos al estilo principal.
- No uses formato JSON.
- No uses markdown.
"""

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
            ),
        )

        return response.text.strip()

    except Exception as error:
        print("Error generando recomendación con Gemini:", error)
        return ""


def validar_preguntas(preguntas):
    preguntas_validadas = []

    if not isinstance(preguntas, list):
        return preguntas_validadas

    for index, pregunta in enumerate(preguntas, start=1):
        if not isinstance(pregunta, dict):
            continue

        texto = str(pregunta.get("texto", "")).strip()
        opciones = pregunta.get("opciones", [])

        if not texto or not isinstance(opciones, list):
            continue

        opciones_validadas = []
        estilos_encontrados = set()

        for opcion in opciones:
            if not isinstance(opcion, dict):
                continue

            valor = str(opcion.get("valor", "")).strip().lower()
            texto_opcion = str(opcion.get("texto", "")).strip()

            if valor not in ESTILOS_VALIDOS:
                continue

            if valor in estilos_encontrados:
                continue

            if not texto_opcion:
                continue

            estilos_encontrados.add(valor)
            opciones_validadas.append(
                {
                    "valor": valor,
                    "texto": texto_opcion,
                }
            )

        if set(estilos_encontrados) == set(ESTILOS_VALIDOS):
            preguntas_validadas.append(
                {
                    "id": index,
                    "texto": texto,
                    "opciones": opciones_validadas,
                }
            )

    return preguntas_validadas


def preparar_preguntas(preguntas):
    preguntas_preparadas = []

    for index, pregunta in enumerate(preguntas, start=1):
        opciones = pregunta["opciones"].copy()
        random.shuffle(opciones)

        preguntas_preparadas.append(
            {
                "id": index,
                "texto": pregunta["texto"],
                "opciones": opciones,
            }
        )

    return preguntas_preparadas


def limpiar_json(texto):
    texto = str(texto or "").strip()

    if texto.startswith("```json"):
        texto = texto.replace("```json", "", 1).strip()

    if texto.startswith("```"):
        texto = texto.replace("```", "", 1).strip()

    if texto.endswith("```"):
        texto = texto[:-3].strip()

    return texto


def obtener_estilos_ganadores(puntajes):
    puntaje_maximo = max(puntajes.values())

    return [
        estilo
        for estilo, puntaje in puntajes.items()
        if puntaje == puntaje_maximo
    ]


def generar_pregunta_desempate(estilos_empatados):
    etiquetas = {
        "visual": "Visual",
        "auditivo": "Auditivo",
        "lectura": "Lectura/Escritura",
        "kinestesico": "Kinestésico",
    }

    opciones_base = {
        "visual": "Ver un esquema, imagen, mapa, color o demostración visual.",
        "auditivo": "Escuchar una explicación o conversar sobre el tema.",
        "lectura": "Leer una guía, resumen, lista o instrucciones escritas.",
        "kinestesico": "Practicar, probar, manipular o resolver algo directamente.",
    }

    opciones = [
        {
            "valor": estilo,
            "texto": opciones_base[estilo],
            "label": etiquetas[estilo],
        }
        for estilo in estilos_empatados
    ]

    random.shuffle(opciones)

    return {
        "texto": "Tus respuestas quedaron muy equilibradas. Para definir un estilo principal, elige la opción que más se parece a ti cuando aprendes algo nuevo:",
        "opciones": opciones,
    }