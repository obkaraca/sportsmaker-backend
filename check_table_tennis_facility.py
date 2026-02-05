"""
Ankara'da masa tenisi tesisi kontrolü
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
    print("🏓 MASA TENİSİ TESİSİ KONTROLÜ")
    print("="*80)
    
    # 1. Ankara'daki tüm tesisler
    ankara_facilities = await db.facilities.find({"city": "Ankara"}).to_list(None)
    print(f"\n📍 Ankara'daki tesisler: {len(ankara_facilities)}")
    
    for fac in ankara_facilities:
        print(f"\n   - {fac.get('name')}")
        print(f"     ID: {fac.get('id')}")
        print(f"     Owner: {fac.get('owner_id')}")
        print(f"     Active: {fac.get('is_active')}")
    
    # 2. Masa tenisi sport configs
    table_tennis_configs = await db.sport_configs.find({
        "sport": {"$regex": "masa tenisi", "$options": "i"}
    }).to_list(None)
    
    print(f"\n\n🏓 Masa Tenisi Sport Configs: {len(table_tennis_configs)}")
    
    for config in table_tennis_configs:
        print(f"\n   Config ID: {config.get('id')}")
        print(f"   Facility ID: {config.get('facility_id')}")
        print(f"   Sport: {config.get('sport')}")
        print(f"   Field Type: {config.get('field_type')}")
        print(f"   Hourly Rate: {config.get('hourly_rate')} TL")
        print(f"   Active: {config.get('is_active')}")
        
        # Bu config'in tesisini bul
        facility = await db.facilities.find_one({"id": config.get('facility_id')})
        if facility:
            print(f"   Tesis: {facility.get('name')} ({facility.get('city')})")
            print(f"   Tesis Active: {facility.get('is_active')}")
        else:
            print(f"   ❌ Tesis bulunamadı!")
    
    # 3. "Masa Tenisi Salonu" adında tesis var mı?
    print(f"\n\n🔍 'Masa Tenisi Salonu' araması:")
    specific = await db.facilities.find_one({
        "name": {"$regex": "masa tenisi", "$options": "i"}
    })
    
    if specific:
        print(f"\n   ✅ Bulundu: {specific.get('name')}")
        print(f"   ID: {specific.get('id')}")
        print(f"   City: {specific.get('city')}")
        print(f"   Active: {specific.get('is_active')}")
        
        # Bu tesisin sport configs
        configs = await db.sport_configs.find({"facility_id": specific.get('id')}).to_list(None)
        print(f"   Sport Configs: {len(configs)}")
        for c in configs:
            print(f"      - {c.get('sport')}: {c.get('hourly_rate')} TL/saat")
    else:
        print(f"\n   ❌ 'Masa Tenisi Salonu' adında tesis bulunamadı!")
        print(f"   Yeni tesis oluşturulmalı mı?")
    
    print("\n" + "="*80)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
