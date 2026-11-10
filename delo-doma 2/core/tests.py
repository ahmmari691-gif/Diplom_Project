import base64
import io
import json
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from openpyxl import Workbook
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from .models import (AuditLog, Business, Campaign, Consumption, Invitation, KnowledgeDocument,
                     Order, Product, RateBucket, RecipeLine, StockItem, StockMovement, User)
from .security import business_id, digest, seal, unseal
from .serializers import order_payload

from django.test import TransactionTestCase, RequestFactory
from django.db import close_old_connections
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], DELO_DEMO=False, DEMO_MODE=False, AI_MODE='local')
class PlatformTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='owner', email='owner@example.com', password='Strong-test-phrase!847', name='Владелец')
        cls.other = User.objects.create_user(username='other', email='other@example.com', password='Strong-test-phrase!847')
        cls.manager = User.objects.create_user(username='manager', email='manager@example.com', role='manager', platform_active=True)
        cls.admin = User.objects.create_user(username='admin', email='admin@example.com', role='admin', is_staff=True, is_superuser=True)
        cls.business = Business.objects.create(id=business_id(cls.owner), owner=cls.owner, name='Крошка', category='Кондитер', lead_hours=0, pickup_instructions='Частная инструкция')
        cls.other_business = Business.objects.create(id=business_id(cls.other), owner=cls.other, name='Другой бизнес', category='Ателье')
        cls.product = Product.objects.create(business=cls.business, name='Бенто-торт', price=6500)
        cls.item = StockItem.objects.create(business=cls.business, name='Клубника', unit='кг', stock=10, minimum=2)
        RecipeLine.objects.create(product=cls.product, item=cls.item, quantity=Decimal('0.5'))

    def setUp(self):
        self.c = Client()
        self.c.force_login(self.owner)
        self.anonymous = Client()

    def post(self, route, value, client=None, **extra):
        return (client or self.c).post('/api/' + route, data=json.dumps(value), content_type='application/json', **extra)

    def order(self, **extra):
        value = {'action': 'order', 'business': self.business.pk, 'product': self.product.name, 'qty': 2,
                 'total': 1, 'due': (timezone.now() + timedelta(days=3)).isoformat(), 'name': 'Частное имя',
                 'phone': 'private-contact', 'note': 'Частное пожелание', 'privacyConsent': True, 'sellerAcknowledged': True}
        value.update(extra)
        r = self.post('data', value, self.anonymous)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def status(self, order, status, client=None):
        return self.post('data', {'action': 'status', 'id': order['id'], 'status': status}, client)

    def upload(self, text='Название;Цена;Описание;Email\nБрауни;4500;Хранить 48 часов;private@example.com\n', name='catalog.csv', client=None):
        return self.post('knowledge', {'action': 'upload', 'rightsConfirmed': True, 'name': name,
                                      'base64': base64.b64encode(text.encode()).decode()}, client)

    def test_signup_never_grants_privileged_role_and_requires_terms(self):
        value = {'action': 'signup', 'email': 'new@example.com', 'password': 'Fresh-account-pass!984', 'role': 'admin', 'name': 'Новый'}
        self.assertEqual(self.post('auth', value, self.anonymous).status_code, 400)
        value['termsAccepted'] = True
        response = self.post('auth', value, self.anonymous)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['user']['role'], 'business')
        self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME]['httponly'])
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]['samesite'], 'Lax')

    def test_login_logout_and_invalid_password(self):
        self.assertEqual(self.post('auth', {'action': 'login', 'email': self.owner.email, 'password': 'incorrect-long-password'}, self.anonymous).status_code, 401)
        response = self.post('auth', {'action': 'login', 'email': self.owner.email, 'password': 'Strong-test-phrase!847'}, self.anonymous)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.post('auth', {'action': 'logout'}, self.anonymous).status_code, 200)
        self.assertEqual(self.anonymous.get('/api/data').status_code, 401)

    def test_csrf_missing_token_and_foreign_origin_are_blocked(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post('auth', {'action': 'logout'}, client).status_code, 403)
        client.get('/api/me')
        token = client.cookies['csrftoken'].value
        self.assertEqual(self.post('auth', {'action': 'logout'}, client, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN='https://evil.test').status_code, 403)
        self.assertEqual(self.post('auth', {'action': 'logout'}, client, HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_api_rejects_invalid_json_content_type_and_method(self):
        self.assertEqual(self.c.post('/api/auth', data='{}', content_type='text/plain').status_code, 403)
        self.assertEqual(self.c.post('/api/auth', data='{', content_type='application/json').status_code, 400)
        self.assertEqual(self.post('auth', []).status_code, 400)
        self.assertEqual(self.c.get('/api/auth').status_code, 405)
        self.assertEqual(self.c.get('/api/unknown').status_code, 404)

    def test_preview_unavailable_without_explicit_demo_mode(self):
        self.assertEqual(self.post('preview', {'role': 'admin'}, self.anonymous).status_code, 404)

    @override_settings(DEMO_MODE=True, DEBUG=True)
    def test_preview_rejects_remote_connections(self):
        self.assertEqual(self.post('preview', {'role': 'admin'}, self.anonymous, REMOTE_ADDR='192.0.2.4', HTTP_HOST='localhost').status_code, 404)

    @override_settings(DEMO_MODE=True, DEBUG=True)
    def test_preview_removed_even_for_local_demo(self):
        self.assertEqual(self.post('preview', {'role': 'admin'}, self.anonymous,
                                   REMOTE_ADDR='127.0.0.1', HTTP_HOST='localhost').status_code, 404)
        self.assertIsNone(self.anonymous.get('/api/me').json()['user'])
        self.assertFalse(self.anonymous.get('/api/me').json()['localPreview'])

    def test_account_role_determines_own_interface(self):
        for user, role in ((self.owner, 'business'), (self.manager, 'manager'), (self.admin, 'admin')):
            client = Client()
            client.force_login(user)
            self.assertEqual(client.get('/api/me').json()['user']['role'], role)
            self.assertFalse(client.get('/api/me').json()['localPreview'])

    def test_role_separation_including_admin_private_data(self):
        for user in (self.manager, self.admin):
            client = Client()
            client.force_login(user)
            for route in ('data', 'inventory', 'knowledge', 'analytics', 'security'):
                self.assertEqual(client.get('/api/' + route).status_code, 403, (user.role, route))
        for route in ('platform', 'admin', 'staff'):
            self.assertEqual(self.c.get('/api/' + route).status_code, 403)

    def test_public_catalog_hides_private_fields(self):
        response = self.anonymous.get('/api/data', {'business': self.business.pk})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('owner', response.json())
        self.assertNotIn('pickupInstructions', response.json())
        self.assertIn('продавец', response.json()['disclaimer'])

    def test_save_business_through_authenticated_django_request(self):
        data = {'name': 'Обновлённый бизнес', 'category': 'Услуги из дома', 'description': 'Обучение английскому',
                'currency': '₸', 'check': 10000, 'leadHours': 24, 'dailyCapacity': 8,
                'pickupArea': 'Астана', 'products': [{'name': self.product.name, 'price': 7000, 'description': 'Описание'}]}
        response = self.post('data', {'action': 'business', 'data': data})
        self.assertEqual(response.status_code, 200, response.content)
        saved = self.c.get('/api/data').json()['business']
        self.assertEqual(saved['name'], data['name'])
        self.assertEqual(saved['products'][0]['price'], 7000)
        self.assertEqual(self.product.recipe_lines.count(), 1)

    def test_first_business_save_persists_across_requests(self):
        client = Client()
        new_owner = User.objects.create_user(username='newowner', email='newowner@example.com')
        client.force_login(new_owner)
        data = {'name': 'Школа', 'category': 'Услуги из дома', 'products': [{'name': 'Урок', 'price': 1500}]}
        response = self.post('data', {'action': 'business', 'data': data}, client)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(client.get('/api/data').json()['business']['name'], 'Школа')

    @override_settings(AI_MODE='gemini')
    def test_ai_receives_education_context_and_specific_questions(self):
        self.business.category = 'Услуги из дома'
        self.business.description = 'Подготовка детей к английскому языку'
        self.business.ai_provider = 'gemini'
        self.business.ai_external_consent = True
        self.business.save()
        self.product.name = 'Месяц английского'
        self.product.save()
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-only'}), patch('core.assistant.gemini_request', return_value={
            'reply': 'Какой у вас текущий уровень?', 'ready': False, 'product': 'Месяц английского', 'qty': 1, 'due': None, 'note': None}) as model:
            r = self.post('chat', {'aiConsent': True, 'business': self.business.pk, 'messages': [{'role': 'user', 'content': 'Хочу учить английский'}]}, self.anonymous)
        self.assertEqual(r.status_code, 200)
        instructions = model.call_args.args[0]['instructions']
        self.assertIn('Месяц английского', instructions)
        self.assertIn('Какой текущий уровень?', instructions)
        self.assertIn('не превращай месячный абонемент в отдельные уроки', instructions)
        self.assertEqual(r.json()['product'], 'Месяц английского')

    def test_local_service_assistant_does_not_use_food_language(self):
        self.business.category = 'Услуги из дома'
        self.business.description = 'Индивидуальные уроки английского'
        self.business.save()
        self.product.name = 'Пробный урок'
        self.product.save()
        r = self.post('chat', {'aiConsent': True, 'business': self.business.pk, 'messages': [{'role': 'user', 'content': 'Хочу пробный урок'}],
                               'draft': {'product': 'Пробный урок', 'qty': 1}}, self.anonymous)
        self.assertEqual(r.status_code, 200)
        self.assertIn('занятия', r.json()['reply'])
        self.assertNotIn('шт.', r.json()['reply'])

    def test_manual_business_format_and_tracking_labels(self):
        data = {'name': 'Универсальный бизнес', 'category': 'Другое', 'businessType': 'education',
                'products': [{'name': self.product.name, 'price': 6500}]}
        r = self.post('data', {'action': 'business', 'data': data})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['experience']['kind'], 'education')
        order = self.order()
        tracked = self.anonymous.get('/api/data', {'track': order['id'], 'token': order['token']}).json()
        self.assertEqual(tracked['experience']['statuses']['ready'], 'Запись подтверждена')
        self.assertEqual(tracked['experience']['dueLabel'], 'Дата и время занятия')
        self.assertEqual(tracked['data']['total'], 13000)

    def test_order_requires_both_consents_and_uses_server_price(self):
        for key in ('privacyConsent', 'sellerAcknowledged'):
            r = self.post('data', {'action': 'order', key: False}, self.anonymous)
            self.assertEqual(r.status_code, 400)
        order = self.order()
        r = self.anonymous.get('/api/data', {'track': order['id'], 'token': order['token']})
        self.assertEqual(r.json()['data']['total'], 13000)
        self.assertEqual(r.json()['pickupInstructions'], '')
        stored = Order.objects.get(pk=order['id'].split('.')[0])
        self.assertNotIn('private-contact', stored.encrypted_data)
        self.assertEqual(stored.token_hash, digest(order['token']))
        self.assertNotEqual(stored.token_hash, order['token'])

    def test_tracking_token_and_invalid_reference(self):
        order = self.order()
        for reference, token in [(order['id'], 'wrong'), ('invalid', order['token']), ('-' * 36 + '.' + self.business.pk, order['token'])]:
            self.assertEqual(self.anonymous.get('/api/data', {'track': reference, 'token': token}).status_code, 404)

    def test_other_tenant_cannot_read_or_change_order(self):
        order = self.order()
        client = Client()
        client.force_login(self.other)
        self.assertEqual(self.status(order, 'working', client).status_code, 403)
        self.assertEqual(client.get('/api/data').json()['orders'], [])

    def test_cancellation_cutoff_enforced_on_server(self):
        early = self.order()
        self.assertEqual(self.post('data', {'action': 'cancel', **early}, self.anonymous).status_code, 200)
        late = self.order(due=(timezone.now() + timedelta(hours=12)).isoformat())
        self.assertEqual(self.post('data', {'action': 'cancel', **late}, self.anonymous).status_code, 403)
        self.assertEqual(Order.objects.get(pk=late['id'].split('.')[0]).status, 'new')

    def test_lead_time_and_quantities_are_validated(self):
        for qty in (-1, 0, 1.5, 1001, True, 'NaN'):
            self.assertEqual(self.post('data', {'action': 'order', 'business': self.business.pk, 'product': self.product.name,
                'qty': qty, 'privacyConsent': True, 'sellerAcknowledged': True}, self.anonymous).status_code, 400)
        self.product.lead_hours = 24
        self.product.save()
        self.assertEqual(self.post('data', {'action': 'order', 'business': self.business.pk, 'product': self.product.name,
            'qty': 1, 'due': (timezone.now()+timedelta(hours=12)).isoformat(), 'privacyConsent': True, 'sellerAcknowledged': True}, self.anonymous).status_code, 400)

    def test_ready_deducts_recipe_exactly_once(self):
        order = self.order()
        self.assertEqual(self.status(order, 'working').status_code, 200)
        self.assertEqual(self.status(order, 'ready').status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 9)
        self.assertEqual(Consumption.objects.count(), 1)
        self.assertEqual(self.status(order, 'ready').status_code, 400)
        self.assertEqual(self.status(order, 'done').status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 9)

    def test_shortage_rolls_back_all_ingredients_and_order_status(self):
        flour = StockItem.objects.create(business=self.business, name='Мука', unit='кг', stock=Decimal('0.1'))
        RecipeLine.objects.create(product=self.product, item=flour, quantity=1)
        order = self.order()
        self.status(order, 'working')
        self.assertEqual(self.status(order, 'ready').status_code, 409)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 10)
        self.assertEqual(Order.objects.get(pk=order['id'].split('.')[0]).status, 'working')
        self.assertEqual(Consumption.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_manual_consumption_idempotency_and_insufficient_stock(self):
        value = {'action': 'consume', 'reference': 'manual:' + str(uuid.uuid4()), 'lines': [{'item': str(self.item.pk), 'qty': 1}]}
        for _ in range(2):
            self.assertEqual(self.post('inventory', value).status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 9)
        value.update(reference='manual:' + str(uuid.uuid4()), lines=[{'item': str(self.item.pk), 'qty': 99}])
        self.assertEqual(self.post('inventory', value).status_code, 409)

    def test_inventory_receive_and_tenant_recipe_isolation(self):
        self.assertEqual(self.post('inventory', {'action': 'receive', 'item': str(self.item.pk), 'qty': -1}).status_code, 400)
        self.assertEqual(self.post('inventory', {'action': 'receive', 'item': str(self.item.pk), 'qty': 2}).status_code, 200)
        foreign = StockItem.objects.create(business=self.other_business, name='Чужое', unit='кг', stock=10)
        self.assertEqual(self.post('inventory', {'action': 'recipe', 'product': self.product.name, 'lines': [{'item': str(foreign.pk), 'qty': 1}]}).status_code, 404)

    def test_upload_discards_sensitive_columns_and_encrypts_data(self):
        r = self.upload()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('Email', r.json()['ignoredColumns'])
        self.assertNotIn('private@example.com', r.content.decode())
        doc = KnowledgeDocument.objects.get(pk=r.json()['id'])
        self.assertNotIn('Хранить', doc.encrypted_payload)
        other = Client()
        other.force_login(self.other)
        self.assertEqual(other.get('/api/knowledge', {'id': str(doc.pk)}).status_code, 404)

    def test_upload_rejects_secrets_macros_and_spoofed_excel(self):
        self.assertEqual(self.upload('Вопрос;Ответ\nКак связаться;secret@example.com\n').status_code, 400)
        self.assertEqual(self.upload(name='bad.xlsm').status_code, 400)
        self.assertEqual(self.upload('Not an Excel', name='bad.xlsx').status_code, 400)
        self.assertEqual(self.post('knowledge', {'action': 'upload', 'rightsConfirmed': False}).status_code, 400)

    def test_actual_xlsx_skips_formulas_and_rejects_external_links(self):
        book = Workbook()
        sheet = book.active
        sheet.append(['Название', 'Цена', 'Описание'])
        sheet.append(['Чизкейк', 5500, 'Ванильный'])
        sheet.append(['Формула', '=1+1', 'Не выполнять'])
        def upload_book():
            output = io.BytesIO()
            book.save(output)
            return self.post('knowledge', {'action': 'upload', 'rightsConfirmed': True, 'name': 'catalog.xlsx',
                                          'base64': base64.b64encode(output.getvalue()).decode()})
        response = upload_book()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['formulaCount'], 1)
        self.assertEqual(len(response.json()['candidates']), 1)
        sheet['A2'].hyperlink = 'https://example.com'
        self.assertEqual(upload_book().status_code, 400)

    def test_knowledge_activation_retrieval_and_deletion(self):
        doc = self.upload().json()
        foreign_client = Client()
        foreign_client.force_login(self.other)
        other_doc = self.upload('Вопрос;Ответ\nХранить брауни;FOREIGN_TENANT_SECRET\n', client=foreign_client).json()
        self.post('knowledge', {'action': 'activate', 'id': other_doc['id'], 'columns': other_doc['columns'], 'confirmed': True}, foreign_client)
        chat = {'business': self.business.pk, 'aiConsent': True, 'messages': [{'role': 'user', 'content': 'Как хранить брауни?'}], 'draft': {}}
        self.assertEqual(self.post('chat', {**chat, 'aiConsent': False}, self.anonymous).status_code, 400)
        self.assertEqual(self.post('chat', chat, self.anonymous).json()['sources'], [])
        self.assertEqual(self.post('knowledge', {'action': 'activate', 'id': doc['id'], 'columns': ['Email'], 'confirmed': True}).status_code, 400)
        self.assertEqual(self.post('knowledge', {'action': 'activate', 'id': doc['id'], 'columns': doc['columns'], 'confirmed': False}).status_code, 400)
        self.assertEqual(self.post('knowledge', {'action': 'activate', 'id': doc['id'], 'columns': doc['columns'], 'confirmed': True}).status_code, 200)
        reply = self.post('chat', chat, self.anonymous)
        self.assertEqual(reply.status_code, 200, reply.content)
        self.assertEqual(reply.json()['sources'][0]['id'], doc['id'])
        self.assertNotIn('FOREIGN_TENANT_SECRET', reply.content.decode())
        self.post('knowledge', {'action': 'delete', 'id': doc['id']})
        self.assertEqual(self.post('chat', chat, self.anonymous).json()['sources'], [])

    def test_catalog_import_keeps_exact_prices_and_existing_recipe(self):
        doc = self.upload().json()
        r = self.post('knowledge', {'action': 'import_catalog', 'id': doc['id'], 'confirmed': True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Product.objects.get(business=self.business, name='Брауни').price, 4500)
        self.assertEqual(self.product.recipe_lines.count(), 1)

    def test_platform_manager_sees_aggregates_without_decryption(self):
        self.order()
        client = Client()
        client.force_login(self.manager)
        with patch('core.serializers.unseal', side_effect=AssertionError('Should not decrypt')):
            r = client.get('/api/platform')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['metrics']['businesses'], 2)
        self.assertNotIn('private-contact', r.content.decode())
        self.assertNotIn('Частное имя', r.content.decode())
        self.assertEqual(client.get('/api/staff').status_code, 403)

    def test_platform_campaigns_and_tasks_do_not_belong_to_business(self):
        client = Client()
        client.force_login(self.manager)
        c = self.post('platform', {'action': 'campaign', 'name': 'Развитие', 'source': 'instagram', 'cost': 5000}, client)
        self.assertEqual(c.status_code, 200)
        self.assertEqual(c.json()['scope'], 'platform')
        self.assertNotIn('business', c.json())
        task = self.post('platform', {'action': 'task', 'title': 'Проверить регистрацию'}, client).json()
        self.assertEqual(self.post('platform', {'action': 'task_status', 'id': task['id'], 'status': 'working'}, client).status_code, 200)
        self.assertEqual(self.post('campaigns', {'name': 'Нет', 'source': 'other'}, client).status_code, 403)

    def test_manager_invitation_email_binding_and_revoke(self):
        admin = Client()
        admin.force_login(self.admin)
        self.assertEqual(self.post('staff', {'action': 'invite', 'email': 'newmanager@example.com'}).status_code, 403)
        invitation = self.post('staff', {'action': 'invite', 'email': 'newmanager@example.com'}, admin).json()
        signup = {'action': 'signup', 'email': 'wrong@example.com', 'password': 'Fresh-account-pass!984', 'termsAccepted': True, 'invite': invitation['token']}
        self.assertEqual(self.post('auth', signup, self.anonymous).status_code, 403)
        signup['email'] = 'newmanager@example.com'
        r = self.post('auth', signup, self.anonymous)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['user']['role'], 'manager')
        self.assertNotIn('businessId', r.json()['user'])
        self.assertEqual(self.anonymous.get('/api/platform').status_code, 200)
        self.assertEqual(self.post('staff', {'action': 'revoke', 'id': r.json()['user']['id']}, admin).status_code, 200)
        self.assertEqual(self.anonymous.get('/api/platform').status_code, 401)

    def test_pause_business_blocks_new_orders_not_existing_tracking(self):
        order = self.order()
        admin = Client()
        admin.force_login(self.admin)
        self.assertEqual(self.post('admin', {'action': 'set_status', 'business': self.business.pk, 'status': 'paused', 'reason': 'Проверка бизнеса'}, admin).status_code, 200)
        self.assertEqual(self.post('data', {'action': 'order', 'business': self.business.pk, 'privacyConsent': True, 'sellerAcknowledged': True}, self.anonymous).status_code, 403)
        self.assertEqual(self.anonymous.get('/api/data', {'track': order['id'], 'token': order['token']}).status_code, 200)

    def test_anonymization_and_scheduled_retention_keep_totals(self):
        order = self.order()
        self.assertEqual(self.post('data', {'action': 'anonymize', 'id': order['id']}).status_code, 400)
        o = Order.objects.get(pk=order['id'].split('.')[0])
        o.status = 'done'
        o.save()
        Order.objects.filter(pk=o.pk).update(updated=timezone.now() - timedelta(days=91))
        with io.StringIO() as output:
            call_command('purge_contacts', stdout=output)
        o.refresh_from_db()
        self.assertEqual(order_payload(o)['phone'], '')
        self.assertEqual(order_payload(o)['total'], 13000)
        self.assertIsNotNone(o.anonymized)

    def test_sessions_revoked_and_audit_contains_no_customer_contact(self):
        self.order()
        self.assertNotIn('private-contact', json.dumps(list(AuditLog.objects.values()), default=str))
        self.post('auth', {'action': 'login', 'email': self.owner.email, 'password': 'Strong-test-phrase!847'})
        self.assertEqual(self.post('security', {'action': 'revoke_sessions'}).status_code, 200)
        self.assertEqual(self.c.get('/api/data').status_code, 401)

    def test_visit_requires_opt_in_and_business_analytics(self):
        self.assertFalse(self.post('events', {'analyticsConsent': False}, self.anonymous).json()['recorded'])
        self.assertTrue(self.post('events', {'analyticsConsent': True, 'business': self.business.pk}, self.anonymous).json()['recorded'])
        self.order()
        stats = self.c.get('/api/analytics').json()
        self.assertEqual(stats['metrics']['orderValue'], 13000)
        self.assertEqual(stats['metrics']['consentedViews'], 1)

    def test_rate_limiting_and_ciphertext_scope(self):
        for _ in range(12):
            self.post('chat', {'aiConsent': True, 'business': self.business.pk, 'messages': [{'role': 'user', 'content': 'Привет'}]}, self.anonymous)
        self.assertEqual(self.post('chat', {'aiConsent': True, 'business': self.business.pk, 'messages': [{'role': 'user', 'content': 'Привет'}]}, self.anonymous).status_code, 429)
        value = seal({'secret': 'private'}, 'business:a')
        with self.assertRaises(Exception):
            unseal(value, 'business:b')

    @override_settings(AI_MODE='model')
    def test_external_ai_requires_owner_consent_and_validates_output(self):
        chat = {'aiConsent': True, 'business': self.business.pk, 'messages': [{'role': 'user', 'content': 'Хочу торт'}], 'draft': {}}
        self.assertEqual(self.post('chat', chat, self.anonymous).status_code, 503)
        self.business.ai_external_consent = True
        self.business.save()
        with patch('core.assistant.api_key', return_value='test-only'), patch('core.assistant.model_request', return_value={
                'reply': 'Черновик', 'ready': True, 'product': 'Выдуманный товар', 'qty': 2, 'due': '2027-01-01T12:00', 'note': None}):
            r = self.post('chat', chat, self.anonymous)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()['ready'])
        self.assertIsNone(r.json()['product'])
        self.assertEqual(Order.objects.count(), 0)

    def test_encrypted_security_headers(self):
        response = self.c.get('/api/me')
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        self.assertIn("frame-ancestors 'none'", response['Content-Security-Policy'])

    @override_settings(AI_MODE='gemini')
    def test_gemini_needs_separate_provider_consent(self):
        self.business.ai_external_consent = True
        self.business.ai_provider = 'openai'
        self.business.save()
        chat = {'aiConsent': True, 'business': self.business.pk, 'messages': [{'role': 'user', 'content': 'Хочу торт'}]}
        with patch('core.assistant.gemini_request') as transport:
            self.assertEqual(self.post('chat', chat, self.anonymous).status_code, 503)
            transport.assert_not_called()

    @override_settings(AI_MODE='gemini')
    def test_gemini_transport_and_server_validation(self):
        self.business.ai_external_consent = True
        self.business.ai_provider = 'gemini'
        self.business.save()
        text = json.dumps({'reply': 'Выберите время получения', 'ready': False, 'product': self.product.name,
                           'qty': 2, 'due': None, 'note': None})
        response = io.BytesIO(json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': text}]}}]}).encode())
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-only-gemini'}), patch('urllib.request.urlopen', return_value=response) as transport:
            result = self.post('chat', {'aiConsent': True, 'business': self.business.pk, 'messages': [
                {'role': 'user', 'content': 'Хочу торт'}, {'role': 'assistant', 'content': 'Сколько нужно?'},
                {'role': 'user', 'content': 'Два'}]}, self.anonymous)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['product'], self.product.name)
        self.assertFalse(result.json()['ready'])
        request = transport.call_args.args[0]
        payload = json.loads(request.data)
        self.assertIn('generativelanguage.googleapis.com', request.full_url)
        self.assertNotIn('test-only-gemini', request.full_url)
        self.assertEqual([m['role'] for m in payload['contents']], ['user', 'model', 'user'])
        self.assertEqual(payload['generationConfig']['responseMimeType'], 'application/json')
        self.assertIn('responseJsonSchema', payload['generationConfig'])
        self.assertNotIn('test-only-gemini', result.content.decode())
        self.assertEqual(Order.objects.count(), 0)

    @override_settings(AI_MODE='gemini')
    def test_gemini_quota_error_is_safe_and_does_not_fallback_to_paid_provider(self):
        from urllib.error import HTTPError
        self.business.ai_external_consent = True
        self.business.ai_provider = 'gemini'
        self.business.save()
        error = HTTPError('https://generativelanguage.googleapis.com', 429, 'Quota', {}, io.BytesIO(b'private-provider-error'))
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-only'}), patch('urllib.request.urlopen', side_effect=error), patch('core.assistant.model_request') as other:
            result = self.post('chat', {'aiConsent': True, 'business': self.business.pk, 'messages': [{'role': 'user', 'content': 'Привет'}]}, self.anonymous)
        self.assertEqual(result.status_code, 429)
        self.assertEqual(result.json()['code'], 'ai_quota')
        self.assertNotIn('private-provider-error', result.content.decode())
        other.assert_not_called()

    @override_settings(AI_MODE='gemini')
    def test_gemini_retries_once_after_transport_failure(self):
        from urllib.error import URLError
        self.business.ai_external_consent = True
        self.business.ai_provider = 'gemini'
        self.business.save()
        text = json.dumps({'reply': 'Сколько уроков нужно?', 'ready': False, 'product': None, 'qty': None, 'due': None, 'note': None})
        response = io.BytesIO(json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': text}]}}]}).encode())
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-only'}), patch('core.assistant.time.sleep'), patch('urllib.request.urlopen', side_effect=[URLError('temporary'), response]) as transport:
            result = self.post('chat', {'aiConsent': True, 'business': self.business.pk, 'messages': [{'role': 'user', 'content': 'Привет'}]}, self.anonymous)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(transport.call_count, 2)

    @override_settings(AI_MODE='gemini')
    def test_network_reset_is_distinguished_from_provider_response_error(self):
        from urllib.error import URLError
        self.business.ai_external_consent = True
        self.business.ai_provider = 'gemini'
        self.business.save()
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-only'}), patch('core.assistant.time.sleep'), patch('urllib.request.urlopen', side_effect=URLError(ConnectionResetError('private-error-text'))), self.assertLogs('core.assistant', level='WARNING') as logs:
            result = self.post('chat', {'aiConsent': True, 'business': self.business.pk, 'messages': [{'role': 'user', 'content': 'Привет'}]}, self.anonymous)
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json()['code'], 'ai_network')
        self.assertIn('connection_reset', logs.output[0])
        self.assertNotIn('private-error-text', str(logs.output))
        self.assertNotIn('test-only', str(logs.output))

    def test_diagnostic_does_not_call_api_when_tls_fails(self):
        output = io.StringIO()
        with patch('socket.getaddrinfo', return_value=[]), patch('socket.create_connection', side_effect=ConnectionResetError()), patch('core.management.commands.diagnose_gemini.gemini_request') as model:
            call_command('diagnose_gemini', with_api=True, as_json=True, stdout=output)
        report = json.loads(output.getvalue())
        self.assertTrue(report['dns'])
        self.assertFalse(report['tls'])
        self.assertEqual(report['failure'], 'connection_reset')
        self.assertFalse(report['apiChecked'])
        model.assert_not_called()

    @override_settings(AI_MODE='model')
    def test_model_transport_uses_responses_schema_and_disables_history(self):
        self.business.ai_external_consent = True
        self.business.save()
        text = json.dumps({'reply': 'Проверьте заказ', 'ready': True, 'product': self.product.name,
                           'qty': 2, 'due': (timezone.now() + timedelta(days=3)).isoformat(), 'note': None})
        response = io.BytesIO(json.dumps({'output': [{'content': [{'type': 'output_text', 'text': text}]}]}).encode())
        with patch('core.assistant.api_key', return_value='test-only'), patch('urllib.request.urlopen', return_value=response) as transport:
            r = self.post('chat', {'aiConsent': True, 'business': self.business.pk,
                                  'messages': [{'role': 'user', 'content': 'Хочу торт'}]}, self.anonymous)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['ready'])
        payload = json.loads(transport.call_args.args[0].data)
        self.assertFalse(payload['store'])
        self.assertEqual(payload['text']['format']['type'], 'json_schema')
        self.assertEqual(Order.objects.count(), 0)

class ConcurrentStockTests(TransactionTestCase):
    def test_simultaneous_ready_requests_cannot_double_consume(self):
        from .views import api
        owner = User.objects.create(username='parallel', email='parallel@example.com')
        b = Business.objects.create(id=business_id(owner), owner=owner, name='Параллельный тест')
        p = Product.objects.create(business=b, name='Торт', price=1000)
        item = StockItem.objects.create(business=b, name='Клубника', unit='кг', stock=10)
        RecipeLine.objects.create(product=p, item=item, quantity=Decimal('0.5'))
        order = Order.objects.create(business=b, status='working', token_hash='x' * 64,
            due=timezone.now() + timedelta(days=3), encrypted_data=seal({'product': 'Торт', 'qty': 2}, 'order:' + b.pk))
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            try:
                request = RequestFactory().post('/api/data', data=json.dumps({'action': 'status', 'id': str(order.pk) + '.' + b.pk, 'status': 'ready'}), content_type='application/json')
                request.user = owner
                barrier.wait(timeout=5)
                return api(request, 'data').status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(lambda _: worker(), range(2)))
        self.assertIn(200, codes)
        self.assertTrue(all(code in (200, 400, 409) for code in codes), codes)
        item.refresh_from_db()
        self.assertEqual(item.stock, 9)
        self.assertEqual(Consumption.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)

class ImportTests(TestCase):
    def test_legacy_import_reencrypts_and_preserves_password_and_stock(self):
        import tempfile
        import hashlib
        from pathlib import Path
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from django.core.management.base import CommandError
        owner_id = str(uuid.uuid4())
        bid = digest('business:' + owner_id)[:32]
        old_key = secrets.token_bytes(32)
        password = 'Migrated-passphrase!743'
        salt = '0123456789abcdef'
        old_hash = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64).hex()
        def encrypted(data, scope):
            nonce = secrets.token_bytes(12)
            result = AESGCM(old_key).encrypt(nonce, json.dumps(data).encode(), scope.encode())
            return {'encrypted': True, 'iv': base64.b64encode(nonce).decode(), 'body': base64.b64encode(result[:-16]).decode(), 'tag': base64.b64encode(result[-16:]).decode()}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'encryption.key').write_text(base64.b64encode(old_key).decode())
            root = source / 'blobs' / 'entries' / 'site' / 'site:local'
            def write(path, value):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(value))
            now = int(timezone.now().timestamp() * 1000)
            write('profiles/' + owner_id, {'id': owner_id, 'email': 'import@example.com', 'name': 'Импорт', 'role': 'business'})
            write('users/account', {'id': owner_id, 'salt': salt, 'password': old_hash})
            write('business/' + bid, {'id': bid, 'owner': owner_id, 'name': 'Импорт', 'created': now, 'products': [{'name': 'Торт', 'price': 1000}]})
            oid = str(uuid.uuid4())
            write('orders/' + bid + '/' + oid, {'id': oid + '.' + bid, 'business': bid, 'tokenHash': digest('tracking'),
                'status': 'working', 'created': now, 'due': now + 3 * 86400000,
                'data': encrypted({'name': 'Частный клиент', 'phone': 'private-import-contact', 'product': 'Торт', 'qty': 1, 'total': 1000}, 'order:' + bid)})
            with io.StringIO() as output:
                call_command('import_netlify', source, stdout=output)
            user = User.objects.get(pk=owner_id)
            self.assertTrue(user.check_password(password))
            self.assertTrue(user.password.startswith('pbkdf2_sha256$'))
            order = Order.objects.get(pk=oid)
            self.assertEqual(order_payload(order)['phone'], 'private-import-contact')
            self.assertNotIn('private-import-contact', order.encrypted_data)
            self.assertEqual(json.loads((root / ('orders/' + bid + '/' + oid)).read_text())['status'], 'working')
            with self.assertRaises(CommandError):
                call_command('import_netlify', source, stdout=io.StringIO())

class BusinessExperienceTests(TestCase):
    def test_auto_formats_and_safe_generic_fallback(self):
        from .experience import experience
        cases = [('Услуги из дома', 'Готовлю детей к англискому', 'Пробный урок', 'education'),
                 ('Домашняя кондитерская', 'Десерты по заказу', 'Бенто-торт', 'food'),
                 ('Красота на дому', 'Уход и маникюр', 'Маникюр', 'beauty'),
                 ('Цветы и растения', 'Букеты', 'Букет роз', 'flowers'),
                 ('Керамика', 'Ручная работа', 'Чашка', 'craft'),
                 ('Керамика ручной работы', 'Старое тестовое описание: десерты', 'Чашка', 'craft'),
                 ('Услуги', 'Ремонт техники', 'Диагностика', 'services'),
                 ('Магазин', 'Продажа товаров', 'Товар', 'retail'),
                 ('Другое', 'Описание без специальной терминологии', 'Предложение', 'other')]
        for i, (category, description, name, expected) in enumerate(cases):
            with self.subTest(expected=expected):
                owner = User.objects.create(username='sector-'+str(i), email='sector-'+str(i)+'@example.com')
                b = Business.objects.create(id=business_id(owner), owner=owner, name='Бизнес', category=category, description=description)
                Product.objects.create(business=b, name=name, price=1000)
                profile = experience(b)
                self.assertEqual(profile['kind'], expected)
                self.assertTrue(profile['quickQuestions'])
                if expected != 'food':
                    self.assertNotIn('десерт', profile['welcome'].lower())
                    self.assertNotIn('торт', profile['notePlaceholder'].lower())

@override_settings(AI_MODE='gemini')
class SiteHelpTests(TestCase):
    def post(self, **overrides):
        value = {'message': 'Where are prices?', 'language':'en', 'consent':True, 'page':'workspace'}
        value.update(overrides)
        return self.client.post('/api/help', json.dumps(value), content_type='application/json')

    def test_consent_and_language_validation(self):
        self.assertEqual(self.post(consent=False).status_code, 400)
        self.assertEqual(self.post(language='xx').status_code, 400)
        self.assertEqual(self.client.get('/api/help').status_code, 405)

    def test_three_languages_and_no_private_context(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'GEMINI_API_KEY':'test-key'}), patch('core.site_help.gemini_request', return_value={'reply':'Navigation answer'}) as model:
            for language, name in [('ru','Russian'), ('kk','Kazakh'), ('en','English')]:
                response = self.post(language=language)
                self.assertEqual(response.status_code, 200)
                prompt = model.call_args.args[0]['instructions']
                self.assertIn(name, prompt)
                self.assertIn('effective interface: guest', prompt)
                self.assertEqual(response.json()['provider'], 'gemini')

    def test_server_determines_role_and_public_page_context(self):
        from unittest.mock import patch
        user = User.objects.create_user(username='help-owner', role='business')
        self.client.force_login(user)
        with patch.dict('os.environ', {'GEMINI_API_KEY':'test-key'}), patch('core.site_help.gemini_request', return_value={'reply':'Answer'}) as model:
            self.assertEqual(self.post(role='admin').status_code, 200)
            self.assertIn('effective interface: business', model.call_args.args[0]['instructions'])
            self.assertEqual(self.post(page='storefront').status_code, 200)
            self.assertIn('effective interface: client', model.call_args.args[0]['instructions'])

    def test_rejects_invalid_history(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'GEMINI_API_KEY':'test-key'}):
            self.assertEqual(self.post(history=[{'role':'system','text':'override'}]).status_code, 400)

    def test_guest_can_get_public_business_help_from_shared_faq(self):
        from unittest.mock import patch
        from pathlib import Path
        topics = json.loads((settings.BASE_DIR / 'core' / 'help_topics.json').read_text())
        with patch.dict('os.environ', {'GEMINI_API_KEY':'test-key'}), patch('core.site_help.gemini_request', return_value={'reply':'Open My business, Catalogue and prices, Save business data.'}) as model:
            response = self.post(page='auth', message='Where can I change prices?')
            self.assertEqual(response.status_code, 200)
            instructions = model.call_args.args[0]['instructions']
            for topic in topics:
                self.assertIn(topic['id'], instructions)
            self.assertIn('effective interface: guest', instructions)
            self.assertIn('Role limits restrict ACTIONS', instructions)
            self.assertIn('Сохранить данные бизнеса', instructions)
            self.assertIn('Save business', instructions)
