"""
Beste Özer'in admin yetkilerini doğrula
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
    print("🔍 BESTE ÖZER ADMIN YETKİLERİ KONTROLÜ")
    print("="*80)
    
    # Beste Özer
    beste = await db.users.find_one({"email": "beste@test.com"})
    if not beste:
        print("\n❌ Beste Özer bulunamadı!")
        return
    
    beste_id = beste.get('id')
    print(f"\n✅ Beste Özer: {beste_id}")
    print(f"   Name: {beste.get('full_name')}")
    print(f"   Email: {beste.get('email')}")
    
    # Ankara Veteran etkinliği
    event = await db.events.find_one({"title": {"$regex": "Ankara Veteran", "$options": "i"}})
    if not event:
        print("\n❌ Ankara Veteran etkinliği bulunamadı!")
        return
    
    event_id = event.get('id')
    organizer_id = event.get('organizer_id')
    
    print(f"\n📅 Ankara Veteran Etkinliği:")
    print(f"   ID: {event_id}")
    print(f"   Organizer ID: {organizer_id}")
    print(f"   Beste Özer organizer mi? {organizer_id == beste_id}")
    
    if organizer_id != beste_id:
        print(f"\n❌ BESTE ÖZER ORGANIZER DEĞİL!")
        print(f"   Gerçek organizer: {organizer_id}")
        
        # Organizer'ı kim?
        real_organizer = await db.users.find_one({"id": organizer_id})
        if real_organizer:
            print(f"   Gerçek organizer: {real_organizer.get('full_name')} ({real_organizer.get('email')})")
    
    # Grup sohbeti
    group = await db.group_chats.find_one({"event_id": event_id})
    if not group:
        print("\n❌ Grup sohbeti bulunamadı!")
        return
    
    print(f"\n💬 Grup Sohbeti:")
    print(f"   ID: {group.get('id')}")
    print(f"   Name: {group.get('name')}")
    print(f"   Created By: {group.get('created_by')}")
    print(f"   Admin IDs: {group.get('admin_ids', [])}")
    print(f"   Permission: {group.get('permission', 'everyone')}")
    print(f"   Members: {len(group.get('member_ids', []))}")
    
    is_admin = beste_id in group.get('admin_ids', [])
    print(f"\n✅ Beste Özer admin mi? {is_admin}")
    
    if not is_admin:
        print(f"\n❌ BESTE ÖZER ADMIN DEĞİL! Admin listesine ekleniyor...")
        await db.group_chats.update_one(
            {"id": group.get('id')},
            {"$addToSet": {"admin_ids": beste_id}}
        )
        print(f"✅ Eklendi!")
    
    print("\n" + "="*80)
    print("ÖNEMLİ NOTLAR:")
    print("- Frontend'te isOrganizer flag'i event.organizer_id kontrolü yapıyor")
    print("- Beste Özer admin listesinde OLSA BİLE, event organizer DEĞİLSE yetkileri sınırlı")
    print("- Toggle mute ve remove member endpoint'leri SADECE event organizer'a izin veriyor")
    print("="*80)
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
