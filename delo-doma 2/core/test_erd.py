"""Regression coverage for guest buyers, normalized relations and platform roles."""
import base64
import json
from datetime import timedelta
from decimal import Decimal
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from .models import (Account, User, Business, Product, Order, OrderConsent, OrderStatusHistory,
                     ProviderConsent, AuditLog, Invitation, KnowledgeDocument)
from .security import unseal

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ERDTests(TestCase):
    def setUp(self):
        self.owner = Account.objects.create_user(username='owner', email='owner@example.test')
        self.manager = Account.objects.create_user(username='manager', email='manager@example.test', role='manager', platform_active=True)
        self.admin = Account.objects.create_user(username='admin', email='admin@example.test', role='admin')
        self.business = Business.objects.create(id='a'*32, owner=self.owner, name='Бизнес', lead_hours=0)
        self.product = Product.objects.create(catalogue=self.business.default_catalogue(), name='Товар', price=Decimal('12.30'))
        self.guest = Client()
        self.staff = Client(); self.staff.force_login(self.manager)
        self.admin_client = Client(); self.admin_client.force_login(self.admin)
        self.owner_client = Client(); self.owner_client.force_login(self.owner)

    def post(self, route, data, client=None):
        return (client or self.guest).post('/api/'+route, json.dumps(data), content_type='application/json')

    def checkout(self):
        r = self.post('data', {'action':'order','business':self.business.pk,'product':self.product.name,
            'qty':2,'due':(timezone.now()+timedelta(days=3)).isoformat(),
            'name':'Guest private name','phone':'private-contact','note':'private note',
            'privacyConsent':True,'sellerAcknowledged':True,'aiConsent':False, 'user':'forged'})
        self.assertEqual(r.status_code, 200, r.content)
        return r.json(), Order.objects.latest('created')

    def test_guest_is_not_an_account_and_business_only_connected_through_order(self):
        response, order = self.checkout()
        self.assertEqual(Account.objects.count(), 3)
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(any(f.name in ('business', 'owner', 'password', 'email', 'phone') for f in User._meta.fields))
        self.assertEqual(order.business, self.business)
        self.assertEqual(order.reference, response['id'])
        self.assertEqual(order.total, Decimal('24.60'))
        self.assertNotIn('Guest private name', order.encrypted_data)
        self.assertEqual(unseal(order.encrypted_data, 'order:'+self.business.pk)['name'], 'Guest private name')
        self.assertEqual(self.guest.get('/api/data', {'track':response['id'],'token':response['token']}).status_code, 200)
        self.assertEqual(self.guest.get('/api/data', {'track':response['id'],'token':'wrong'}).status_code, 404)
        self.assertTrue(order.consent.personal_data)
        self.assertTrue(order.consent.seller_acknowledged)
        self.assertFalse(order.consent.external_ai)
        self.assertEqual(order.status_history.get().customer, order.user)
        self.assertEqual(order.audit_events.get().action, 'order.created')
        self.assertEqual(self.product.catalogue.business, self.business)
        self.assertEqual(self.product.catalogue.created_by, self.owner)

    def test_history_links_owner_and_guest_without_granting_staff_order_access(self):
        response, order = self.checkout()
        change={'action':'status','id':response['id'],'status':'working'}
        for client in (self.staff,self.admin_client):
            self.assertEqual(self.post('data',change,client).status_code,403)
        self.assertEqual(self.post('data',change,self.owner_client).status_code,200)
        h=order.status_history.get(to_status='working')
        self.assertEqual(h.changed_by,self.owner); self.assertIsNone(h.customer)
        self.assertEqual(self.post('data',{'action':'cancel',**response}).status_code,200)
        self.assertEqual(order.status_history.get(to_status='cancelled').customer,order.user)
        audit=order.audit_events.get(action='order.status_changed',actor_account=self.owner)
        self.assertEqual(audit.order,order)

    def test_manager_and_admin_manage_profiles_but_only_admin_pauses_business(self):
        for client in (self.staff,self.admin_client):
            self.assertEqual(client.get('/api/operations').status_code,200)
            self.assertEqual(self.post('operations',{'action':'update_business','business':self.business.pk,'name':'Обновлено'},client).status_code,200)
        self.assertEqual(self.owner_client.get('/api/operations').status_code,403)
        self.assertEqual(self.guest.get('/api/operations').status_code,401)
        self.assertEqual(self.post('operations',{'action':'update_business','business':self.business.pk,'status':'paused'},self.staff).status_code,403)
        pause={'action':'set_status','business':self.business.pk,'status':'paused','reason':'Test pause'}
        self.assertEqual(self.post('admin',pause,self.staff).status_code,403)
        self.assertEqual(self.post('admin',pause,self.admin_client).status_code,200)
        self.business.refresh_from_db(); self.assertEqual(self.business.status,'paused')
        self.manager.platform_active=False;self.manager.save()
        self.assertEqual(self.staff.get('/api/operations').status_code,401)

    def test_staff_document_workflow_and_owner_isolation(self):
        upload={'action':'upload','business':self.business.pk,'name':'faq.txt','rightsConfirmed':True,
                'base64':base64.b64encode('Вопрос | Ответ\nДоставка | Самовывоз'.encode()).decode()}
        r=self.post('platform_knowledge',upload,self.staff)
        self.assertEqual(r.status_code,200,r.content)
        doc=KnowledgeDocument.objects.get(pk=r.json()['id'])
        self.assertEqual(doc.uploaded_by,self.manager)
        route='/api/platform_knowledge?business='+self.business.pk+'&id='+str(doc.pk)
        self.assertEqual(self.staff.get(route).status_code,200)
        self.assertEqual(self.guest.get(route).status_code,401)
        self.assertEqual(self.owner_client.get(route).status_code,403)
        self.assertEqual(self.post('platform_knowledge',{'action':'import_catalog','business':self.business.pk,'id':str(doc.pk)},self.staff).status_code,403)
        activate={'action':'activate','business':self.business.pk,'id':str(doc.pk),'confirmed':True,'columns':doc.columns}
        self.assertEqual(self.post('platform_knowledge',activate,self.admin_client).status_code,200)
        doc.refresh_from_db();self.assertEqual(doc.reviewed_by,self.admin);self.assertIsNotNone(doc.reviewed_at)
        self.assertEqual(doc.status,'active')
        self.assertEqual(self.post('platform_knowledge',{'action':'delete','business':self.business.pk,'id':str(doc.pk)},self.staff).status_code,200)
        self.assertFalse(KnowledgeDocument.objects.exists())

    def test_provider_consent_is_persisted_and_revoked_on_switch(self):
        self.business.ai_external_consent=True;self.business.save()
        consent=ProviderConsent.objects.get(business=self.business,provider='openai')
        self.assertTrue(consent.granted);self.assertEqual(consent.granted_by,self.owner)
        self.business.ai_provider='gemini';self.business.ai_external_consent=True;self.business.save()
        consent.refresh_from_db();self.assertFalse(consent.granted);self.assertIsNotNone(consent.revoked_at)
        self.business.ai_external_consent=False;self.business.save()
        self.assertFalse(self.business.provider_consents.filter(granted=True).exists())

    def test_invitation_has_admin_creator_and_cannot_be_issued_by_manager(self):
        payload={'action':'invite','email':'invited@example.test'}
        self.assertEqual(self.post('staff',payload,self.staff).status_code,403)
        r=self.post('staff',payload,self.admin_client)
        self.assertEqual(r.status_code,200,r.content)
        i=Invitation.objects.get();self.assertEqual(i.created_by,self.admin);self.assertEqual(i.role,'manager')
        self.assertNotEqual(i.token_hash,r.json()['token'])

    def test_unpublished_catalogue_and_unavailable_product_reject_checkout(self):
        self.product.is_available=False;self.product.save()
        public=self.guest.get('/api/data',{'business':self.business.pk}).json()
        self.assertEqual(public['products'],[])
        r=self.post('data',{'action':'order','business':self.business.pk,'product':self.product.name,
            'qty':1,'due':(timezone.now()+timedelta(days=3)).isoformat(),'name':'N','phone':'P',
            'privacyConsent':True,'sellerAcknowledged':True})
        self.assertEqual(r.status_code,400);self.assertFalse(Order.objects.exists());self.assertFalse(User.objects.exists())
        self.product.is_available=True;self.product.save()
        c=self.product.catalogue;c.is_published=False;c.save()
        self.assertEqual(self.guest.get('/api/data',{'business':self.business.pk}).json()['products'],[])

    def test_interface_language_does_not_overwrite_business_language(self):
        r=self.post('operations',{'action':'update_business','business':self.business.pk,
            'businessLanguage':'kk','language':'en'},self.staff)
        self.assertEqual(r.status_code,200,r.content)
        self.business.refresh_from_db();self.assertEqual(self.business.language,'kk')
        r=self.post('operations',{'action':'update_business','business':self.business.pk,
            'name':'Renamed','language':'ru'},self.staff)
        self.assertEqual(r.status_code,200)
        self.business.refresh_from_db();self.assertEqual(self.business.language,'kk')

    def test_startup_guard_rejects_previous_authentication_schema(self):
        from unittest.mock import patch
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with patch('core.management.commands.check_schema_baseline.connection.introspection.table_names', return_value=['core_user','django_migrations']):
            with self.assertRaisesMessage(CommandError,'NEW EMPTY'):
                call_command('check_schema_baseline')
        self.assertEqual(Account.objects.count(),3)
