from django.shortcuts import render
from rest_framework import status, viewsets, permissions, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser, DjangoModelPermissions
from rest_framework.decorators import action, permission_classes
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q, Count, Sum, Avg, F
from .serializers import LoginSerializer, CitySerializer, DistrictSerializer, NeighborhoodSerializer, CompanySerializer, BranchSerializer, EmployeeSerializer, PlanSerializer, SubscriptionSerializer, InvoiceSerializer, NotificationSerializer, AnnouncementSerializer, MaintenanceModeSerializer, CompanyBrandingSerializer, APIUsageSerializer, IntegrationSerializer, FileStorageSerializer, AuditLogSerializer
from .models import City, District, Neighborhood, Company, Branch, Employee, Plan, Subscription, Invoice, Notification, Announcement, MaintenanceMode, CompanyBranding, APIUsage, Integration, FileStorage, AuditLog
from datetime import datetime, timedelta
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType

# Create your views here.

class LoginView(APIView):
    """
    Kullanıcı girişi için API view.
    
    POST /auth/login/ ile kullanılır.
    username ve password alır, başarılı girişte token ve kullanıcı bilgilerini döndürür.
    """
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

# Konum ViewSet'leri
class CityViewSet(viewsets.ModelViewSet):
    """
    İl yönetimi için API endpoint'leri.
    Token gerektirmez.

    list:
    İlleri listeler.
    * Filtreleme: is_active
    * Arama: name, code
    * Sıralama: name, code

    retrieve:
    İl detaylarını getirir.
    """
    queryset = City.objects.all()
    serializer_class = CitySerializer
    permission_classes = [AllowAny]  # Token gerektirmez
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    pagination_class = None  # Sayfalama yok
    filterset_fields = ['is_active']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'code']

    def get_permissions(self):
        """GET metodları için izin gerektirmez, diğerleri için admin gerekir"""
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]

class DistrictViewSet(viewsets.ModelViewSet):
    """
    İlçe yönetimi için API endpoint'leri.
    Token gerektirmez.

    list:
    İlçeleri listeler.
    * Filtreleme: city, is_active
    * Arama: name, city__name
    * Sıralama: name, city__name

    retrieve:
    İlçe detaylarını getirir.
    """
    queryset = District.objects.all()
    serializer_class = DistrictSerializer
    permission_classes = [AllowAny]  # Token gerektirmez
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    pagination_class = None  # Sayfalama yok
    filterset_fields = ['city', 'is_active']
    search_fields = ['name', 'city__name']
    ordering_fields = ['name', 'city__name']

    def get_permissions(self):
        """GET metodları için izin gerektirmez, diğerleri için admin gerekir"""
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        queryset = super().get_queryset()
        city_id = self.request.query_params.get('city', None)
        if city_id:
            queryset = queryset.filter(city_id=city_id)
        return queryset

class NeighborhoodViewSet(viewsets.ModelViewSet):
    """
    Mahalle yönetimi için API endpoint'leri.
    Token gerektirmez.

    list:
    Mahalleleri listeler.
    * Filtreleme: district, district__city, is_active
    * Arama: name, postal_code, district__name
    * Sıralama: name, postal_code

    retrieve:
    Mahalle detaylarını getirir.
    """
    queryset = Neighborhood.objects.all()
    serializer_class = NeighborhoodSerializer
    permission_classes = [AllowAny]  # Token gerektirmez
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    pagination_class = None  # Sayfalama yok
    filterset_fields = ['district', 'district__city', 'is_active']
    search_fields = ['name', 'postal_code', 'district__name', 'district__city__name']
    ordering_fields = ['name', 'postal_code']

    def get_permissions(self):
        """GET metodları için izin gerektirmez, diğerleri için admin gerekir"""
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]

# Şirket ve Şube ViewSet'leri
class BaseViewSet(viewsets.ModelViewSet):
    """Tüm ViewSet'ler için temel sınıf"""
    permission_classes = [IsAuthenticated, DjangoModelPermissions]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    def perform_create(self, serializer):
        """Oluşturma sırasında audit log kaydı"""
        instance = serializer.save()
        content_type = ContentType.objects.get_for_model(instance)
        
        AuditLog.objects.create(
            user=self.request.user,
            action='create',
            content_type=content_type,
            object_id=instance.id,
            object_repr=str(instance),
            changes=serializer.data,
            company=instance if isinstance(instance, Company) else getattr(instance, 'company', None)
        )

    def perform_update(self, serializer):
        """Güncelleme sırasında audit log kaydı"""
        instance = serializer.save()
        content_type = ContentType.objects.get_for_model(instance)
        
        AuditLog.objects.create(
            user=self.request.user,
            action='update',
            content_type=content_type,
            object_id=instance.id,
            object_repr=str(instance),
            changes=serializer.data,
            company=instance if isinstance(instance, Company) else getattr(instance, 'company', None)
        )

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        """Toplu silme işlemi"""
        ids = request.data.get('ids', [])
        deleted_count = self.get_queryset().filter(id__in=ids).delete()[0]
        return Response({'deleted_count': deleted_count})

class CompanyViewSet(BaseViewSet):
    """
    Şirket yönetimi için API endpoint'leri.
    
    list:
    Şirketleri listeler.
    * Yetki: Authenticated
    * Filtreleme: company_type, is_active
    * Arama: name, tax_number, email
    * Sıralama: name, created_at
    
    create:
    Yeni şirket oluşturur.
    * Otomatik olarak merkez şube oluşturulur
    * 30 günlük deneme planı atanır
    
    retrieve:
    Şirket detaylarını getirir.
    * Şube bilgileri
    * Çalışan sayıları
    * Abonelik durumu
    
    update:
    Şirket bilgilerini günceller.
    * Audit log kaydı oluşturulur
    
    destroy:
    Şirketi siler.
    * İlişkili tüm kayıtlar silinir
    
    statistics:
    Şirket istatistiklerini döndürür.
    * Şube ve çalışan sayıları
    * Abonelik bilgileri
    * API kullanım istatistikleri
    
    audit_logs:
    Şirket denetim kayıtlarını listeler.
    * Tüm değişiklik geçmişi
    * Kullanıcı ve IP bilgileri
    """
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    filterset_fields = ['company_type', 'is_active']
    search_fields = ['name', 'tax_number', 'email']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        """Kullanıcının yetkisine göre şirketleri filtrele"""
        queryset = super().get_queryset()
        user = self.request.user
        
        if not user.is_superuser and not user.is_staff:
            if hasattr(user, 'employee'):
                return Company.objects.filter(id=user.employee.branch.company.id)
            return Company.objects.none()
        return queryset

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Şirket istatistiklerini döndürür"""
        company = self.get_object()
        
        # İstatistikleri hesapla
        stats = {
            'general': {
                'total_branches': company.branches.count(),
                'total_employees': Employee.objects.filter(branch__company=company).count(),
                'active_employees': Employee.objects.filter(
                    branch__company=company,
                    is_active=True,
                    termination_date__isnull=True
                ).count(),
            },
            'subscription': {
                'current_plan': None,
                'remaining_days': 0,
                'usage_stats': {
                    'storage_used': FileStorage.objects.filter(company=company)
                        .aggregate(total=Sum('file_size'))['total'] or 0,
                    'api_calls_today': APIUsage.objects.filter(
                        company=company,
                        date=timezone.now().date()
                    ).aggregate(total=Sum('requests_count'))['total'] or 0,
                }
            },
            'financial': {
                'total_invoices': Invoice.objects.filter(
                    subscription__company=company
                ).count(),
                'pending_invoices': Invoice.objects.filter(
                    subscription__company=company,
                    status='pending'
                ).count(),
            }
        }

        # Aktif abonelik bilgileri
        active_sub = company.subscriptions.filter(
            status='active',
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now()
        ).first()

        if active_sub:
            stats['subscription']['current_plan'] = {
                'name': active_sub.plan.name,
                'price': str(active_sub.plan.price),
                'features': active_sub.plan.features,
            }
            stats['subscription']['remaining_days'] = (
                active_sub.end_date - timezone.now().date()
            ).days

        return Response(stats)

    @action(detail=True, methods=['get'])
    def audit_logs(self, request, pk=None):
        """Şirket audit loglarını döndürür"""
        company = self.get_object()
        page = self.paginate_queryset(
            AuditLog.objects.filter(company=company).order_by('-created_at')
        )
        serializer = AuditLogSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

class BranchViewSet(viewsets.ModelViewSet):
    """
    Şube yönetimi için API endpoint'leri.

    list:
    Şubeleri listeler.
    * Filtreleme: company, is_main_branch, is_active
    * Arama: name, company__name, email
    * Sıralama: name, created_at

    create:
    Yeni şube oluşturur.
    * Gerekli alanlar: company, name, phone, email, address, neighborhood

    retrieve:
    Şube detaylarını getirir.
    * Çalışan bilgileri dahil edilir

    update:
    Şube bilgilerini günceller.
    * Audit log kaydı oluşturulur

    destroy:
    Şubeyi siler.
    * İlişkili çalışanlar da silinir
    """
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['company', 'is_main_branch', 'is_active']
    search_fields = ['name', 'company__name', 'email']
    ordering_fields = ['name', 'created_at']

class EmployeeViewSet(BaseViewSet):
    """
    Çalışan yönetimi için API endpoint'leri.

    list:
    Çalışanları listeler.
    * Filtreleme: branch, role, gender, is_active
    * Arama: user__username, user__first_name, user__last_name, identity_number
    * Sıralama: user__first_name, hire_date

    create:
    Yeni çalışan oluşturur.
    * Otomatik kullanıcı hesabı oluşturulur
    * Gerekli alanlar: branch, identity_number, birth_date, gender, phone, address

    retrieve:
    Çalışan detaylarını getirir.
    * Kullanıcı bilgileri dahil edilir

    update:
    Çalışan bilgilerini günceller.
    * Audit log kaydı oluşturulur

    destroy:
    Çalışanı siler.
    * İlişkili kullanıcı hesabı da silinir

    statistics:
    Çalışan istatistiklerini döndürür.
    * Toplam ve aktif çalışan sayısı
    * Cinsiyet dağılımı
    * Rol dağılımı
    * Ortalama çalışma süresi
    """
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    filterset_fields = ['branch', 'role', 'gender', 'is_active']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'identity_number']
    ordering_fields = ['user__first_name', 'hire_date']

    def get_queryset(self):
        """Kullanıcının yetkisine göre çalışanları filtrele"""
        queryset = super().get_queryset()
        user = self.request.user

        if not user.is_superuser and not user.is_staff:
            if hasattr(user, 'employee'):
                if user.employee.role == 'company_admin':
                    return queryset.filter(branch__company=user.employee.branch.company)
                elif user.employee.role == 'branch_admin':
                    return queryset.filter(branch=user.employee.branch)
                return queryset.filter(id=user.employee.id)
            return Employee.objects.none()
        return queryset

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Çalışan istatistiklerini döndürür"""
        queryset = self.get_queryset()
        stats = {
            'total_count': queryset.count(),
            'active_count': queryset.filter(is_active=True).count(),
            'gender_distribution': queryset.values('gender')
                .annotate(count=Count('id')),
            'role_distribution': queryset.values('role')
                .annotate(count=Count('id')),
            'average_tenure': queryset.filter(
                hire_date__isnull=False,
                termination_date__isnull=True
            ).aggregate(
                avg_days=Avg(
                    timezone.now().date() - F('hire_date')
                )
            )['avg_days']
        }
        return Response(stats)

# Abonelik ve Ödeme ViewSet'leri
class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name']
    ordering_fields = ['price', 'created_at']

class SubscriptionViewSet(BaseViewSet):
    """
    Abonelik yönetimi için API endpoint'leri.

    list:
    Abonelikleri listeler.
    * Filtreleme: company, plan, status, is_active
    * Arama: company__name
    * Sıralama: start_date, end_date

    create:
    Yeni abonelik oluşturur.
    * Gerekli alanlar: company, plan, start_date

    retrieve:
    Abonelik detaylarını getirir.
    * Plan bilgileri dahil edilir

    update:
    Abonelik bilgilerini günceller.
    * Audit log kaydı oluşturulur

    destroy:
    Aboneliği siler.

    cancel:
    Aboneliği iptal eder.
    * Otomatik bildirim oluşturulur

    extend:
    Abonelik süresini uzatır.
    * months parametresi ile süre belirtilir
    """
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    filterset_fields = ['company', 'plan', 'status', 'is_active']
    search_fields = ['company__name']
    ordering_fields = ['start_date', 'end_date']

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Aboneliği iptal et"""
        subscription = self.get_object()
        subscription.status = 'cancelled'
        subscription.save()
        
        # Bildirim oluştur
        Notification.objects.create(
            title=_("Abonelik İptali"),
            message=_(f"{subscription.company.name} şirketi için abonelik iptal edildi."),
            notification_type='subscription_cancelled',
            company=subscription.company,
            created_by=request.user
        )
        
        return Response({'status': 'cancelled'})

    @action(detail=True, methods=['post'])
    def extend(self, request, pk=None):
        """Abonelik süresini uzat"""
        subscription = self.get_object()
        months = int(request.data.get('months', 1))
        
        if subscription.end_date:
            subscription.end_date += timedelta(days=30 * months)
        subscription.save()
        
        return Response({
            'status': 'extended',
            'new_end_date': subscription.end_date
        })

class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['subscription', 'status', 'is_active']
    search_fields = ['number', 'subscription__company__name']
    ordering_fields = ['due_date', 'created_at']

# Bildirim ViewSet'leri
class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['notification_type', 'scope', 'is_active']
    search_fields = ['title', 'message']
    ordering_fields = ['-created_at']

class AnnouncementViewSet(viewsets.ModelViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['priority', 'target_role', 'is_active']
    search_fields = ['title', 'content']
    ordering_fields = ['-publish_date', '-priority']

# Sistem ViewSet'leri
class MaintenanceModeViewSet(viewsets.ModelViewSet):
    queryset = MaintenanceMode.objects.all()
    serializer_class = MaintenanceModeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['platform', 'status', 'is_active']
    search_fields = ['title']
    ordering_fields = ['planned_start_time']

class CompanyBrandingViewSet(viewsets.ModelViewSet):
    queryset = CompanyBranding.objects.all()
    serializer_class = CompanyBrandingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['company', 'is_active']
    search_fields = ['company__name']

class APIUsageViewSet(viewsets.ModelViewSet):
    queryset = APIUsage.objects.all()
    serializer_class = APIUsageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['company', 'endpoint', 'method', 'date']
    search_fields = ['company__name', 'endpoint']
    ordering_fields = ['-date', '-requests_count']

class IntegrationViewSet(viewsets.ModelViewSet):
    queryset = Integration.objects.all()
    serializer_class = IntegrationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['company', 'integration_type', 'is_active']
    search_fields = ['name', 'company__name']
    ordering_fields = ['name']

class FileStorageViewSet(viewsets.ModelViewSet):
    queryset = FileStorage.objects.all()
    serializer_class = FileStorageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['company', 'file_type', 'is_active']
    search_fields = ['description', 'company__name']
    ordering_fields = ['-created_at']

class AuditLogViewSet(viewsets.ModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['action', 'content_type', 'user', 'company']
    search_fields = ['object_repr', 'user__username', 'company__name']
    ordering_fields = ['-created_at']
