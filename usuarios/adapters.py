import re

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model


class TutorSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Adaptador para que Google cree/inicie sesion sin mostrar
    la pantalla intermedia /accounts/3rdparty/signup/.
    """

    def is_auto_signup_allowed(self, request, sociallogin):
        return True

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)

        email = (data.get("email") or getattr(user, "email", "") or "").strip().lower()
        name = (data.get("name") or "").strip()
        first_name = (data.get("first_name") or "").strip()
        last_name = (data.get("last_name") or "").strip()

        if email:
            user.email = email

        if first_name:
            user.first_name = first_name[:150]
        elif name:
            partes = name.split()
            if partes:
                user.first_name = partes[0][:150]

        if last_name:
            user.last_name = last_name[:150]
        elif name:
            partes = name.split()
            if len(partes) > 1:
                user.last_name = " ".join(partes[1:])[:150]

        if not getattr(user, "username", ""):
            user.username = self._generar_username_unico(email=email, name=name)

        return user

    def save_user(self, request, sociallogin, form=None):
        user = sociallogin.user

        email = (getattr(user, "email", "") or "").strip().lower()
        name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()

        if email:
            user.email = email

        if not getattr(user, "username", ""):
            user.username = self._generar_username_unico(email=email, name=name)

        sociallogin.user = user

        return super().save_user(request, sociallogin, form)

    def _generar_username_unico(self, email="", name=""):
        User = get_user_model()

        if email:
            base = email.split("@")[0]
        elif name:
            base = name
        else:
            base = "usuario"

        base = base.lower()
        base = re.sub(r"[^a-z0-9_]+", "_", base)
        base = base.strip("_")

        if not base:
            base = "usuario"

        base = base[:30]
        username = base
        contador = 1

        while User.objects.filter(username=username).exists():
            sufijo = f"_{contador}"
            username = f"{base[:30 - len(sufijo)]}{sufijo}"
            contador += 1

        return username