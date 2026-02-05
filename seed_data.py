"""
Seed data script for SportConnect
Creates sample venues, coaches, and referees
"""
import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import uuid
from passlib.context import CryptContext
import os
from dotenv import load_dotenv

load_dotenv()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "test_database")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

async def create_sample_venues():
    """Create sample venues"""
    venues = [
        {
            "id": str(uuid.uuid4()),
            "name": "Olimpiyat Spor Kompleksi",
            "address": "Atatürk Bulvarı No:123, Çankaya",
            "city": "Ankara",
            "owner_id": "system",
            "sports": ["Futbol", "Basketbol", "Voleybol"],
            "facilities": ["Soyunma Odası", "Duş", "Kafe", "Otopark", "Aydınlatma"],
            "hourly_rate": 300,
            "capacity": 22,
            "dimensions": "40m x 20m",
            "rating": 4.5,
            "rating_count": 120,
            "location": {"lat": 39.9334, "lng": 32.8597},
            "images": [],
            "available_hours": {
                "monday": ["09:00-23:00"],
                "tuesday": ["09:00-23:00"],
                "wednesday": ["09:00-23:00"],
                "thursday": ["09:00-23:00"],
                "friday": ["09:00-23:00"],
                "saturday": ["08:00-23:00"],
                "sunday": ["08:00-23:00"]
            },
            "approved": True,
            "is_active": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Kadıköy Spor Salonu",
            "address": "Bahariye Caddesi No:45, Kadıköy",
            "city": "İstanbul Anadolu",
            "owner_id": "system",
            "sports": ["Basketbol", "Voleybol", "Masa Tenisi"],
            "facilities": ["Soyunma Odası", "Duş", "Tribün", "Kafe"],
            "hourly_rate": 350,
            "capacity": 20,
            "dimensions": "28m x 15m",
            "rating": 4.7,
            "rating_count": 89,
            "location": {"lat": 40.9894, "lng": 29.0257},
            "images": [],
            "is_active": True,
            "available_hours": {
                "monday": ["10:00-22:00"],
                "tuesday": ["10:00-22:00"],
                "wednesday": ["10:00-22:00"],
                "thursday": ["10:00-22:00"],
                "friday": ["10:00-22:00"],
                "saturday": ["09:00-22:00"],
                "sunday": ["09:00-20:00"]
            },
            "approved": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Beşiktaş Arena",
            "address": "Fulya Mahallesi No:78, Beşiktaş",
            "city": "İstanbul Avrupa",
            "owner_id": "system",
            "sports": ["Futbol", "Tenis"],
            "facilities": ["Soyunma Odası", "Duş", "Otopark", "Kafe", "Aydınlatma", "Tribün"],
            "hourly_rate": 400,
            "capacity": 24,
            "dimensions": "50m x 30m",
            "rating": 4.8,
            "rating_count": 156,
            "location": {"lat": 41.0422, "lng": 29.0072},
            "images": [],
            "is_active": True,
            "available_hours": {
                "monday": ["08:00-23:00"],
                "tuesday": ["08:00-23:00"],
                "wednesday": ["08:00-23:00"],
                "thursday": ["08:00-23:00"],
                "friday": ["08:00-23:00"],
                "saturday": ["07:00-23:00"],
                "sunday": ["07:00-23:00"]
            },
            "approved": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "İzmir Spor Merkezi",
            "address": "Alsancak Mahallesi No:234, Konak",
            "city": "İzmir",
            "owner_id": "system",
            "sports": ["Futbol", "Basketbol", "Voleybol", "Masa Tenisi"],
            "facilities": ["Soyunma Odası", "Duş", "Otopark", "Kafe", "Aydınlatma"],
            "hourly_rate": 280,
            "capacity": 18,
            "dimensions": "35m x 18m",
            "rating": 4.3,
            "rating_count": 67,
            "location": {"lat": 38.4237, "lng": 27.1428},
            "images": [],
            "is_active": True,
            "available_hours": {
                "monday": ["09:00-22:00"],
                "tuesday": ["09:00-22:00"],
                "wednesday": ["09:00-22:00"],
                "thursday": ["09:00-22:00"],
                "friday": ["09:00-22:00"],
                "saturday": ["08:00-22:00"],
                "sunday": ["08:00-20:00"]
            },
            "approved": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Antalya Tenis Kulübü",
            "address": "Konyaaltı Sahil No:12, Konyaaltı",
            "city": "Antalya",
            "owner_id": "system",
            "sports": ["Tenis", "Masa Tenisi"],
            "facilities": ["Soyunma Odası", "Duş", "Kafe", "Otopark"],
            "hourly_rate": 250,
            "capacity": 8,
            "dimensions": "23m x 11m (kort)",
            "rating": 4.6,
            "rating_count": 45,
            "location": {"lat": 36.8969, "lng": 30.7133},
            "images": [],
            "is_active": True,
            "available_hours": {
                "monday": ["07:00-21:00"],
                "tuesday": ["07:00-21:00"],
                "wednesday": ["07:00-21:00"],
                "thursday": ["07:00-21:00"],
                "friday": ["07:00-21:00"],
                "saturday": ["07:00-21:00"],
                "sunday": ["07:00-19:00"]
            },
            "approved": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Bursa Voleybol Salonu",
            "address": "Nilüfer Caddesi No:56, Nilüfer",
            "city": "Bursa",
            "owner_id": "system",
            "sports": ["Voleybol", "Basketbol"],
            "facilities": ["Soyunma Odası", "Duş", "Tribün", "Otopark"],
            "hourly_rate": 270,
            "capacity": 16,
            "dimensions": "30m x 16m",
            "rating": 4.4,
            "rating_count": 52,
            "location": {"lat": 40.1826, "lng": 29.0666},
            "images": [],
            "is_active": True,
            "available_hours": {
                "monday": ["09:00-22:00"],
                "tuesday": ["09:00-22:00"],
                "wednesday": ["09:00-22:00"],
                "thursday": ["09:00-22:00"],
                "friday": ["09:00-22:00"],
                "saturday": ["09:00-22:00"],
                "sunday": ["09:00-20:00"]
            },
            "approved": True,
            "created_at": datetime.utcnow()
        }
    ]
    
    for venue in venues:
        existing = await db.venues.find_one({"name": venue["name"]})
        if not existing:
            await db.venues.insert_one(venue)
            print(f"✅ Created venue: {venue['name']}")
        else:
            print(f"⏭️  Venue already exists: {venue['name']}")

async def create_sample_coaches():
    """Create sample coaches"""
    coaches = [
        {
            "id": str(uuid.uuid4()),
            "email": "mehmet.coach@example.com",
            "phone": "+905551234567",
            "password_hash": pwd_context.hash("coach123"),
            "full_name": "Mehmet Yılmaz",
            "user_type": "coach",
            "city": "Ankara",
            "date_of_birth": "1985-05-15",
            "sports": ["Futbol", "Basketbol"],
            "coach_profile": {
                "sports": ["Futbol", "Basketbol"],
                "skill_levels": {
                    "Futbol": "İleri",
                    "Basketbol": "Orta"
                },
                "available_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "available_hours": ["09:00-12:00", "14:00-18:00", "19:00-21:00"],
                "cities": ["Ankara", "Çankaya"],
                "hourly_rate": 250,
                "bio": "15 yıllık tecrübeli futbol ve basketbol antrenörü. UEFA B lisanslı. Gençler ve yetişkinler için özel antrenman programları.",
                "certifications": ["UEFA B Lisansı", "FIBA Level 2", "İlk Yardım Sertifikası"],
                "rating": 4.8,
                "review_count": 124
            },
            "verified": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "email": "ayse.coach@example.com",
            "phone": "+905552345678",
            "password_hash": pwd_context.hash("coach123"),
            "full_name": "Ayşe Demir",
            "user_type": "coach",
            "city": "İstanbul Anadolu",
            "date_of_birth": "1990-08-22",
            "sports": ["Voleybol", "Tenis"],
            "coach_profile": {
                "sports": ["Voleybol", "Tenis"],
                "skill_levels": {
                    "Voleybol": "İleri",
                    "Tenis": "İleri"
                },
                "available_days": ["monday", "wednesday", "friday", "saturday", "sunday"],
                "available_hours": ["10:00-13:00", "15:00-19:00"],
                "cities": ["İstanbul Anadolu", "Kadıköy", "Üsküdar"],
                "hourly_rate": 300,
                "bio": "Milli takım geçmişi olan voleybol ve tenis antrenörü. 10 yıldır profesyonel antrenörlük yapıyorum. Kadınlar ve çocuklar için özel programlar.",
                "certifications": ["Voleybol Antrenör Sertifikası", "ITF Tenis Level 2", "Spor Psikolojisi"],
                "rating": 4.9,
                "review_count": 87
            },
            "verified": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "email": "ahmet.coach@example.com",
            "phone": "+905553456789",
            "password_hash": pwd_context.hash("coach123"),
            "full_name": "Ahmet Kaya",
            "user_type": "coach",
            "city": "İstanbul Avrupa",
            "date_of_birth": "1988-03-10",
            "sports": ["Futbol"],
            "coach_profile": {
                "sports": ["Futbol"],
                "skill_levels": {
                    "Futbol": "İleri"
                },
                "available_days": ["tuesday", "thursday", "friday", "saturday"],
                "available_hours": ["08:00-12:00", "16:00-20:00"],
                "cities": ["İstanbul Avrupa", "Beşiktaş", "Sarıyer"],
                "hourly_rate": 350,
                "bio": "Eski profesyonel futbolcu ve UEFA A lisanslı antrenör. Kaleci antrenörlüğü konusunda uzmanım. Tüm seviyelerde özel antrenmanlar.",
                "certifications": ["UEFA A Lisansı", "Kaleci Antrenör Sertifikası", "Beslenme Koçluğu"],
                "rating": 4.7,
                "review_count": 156
            },
            "verified": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "email": "zeynep.coach@example.com",
            "phone": "+905554567890",
            "password_hash": pwd_context.hash("coach123"),
            "full_name": "Zeynep Şahin",
            "user_type": "coach",
            "city": "İzmir",
            "date_of_birth": "1992-11-05",
            "sports": ["Basketbol", "Masa Tenisi"],
            "coach_profile": {
                "sports": ["Basketbol", "Masa Tenisi"],
                "skill_levels": {
                    "Basketbol": "Orta",
                    "Masa Tenisi": "İleri"
                },
                "available_days": ["monday", "tuesday", "wednesday", "thursday", "saturday"],
                "available_hours": ["09:00-12:00", "14:00-17:00"],
                "cities": ["İzmir", "Konak", "Alsancak"],
                "hourly_rate": 220,
                "bio": "Gençlerle çalışmayı seven dinamik antrenör. Basketbol ve masa tenisinde 8 yıllık deneyim. Çocuk ve genç yaş grupları için özel programlar.",
                "certifications": ["FIBA Level 1", "Masa Tenisi Antrenör Belgesi", "Çocuk Psikolojisi"],
                "rating": 4.6,
                "review_count": 63
            },
            "verified": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "email": "emre.coach@example.com",
            "phone": "+905555678901",
            "password_hash": pwd_context.hash("coach123"),
            "full_name": "Emre Özkan",
            "user_type": "coach",
            "city": "Antalya",
            "date_of_birth": "1987-07-18",
            "sports": ["Tenis"],
            "coach_profile": {
                "sports": ["Tenis"],
                "skill_levels": {
                    "Tenis": "İleri"
                },
                "available_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                "available_hours": ["07:00-11:00", "17:00-20:00"],
                "cities": ["Antalya", "Konyaaltı", "Lara"],
                "hourly_rate": 280,
                "bio": "Profesyonel tenis antrenörü. ITF turnuvalarında oynadım. Başlangıç seviyesinden ileri seviyeye kadar tüm yaş gruplarına özel ders.",
                "certifications": ["ITF Level 3", "RPT (Registered Professional Tennis)", "Spor Fizyolojisi"],
                "rating": 4.9,
                "review_count": 91
            },
            "verified": True,
            "created_at": datetime.utcnow()
        }
    ]
    
    for coach in coaches:
        existing = await db.users.find_one({"email": coach["email"]})
        if not existing:
            await db.users.insert_one(coach)
            print(f"✅ Created coach: {coach['full_name']}")
        else:
            print(f"⏭️  Coach already exists: {coach['full_name']}")

async def create_sample_referees():
    """Create sample referees"""
    referees = [
        {
            "id": str(uuid.uuid4()),
            "email": "can.hakem@example.com",
            "phone": "+905556789012",
            "password_hash": pwd_context.hash("referee123"),
            "full_name": "Can Arslan",
            "user_type": "referee",
            "city": "Ankara",
            "date_of_birth": "1989-04-12",
            "sports": ["Futbol"],
            "referee_profile": {
                "sport": "Futbol",
                "level": "ulusal",
                "license_number": "TR-FB-2156",
                "years_of_experience": 8,
                "bio": "Ulusal klasman futbol hakemi. Süper Lig ve 1. Lig maçlarında görev aldım. Profesyonel yaklaşım ve adil hakemlik.",
                "available_days": ["friday", "saturday", "sunday"],
                "available_hours": ["09:00-21:00"],
                "rating": 4.7,
                "review_count": 143
            },
            "verified": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "email": "selin.hakem@example.com",
            "phone": "+905557890123",
            "password_hash": pwd_context.hash("referee123"),
            "full_name": "Selin Yıldırım",
            "user_type": "referee",
            "city": "İstanbul Anadolu",
            "date_of_birth": "1993-09-28",
            "sports": ["Basketbol"],
            "referee_profile": {
                "sport": "Basketbol",
                "level": "ulusal",
                "license_number": "TR-BB-3421",
                "years_of_experience": 6,
                "bio": "FIBA lisanslı basketbol hakemi. Kadın ve erkek liglerinde deneyimli. Genç ve amatör liglerde de görev alıyorum.",
                "available_days": ["wednesday", "thursday", "saturday", "sunday"],
                "available_hours": ["10:00-22:00"],
                "rating": 4.8,
                "review_count": 78
            },
            "verified": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "email": "murat.hakem@example.com",
            "phone": "+905558901234",
            "password_hash": pwd_context.hash("referee123"),
            "full_name": "Murat Demir",
            "user_type": "referee",
            "city": "İstanbul Avrupa",
            "date_of_birth": "1986-12-15",
            "sports": ["Futbol"],
            "referee_profile": {
                "sport": "Futbol",
                "level": "il",
                "license_number": "TR-FB-5678",
                "years_of_experience": 5,
                "bio": "İl klasman futbol hakemi. Amatör ve bölgesel liglerde görev alıyorum. Hafta sonu ve akşam maçlarında uygunum.",
                "available_days": ["friday", "saturday", "sunday"],
                "available_hours": ["14:00-22:00"],
                "rating": 4.5,
                "review_count": 67
            },
            "verified": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "email": "elif.hakem@example.com",
            "phone": "+905559012345",
            "password_hash": pwd_context.hash("referee123"),
            "full_name": "Elif Kara",
            "user_type": "referee",
            "city": "İzmir",
            "date_of_birth": "1991-06-20",
            "sports": ["Voleybol"],
            "referee_profile": {
                "sport": "Voleybol",
                "level": "ulusal",
                "license_number": "TR-VB-2893",
                "years_of_experience": 7,
                "bio": "Ulusal klasman voleybol hakemi. Kadın voleybol liginde aktif görev alıyorum. Turnuva ve maç organizasyonları için uygunum.",
                "available_days": ["tuesday", "wednesday", "thursday", "saturday", "sunday"],
                "available_hours": ["09:00-20:00"],
                "rating": 4.9,
                "review_count": 102
            },
            "verified": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "email": "berk.hakem@example.com",
            "phone": "+905550123456",
            "password_hash": pwd_context.hash("referee123"),
            "full_name": "Berk Özdemir",
            "user_type": "referee",
            "city": "Bursa",
            "date_of_birth": "1994-02-08",
            "sports": ["Basketbol"],
            "referee_profile": {
                "sport": "Basketbol",
                "level": "il",
                "license_number": "TR-BB-6754",
                "years_of_experience": 3,
                "bio": "İl klasman basketbol hakemi. Genç ve yıldız liglerde aktif. Hafta içi akşam ve hafta sonu müsaitim.",
                "available_days": ["monday", "tuesday", "thursday", "saturday", "sunday"],
                "available_hours": ["17:00-22:00"],
                "rating": 4.4,
                "review_count": 34
            },
            "verified": True,
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "email": "deniz.hakem@example.com",
            "phone": "+905551234560",
            "password_hash": pwd_context.hash("referee123"),
            "full_name": "Deniz Aydın",
            "user_type": "referee",
            "city": "Antalya",
            "date_of_birth": "1990-10-30",
            "sports": ["Tenis"],
            "referee_profile": {
                "sport": "Tenis",
                "level": "uluslararasi",
                "license_number": "ITF-WO-4521",
                "years_of_experience": 9,
                "bio": "ITF lisanslı uluslararası tenis hakemi. ATP ve WTA turnuvalarında görev aldım. Profesyonel ve amatör turnuvalarda deneyimliyim.",
                "available_days": ["friday", "saturday", "sunday"],
                "available_hours": ["08:00-19:00"],
                "rating": 5.0,
                "review_count": 56
            },
            "verified": True,
            "created_at": datetime.utcnow()
        }
    ]
    
    for referee in referees:
        existing = await db.users.find_one({"email": referee["email"]})
        if not existing:
            await db.users.insert_one(referee)
            print(f"✅ Created referee: {referee['full_name']}")
        else:
            print(f"⏭️  Referee already exists: {referee['full_name']}")

async def create_sample_events():
    """Create sample events"""
    from datetime import datetime, timedelta
    
    # Get some venue and user IDs for the events
    venues = await db.venues.find().limit(6).to_list(length=6)
    coaches = await db.users.find({"user_type": "coach"}).limit(5).to_list(length=5)
    referees = await db.users.find({"user_type": "referee"}).limit(6).to_list(length=6)
    
    if not venues or not coaches or not referees:
        print("⚠️  Need venues, coaches, and referees to create events. Skipping event creation.")
        return
    
    # Create events for the next 30 days
    base_date = datetime.utcnow()
    
    events = [
        {
            "id": str(uuid.uuid4()),
            "title": "Futbol Turnuvası - Ankara",
            "description": "Amatör futbol turnuvası. Tüm yaş grupları katılabilir. Ödüllü turnuva.",
            "event_type": "tournament",
            "sport": "Futbol",
            "start_date": base_date + timedelta(days=5, hours=9),
            "end_date": base_date + timedelta(days=5, hours=18),
            "venue_id": venues[0]["id"],
            "organizer_id": coaches[0]["id"],
            "city": "Ankara",
            "max_participants": 64,
            "participant_count": 0,
            "is_active": True,
            "images": [],
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Basketbol Ligi Maçı",
            "description": "Kadıköy Basketbol Ligi 3. hafta maçı. Seyirci kabul edilir.",
            "event_type": "maç",
            "sport": "Basketbol",
            "start_date": base_date + timedelta(days=7, hours=19),
            "end_date": base_date + timedelta(days=7, hours=21),
            "venue_id": venues[1]["id"],
            "organizer_id": coaches[1]["id"],
            "city": "İstanbul Anadolu",
            "max_participants": 24,
            "participant_count": 0,
            "is_active": True,
            "images": [],
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Voleybol Kampı",
            "description": "3 günlük yoğun voleybol antrenman kampı. Profesyonel antrenörler eşliğinde.",
            "event_type": "kamp",
            "sport": "Voleybol",
            "start_date": base_date + timedelta(days=12, hours=9),
            "end_date": base_date + timedelta(days=14, hours=17),
            "venue_id": venues[5]["id"],
            "organizer_id": coaches[1]["id"],
            "city": "Bursa",
            "max_participants": 20,
            "participant_count": 0,
            "is_active": True,
            "images": [],
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Tenis Turnuvası - Antalya",
            "description": "Açık kort tenis turnuvası. Tek ve çift kategorileri mevcut.",
            "event_type": "tournament",
            "sport": "Tenis",
            "start_date": base_date + timedelta(days=15, hours=8),
            "end_date": base_date + timedelta(days=15, hours=19),
            "venue_id": venues[4]["id"],
            "organizer_id": coaches[4]["id"],
            "city": "Antalya",
            "max_participants": 32,
            "participant_count": 0,
            "is_active": True,
            "images": [],
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Futbol Dostluk Maçı",
            "description": "Hafta sonu dostluk maçı. Herkes katılabilir, eğlence amaçlı.",
            "event_type": "maç",
            "sport": "Futbol",
            "start_date": base_date + timedelta(days=3, hours=15),
            "end_date": base_date + timedelta(days=3, hours=17),
            "venue_id": venues[2]["id"],
            "organizer_id": coaches[2]["id"],
            "city": "İstanbul Avrupa",
            "max_participants": 22,
            "participant_count": 0,
            "is_active": True,
            "images": [],
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Basketbol Antrenman Kampı",
            "description": "Gençler için 5 günlük basketbol antrenman kampı. Temel beceriler ve taktikler.",
            "event_type": "kamp",
            "sport": "Basketbol",
            "start_date": base_date + timedelta(days=20, hours=10),
            "end_date": base_date + timedelta(days=24, hours=16),
            "venue_id": venues[3]["id"],
            "organizer_id": coaches[3]["id"],
            "city": "İzmir",
            "max_participants": 16,
            "participant_count": 0,
            "is_active": True,
            "images": [],
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Masa Tenisi Ligi",
            "description": "Haftalık masa tenisi ligi. Her seviyeden oyuncu katılabilir.",
            "event_type": "lig",
            "sport": "Masa Tenisi",
            "start_date": base_date + timedelta(days=8, hours=18),
            "end_date": base_date + timedelta(days=8, hours=22),
            "venue_id": venues[3]["id"],
            "organizer_id": coaches[3]["id"],
            "city": "İzmir",
            "max_participants": 12,
            "participant_count": 0,
            "is_active": True,
            "images": [],
            "created_at": datetime.utcnow()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Voleybol Dostluk Turnuvası",
            "description": "Kadın voleybol dostluk turnuvası. Takım halinde katılım.",
            "event_type": "tournament",
            "sport": "Voleybol",
            "start_date": base_date + timedelta(days=25, hours=10),
            "end_date": base_date + timedelta(days=25, hours=18),
            "venue_id": venues[5]["id"],
            "organizer_id": coaches[1]["id"],
            "city": "Bursa",
            "max_participants": 48,
            "participant_count": 0,
            "is_active": True,
            "images": [],
            "created_at": datetime.utcnow()
        }
    ]
    
    for event in events:
        existing = await db.events.find_one({"title": event["title"]})
        if not existing:
            await db.events.insert_one(event)
            print(f"✅ Created event: {event['title']}")
        else:
            print(f"⏭️  Event already exists: {event['title']}")

async def main():
    print("\n🌱 Starting seed data generation...\n")
    
    print("📍 Creating sample venues...")
    await create_sample_venues()
    print()
    
    print("🏃 Creating sample coaches...")
    await create_sample_coaches()
    print()
    
    print("🛡️  Creating sample referees...")
    await create_sample_referees()
    print()
    
    print("🎯 Creating sample events...")
    await create_sample_events()
    print()
    
    print("✅ Seed data generation completed!\n")
    
    # Print summary
    venue_count = await db.venues.count_documents({})
    coach_count = await db.users.count_documents({"user_type": "coach"})
    referee_count = await db.users.count_documents({"user_type": "referee"})
    event_count = await db.events.count_documents({})
    
    print("📊 Database Summary:")
    print(f"   - Venues: {venue_count}")
    print(f"   - Coaches: {coach_count}")
    print(f"   - Referees: {referee_count}")
    print(f"   - Events: {event_count}")
    print()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Seed process interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
