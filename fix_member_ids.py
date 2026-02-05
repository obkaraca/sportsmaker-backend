"""
member_ids listesindeki dict'leri string ID'ye çevir
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
    print("🔧 MEMBER_IDS DİCT FIX")
    print("="*80)
    
    group = await db.group_chats.find_one({"id": "a4b7a9b4-c6c8-4549-8447-e21bdbaed799"})
    
    if not group:
        print("\n❌ Grup bulunamadı!")
        return
    
    print(f"\n📋 Mevcut member_ids:")
    member_ids = group.get('member_ids', [])
    print(f"   {member_ids}")
    
    # Her member'ı kontrol et ve dict ise extract et
    fixed_member_ids = []
    needs_fix = False
    
    for member in member_ids:
        if isinstance(member, dict):
            # Dict - extract ID
            member_id = member.get('id')
            if member_id:
                fixed_member_ids.append(member_id)
                needs_fix = True
                print(f"   ❌ Dict bulundu: {member} → {member_id}")
        elif isinstance(member, str):
            # String - doğru format
            fixed_member_ids.append(member)
            print(f"   ✅ String: {member}")
        else:
            print(f"   ⚠️ Bilinmeyen format: {member}")
    
    if needs_fix:
        print(f"\n🔧 member_ids düzeltiliyor...")
        print(f"   Öncesi: {member_ids}")
        print(f"   Sonrası: {fixed_member_ids}")
        
        await db.group_chats.update_one(
            {"id": group.get('id')},
            {"$set": {"member_ids": fixed_member_ids}}
        )
        print(f"✅ Düzeltildi!")
    else:
        print(f"\n✅ member_ids zaten doğru formatta")
    
    # Final durum
    group_final = await db.group_chats.find_one({"id": group.get('id')})
    print(f"\n📋 Güncellenmiş member_ids:")
    print(f"   {group_final.get('member_ids', [])}")
    
    print("\n" + "="*80)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
