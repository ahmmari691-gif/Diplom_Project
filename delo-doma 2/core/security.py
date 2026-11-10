import base64
import hashlib
import json
import math
import re
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import AuditLog, Business, RateBucket

SELLER_NOTICE = 'За качество товаров и услуг, безопасность и соответствие описанию отвечает продавец — владелец бизнеса, а не платформа «Дело дома». Платформа помогает оформить и отслеживать заявку.'

class AppError(Exception):
    def __init__(self, message, status=400, code='invalid_request'):
        super().__init__(message)
        self.status, self.code = status, code

def fail(message, status=400, code='invalid_request'):
    raise AppError(message, status, code)

def clean(value, maximum=2000):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', value.strip())[:maximum] if isinstance(value, str) else ''

def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()

def business_id(user):
    return digest('business:' + str(user.pk))[:32]

def ms(value):
    return int(value.timestamp() * 1000) if value else None

def decimal(value, minimum=0, maximum=1_000_000_000, integer=False):
    try:
        if isinstance(value, bool):
            raise ValueError()
        result = Decimal(str(value))
        if not result.is_finite() or result < minimum or result > maximum or (integer and result != int(result)):
            raise ValueError()
        return result
    except (ValueError, TypeError, InvalidOperation):
        fail('Проверьте числовое значение и допустимый диапазон.')

def seal(value, scope):
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(base64.urlsafe_b64decode(settings.DATA_ENCRYPTION_KEY)).encrypt(
        nonce, json.dumps(value, ensure_ascii=False).encode(), scope.encode())
    return base64.urlsafe_b64encode(nonce + encrypted).decode()

def unseal(value, scope):
    raw = base64.urlsafe_b64decode(value)
    return json.loads(AESGCM(base64.urlsafe_b64decode(settings.DATA_ENCRYPTION_KEY)).decrypt(raw[:12], raw[12:], scope.encode()))

def current_user(request):
    user = request.user
    if not user.is_authenticated or not user.is_active or (user.role == 'manager' and not user.platform_active):
        return None
    return user

def require_role(request, *roles):
    user = current_user(request)
    if not user:
        fail('Войдите в аккаунт.', 401, 'auth_required')
    role = 'admin' if user.is_superuser else user.role
    if role not in roles:
        fail('Для вашей роли это действие недоступно.', 403, 'forbidden')
    return user

def owned_business(request, lock=False):
    user = require_role(request, 'business')
    query = Business.objects.select_for_update() if lock else Business.objects
    business = query.filter(owner=user).first()
    if not business:
        fail('Сначала добавьте свой бизнес.', 404)
    return business

def audit(user, action, business=None, details=None):
    AuditLog.objects.create(actor=digest(user.pk if user else 'anonymous')[:12],
                            role=('admin' if user.is_superuser else user.role) if user else 'client',
                            action=action, business_id=getattr(business, 'pk', business), details=details or {})

def rate_limit(request, scope, maximum):
    # Only REMOTE_ADDR: untrusted forwarded headers cannot bypass the limit.
    now = timezone.now()
    key = scope + ':' + digest(request.META.get('REMOTE_ADDR', 'unknown'))[:24] + ':' + str(int(now.timestamp()) // 60)
    with transaction.atomic():
        bucket, _ = RateBucket.objects.get_or_create(key=key, defaults={'expires': now + timedelta(minutes=2)})
        if not RateBucket.objects.filter(pk=key, count__lt=maximum).update(count=F('count') + 1):
            fail('Слишком много запросов. Попробуйте через минуту.', 429, 'rate_limit')

def user_data(user):
    if not user:
        return None
    role = 'admin' if user.is_superuser else user.role
    result = {'id': str(user.pk), 'name': user.name or user.email.split('@')[0], 'email': user.email, 'role': role}
    if role == 'business':
        result['businessId'] = business_id(user)
    elif role == 'manager':
        result['scope'] = 'platform'
    return result
