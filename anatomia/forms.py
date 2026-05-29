from django import forms
from django.utils import timezone

from .models import DatosAcademicos


class DatosAcademicosForm(forms.ModelForm):
    class Meta:
        model = DatosAcademicos
        fields = [
            "materia",
            "tema_actual",
            "fecha_inicio",
            "fecha_examen",
            "minutos_por_dia",
            "tipo_examen",
            "nivel_dificultad",
            "temas_dificiles",
            "objetivo_estudio",
        ]

        widgets = {
            "materia": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Anatomía I",
                }
            ),
            "tema_actual": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ejemplo: Sistema óseo",
                }
            ),
            "fecha_inicio": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "fecha_examen": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "minutos_por_dia": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "30",
                    "max": "720",
                    "step": "30",
                    "placeholder": "Ejemplo: 30, 60, 90",
                }
            ),
            "tipo_examen": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "nivel_dificultad": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "temas_dificiles": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Ejemplo: huesos del cráneo, articulaciones, músculos del brazo...",
                }
            ),
            "objetivo_estudio": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Ejemplo: prepararme para aprobar el parcial con buena nota...",
                }
            ),
        }

        labels = {
            "materia": "Materia",
            "tema_actual": "Tema actual",
            "fecha_inicio": "Fecha de inicio de estudio",
            "fecha_examen": "Fecha del examen",
            "minutos_por_dia": "Minutos disponibles por día",
            "tipo_examen": "Tipo de examen",
            "nivel_dificultad": "Nivel de dificultad percibido",
            "temas_dificiles": "Temas que te cuestan más",
            "objetivo_estudio": "Objetivo de estudio",
        }

    def clean_fecha_examen(self):
        fecha_examen = self.cleaned_data.get("fecha_examen")
        hoy = timezone.localdate()

        if fecha_examen and fecha_examen < hoy:
            raise forms.ValidationError("La fecha del examen no puede estar en el pasado.")

        return fecha_examen

    def clean_minutos_por_dia(self):
        minutos = self.cleaned_data.get("minutos_por_dia")

        if minutos is None:
            return minutos

        if minutos < 30:
            raise forms.ValidationError("Debes registrar al menos 30 minutos de estudio por día.")

        if minutos > 720:
            raise forms.ValidationError("El máximo permitido es 720 minutos por día.")

        if minutos % 30 != 0:
            raise forms.ValidationError("El tiempo debe registrarse en bloques de 30 minutos.")

        return minutos