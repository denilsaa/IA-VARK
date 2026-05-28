from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required
def subir(request):
    if request.method == "POST":
        return redirect("documentos:lista")

    return render(request, "documentos/subir.html")


@login_required
def lista(request):
    materiales = [
        {
            "nombre": "Sistema oseo - apuntes.pdf",
            "tipo": "PDF",
            "fecha": "2026-05-20",
            "tema": "Sistema oseo",
            "estado": "Procesado",
        },
        {
            "nombre": "Craneo lateral.png",
            "tipo": "PNG",
            "fecha": "2026-05-23",
            "tema": "Huesos del craneo",
            "estado": "Pendiente",
        },
        {
            "nombre": "Resumen articulaciones.docx",
            "tipo": "Word",
            "fecha": "2026-05-25",
            "tema": "Artrologia",
            "estado": "Procesado",
        },
    ]
    return render(request, "documentos/lista.html", {"materiales": materiales})
