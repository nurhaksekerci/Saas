from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils.translation import gettext_lazy as _
from .models import (
    City, District, Neighborhood, Currency, Company, Branch, 
    Employee, Plan, Subscription, Invoice, Notification, 
    NotificationRecipient, MaintenanceMode, Announcement,
    AnnouncementRead, CompanyBranding, APIUsage, Integration,
    FileStorage, AuditLog
)
from django.utils import timezone
from django.conf import settings

class UserSerializer(serializers.ModelSerializer):
    """
    Kullanıcı bilgilerini serialize eden sınıf.
    
    Bu serializer, User modelinin temel alanlarını ve ek olarak token bilgilerini içerir.
    Token bilgileri sadece create işleminde döndürülür.
    """
    password = serializers.CharField(write_only=True)
    tokens = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'password', 'tokens')
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def get_tokens(self, user):
        """JWT token bilgilerini döndürür"""
        if 'context' in self.__dict__ and self.context.get('include_tokens', False):
            refresh = RefreshToken.for_user(user)
            return {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        return None

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

class CompanyDetailSerializer(serializers.ModelSerializer):
    """Giriş yapan kullanıcının şirket detayları için özel serializer"""
    class Meta:
        model = Company
        fields = (
            'id', 'name', 'slug', 'company_type', 'tax_number', 'tax_office',
            'phone', 'email', 'address', 'is_active', 'created_at'
        )

class BranchDetailSerializer(serializers.ModelSerializer):
    """Giriş yapan kullanıcının şube detayları için özel serializer"""
    company = CompanyDetailSerializer(read_only=True)
    
    class Meta:
        model = Branch
        fields = (
            'id', 'company', 'name', 'slug', 'is_main_branch',
            'phone', 'email', 'address', 'is_active', 'created_at'
        )

class LoginSerializer(serializers.Serializer):
    """
    Kullanıcı girişi için kullanılan serializer.
    
    Giriş yapmadan önce:
    1. Sistem bakım durumunu kontrol eder
    2. Kullanıcı aktiflik durumunu kontrol eder
    3. Kullanıcı yetkilerini ve abonelik durumunu kontrol eder
    """
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        # Kullanıcıyı doğrula
        user = authenticate(**data)
        if not user:
            raise serializers.ValidationError(_("Geçersiz kullanıcı adı veya parola."))

        # 1. Sistem bakım kontrolü
        active_maintenance = MaintenanceMode.objects.filter(
            status='in_progress',
            actual_start_time__lte=timezone.now()
        ).exclude(actual_end_time__lte=timezone.now()).first()

        if active_maintenance:
            # Bakım sırasında erişim izni kontrolü
            if not active_maintenance.can_access(user):
                raise serializers.ValidationError(_(
                    "Sistem şu anda bakımda. "
                    f"Tahmini bitiş zamanı: {active_maintenance.planned_end_time}"
                ))

        # 2. Kullanıcı aktiflik kontrolü
        if not user.is_active:
            raise serializers.ValidationError(_("Giriş yapma izniniz yok. Hesabınız aktif değil."))

        # 3. Yetki ve abonelik kontrolü
        if user.is_superuser or user.is_staff:
            # Süper kullanıcı veya personel direkt giriş yapabilir
            refresh = RefreshToken.for_user(user)
            return {
                'user': user,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }
        
        # Normal kullanıcı için şirket ve abonelik kontrolü
        try:
            employee = user.employee
            company = employee.branch.company
            
            # Aktif abonelik kontrolü
            active_subscription = Subscription.objects.filter(
                company=company,
                status='active',
                start_date__lte=timezone.now(),
                end_date__gte=timezone.now(),
                is_active=True
            ).first()

            if not active_subscription:
                raise serializers.ValidationError(_(
                    "Şirketinizin abonelik süresi bitmiştir. "
                    "Lütfen sistem yöneticiniz ile iletişime geçin."
                ))

            # Tüm kontroller başarılı, token oluştur
            refresh = RefreshToken.for_user(user)
            return {
                'user': user,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }

        except Employee.DoesNotExist:
            raise serializers.ValidationError(_(
                "Çalışan kaydınız bulunamadı. "
                "Lütfen sistem yöneticiniz ile iletişime geçin."
            ))

    def to_representation(self, instance):
        data = {
            'status': 'success',
            'message': _('Giriş başarılı'),
            'auth': {
                'type': 'Bearer',
                'access_token': instance['tokens']['access'],
                'refresh_token': instance['tokens']['refresh'],
                'expires_in': 3600,
            },
            'user': {
                'id': instance['user'].id,
                'username': instance['user'].username,
                'email': instance['user'].email,
                'personal': {
                    'first_name': instance['user'].first_name,
                    'last_name': instance['user'].last_name,
                    'full_name': instance['user'].get_full_name(),
                    'date_joined': instance['user'].date_joined,
                    'last_login': instance['user'].last_login,
                },
                'permissions': {
                    'is_active': instance['user'].is_active,
                    'is_staff': instance['user'].is_staff,
                    'is_superuser': instance['user'].is_superuser,
                    'groups': list(instance['user'].groups.values('id', 'name')),
                    'user_permissions': list(instance['user'].user_permissions.values('id', 'name')),
                }
            }
        }

        user = instance['user']

        # Çalışan bilgileri
        if hasattr(user, 'employee'):
            employee = user.employee
            branch = employee.branch
            company = branch.company

            # Şube ve şirket bilgilerini serialize et
            branch_serializer = BranchDetailSerializer(branch)
            company_serializer = CompanyDetailSerializer(company)

            data['user'].update({
                'employee': {
                    'id': employee.id,
                    'role': {
                        'code': employee.role,
                        'display': employee.get_role_display(),
                    },
                    'identity_number': employee.identity_number[-4:] + '****',
                    'personal': {
                        'birth_date': employee.birth_date,
                        'gender': {
                            'code': employee.gender,
                            'display': employee.get_gender_display(),
                        },
                        'phone': employee.phone,
                    },
                    'employment': {
                        'hire_date': employee.hire_date,
                        'termination_date': employee.termination_date,
                        'is_active': employee.is_active,
                        'tenure': (timezone.now().date() - employee.hire_date).days,
                    },
                    'location': {
                        'address': employee.address,
                        'neighborhood': {
                            'id': employee.neighborhood.id if employee.neighborhood else None,
                            'name': str(employee.neighborhood) if employee.neighborhood else None,
                        }
                    }
                },
                'branch': branch_serializer.data,
                'company': company_serializer.data,
            })

            # Aktif abonelik bilgileri
            active_subscription = company.subscriptions.filter(
                status='active',
                start_date__lte=timezone.now(),
                end_date__gte=timezone.now(),
                is_active=True
            ).first()

            if active_subscription:
                data['user']['company']['subscription'] = {
                    'id': active_subscription.id,
                    'plan': {
                        'id': active_subscription.plan.id,
                        'name': active_subscription.plan.name,
                        'features': active_subscription.plan.features,
                        'price': str(active_subscription.plan.price),
                        'max_users': active_subscription.plan.max_users,
                        'max_storage': active_subscription.plan.max_storage,
                    },
                    'status': {
                        'code': active_subscription.status,
                        'display': active_subscription.get_status_display(),
                    },
                    'dates': {
                        'start': active_subscription.start_date,
                        'end': active_subscription.end_date,
                        'trial_ends': active_subscription.trial_ends,
                    },
                    'is_trial': active_subscription.is_trial,
                    'remaining_days': (active_subscription.end_date - timezone.now().date()).days,
                }

            # Şirket görünüm ayarları
            if hasattr(company, 'branding'):
                data['user']['company']['branding'] = {
                    'primary_color': company.branding.primary_color,
                    'secondary_color': company.branding.secondary_color,
                    'logo_url': company.branding.logo.url if company.branding.logo else None,
                    'favicon_url': company.branding.favicon.url if company.branding.favicon else None,
                }

        # Sistem durumu
        maintenance_mode = MaintenanceMode.objects.filter(
            status='in_progress',
            actual_start_time__lte=timezone.now()
        ).exclude(actual_end_time__lte=timezone.now()).first()

        data['system'] = {
            'maintenance_mode': {
                'is_active': bool(maintenance_mode),
                'details': {
                    'title': maintenance_mode.title if maintenance_mode else None,
                    'description': maintenance_mode.description if maintenance_mode else None,
                    'planned_end_time': maintenance_mode.planned_end_time if maintenance_mode else None,
                } if maintenance_mode else None,
                'has_access': maintenance_mode.can_access(user) if maintenance_mode else True,
            },
            'server_time': timezone.now(),
            'version': '1.0.0',
            'environment': 'production' if not settings.DEBUG else 'development'
        }

        return data

class CitySerializer(serializers.ModelSerializer):
    """
    İl bilgilerini serialize eden sınıf.
    """
    class Meta:
        model = City
        fields = '__all__'

class DistrictSerializer(serializers.ModelSerializer):
    """
    İlçe bilgilerini serialize eden sınıf.
    İl bilgisini hem ID hem de isim olarak içerir.
    """
    city_name = serializers.CharField(source='city.name', read_only=True)

    class Meta:
        model = District
        fields = ('id', 'city', 'city_name', 'name', 'is_active', 'created_at', 'updated_at')

class NeighborhoodSerializer(serializers.ModelSerializer):
    """
    Mahalle bilgilerini serialize eden sınıf.
    İlçe ve il bilgilerini hem ID hem de isim olarak içerir.
    """
    district_name = serializers.CharField(source='district.name', read_only=True)
    city_name = serializers.CharField(source='district.city.name', read_only=True)

    class Meta:
        model = Neighborhood
        fields = ('id', 'district', 'district_name', 'city_name', 'name', 
                 'postal_code', 'is_active', 'created_at', 'updated_at')

class CurrencySerializer(serializers.ModelSerializer):
    """
    Para birimi bilgilerini serialize eden sınıf.
    """
    class Meta:
        model = Currency
        fields = '__all__'

class CompanySerializer(serializers.ModelSerializer):
    """
    Şirket bilgilerini serialize eden sınıf.
    """
    class Meta:
        model = Company
        fields = (
            'id', 'name', 'company_type', 'tax_number', 'tax_office',
            'phone', 'email', 'address', 'neighborhood', 'is_active'
        )
        read_only_fields = ('id', 'is_active')

    def validate(self, data):
        """Özel validasyon kuralları"""
        # Vergi numarası kontrolü
        if 'tax_number' in data:
            if not data['tax_number'].isdigit() or len(data['tax_number']) != 10:
                raise serializers.ValidationError({
                    'tax_number': 'Vergi numarası 10 haneli sayı olmalıdır.'
                })

        # Telefon format kontrolü
        if 'phone' in data:
            phone = ''.join(filter(str.isdigit, data['phone']))
            if len(phone) != 10:
                raise serializers.ValidationError({
                    'phone': 'Telefon numarası 10 haneli olmalıdır.'
                })
            data['phone'] = f"0{phone}"  # Standardize format

        return data

class BranchSerializer(serializers.ModelSerializer):
    """
    Şube bilgilerini serialize eden sınıf.
    Şirket ve mahalle bilgilerini hem ID hem de isim olarak içerir.
    """
    company_name = serializers.CharField(source='company.name', read_only=True)
    neighborhood_full_name = serializers.CharField(
        source='neighborhood.__str__', 
        read_only=True
    )

    class Meta:
        model = Branch
        fields = ('id', 'company', 'company_name', 'name', 'slug', 'phone',
                 'email', 'address', 'neighborhood', 'neighborhood_full_name',
                 'is_main_branch', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('slug',)

class EmployeeSerializer(serializers.ModelSerializer):
    """
    Çalışan bilgilerini serialize eden sınıf.
    Kullanıcı, şube ve mahalle bilgilerini hem ID hem de isim olarak içerir.
    """
    user_full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    company_name = serializers.CharField(source='branch.company.name', read_only=True)
    neighborhood_full_name = serializers.CharField(
        source='neighborhood.__str__', 
        read_only=True
    )
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)

    class Meta:
        model = Employee
        fields = ('id', 'user', 'user_full_name', 'branch', 'branch_name',
                 'company_name', 'slug', 'identity_number', 'birth_date',
                 'gender', 'gender_display', 'phone', 'address', 'neighborhood',
                 'neighborhood_full_name', 'hire_date', 'termination_date',
                 'role', 'role_display', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('slug',)

class PlanSerializer(serializers.ModelSerializer):
    """Plan bilgilerini serialize eden sınıf."""
    class Meta:
        model = Plan
        fields = '__all__'

class SubscriptionSerializer(serializers.ModelSerializer):
    """Abonelik bilgilerini serialize eden sınıf."""
    plan_details = PlanSerializer(source='plan', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    remaining_days = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = ('id', 'company', 'company_name', 'plan', 'plan_details',
                 'status', 'start_date', 'end_date', 'trial_ends',
                 'is_trial', 'is_active', 'created_at', 'remaining_days')

    def get_remaining_days(self, obj):
        if obj.end_date:
            return (obj.end_date - timezone.now().date()).days
        return None

class InvoiceSerializer(serializers.ModelSerializer):
    """Fatura bilgilerini serialize eden sınıf."""
    subscription_details = SubscriptionSerializer(source='subscription', read_only=True)
    company_name = serializers.CharField(source='subscription.company.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)

    class Meta:
        model = Invoice
        fields = ('id', 'number', 'subscription', 'subscription_details',
                 'company_name', 'amount', 'currency', 'currency_code',
                 'status', 'due_date', 'paid_at', 'notes', 'is_active',
                 'created_at')

class NotificationSerializer(serializers.ModelSerializer):
    """Bildirim bilgilerini serialize eden sınıf."""
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = Notification
        fields = ('id', 'title', 'message', 'notification_type', 'scope',
                 'company', 'created_by', 'created_by_name', 'is_active',
                 'created_at')

class AnnouncementSerializer(serializers.ModelSerializer):
    """Duyuru bilgilerini serialize eden sınıf."""
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    target_companies_names = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = ('id', 'title', 'content', 'priority', 'target_role',
                 'publish_date', 'end_date', 'created_by', 'created_by_name',
                 'target_companies', 'target_companies_names', 'is_active',
                 'created_at')

    def get_target_companies_names(self, obj):
        return list(obj.target_companies.values_list('name', flat=True))

class MaintenanceModeSerializer(serializers.ModelSerializer):
    """Bakım modu bilgilerini serialize eden sınıf."""
    class Meta:
        model = MaintenanceMode
        fields = '__all__'

class CompanyBrandingSerializer(serializers.ModelSerializer):
    """Şirket görünüm ayarlarını serialize eden sınıf."""
    class Meta:
        model = CompanyBranding
        fields = '__all__'

class APIUsageSerializer(serializers.ModelSerializer):
    """API kullanım istatistiklerini serialize eden sınıf."""
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = APIUsage
        fields = ('id', 'company', 'company_name', 'endpoint', 'method',
                 'requests_count', 'data_transfer', 'date', 'is_active')

class IntegrationSerializer(serializers.ModelSerializer):
    """Entegrasyon bilgilerini serialize eden sınıf."""
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = Integration
        fields = ('id', 'company', 'company_name', 'name', 'integration_type',
                 'config', 'is_active', 'created_at')

class FileStorageSerializer(serializers.ModelSerializer):
    """Dosya depolama bilgilerini serialize eden sınıf."""
    company_name = serializers.CharField(source='company.name', read_only=True)
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = FileStorage
        fields = ('id', 'company', 'company_name', 'file', 'file_type',
                 'description', 'file_size', 'file_size_display',
                 'uploaded_by', 'uploaded_by_name', 'is_active', 'created_at')

    def get_file_size_display(self, obj):
        """Dosya boyutunu okunabilir formatta döndürür"""
        size = obj.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

class AuditLogSerializer(serializers.ModelSerializer):
    """İşlem kayıtlarını serialize eden sınıf."""
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    content_type_name = serializers.CharField(source='content_type.model', read_only=True)

    class Meta:
        model = AuditLog
        fields = ('id', 'user', 'user_name', 'company', 'company_name',
                 'action', 'content_type', 'content_type_name', 'object_id',
                 'object_repr', 'changes', 'ip_address', 'user_agent',
                 'created_at')

# ... Diğer serializerlar bir sonraki mesajda devam edecek ... 