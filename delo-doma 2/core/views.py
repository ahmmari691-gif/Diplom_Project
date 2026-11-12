import json
import logging
from django.conf import settings
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import IntegrityError, OperationalError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from .accounts import auth_route
from .assistant import chat_route
from .site_help import help_route
from .inventory import inventory_route
from .knowledge import knowledge_route
from .orders import data_route
from .platform import admin_route, analytics_route, events_route, make_campaign, platform_route, security_route, staff_route
from .security import AppError, SELLER_NOTICE, current_user, fail, owned_business, user_data

logger = logging.getLogger(__name__)

def csrf_failure(request, reason=''):
    return JsonResponse({'error': 'Запрос отклонён защитой сайта. Обновите страницу и повторите.', 'code': 'csrf'}, status=403)

@ensure_csrf_cookie
def index(request):
    return render(request, 'index.html')

@ensure_csrf_cookie
def api(request, route):
    try:
        if request.method not in ('GET', 'POST'):
            fail('Метод не поддерживается.', 405)
        if request.method == 'POST':
            if request.content_type != 'application/json':
                fail('Запрос отклонён защитой сайта.', 403, 'csrf')
            try:
                v = json.loads(request.body)
            except (ValueError, UnicodeError):
                fail('Некорректный JSON.')
            if not isinstance(v, dict):
                fail('Некорректные данные.')
        else:
            v = {}
        post_only = {'auth', 'chat', 'help', 'events', 'campaigns'}
        if route in post_only and request.method != 'POST':
            fail('Метод не поддерживается.', 405)
        if route in ('analytics', 'me') and request.method != 'GET':
            fail('Метод не поддерживается.', 405)
        if route == 'me':
            result = {'user': user_data(current_user(request)), 'localPreview': False,
                      'features': {'inventory': settings.INVENTORY_ENABLED},
                      'aiMode': settings.AI_MODE, 'aiProvider': 'gemini' if settings.AI_MODE == 'gemini' else 'openai',
                      'aiProviderName': 'Google Gemini' if settings.AI_MODE == 'gemini' else 'OpenAI',
                      'backend': 'Django', 'disclaimer': SELLER_NOTICE}
        elif route == 'auth':
            result = auth_route(request, v)
        elif route == 'data':
            result = data_route(request, v)
        elif route == 'inventory':
            result = inventory_route(request, v)
        elif route == 'knowledge':
            result = knowledge_route(request, v)
        elif route == 'help':
            result = help_route(request, v)
        elif route == 'chat':
            result = chat_route(request, v)
        elif route == 'platform':
            result = platform_route(request, v)
        elif route == 'staff':
            result = staff_route(request, v)
        elif route == 'security':
            result = security_route(request, v)
        elif route == 'admin':
            result = admin_route(request, v)
        elif route == 'analytics':
            result = analytics_route(request)
        elif route == 'campaigns':
            result = make_campaign(request, v, owned_business(request))
        elif route == 'events':
            result = events_route(request, v)
        else:
            fail('Страница не найдена.', 404)
        return JsonResponse(result, json_dumps_params={'ensure_ascii': False})
    except AppError as error:
        return JsonResponse({'error': str(error), 'code': error.code}, status=error.status)
    except RequestDataTooBig:
        return JsonResponse({'error': 'Запрос слишком большой.'}, status=413)
    except (ValidationError, TypeError, KeyError, ValueError):
        return JsonResponse({'error': 'Некорректные данные запроса.'}, status=400)
    except (IntegrityError, OperationalError):
        return JsonResponse({'error': 'Данные уже изменились. Обновите страницу и повторите.'}, status=409)
    except Exception as error:
        # Never write customer messages, request bodies, API credentials or decrypted files to logs.
        logger.error('API failure: %s', type(error).__name__)
        return JsonResponse({'error': 'Не удалось выполнить запрос. Повторите позднее.'}, status=500)
