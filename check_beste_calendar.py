"""
Beste Özer'in calendar item'larını kontrol et
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
    print("🔍 BESTE ÖZER CALENDAR ITEMS KONTROLÜ")
    print("="*80)
    
    beste_id = "aafe3f2e-b3b4-47a1-a83a-0758bdb698b3"
    
    # Calendar items
    items = await db.calendar_items.find({"user_id": beste_id}).to_list(None)
    
    print(f"\n✅ Toplam calendar items: {len(items)}")
    
    now = datetime.utcnow()
    print(f"\n🕐 Şu anki tarih: {now}")
    
    for i, item in enumerate(items, 1):
        print(f"\n📅 Item {i}:")
        print(f"   ID: {item.get('id')}")
        print(f"   Title: {item.get('title')}")
        print(f"   Type: {item.get('type')}")
        print(f"   Date: {item.get('date')}")
        print(f"   Start Time: {item.get('start_time')}")
        print(f"   End Time: {item.get('end_time')}")
        print(f"   is_read: {item.get('is_read', False)}")
        print(f"   Location: {item.get('location')}")
        
        # Tarih kontrolü
        item_date_str = item.get('date')
        if item_date_str:
            try:
                if isinstance(item_date_str, str):
                    # String ise parse et
                    item_date = datetime.fromisoformat(item_date_str.replace('Z', '+00:00'))
                else:
                    # Datetime ise direkt kullan
                    item_date = item_date_str
                
                is_past = item_date < now
                print(f"   📆 Tarih durumu: {'GEÇMIŞ' if is_past else 'GELECEK'}")
                print(f"   📆 Kalan/Geçen: {abs((item_date - now).days)} gün")
            except Exception as e:
                print(f"   ❌ Tarih parse hatası: {e}")
    
    print("\n" + "="*80)
    print("FRONTEND FİLTRELEME ANALİZİ:")
    print("- Eğer tüm item'lar GEÇMIŞ ve showPast=false ise görünmez")
    print("- Frontend'te showPast toggle'ı kontrol edin")
    print("="*80)
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
