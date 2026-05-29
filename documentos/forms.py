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
            "descripcion",
            "tipo",
            "archivo",
            "texto_manual",
        ]

        widgets = {
            "titulo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ejemplo: Apuntes sistema óseo",
                }
            ),
            "tema": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ejemplo: Sistema óseo, cráneo, músculos...",
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
            "texto_manual": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": "También puedes pegar aquí apuntes escritos manualmente.",
                }
            ),
        }

        labels = {
            "titulo": "Título del material",
            "tema": "Tema relacionado",
            "descripcion": "Descripción",
            "tipo": "Tipo de material",
            "archivo": "Archivo",
            "texto_manual": "Texto manual",
        }

    def clean(self):
        cleaned_data = super().clean()

        archivo_limpio = cleaned_data.get("archivo")
        archivo_enviado = self.files.get("archivo")
        texto_manual = cleaned_data.get("texto_manual", "").strip()

        if not archivo_limpio and not archivo_enviado and not texto_manual:
            raise forms.ValidationError(
                "Debes subir un archivo o escribir texto manual."
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