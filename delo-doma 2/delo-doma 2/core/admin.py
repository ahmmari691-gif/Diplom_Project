from django.contrib import admin
from .models import Business, AuditLog

admin.site.site_header = 'Дело дома · Django'
admin.site.site_title = 'Администрирование Дело дома'

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'status', 'created')
    fields = ('id', 'name', 'category', 'status', 'created', 'updated')
    readonly_fields = fields
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(AuditLog)
class AuditAdmin(admin.ModelAdmin):
    list_display = ('created', 'role', 'action', 'business_id')
    readonly_fields = ('created', 'actor', 'role', 'action', 'business_id', 'details')
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
