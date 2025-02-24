from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView
)
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.conf import settings
from rest_framework import permissions
from . import views

# API dokümantasyonu için schema view
schema_view = get_schema_view(
    openapi.Info(
        title="SaaS API",
        default_version='v1',
        description="""
# SaaS Platformu API Dokümantasyonu

## Genel Bilgiler
- Tüm istekler için JWT token gereklidir
- Tarih formatı: YYYY-MM-DD
- Zaman formatı: YYYY-MM-DD HH:MM:SS
- Sayfalama: Her sayfada 10 kayıt

## Kimlik Doğrulama
Token almak için:

### Kimlik Doğrulama
API JWT (JSON Web Token) tabanlı kimlik doğrulama kullanmaktadır.

**Token Alma:**
```bash
POST /auth/login/
{
    "username": "your_username",
    "password": "your_password"
}
```

**Token Kullanımı:**
```bash
Authorization: Bearer <your_access_token>
```

### Yanıt Formatları
Tüm API yanıtları JSON formatındadır ve aşağıdaki yapıyı takip eder:

**Başarılı Yanıt:**
```json
{
    "status": "success",
    "message": "İşlem başarılı",
    "data": { ... }
}
```

**Hata Yanıtı:**
```json
{
    "status": "error",
    "message": "Hata mesajı",
    "errors": { ... }
}
```

### Hata Kodları
| Kod | Açıklama |
|-----|-----------|
| 400 | Geçersiz İstek - İstek parametreleri hatalı |
| 401 | Yetkisiz - Kimlik doğrulama gerekli |
| 403 | Yasaklı - Yetkiniz yok |
| 404 | Bulunamadı - Kaynak mevcut değil |
| 429 | Çok Fazla İstek - Rate limit aşıldı |
| 500 | Sunucu Hatası - Beklenmeyen hata |

### Sayfalama
Listeleme API'leri sayfalama kullanır:

```
GET /api/v1/employees/?page=2&page_size=10
```

**Yanıt:**
```json
{
    "count": 100,
    "next": "http://api.saas.local/api/v1/employees/?page=3",
    "previous": "http://api.saas.local/api/v1/employees/?page=1",
    "results": [ ... ]
}
```

### Filtreleme ve Arama
API endpoint'leri filtreleme ve arama özelliklerini destekler:

**Filtreleme:**
```
GET /api/v1/employees/?branch=1&is_active=true
```

**Arama:**
```
GET /api/v1/companies/?search=acme
```

**Sıralama:**
```
GET /api/v1/invoices/?ordering=-created_at
```

### Rate Limiting
API istekleri rate limiting ile sınırlandırılmıştır:
- Anonim: 100 istek/saat
- Kimliği Doğrulanmış: 1000 istek/saat
- Premium: 10000 istek/saat

### Versiyonlama
API'nin mevcut versiyonu v1'dir. URL'de versiyon belirtilmelidir:
```
/api/v1/...
```

### Destek
Teknik destek için:
- Email: support@saas.local
- Docs: https://docs.saas.local
- Status: https://status.saas.local
""",
        terms_of_service="https://www.saas.local/terms/",
        contact=openapi.Contact(
            name="API Support Team",
            url="https://support.saas.local",
            email="api@saas.local"
        ),
        license=openapi.License(
            name="Proprietary License",
            url="https://www.saas.local/license/"
        ),
        x_logo={
            "url": "https://www.saas.local/static/images/logo.png",
            "backgroundColor": "#FFFFFF",
            "altText": "SaaS Logo"
        },
        x_tagGroups=[
            {
                "name": "Kimlik Doğrulama",
                "tags": ["auth", "users"]
            },
            {
                "name": "Şirket Yönetimi",
                "tags": ["companies", "branches", "employees"]
            },
            {
                "name": "Abonelik ve Ödeme",
                "tags": ["plans", "subscriptions", "invoices"]
            },
            {
                "name": "Bildirimler",
                "tags": ["notifications", "announcements"]
            },
            {
                "name": "Sistem",
                "tags": ["maintenance", "api-usage", "audit-logs"]
            }
        ]
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    authentication_classes=(),
    patterns=[
        path('api/v1/', include('saas.urls')),
        path('auth/', include('saas.urls')),
    ],
)

# API Router
router = DefaultRouter()

# Konum endpoint'leri
router.register(r'cities', views.CityViewSet)
router.register(r'districts', views.DistrictViewSet)
router.register(r'neighborhoods', views.NeighborhoodViewSet)

# Şirket ve şube endpoint'leri
router.register(r'companies', views.CompanyViewSet)
router.register(r'branches', views.BranchViewSet)
router.register(r'employees', views.EmployeeViewSet)

# Abonelik ve ödeme endpoint'leri
router.register(r'plans', views.PlanViewSet)
router.register(r'subscriptions', views.SubscriptionViewSet)
router.register(r'invoices', views.InvoiceViewSet)

# Bildirim endpoint'leri
router.register(r'notifications', views.NotificationViewSet)
router.register(r'announcements', views.AnnouncementViewSet)

# Sistem endpoint'leri
router.register(r'maintenance', views.MaintenanceModeViewSet)
router.register(r'branding', views.CompanyBrandingViewSet)
router.register(r'api-usage', views.APIUsageViewSet)
router.register(r'integrations', views.IntegrationViewSet)
router.register(r'files', views.FileStorageViewSet)
router.register(r'audit-logs', views.AuditLogViewSet)

app_name = 'saas'

urlpatterns = [
    # Auth URLs
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # API Dokümantasyonu
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    # API endpoints (v1)
    path('api/v1/', include(router.urls)),
]

# Debug Toolbar URL'leri
if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns

# Medya dosyaları için URL (development)
if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 