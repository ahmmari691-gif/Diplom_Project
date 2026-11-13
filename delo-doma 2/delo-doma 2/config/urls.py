from django.contrib import admin
from django.urls import path
from core import views
from config.health import health

urlpatterns = [path('healthz/', health), path('django-admin/', admin.site.urls),
               path('api/<str:route>', views.api), path('', views.index)]
