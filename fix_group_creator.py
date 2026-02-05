"""
Grup sohbetinin created_by field'ını düzelt ve kontrol et
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
    print("🔧 GRUP CREATOR FIX")
    print("="*80)
    
    # Ankara Veteran grup sohbeti
    group = await db.group_chats.find_one({"name": {"$regex": "Ankara Veteran", "$options": "i"}})
    
    if not group:
        print("\n❌ Grup bulunamadı!")
        return
    
    print(f"\n📋 Mevcut Grup Durumu:")
    print(f"   ID: {group.get('id')}")
    print(f"   Name: {group.get('name')}")
    print(f"   Created By: {group.get('created_by')}")
    print(f"   Admin IDs: {group.get('admin_ids', [])}")
    print(f"   Event ID: {group.get('event_id')}")
    
    # Event'i bul
    event_id = group.get('event_id')
    if event_id:
        event = await db.events.find_one({"id": event_id})
        if event:
            organizer_id = event.get('organizer_id')
            print(f"\n📅 Event Bilgisi:")
            print(f"   Organizer ID: {organizer_id}")
            
            # Organizer bilgisi
            organizer = await db.users.find_one({"id": organizer_id})
            if organizer:
                print(f"   Organizer: {organizer.get('full_name')} ({organizer.get('email')})")
            
            # Grup'un created_by'ını düzelt
            if group.get('created_by') is None:
                print(f"\n🔧 Created_by field'ı None, düzeltiliyor...")
                await db.group_chats.update_one(
                    {"id": group.get('id')},
                    {"$set": {"created_by": organizer_id}}
                )
                print(f"✅ Created_by field'ı {organizer_id} olarak güncellendi")
            
            # Admin listesinde olduğundan emin ol
            if organizer_id not in group.get('admin_ids', []):
                print(f"\n🔧 Organizer admin listesinde değil, ekleniyor...")
                await db.group_chats.update_one(
                    {"id": group.get('id')},
                    {"$addToSet": {"admin_ids": organizer_id}}
                )
                print(f"✅ Organizer admin listesine eklendi")
            else:
                print(f"\n✅ Organizer zaten admin listesinde")
    
    # Final durum
    group_updated = await db.group_chats.find_one({"id": group.get('id')})
    print(f"\n📋 Güncellenmiş Grup Durumu:")
    print(f"   Created By: {group_updated.get('created_by')}")
    print(f"   Admin IDs: {group_updated.get('admin_ids', [])}")
    
    print("\n" + "="*80)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
