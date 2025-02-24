from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import timedelta

def tr_slugify(text):
    """
    Türkçe karakterleri düzelterek slug oluşturur
    """
    text = text.replace('ı', 'i')
    text = text.replace('İ', 'i')
    text = text.replace('ğ', 'g')
    text = text.replace('Ğ', 'g')
    text = text.replace('ü', 'u')
    text = text.replace('Ü', 'u')
    text = text.replace('ş', 's')
    text = text.replace('Ş', 's')
    text = text.replace('ö', 'o')
    text = text.replace('Ö', 'o')
    text = text.replace('ç', 'c')
    text = text.replace('Ç', 'c')
    return slugify(text)

def unique_slugify(instance, slug, counter=0):
    """
    Verilen slug'ın benzersiz olmasını sağlar
    Eğer slug kullanımdaysa sonuna sayı ekler
    """
    suffix = f"-{counter}" if counter > 0 else ""
    test_slug = f"{slug}{suffix}"
    
    # Aynı model içinde slug kontrolü
    qs = instance.__class__.objects.filter(slug=test_slug)
    
    # Düzenleme durumunda kendisini hariç tut
    if instance.pk:
        qs = qs.exclude(pk=instance.pk)
    
    # Branch ve Employee için company/branch bazında kontrol
    if isinstance(instance, Branch):
        qs = qs.filter(company=instance.company)
    elif isinstance(instance, Employee):
        qs = qs.filter(branch=instance.branch)
    
    if qs.exists():
        # Recursive olarak yeni sayı ile dene
        return unique_slugify(instance, slug, counter + 1)
    return test_slug

class BaseModel(models.Model):
    is_active = models.BooleanField(default=True, verbose_name="Aktif mi?")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma Tarihi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")

    class Meta:
        abstract = True

class City(BaseModel):
    name = models.CharField(max_length=50, verbose_name="İl Adı")
    code = models.CharField(max_length=2, unique=True, verbose_name="İl Kodu")
    
    class Meta:
        verbose_name = 'İl'
        verbose_name_plural = 'İller'
        ordering = ['name']
    
    def __str__(self):
        return self.name

class District(BaseModel):
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='districts', verbose_name="İl")
    name = models.CharField(max_length=50, verbose_name="İlçe Adı")
    
    class Meta:
        verbose_name = 'İlçe'
        verbose_name_plural = 'İlçeler'
        ordering = ['name']
        unique_together = ['city', 'name']
    
    def __str__(self):
        return f"{self.city.name} - {self.name}"

class Neighborhood(BaseModel):
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='neighborhoods', verbose_name="İlçe")
    name = models.CharField(max_length=100, verbose_name="Mahalle Adı")
    postal_code = models.CharField(max_length=5, blank=True, null=True, verbose_name="Posta Kodu")
    
    class Meta:
        verbose_name = 'Mahalle'
        verbose_name_plural = 'Mahalleler'
        ordering = ['name']
        unique_together = ['district', 'name']
    
    def __str__(self):
        return f"{self.district.city.name} - {self.district.name} - {self.name}"

class Currency(BaseModel):
    name = models.CharField(max_length=50, verbose_name="Para Birimi Adı")
    code = models.CharField(max_length=3, unique=True, verbose_name="Para Birimi Kodu")
    symbol = models.CharField(max_length=5, verbose_name="Sembol")
    
    class Meta:
        verbose_name = 'Para Birimi'
        verbose_name_plural = 'Para Birimleri'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"

class Company(BaseModel):
    COMPANY_TYPES = [
        ('sahis', 'Şahıs Şirketi'),
        ('kolektif', 'Kolektif Şirket'),
        ('komandit', 'Komandit Şirket'),
        ('limited', 'Limited Şirket'),
        ('anonim', 'Anonim Şirket'),
        ('kooperatif', 'Kooperatif'),
        ('other', 'Diğer')
    ]
    
    name = models.CharField(max_length=100, verbose_name="Şirket Adı")
    company_type = models.CharField(
        max_length=20, 
        choices=COMPANY_TYPES, 
        default='limited',
        verbose_name="Şirket Türü"
    )
    slug = models.SlugField(max_length=150, unique=True, blank=True, verbose_name="URL")
    tax_number = models.CharField(max_length=10, unique=True, verbose_name="Vergi Numarası")
    tax_office = models.CharField(max_length=50, verbose_name="Vergi Dairesi")
    phone = models.CharField(max_length=15, verbose_name="Telefon")
    email = models.EmailField(verbose_name="E-posta")
    address = models.TextField(verbose_name="Adres")
    neighborhood = models.ForeignKey(Neighborhood, on_delete=models.SET_NULL, null=True, verbose_name="Mahalle")
    
    class Meta:
        verbose_name = 'Şirket'
        verbose_name_plural = 'Şirketler'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_company_type_display()})"

    def save(self, *args, **kwargs):
        is_new = self._state.adding  # Yeni kayıt mı kontrolü
        
        if not self.slug:
            slug = tr_slugify(self.name)
            self.slug = unique_slugify(self, slug)
        
        super().save(*args, **kwargs)

        # Yeni şirket ise otomatik işlemleri yap
        if is_new:
            # Merkez şube oluştur
            self.create_main_branch()
            
            # 30 günlük deneme planı oluştur
            try:
                trial_plan = Plan.objects.get(id=1)  # Deneme planı (ID: 1)
                
                from .models import Subscription  # Circular import'u önlemek için
                
                Subscription.objects.create(
                    company=self,
                    plan=trial_plan,
                    status='active',
                    start_date=timezone.now().date(),
                    end_date=timezone.now().date() + timedelta(days=30),
                    is_trial=True,
                    trial_ends=timezone.now().date() + timedelta(days=30)
                )
            except Plan.DoesNotExist:
                # Plan bulunamazsa log kaydı oluştur
                from django.core.exceptions import ObjectDoesNotExist
                from django.core.mail import mail_admins
                
                error_message = f"ID'si 1 olan deneme planı bulunamadı. Şirket: {self.name}"
                mail_admins(
                    "Deneme Planı Hatası",
                    error_message
                )
                raise ObjectDoesNotExist(error_message)

    def create_main_branch(self):
        """Şirket için merkez şube oluşturur"""
        from .models import Branch  # Circular import'u önlemek için
        
        return Branch.objects.create(
            company=self,
            name="Merkez Şube",
            is_main_branch=True,
            phone=self.phone,
            email=self.email,
            address=self.address,
            neighborhood=self.neighborhood
        )

@receiver(post_save, sender=Company)
def create_main_branch(sender, instance, created, **kwargs):
    """Yeni şirket oluşturulduğunda otomatik merkez şube oluşturur"""
    if created:
        instance.create_main_branch()

class Branch(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='branches', verbose_name="Şirket")
    name = models.CharField(max_length=100, verbose_name="Şube Adı")
    slug = models.SlugField(max_length=150, blank=True, verbose_name="URL")
    phone = models.CharField(max_length=15, verbose_name="Telefon")
    email = models.EmailField(verbose_name="E-posta")
    address = models.TextField(verbose_name="Adres")
    neighborhood = models.ForeignKey(Neighborhood, on_delete=models.SET_NULL, null=True, verbose_name="Mahalle")
    is_main_branch = models.BooleanField(default=False, verbose_name="Ana Şube mi?")
    
    class Meta:
        verbose_name = 'Şube'
        verbose_name_plural = 'Şubeler'
        ordering = ['company', 'name']
        unique_together = [
            ['company', 'name'],
            ['company', 'slug']  # Aynı şirkette aynı slug olamaz
        ]
    
    def __str__(self):
        return f"{self.company.name} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            slug = tr_slugify(f"{self.company.name} {self.name}")
            self.slug = unique_slugify(self, slug)
        super().save(*args, **kwargs)

class Employee(BaseModel):
    GENDER_CHOICES = [
        ('M', 'Erkek'),
        ('F', 'Kadın'),
        ('O', 'Diğer')
    ]
    
    ROLE_CHOICES = [
        ('employee', 'Çalışan'),
        ('branch_admin', 'Şube Yöneticisi'),
        ('company_admin', 'Şirket Yöneticisi'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee', verbose_name="Kullanıcı")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='employees', verbose_name="Şube")
    slug = models.SlugField(max_length=150, blank=True, verbose_name="URL")
    identity_number = models.CharField(max_length=11, unique=True, verbose_name="TC Kimlik No")
    birth_date = models.DateField(verbose_name="Doğum Tarihi")
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, verbose_name="Cinsiyet")
    phone = models.CharField(max_length=15, verbose_name="Telefon")
    address = models.TextField(verbose_name="Adres")
    neighborhood = models.ForeignKey(Neighborhood, on_delete=models.SET_NULL, null=True, verbose_name="Mahalle")
    hire_date = models.DateField(verbose_name="İşe Başlama Tarihi")
    termination_date = models.DateField(null=True, blank=True, verbose_name="İşten Ayrılma Tarihi")
    
    # Yeni eklenen rol alanları
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='employee',
        verbose_name="Rol"
    )
    
    class Meta:
        verbose_name = 'Çalışan'
        verbose_name_plural = 'Çalışanlar'
        ordering = ['user__first_name', 'user__last_name']
        unique_together = [
            ['branch', 'slug']  # Aynı şubede aynı slug olamaz
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.branch.name}/{self.branch.company.name}"
    
    @property
    def full_name(self):
        return self.user.get_full_name()

    @property
    def is_company_admin(self):
        """Şirket yöneticisi mi?"""
        return self.role == 'company_admin'
    
    @property
    def is_branch_admin(self):
        """Şube yöneticisi mi?"""
        return self.role == 'branch_admin'

    def save(self, *args, **kwargs):
        if not self.slug:
            slug = tr_slugify(f"{self.user.get_full_name()} {self.identity_number[-4:]}")
            self.slug = unique_slugify(self, slug)
        super().save(*args, **kwargs)

class Plan(BaseModel):
    name = models.CharField(max_length=50, verbose_name="Plan Adı")
    slug = models.SlugField(max_length=70, unique=True, blank=True, verbose_name="URL")
    description = models.TextField(verbose_name="Açıklama")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Fiyat")
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, verbose_name="Para Birimi")
    max_users = models.PositiveIntegerField(verbose_name="Maksimum Kullanıcı Sayısı")
    max_storage = models.PositiveIntegerField(verbose_name="Depolama Alanı (MB)")
    features = models.JSONField(default=dict, verbose_name="Özellikler")
    
    class Meta:
        verbose_name = 'Plan'
        verbose_name_plural = 'Planlar'
        ordering = ['price']
    
    def __str__(self):
        return f"{self.name} - {self.price} {self.currency.code}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, tr_slugify(self.name))
        super().save(*args, **kwargs)

class Subscription(BaseModel):
    STATUS_CHOICES = [
        ('trial', 'Deneme'),
        ('active', 'Aktif'),
        ('past_due', 'Ödeme Bekliyor'),
        ('canceled', 'İptal Edildi'),
        ('expired', 'Süresi Doldu')
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='subscriptions', verbose_name="Şirket")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, verbose_name="Plan")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trial', verbose_name="Durum")
    start_date = models.DateTimeField(verbose_name="Başlangıç Tarihi")
    end_date = models.DateTimeField(verbose_name="Bitiş Tarihi")
    trial_ends = models.DateTimeField(null=True, blank=True, verbose_name="Deneme Süresi Bitişi")
    canceled_at = models.DateTimeField(null=True, blank=True, verbose_name="İptal Tarihi")
    
    class Meta:
        verbose_name = 'Abonelik'
        verbose_name_plural = 'Abonelikler'
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.company.name} - {self.plan.name}"

class Invoice(BaseModel):
    STATUS_CHOICES = [
        ('draft', 'Taslak'),
        ('pending', 'Beklemede'),
        ('paid', 'Ödendi'),
        ('canceled', 'İptal Edildi'),
        ('refunded', 'İade Edildi')
    ]
    
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='invoices', verbose_name="Abonelik")
    number = models.CharField(max_length=50, unique=True, verbose_name="Fatura No")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Tutar")
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, verbose_name="Para Birimi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Durum")
    due_date = models.DateField(verbose_name="Son Ödeme Tarihi")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Ödeme Tarihi")
    notes = models.TextField(blank=True, verbose_name="Notlar")
    
    class Meta:
        verbose_name = 'Fatura'
        verbose_name_plural = 'Faturalar'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.number} - {self.subscription.company.name}"

class Notification(BaseModel):
    NOTIFICATION_TYPES = [
        ('info', 'Bilgi'),
        ('warning', 'Uyarı'),
        ('success', 'Başarılı'),
        ('error', 'Hata'),
        ('system', 'Sistem'),
    ]

    SCOPE_TYPES = [
        ('user', 'Tek Kullanıcı'),
        ('company', 'Şirket Geneli'),
        ('branch', 'Şube Geneli'),
        ('all', 'Tüm Kullanıcılar'),
    ]

    title = models.CharField(max_length=255, verbose_name="Başlık")
    message = models.TextField(verbose_name="Mesaj")
    notification_type = models.CharField(
        max_length=20, 
        choices=NOTIFICATION_TYPES, 
        default='info',
        verbose_name="Bildirim Tipi"
    )
    scope = models.CharField(
        max_length=20,
        choices=SCOPE_TYPES,
        default='user',
        verbose_name="Kapsam"
    )
    
    # Bildirim hedefleri (NULL olabilir çünkü scope'a göre kullanılacak)
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE,
        null=True, 
        blank=True,
        verbose_name="Şirket"
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Şube"
    )
    
    # Bildirim oluşturan kullanıcı (sistem bildirimleri için NULL olabilir)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_notifications',
        verbose_name="Oluşturan"
    )
    
    # Otomatik bildirimler için referans
    reference_model = models.CharField(max_length=50, null=True, blank=True)
    reference_id = models.PositiveIntegerField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Bildirim'
        verbose_name_plural = 'Bildirimler'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_notification_type_display()}: {self.title}"

class NotificationRecipient(BaseModel):
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name='recipients',
        verbose_name="Bildirim"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="Kullanıcı"
    )
    is_read = models.BooleanField(default=False, verbose_name="Okundu mu?")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="Okunma Tarihi")
    
    class Meta:
        verbose_name = 'Bildirim Alıcısı'
        verbose_name_plural = 'Bildirim Alıcıları'
        unique_together = ['notification', 'user']
        ordering = ['-notification__created_at']
    
    def __str__(self):
        return f"{self.notification.title} -> {self.user.get_full_name()}"
    
    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()

class MaintenanceMode(BaseModel):
    PLATFORM_CHOICES = [
        ('all', 'Tüm Platformlar'),
        ('web', 'Web Uygulaması'),
        ('mobile', 'Mobil Uygulama'),
        ('api', 'API Servisleri'),
    ]

    STATUS_CHOICES = [
        ('scheduled', 'Planlandı'),
        ('in_progress', 'Devam Ediyor'),
        ('completed', 'Tamamlandı'),
        ('canceled', 'İptal Edildi'),
    ]

    ACCESS_LEVELS = [
        ('none', 'Erişim Yok'),
        ('superuser', 'Sadece Süper Kullanıcılar'),
        ('staff', 'Yönetici Kullanıcılar'),
        ('company_admin', 'Şirket Yöneticileri'),
        ('all', 'Tüm Kullanıcılar'),
    ]

    title = models.CharField(max_length=255, verbose_name="Bakım Başlığı")
    description = models.TextField(verbose_name="Bakım Açıklaması")
    platform = models.CharField(
        max_length=20,
        choices=PLATFORM_CHOICES,
        default='all',
        verbose_name="Platform"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='scheduled',
        verbose_name="Durum"
    )
    
    # Bakım zamanlaması
    planned_start_time = models.DateTimeField(verbose_name="Planlanan Başlangıç")
    planned_end_time = models.DateTimeField(verbose_name="Planlanan Bitiş")
    actual_start_time = models.DateTimeField(null=True, blank=True, verbose_name="Gerçek Başlangıç")
    actual_end_time = models.DateTimeField(null=True, blank=True, verbose_name="Gerçek Bitiş")
    
    # Bakım ayarları
    show_message = models.BooleanField(default=True, verbose_name="Mesaj Gösterilsin mi?")
    block_access = models.BooleanField(default=True, verbose_name="Erişim Engellensin mi?")
    access_level = models.CharField(
        max_length=20,
        choices=ACCESS_LEVELS,
        default='superuser',
        verbose_name="Erişim Seviyesi",
        help_text="Bakım sırasında kimlerin erişebileceğini belirler"
    )
    allowed_companies = models.ManyToManyField(
        Company,
        blank=True,
        verbose_name="İzin Verilen Şirketler",
        help_text="Sadece seçili şirketlerin erişimine izin verir (boş bırakılırsa tüm şirketler için geçerlidir)"
    )
    
    # Bakımı yapan ekip
    maintenance_team = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Bakım Ekibi",
        help_text="Bakımdan sorumlu ekip üyeleri ve görevleri"
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_maintenances',
        verbose_name="Oluşturan"
    )

    class Meta:
        verbose_name = 'Bakım Modu'
        verbose_name_plural = 'Bakım Modları'
        ordering = ['-planned_start_time']

    def __str__(self):
        return f"{self.get_platform_display()} - {self.title}"

    @property
    def is_active(self):
        """Bakımın şu anda aktif olup olmadığını kontrol eder"""
        now = timezone.now()
        if self.status == 'in_progress' and self.actual_start_time:
            return not self.actual_end_time or self.actual_end_time > now
        return False

    def can_access(self, user):
        """
        Kullanıcının bakım sırasında erişim izni olup olmadığını kontrol eder
        """
        if not self.block_access:
            return True

        if not user.is_authenticated:
            return False

        # Süper kullanıcılar her zaman erişebilir
        if user.is_superuser:
            return True

        access_level = self.access_level

        if access_level == 'none':
            return False
        elif access_level == 'superuser':
            return user.is_superuser
        elif access_level == 'staff':
            return user.is_staff
        elif access_level == 'company_admin':
            # Kullanıcının şirket yöneticisi olup olmadığını kontrol et
            if hasattr(user, 'employee'):
                company = user.employee.branch.company
                # Eğer allowed_companies belirtilmişse, şirketin izinli olup olmadığını kontrol et
                if self.allowed_companies.exists():
                    return (
                        company.employees.filter(user=user, is_company_admin=True).exists() and
                        self.allowed_companies.filter(id=company.id).exists()
                    )
                return company.employees.filter(user=user, is_company_admin=True).exists()
            return False
        elif access_level == 'all':
            # Eğer allowed_companies belirtilmişse, kullanıcının şirketinin izinli olup olmadığını kontrol et
            if self.allowed_companies.exists() and hasattr(user, 'employee'):
                return self.allowed_companies.filter(id=user.employee.branch.company.id).exists()
            return True
        
        return False

    def start_maintenance(self):
        """Bakımı başlatır"""
        if self.status == 'scheduled':
            self.status = 'in_progress'
            self.actual_start_time = timezone.now()
            self.save()
            
            # Otomatik bildirim oluştur
            Notification.objects.create(
                title=f"Sistem Bakımı Başladı: {self.title}",
                message=self.description,
                notification_type='system',
                scope='all',
                reference_model='MaintenanceMode',
                reference_id=self.id
            )

    def end_maintenance(self):
        """Bakımı sonlandırır"""
        if self.status == 'in_progress':
            self.status = 'completed'
            self.actual_end_time = timezone.now()
            self.save()
            
            # Otomatik bildirim oluştur
            Notification.objects.create(
                title=f"Sistem Bakımı Tamamlandı: {self.title}",
                message=f"{self.title} bakımı başarıyla tamamlanmıştır.",
                notification_type='system',
                scope='all',
                reference_model='MaintenanceMode',
                reference_id=self.id
            )

class Announcement(BaseModel):
    TARGET_ROLES = [
        ('all', 'Tüm Kullanıcılar'),
        ('superuser', 'Süper Kullanıcılar'),
        ('staff', 'Sistem Yetkilileri'),
        ('company_admin', 'Şirket Yöneticileri'),
        ('branch_admin', 'Şube Yöneticileri'),
        ('employee', 'Çalışanlar'),
    ]

    PRIORITY_LEVELS = [
        ('low', 'Düşük'),
        ('medium', 'Orta'),
        ('high', 'Yüksek'),
        ('urgent', 'Acil'),
    ]

    title = models.CharField(max_length=255, verbose_name="Başlık")
    content = models.TextField(verbose_name="İçerik")
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_LEVELS,
        default='medium',
        verbose_name="Öncelik"
    )
    target_role = models.CharField(
        max_length=20,
        choices=TARGET_ROLES,
        default='all',
        verbose_name="Hedef Rol"
    )
    target_companies = models.ManyToManyField(
        Company,
        blank=True,
        verbose_name="Hedef Şirketler",
        help_text="Boş bırakılırsa tüm şirketler için geçerli olur"
    )
    publish_date = models.DateTimeField(
        default=timezone.now,
        verbose_name="Yayın Tarihi"
    )
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Bitiş Tarihi",
        help_text="Boş bırakılırsa süresiz yayınlanır"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_announcements',
        verbose_name="Oluşturan"
    )
    
    class Meta:
        verbose_name = 'Duyuru'
        verbose_name_plural = 'Duyurular'
        ordering = ['-publish_date', '-priority']

    def __str__(self):
        return f"{self.get_priority_display()}: {self.title}"

    @property
    def is_active(self):
        """Duyurunun aktif olup olmadığını kontrol eder"""
        now = timezone.now()
        if self.publish_date > now:
            return False
        if self.end_date and self.end_date < now:
            return False
        return True

    def can_view(self, user):
        """Kullanıcının duyuruyu görüntüleme yetkisi var mı kontrol eder"""
        if not user.is_authenticated:
            return False

        # Süper kullanıcılar her zaman görüntüleyebilir
        if user.is_superuser:
            return True

        # Sistem yetkilileri her zaman görüntüleyebilir
        if user.is_staff:
            return True

        # Kullanıcının çalışan kaydı yoksa görüntüleyemez
        if not hasattr(user, 'employee'):
            return False

        employee = user.employee
        company = employee.branch.company

        # Hedef şirketler belirtilmişse, kullanıcının şirketi kontrol edilir
        if self.target_companies.exists():
            if not self.target_companies.filter(id=company.id).exists():
                return False

        # Hedef role göre kontrol
        target_role = self.target_role
        if target_role == 'all':
            return True
        elif target_role == 'company_admin':
            return employee.is_company_admin
        elif target_role == 'branch_admin':
            return employee.is_branch_admin
        elif target_role == 'employee':
            return employee.role == 'employee'
        
        return False

    def create_notification(self):
        """Duyuru için otomatik bildirim oluşturur"""
        notification = Notification.objects.create(
            title=f"Yeni Duyuru: {self.title}",
            message=self.content,
            notification_type='info',
            scope='all' if not self.target_companies.exists() else 'company',
            reference_model='Announcement',
            reference_id=self.id,
            created_by=self.created_by
        )

        # Hedef şirketler varsa bildirime ekle
        if self.target_companies.exists():
            notification.company = self.target_companies.first()
            notification.save()

        return notification

    def save(self, *args, **kwargs):
        # Yeni oluşturuluyorsa bildirim gönder
        is_new = not self.pk
        super().save(*args, **kwargs)
        
        if is_new:
            self.create_notification()

class AnnouncementRead(BaseModel):
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name='reads',
        verbose_name="Duyuru"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='announcement_reads',
        verbose_name="Kullanıcı"
    )
    read_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Okunma Tarihi"
    )

    class Meta:
        verbose_name = 'Duyuru Okunma'
        verbose_name_plural = 'Duyuru Okunmaları'
        unique_together = ['announcement', 'user']
        ordering = ['-read_at']

    def __str__(self):
        return f"{self.announcement.title} - {self.user.get_full_name()}"

class CompanyBranding(BaseModel):
    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name='branding',
        verbose_name="Şirket"
    )
    logo = models.ImageField(
        upload_to='company_logos/',
        null=True,
        blank=True,
        verbose_name="Logo"
    )
    favicon = models.ImageField(
        upload_to='company_favicons/',
        null=True,
        blank=True,
        verbose_name="Favicon"
    )
    primary_color = models.CharField(
        max_length=7,
        default="#007bff",
        verbose_name="Ana Renk"
    )
    secondary_color = models.CharField(
        max_length=7,
        default="#6c757d",
        verbose_name="İkincil Renk"
    )
    custom_css = models.TextField(
        blank=True,
        verbose_name="Özel CSS"
    )
    custom_js = models.TextField(
        blank=True,
        verbose_name="Özel JavaScript"
    )
    
    class Meta:
        verbose_name = 'Şirket Görünümü'
        verbose_name_plural = 'Şirket Görünümleri'

class APIUsage(BaseModel):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='api_usage',
        verbose_name="Şirket"
    )
    endpoint = models.CharField(
        max_length=255,
        verbose_name="API Endpoint"
    )
    method = models.CharField(
        max_length=10,
        verbose_name="HTTP Metodu"
    )
    requests_count = models.PositiveIntegerField(
        default=0,
        verbose_name="İstek Sayısı"
    )
    data_transfer = models.BigIntegerField(
        default=0,
        verbose_name="Veri Transferi (bytes)"
    )
    date = models.DateField(
        verbose_name="Tarih"
    )

    class Meta:
        verbose_name = 'API Kullanımı'
        verbose_name_plural = 'API Kullanımları'
        unique_together = ['company', 'endpoint', 'method', 'date']

class Integration(BaseModel):
    INTEGRATION_TYPES = [
        ('payment', 'Ödeme Sistemi'),
        ('sms', 'SMS Servisi'),
        ('email', 'E-posta Servisi'),
        ('crm', 'CRM Sistemi'),
        ('erp', 'ERP Sistemi'),
        ('other', 'Diğer'),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='integrations',
        verbose_name="Şirket"
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Entegrasyon Adı"
    )
    integration_type = models.CharField(
        max_length=20,
        choices=INTEGRATION_TYPES,
        verbose_name="Entegrasyon Tipi"
    )
    api_key = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="API Anahtarı"
    )
    api_secret = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="API Gizli Anahtarı"
    )
    settings = models.JSONField(
        default=dict,
        verbose_name="Ayarlar"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Aktif mi?"
    )

    class Meta:
        verbose_name = 'Entegrasyon'
        verbose_name_plural = 'Entegrasyonlar'

class FileStorage(BaseModel):
    FILE_TYPES = [
        ('document', 'Doküman'),
        ('image', 'Görsel'),
        ('video', 'Video'),
        ('other', 'Diğer'),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='files',
        verbose_name="Şirket"
    )
    file = models.FileField(
        upload_to='company_files/',
        verbose_name="Dosya"
    )
    file_type = models.CharField(
        max_length=20,
        choices=FILE_TYPES,
        verbose_name="Dosya Tipi"
    )
    file_size = models.PositiveIntegerField(
        verbose_name="Dosya Boyutu (bytes)"
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_files',
        verbose_name="Yükleyen"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Açıklama"
    )

    class Meta:
        verbose_name = 'Dosya'
        verbose_name_plural = 'Dosyalar'

class AuditLog(BaseModel):
    ACTION_TYPES = [
        ('create', 'Oluşturma'),
        ('update', 'Güncelleme'),
        ('delete', 'Silme'),
        ('login', 'Giriş'),
        ('logout', 'Çıkış'),
        ('other', 'Diğer'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs',
        verbose_name="Kullanıcı"
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='audit_logs',
        verbose_name="Şirket"
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_TYPES,
        verbose_name="İşlem"
    )
    content_type = models.ForeignKey(
        'contenttypes.ContentType',
        on_delete=models.CASCADE,
        verbose_name="İçerik Tipi"
    )
    object_id = models.PositiveIntegerField(verbose_name="Nesne ID")
    object_repr = models.CharField(
        max_length=200,
        verbose_name="Nesne Gösterimi"
    )
    changes = models.JSONField(
        default=dict,
        verbose_name="Değişiklikler"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        verbose_name="IP Adresi"
    )
    user_agent = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Kullanıcı Tarayıcısı"
    )

    class Meta:
        verbose_name = 'İşlem Kaydı'
        verbose_name_plural = 'İşlem Kayıtları'
        ordering = ['-created_at']


