"""
Comprehensive Orphaned Data Cleanup
Mevcut olmayan kullanıcılara ait TÜM verileri temizler
"""
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client.sportsmaker

async def get_all_user_ids():
    """Sistemdeki tüm mevcut kullanıcı ID'lerini al"""
    users = await db.users.find({}, {"id": 1}).to_list(None)
    user_ids = set([u["id"] for u in users])
    logger.info(f"✅ Found {len(user_ids)} active users in system")
    return user_ids

async def cleanup_orphaned_reservations(valid_user_ids):
    """Mevcut olmayan kullanıcılara ait rezervasyonları sil"""
    logger.info("\n🔍 Checking reservations...")
    
    reservations = await db.reservations.find({}).to_list(None)
    logger.info(f"   Total reservations: {len(reservations)}")
    
    deleted = 0
    for res in reservations:
        user_id = res.get("user_id")
        
        # user_id bazen dict olabiliyor
        if isinstance(user_id, dict):
            user_id = user_id.get("id")
        
        if user_id and user_id not in valid_user_ids:
            logger.warning(f"   ❌ Orphaned reservation: {res.get('id', 'no-id')[:15]}... (user: {user_id[:8]}...)")
            await db.reservations.delete_one({"_id": res["_id"]})
            deleted += 1
    
    logger.info(f"✅ Reservations cleanup: {deleted} deleted")
    return deleted

async def cleanup_orphaned_calendar_items(valid_user_ids):
    """Mevcut olmayan kullanıcılara veya rezervasyonlara ait ajanda maddelerini sil"""
    logger.info("\n🔍 Checking calendar items...")
    
    calendar_items = await db.calendar_items.find({}).to_list(None)
    logger.info(f"   Total calendar items: {len(calendar_items)}")
    
    # Mevcut rezervasyon ID'lerini al
    reservations = await db.reservations.find({}, {"id": 1}).to_list(None)
    valid_reservation_ids = set([r["id"] for r in reservations])
    
    deleted = 0
    for item in calendar_items:
        user_id = item.get("user_id")
        reservation_id = item.get("reservation_id")
        
        should_delete = False
        reason = ""
        
        # User kontrolü
        if user_id and user_id not in valid_user_ids:
            should_delete = True
            reason = f"user not found ({user_id[:8]}...)"
        
        # Reservation kontrolü
        if not should_delete and reservation_id and reservation_id not in valid_reservation_ids:
            should_delete = True
            reason = f"reservation not found ({reservation_id[:8]}...)"
        
        if should_delete:
            logger.warning(f"   ❌ Orphaned calendar item: {item.get('id', 'no-id')[:15]}... - {reason}")
            await db.calendar_items.delete_one({"_id": item["_id"]})
            deleted += 1
    
    logger.info(f"✅ Calendar items cleanup: {deleted} deleted")
    return deleted

async def cleanup_orphaned_notifications(valid_user_ids):
    """Mevcut olmayan kullanıcılara ait bildirimleri sil"""
    logger.info("\n🔍 Checking notifications...")
    
    notifications = await db.notifications.find({}).to_list(None)
    logger.info(f"   Total notifications: {len(notifications)}")
    
    deleted = 0
    for notif in notifications:
        user_id = notif.get("user_id")
        
        if user_id and user_id not in valid_user_ids:
            logger.warning(f"   ❌ Orphaned notification: {notif.get('id', 'no-id')[:15]}... (user: {user_id[:8]}...)")
            await db.notifications.delete_one({"_id": notif["_id"]})
            deleted += 1
    
    logger.info(f"✅ Notifications cleanup: {deleted} deleted")
    return deleted

async def cleanup_orphaned_participations(valid_user_ids):
    """Mevcut olmayan kullanıcılara ait etkinlik katılımlarını sil"""
    logger.info("\n🔍 Checking participations...")
    
    participations = await db.participations.find({}).to_list(None)
    logger.info(f"   Total participations: {len(participations)}")
    
    deleted = 0
    for part in participations:
        user_id = part.get("user_id")
        
        if user_id and user_id not in valid_user_ids:
            logger.warning(f"   ❌ Orphaned participation: {part.get('id', 'no-id')[:15]}... (user: {user_id[:8]}...)")
            await db.participations.delete_one({"_id": part["_id"]})
            deleted += 1
    
    logger.info(f"✅ Participations cleanup: {deleted} deleted")
    return deleted

async def cleanup_orphaned_messages(valid_user_ids):
    """Mevcut olmayan kullanıcılara ait mesajları sil"""
    logger.info("\n🔍 Checking messages...")
    
    messages = await db.messages.find({}).to_list(None)
    logger.info(f"   Total messages: {len(messages)}")
    
    deleted = 0
    for msg in messages:
        sender_id = msg.get("sender_id")
        receiver_id = msg.get("receiver_id")
        
        if (sender_id and sender_id not in valid_user_ids) or \
           (receiver_id and receiver_id not in valid_user_ids):
            logger.warning(f"   ❌ Orphaned message: {msg.get('id', 'no-id')[:15]}...")
            await db.messages.delete_one({"_id": msg["_id"]})
            deleted += 1
    
    logger.info(f"✅ Messages cleanup: {deleted} deleted")
    return deleted

async def find_reservations_with_phone(phone: str):
    """Belirli telefon numarasına ait rezervasyonları bul"""
    logger.info(f"\n🔍 Searching reservations with phone {phone}...")
    
    # Önce bu telefona sahip kullanıcıyı bul
    user = await db.users.find_one({"phone": phone})
    
    if user:
        logger.info(f"   ✅ User found: {user.get('full_name')} ({user.get('email')})")
        user_id = user.get('id')
        
        # Bu kullanıcının rezervasyonlarını bul
        reservations = await db.reservations.find({}).to_list(None)
        user_reservations = []
        
        for res in reservations:
            res_user_id = res.get("user_id")
            if isinstance(res_user_id, dict):
                res_user_id = res_user_id.get("id")
            
            if res_user_id == user_id:
                user_reservations.append(res)
        
        logger.info(f"   Found {len(user_reservations)} reservations for this user")
        return user_reservations
    else:
        logger.info(f"   ❌ No user found with phone {phone}")
        
        # Yine de tüm rezervasyonları kontrol et (eski veriler için)
        logger.info(f"   Checking all reservations for orphaned data...")
        reservations = await db.reservations.find({}).to_list(None)
        
        orphaned = []
        for res in reservations:
            res_user_id = res.get("user_id")
            if isinstance(res_user_id, dict):
                res_user_id = res_user_id.get("id")
            
            if res_user_id:
                user_exists = await db.users.find_one({"id": res_user_id})
                if not user_exists:
                    orphaned.append(res)
        
        logger.info(f"   Found {len(orphaned)} orphaned reservations (user not found)")
        return orphaned

async def main():
    logger.info("=" * 80)
    logger.info("🧹 COMPREHENSIVE ORPHANED DATA CLEANUP")
    logger.info("=" * 80)
    
    # 1. Telefon numarasını kontrol et
    phone = "+905552222222"
    reservations = await find_reservations_with_phone(phone)
    
    if len(reservations) > 0:
        logger.info(f"\n📋 Found {len(reservations)} reservations:")
        for i, res in enumerate(reservations[:5], 1):  # İlk 5'ini göster
            logger.info(f"{i}. ID: {res.get('id', 'N/A')[:20]}... | Date: {res.get('date', 'N/A')} | Status: {res.get('status', 'N/A')}")
    
    # 2. Tüm mevcut kullanıcı ID'lerini al
    logger.info("\n" + "=" * 80)
    valid_user_ids = await get_all_user_ids()
    
    # 3. Cleanup işlemleri
    total_deleted = 0
    
    res_deleted = await cleanup_orphaned_reservations(valid_user_ids)
    total_deleted += res_deleted
    
    cal_deleted = await cleanup_orphaned_calendar_items(valid_user_ids)
    total_deleted += cal_deleted
    
    notif_deleted = await cleanup_orphaned_notifications(valid_user_ids)
    total_deleted += notif_deleted
    
    part_deleted = await cleanup_orphaned_participations(valid_user_ids)
    total_deleted += part_deleted
    
    msg_deleted = await cleanup_orphaned_messages(valid_user_ids)
    total_deleted += msg_deleted
    
    # Özet
    logger.info("\n" + "=" * 80)
    logger.info("✅ CLEANUP COMPLETE")
    logger.info(f"   Reservations deleted: {res_deleted}")
    logger.info(f"   Calendar items deleted: {cal_deleted}")
    logger.info(f"   Notifications deleted: {notif_deleted}")
    logger.info(f"   Participations deleted: {part_deleted}")
    logger.info(f"   Messages deleted: {msg_deleted}")
    logger.info(f"   TOTAL DELETED: {total_deleted}")
    logger.info("=" * 80)
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
