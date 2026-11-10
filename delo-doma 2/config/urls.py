from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [path('django-admin/', admin.site.urls),
               path('api/<str:route>', views.api), path('', views.index)]
