"""
Beste Özer'in grup durumunu detaylı kontrol et
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
    print("🔍 BESTE ÖZER GRUP YETKİ KONTROLÜ")
    print("="*80)
    
    # Beste Özer
    beste = await db.users.find_one({"email": "beste@test.com"})
    beste_id = beste.get('id')
    
    print(f"\n✅ Beste Özer ID: {beste_id}")
    
    # Ankara Veteran grup
    group = await db.group_chats.find_one({"name": {"$regex": "Ankara Veteran", "$options": "i"}})
    
    if not group:
        print("\n❌ Grup bulunamadı!")
        return
    
    print(f"\n📋 Grup Detayları:")
    print(f"   ID: {group.get('id')}")
    print(f"   Name: {group.get('name')}")
    print(f"   Created By: {group.get('created_by')}")
    print(f"   Admin IDs: {group.get('admin_ids', [])}")
    print(f"   Member IDs: {group.get('member_ids', [])}")
    print(f"   Permission: {group.get('permission', 'everyone')}")
    print(f"   Can Members Message: {group.get('can_members_message', True)}")
    
    # Kontroller
    is_admin = beste_id in group.get('admin_ids', [])
    is_member = beste_id in group.get('member_ids', [])
    is_creator = group.get('created_by') == beste_id
    permission = group.get('permission', 'everyone')
    
    print(f"\n🔍 Beste Özer Durumu:")
    print(f"   Admin mi? {is_admin}")
    print(f"   Üye mi? {is_member}")
    print(f"   Creator mi? {is_creator}")
    
    print(f"\n🔍 Grup İzinleri:")
    print(f"   Permission: {permission}")
    
    if permission == 'admins_only':
        print(f"   ❌ SORUN: Grup 'admins_only' modunda!")
        print(f"   Sadece adminler mesaj gönderebilir")
        
        if not is_admin:
            print(f"\n   ❌ BESTE ÖZER ADMIN DEĞİL!")
            print(f"   Admin listesine ekleniyor...")
            
            await db.group_chats.update_one(
                {"id": group.get('id')},
                {"$addToSet": {"admin_ids": beste_id}}
            )
            print(f"   ✅ Eklendi!")
        else:
            print(f"\n   ✅ Beste Özer zaten admin")
            print(f"   Sorun frontend'te olabilir")
    else:
        print(f"   ✅ Grup açık - herkes mesaj gönderebilir")
        
        if not is_admin:
            print(f"\n   ⚠️ Beste Özer admin değil ama grup açık olduğu için mesaj gönderebilmeli")
            print(f"   Admin listesine ekleyeceğiz...")
            
            await db.group_chats.update_one(
                {"id": group.get('id')},
                {"$addToSet": {"admin_ids": beste_id}}
            )
            print(f"   ✅ Admin olarak eklendi!")
    
    # Üye kontrolü
    if not is_member:
        print(f"\n   ❌ BESTE ÖZER ÜYE DEĞİL!")
        print(f"   Üye listesine ekleniyor...")
        
        await db.group_chats.update_one(
            {"id": group.get('id')},
            {"$addToSet": {"member_ids": beste_id}}
        )
        print(f"   ✅ Üye olarak eklendi!")
    
    # Final durum
    group_final = await db.group_chats.find_one({"id": group.get('id')})
    print(f"\n📋 Güncellenmiş Grup Durumu:")
    print(f"   Admin IDs: {group_final.get('admin_ids', [])}")
    print(f"   Member IDs: {group_final.get('member_ids', [])}")
    print(f"   Permission: {group_final.get('permission', 'everyone')}")
    
    print("\n" + "="*80)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
