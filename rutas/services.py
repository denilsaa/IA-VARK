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
          "titulo": "Mapa mental premium del día",
          "tipo": "mapa_mental",
          "mermaid": "mindmap\\n  root((Tema))\\n    Rama 1\\n    Rama 2",
          "apoyo_visual": ["Elemento visual 1", "Elemento visual 2"]
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
          "titulo": "Lámina anatómica guiada realista",
          "tipo_vista": "anterior",
          "descripcion": "Descripción breve de la lámina, indicando la vista anatómica y qué relaciones debe observar el estudiante",
          "marcadores": [
            {{"id": 1, "nombre": "Estructura 1", "x": 50, "y": 20, "pista": "Pista breve", "detalle": "Qué debe reconocer"}},
            {{"id": 2, "nombre": "Estructura 2", "x": 55, "y": 55, "pista": "Pista breve", "detalle": "Qué debe reconocer"}}
          ],
          "preguntas": ["¿Qué estructura corresponde al marcador 1?", "¿Qué relación anatómica observas?"],
          "modo_practica": "primero identificar sin ver respuesta y luego revelar"
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
- Si Visual > 0, genera visual.habilitado=true con un Mermaid mucho más didáctico y visual. Prefiere flowchart TD o mindmap limpio con un nodo central, 3 a 5 ramas principales y 1 o 2 subramas por rama. Además imagen_anatomica.habilitado=true con 3 a 5 marcadores bien distribuidos visualmente. Las pistas deben ser específicas, cortas y conectadas al tema seleccionado.
- Los marcadores deben usar coordenadas x e y entre 10 y 90 para poder dibujarse dentro del diagrama.
- Si Kinestésico > 0, genera kinestesico.habilitado=true.
- Si Lectura/Escritura > 0, genera lectura.habilitado=true; si es 0, puede quedar false.
- No inventes detalles anatómicos ultraespecíficos fuera del contexto; si falta precisión, enfoca la lámina en relaciones generales del tema y subtema, priorizando una vista anatómica realista y coherente.
- Cada día debe incluir mini_quiz con 3 preguntas evaluables.
- Cada pregunta del mini_quiz debe tener exactamente 4 opciones y una respuesta_correcta que coincida exactamente con una opción.
- Las preguntas deben evaluar el tema del día, la lámina, el audio o el ejercicio práctico.
- Para Mermaid usa SOLO diagramas simples. Prefiere flowchart TD o mindmap con un estilo limpio, máximo 8 nodos visibles, textos cortos de 1 a 4 palabras por nodo, sin paréntesis complejos, sin comillas y sin caracteres raros. Distribuye el mapa para que se vea como un esquema docente claro y prioriza legibilidad visual.
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
                        "tipo_vista": "anterior",
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
    return {
        "habilitado": bool(valor.get("habilitado")),
        "titulo": str(valor.get("titulo", "Mapa visual")).strip(),
        "tipo": str(valor.get("tipo", "mapa_mental")).strip(),
        "mermaid": str(valor.get("mermaid", "")).strip(),
        "apoyo_visual": normalizar_lista(valor.get("apoyo_visual", [])),
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
            x = max(10, min(int(item.get("x") or 50), 90))
            y = max(10, min(int(item.get("y") or 50), 90))
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
        "titulo": str(valor.get("titulo", "Lámina anatómica guiada")).strip(),
        "tipo_vista": str(valor.get("tipo_vista", "anterior")).strip(),
        "descripcion": str(valor.get("descripcion", "")).strip(),
        "marcadores": marcadores_limpios,
        "preguntas": normalizar_lista(valor.get("preguntas", [])),
        "modo_practica": str(valor.get("modo_practica", "")).strip(),
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
