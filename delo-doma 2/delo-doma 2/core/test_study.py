import io
import json
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from core.models import Business, Product, User
from core.management.commands.ensure_study_accounts import ACCOUNTS

@override_settings(STUDY_MODE=True, DEBUG=True, DEMO_MODE=False,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StudyAccountTests(TestCase):
    def seed(self):
        call_command('ensure_study_accounts', stdout=io.StringIO())

    def test_real_login_each_role_and_wrong_password(self):
        self.seed()
        for role, email, _, password in ACCOUNTS:
            client = Client()
            response = client.post('/api/auth', json.dumps({'action': 'login', 'email': email, 'password': password}), content_type='application/json')
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()['user']['role'], role)
            self.assertEqual(client.get('/api/me').json()['user']['role'], role)
        client = Client()
        response = client.post('/api/auth', json.dumps({'action': 'login', 'email': 'admin@demo.local', 'password': 'Incorrect-password!'}), content_type='application/json')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(Business.objects.count(), 1)
        self.assertEqual(Product.objects.count(), 1)

    def test_repeated_start_preserves_password_catalog_and_revocation(self):
        self.seed()
        manager = User.objects.get(role='manager')
        manager.set_password('Changed-password!829')
        manager.platform_active = False
        manager.save()
        product = Product.objects.get()
        product.price = 7000
        product.save()
        self.seed()
        manager.refresh_from_db()
        product.refresh_from_db()
        self.assertTrue(manager.check_password('Changed-password!829'))
        self.assertFalse(manager.platform_active)
        self.assertEqual(product.price, 7000)
        self.assertEqual(User.objects.count(), 3)
        self.assertEqual(Product.objects.count(), 1)

    def test_missing_account_recreated_without_duplicates(self):
        self.seed()
        User.objects.get(role='manager').delete()
        self.seed()
        self.assertEqual(User.objects.count(), 3)
        self.assertTrue(User.objects.get(role='manager').check_password(ACCOUNTS[1][3]))
        self.assertEqual(Business.objects.count(), 1)

    @override_settings(STUDY_MODE=False)
    def test_disabled_mode_never_seeds(self):
        with self.assertRaises(CommandError):
            self.seed()
        call_command('ensure_study_accounts', if_enabled=True)
        self.assertEqual(User.objects.count(), 0)

    @override_settings(DEBUG=False)
    def test_hosted_requires_private_passwords_and_is_atomic(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(CommandError):
                self.seed()
        self.assertEqual(User.objects.count(), 0)
        with patch.dict('os.environ', {f'DELO_STUDY_{role.upper()}_PASSWORD': f'Private-{role}-password!582' for role, *_ in ACCOUNTS}, clear=True):
            self.seed()
        self.assertEqual(User.objects.count(), 3)

    def test_role_conflict_does_not_escalate(self):
        User.objects.create_user(username='existing', email='admin@demo.local', role='business')
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().role, 'business')
