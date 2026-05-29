import os

from django import forms

from .models import MaterialEstudio


class MaterialEstudioForm(forms.ModelForm):
    EXTENSIONES_PERMITIDAS = [
        ".pdf",
        ".doc",
        ".docx",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".txt",
    ]

    LIMITE_MB = 500

    class Meta:
        model = MaterialEstudio
        fields = [
            "titulo",
            "tema",
            "temario_examen",
            "descripcion",
            "tipo",
            "archivo",
        ]

        widgets = {
            "titulo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ejemplo: Libro de Anatomía - Rouvière Tomo 2",
                }
            ),
            "tema": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ejemplo: Tronco, abdomen, pelvis",
                }
            ),
            "temario_examen": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Ejemplo:\n"
                        "Órganos del abdomen\n"
                        "Órganos de la región lumbar y pelvis menor\n"
                        "Periné\n"
                        "Anatomía topográfica del periné"
                    ),
                }
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Descripción breve del material.",
                }
            ),
            "tipo": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "archivo": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": ".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp,.txt",
                }
            ),
        }

        labels = {
            "titulo": "Título del material",
            "tema": "Tema general",
            "temario_examen": "Temas que entran al examen",
            "descripcion": "Descripción",
            "tipo": "Tipo de material",
            "archivo": "Archivo",
        }

    def clean(self):
        cleaned_data = super().clean()

        archivo_limpio = cleaned_data.get("archivo")
        archivo_enviado = self.files.get("archivo")

        if not archivo_limpio and not archivo_enviado:
            raise forms.ValidationError(
                "Debes subir un archivo para guardar el material."
            )

        return cleaned_data

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")

        if not archivo:
            return archivo

        nombre = archivo.name
        _, extension = os.path.splitext(nombre)
        extension = extension.lower()

        if extension not in self.EXTENSIONES_PERMITIDAS:
            raise forms.ValidationError(
                "Formato no permitido. Usa PDF, Word, imagen o TXT."
            )

        limite_bytes = self.LIMITE_MB * 1024 * 1024

        if archivo.size > limite_bytes:
            raise forms.ValidationError(
                f"El archivo no debe superar {self.LIMITE_MB} MB."
            )

        return archivo