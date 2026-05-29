import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import MaterialEstudioForm
from .models import MaterialEstudio
from .services import procesar_material


@login_required
def subir_material(request):
    if request.method == "POST":
        form = MaterialEstudioForm(request.POST, request.FILES)

        if form.is_valid():
            material = form.save(commit=False)
            material.user = request.user

            if material.archivo:
                material.tipo = detectar_tipo_archivo(material.archivo.name)

            material.estado = MaterialEstudio.ESTADO_PENDIENTE
            material.save()

            procesar_material(material)

            messages.success(
                request,
                "Material guardado y procesado correctamente.",
            )

            return redirect("documentos:detalle", pk=material.pk)
    else:
        form = MaterialEstudioForm()

    return render(
        request,
        "documentos/subir.html",
        {
            "form": form,
        },
    )


@login_required
def lista_materiales(request):
    materiales = MaterialEstudio.objects.filter(user=request.user)

    return render(
        request,
        "documentos/lista.html",
        {
            "materiales": materiales,
        },
    )


@login_required
def detalle_material(request, pk):
    material = get_object_or_404(
        MaterialEstudio,
        pk=pk,
        user=request.user,
    )

    return render(
        request,
        "documentos/detalle.html",
        {
            "material": material,
        },
    )


@login_required
def reprocesar_material(request, pk):
    material = get_object_or_404(
        MaterialEstudio,
        pk=pk,
        user=request.user,
    )

    if request.method != "POST":
        raise Http404()

    procesar_material(material)

    messages.success(
        request,
        "Material reprocesado correctamente.",
    )

    return redirect("documentos:detalle", pk=material.pk)


@login_required
def eliminar_material(request, pk):
    material = get_object_or_404(
        MaterialEstudio,
        pk=pk,
        user=request.user,
    )

    if request.method != "POST":
        raise Http404()

    if material.archivo:
        material.archivo.delete(save=False)

    material.delete()

    messages.success(
        request,
        "Material eliminado correctamente.",
    )

    return redirect("documentos:lista")


def detectar_tipo_archivo(nombre_archivo):
    _, extension = os.path.splitext(nombre_archivo)
    extension = extension.lower()

    if extension == ".pdf":
        return MaterialEstudio.TIPO_PDF

    if extension in [".doc", ".docx"]:
        return MaterialEstudio.TIPO_WORD

    if extension in [".jpg", ".jpeg", ".png", ".webp"]:
        return MaterialEstudio.TIPO_IMAGEN

    if extension == ".txt":
        return MaterialEstudio.TIPO_TEXTO

    return MaterialEstudio.TIPO_OTRO