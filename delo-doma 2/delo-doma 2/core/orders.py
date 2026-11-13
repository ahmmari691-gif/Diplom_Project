import re
import secrets
from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .inventory import consume_order
from .models import Business, Order, Product
from .security import SELLER_NOTICE, audit, business_id, clean, decimal, digest, fail, owned_business, rate_limit, require_role, seal
from .serializers import business_data, document_meta, order_data, order_payload, order_reference
from .experience import experience, TYPE_NAMES

def parse_date(value):
    try:
        date = parse_datetime(value) if isinstance(value, str) else None
        if date and timezone.is_naive(date):
            date = timezone.make_aware(date)
        if not date:
            raise ValueError()
        return date
    except (ValueError, OverflowError):
        fail('Проверьте дату и время получения.')

def find_order(reference):
    match = re.fullmatch(r'([a-f0-9-]{36})\.([a-f0-9]{32})', str(reference or ''))
    if not match:
        fail('Заказ не найден.', 404)
    try:
        order = Order.objects.filter(pk=match[1], business_id=match[2]).first()
    except (ValueError, ValidationError):
        order = None
    if not order:
        fail('Заказ не найден.', 404)
    return order

def check_token(order, token):
    if not isinstance(token, str) or not secrets.compare_digest(order.token_hash, digest(token)):
        fail('Заказ не найден.', 404)

def save_business(request, data):
    user = require_role(request, 'business')
    if not isinstance(data, dict) or not clean(data.get('name')) or not isinstance(data.get('products'), list) or not 1 <= len(data['products']) <= 100:
        fail('Укажите название бизнеса и от 1 до 100 товаров.')
    names, products = set(), []
    for p in data['products']:
        if not isinstance(p, dict):
            fail('Проверьте каталог.')
        name = clean(p.get('name'), 160)
        if not name or name in names:
            fail('Названия товаров должны быть непустыми и уникальными.')
        names.add(name)
        products.append({'name': name, 'price': decimal(p.get('price'), minimum=Decimal('0.01')),
                         'description': clean(p.get('description'), 1200), 'category': clean(p.get('category'), 80),
                         'lead_hours': int(decimal(p.get('leadHours') or 0, maximum=720, integer=True))})
    with transaction.atomic():
        # Serialize creation for this owner as well as edits of an existing business.
        get_user_model().objects.select_for_update().get(pk=user.pk)
        b, created = Business.objects.get_or_create(owner=user, defaults={'id': business_id(user), 'name': clean(data['name'], 120)})
        b.name, b.category, b.description = clean(data['name'], 120), clean(data.get('category'), 100), clean(data.get('description'), 3000)
        kind = data.get('businessType', b.business_type)
        if kind not in TYPE_NAMES:
            fail('Выберите корректный формат бизнеса.')
        b.business_type = kind
        b.currency = data.get('currency') if data.get('currency') in ('₸', '₽', '$', '€') else '₸'
        b.average_check = decimal(data.get('check') or 0)
        b.pickup_area, b.pickup_instructions = clean(data.get('pickupArea'), 150), clean(data.get('pickupInstructions'), 700)
        b.lead_hours = int(decimal(data.get('leadHours') or 0, maximum=720, integer=True))
        b.daily_capacity = int(decimal(data.get('dailyCapacity') or 8, minimum=1, maximum=1000, integer=True))
        b.ai_external_consent = data.get('aiExternalConsent') is True
        if b.ai_external_consent:
            from django.conf import settings
            expected = 'gemini' if settings.AI_MODE == 'gemini' else 'openai'
            if data.get('aiProvider', 'openai') != expected:
                fail('Подтвердите разрешение для текущего провайдера ИИ.')
            b.ai_provider = expected
        b.save()
        # Existing product IDs/recipes survive edits when the product name is retained.
        b.products.exclude(name__in=names).delete()
        for p in products:
            Product.objects.update_or_create(business=b, name=p['name'], defaults={k: v for k, v in p.items() if k != 'name'})
        audit(user, 'business.created' if created else 'business.updated', b)
        return business_data(b)

def create_order(request, v):
    rate_limit(request, 'order', 15)
    if v.get('privacyConsent') is not True or v.get('sellerAcknowledged') is not True:
        fail('Подтвердите обработку данных для заказа и ответственность продавца.')
    with transaction.atomic():
        b = Business.objects.select_for_update().filter(pk=clean(v.get('business'), 32)).first()
        if not b:
            fail('Бизнес не найден.', 404)
        if b.status != 'active':
            fail('Этот бизнес временно не принимает заказы.', 403)
        p = b.products.filter(name=v.get('product')).first()
        if not p:
            fail('Выберите товар из каталога.')
        qty, due = int(decimal(v.get('qty'), minimum=1, maximum=1000, integer=True)), parse_date(v.get('due'))
        lead = max(b.lead_hours, p.lead_hours)
        if due <= timezone.now() + timedelta(hours=lead):
            fail('Минимальный срок до выбранного времени: ' + str(lead) + ' ч.')
        name, phone = clean(v.get('name'), 120), clean(v.get('phone'), 100)
        if not name or not phone:
            fail('Укажите имя и контакт для заказа.')
        token = secrets.token_hex(32)
        data = {'name': name, 'phone': phone, 'product': p.name, 'qty': qty,
                'total': float(p.price * qty), 'currency': b.currency, 'note': clean(v.get('note'), 2000)}
        o = Order.objects.create(business=b, token_hash=digest(token), due=due,
            channel=v.get('channel') if v.get('channel') in ('instagram', 'telegram', 'whatsapp', 'tiktok', 'facebook', 'direct', 'other') else 'direct',
            campaign=v.get('campaign') if re.fullmatch(r'[a-z0-9_-]{1,80}', str(v.get('campaign', ''))) else '',
            consents={'privacy': True, 'seller': True, 'marketing': v.get('marketingConsent') is True,
                      'version': '2026-10-21', 'at': int(timezone.now().timestamp() * 1000)},
            encrypted_data=seal(data, 'order:' + b.pk))
        audit(None, 'order.created', b, {'order': str(o.pk)})
        return {'id': order_reference(o), 'token': token}

def anonymize(order):
    data = order_payload(order)
    data.update(name='Контакт удалён', phone='', note='')
    order.encrypted_data, order.anonymized = seal(data, 'order:' + order.business_id), timezone.now()

def change_order(request, v):
    initial = find_order(v.get('id'))
    with transaction.atomic():
        # Consistent lock ordering: business first, then order, then stock.
        b = Business.objects.select_for_update().get(pk=initial.business_id)
        o = Order.objects.select_for_update().get(pk=initial.pk)
        action = v['action']
        if action == 'cancel':
            check_token(o, v.get('token'))
            if o.due - timezone.now() < timedelta(days=1):
                fail('Отмена доступна не позднее чем за 24 часа до получения.', 403)
            if o.status in ('done', 'cancelled'):
                fail('Заказ уже закрыт.')
            o.status = 'cancelled'
        else:
            user = require_role(request, 'business')
            if b.owner_id != user.pk:
                fail('Нет доступа к заказу.', 403)
            if action == 'anonymize':
                if o.status not in ('done', 'cancelled'):
                    fail('Контакты можно удалить после завершения или отмены заказа.')
                anonymize(o)
            else:
                allowed = {'new': ('working', 'cancelled'), 'working': ('ready', 'cancelled'), 'ready': ('done',)}
                if v.get('status') not in allowed.get(o.status, ()):
                    fail('Этот переход статуса недоступен.')
                if v['status'] == 'ready':
                    consume_order(b, o)
                o.status = v['status']
        o.save()
        audit(request.user if request.user.is_authenticated else None,
              'order.anonymized' if action == 'anonymize' else 'order.status_changed', b,
              {'order': str(o.pk), 'status': o.status})
        return {'ok': True}

def data_route(request, v):
    if request.method == 'GET':
        if request.GET.get('business'):
            b = Business.objects.filter(pk=request.GET['business']).first()
            if not b:
                fail('Бизнес не найден.', 404)
            return business_data(b, public=True)
        if request.GET.get('track'):
            o = find_order(request.GET['track'])
            check_token(o, request.GET.get('token'))
            return {**order_data(o), 'businessName': o.business.name, 'experience': experience(o.business),
                    'pickupInstructions': o.business.pickup_instructions if o.status in ('working', 'ready', 'done') else '',
                    'disclaimer': SELLER_NOTICE}
        user = require_role(request, 'business')
        b = Business.objects.filter(owner=user).first()
        from .security import user_data
        return {'user': user_data(user), 'business': business_data(b) if b else None,
                'orders': [order_data(o) for o in b.orders.order_by('-created')] if b else [],
                'documents': [document_meta(d) for d in b.documents.order_by('-created')] if b else []}
    action = v.get('action')
    if action == 'business':
        return save_business(request, v.get('data'))
    if action == 'order':
        return create_order(request, v)
    if action in ('cancel', 'status', 'anonymize'):
        return change_order(request, v)
    fail('Неизвестное действие.')
