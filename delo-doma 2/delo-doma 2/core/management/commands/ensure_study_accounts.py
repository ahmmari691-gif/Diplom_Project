"""Recreate fictional accounts in the explicitly isolated study database."""
import os
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Business, Product, User
from core.security import business_id

ACCOUNTS = (
    ('business', 'business@demo.local', 'Учебный бизнес', 'Study-Business-2026!'),
    ('manager', 'manager@demo.local', 'Учебный менеджер', 'Study-Manager-2026!'),
    ('admin', 'admin@demo.local', 'Учебный администратор', 'Study-Admin-2026!'),
)

class Command(BaseCommand):
    help = 'Создать недостающие учебные аккаунты без изменения существующих данных.'

    def add_arguments(self, parser):
        parser.add_argument('--if-enabled', action='store_true')

    @transaction.atomic
    def handle(self, **options):
        if not settings.STUDY_MODE:
            if options.get('if_enabled'):
                return
            raise CommandError('Сначала включите DELO_STUDY_MODE=1 (отдельная SQLite).')
        prepared = []
        for role, email, name, local_password in ACCOUNTS:
            existing = User.objects.filter(email=email).first()
            if existing:
                if existing.role != role:
                    raise CommandError(f'Конфликт роли для {email}; аккаунт не изменён.')
                prepared.append((existing, False))
                continue
            variable = f'DELO_STUDY_{role.upper()}_PASSWORD'
            password = os.getenv(variable) or (local_password if settings.DEBUG else '')
            if not password:
                raise CommandError(f'Укажите {variable} в окружении сервера.')
            if not settings.DEBUG and password in [row[3] for row in ACCOUNTS]:
                raise CommandError(f'Укажите собственный пароль в {variable}, отличный от локальных примеров.')
            user = User(email=email, username=email, name=name, role=role,
                        platform_active=role == 'manager', is_staff=role == 'admin',
                        is_superuser=role == 'admin', terms={'educationalFixture': True})
            try:
                validate_password(password, user)
            except ValidationError as exc:
                raise CommandError(f'{variable}: ' + ' '.join(exc.messages)) from exc
            user.set_password(password)
            prepared.append((user, True))
        for user, created in prepared:
            if created:
                user.save()
            if user.role == 'business':
                business, new_business = Business.objects.get_or_create(owner=user, defaults={
                    'id': business_id(user), 'name': 'Учебная кондитерская',
                    'category': 'Кондитерская', 'description': 'Учебный пример. Все данные вымышлены.',
                    'pickup_area': 'Демонстрационная зона', 'lead_hours': 24,
                })
                if new_business:
                    Product.objects.create(business=business, name='Учебный бенто-торт',
                                           price=6500, description='Вымышленный товар для защиты проекта.')
            self.stdout.write(f'{user.email}: ' + ('создан' if created else 'уже существует, не изменён'))
