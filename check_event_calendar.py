"""
Özgür Barış Karaca'nın etkinlik katılımını ve ajanda durumunu kontrol et
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

async def main():
    print("="*80)
    print("🔍 ÖZGÜR BARIŞ KARACA - ETKİNLİK VE AJANDA KONTROLÜ")
    print("="*80)
    
    user_id = "07ab0660-c851-47fd-b1e5-4d67ea5d4551"
    
    # Kullanıcıyı kontrol et
    user = await db.users.find_one({"id": user_id})
    if user:
        print(f"\n✅ Kullanıcı bulundu: {user.get('full_name')} ({user.get('phone')})")
    else:
        print(f"\n❌ Kullanıcı bulunamadı!")
        return
    
    # Ankara Veteran etkinliğini bul
    event = await db.events.find_one({"title": {"$regex": "Ankara Veteran", "$options": "i"}})
    
    if event:
        print(f"\n✅ Etkinlik bulundu:")
        print(f"   ID: {event.get('id')}")
        print(f"   Title: {event.get('title')}")
        print(f"   City: {event.get('city')}")
        print(f"   Start Date: {event.get('start_date')}")
        print(f"   End Date: {event.get('end_date')}")
        event_id = event.get('id')
    else:
        print(f"\n❌ 'Ankara Veteran' etkinliği bulunamadı!")
        
        # Ankara'daki tüm etkinlikleri listele
        ankara_events = await db.events.find({"city": "Ankara"}).to_list(None)
        print(f"\n📋 Ankara'daki etkinlikler ({len(ankara_events)} adet):")
        for i, evt in enumerate(ankara_events, 1):
            print(f"{i}. {evt.get('title')} | ID: {evt.get('id')[:20]}...")
        return
    
    # Participation kontrolü
    participation = await db.participations.find_one({
        "event_id": event_id,
        "user_id": user_id
    })
    
    if participation:
        print(f"\n✅ Katılım kaydı bulundu:")
        print(f"   ID: {participation.get('id')}")
        print(f"   Status: {participation.get('status')}")
        print(f"   Created: {participation.get('created_at')}")
    else:
        print(f"\n❌ Katılım kaydı BULUNAMADI!")
        print(f"   Kullanıcı etkinliğe katılmamış veya kayıt silinmiş")
    
    # Calendar item kontrolü
    calendar_item = await db.calendar_items.find_one({
        "user_id": user_id,
        "type": "event"
    })
    
    print(f"\n📅 Calendar Items:")
    calendar_items = await db.calendar_items.find({"user_id": user_id}).to_list(None)
    print(f"   Toplam: {len(calendar_items)}")
    
    event_calendar_item = None
    for item in calendar_items:
        print(f"\n   - ID: {item.get('id')[:20]}...")
        print(f"     Title: {item.get('title')}")
        print(f"     Type: {item.get('type')}")
        print(f"     Date: {item.get('date')}")
        
        if item.get('type') == 'event' and event_id in str(item):
            event_calendar_item = item
    
    if not event_calendar_item:
        print(f"\n❌ Bu etkinlik için ajanda maddesi BULUNAMADI!")
        print(f"   OLUŞTURULMALI!")
        
        # Calendar item oluştur
        if participation:
            import uuid
            calendar_id = str(uuid.uuid4())
            
            new_calendar_item = {
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
            
            await db.calendar_items.insert_one(new_calendar_item)
            print(f"\n✅ AJANDA MADDESİ OLUŞTURULDU:")
            print(f"   ID: {calendar_id}")
            print(f"   Title: {event.get('title')}")
            print(f"   Date: {event.get('start_date')}")
    else:
        print(f"\n✅ Ajanda maddesi mevcut")
    
    print("\n" + "="*80)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
