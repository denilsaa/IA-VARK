from django import forms
from django.utils import timezone

from .models import DatosAcademicos, TemaAnatomia


MATERIA_CHOICES = [
    ("Anatomía I", "Anatomía I"),
]

MINUTOS_CHOICES = [
    (minutos, f"{minutos} minutos")
    for minutos in range(15, 61, 5)
]


class DatosAcademicosForm(forms.ModelForm):
    materia = forms.ChoiceField(
        choices=MATERIA_CHOICES,
        label="Materia",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    tema_actual = forms.ChoiceField(
        label="Tema actual",
        widget=forms.Select(attrs={"class": "form-control", "id": "id_tema_actual"}),
    )

    temas_dificiles = forms.ChoiceField(
        required=False,
        label="Punto específico que te cuesta más",
        widget=forms.Select(attrs={"class": "form-control", "id": "id_temas_dificiles"}),
    )

    minutos_por_dia = forms.TypedChoiceField(
        choices=MINUTOS_CHOICES,
        coerce=int,
        label="Minutos disponibles por día",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = DatosAcademicos
        fields = [
            "materia",
            "tema_actual",
            "fecha_inicio",
            "fecha_examen",
            "minutos_por_dia",
            "tipo_examen",
            "temas_dificiles",
            "objetivo_estudio",
        ]

        widgets = {
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
            "tipo_examen": forms.Select(
                attrs={
                    "class": "form-control",
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
            "fecha_inicio": "Fecha de inicio de estudio",
            "fecha_examen": "Fecha del examen",
            "tipo_examen": "Tipo de examen",
            "objetivo_estudio": "Objetivo de estudio",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        temas_principales = list(TemaAnatomia.temas_principales())
        tema_choices = [("", "Selecciona un tema del libro")] + [
            (tema.nombre, tema.nombre)
            for tema in temas_principales
        ]
        self.fields["tema_actual"].choices = tema_choices

        tema_seleccionado = self.data.get("tema_actual")
        if not tema_seleccionado and self.instance and self.instance.pk:
            tema_seleccionado = self.instance.tema_actual

        subtema_choices = [("", "Selecciona primero un tema")]
        if tema_seleccionado:
            subtemas = TemaAnatomia.objects.filter(
                tema_padre__nombre=tema_seleccionado,
                activo=True,
            ).order_by("orden", "nombre")
            subtema_choices = [("", "Selecciona un punto específico")] + [
                (subtema.nombre, subtema.nombre)
                for subtema in subtemas
            ]

        # Si el usuario tenía guardado un valor antiguo que no está en el dataset,
        # lo mantenemos para que el formulario no falle al editar.
        valor_guardado = ""
        if self.instance and self.instance.pk:
            valor_guardado = self.instance.temas_dificiles or ""

        valores_choices = {valor for valor, _ in subtema_choices}
        if valor_guardado and valor_guardado not in valores_choices:
            subtema_choices.append((valor_guardado, valor_guardado))

        self.fields["temas_dificiles"].choices = subtema_choices

    def clean_materia(self):
        return "Anatomía I"

    def clean_tema_actual(self):
        tema = self.cleaned_data.get("tema_actual")

        if not tema:
            raise forms.ValidationError("Debes seleccionar un tema del libro.")

        existe = TemaAnatomia.objects.filter(
            nombre=tema,
            tema_padre__isnull=True,
            activo=True,
        ).exists()

        if not existe:
            raise forms.ValidationError("Selecciona un tema válido del dataset de Anatomía I.")

        return tema

    def clean_temas_dificiles(self):
        subtema = self.cleaned_data.get("temas_dificiles")
        tema = self.cleaned_data.get("tema_actual")

        if not subtema:
            return ""

        existe = TemaAnatomia.objects.filter(
            nombre=subtema,
            tema_padre__nombre=tema,
            activo=True,
        ).exists()

        if not existe:
            raise forms.ValidationError("Selecciona un punto específico válido para el tema elegido.")

        return subtema

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

        if minutos < 15:
            raise forms.ValidationError("Debes registrar al menos 15 minutos de estudio por día.")

        if minutos > 60:
            raise forms.ValidationError("El máximo permitido es 60 minutos por día.")

        if minutos % 5 != 0:
            raise forms.ValidationError("El tiempo debe registrarse en intervalos de 5 minutos.")

        return minutos
