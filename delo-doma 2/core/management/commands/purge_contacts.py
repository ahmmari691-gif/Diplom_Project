from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from core.models import Business, RateBucket
from core.orders import anonymize
from core.security import audit

class Command(BaseCommand):
    help = 'Удалить контакты завершённых и отменённых заказов старше 90 дней; очистить истёкшие лимиты.'
    def handle(self, **options):
        count = 0
        for key in Business.objects.values_list('pk', flat=True):
            with transaction.atomic():
                b = Business.objects.select_for_update().get(pk=key)
                for order in b.orders.select_for_update().filter(status__in=['done', 'cancelled'], anonymized__isnull=True,
                                                                updated__lt=timezone.now() - timedelta(days=90)):
                    anonymize(order)
                    order.save()
                    count += 1
        RateBucket.objects.filter(expires__lt=timezone.now()).delete()
        audit(None, 'privacy.scheduled_purge', details={'count': count})
        self.stdout.write('Удалены контакты заказов: ' + str(count))
