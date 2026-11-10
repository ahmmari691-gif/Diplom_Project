"""Layer-by-layer network diagnostics. Default checks send no key or user content."""
import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from django.conf import settings
from django.core.management.base import BaseCommand
from core.assistant import gemini_request, network_failure_kind
from core.security import AppError

HOST = 'generativelanguage.googleapis.com'

class Command(BaseCommand):
    help = 'Проверить DNS, TCP, TLS и HTTP Gemini без вывода ключей. API-запрос только с --with-api.'

    def add_arguments(self, parser):
        parser.add_argument('--with-api', action='store_true', help='Отправить короткий синтетический запрос; расходует квоту API.')
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, **options):
        report = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'host': HOST,
                  'model': settings.GEMINI_MODEL, 'dns': False, 'tcp': False, 'tls': False,
                  'httpStatus': None, 'failure': None, 'apiChecked': False}
        try:
            socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
            report['dns'] = True
            with socket.create_connection((HOST, 443), timeout=10) as connection:
                report['tcp'] = True
                with ssl.create_default_context().wrap_socket(connection, server_hostname=HOST) as secure:
                    report['tls'] = True
                    report['tlsVersion'] = secure.version()
            try:
                with urllib.request.urlopen('https://' + HOST + '/v1beta/models', timeout=10) as response:
                    report['httpStatus'] = response.status
            except urllib.error.HTTPError as error:
                # An authentication error is expected here: this check sends no key.
                report['httpStatus'] = error.code
        except (urllib.error.URLError, OSError) as error:
            report['failure'] = network_failure_kind(error)

        if options['with_api'] and report['tls']:
            key = os.environ.get('GEMINI_API_KEY')
            if not key:
                report['apiError'] = 'key_not_configured'
            else:
                report['apiChecked'] = True
                schema = {'type': 'object', 'properties': {'reply': {'type': 'string'}}, 'required': ['reply'], 'additionalProperties': False}
                try:
                    result = gemini_request({'instructions': 'Reply with one short sentence. This is a connection test.',
                        'input': [{'role': 'user', 'content': 'Say connection test passed.'}],
                        'text': {'format': {'schema': schema}}}, key)
                    report['apiSuccess'] = bool(result.get('reply'))
                except AppError as error:
                    report['apiSuccess'], report['apiError'] = False, error.code
        if options['as_json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False))
        else:
            for key, value in report.items():
                self.stdout.write(str(key) + ': ' + str(value))
