from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import DatosAcademicosForm
from .models import DatosAcademicos, TemaAnatomia


def construir_subtemas_por_tema():
    data = {}
    temas = TemaAnatomia.temas_principales().prefetch_related("subtemas")

    for tema in temas:
        data[tema.nombre] = [
            subtema.nombre
            for subtema in tema.subtemas.filter(activo=True).order_by("orden", "nombre")
        ]

    return data


@login_required
def datos_academicos(request):
    datos = DatosAcademicos.objects.filter(user=request.user).first()

    if request.method == "POST":
        form = DatosAcademicosForm(request.POST, instance=datos)

        if form.is_valid():
            datos_guardados = form.save(commit=False)
            datos_guardados.user = request.user
            datos_guardados.materia = "Anatomía I"
            datos_guardados.save()

            messages.success(
                request,
                "Tus datos académicos fueron guardados correctamente.",
            )

            return redirect("usuarios:dashboard")
    else:
        form = DatosAcademicosForm(instance=datos)

    return render(
        request,
        "anatomia/datos_academicos.html",
        {
            "form": form,
            "datos": datos,
            "subtemas_por_tema": construir_subtemas_por_tema(),
        },
    )
