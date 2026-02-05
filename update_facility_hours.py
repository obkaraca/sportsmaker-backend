"""
Ankara Spor Merkezi çalışma saatlerini güncelle
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

async def main():
    print("="*80)
    print("⏰ ANKARA SPOR MERKEZİ ÇALIŞMA SAATLERİ GÜNCELLENİYOR")
    print("="*80)
    
    # Mehmet Yılmaz'ın facility ID'si
    mehmet = await db.users.find_one({"email": "mehmet@sporttesis.com"})
    if not mehmet:
        print("\n❌ Mehmet Yılmaz bulunamadı!")
        return
    
    mehmet_id = mehmet.get('id')
    print(f"\n✅ Mehmet Yılmaz ID: {mehmet_id}")
    
    # Tesis bul
    facility = await db.facilities.find_one({"owner_id": mehmet_id})
    if not facility:
        print("\n❌ Tesis bulunamadı!")
        return
    
    facility_id = facility.get('id')
    facility_name = facility.get('name')
    
    print(f"\n✅ Tesis: {facility_name}")
    print(f"   ID: {facility_id}")
    
    # Yeni çalışma saatleri: Her gün 08:00-20:00
    new_working_hours = {
        "monday": {"open": "08:00", "close": "20:00"},
        "tuesday": {"open": "08:00", "close": "20:00"},
        "wednesday": {"open": "08:00", "close": "20:00"},
        "thursday": {"open": "08:00", "close": "20:00"},
        "friday": {"open": "08:00", "close": "20:00"},
        "saturday": {"open": "08:00", "close": "20:00"},
        "sunday": {"open": "08:00", "close": "20:00"}
    }
    
    # Güncelle
    result = await db.facilities.update_one(
        {"id": facility_id},
        {"$set": {"working_hours": new_working_hours}}
    )
    
    print(f"\n✅ Çalışma saatleri güncellendi:")
    print(f"   Matched: {result.matched_count}")
    print(f"   Modified: {result.modified_count}")
    
    print(f"\n📅 Yeni Çalışma Saatleri:")
    print(f"   Pazartesi - Pazar: 08:00 - 20:00")
    print(f"   (Her gün aynı saatler)")
    
    # Verify
    updated_facility = await db.facilities.find_one({"id": facility_id})
    print(f"\n✅ Doğrulama:")
    print(f"   Pazartesi: {updated_facility.get('working_hours', {}).get('monday')}")
    print(f"   Salı: {updated_facility.get('working_hours', {}).get('tuesday')}")
    print(f"   Çarşamba: {updated_facility.get('working_hours', {}).get('wednesday')}")
    
    print("\n" + "="*80)
    print("✅ ÇALIŞMA SAATLERİ GÜNCELLENDİ!")
    print("="*80)
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
