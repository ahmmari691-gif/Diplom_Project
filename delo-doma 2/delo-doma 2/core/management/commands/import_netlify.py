"""One-time read-only import of the local Netlify Blobs emulator, not production."""
import base64
import json
import uuid
from datetime import datetime, timezone as tz
from decimal import Decimal
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import (AuditLog, Business, Campaign, Consumption, KnowledgeDocument, Order,
                         PlatformTask, Product, RecipeLine, StockItem, StockMovement, User, Visit)
from core.security import seal

def date(value):
    return datetime.fromtimestamp(value / 1000, tz=tz.utc) if value else None

class Command(BaseCommand):
    help = 'Перенести локальные данные Netlify в пустую базу Django. Исходные файлы не изменяются.'
    def add_arguments(self, parser):
        parser.add_argument('source', type=Path, help='Каталог netlify-app/.local-data')

    @transaction.atomic
    def handle(self, source, **options):
        if User.objects.exists() or Business.objects.exists():
            raise CommandError('Импорт разрешён только в пустую базу. Текущие данные не перезаписываются.')
        roots = list((source / 'blobs' / 'entries').glob('*/site:*'))
        roots = [p for p in roots if (p / 'business').exists()]
        if len(roots) != 1 or not (source / 'encryption.key').is_file():
            raise CommandError('Не найдены однозначное локальное хранилище и ключ шифрования.')
        root = roots[0]
        key = base64.b64decode((source / 'encryption.key').read_text().strip())

        def entries(prefix):
            path = root / prefix
            return [json.loads(p.read_text()) for p in path.rglob('*') if p.is_file()] if path.exists() else []

        def decrypt(value, scope):
            if not isinstance(value, dict) or not value.get('encrypted'):
                return value
            return json.loads(AESGCM(key).decrypt(base64.b64decode(value['iv']),
                base64.b64decode(value['body']) + base64.b64decode(value['tag']), scope.encode()))

        members = {m['id']: m for m in entries('platform-members')}
        accounts = {a['id']: a for a in entries('users')}
        users = {}
        for p in entries('profiles'):
            role = p.get('role', 'business')
            u = User(id=p['id'], email=p.get('email') or p['id'] + '@import.local',
                     username=p.get('email') or p['id'], name=p.get('name', 'Владелец'), role=role,
                     platform_active=role == 'manager' and members.get(p['id'], {}).get('active', False),
                     is_active=not p.get('disabled', False), is_staff=role == 'admin', is_superuser=role == 'admin',
                     terms=p.get('terms', {}))
            a = accounts.get(p['id'])
            if a and a.get('password') and a.get('salt'):
                u.password = 'legacy_scrypt$' + a['salt'] + '$' + a['password']
            else:
                u.set_unusable_password()
            u.save()
            users[str(u.pk)] = u

        businesses = {}
        for old in entries('business'):
            owner = users.get(old['owner'])
            if not owner:
                owner = User(id=old['owner'], username=old['owner'], email=old['owner'] + '@import.local', name='Владелец')
                owner.set_unusable_password()
                owner.save()
                users[str(owner.pk)] = owner
            b = Business.objects.create(id=old['id'], owner=owner, name=old['name'], category=old.get('category', ''),
                description=old.get('description', ''), currency=old.get('currency', '₸'), average_check=old.get('check', 0),
                pickup_area=old.get('pickupArea', ''), pickup_instructions=old.get('pickupInstructions', ''),
                lead_hours=old.get('leadHours', 24), daily_capacity=old.get('dailyCapacity', 8),
                ai_external_consent=old.get('aiExternalConsent', False), status=old.get('status', 'active'))
            Business.objects.filter(pk=b.pk).update(created=date(old['created']), updated=date(old.get('updated') or old['created']))
            for p in old.get('products', []):
                Product.objects.create(business=b, name=p['name'], price=p['price'], description=p.get('description', ''),
                                       category=p.get('category', ''), lead_hours=p.get('leadHours', 0))
            businesses[b.pk] = b

        for old in entries('orders'):
            b = businesses[old['business']]
            payload = decrypt(old['data'], 'order:' + b.pk)
            o = Order.objects.create(id=old['id'].split('.')[0], business=b, token_hash=old.get('tokenHash', ''),
                status=old['status'], due=date(old['due']), channel=old.get('channel', 'direct'), campaign=old.get('campaign', ''),
                consents=old.get('consents', {}), anonymized=date(old.get('anonymized')),
                encrypted_data=seal(payload, 'order:' + b.pk))
            Order.objects.filter(pk=o.pk).update(created=date(old['created']), updated=date(old.get('updated') or old['created']))

        for old in entries('knowledge'):
            b = businesses[old['business']]
            payload = decrypt(old['payload'], 'knowledge:' + b.pk)
            d = KnowledgeDocument.objects.create(id=old['id'], business=b, name=old['name'], status=old['status'],
                activated=date(old.get('activated')), row_count=old['rowCount'], columns=old['columns'],
                selected_columns=old.get('selectedColumns', old['columns']), file_type=old['type'],
                formula_count=old.get('formulaCount', 0), ignored_columns=old.get('ignoredColumns', []),
                encrypted_payload=seal(payload, 'knowledge:' + b.pk))
            KnowledgeDocument.objects.filter(pk=d.pk).update(created=date(old['created']))

        inv_root = root / 'inventory'
        if inv_root.exists():
            for path in inv_root.iterdir():
                if not path.is_file() or path.name not in businesses:
                    continue
                b, old, items = businesses[path.name], json.loads(path.read_text()), {}
                for item in old.get('items', []):
                    i = StockItem.objects.create(id=item['id'], business=b, name=item['name'], unit=item['unit'],
                                                 stock=item['stock'], minimum=item.get('min', 0))
                    items[str(i.pk)] = i
                for name, lines in old.get('recipes', {}).items():
                    product = b.products.filter(name=name).first()
                    if product:
                        for line in lines:
                            RecipeLine.objects.create(product=product, item=items[line['item']], quantity=line['qty'])
                for m in old.get('movements', []):
                    movement = StockMovement.objects.create(id=m['id'], item=items[m['item']], delta=m['delta'], balance=m['balance'],
                                                           reference=m.get('reference', ''), note=m.get('note', ''))
                    StockMovement.objects.filter(pk=movement.pk).update(created=date(m['at']))
                for reference, at in old.get('applied', {}).items():
                    c = Consumption.objects.create(business=b, reference=reference)
                    Consumption.objects.filter(pk=c.pk).update(created=date(at))

        for prefix, platform in [('campaigns', False), ('platform-campaigns', True)]:
            for old in entries(prefix):
                try:
                    campaign_id = uuid.UUID(old['id'])
                except ValueError:
                    campaign_id = uuid.uuid5(uuid.NAMESPACE_URL, 'delo-import:' + prefix + ':' + old['id'])
                c = Campaign.objects.create(id=campaign_id, business=None if platform else businesses[old['business']],
                    name=old['name'], source=old['source'], slug=old['slug'], cost=old.get('cost', 0), status=old.get('status', 'draft'))
                Campaign.objects.filter(pk=c.pk).update(created=date(old['created']))
        for old in entries('platform-tasks'):
            t = PlatformTask.objects.create(id=old['id'], title=old['title'], status=old['status'])
            PlatformTask.objects.filter(pk=t.pk).update(created=date(old['created']), updated=date(old.get('updated') or old['created']))
        for old in entries('audit'):
            a = AuditLog.objects.create(actor=old['actor'], role=old['role'], action=old['action'],
                                        business_id=old.get('business'), details=old.get('details', {}))
            AuditLog.objects.filter(pk=a.pk).update(created=date(old['at']))
        events_root = root / 'events'
        if events_root.exists():
            for path in events_root.glob('*/*'):
                if path.is_file() and path.parent.name in businesses:
                    old = json.loads(path.read_text())
                    event = Visit.objects.create(business=businesses[path.parent.name], source=old.get('source', 'direct'))
                    Visit.objects.filter(pk=event.pk).update(created=date(old['at']))
        self.stdout.write(self.style.SUCCESS('Перенесено: бизнесов %s, заказов %s, файлов %s, складских позиций %s. Сессии не переносились.' %
            (Business.objects.count(), Order.objects.count(), KnowledgeDocument.objects.count(), StockItem.objects.count())))
