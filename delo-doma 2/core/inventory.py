import re
from decimal import Decimal
from django.db import transaction
from .models import Consumption, RecipeLine, StockItem, StockMovement
from .security import audit, clean, decimal, fail, ms, owned_business
from .serializers import order_payload, order_reference

def inventory_data(b):
    items = [{'id': str(i.pk), 'name': i.name, 'unit': i.unit, 'stock': float(i.stock), 'min': float(i.minimum)} for i in b.stock_items.all()]
    recipes = {p.name: [{'item': str(l.item_id), 'qty': float(l.quantity)} for l in p.recipe_lines.all()] for p in b.products.prefetch_related('recipe_lines')}
    movements = [{'id': str(m.pk), 'item': str(m.item_id), 'name': m.item.name, 'unit': m.item.unit,
                  'delta': float(m.delta), 'balance': float(m.balance), 'at': ms(m.created),
                  'note': m.note, 'reference': m.reference} for m in StockMovement.objects.filter(item__business=b).select_related('item').order_by('-created')[:200]]
    return {'items': items, 'recipes': recipes, 'movements': movements, 'version': 1}

def get_item(b, key):
    # UUIDs are strings at the API boundary; do not let malformed UUIDs reach ORM validation.
    item = next((i for i in b.stock_items.select_for_update() if str(i.pk) == key), None)
    if not item:
        fail('Складская позиция не найдена.', 404)
    return item

def consume(b, lines, reference, note):
    # Caller holds the business row lock and an atomic transaction.
    if Consumption.objects.filter(business=b, reference=reference).exists():
        return
    totals = {}
    for line in lines:
        key = line.get('item')
        totals[key] = totals.get(key, Decimal(0)) + decimal(line.get('qty'), minimum=Decimal('0.000001'))
    checked = []
    for key, qty in totals.items():
        item = get_item(b, key)
        qty = qty.quantize(Decimal('0.000001'))
        if item.stock < qty:
            fail('Недостаточно на складе: ' + item.name + '.', 409)
        checked.append((item, qty))
    Consumption.objects.create(business=b, reference=reference)
    for item, qty in checked:
        item.stock -= qty
        item.save(update_fields=['stock'])
        StockMovement.objects.create(item=item, delta=-qty, balance=item.stock, reference=reference, note=clean(note, 200))

def consume_order(b, order):
    data = order_payload(order)
    product = b.products.filter(name=data['product']).first()
    if product:
        lines = [{'item': str(l.item_id), 'qty': l.quantity * data['qty']} for l in product.recipe_lines.all()]
        if lines:
            consume(b, lines, 'order:' + order_reference(order), 'Заказ #' + str(order.pk)[:8] + ' · ' + str(data['qty']) + ' шт.')
            audit(None, 'inventory.order_consumed', b, {'order': str(order.pk)})

def inventory_route(request, v):
    if request.method == 'GET':
        return inventory_data(owned_business(request))
    with transaction.atomic():
        b = owned_business(request, lock=True)
        action = v.get('action')
        if action == 'item':
            name, unit = clean(v.get('name'), 100), v.get('unit')
            qty, minimum = decimal(v.get('qty')), decimal(v.get('min') or 0)
            if not name or unit not in ('кг', 'г', 'л', 'мл', 'шт') or b.stock_items.count() >= 200:
                fail('Проверьте название, единицы измерения и число позиций.')
            if b.stock_items.filter(name__iexact=name).exists():
                fail('Такая позиция уже есть.')
            item = StockItem.objects.create(business=b, name=name, unit=unit, stock=qty, minimum=minimum)
            StockMovement.objects.create(item=item, delta=qty, balance=qty, note='Начальный остаток')
        elif action == 'receive':
            item, qty = get_item(b, v.get('item')), decimal(v.get('qty'), minimum=Decimal('0.000001'))
            if item.stock + qty > 1_000_000_000:
                fail('Остаток слишком большой.')
            item.stock += qty
            item.save(update_fields=['stock'])
            StockMovement.objects.create(item=item, delta=qty, balance=item.stock, note='Пополнение')
        elif action == 'recipe':
            p = b.products.filter(name=v.get('product')).first()
            lines = v.get('lines')
            if not p or not isinstance(lines, list) or len(lines) > 100:
                fail('Выберите товар и проверьте рецепт.')
            seen, parsed = set(), []
            for line in lines:
                item = get_item(b, line.get('item'))
                if item.pk in seen:
                    fail('Ингредиент в рецепте не должен повторяться.')
                seen.add(item.pk)
                parsed.append(RecipeLine(product=p, item=item, quantity=decimal(line.get('qty'), minimum=Decimal('0.000001'))))
            p.recipe_lines.all().delete()
            RecipeLine.objects.bulk_create(parsed)
        elif action == 'consume':
            if not re.fullmatch(r'manual:[a-f0-9-]{36}', str(v.get('reference', ''))) or not isinstance(v.get('lines'), list) or len(v['lines']) != 1:
                fail('Некорректная операция расхода.')
            consume(b, v['lines'], v['reference'], v.get('note') or 'Расход вне заказа')
        else:
            fail('Неизвестное действие.')
        audit(request.user, 'inventory.' + action, b)
        return inventory_data(b)
