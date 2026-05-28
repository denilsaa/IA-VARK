from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


PREGUNTAS_VARK = [
    "Cuando estudias el sistema oseo, prefieres apoyarte en:",
    "Si un docente explica una estructura nueva, aprendes mejor cuando:",
    "Para recordar los pares craneales, te resulta mas util:",
    "Cuando preparas un examen, eliges principalmente:",
    "Si tienes dudas sobre una articulacion, prefieres:",
    "Para entender una imagen anatomica compleja, haces primero:",
    "Cuando repasas con tus companeros, te sirve mas:",
    "Si debes memorizar una lista de inserciones, prefieres:",
    "Para aprender el recorrido de un nervio, eliges:",
    "Antes de un simulacro, te funciona mejor:",
]

OPCIONES_VARK = [
    ("visual", "Visual", "Ver esquemas, colores, mapas y laminas."),
    ("auditivo", "Auditivo", "Escuchar explicaciones y repetir en voz alta."),
    ("lectura", "Lectura/Escritura", "Leer apuntes, escribir resumenes y listas."),
    ("kinestesico", "Kinestesico", "Practicar con modelos, casos y ejercicios."),
]


@login_required
def test(request):
    if request.method == "POST":
        return redirect("vark:resultado")

    preguntas = [{"numero": index + 1, "texto": texto} for index, texto in enumerate(PREGUNTAS_VARK)]
    return render(request, "vark/test.html", {"preguntas": preguntas, "opciones": OPCIONES_VARK})


@login_required
def resultado(request):
    puntajes = [
        {"estilo": "Visual", "valor": 42, "class": "bg-success"},
        {"estilo": "Auditivo", "valor": 21, "class": "bg-info"},
        {"estilo": "Lectura/Escritura", "valor": 24, "class": "bg-warning"},
        {"estilo": "Kinestesico", "valor": 13, "class": "bg-danger"},
    ]
    recomendaciones = [
        "Usa esquemas comparativos para huesos, musculos y articulaciones.",
        "Marca estructuras con colores consistentes por sistema.",
        "Convierte cada tema en mapas visuales antes de resolver preguntas.",
    ]
    return render(
        request,
        "vark/resultado.html",
        {
            "estilo_principal": "Visual",
            "puntajes": puntajes,
            "recomendaciones": recomendaciones,
        },
    )
