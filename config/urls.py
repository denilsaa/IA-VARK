from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from usuarios import views as usuarios_views

urlpatterns = [
    path("", usuarios_views.home, name="home"),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("usuarios.urls")),
    path("vark/", include("vark.urls")),
    path("anatomia/", include("anatomia.urls")),
    path("documentos/", include("documentos.urls")),
    path("rutas/", include("rutas.urls")),
    path("examenes/", include("examenes.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, "SERVE_MEDIA_IN_PRODUCTION", False):
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]
