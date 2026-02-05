"""
1. Badge count kontrolü
2. Grup sohbeti yönetim kontrolü
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
    print("🔍 BADGE VE GRUP YÖNETİMİ KONTROLÜ")
    print("="*80)
    
    # Özgür Barış Karaca
    user_ozgur = await db.users.find_one({"phone": "+905324900472"})
    if user_ozgur:
        user_id_ozgur = user_ozgur.get('id')
        print(f"\n✅ Özgür Barış Karaca: {user_id_ozgur}")
        
        # Calendar items kontrolü
        calendar_items = await db.calendar_items.find({"user_id": user_id_ozgur}).to_list(None)
        unread_count = sum(1 for item in calendar_items if not item.get('is_read', True))
        
        print(f"\n📅 Calendar Items:")
        print(f"   Toplam: {len(calendar_items)}")
        print(f"   Okunmamış: {unread_count}")
        
        for item in calendar_items:
            print(f"\n   - {item.get('title')}")
            print(f"     is_read: {item.get('is_read', False)}")
            print(f"     date: {item.get('date')}")
    
    # Beste Özer
    beste_users = await db.users.find({"full_name": {"$regex": "Beste", "$options": "i"}}).to_list(None)
    print(f"\n\n📋 Beste Özer kullanıcıları: {len(beste_users)}")
    
    user_beste = None
    for user in beste_users:
        print(f"   - {user.get('full_name')} | {user.get('email')} | ID: {user.get('id')[:20]}...")
        if user.get('email') == 'beste@test.com':
            user_beste = user
    
    if not user_beste:
        print("\n❌ Beste Özer bulunamadı!")
        return
    
    user_id_beste = user_beste.get('id')
    print(f"\n✅ Beste Özer seçildi: {user_id_beste}")
    
    # Ankara Veteran etkinliği
    event = await db.events.find_one({"title": {"$regex": "Ankara Veteran", "$options": "i"}})
    
    if event:
        event_id = event.get('id')
        organizer_id = event.get('organizer_id')
        
        print(f"\n📅 Ankara Veteran Etkinliği:")
        print(f"   ID: {event_id}")
        print(f"   Organizer ID: {organizer_id}")
        print(f"   Beste Özer mi? {organizer_id == user_id_beste}")
        
        # Group chat kontrolü
        group_chats = await db.group_chats.find({"event_id": event_id}).to_list(None)
        print(f"\n💬 Grup Sohbetleri: {len(group_chats)}")
        
        for group in group_chats:
            print(f"\n   Grup: {group.get('name')}")
            print(f"   ID: {group.get('id')}")
            print(f"   Created By: {group.get('created_by')}")
            print(f"   Admin IDs: {group.get('admin_ids', [])}")
            print(f"   Members: {len(group.get('members', []))}")
            print(f"   Can Members Message: {group.get('can_members_message', True)}")
            
            # Beste Özer admin mi?
            is_admin = user_id_beste in group.get('admin_ids', [])
            is_creator = group.get('created_by') == user_id_beste
            
            print(f"\n   Beste Özer:")
            print(f"   - Creator? {is_creator}")
            print(f"   - Admin? {is_admin}")
            
            if not is_admin and is_creator:
                print(f"\n   ❌ BESTE ÖZER ADMIN DEĞİL AMA CREATOR!")
                print(f"   ✅ Admin listesine eklenecek...")
                
                await db.group_chats.update_one(
                    {"id": group.get('id')},
                    {"$addToSet": {"admin_ids": user_id_beste}}
                )
                print(f"   ✅ Admin olarak eklendi!")
    
    print("\n" + "="*80)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
