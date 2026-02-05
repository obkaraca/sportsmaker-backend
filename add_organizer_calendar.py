"""
Beste Özer'e (organizatör) Ankara Veteran etkinliği için calendar item ekle
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
    print("🔧 ORGANIZATÖR CALENDAR ITEM OLUŞTURMA")
    print("="*80)
    
    # Event
    event = await db.events.find_one({"title": {"$regex": "Ankara Veteran", "$options": "i"}})
    if not event:
        print("\n❌ Event bulunamadı!")
        return
    
    event_id = event.get('id')
    organizer_id = event.get('organizer_id')
    
    print(f"\n📅 Event: {event.get('title')}")
    print(f"   Organizer ID: {organizer_id}")
    print(f"   Start: {event.get('start_date')}")
    print(f"   End: {event.get('end_date')}")
    
    # Organizatör bilgisi
    organizer = await db.users.find_one({"id": organizer_id})
    if organizer:
        print(f"   Organizer: {organizer.get('full_name')} ({organizer.get('email')})")
    
    # Organizatörün zaten calendar item'ı var mı?
    existing = await db.calendar_items.find_one({
        "user_id": organizer_id,
        "type": "event",
        "title": {"$regex": "Ankara Veteran", "$options": "i"}
    })
    
    if existing:
        print(f"\n✅ Organizatör için calendar item zaten mevcut:")
        print(f"   ID: {existing.get('id')}")
        print(f"   Title: {existing.get('title')}")
        return
    
    # Calendar item oluştur
    calendar_item = {
        "id": str(uuid.uuid4()),
        "user_id": organizer_id,
        "type": "event",
        "title": f"{event.get('title')} (Organizatör)",
        "date": event.get("start_date"),
        "start_time": event.get("start_date"),
        "end_time": event.get("end_date"),
        "location": event.get("city", ""),
        "description": f"Etkinlik organizatörüsünüz - {len(event.get('participants', []))} katılımcı",
        "is_read": False,
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    
    await db.calendar_items.insert_one(calendar_item)
    
    print(f"\n✅ CALENDAR ITEM OLUŞTURULDU:")
    print(f"   ID: {calendar_item['id']}")
    print(f"   User: {organizer_id}")
    print(f"   Title: {calendar_item['title']}")
    print(f"   Date: {calendar_item['date']}")
    
    print("\n" + "="*80)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
