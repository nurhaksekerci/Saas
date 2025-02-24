from django.core.management.base import BaseCommand
import json
import requests
from saas.models import City, District, Neighborhood
from django.db import transaction

class Command(BaseCommand):
    help = 'Türkiye il, ilçe ve mahalle verilerini yükler'

    def delete_neighborhoods_in_chunks(self, chunk_size=1000):
        """Mahalleleri küçük parçalar halinde sil"""
        total_deleted = 0
        while True:
            # ID'leri al
            neighborhood_ids = list(
                Neighborhood.objects.values_list('id', flat=True)[:chunk_size]
            )
            if not neighborhood_ids:
                break
            # ID'lere göre sil
            deleted_count = Neighborhood.objects.filter(id__in=neighborhood_ids).delete()[0]
            total_deleted += deleted_count
            self.stdout.write(f"{deleted_count} mahalle silindi... (Toplam: {total_deleted})")

    def handle(self, *args, **kwargs):
        self.stdout.write('Konum verileri yükleniyor...')
        
        base_url = "https://raw.githubusercontent.com/metinyildirimnet/turkiye-adresler-json/main"
        
        try:
            # İlleri yükle
            self.stdout.write('İller kontrol ediliyor...')
            cities_response = requests.get(f"{base_url}/sehirler.json")
            cities_data = cities_response.json()
            
            with transaction.atomic():
                # İlleri kontrol et ve eksikleri kaydet
                cities_dict = {}
                new_cities_count = 0
                existing_cities = {city.id: city for city in City.objects.all()}
                
                for city in cities_data:
                    city_id = int(city['sehir_id'])
                    if city_id not in existing_cities:
                        city_obj = City.objects.create(
                            id=city_id,
                            name=city['sehir_adi'],
                            code=str(city_id).zfill(2)
                        )
                        new_cities_count += 1
                        cities_dict[str(city_id)] = city_obj
                    else:
                        cities_dict[str(city_id)] = existing_cities[city_id]
                
                self.stdout.write(self.style.SUCCESS(
                    f'{new_cities_count} yeni il kaydedildi. '
                    f'Toplam {len(cities_dict)} il mevcut.'
                ))

                # İlçeleri yükle
                self.stdout.write('İlçeler kontrol ediliyor...')
                districts_response = requests.get(f"{base_url}/ilceler.json")
                districts_data = districts_response.json()
                
                districts_dict = {}
                new_districts_count = 0
                existing_districts = {district.id: district for district in District.objects.all()}
                
                for district in districts_data:
                    district_id = int(district['ilce_id'])
                    if district_id not in existing_districts:
                        district_obj = District.objects.create(
                            id=district_id,
                            name=district['ilce_adi'],
                            city=cities_dict[district['sehir_id']]
                        )
                        new_districts_count += 1
                        districts_dict[str(district_id)] = district_obj
                    else:
                        districts_dict[str(district_id)] = existing_districts[district_id]
                
                self.stdout.write(self.style.SUCCESS(
                    f'{new_districts_count} yeni ilçe kaydedildi. '
                    f'Toplam {len(districts_dict)} ilçe mevcut.'
                ))

                # Mahalleleri yükle
                self.stdout.write('Mahalleler siliniyor...')
                self.delete_neighborhoods_in_chunks()
                self.stdout.write('Tüm mahalleler silindi.')

                # Tüm mahalle verilerini topla
                all_neighborhoods = []

                for i in range(1, 5):
                    self.stdout.write(f"Mahalle dosyası {i} yükleniyor...")
                    neighborhoods_response = requests.get(f"{base_url}/mahalleler-{i}.json")
                    data = neighborhoods_response.json()
                    
                    # Debug: İlk mahalle verisini kontrol et
                    if i == 1 and data:
                        self.stdout.write(f"Örnek mahalle verisi: {data[0]}")
                    
                    self.stdout.write(f"Dosya {i}: {len(data)} mahalle bulundu")
                    all_neighborhoods.extend(data)

                # Mahalleleri küçük gruplar halinde kaydet
                self.stdout.write('Mahalleler kaydediliyor...')
                batch_size = 500
                neighborhoods_to_create = []
                seen_neighborhoods = set()
                total_created = 0

                for neighborhood in all_neighborhoods:
                    try:
                        mahalle_id = neighborhood.get('mahalle_id')
                        mahalle_adi = neighborhood.get('mahalle_adi')
                        ilce_id = neighborhood.get('ilce_id')
                        
                        # Boş veya 0 ID'li kayıtları atla
                        if not mahalle_id or mahalle_id == '0' or not mahalle_adi.strip():
                            self.stdout.write(self.style.WARNING(
                                f"Geçersiz mahalle verisi (atlandı): İlçe: {neighborhood.get('ilce_adi')}, "
                                f"Şehir: {neighborhood.get('sehir_adi')}"
                            ))
                            continue

                        unique_key = f"{mahalle_adi}_{ilce_id}"
                        
                        if unique_key not in seen_neighborhoods:
                            seen_neighborhoods.add(unique_key)
                            
                            # District kontrolü
                            if ilce_id not in districts_dict:
                                self.stdout.write(self.style.WARNING(
                                    f"İlçe bulunamadı: {ilce_id} ({neighborhood.get('ilce_adi')})"
                                ))
                                continue
                                
                            neighborhoods_to_create.append(Neighborhood(
                                id=int(mahalle_id),
                                name=mahalle_adi.strip(),  # Boşlukları temizle
                                district=districts_dict[ilce_id]
                            ))

                            # Batch size'a ulaşınca kaydet
                            if len(neighborhoods_to_create) >= batch_size:
                                Neighborhood.objects.bulk_create(
                                    neighborhoods_to_create,
                                    ignore_conflicts=True
                                )
                                total_created += len(neighborhoods_to_create)
                                self.stdout.write(f"{total_created} mahalle kaydedildi...")
                                neighborhoods_to_create = []
                    
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(
                            f"Mahalle işlenirken hata: {str(e)}, Veri: {neighborhood}"
                        ))
                        continue

                # Kalan mahalleleri kaydet
                if neighborhoods_to_create:
                    Neighborhood.objects.bulk_create(
                        neighborhoods_to_create,
                        ignore_conflicts=True
                    )
                    total_created += len(neighborhoods_to_create)

                self.stdout.write(self.style.SUCCESS(f'Toplam {total_created} mahalle kaydedildi'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Hata oluştu: {str(e)}'))
            raise e

        self.stdout.write(self.style.SUCCESS('Tüm konum verileri başarıyla yüklendi!')) 