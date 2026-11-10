import re
import secrets
from collections import Counter, defaultdict
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .accounts import revoke_sessions
from .models import AuditLog, Business, Campaign, Invitation, KnowledgeDocument, Order, PlatformTask, SessionLink, User, Visit
from .orders import anonymize
from .security import audit, clean, decimal, digest, fail, ms, owned_business, rate_limit, require_role
from .serializers import audit_data, campaign_data, order_payload, task_data

def period(request):
    days = request.GET.get('days', '30')
    return int(days) if days in ('7', '30', '90') else 30

def staff_route(request, v):
    user = require_role(request, 'admin')
    if request.method == 'GET':
        return {'members': [{'id': str(u.pk), 'name': u.name, 'email': u.email, 'role': 'manager',
                             'active': u.platform_active, 'scope': 'platform'} for u in User.objects.filter(role='manager')]}
    if v.get('action') == 'invite':
        email = clean(v.get('email'), 254).lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            fail('Введите email сотрудника.')
        token = secrets.token_hex(32)
        expires = timezone.now() + timedelta(days=1)
        Invitation.objects.create(token_hash=digest(token), email=email, expires=expires)
        audit(user, 'platform.manager_invited', 'platform')
        return {'token': token, 'expires': ms(expires)}
    if v.get('action') == 'revoke':
        target = next((u for u in User.objects.filter(role='manager') if str(u.pk) == v.get('id')), None)
        if not target:
            fail('Сотрудник не найден.', 404)
        with transaction.atomic():
            target.platform_active = False
            target.save(update_fields=['platform_active'])
            revoke_sessions(target)
            audit(user, 'platform.manager_revoked', 'platform')
        return {'ok': True}
    fail('Неизвестное действие.')

def make_campaign(request, v, business=None):
    name = clean(v.get('name'), 120)
    source = re.sub(r'[^a-z0-9_-]', '', clean(v.get('source'), 60).lower())
    if not name or not source:
        fail('Укажите название кампании и источник.')
    cost = decimal(v.get('cost') or 0)
    slug = re.sub(r'[^a-z0-9_-]', '', clean(v.get('slug'), 80).lower()) if business else ''
    c = Campaign.objects.create(business=business, name=name, source=source, cost=cost,
                                slug=slug or ('campaign-' if business else 'platform-') + secrets.token_hex(5))
    audit(request.user, 'campaign.created' if business else 'platform.campaign_created', business or 'platform')
    return campaign_data(c)

def platform_route(request, v):
    user = require_role(request, 'manager', 'admin')
    if request.method == 'POST':
        if v.get('action') == 'campaign':
            return make_campaign(request, v)
        if v.get('action') == 'task':
            title = clean(v.get('title'), 150)
            if not title:
                fail('Укажите задачу.')
            task = PlatformTask.objects.create(title=title)
            audit(user, 'platform.task_created', 'platform')
            return task_data(task)
        if v.get('action') == 'task_status':
            if v.get('status') not in ('todo', 'working', 'done'):
                fail('Некорректный статус.')
            task = next((t for t in PlatformTask.objects.all() if str(t.pk) == v.get('id')), None)
            if not task:
                fail('Задача не найдена.', 404)
            task.status = v['status']
            task.save(update_fields=['status', 'updated'])
            audit(user, 'platform.task_status', 'platform')
            return {'ok': True}
        fail('Неизвестное действие.')
    days = period(request)
    since = timezone.now() - timedelta(days=days)
    businesses = Business.objects.all()
    # Read only metadata. This path never decrypts orders or documents.
    orders = Order.objects.filter(created__gte=since).values('created', 'channel', 'status')
    daily, sources, statuses = Counter(), Counter(), Counter()
    for o in orders:
        daily[o['created'].date().isoformat()] += 1
        sources[o['channel']] += 1
        statuses[o['status']] += 1
    categories = Counter(businesses.values_list('category', flat=True))
    return {'days': days, 'metrics': {'businesses': businesses.count(), 'active': businesses.filter(status='active').count(),
            'newBusinesses': businesses.filter(created__gte=since).count(), 'orders': sum(statuses.values()),
            'completed': statuses['done'], 'cancelled': statuses['cancelled'], 'documents': KnowledgeDocument.objects.count()},
            'daily': [{'date': d, 'orders': n} for d, n in sorted(daily.items())],
            'categories': [{'name': k, 'count': n} for k, n in categories.items()],
            'sources': [{'name': k, 'count': n} for k, n in sources.items()],
            'campaigns': [campaign_data(c) for c in Campaign.objects.filter(business__isnull=True).order_by('-created')],
            'tasks': [task_data(t) for t in PlatformTask.objects.order_by('-created')],
            'privacy': 'Только агрегаты площадки. Без имён, контактов, пожеланий, файлов и складов бизнесов.'}

def admin_route(request, v):
    user = require_role(request, 'admin')
    if request.method == 'GET':
        businesses = Business.objects.all()
        docs = KnowledgeDocument.objects
        return {'metrics': {'businesses': businesses.count(), 'active': businesses.filter(status='active').count(),
                'managers': User.objects.filter(role='manager', platform_active=True).count(),
                'documents': docs.count(), 'pendingDocuments': docs.filter(status='review').count()},
                'businesses': [{'id': b.pk, 'name': b.name, 'category': b.category, 'status': b.status,
                                'created': ms(b.created), 'products': b.products.count(), 'documents': b.documents.count()} for b in businesses],
                'audit': [audit_data(a) for a in AuditLog.objects.order_by('-created')[:60]],
                'protections': {'encryption': True, 'roles': True, 'privateUploads': True}}
    if v.get('action') == 'set_status':
        if v.get('status') not in ('active', 'paused') or len(clean(v.get('reason'))) < 5:
            fail('Укажите статус и причину изменения.')
        with transaction.atomic():
            b = Business.objects.select_for_update().filter(pk=clean(v.get('business'), 32)).first()
            if not b:
                fail('Бизнес не найден.', 404)
            b.status = v['status']
            b.save(update_fields=['status', 'updated'])
            audit(user, 'admin.business_' + b.status, b, {'reason': clean(v['reason'], 300)})
        return {'ok': True}
    fail('Неизвестное действие.')

def security_route(request, v):
    user = require_role(request, 'business')
    b = Business.objects.filter(owner=user).first()
    if request.method == 'GET':
        return {'members': [], 'audit': [audit_data(a) for a in AuditLog.objects.filter(business_id=b.pk).order_by('-created')[:40]] if b else [],
                'sessions': [{'created': ms(s.created), 'expires': ms(s.expires)} for s in user.session_links.filter(expires__gt=timezone.now())],
                'protections': {'encryption': True, 'roleChecks': True, 'csrf': True, 'rateLimits': True,
                                'privateUploads': True, 'sessionHours': 12, 'consentRequired': True}, 'retentionDays': 90}
    if v.get('action') == 'revoke_sessions':
        from django.contrib.auth import logout
        revoke_sessions(user)
        logout(request)
        audit(user, 'sessions.revoked', b)
        return {'ok': True}
    if v.get('action') == 'purge_old_contacts':
        with transaction.atomic():
            b = owned_business(request, lock=True)
            count = 0
            for o in b.orders.select_for_update().filter(status__in=['done', 'cancelled'], anonymized__isnull=True, updated__lt=timezone.now() - timedelta(days=90)):
                anonymize(o)
                o.save()
                count += 1
            audit(user, 'privacy.contacts_purged', b, {'count': count})
        return {'count': count}
    if v.get('action') in ('invite', 'revoke_manager'):
        fail('Командой площадки управляет системный администратор.', 403)
    fail('Неизвестное действие.')

def analytics_route(request):
    b = owned_business(request)
    days = period(request)
    since = timezone.now() - timedelta(days=days)
    orders = list(b.orders.filter(created__gte=since))
    sources, products, daily = {}, Counter(), {}
    value, completed, active = 0, 0, 0
    payloads = {}
    for o in orders:
        data = payloads[o.pk] = order_payload(o)
        if o.status != 'cancelled':
            value += data['total']
            active += 1
            products[data['product']] += data['qty']
        if o.status == 'done':
            completed += data['total']
        s = sources.setdefault(o.channel, {'source': o.channel, 'orders': 0, 'value': 0, 'completed': 0})
        s['orders'] += 1
        s['value'] += data['total'] if o.status != 'cancelled' else 0
        s['completed'] += data['total'] if o.status == 'done' else 0
        day = o.created.date().isoformat()
        entry = daily.setdefault(day, {'date': day, 'orders': 0, 'value': 0})
        entry['orders'] += 1
        entry['value'] += data['total'] if o.status != 'cancelled' else 0
    campaigns = []
    for c in Campaign.objects.filter(business=b):
        attributed = [o for o in orders if o.campaign == c.slug and o.status != 'cancelled']
        revenue = sum(payloads[o.pk]['total'] for o in attributed if o.status == 'done')
        campaigns.append({**campaign_data(c), 'orders': len(attributed), 'value': sum(payloads[o.pk]['total'] for o in attributed),
                          'completedRevenue': revenue, 'roas': revenue / float(c.cost) if c.cost else None})
    return {'business': {'id': b.pk, 'name': b.name, 'currency': b.currency}, 'days': days,
            'metrics': {'orders': len(orders), 'orderValue': value, 'completedRevenue': completed,
                        'avgCheck': round(value / active) if active else 0, 'cancelled': sum(o.status == 'cancelled' for o in orders),
                        'completed': sum(o.status == 'done' for o in orders), 'consentedViews': Visit.objects.filter(business=b, created__gte=since).count()},
            'daily': sorted(daily.values(), key=lambda d: d['date']), 'sources': list(sources.values()),
            'products': [{'name': p, 'qty': q} for p, q in products.most_common()], 'campaigns': campaigns,
            'privacy': 'Агрегированные показатели. Имена, контакты, тексты заказов и файлы бизнеса менеджеру не передаются.'}

def events_route(request, v):
    if v.get('analyticsConsent') is not True:
        return {'recorded': False}
    rate_limit(request, 'view', 8)
    b = Business.objects.filter(pk=clean(v.get('business'), 32)).first()
    if not b:
        fail('Бизнес не найден.', 404)
    Visit.objects.create(business=b, source=clean(v.get('channel'), 60) or 'direct')
    return {'recorded': True}
