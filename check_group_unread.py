"""
Özgür Barış Karaca'nın grup mesajlarını kontrol et
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
    print("🔍 GRUP MESAJ UNREAD KONTROLÜ")
    print("="*80)
    
    ozgur_id = "07ab0660-c851-47fd-b1e5-4d67ea5d4551"
    beste_id = "aafe3f2e-b3b4-47a1-a83a-0758bdb698b3"
    
    # Özgür'ün üye olduğu gruplar
    groups = await db.group_chats.find({"member_ids": ozgur_id}).to_list(None)
    print(f"\n✅ Özgür üye olduğu gruplar: {len(groups)}")
    
    for group in groups:
        print(f"\n📋 Grup: {group.get('name')}")
        print(f"   ID: {group.get('id')}")
        print(f"   Members: {group.get('member_ids')}")
        
        group_id = group.get('id')
        
        # Bu gruptaki tüm mesajlar
        messages = await db.group_messages.find({"group_id": group_id}).to_list(None)
        print(f"\n   💬 Toplam mesaj: {len(messages)}")
        
        for i, msg in enumerate(messages, 1):
            sender_id = msg.get('sender_id')
            read_by = msg.get('read_by', [])
            
            # Sender name
            sender = await db.users.find_one({"id": sender_id})
            sender_name = sender.get('full_name') if sender else 'Unknown'
            
            is_from_beste = sender_id == beste_id
            is_read_by_ozgur = ozgur_id in read_by
            
            print(f"\n   {i}. Mesaj:")
            print(f"      Gönderen: {sender_name} ({sender_id[:8]}...)")
            print(f"      Beste'den mi? {is_from_beste}")
            print(f"      read_by: {[uid[:8] + '...' for uid in read_by]}")
            print(f"      Özgür okudu mu? {is_read_by_ozgur}")
            print(f"      Content: {msg.get('content', '')[:50]}...")
        
        # Özgür için unread count hesapla
        unread = await db.group_messages.count_documents({
            "group_id": group_id,
            "sender_id": {"$ne": ozgur_id},  # Özgür göndermemiş
            "read_by": {"$ne": ozgur_id}  # Özgür okumamış
        })
        
        print(f"\n   📊 Özgür için okunmamış mesaj: {unread}")
    
    print("\n" + "="*80)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
