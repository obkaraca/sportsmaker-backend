"""
GERÇEK veritabanındaki orphaned data'yı temizle
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")  # CRITICAL!

print(f"🔗 Connecting to: {MONGO_URL}")
print(f"📊 Database: {DB_NAME}")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]  # Doğru DB!

async def main():
    print("\n" + "="*80)
    print("🔍 GERÇEK VERİTABANI ANALİZİ")
    print("="*80)
    
    # Users kontrol
    users = await db.users.find({}).to_list(None)
    print(f"\n✅ Total users: {len(users)}")
    
    # +905552222222 telefonu ile kullanıcı ara
    user_555 = await db.users.find_one({"phone": "+905552222222"})
    if user_555:
        print(f"\n❌ FOUND USER WITH +905552222222:")
        print(f"   ID: {user_555.get('id')}")
        print(f"   Name: {user_555.get('full_name')}")
        print(f"   Email: {user_555.get('email')}")
        user_id_555 = user_555.get('id')
    else:
        print(f"\n✅ No user with +905552222222")
        user_id_555 = None
    
    # Calendar items kontrol
    calendar_items = await db.calendar_items.find({}).to_list(None)
    print(f"\n📅 Total calendar items: {len(calendar_items)}")
    
    orphaned_calendar = []
    for item in calendar_items:
        user_id = item.get("user_id")
        user = await db.users.find_one({"id": user_id})
        
        if not user:
            orphaned_calendar.append(item)
            print(f"\n❌ ORPHANED calendar item:")
            print(f"   ID: {item.get('id')}")
            print(f"   User ID: {user_id}")
            print(f"   Title: {item.get('title')}")
            print(f"   Date: {item.get('date')}")
    
    # Reservations kontrol
    reservations = await db.reservations.find({}).to_list(None)
    print(f"\n🗓️ Total reservations: {len(reservations)}")
    
    orphaned_reservations = []
    if user_id_555:
        # +905552222222 kullanıcısının rezervasyonları
        res_555 = []
        for res in reservations:
            res_user_id = res.get("user_id")
            if isinstance(res_user_id, dict):
                res_user_id = res_user_id.get("id")
            
            if res_user_id == user_id_555:
                res_555.append(res)
        
        print(f"\n❌ Reservations for +905552222222: {len(res_555)}")
        for res in res_555[:3]:
            print(f"   - {res.get('date')} | Status: {res.get('status')} | ID: {res.get('id')[:20]}...")
    
    # Orphaned reservations
    for res in reservations:
        res_user_id = res.get("user_id")
        if isinstance(res_user_id, dict):
            res_user_id = res_user_id.get("id")
        
        if res_user_id:
            user = await db.users.find_one({"id": res_user_id})
            if not user:
                orphaned_reservations.append(res)
    
    print(f"\n❌ Orphaned reservations (user not found): {len(orphaned_reservations)}")
    
    # CLEANUP YAP!
    print("\n" + "="*80)
    print("🧹 CLEANUP BAŞLATILIYOR...")
    print("="*80)
    
    deleted_count = 0
    
    # Orphaned calendar items sil
    for item in orphaned_calendar:
        await db.calendar_items.delete_one({"_id": item["_id"]})
        deleted_count += 1
        print(f"✅ Deleted calendar item: {item.get('id', 'no-id')[:20]}...")
    
    # Orphaned reservations sil
    for res in orphaned_reservations:
        await db.reservations.delete_one({"_id": res["_id"]})
        deleted_count += 1
        print(f"✅ Deleted reservation: {res.get('id', 'no-id')[:20]}...")
    
    # +905552222222 kullanıcısı ve verilerini sil
    if user_id_555:
        print(f"\n🗑️ Deleting user +905552222222 and all related data...")
        
        # Calendar items
        result = await db.calendar_items.delete_many({"user_id": user_id_555})
        print(f"   ✅ Deleted {result.deleted_count} calendar items")
        deleted_count += result.deleted_count
        
        # Reservations
        result = await db.reservations.delete_many({"user_id": user_id_555})
        print(f"   ✅ Deleted {result.deleted_count} reservations (exact match)")
        deleted_count += result.deleted_count
        
        # Reservations with dict user_id
        reservations_all = await db.reservations.find({}).to_list(None)
        for res in reservations_all:
            res_user_id = res.get("user_id")
            if isinstance(res_user_id, dict) and res_user_id.get("id") == user_id_555:
                await db.reservations.delete_one({"_id": res["_id"]})
                deleted_count += 1
                print(f"   ✅ Deleted reservation (dict format)")
        
        # Notifications
        result = await db.notifications.delete_many({"user_id": user_id_555})
        print(f"   ✅ Deleted {result.deleted_count} notifications")
        deleted_count += result.deleted_count
        
        # Participations
        result = await db.participations.delete_many({"user_id": user_id_555})
        print(f"   ✅ Deleted {result.deleted_count} participations")
        deleted_count += result.deleted_count
        
        # Messages
        result1 = await db.messages.delete_many({"sender_id": user_id_555})
        result2 = await db.messages.delete_many({"receiver_id": user_id_555})
        print(f"   ✅ Deleted {result1.deleted_count + result2.deleted_count} messages")
        deleted_count += result1.deleted_count + result2.deleted_count
        
        # User'ı sil
        await db.users.delete_one({"id": user_id_555})
        print(f"   ✅ Deleted user")
        deleted_count += 1
    
    print("\n" + "="*80)
    print(f"✅ CLEANUP TAMAMLANDI: {deleted_count} kayıt silindi")
    print("="*80)
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
