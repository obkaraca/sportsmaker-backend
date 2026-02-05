"""
Orphaned Data Cleanup Script
Mevcut olmayan kullanıcılara ait bildirim ve ajanda maddelerini temizler
"""
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB connection
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client.sportsmaker

async def cleanup_orphaned_notifications():
    """Silinmiş kullanıcılara ait bildirimleri temizle"""
    logger.info("🔍 Checking orphaned notifications...")
    
    # Tüm bildirimleri al
    notifications = await db.notifications.find({}).to_list(None)
    logger.info(f"   Total notifications: {len(notifications)}")
    
    orphaned_count = 0
    deleted_count = 0
    
    for notification in notifications:
        user_id = notification.get("user_id")
        if not user_id:
            continue
            
        # Kullanıcının var olup olmadığını kontrol et
        user = await db.users.find_one({"id": user_id})
        
        if not user:
            # Kullanıcı yok - orphaned notification
            orphaned_count += 1
            logger.warning(f"   ❌ Orphaned notification: {notification.get('id')} (user: {user_id[:8]}...)")
            
            # Sil
            result = await db.notifications.delete_one({"_id": notification["_id"]})
            if result.deleted_count > 0:
                deleted_count += 1
    
    logger.info(f"✅ Notifications cleanup: {orphaned_count} orphaned, {deleted_count} deleted")
    return deleted_count

async def cleanup_orphaned_calendar_items():
    """Silinmiş kullanıcılara veya rezervasyonlara ait ajanda maddelerini temizle"""
    logger.info("🔍 Checking orphaned calendar items...")
    
    # Tüm ajanda maddelerini al
    calendar_items = await db.calendar_items.find({}).to_list(None)
    logger.info(f"   Total calendar items: {len(calendar_items)}")
    
    orphaned_count = 0
    deleted_count = 0
    
    for item in calendar_items:
        user_id = item.get("user_id")
        reservation_id = item.get("reservation_id")
        
        is_orphaned = False
        reason = ""
        
        # 1. Kullanıcı kontrolü
        if user_id:
            user = await db.users.find_one({"id": user_id})
            if not user:
                is_orphaned = True
                reason = f"user not found ({user_id[:8]}...)"
        
        # 2. Rezervasyon kontrolü
        if not is_orphaned and reservation_id:
            reservation = await db.reservations.find_one({"id": reservation_id})
            if not reservation:
                is_orphaned = True
                reason = f"reservation not found ({reservation_id[:8]}...)"
        
        if is_orphaned:
            orphaned_count += 1
            logger.warning(f"   ❌ Orphaned calendar item: {item.get('id', 'no-id')[:8]}... - {reason}")
            
            # Sil
            result = await db.calendar_items.delete_one({"_id": item["_id"]})
            if result.deleted_count > 0:
                deleted_count += 1
    
    logger.info(f"✅ Calendar items cleanup: {orphaned_count} orphaned, {deleted_count} deleted")
    return deleted_count

async def find_user_by_phone(phone: str):
    """Telefon numarasına göre kullanıcı bul"""
    user = await db.users.find_one({"phone": phone})
    if user:
        logger.info(f"📱 User found with phone {phone}:")
        logger.info(f"   ID: {user.get('id')}")
        logger.info(f"   Name: {user.get('full_name')}")
        logger.info(f"   Email: {user.get('email')}")
        return user
    else:
        logger.info(f"📱 No user found with phone {phone}")
        return None

async def main():
    logger.info("=" * 60)
    logger.info("🧹 ORPHANED DATA CLEANUP SCRIPT")
    logger.info("=" * 60)
    
    # Önce telefon numarasına sahip kullanıcıyı kontrol et
    logger.info("\n1️⃣ Checking user with phone +905552222222...")
    user = await find_user_by_phone("+905552222222")
    
    # Orphaned notifications temizle
    logger.info("\n2️⃣ Cleaning up orphaned notifications...")
    notif_deleted = await cleanup_orphaned_notifications()
    
    # Orphaned calendar items temizle
    logger.info("\n3️⃣ Cleaning up orphaned calendar items...")
    calendar_deleted = await cleanup_orphaned_calendar_items()
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ CLEANUP COMPLETE")
    logger.info(f"   Notifications deleted: {notif_deleted}")
    logger.info(f"   Calendar items deleted: {calendar_deleted}")
    logger.info("=" * 60)
    
    # Close connection
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
