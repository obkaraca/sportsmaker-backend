"""
Test için eksiksiz tesis sahibi kullanıcısı oluştur
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
import uuid
import bcrypt
from datetime import datetime

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

async def main():
    print("="*80)
    print("🏢 TESİS SAHİBİ KULLANICISI OLUŞTURMA")
    print("="*80)
    
    # 1. Kullanıcı oluştur
    user_id = str(uuid.uuid4())
    hashed_password = bcrypt.hashpw("123456".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    user = {
        "id": user_id,
        "full_name": "Mehmet Yılmaz",
        "email": "mehmet@sporttesis.com",
        "phone": "+905551234567",
        "password": hashed_password,
        "hashed_password": hashed_password,
        "user_type": "facility_owner",
        "is_active": True,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "profile_image": "https://randomuser.me/api/portraits/men/32.jpg",
        "bio": "Ankara'nın en modern spor tesislerinden birinin sahibiyim. 15 yıllık deneyimle spor tutkunlarına hizmet veriyoruz.",
        "location": {
            "city": "Ankara",
            "district": "Çankaya",
            "address": "Kızılay, Atatürk Bulvarı No:125"
        }
    }
    
    await db.users.insert_one(user)
    print(f"\n✅ Kullanıcı oluşturuldu:")
    print(f"   ID: {user_id}")
    print(f"   Ad: Mehmet Yılmaz")
    print(f"   Email: mehmet@sporttesis.com")
    print(f"   Telefon: +905551234567")
    print(f"   Şifre: 123456")
    print(f"   Tip: facility_owner")
    
    # 2. Tesis oluştur
    facility_id = str(uuid.uuid4())
    
    facility = {
        "id": facility_id,
        "owner_id": user_id,
        "name": "Ankara Spor Merkezi",
        "description": "Modern ekipmanlar ve profesyonel antrenörler eşliğinde spor yapabileceğiniz, çok amaçlı spor tesisi. Halı saha, basketbol, voleybol ve tenis kortları mevcut.",
        "city": "Ankara",
        "district": "Çankaya",
        "address": "Kızılay, Atatürk Bulvarı No:125, Çankaya/Ankara",
        "location": {
            "type": "Point",
            "coordinates": [32.8543, 39.9208]  # Ankara Kızılay
        },
        "photos": [
            "https://images.unsplash.com/photo-1574629810360-7efbbe195018?w=800",
            "https://images.unsplash.com/photo-1556817411-31ae72fa3ea0?w=800",
            "https://images.unsplash.com/photo-1526506118085-60ce8714f8c5?w=800",
            "https://images.unsplash.com/photo-1571902943202-507ec2618e8f?w=800"
        ],
        "phone": "+903124445566",
        "email": "info@ankaraspormerkezim.com",
        "website": "www.ankaraspormerkezim.com",
        "working_hours": {
            "monday": {"open": "08:00", "close": "23:00"},
            "tuesday": {"open": "08:00", "close": "23:00"},
            "wednesday": {"open": "08:00", "close": "23:00"},
            "thursday": {"open": "08:00", "close": "23:00"},
            "friday": {"open": "08:00", "close": "23:00"},
            "saturday": {"open": "09:00", "close": "22:00"},
            "sunday": {"open": "09:00", "close": "22:00"}
        },
        "amenities": [
            "Ücretsiz Otopark",
            "Duş ve Soyunma Odası",
            "Kafe",
            "Spor Malzemesi Kiralama",
            "Profesyonel Antrenör",
            "Aydınlatma Sistemi",
            "Wi-Fi",
            "Soyunma Dolabı",
            "Klima"
        ],
        "rules": [
            "Rezervasyon saatinden 10 dakika geç kalınırsa rezervasyon iptal edilir",
            "Tesise spor ayakkabısı ile girilmelidir",
            "Sigara içmek yasaktır",
            "Tesisin genel kurallarına uyulmalıdır"
        ],
        "is_active": True,
        "is_verified": True,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "rating": 4.7,
        "review_count": 156
    }
    
    await db.facilities.insert_one(facility)
    print(f"\n✅ Tesis oluşturuldu:")
    print(f"   ID: {facility_id}")
    print(f"   Ad: Ankara Spor Merkezi")
    print(f"   Şehir: Ankara / Çankaya")
    print(f"   Rating: 4.7/5 (156 yorum)")
    
    # 3. Spor konfigürasyonları oluştur
    sports = [
        {
            "sport": "Futbol",
            "field_type": "Halı Saha",
            "field_size": "7x7",
            "hourly_rate": 350,
            "description": "Profesyonel FIFA onaylı halı saha, aydınlatma sistemi mevcut"
        },
        {
            "sport": "Futbol",
            "field_type": "Halı Saha",
            "field_size": "11x11",
            "hourly_rate": 600,
            "description": "Tam boy halı saha, profesyonel aydınlatma ve kale sistemleri"
        },
        {
            "sport": "Basketbol",
            "field_type": "Kapalı Salon",
            "field_size": "Standart",
            "hourly_rate": 200,
            "description": "Kapalı basketbol sahası, profesyonel parke zemin"
        },
        {
            "sport": "Voleybol",
            "field_type": "Kapalı Salon",
            "field_size": "Standart",
            "hourly_rate": 180,
            "description": "Profesyonel voleybol sahası, yüksek tavan"
        },
        {
            "sport": "Tenis",
            "field_type": "Açık Kort",
            "field_size": "Standart",
            "hourly_rate": 150,
            "description": "Akrilik zemin tenis kortu, aydınlatma sistemi"
        }
    ]
    
    sport_config_ids = []
    for sport_data in sports:
        config_id = str(uuid.uuid4())
        
        sport_config = {
            "id": config_id,
            "facility_id": facility_id,
            "sport": sport_data["sport"],
            "field_type": sport_data["field_type"],
            "field_size": sport_data["field_size"],
            "hourly_rate": sport_data["hourly_rate"],
            "description": sport_data["description"],
            "is_active": True,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        
        await db.sport_configs.insert_one(sport_config)
        sport_config_ids.append(config_id)
        print(f"\n   ✅ Spor: {sport_data['sport']} - {sport_data['field_type']} ({sport_data['field_size']}) - {sport_data['hourly_rate']} TL/saat")
    
    # 4. Örnek yorumlar oluştur
    reviews = [
        {
            "user_name": "Ali Demir",
            "rating": 5,
            "comment": "Harika bir tesis! Temizlik ve profesyonellik açısından çok başarılılar.",
            "date": "2025-11-15"
        },
        {
            "user_name": "Ayşe Kaya",
            "rating": 4,
            "comment": "Halı saha kalitesi çok iyi, fiyatlar makul. Otopark biraz dar.",
            "date": "2025-11-20"
        },
        {
            "user_name": "Can Yıldız",
            "rating": 5,
            "comment": "Basketbol sahası muhteşem! Kesinlikle tavsiye ederim.",
            "date": "2025-11-25"
        }
    ]
    
    for review_data in reviews:
        review_id = str(uuid.uuid4())
        review = {
            "id": review_id,
            "facility_id": facility_id,
            "user_name": review_data["user_name"],
            "rating": review_data["rating"],
            "comment": review_data["comment"],
            "created_at": review_data["date"] + "T10:00:00Z"
        }
        await db.reviews.insert_one(review)
    
    print(f"\n✅ 3 örnek yorum eklendi")
    
    # 5. Özet
    print("\n" + "="*80)
    print("📊 OLUŞTURMA ÖZETİ")
    print("="*80)
    print(f"\n👤 Kullanıcı Bilgileri:")
    print(f"   Email: mehmet@sporttesis.com")
    print(f"   Şifre: 123456")
    print(f"   Telefon: +905551234567")
    print(f"   Tip: Tesis Sahibi")
    
    print(f"\n🏢 Tesis Bilgileri:")
    print(f"   Ad: Ankara Spor Merkezi")
    print(f"   Konum: Ankara / Çankaya - Kızılay")
    print(f"   Spor Sayısı: {len(sports)}")
    print(f"   Rating: 4.7/5 (156 yorum)")
    print(f"   Durum: Aktif ve Onaylı")
    
    print(f"\n⚽ Mevcut Sporlar:")
    for sport in sports:
        print(f"   - {sport['sport']}: {sport['field_size']} - {sport['hourly_rate']} TL/saat")
    
    print(f"\n✨ Özellikler:")
    print(f"   - Tam dolu profil bilgileri")
    print(f"   - Profesyonel fotoğraflar (4 adet)")
    print(f"   - Detaylı çalışma saatleri")
    print(f"   - 9 farklı tesis özelliği")
    print(f"   - 5 farklı spor konfigürasyonu")
    print(f"   - 3 örnek müşteri yorumu")
    
    print("\n" + "="*80)
    print("✅ TESİS SAHİBİ HESABI HAZIR!")
    print("="*80)
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
