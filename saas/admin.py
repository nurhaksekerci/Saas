from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.contrib.admin import SimpleListFilter
from .models import (
    City, District, Neighborhood, Currency, Company, Branch, 
    Employee, Plan, Subscription, Invoice, Notification, 
    NotificationRecipient, MaintenanceMode, Announcement,
    AnnouncementRead, CompanyBranding, APIUsage, Integration,
    FileStorage, AuditLog
)

class BaseAdmin(admin.ModelAdmin):
    """Temel admin özellikleri"""
    list_per_page = 25
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at')
    list_filter = ['is_active']
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Düzenleme durumunda
            return self.readonly_fields + ('created_at', 'updated_at')
        return self.readonly_fields

class LocationBaseAdmin(BaseAdmin):
    """Konum tabanlı modeller için temel admin"""
    search_fields = ('name',)
    list_display = ('name', 'is_active', 'created_at')

@admin.register(City)
class CityAdmin(LocationBaseAdmin):
    list_display = ('name', 'code', 'is_active')
    search_fields = ('name', 'code')
    list_filter = ('is_active',)

@admin.register(District)
class DistrictAdmin(LocationBaseAdmin):
    list_display = ('name', 'city', 'is_active')
    list_filter = ('city', 'is_active')
    search_fields = ('name', 'city__name')

@admin.register(Neighborhood)
class NeighborhoodAdmin(LocationBaseAdmin):
    list_display = ('name', 'district', 'is_active')
    list_filter = ('district__city', 'district', 'is_active')
    search_fields = ('name', 'district__name', 'district__city__name')

@admin.register(Currency)
class CurrencyAdmin(LocationBaseAdmin):
    list_display = ('code', 'name', 'symbol', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')

class CompanySubscriptionInline(admin.TabularInline):
    model = Subscription
    extra = 0
    readonly_fields = ('created_at',)
    fields = ('plan', 'status', 'start_date', 'end_date', 'created_at')
    show_change_link = True

class CompanyBranchInline(admin.TabularInline):
    model = Branch
    extra = 0
    fields = ('name', 'is_main_branch', 'phone', 'email')
    show_change_link = True

@admin.register(Company)
class CompanyAdmin(BaseAdmin):
    list_display = ('name', 'company_type', 'tax_number', 'phone', 'email', 'is_active')
    list_filter = ('company_type', 'is_active', 'created_at')
    search_fields = ('name', 'tax_number', 'email')
    readonly_fields = ('slug', 'created_at', 'updated_at')
    ordering = ('name',)
    inlines = [CompanyBranchInline, CompanySubscriptionInline]
    
    def subscription_status(self, obj):
        active_sub = obj.subscriptions.filter(is_active=True).first()
        if active_sub:
            return format_html(
                '<span style="color: {};">{}</span>',
                '#28a745' if active_sub.status == 'active' else '#ffc107',
                active_sub.get_status_display()
            )
        return format_html('<span style="color: #dc3545;">Aktif Abonelik Yok</span>')
    subscription_status.short_description = _('Abonelik Durumu')

    def employee_count(self, obj):
        count = Employee.objects.filter(branch__company=obj).count()
        return format_html('<b>{}</b>', count)
    employee_count.short_description = _('Çalışan Sayısı')

class BranchEmployeeInline(admin.TabularInline):
    model = Employee
    extra = 0
    fields = ('user', 'role', 'phone', 'hire_date')
    show_change_link = True

@admin.register(Branch)
class BranchAdmin(BaseAdmin):
    list_display = ('name', 'company', 'is_main_branch', 'phone', 'email', 'is_active')
    list_filter = ('company', 'is_main_branch', 'is_active', 'created_at')
    search_fields = ('name', 'company__name', 'email')
    readonly_fields = ('slug', 'created_at', 'updated_at')
    ordering = ('company', 'name')
    date_hierarchy = 'created_at'
    inlines = [BranchEmployeeInline]
    
    def employee_count(self, obj):
        count = obj.employees.count()
        url = reverse('admin:saas_employee_changelist') + f'?branch__id__exact={obj.id}'
        return format_html('<a href="{}">{} çalışan</a>', url, count)
    employee_count.short_description = _('Çalışan Sayısı')

@admin.register(Employee)
class EmployeeAdmin(BaseAdmin):
    list_display = ('user', 'branch', 'role', 'phone', 'is_active')
    list_filter = ('role', 'gender', 'is_active', 'created_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'identity_number')
    readonly_fields = ('slug', 'created_at', 'updated_at')
    ordering = ('user__first_name', 'user__last_name')
    date_hierarchy = 'created_at'

@admin.register(Plan)
class PlanAdmin(BaseAdmin):
    list_display = ('name', 'price', 'currency', 'is_active')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)

class SubscriptionInvoiceInline(admin.TabularInline):
    model = Invoice
    extra = 0
    readonly_fields = ('created_at',)
    fields = ('number', 'amount', 'status', 'due_date', 'created_at')
    show_change_link = True

@admin.register(Subscription)
class SubscriptionAdmin(BaseAdmin):
    list_display = ('company', 'plan', 'status', 'start_date', 'end_date', 'is_active')
    list_filter = ('status', 'plan', 'is_active')
    search_fields = ('company__name',)
    inlines = [SubscriptionInvoiceInline]

@admin.register(Invoice)
class InvoiceAdmin(BaseAdmin):
    list_display = ('number', 'subscription', 'amount_display', 'status', 'due_date', 'is_active')
    list_filter = ('status', 'is_active')
    search_fields = ('number', 'subscription__company__name')
    
    def amount_display(self, obj):
        return f"{obj.amount} {obj.currency.code}"
    amount_display.short_description = _('Tutar')

@admin.register(Notification)
class NotificationAdmin(BaseAdmin):
    list_display = ('title', 'notification_type', 'scope', 'company', 'created_by', 'created_at')
    list_filter = ('notification_type', 'scope', 'is_active')
    search_fields = ('title', 'message')

@admin.register(MaintenanceMode)
class MaintenanceModeAdmin(BaseAdmin):
    list_display = ('title', 'platform', 'status', 'planned_start_time', 'is_active')
    list_filter = ('platform', 'status')
    search_fields = ('title', 'description')

@admin.register(Announcement)
class AnnouncementAdmin(BaseAdmin):
    list_display = ('title', 'priority', 'target_role', 'publish_date', 'is_active')
    list_filter = ('priority', 'target_role')
    search_fields = ('title', 'content')

@admin.register(CompanyBranding)
class CompanyBrandingAdmin(BaseAdmin):
    list_display = ('company', 'has_logo', 'has_favicon', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('company__name',)
    
    def has_logo(self, obj):
        return bool(obj.logo)
    has_logo.boolean = True
    has_logo.short_description = _('Logo')
    
    def has_favicon(self, obj):
        return bool(obj.favicon)
    has_favicon.boolean = True
    has_favicon.short_description = _('Favicon')

@admin.register(APIUsage)
class APIUsageAdmin(BaseAdmin):
    list_display = ('company', 'endpoint', 'method', 'requests_count', 'date', 'is_active')
    list_filter = ('method', 'is_active', 'date')
    search_fields = ('company__name', 'endpoint')

@admin.register(Integration)
class IntegrationAdmin(BaseAdmin):
    list_display = ('name', 'company', 'integration_type', 'is_active')
    list_filter = ('integration_type', 'is_active')
    search_fields = ('name', 'company__name')

@admin.register(FileStorage)
class FileStorageAdmin(BaseAdmin):
    list_display = ('company', 'file_type', 'file_size_display', 'uploaded_by', 'created_at')
    list_filter = ('file_type', 'is_active')
    search_fields = ('company__name', 'description')
    
    def file_size_display(self, obj):
        # Boyutu MB cinsinden göster
        mb_size = obj.file_size / (1024 * 1024)
        return f"{mb_size:.2f} MB"
    file_size_display.short_description = _('Dosya Boyutu')

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'action', 'content_type', 'created_at')
    list_filter = ('action', 'content_type')
    search_fields = ('user__username', 'company__name', 'object_repr')
    readonly_fields = ('user', 'company', 'action', 'content_type', 'object_id', 
                      'object_repr', 'changes', 'ip_address', 'user_agent', 'created_at')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
