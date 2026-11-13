#!/usr/bin/env python3
"""A small local launcher; production uses config.wsgi + a Python web server."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description='Запуск локальной Python-версии «Дело дома»')
parser.add_argument('--study', action='store_true', help='Изолированная SQLite и три учебных аккаунта с паролями')
parser.add_argument('--demo', action='store_true', help='Создать примеры данных для локальной проверки')
parser.add_argument('--live-ai', action='store_true', help='Разрешить запросы к OpenAI (нужны ключ, баланс и согласия)')
parser.add_argument('--gemini', action='store_true', help='Использовать Google Gemini')
parser.add_argument('--port', type=int, default=8000)
args = parser.parse_args()
root = Path(__file__).resolve().parent
os.chdir(root)
os.environ.setdefault('DJANGO_DEBUG', '1')
if args.study and args.demo:
    parser.error('Используйте --study отдельно от старого режима --demo.')
if args.study:
    os.environ['DELO_STUDY_MODE'] = '1'
os.environ['DELO_DEMO'] = '1' if args.demo else '0'
if args.gemini:
    os.environ['DELO_AI_MODE'] = 'gemini'
elif args.live_ai:
    os.environ['DELO_AI_MODE'] = 'model'
# Otherwise use .env settings; the default remains local when no provider is configured.
if not (root / 'frontend' / 'dist' / 'index.html').is_file():
    parser.error('Сначала соберите интерфейс: cd frontend && npm install && npm run build')
if not 1024 <= args.port <= 65535:
    parser.error('Порт должен быть от 1024 до 65535.')
def manage(*commands):
    subprocess.run([sys.executable, 'manage.py', *commands], check=True)
manage('migrate', '--noinput')
if args.demo:
    manage('seed_demo')
manage('ensure_study_accounts', '--if-enabled')
manage('check')
os.execv(sys.executable, [sys.executable, 'manage.py', 'runserver', '127.0.0.1:' + str(args.port), '--noreload'])
