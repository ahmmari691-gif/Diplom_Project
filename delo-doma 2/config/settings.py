"""Local development by default. Production must supply independent secrets."""
import base64
import os
import secrets
from pathlib import Path
from urllib.parse import unquote, urlparse
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Read only the new project's explicit configuration. Never copy the old API key.
env_file = BASE_DIR / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            name, value = line.split('=', 1)
            os.environ.setdefault(name.strip(), value.strip().strip('"\''))

DEBUG = os.getenv('DJANGO_DEBUG', '1') == '1'
DEMO_MODE = os.getenv('DELO_DEMO', '0') == '1'
AI_MODE = os.getenv('DELO_AI_MODE', 'local')
if DEMO_MODE and not DEBUG:
    raise ImproperlyConfigured('Demo role switching is forbidden outside DEBUG.')

def local_secret(filename, size):
    directory = BASE_DIR / '.local'
    directory.mkdir(mode=0o700, exist_ok=True)
    target = directory / filename
    try:
        with target.open('x') as stream:
            os.chmod(target, 0o600)
            stream.write(base64.urlsafe_b64encode(secrets.token_bytes(size)).decode())
    except FileExistsError:
        pass
    return target.read_text().strip()

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
DATA_ENCRYPTION_KEY = os.getenv('DATA_ENCRYPTION_KEY')
if DEBUG:
    SECRET_KEY = SECRET_KEY or local_secret('django-secret', 48)
    DATA_ENCRYPTION_KEY = DATA_ENCRYPTION_KEY or local_secret('encryption.key', 32)
if not SECRET_KEY or not DATA_ENCRYPTION_KEY:
    raise ImproperlyConfigured('Set DJANGO_SECRET_KEY and DATA_ENCRYPTION_KEY.')
try:
    if len(base64.urlsafe_b64decode(DATA_ENCRYPTION_KEY)) != 32:
        raise ValueError()
except Exception:
    raise ImproperlyConfigured('DATA_ENCRYPTION_KEY must be a base64 encoded 32 byte key.')

ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost,[::1]').split(',')
CSRF_TRUSTED_ORIGINS = [v for v in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if v]
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'core',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.ResponseSecurity',
]
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates',
              'DIRS': [BASE_DIR / 'frontend' / 'dist'], 'APP_DIRS': True,
              'OPTIONS': {'context_processors': ['django.template.context_processors.request',
                          'django.contrib.auth.context_processors.auth',
                          'django.contrib.messages.context_processors.messages']}}]
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3',
                        'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'}}}
if os.getenv('DATABASE_URL'):
    db = urlparse(os.environ['DATABASE_URL'])
    if db.scheme not in ('postgres', 'postgresql'):
        raise ImproperlyConfigured('DATABASE_URL must use PostgreSQL.')
    DATABASES['default'] = {'ENGINE': 'django.db.backends.postgresql', 'NAME': unquote(db.path[1:]),
                           'USER': unquote(db.username or ''), 'PASSWORD': unquote(db.password or ''),
                           'HOST': db.hostname, 'PORT': db.port or 5432, 'CONN_MAX_AGE': 60,
                           'OPTIONS': {'sslmode': os.getenv('DB_SSLMODE', 'require')}}
AUTH_USER_MODEL = 'core.User'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Asia/Almaty'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SESSION_COOKIE_NAME = 'delo_django_session'
SESSION_COOKIE_AGE = 43200
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_REFERRER_POLICY = 'no-referrer'
X_FRAME_OPTIONS = 'DENY'
CSRF_FAILURE_VIEW = 'core.views.csrf_failure'
DATA_UPLOAD_MAX_MEMORY_SIZE = 3_000_000
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'frontend' / 'dist']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
WHITENOISE_USE_FINDERS = DEBUG
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
# Optional reuse of the already-authorized local credential, read only in model mode.
OPENAI_ENV_FILE = Path(os.getenv('OPENAI_ENV_FILE', str(BASE_DIR.parent / '.env.local')))

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "core.hashers.LegacyScryptHasher",
]
