from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required
def generar(request):
    if request.method == "POST":
        return redirect("examenes:resolver")

    tipos = ["Opcion multiple", "Verdadero/falso", "Preguntas abiertas", "Mixto"]
    niveles = ["Basico", "Intermedio", "Avanzado"]
    return render(request, "examenes/generar.html", {"tipos": tipos, "niveles": niveles})


@login_required
def resolver(request):
    if request.method == "POST":
        return redirect("examenes:resultado")

    preguntas = [
        {
            "numero": 1,
            "tipo": "opcion",
            "texto": "Que hueso forma la mayor parte de la frente?",
            "opciones": ["Frontal", "Parietal", "Temporal", "Occipital"],
        },
        {
            "numero": 2,
            "tipo": "vf",
            "texto": "Las vertebras cervicales tipicas presentan foramen transverso.",
            "opciones": ["Verdadero", "Falso"],
        },
        {
            "numero": 3,
            "tipo": "abierta",
            "texto": "Describe dos diferencias entre una vertebra cervical y una toracica.",
            "opciones": [],
        },
    ]
    return render(request, "examenes/resolver.html", {"preguntas": preguntas})


@login_required
def resultado(request):
    respuestas = [
        {"pregunta": "Hueso de la frente", "estado": "Correcta", "detalle": "Frontal"},
        {"pregunta": "Foramen transverso", "estado": "Correcta", "detalle": "Verdadero"},
        {
            "pregunta": "Diferencias vertebrales",
            "estado": "Incorrecta",
            "detalle": "Falto mencionar facetas costales y apofisis espinosa.",
        },
    ]
    return render(
        request,
        "examenes/resultado.html",
        {
            "puntaje": 82,
            "respuestas": respuestas,
            "debilidades": ["Vertebras toracicas", "Articulaciones costovertebrales"],
            "recomendacion": "Revisa comparaciones por region vertebral y repite un bloque de 15 preguntas mixtas.",
        },
    )
