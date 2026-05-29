from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import DatosAcademicosForm
from .models import DatosAcademicos


@login_required
def datos_academicos(request):
    datos = DatosAcademicos.objects.filter(user=request.user).first()

    if request.method == "POST":
        form = DatosAcademicosForm(request.POST, instance=datos)

        if form.is_valid():
            datos_guardados = form.save(commit=False)
            datos_guardados.user = request.user
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
        },
    )