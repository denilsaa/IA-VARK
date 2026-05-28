from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required
def datos_academicos(request):
    if request.method == "POST":
        return redirect("usuarios:dashboard")

    tipos_examen = ["Opcion multiple", "Verdadero/falso", "Preguntas abiertas", "Mixto"]
    niveles = ["Basico", "Intermedio", "Avanzado"]
    return render(
        request,
        "anatomia/datos_academicos.html",
        {"tipos_examen": tipos_examen, "niveles": niveles},
    )
