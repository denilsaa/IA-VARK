from django.core.management.base import BaseCommand
from django.utils.text import slugify

from anatomia.dataset_anatomia import ANATOMIA_I_DATASET
from anatomia.models import TemaAnatomia


class Command(BaseCommand):
    help = "Carga o actualiza el dataset interno de temas de Anatomía I."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpiar",
            action="store_true",
            help="Elimina los temas existentes antes de cargar el dataset.",
        )

    def handle(self, *args, **options):
        if options["limpiar"]:
            TemaAnatomia.objects.all().delete()
            self.stdout.write(self.style.WARNING("Dataset anterior eliminado."))

        total_principales = 0
        total_subtemas = 0

        for item in ANATOMIA_I_DATASET:
            tema, _ = TemaAnatomia.objects.update_or_create(
                codigo=item["codigo"],
                defaults={
                    "nombre": item["nombre"],
                    "tema_padre": None,
                    "descripcion": item.get("descripcion", ""),
                    "pagina_inicio": item.get("pagina_inicio"),
                    "pagina_fin": item.get("pagina_fin"),
                    "orden": item.get("orden", 0),
                    "activo": True,
                },
            )
            total_principales += 1

            for index, subtema_nombre in enumerate(item.get("subtemas", []), start=1):
                codigo_subtema = f"{item['codigo']}-{slugify(subtema_nombre)}"[:120]
                TemaAnatomia.objects.update_or_create(
                    codigo=codigo_subtema,
                    defaults={
                        "nombre": subtema_nombre,
                        "tema_padre": tema,
                        "descripcion": f"Subtema de {tema.nombre}",
                        "pagina_inicio": item.get("pagina_inicio"),
                        "pagina_fin": item.get("pagina_fin"),
                        "orden": index,
                        "activo": True,
                    },
                )
                total_subtemas += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Dataset de Anatomía I cargado: {total_principales} temas principales y {total_subtemas} subtemas."
            )
        )
