"""
Son gönderilen grup mesajını kontrol et
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
    ozgur_id = "07ab0660-c851-47fd-b1e5-4d67ea5d4551"
    beste_id = "aafe3f2e-b3b4-47a1-a83a-0758bdb698b3"
    group_id = "a4b7a9b4-c6c8-4549-8447-e21bdbaed799"
    
    print("="*80)
    print("🔍 SON GRUP MESAJI KONTROLÜ")
    print("="*80)
    
    # Son mesajları al (en yeni önce)
    messages = await db.group_messages.find({"group_id": group_id}).sort("created_at", -1).limit(5).to_list(None)
    
    print(f"\n📨 Son {len(messages)} mesaj:\n")
    
    for i, msg in enumerate(messages, 1):
        sender_id = msg.get('sender_id')
        read_by = msg.get('read_by', [])
        created = msg.get('created_at', 'N/A')
        
        sender = await db.users.find_one({"id": sender_id})
        sender_name = sender.get('full_name') if sender else 'Unknown'
        
        is_from_beste = sender_id == beste_id
        is_read_by_ozgur = ozgur_id in read_by
        
        print(f"{i}. Mesaj ({created}):")
        print(f"   Gönderen: {sender_name}")
        print(f"   Beste'den mi? {'✅' if is_from_beste else '❌'}")
        print(f"   Content: {msg.get('content', '')}")
        print(f"   read_by sayısı: {len(read_by)}")
        print(f"   read_by: {read_by}")
        print(f"   Özgür okudu mu? {'✅ EVET' if is_read_by_ozgur else '❌ HAYIR'}")
        print()
    
    # Özgür için unread count hesapla
    print("="*80)
    print("📊 UNREAD COUNT HESAPLAMA")
    print("="*80)
    
    unread = await db.group_messages.count_documents({
        "group_id": group_id,
        "sender_id": {"$ne": ozgur_id},
        "read_by": {"$ne": ozgur_id}
    })
    
    print(f"\nÖzgür için okunmamış grup mesajı: {unread}")
    
    # Tüm gruplar için
    groups = await db.group_chats.find({"member_ids": ozgur_id}).to_list(None)
    group_ids = [g['id'] for g in groups]
    
    total_unread = await db.group_messages.count_documents({
        "group_id": {"$in": group_ids},
        "sender_id": {"$ne": ozgur_id},
        "read_by": {"$ne": ozgur_id}
    })
    
    print(f"Tüm gruplarda okunmamış: {total_unread}")
    
    print("\n" + "="*80)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
