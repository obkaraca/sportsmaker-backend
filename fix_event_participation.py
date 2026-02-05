"""
Özgür Barış Karaca'yı Ankara Veteran etkinliğine ekle ve ajandaya kaydet
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
from datetime import datetime
import uuid

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

async def main():
    print("="*80)
    print("🔧 ETKİNLİK KATILIMI VE AJANDA OLUŞTURMA")
    print("="*80)
    
    user_id = "07ab0660-c851-47fd-b1e5-4d67ea5d4551"
    
    # Etkinliği bul
    event = await db.events.find_one({"title": {"$regex": "Ankara Veteran", "$options": "i"}})
    
    if not event:
        print("\n❌ Etkinlik bulunamadı!")
        return
    
    event_id = event.get('id')
    print(f"\n✅ Etkinlik bulundu: {event.get('title')}")
    
    # 1. Participation oluştur
    participation_id = str(uuid.uuid4())
    
    participation = {
        "id": participation_id,
        "event_id": event_id,
        "user_id": user_id,
        "status": "confirmed",
        "payment_status": "completed",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z"
    }
    
    await db.participations.insert_one(participation)
    print(f"\n✅ PARTICIPATION OLUŞTURULDU:")
    print(f"   ID: {participation_id}")
    print(f"   Status: confirmed")
    
    # 2. Event'in participants listesine ekle
    await db.events.update_one(
        {"id": event_id},
        {"$addToSet": {"participants": user_id}}
    )
    print(f"\n✅ Event participants listesine eklendi")
    
    # 3. Calendar item oluştur
    calendar_id = str(uuid.uuid4())
    
    calendar_item = {
        "id": calendar_id,
        "user_id": user_id,
        "type": "event",
        "title": event.get('title'),
        "date": event.get('start_date'),
        "start_time": event.get('start_date'),
        "end_time": event.get('end_date'),
        "location": event.get('city'),
        "description": event.get('description', ''),
        "is_read": False,
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    
    await db.calendar_items.insert_one(calendar_item)
    print(f"\n✅ AJANDA MADDESİ OLUŞTURULDU:")
    print(f"   ID: {calendar_id}")
    print(f"   Title: {event.get('title')}")
    print(f"   Date: {event.get('start_date')}")
    print(f"   Location: {event.get('city')}")
    print(f"   is_read: False")
    
    print("\n" + "="*80)
    print("✅ İŞLEM TAMAMLANDI")
    print("   - Participation kaydı oluşturuldu")
    print("   - Event participants listesine eklendi")
    print("   - Ajanda maddesi oluşturuldu")
    print("="*80)
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
