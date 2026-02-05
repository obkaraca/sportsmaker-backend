import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

async def check_event():
    mongo_url = os.getenv("MONGO_URL")
    print(f"Mongo URL: {mongo_url[:40]}...")
    client = AsyncIOMotorClient(mongo_url)
    db = client.spor_app
    
    # Tüm etkinlikleri listele
    events = await db.events.find({}).to_list(length=100)
    print(f"Toplam etkinlik sayısı: {len(events)}")
    
    for event in events:
        title = event.get('title', 'N/A')
        event_id = event.get('id', 'N/A')
        status = event.get('status', 'N/A')
        print(f"  - {title} (ID: {event_id[:8]}...) Status: {status}")
    
    client.close()

asyncio.run(check_event())
