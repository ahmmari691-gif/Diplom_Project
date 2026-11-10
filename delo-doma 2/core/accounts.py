import re
import secrets
from datetime import timedelta
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from .models import Invitation, SessionLink, User
from .security import audit, clean, digest, fail, rate_limit, user_data

def start_session(request, user):
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session.set_expiry(43200)
    request.session.save()
    SessionLink.objects.update_or_create(session_key=request.session.session_key,
        defaults={'user': user, 'expires': timezone.now() + timedelta(hours=12)})

def auth_route(request, v):
    action = v.get('action')
    if action == 'logout':
        SessionLink.objects.filter(session_key=request.session.session_key).delete()
        logout(request)
        return {'ok': True}
    if action not in ('signup', 'login'):
        fail('Неизвестное действие.')
    rate_limit(request, 'auth', 10)
    email, password = clean(v.get('email'), 254).lower(), v.get('password')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or not isinstance(password, str) or not 8 <= len(password) <= 128:
        fail('Введите email и пароль длиной от 8 до 128 символов.')
    if action == 'signup':
        if v.get('termsAccepted') is not True:
            fail('Подтвердите ознакомление с условиями и хранением данных.')
        if User.objects.filter(email=email).exists():
            fail('Этот email уже зарегистрирован. Войдите в аккаунт.', 409)
        try:
            with transaction.atomic():
                invitation = None
                if v.get('invite'):
                    invitation = Invitation.objects.select_for_update().filter(token_hash=digest(v['invite']), email=email, used=False, expires__gt=timezone.now()).first()
                    if not invitation:
                        fail('Приглашение недействительно или истекло.', 403)
                user = User(email=email, username=email, name=clean(v.get('name'), 100) or email.split('@')[0],
                            role='manager' if invitation else 'business', platform_active=bool(invitation),
                            terms={'version': '2026-10-21', 'acceptedAt': int(timezone.now().timestamp() * 1000)})
                try:
                    validate_password(password, user)
                except ValidationError as error:
                    fail(' '.join(error.messages))
                user.set_password(password)
                user.save()
                if invitation:
                    invitation.used = True
                    invitation.save(update_fields=['used'])
                audit(user, 'account.created')
        except IntegrityError:
            fail('Этот email уже зарегистрирован.', 409)
    else:
        user = authenticate(request, username=email, password=password)
        if not user:
            fail('Неверный email или пароль.', 401)
        if user.role == 'manager' and not user.platform_active:
            fail('Доступ к команде площадки отозван.', 403)
        audit(user, 'account.login')
    start_session(request, user)
    return {'user': user_data(user)}

def revoke_sessions(user):
    keys = list(user.session_links.values_list('session_key', flat=True))
    Session.objects.filter(session_key__in=keys).delete()
    user.session_links.all().delete()
