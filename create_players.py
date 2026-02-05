import asyncio
import motor.motor_asyncio
import uuid
from datetime import datetime
import random
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")

# Oyuncu listesi
players_str = """Abdülkadir TAŞÇI, Alp KAYMAN, Burak KARATATAR, Alperen KUZU, Ersoy ÖNEMLİ, Özgür Barış KARACA, Mustafa CANDAN, Cihan ADLI, Coşkun KOCAGÖZ, Salih GEÇGİL, Duran BEYAZIT, Barış UĞUR, Bilal SAN, Muhammet Ali ŞAHİN, Berke Arda DÜNDAR, Soner KARTOP, Erol DENİZ, Ahmet YILDIZGÖZ, Zafer AŞIK, Kağan YURDAL, Serhat ÖZKILIÇ, Emre BALLI, Haydar ÇINAR, Hakan GÖKÇAYIR, Muhammet KARTAL, Soner CANTÜRK, Nihat KAYALI, Mesut ALPARSLAN, Uğur ÖZGÜRGİL, Cavit YILMAZ, Koray YAVAŞ, Ömer YETİLMİŞ, Haydar KAHRAMAN, İlhan GÜLTEKİN, Yusuf TUNA, Şeref COŞKUNYÜREK, Bülent YAŞAR, Murat ER, İsmail Hakkı YİĞİT, Hasan KARCİ, Adil Samet YALÇINKAYA, Hami KALKAN, Abdurrahman YAVUZ, Çağlar Mehmet ÇAĞLAYAN, Cuma YAVUZ, Cüneyt GÜRBÜZ, Erol ALGÜN, Ümit İPEK, Sungur DURAN, Muammer ÖZKORUL, Yiğit Mehmet UZEL, Kubilay AKAYDIN, Tuncay GÖK, Murathan SAYINALP, İsmail DOLU, Erkan KAYA, Fatih YILDIRIM, Ender ALPAGÜL, Halit JABBAR, Emin TUĞRUL, Oktay UNCU, Onur ATAOĞLU, İsmail CANLI, Suna GENÇOĞLU, Mesut BAYRAM, Serdal YÜKSEL, Engin Burak KOÇAK, Eray KILIÇ, İrem TOMAK, Metin Alp YURTSEVEN, Tayfun KAYABAŞI, Abdülbasit YAVUZ, Ömer AYVAZ, Tevfik Furkan PEKŞEN, Ersin ATLAS"""

# Kadın oyuncular
female_players = ["İrem TOMAK", "Suna GENÇOĞLU"]

# Planet Lig event ID
EVENT_ID = "1dbb0527-bbfa-4338-991b-7f9e5278377b"

async def main():
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client.activity_tracker
    
    # Oyuncuları parse et
    players = [p.strip() for p in players_str.split(',') if p.strip()]
    print(f"Toplam {len(players)} oyuncu bulundu")
    
    # Etkinliği al
    event = await db.events.find_one({"id": EVENT_ID})
    if not event:
        print(f"❌ Etkinlik bulunamadı: {EVENT_ID}")
        return
    
    print(f"✅ Etkinlik bulundu: {event['title']}")
    
    created_users = []
    
    for i, player_name in enumerate(players):
        # İsim ve soyisim ayır
        parts = player_name.split()
        if len(parts) >= 2:
            first_name = ' '.join(parts[:-1])
            last_name = parts[-1]
        else:
            first_name = player_name
            last_name = ""
        
        full_name = player_name
        
        # Cinsiyet belirle
        gender = "female" if any(f.upper() in player_name.upper() for f in ["İREM TOMAK", "SUNA GENÇOĞLU"]) else "male"
        
        # Seviye belirle (ilk 25 iyi, sonraki 25 orta-iyi, son 25 orta)
        if i < 25:
            skill_level = "iyi"
        elif i < 50:
            skill_level = "orta-iyi"
        else:
            skill_level = "orta"
        
        # Email oluştur
        email = f"{first_name.lower().replace(' ', '').replace('ı', 'i').replace('ğ', 'g').replace('ü', 'u').replace('ş', 's').replace('ö', 'o').replace('ç', 'c').replace('İ', 'i')}.{last_name.lower().replace('ı', 'i').replace('ğ', 'g').replace('ü', 'u').replace('ş', 's').replace('ö', 'o').replace('ç', 'c').replace('İ', 'i')}@planetlig.com"
        
        # Kullanıcı var mı kontrol et
        existing = await db.users.find_one({"email": email})
        if existing:
            print(f"⚠️ Kullanıcı zaten var: {full_name} ({email})")
            user_id = existing["id"]
        else:
            # Yeni kullanıcı oluştur
            user_id = str(uuid.uuid4())
            user = {
                "id": user_id,
                "email": email,
                "full_name": full_name,
                "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4DpT2gVJgH1mPwHm",  # Default: password123
                "user_type": "player",
                "gender": gender,
                "city": "Ankara",
                "phone": f"05{random.randint(300000000, 599999999)}",
                "date_of_birth": f"{random.randint(1970, 2000)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                "player_profile": {
                    "skill_levels": {
                        "Masa Tenisi": skill_level
                    },
                    "preferred_sports": ["Masa Tenisi"],
                    "achievements": [],
                    "bio": f"Masa tenisi oyuncusu - {skill_level} seviye"
                },
                "is_verified": True,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            await db.users.insert_one(user)
            print(f"✅ Kullanıcı oluşturuldu: {full_name} ({gender}, {skill_level})")
        
        created_users.append(user_id)
        
        # Etkinliğe katılım ekle
        existing_participation = await db.event_participations.find_one({
            "event_id": EVENT_ID,
            "user_id": user_id
        })
        
        if existing_participation:
            print(f"⚠️ Zaten katılımcı: {full_name}")
        else:
            participation = {
                "id": str(uuid.uuid4()),
                "event_id": EVENT_ID,
                "user_id": user_id,
                "status": "confirmed",
                "registration_date": datetime.utcnow().isoformat(),
                "payment_status": "completed",
                "category": "Open",
                "created_at": datetime.utcnow().isoformat()
            }
            await db.event_participations.insert_one(participation)
            print(f"✅ Etkinliğe kaydedildi: {full_name}")
    
    # Etkinlik katılımcı sayısını güncelle
    participant_count = await db.event_participations.count_documents({"event_id": EVENT_ID, "status": "confirmed"})
    await db.events.update_one(
        {"id": EVENT_ID},
        {"$set": {
            "ticket_info.available_slots": max(0, event.get("max_participants", 100) - participant_count),
            "updated_at": datetime.utcnow().isoformat()
        }}
    )
    
    print(f"\n✅ Toplam {len(created_users)} oyuncu işlendi")
    print(f"✅ Etkinlik katılımcı sayısı: {participant_count}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
