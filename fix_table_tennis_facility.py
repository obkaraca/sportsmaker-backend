"""
Ankara Masa Tenisi Salonu'nu düzelt ve sport config ekle
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
import uuid
from datetime import datetime

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

async def main():
    print("="*80)
    print("🔧 ANKARA MASA TENİSİ SALONU DÜZELTİLİYOR")
    print("="*80)
    
    # Tesis ID
    facility_id = "1293c458-715a-4490-a93d-93c95afe9f3e"
    
    # 1. Tesisi aktif yap
    result = await db.facilities.update_one(
        {"id": facility_id},
        {"$set": {
            "is_active": True,
            "is_verified": True,
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }}
    )
    
    print(f"\n✅ Tesis aktif yapıldı (matched: {result.matched_count}, modified: {result.modified_count})")
    
    # 2. Sport configs ekle
    configs = [
        {
            "sport": "Masa Tenisi",
            "field_type": "Standart Masa",
            "field_size": "Olimpik",
            "hourly_rate": 80,
            "description": "Profesyonel masa tenisi masası, olimpik standartlarda"
        },
        {
            "sport": "Masa Tenisi",
            "field_type": "Antrenman Masası",
            "field_size": "Standart",
            "hourly_rate": 60,
            "description": "Antrenman için uygun masa tenisi masası"
        }
    ]
    
    for config_data in configs:
        config_id = str(uuid.uuid4())
        
        sport_config = {
            "id": config_id,
            "facility_id": facility_id,
            "sport": config_data["sport"],
            "field_type": config_data["field_type"],
            "field_size": config_data["field_size"],
            "hourly_rate": config_data["hourly_rate"],
            "description": config_data["description"],
            "is_active": True,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        
        await db.sport_configs.insert_one(sport_config)
        print(f"\n✅ Sport Config eklendi:")
        print(f"   {config_data['sport']} - {config_data['field_type']}")
        print(f"   {config_data['hourly_rate']} TL/saat")
    
    # 3. Verify
    facility = await db.facilities.find_one({"id": facility_id})
    configs_count = await db.sport_configs.count_documents({"facility_id": facility_id})
    
    print(f"\n📊 SONUÇ:")
    print(f"   Tesis: {facility.get('name')}")
    print(f"   is_active: {facility.get('is_active')}")
    print(f"   is_verified: {facility.get('is_verified')}")
    print(f"   Sport configs: {configs_count} adet")
    
    print("\n" + "="*80)
    print("✅ ANKARA MASA TENİSİ SALONU HAZIR!")
    print("="*80)
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
