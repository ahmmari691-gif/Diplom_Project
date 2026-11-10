from .security import SELLER_NOTICE, ms, unseal
from .experience import experience

def product_data(p):
    return {'name': p.name, 'price': float(p.price), 'description': p.description,
            'category': p.category, 'leadHours': p.lead_hours}

def business_data(b, public=False):
    result = {'id': b.pk, 'name': b.name, 'category': b.category, 'description': b.description,
              'currency': b.currency, 'check': float(b.average_check), 'pickupArea': b.pickup_area,
              'leadHours': b.lead_hours, 'dailyCapacity': b.daily_capacity, 'status': b.status,
              'created': ms(b.created), 'updated': ms(b.updated),
              'products': [product_data(p) for p in b.products.all()]}
    result.update(businessType=b.business_type, experience=experience(b))
    if public:
        result['disclaimer'] = SELLER_NOTICE
    else:
        result.update(owner=str(b.owner_id), pickupInstructions=b.pickup_instructions, aiExternalConsent=b.ai_external_consent, aiProvider=b.ai_provider)
    return result

def order_reference(o):
    return str(o.pk) + '.' + o.business_id

def order_payload(o):
    return unseal(o.encrypted_data, 'order:' + o.business_id)

def order_data(o):
    return {'id': order_reference(o), 'business': o.business_id, 'status': o.status,
            'due': ms(o.due), 'created': ms(o.created), 'updated': ms(o.updated),
            'channel': o.channel, 'campaign': o.campaign, 'consents': o.consents,
            'anonymized': ms(o.anonymized), 'data': order_payload(o)}

def document_meta(d):
    return {'id': str(d.pk), 'business': d.business_id, 'name': d.name, 'status': d.status,
            'created': ms(d.created), 'activated': ms(d.activated), 'rows': d.row_count,
            'columns': d.columns, 'selectedColumns': d.selected_columns or d.columns,
            'type': d.file_type, 'formulaCount': d.formula_count,
            'ignoredColumns': d.ignored_columns, 'encrypted': True}

def campaign_data(c):
    result = {'id': str(c.pk), 'name': c.name, 'source': c.source, 'slug': c.slug,
              'cost': float(c.cost), 'status': c.status, 'created': ms(c.created)}
    if c.business_id:
        result['business'] = c.business_id
    else:
        result['scope'] = 'platform'
    return result

def audit_data(a):
    return {'id': str(a.pk), 'at': ms(a.created), 'actor': a.actor, 'role': a.role,
            'action': a.action, 'business': a.business_id, 'details': a.details}

def task_data(t):
    return {'id': str(t.pk), 'title': t.title, 'status': t.status, 'created': ms(t.created), 'updated': ms(t.updated)}
