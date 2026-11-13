import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=12, choices=[('business', 'Бизнес'), ('manager', 'Менеджер площадки'), ('admin', 'Администратор')], default='business')
    name = models.CharField(max_length=100, blank=True)
    platform_active = models.BooleanField(default=False)
    terms = models.JSONField(default=dict)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

class Business(models.Model):
    id = models.CharField(primary_key=True, max_length=32)
    owner = models.OneToOneField(User, on_delete=models.PROTECT, related_name='business')
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
    ai_external_consent = models.BooleanField(default=False)
    ai_provider = models.CharField(max_length=12, default='openai')
    status = models.CharField(max_length=12, default='active', choices=[('active', 'Активен'), ('paused', 'Приостановлен')])
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.name

class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=160)
    price = models.DecimalField(max_digits=16, decimal_places=2)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    lead_hours = models.PositiveIntegerField(default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'name'], name='unique_product_name'),
                       models.CheckConstraint(condition=Q(price__gt=0), name='positive_product_price')]

class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=12, default='new', choices=[(v, v) for v in ('new', 'working', 'ready', 'done', 'cancelled')])
    token_hash = models.CharField(max_length=64)
    due = models.DateTimeField()
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    updated = models.DateTimeField(auto_now=True)
    channel = models.CharField(max_length=60, default='direct')
    campaign = models.CharField(max_length=80, blank=True)
    consents = models.JSONField(default=dict)
    # Entire customer/order snapshot is encrypted, not a plain JSON column.
    encrypted_data = models.TextField()
    anonymized = models.DateTimeField(null=True, blank=True)

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

class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created = models.DateTimeField(auto_now_add=True)
    actor = models.CharField(max_length=12)
    role = models.CharField(max_length=12)
    action = models.CharField(max_length=80)
    business_id = models.CharField(max_length=32, null=True)
    details = models.JSONField(default=dict)

class Invitation(models.Model):
    token_hash = models.CharField(primary_key=True, max_length=64)
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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='session_links')
    session_key = models.CharField(max_length=40, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    expires = models.DateTimeField()

class RateBucket(models.Model):
    key = models.CharField(primary_key=True, max_length=120)
    count = models.PositiveIntegerField(default=0)
    expires = models.DateTimeField(db_index=True)
