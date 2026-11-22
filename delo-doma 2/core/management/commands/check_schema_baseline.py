from django.core.management.base import BaseCommand, CommandError
from django.db import connection

class Command(BaseCommand):
    help = 'Refuse the pre-ERD test schema; this release requires an empty database.'

    def handle(self, **options):
        tables = set(connection.introspection.table_names())
        if 'core_user' in tables and 'core_account' not in tables:
            raise CommandError(
                'The old authentication schema was detected. This ERD release requires a NEW EMPTY '
                'test database. Do not fake migrations. See docs/erd/README.md. No data was deleted.')
        self.stdout.write('Database schema baseline is compatible.')
