from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from core.models import Business, KnowledgeDocument, Order, Product, RecipeLine, StockItem, StockMovement, User
from core.security import business_id, digest, seal

class Command(BaseCommand):
    help = 'Создать отдельные демонстрационные аккаунты и пример кондитерской (только DEBUG).'
    @transaction.atomic
    def handle(self, **options):
        if not settings.DEBUG:
            raise CommandError('Демо запрещено в production.')
        if User.objects.filter(email='alina@preview.local').exists():
            self.stdout.write('Демо уже существует; данные не изменены.')
            return
        for email, name, role in [('alina@preview.local', 'Алина', 'business'), ('dana@preview.local', 'Дана', 'manager'), ('admin@preview.local', 'Администратор', 'admin')]:
            u = User(email=email, username=email, name=name, role=role, platform_active=role == 'manager', is_staff=role == 'admin', is_superuser=role == 'admin')
            u.set_unusable_password()
            u.save()
            if role == 'business':
                owner = u
        b = Business.objects.create(id=business_id(owner), owner=owner, name='Крошка', category='Домашняя кондитерская',
            description='Свежие домашние десерты небольшими партиями по предзаказу.', pickup_area='Астана',
            pickup_instructions='Согласуйте самовывоз с продавцом после подтверждения заказа.', average_check=7500)
        products = []
        for name, price, desc in [('Бенто-торт «Маленький праздник»', 6500, 'Ванильный бисквит, крем-чиз и ваша надпись. 450 г.'),
                                  ('Клубника в шоколаде', 8500, 'Набор 12 штук.'), ('Капкейки «Облака»', 7200, 'Шесть капкейков с ягодной начинкой.')]:
            products.append(Product.objects.create(business=b, name=name, price=price, description=desc))
        item = StockItem.objects.create(business=b, name='Клубника', unit='кг', stock=10, minimum=2)
        StockMovement.objects.create(item=item, delta=10, balance=10, note='Начальный остаток')
        RecipeLine.objects.create(product=products[0], item=item, quantity='0.5')
        for i, status in enumerate(['new', 'working', 'ready', 'done']):
            p = products[i % len(products)]
            Order.objects.create(business=b, status=status, token_hash=digest('demo-' + str(i)),
                due=timezone.now() + timedelta(days=3), consents={'privacy': True, 'seller': True},
                encrypted_data=seal({'name': 'Демонстрационный клиент', 'phone': 'Демо-контакт', 'product': p.name,
                                     'qty': 1, 'total': float(p.price), 'currency': '₸', 'note': ''}, 'order:' + b.pk))
        parsed = {'headers': ['Вопрос', 'Ответ'], 'rows': [{'Вопрос': 'Как хранить десерт?', 'Ответ': 'Храните в холодильнике. Уточните срок хранения у продавца.'}],
                  'candidates': [], 'formulaCount': 0, 'ignoredColumns': [], 'type': 'txt'}
        KnowledgeDocument.objects.create(business=b, name='Ответы клиентам.txt', status='active', activated=timezone.now(),
            row_count=1, columns=parsed['headers'], selected_columns=parsed['headers'], file_type='txt', encrypted_payload=seal(parsed, 'knowledge:' + b.pk))
        self.stdout.write(self.style.SUCCESS('Демонстрационные данные созданы. Паролей у демо-аккаунтов нет.'))
