"""
Beste'den test mesajı gönder - Özgür'ü read_by'a EKLEME
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
import uuid
from datetime import datetime

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

async def main():
    beste_id = "aafe3f2e-b3b4-47a1-a83a-0758bdb698b3"
    group_id = "a4b7a9b4-c6c8-4549-8447-e21bdbaed799"
    
    print("="*80)
    print("📨 TEST MESAJI GÖNDERME")
    print("="*80)
    
    message_id = str(uuid.uuid4())
    message = {
        "id": message_id,
        "group_id": group_id,
        "sender_id": beste_id,
        "sender_name": "Beste Özer",
        "content": "TEST: Bu mesaj badge testi için gönderildi",
        "sent_at": datetime.utcnow(),
        "read_by": [beste_id]  # Sadece Beste (gönderen)
    }
    
    await db.group_messages.insert_one(message)
    
    print(f"\n✅ Test mesajı oluşturuldu:")
    print(f"   ID: {message_id}")
    print(f"   Content: {message['content']}")
    print(f"   read_by: {message['read_by']}")
    print(f"\n🔔 Özgür'ün badge'inde artık 1 görünmeli!")
    print(f"   10 saniye bekleyin ve kontrol edin")
    
    print("\n" + "="*80)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
