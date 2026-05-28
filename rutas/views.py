from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def ruta_aprendizaje(request):
    dias = [
        {
            "dia": 1,
            "titulo": "Introduccion al sistema oseo",
            "actividades": ["Mapa general del esqueleto", "Lectura guiada", "10 preguntas de repaso"],
        },
        {
            "dia": 2,
            "titulo": "Huesos del craneo",
            "actividades": ["Lamina rotulada", "Tabla de foramenes", "Practica visual"],
        },
        {
            "dia": 3,
            "titulo": "Columna vertebral",
            "actividades": ["Comparar regiones", "Resumen de accidentes oseos", "Mini quiz"],
        },
        {
            "dia": 4,
            "titulo": "Preguntas de practica",
            "actividades": ["Bloque de opcion multiple", "Revision de errores", "Tarjetas de memoria"],
        },
        {
            "dia": 5,
            "titulo": "Mini simulacro",
            "actividades": ["Simulacro mixto", "Correccion", "Ajuste de temas debiles"],
        },
    ]
    return render(
        request,
        "rutas/ruta_aprendizaje.html",
        {"dias": dias, "tema": "Sistema oseo", "fecha_examen": "2026-06-12", "estilo_vark": "Visual"},
    )
