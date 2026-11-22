import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.utils import timezone
from django.db.models import Q

class Account(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=12, choices=[('business', 'Бизнес'), ('manager', 'Менеджер площадки'), ('admin', 'Администратор')], default='business')
    name = models.CharField(max_length=100, blank=True)
    platform_active = models.BooleanField(default=False)
    terms = models.JSONField(default=dict)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

class User(models.Model):
    """Guest buyer, not a login. Contacts live only in the encrypted order snapshot.

    A new guest identity is issued per checkout; phone numbers are not used to
    identify or merge people across businesses.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

class Business(models.Model):
    id = models.CharField(primary_key=True, max_length=32)
    owner = models.OneToOneField(Account, on_delete=models.PROTECT, related_name='business')
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=100)
    business_type = models.CharField(max_length=16, default='auto')
    description = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default='₸')
    average_check = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    pickup_area = models.CharField(max_length=150, blank=True)
    pickup_instructions = models.TextField(blank=True)
    lead_hours = models.PositiveIntegerField(default=24)
    daily_capacity = models.PositiveIntegerField(default=8)
    ai_provider = models.CharField(max_length=12, default='openai')
    status = models.CharField(max_length=12, default='active', choices=[('active', 'Активен'), ('paused', 'Приостановлен')])
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    ordering_conditions = models.TextField(blank=True)
    contact_phone = models.CharField(max_length=100, blank=True)
    language = models.CharField(max_length=5, default='ru')

    @property
    def ai_external_consent(self):
        if hasattr(self, '_pending_consent'):
            return self._pending_consent
        return self.provider_consents.filter(provider=self.ai_provider, granted=True).exists()

    @ai_external_consent.setter
    def ai_external_consent(self, value):
        self._pending_consent = bool(value)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            if hasattr(self, '_pending_consent'):
                now = timezone.now()
                # Switching providers never transfers permission to the new provider.
                self.provider_consents.exclude(provider=self.ai_provider).filter(granted=True).update(granted=False, revoked_at=now)
                consent, _ = ProviderConsent.objects.get_or_create(business=self, provider=self.ai_provider)
                if self._pending_consent and not consent.granted:
                    consent.granted_at = now
                consent.granted = self._pending_consent
                consent.revoked_at = None if consent.granted else now
                consent.granted_by = self.owner
                consent.save()
                del self._pending_consent

    @property
    def products(self):
        return Product.objects.filter(catalogue__business=self)

    def default_catalogue(self):
        return Catalogue.objects.get_or_create(business=self, title='Основной каталог',
            defaults={'created_by': self.owner})[0]

    def __str__(self):
        return self.name

class Catalogue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='catalogues')
    created_by = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='created_catalogues')
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'title'], name='unique_catalogue_title')]

class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catalogue = models.ForeignKey(Catalogue, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=160)
    price = models.DecimalField(max_digits=16, decimal_places=2)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    lead_hours = models.PositiveIntegerField(default=0)
    is_available = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['catalogue', 'name'], name='unique_product_name'),
                       models.CheckConstraint(condition=Q(price__gt=0), name='positive_product_price')]

class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=12, default='new', choices=[(v, v) for v in ('new', 'working', 'ready', 'done', 'cancelled')])
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='orders')
    reference = models.CharField(max_length=80, unique=True)
    total = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    token_hash = models.CharField(max_length=64)
    due = models.DateTimeField()
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    updated = models.DateTimeField(auto_now=True)
    channel = models.CharField(max_length=60, default='direct')
    campaign = models.CharField(max_length=80, blank=True)
    # Entire customer/order snapshot is encrypted, not a plain JSON column.
    encrypted_data = models.TextField()
    anonymized = models.DateTimeField(null=True, blank=True)

    @property
    def consents(self):
        c = self.consent
        return {'privacy': c.personal_data, 'seller': c.seller_acknowledged,
                'externalAi': c.external_ai, 'marketing': c.marketing, 'version': c.version,
                'at': int(c.accepted_at.timestamp() * 1000)}

    @consents.setter
    def consents(self, value):
        self._pending_consents = value

    def save(self, *args, **kwargs):
        with transaction.atomic():
            creating = self._state.adding
            if not self.user_id:
                self.user = User.objects.create()
            if not self.reference:
                self.reference = str(self.pk) + '.' + self.business_id
            super().save(*args, **kwargs)
            if creating:
                OrderStatusHistory.objects.create(order=self, from_status='', to_status=self.status, customer=self.user)
            if creating or hasattr(self, '_pending_consents'):
                c = getattr(self, '_pending_consents', {})
                OrderConsent.objects.update_or_create(order=self, defaults={
                    'personal_data': c.get('privacy') is True, 'seller_acknowledged': c.get('seller') is True,
                    'external_ai': c.get('externalAi') is True, 'marketing': c.get('marketing') is True,
                    'version': c.get('version', '')})
                if hasattr(self, '_pending_consents'):
                    del self._pending_consents

class OrderConsent(models.Model):
    order = models.OneToOneField(Order, primary_key=True, on_delete=models.CASCADE, related_name='consent')
    personal_data = models.BooleanField(default=False)
    seller_acknowledged = models.BooleanField(default=False)
    external_ai = models.BooleanField(default=False)
    marketing = models.BooleanField(default=False)
    version = models.CharField(max_length=32, blank=True)
    accepted_at = models.DateTimeField(default=timezone.now)

class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    from_status = models.CharField(max_length=12, blank=True)
    to_status = models.CharField(max_length=12)
    changed_by = models.ForeignKey(Account, null=True, on_delete=models.SET_NULL, related_name='order_changes')
    customer = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name='order_changes')
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(changed_by__isnull=True) | Q(customer__isnull=True), name='one_status_actor')]

class ProviderConsent(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='provider_consents')
    provider = models.CharField(max_length=12)
    granted = models.BooleanField(default=False)
    granted_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)
    granted_by = models.ForeignKey(Account, null=True, on_delete=models.SET_NULL, related_name='provider_consents')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'provider'], name='unique_provider_consent')]

class StockItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='stock_items')
    name = models.CharField(max_length=100)
    unit = models.CharField(max_length=4)
    stock = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    minimum = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'name'], name='unique_stock_name'),
                       models.CheckConstraint(condition=Q(stock__gte=0), name='nonnegative_stock')]

class RecipeLine(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='recipe_lines')
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['product', 'item'], name='unique_recipe_item'),
                       models.CheckConstraint(condition=Q(quantity__gt=0), name='positive_recipe_quantity')]

class Consumption(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    reference = models.CharField(max_length=120)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'reference'], name='unique_consumption')]

class StockMovement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name='movements')
    delta = models.DecimalField(max_digits=20, decimal_places=6)
    balance = models.DecimalField(max_digits=20, decimal_places=6)
    note = models.CharField(max_length=200, blank=True)
    reference = models.CharField(max_length=120, blank=True)
    created = models.DateTimeField(auto_now_add=True)

class KnowledgeDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='documents')
    name = models.CharField(max_length=140)
    status = models.CharField(max_length=12, default='review')
    created = models.DateTimeField(auto_now_add=True)
    activated = models.DateTimeField(null=True)
    row_count = models.PositiveIntegerField()
    columns = models.JSONField(default=list)
    selected_columns = models.JSONField(default=list)
    file_type = models.CharField(max_length=5)
    formula_count = models.PositiveIntegerField(default=0)
    ignored_columns = models.JSONField(default=list)
    encrypted_payload = models.TextField()
    uploaded_by = models.ForeignKey(Account, null=True, on_delete=models.SET_NULL, related_name='uploaded_documents')
    reviewed_by = models.ForeignKey(Account, null=True, on_delete=models.SET_NULL, related_name='reviewed_documents')
    reviewed_at = models.DateTimeField(null=True)

class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created = models.DateTimeField(auto_now_add=True)
    actor = models.CharField(max_length=12)
    actor_account = models.ForeignKey(Account, null=True, on_delete=models.SET_NULL, related_name='audit_events')
    order = models.ForeignKey(Order, null=True, on_delete=models.SET_NULL, related_name='audit_events')
    role = models.CharField(max_length=12)
    action = models.CharField(max_length=80)
    business_id = models.CharField(max_length=32, null=True)
    details = models.JSONField(default=dict)

class Invitation(models.Model):
    id = models.BigAutoField(primary_key=True)
    created_by = models.ForeignKey(Account, null=True, on_delete=models.SET_NULL, related_name='invitations')
    role = models.CharField(max_length=12, default='manager', choices=[('manager', 'Менеджер')])
    token_hash = models.CharField(unique=True, max_length=64)
    email = models.EmailField()
    expires = models.DateTimeField()
    used = models.BooleanField(default=False)

class Campaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, null=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    source = models.CharField(max_length=60)
    slug = models.CharField(max_length=80)
    cost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    status = models.CharField(max_length=12, default='draft')
    created = models.DateTimeField(auto_now_add=True)

class PlatformTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=150)
    status = models.CharField(max_length=12, default='todo')
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

class Visit(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    source = models.CharField(max_length=60)
    created = models.DateTimeField(auto_now_add=True)

class SessionLink(models.Model):
    user = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='session_links')
    session_key = models.CharField(max_length=40, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    expires = models.DateTimeField()

class RateBucket(models.Model):
    key = models.CharField(primary_key=True, max_length=120)
    count = models.PositiveIntegerField(default=0)
    expires = models.DateTimeField(db_index=True)
