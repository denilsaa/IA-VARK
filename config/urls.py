from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("vark/", include("vark.urls")),
    path("anatomia/", include("anatomia.urls")),
    path("documentos/", include("documentos.urls")),
    path("rutas/", include("rutas.urls")),
    path("examenes/", include("examenes.urls")),
    path("", include("usuarios.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
