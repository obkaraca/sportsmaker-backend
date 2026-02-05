"""
Kullanıcı durumunu kontrol et ve gerekirse geri yükle
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
import bcrypt
import uuid

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

async def main():
    print("="*80)
    print("🔍 KULLANICI KONTROLÜ")
    print("="*80)
    
    # +905324900472 ile kullanıcı ara (GERÇEK KULLANICI)
    user_real = await db.users.find_one({"phone": "+905324900472"})
    
    if user_real:
        print(f"\n✅ +905324900472 telefonu ile kullanıcı bulundu:")
        print(f"   ID: {user_real.get('id')}")
        print(f"   Name: {user_real.get('full_name')}")
        print(f"   Email: {user_real.get('email')}")
        print(f"   User Type: {user_real.get('user_type')}")
    else:
        print(f"\n❌ +905324900472 telefonu ile kullanıcı BULUNAMADI!")
        print(f"   GERİ OLUŞTURULMASI GEREKİYOR!")
        
        # Özgür Barış Karaca kullanıcısını geri oluştur
        user_id = str(uuid.uuid4())
        hashed_password = bcrypt.hashpw("123456".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        new_user = {
            "id": user_id,
            "full_name": "Özgür Barış Karaca",
            "email": "obkaraca@gmail.com",
            "phone": "+905324900472",
            "password": hashed_password,
            "hashed_password": hashed_password,
            "user_type": "admin",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z"
        }
        
        await db.users.insert_one(new_user)
        print(f"\n✅ KULLANICI GERİ OLUŞTURULDU:")
        print(f"   ID: {user_id}")
        print(f"   Name: Özgür Barış Karaca")
        print(f"   Phone: +905324900472")
        print(f"   Email: obkaraca@gmail.com")
        print(f"   Password: 123456")
        print(f"   User Type: admin")
    
    # +905552222222 kullanıcısı kontrol (SİLİNEN TEST KULLANICISI)
    user_test = await db.users.find_one({"phone": "+905552222222"})
    
    if user_test:
        print(f"\n⚠️ +905552222222 test kullanıcısı hala var:")
        print(f"   ID: {user_test.get('id')}")
        print(f"   Name: {user_test.get('full_name')}")
    else:
        print(f"\n✅ +905552222222 test kullanıcısı silindi (doğru)")
    
    # Tüm kullanıcıları listele
    all_users = await db.users.find({}).to_list(None)
    print(f"\n📊 Toplam kullanıcı sayısı: {len(all_users)}")
    print("\nKullanıcılar:")
    for i, user in enumerate(all_users, 1):
        print(f"{i}. {user.get('full_name')} | {user.get('phone')} | {user.get('email')}")
    
    print("\n" + "="*80)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
