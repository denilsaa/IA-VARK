import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from anatomia.models import TemaAnatomia

from .forms import MaterialEstudioForm
from .models import MaterialEstudio
from .services import procesar_material


@login_required
def subir_material(request):
    if request.method == "POST":
        form = MaterialEstudioForm(request.POST, request.FILES, user=request.user)

        if form.is_valid():
            archivos = form.cleaned_data.get("archivo") or []

            if not isinstance(archivos, list):
                archivos = [archivos]

            materiales_creados = []

            for index, archivo in enumerate(archivos, start=1):
                titulo_base = form.cleaned_data.get("titulo") or "Material de estudio"
                titulo = titulo_base

                if len(archivos) > 1:
                    nombre_archivo = os.path.splitext(os.path.basename(archivo.name))[0]
                    titulo = f"{titulo_base} - {nombre_archivo}"

                tema_principal = form.cleaned_data.get("tema_principal", "")
                subtema_relacionado = form.cleaned_data.get("subtema_relacionado", "")
                tema_compuesto = tema_principal
                if subtema_relacionado:
                    tema_compuesto = f"{tema_principal} > {subtema_relacionado}"

                material = MaterialEstudio.objects.create(
                    user=request.user,
                    titulo=titulo,
                    tema=tema_compuesto,
                    temario_examen=form.cleaned_data.get("temario_examen", ""),
                    descripcion=form.cleaned_data.get("descripcion", ""),
                    tipo=detectar_tipo_archivo(archivo.name),
                    archivo=archivo,
                    estado=MaterialEstudio.ESTADO_PENDIENTE,
                )

                procesar_material(material)
                materiales_creados.append(material)

            if len(materiales_creados) == 1:
                messages.success(
                    request,
                    "Material guardado y analizado correctamente. Revisa el resumen, temas clave y preguntas sugeridas.",
                )
                return redirect("documentos:detalle", pk=materiales_creados[0].pk)

            messages.success(
                request,
                f"Se guardaron y analizaron {len(materiales_creados)} materiales correctamente.",
            )
            return redirect("documentos:lista")
    else:
        form = MaterialEstudioForm(user=request.user)

    subtema_dataset = {
        tema.nombre: list(
            TemaAnatomia.objects.filter(tema_padre=tema, activo=True)
            .order_by("orden", "nombre")
            .values_list("nombre", flat=True)
        )
        for tema in TemaAnatomia.temas_principales()
    }

    return render(
        request,
        "documentos/subir.html",
        {
            "form": form,
            "subtema_dataset": subtema_dataset,
        },
    )


@login_required
def lista_materiales(request):
    materiales = MaterialEstudio.objects.filter(user=request.user)

    total_materiales = materiales.count()
    procesados = materiales.filter(estado=MaterialEstudio.ESTADO_PROCESADO).count()
    pendientes = materiales.filter(
        estado__in=[MaterialEstudio.ESTADO_PENDIENTE, MaterialEstudio.ESTADO_PROCESANDO]
    ).count()
    con_error = materiales.filter(estado=MaterialEstudio.ESTADO_ERROR).count()

    return render(
        request,
        "documentos/lista.html",
        {
            "materiales": materiales,
            "stats_materiales": {
                "total": total_materiales,
                "procesados": procesados,
                "pendientes": pendientes,
                "error": con_error,
            },
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
        "Material reprocesado correctamente. Se actualizó el análisis IA.",
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
