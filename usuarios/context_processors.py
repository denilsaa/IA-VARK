from django.conf import settings


def auth_settings(request):
    return {
        "GOOGLE_AUTH_ENABLED": getattr(settings, "GOOGLE_AUTH_ENABLED", False),
    }