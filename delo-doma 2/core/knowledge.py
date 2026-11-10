import base64
import csv
import io
import re
import zipfile
from decimal import Decimal, InvalidOperation
from openpyxl import load_workbook
from django.db import transaction
from django.utils import timezone
from .models import KnowledgeDocument, Product
from .security import audit, clean, fail, owned_business, rate_limit, seal, unseal
from .serializers import document_meta, product_data

SENSITIVE = re.compile(r'парол|password|secret|token|api.?key|email|e-mail|телефон|phone|фио|клиент|customer|client|адрес|address|паспорт|карта|card', re.I)
SECRET_TEXT = re.compile(r'sk-[a-zA-Z0-9_-]{16,}|-----BEGIN .*PRIVATE KEY|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b|\+\d[\d ()-]{9,}\d', re.I)

def inspect_xlsx(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > 200 or sum(e.file_size for e in entries) > 16 * 1024 * 1024:
                fail('Excel-файл слишком большой после распаковки.')
            for entry in entries:
                if entry.file_size > 8 * 1024 * 1024 or (entry.file_size > 1024 * 1024 and entry.file_size / max(1, entry.compress_size) > 120) or entry.flag_bits & 1:
                    fail('Файл слишком сложный или защищён паролем.')
                if re.search(r'vbaProject|externalLinks|\.exe$|\.js$', entry.filename, re.I):
                    fail('Макросы и внешние ссылки не поддерживаются.')
                if entry.filename.endswith(('.xml', '.rels')):
                    text = archive.read(entry).decode('utf-8', errors='strict')
                    if re.search(r'<!DOCTYPE|<!ENTITY|TargetMode=["\']External["\']', text, re.I):
                        fail('Активные элементы и внешние ссылки не поддерживаются.')
                    if re.search(r'xl/worksheets/sheet\d+\.xml', entry.filename):
                        if len(re.findall(r'<row(?:\s|>)', text)) > 1001:
                            fail('Не больше 1000 строк данных.')
                        for col, row in re.findall(r'<c\b[^>]*\br=["\']([A-Z]+)(\d+)["\']', text):
                            number = 0
                            for char in col:
                                number = number * 26 + ord(char) - 64
                            if number > 20 or int(row) > 1001:
                                fail('Не больше 1000 строк и 20 столбцов.')
    except (zipfile.BadZipFile, UnicodeError, RuntimeError, KeyError):
        fail('Повреждённый Excel-файл.')

def parse_knowledge(name, raw):
    ext = name.lower().rsplit('.', 1)[-1]
    if ext not in ('xlsx', 'csv', 'txt'):
        fail('Поддерживаются XLSX, CSV и TXT. Макросы и старый XLS не принимаются.')
    if not raw or len(raw) > 2 * 1024 * 1024:
        fail('Размер файла должен быть от 1 байта до 2 МБ.')
    matrix, formulas = [], 0
    if ext == 'xlsx':
        inspect_xlsx(raw)
        try:
            book = load_workbook(io.BytesIO(raw), read_only=True, data_only=False, keep_links=False)
            try:
                if not book.worksheets or len(book.worksheets) > 5:
                    fail('В файле должно быть от 1 до 5 листов.')
                sheet = book.worksheets[0]
                if (sheet.max_row or 0) > 1001 or (sheet.max_column or 0) > 20:
                    fail('Не больше 1000 строк и 20 столбцов.')
                for row in sheet.iter_rows():
                    values = []
                    for cell in row:
                        if cell.data_type == 'f':
                            formulas += 1
                            values.append('')
                        else:
                            values.append(str(cell.value) if cell.value is not None else '')
                    if any(values):
                        matrix.append(values)
            finally:
                book.close()
        except (ValueError, KeyError, OSError):
            fail('Не удалось прочитать Excel-файл.')
    else:
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeError:
            fail('Сохраните текстовый файл в кодировке UTF-8.')
        if '\x00' in text:
            fail('Это не текстовый файл.')
        if ext == 'csv':
            try:
                dialect = csv.Sniffer().sniff(text[:8192], delimiters=';,\t,')
                matrix = [r for r in csv.reader(io.StringIO(text), dialect, strict=True) if any(c.strip() for c in r)]
            except csv.Error:
                fail('Не удалось прочитать CSV. Проверьте разделитель и кавычки.')
        else:
            lines = [line for line in text.splitlines() if line.strip()]
            matrix = [['Вопрос', 'Ответ']]
            for line in lines:
                parts = re.split(r'\s*[|\t]\s*', line, maxsplit=1)
                matrix.append(parts if len(parts) == 2 else ['Информация', line])
    if len(matrix) < 2 or len(matrix) > 1001 or max(map(len, matrix), default=0) > 20:
        fail('Нужны заголовки и от 1 до 1000 строк данных, не больше 20 столбцов.')
    original = [clean(str(c), 100) or 'Столбец ' + str(i + 1) for i, c in enumerate(matrix[0])]
    if len(set(original)) != len(original):
        fail('Названия столбцов должны быть уникальными.')
    allowed = [(i, h) for i, h in enumerate(original) if not SENSITIVE.search(h)]
    if not allowed:
        fail('В файле только столбцы с персональными или секретными данными.')
    rows = [{h: clean(str(row[i]), 1200) if i < len(row) else '' for i, h in allowed} for row in matrix[1:]]
    if any(SECRET_TEXT.search(v) for row in rows for v in row.values()):
        fail('Найдены контакты или секретные данные. Удалите их перед загрузкой.')
    # Never evaluate spreadsheet/CSV formulas, including formula-like CSV cells.
    for row in rows:
        for header, value in row.items():
            if value.startswith(('=', '+', '@')):
                formulas += 1
                row[header] = ''
    headers = [h for _, h in allowed]
    candidates = catalog_candidates(headers, rows)
    return {'headers': headers, 'rows': rows, 'candidates': candidates,
            'ignoredColumns': [h for h in original if SENSITIVE.search(h)], 'formulaCount': formulas, 'type': ext}

def catalog_candidates(headers, rows):
    name_col = next((h for h in headers if re.fullmatch(r'название|товар|product|name|наименование', h, re.I)), None)
    price_col = next((h for h in headers if re.fullmatch(r'цена|price|стоимость', h, re.I)), None)
    desc_col = next((h for h in headers if re.search(r'описан|description|состав', h, re.I)), None)
    found = {}
    if name_col and price_col:
        for row in rows:
            try:
                price = Decimal(re.sub(r'\s|₸|₽|тенге|руб', '', row[price_col], flags=re.I).replace(',', '.'))
                name = clean(row[name_col], 160)
                if name and price.is_finite() and 0 < price <= 1_000_000_000:
                    found[name] = {'name': name, 'price': float(price), 'description': row.get(desc_col, '')}
            except (InvalidOperation, ValueError):
                continue
    return list(found.values())[:100]

def knowledge_route(request, v):
    b = owned_business(request)
    if request.method == 'GET' and not request.GET.get('id'):
        return {'documents': [document_meta(d) for d in b.documents.order_by('-created')]}
    if request.method == 'POST' and v.get('action') == 'upload':
        rate_limit(request, 'upload', 8)
        if v.get('rightsConfirmed') is not True:
            fail('Подтвердите право использовать файл и отсутствие клиентских персональных данных.')
        encoded = v.get('base64')
        if not isinstance(encoded, str) or len(encoded) > 2_850_000:
            fail('Файл слишком большой.')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except ValueError:
            fail('Некорректный файл.')
        name = clean(v.get('name'), 140)
        parsed = parse_knowledge(name, raw)
        with transaction.atomic():
            b = owned_business(request, lock=True)
            if b.documents.count() >= 10:
                fail('Не больше 10 файлов на бизнес.')
            d = KnowledgeDocument.objects.create(business=b, name=name, row_count=len(parsed['rows']),
                columns=parsed['headers'], file_type=parsed['type'], formula_count=parsed['formulaCount'],
                ignored_columns=parsed['ignoredColumns'], encrypted_payload=seal(parsed, 'knowledge:' + b.pk))
            audit(request.user, 'knowledge.uploaded', b, {'document': str(d.pk), 'rows': d.row_count})
        return {**document_meta(d), 'preview': parsed['rows'][:5], 'candidates': parsed['candidates']}
    key = request.GET.get('id') if request.method == 'GET' else v.get('id')
    d = next((d for d in b.documents.all() if str(d.pk) == key), None)
    if not d:
        fail('Файл не найден.', 404)
    parsed = unseal(d.encrypted_payload, 'knowledge:' + b.pk)
    if request.method == 'GET':
        return {**document_meta(d), 'preview': parsed['rows'][:5], 'candidates': parsed['candidates']}
    action = v.get('action')
    if action == 'delete':
        key = str(d.pk)
        d.delete()
        audit(request.user, 'knowledge.deleted', b, {'document': key})
        return {'ok': True}
    if action == 'activate':
        columns = v.get('columns')
        if v.get('confirmed') is not True or not isinstance(columns, list) or not columns or len(set(columns)) != len(columns) or any(c not in parsed['headers'] or SENSITIVE.search(c) for c in columns):
            fail('Подтвердите проверку и выберите допустимые столбцы.')
        # Keep original sanitized rows encrypted for later review; retrieval uses selection only.
        d.selected_columns, d.columns, d.status, d.activated = columns, columns, 'active', timezone.now()
        d.save()
        audit(request.user, 'knowledge.activated', b, {'document': str(d.pk)})
        return document_meta(d)
    if action == 'import_catalog':
        if v.get('confirmed') is not True or not parsed['candidates']:
            fail('Проверьте и подтвердите товары с ценами.')
        with transaction.atomic():
            b = owned_business(request, lock=True)
            if len(set(b.products.values_list('name', flat=True)) | {p['name'] for p in parsed['candidates']}) > 100:
                fail('В каталоге может быть не больше 100 товаров.')
            for p in parsed['candidates']:
                Product.objects.update_or_create(business=b, name=p['name'], defaults={'price': p['price'], 'description': p['description']})
            audit(request.user, 'catalog.imported', b, {'document': str(d.pk)})
        return {'products': [product_data(p) for p in b.products.all()]}
    fail('Неизвестное действие.')

def retrieval(b, message):
    stop = {'как', 'что', 'для', 'это', 'мне', 'хочу', 'есть', 'нужен', 'нужно', 'заказ', 'заказать', 'можно', 'пожалуйста'}
    words = {w[:4] if len(w) > 5 else w for w in re.findall(r'[a-zа-яё0-9]{3,}', message.lower()) if w not in stop}
    chunks = []
    for d in b.documents.filter(status='active'):
        parsed = unseal(d.encrypted_payload, 'knowledge:' + b.pk)
        for raw in parsed['rows']:
            row = {k: raw.get(k, '') for k in d.selected_columns or d.columns}
            text = ' · '.join(k + ': ' + v for k, v in row.items())[:2000]
            score = sum(w in text.lower() for w in words)
            if score:
                chunks.append({'documentId': str(d.pk), 'source': d.name, 'text': text, 'score': score,
                               'answer': row.get('Ответ') or row.get('Answer') or row.get('answer', '')})
    return sorted(chunks, key=lambda c: c['score'], reverse=True)[:3]
