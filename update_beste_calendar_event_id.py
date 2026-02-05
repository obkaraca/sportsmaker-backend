"""
Beste Özer'in calendar item'ına event_id ekle
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
    beste_id = "aafe3f2e-b3b4-47a1-a83a-0758bdb698b3"
    
    # Event'i bul
    event = await db.events.find_one({"title": {"$regex": "Ankara Veteran", "$options": "i"}})
    if not event:
        print("❌ Event bulunamadı!")
        return
    
    event_id = event.get('id')
    print(f"✅ Event ID: {event_id}")
    
    # Beste'nin calendar item'ını bul
    calendar_item = await db.calendar_items.find_one({
        "user_id": beste_id,
        "type": "event"
    })
    
    if not calendar_item:
        print("❌ Calendar item bulunamadı!")
        return
    
    print(f"\n📅 Mevcut calendar item:")
    print(f"   ID: {calendar_item.get('id')}")
    print(f"   Title: {calendar_item.get('title')}")
    print(f"   event_id: {calendar_item.get('event_id', 'YOK!')}")
    
    # event_id ekle
    await db.calendar_items.update_one(
        {"_id": calendar_item["_id"]},
        {"$set": {"event_id": event_id}}
    )
    
    print(f"\n✅ event_id eklendi: {event_id}")
    
    # Verify
    updated = await db.calendar_items.find_one({"_id": calendar_item["_id"]})
    print(f"\n✅ Güncellenmiş calendar item:")
    print(f"   event_id: {updated.get('event_id')}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
