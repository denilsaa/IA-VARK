import os

from django import forms

from anatomia.models import TemaAnatomia
try:
    from anatomia.dataset_anatomia import ANATOMIA_I_DATASET
except Exception:  # pragma: no cover
    ANATOMIA_I_DATASET = []

from .models import MaterialEstudio


def dataset_temas_principales():
    return [item.get("nombre", "") for item in ANATOMIA_I_DATASET if item.get("nombre")]


def dataset_subtemas_por_tema():
    return {
        item.get("nombre", ""): item.get("subtemas", [])
        for item in ANATOMIA_I_DATASET
        if item.get("nombre")
    }


def obtener_temas_principales():
    temas_db = list(TemaAnatomia.temas_principales())
    if temas_db:
        return [(tema.nombre, tema.nombre) for tema in temas_db]
    return [(nombre, nombre) for nombre in dataset_temas_principales()]


def obtener_subtemas(tema_nombre):
    if not tema_nombre:
        return []

    subtemas_db = list(
        TemaAnatomia.objects.filter(
            tema_padre__nombre=tema_nombre,
            activo=True,
        )
        .order_by("orden", "nombre")
        .values_list("nombre", flat=True)
    )

    if subtemas_db:
        return subtemas_db

    return dataset_subtemas_por_tema().get(tema_nombre, [])


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        single_clean = super().clean

        if isinstance(data, (list, tuple)):
            archivos_limpios = []
            errores = []

            for archivo in data:
                try:
                    archivos_limpios.append(single_clean(archivo, initial))
                except forms.ValidationError as error:
                    errores.extend(error.error_list)

            if errores:
                raise forms.ValidationError(errores)

            return archivos_limpios

        if data:
            return [single_clean(data, initial)]

        return []


class MaterialEstudioForm(forms.ModelForm):
    EXTENSIONES_PERMITIDAS = [
        ".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".webp", ".txt",
    ]

    LIMITE_MB = 500

    tema_principal = forms.ChoiceField(
        label="Tema al que pertenece",
        required=True,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_tema_principal"}),
    )

    subtema_relacionado = forms.ChoiceField(
        label="Subtema relacionado",
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_subtema_relacionado"}),
    )

    archivo = MultipleFileField(
        label="Archivo o archivos",
        required=True,
        widget=MultipleFileInput(
            attrs={
                "class": "form-control smart-file-input",
                "accept": ".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp,.txt",
                "multiple": True,
            }
        ),
    )

    class Meta:
        model = MaterialEstudio
        fields = ["titulo", "temario_examen", "descripcion", "archivo"]

        widgets = {
            "titulo": forms.TextInput(attrs={"class": "form-control", "placeholder": ""}),
            "temario_examen": forms.Textarea(
                attrs={
                    "class": "form-control material-topic-textarea",
                    "rows": 5,
                    "placeholder": "",
                }
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "",
                }
            ),
        }

        labels = {
            "titulo": "Nombre del material",
            "temario_examen": "¿Qué es lo importante de este documento o foto?",
            "descripcion": "Nota adicional (opcional)",
            "archivo": "Archivo o archivos",
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        tema_choices = [("", "Selecciona un tema")] + obtener_temas_principales()
        self.fields["tema_principal"].choices = tema_choices

        tema_inicial = ""
        subtema_inicial = ""

        if user and hasattr(user, "datos_academicos"):
            tema_inicial = user.datos_academicos.tema_actual or ""
            subtema_inicial = user.datos_academicos.temas_dificiles or ""

        tema_seleccionado = self.data.get("tema_principal") or tema_inicial
        subtema_seleccionado = self.data.get("subtema_relacionado") or subtema_inicial

        if not self.is_bound:
            self.fields["tema_principal"].initial = tema_inicial

        subtema_choices = [("", "Selecciona un subtema")]
        if tema_seleccionado:
            subtema_choices += [(subtema, subtema) for subtema in obtener_subtemas(tema_seleccionado)]

        valores_choices = {valor for valor, _ in subtema_choices}
        if subtema_seleccionado and subtema_seleccionado not in valores_choices:
            subtema_choices.append((subtema_seleccionado, subtema_seleccionado))

        self.fields["subtema_relacionado"].choices = subtema_choices
        if not self.is_bound:
            self.fields["subtema_relacionado"].initial = subtema_inicial

    def clean(self):
        cleaned_data = super().clean()
        archivos = cleaned_data.get("archivo") or self.files.getlist("archivo")

        if not archivos:
            raise forms.ValidationError("Debes subir al menos un archivo para analizar el material.")

        return cleaned_data

    def clean_tema_principal(self):
        tema = self.cleaned_data.get("tema_principal")

        if not tema:
            raise forms.ValidationError("Selecciona el tema al que pertenece el material.")

        temas_validos = {valor for valor, _ in obtener_temas_principales()}
        if tema not in temas_validos:
            raise forms.ValidationError("Selecciona un tema válido.")

        return tema

    def clean_subtema_relacionado(self):
        subtema = self.cleaned_data.get("subtema_relacionado")
        tema = self.cleaned_data.get("tema_principal") or self.data.get("tema_principal")

        if not subtema:
            return ""

        subtemas_validos = set(obtener_subtemas(tema))
        if subtemas_validos and subtema not in subtemas_validos:
            raise forms.ValidationError("Selecciona un subtema válido para el tema elegido.")

        return subtema

    def clean_archivo(self):
        archivos = self.cleaned_data.get("archivo") or []

        if not isinstance(archivos, list):
            archivos = [archivos]

        limite_bytes = self.LIMITE_MB * 1024 * 1024
        archivos_validados = []

        for archivo in archivos:
            if not archivo:
                continue

            nombre = archivo.name
            _, extension = os.path.splitext(nombre)
            extension = extension.lower()

            if extension not in self.EXTENSIONES_PERMITIDAS:
                raise forms.ValidationError(
                    f"El archivo '{nombre}' no tiene un formato permitido. Usa PDF, Word, imagen o TXT."
                )

            if archivo.size > limite_bytes:
                raise forms.ValidationError(
                    f"El archivo '{nombre}' supera el límite de {self.LIMITE_MB} MB."
                )

            archivos_validados.append(archivo)

        if not archivos_validados:
            raise forms.ValidationError("Debes seleccionar al menos un archivo válido.")

        return archivos_validados
