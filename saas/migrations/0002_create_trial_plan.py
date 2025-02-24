from django.db import migrations
from django.utils import timezone

def create_trial_plan(apps, schema_editor):
    Plan = apps.get_model('saas', 'Plan')
    Currency = apps.get_model('saas', 'Currency')
    
    # Varsayılan para birimi (TRY) oluştur
    currency, _ = Currency.objects.get_or_create(
        code='TRY',
        defaults={
            'name': 'Türk Lirası',
            'symbol': '₺',
            'is_default': True
        }
    )
    
    # Eğer ID 1 olan plan yoksa oluştur
    if not Plan.objects.filter(id=1).exists():
        Plan.objects.create(
            id=1,
            name='30 Günlük Deneme',
            description='30 günlük ücretsiz deneme sürümü',
            price=0,
            currency=currency,
            features={
                'max_branches': 1,
                'max_employees': 10,
                'storage_limit': 100,  # MB
                'api_limit': 1000,     # Günlük API çağrısı
            },
            is_trial=True,
            is_active=True,
            created_at=timezone.now(),
            updated_at=timezone.now()
        )

def remove_trial_plan(apps, schema_editor):
    Plan = apps.get_model('saas', 'Plan')
    Plan.objects.filter(id=1).delete()

class Migration(migrations.Migration):
    dependencies = [
        ('saas', '0001_initial'),  # İlk migration'a bağımlı
    ]

    operations = [
        migrations.RunPython(create_trial_plan, remove_trial_plan),
    ] 