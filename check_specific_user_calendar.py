"""
Check specific user calendar items
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client.sportsmaker

async def main():
    user_id = "dc4e3507-c113-41cc-894c-a35b7b909702"
    
    print("=" * 80)
    print(f"📅 CALENDAR ITEMS FOR USER: {user_id}")
    print("=" * 80)
    
    # User bilgisi
    user = await db.users.find_one({"id": user_id})
    if user:
        print(f"\n✅ User found:")
        print(f"   Name: {user.get('full_name')}")
        print(f"   Email: {user.get('email')}")
        print(f"   Phone: {user.get('phone')}")
    else:
        print(f"\n❌ User not found!")
        return
    
    # Calendar items
    items = await db.calendar_items.find({"user_id": user_id}).to_list(None)
    print(f"\n✅ Total calendar items: {len(items)}")
    
    if len(items) > 0:
        for i, item in enumerate(items, 1):
            print(f"\n📅 Item {i}:")
            print(f"   ID: {item.get('id')}")
            print(f"   Title: {item.get('title')}")
            print(f"   Type: {item.get('type')}")
            print(f"   Date: {item.get('date')}")
            print(f"   Hour: {item.get('hour')}")
            print(f"   is_read: {item.get('is_read', False)}")
            print(f"   Reservation ID: {item.get('reservation_id')}")
            print(f"   Reservation Status: {item.get('reservation_status')}")
            
            # Check reservation
            res_id = item.get('reservation_id')
            if res_id:
                reservation = await db.reservations.find_one({"id": res_id})
                if reservation:
                    print(f"   ✅ Reservation exists:")
                    print(f"      Status: {reservation.get('status')}")
                    print(f"      Date: {reservation.get('date')}")
                    print(f"      User ID: {reservation.get('user_id')}")
                    
                    # Check user_id type
                    res_user_id = reservation.get('user_id')
                    print(f"      User ID type: {type(res_user_id)}")
                    if isinstance(res_user_id, dict):
                        print(f"      ⚠️ User ID is DICT: {res_user_id}")
                    
                    # Check if requester user exists
                    if res_user_id:
                        if isinstance(res_user_id, dict):
                            res_user_id = res_user_id.get('id')
                        
                        req_user = await db.users.find_one({"id": res_user_id})
                        if req_user:
                            print(f"      ✅ Requester user exists: {req_user.get('full_name')} ({req_user.get('phone')})")
                        else:
                            print(f"      ❌ Requester user NOT found - ORPHANED!")
                else:
                    print(f"   ❌ Reservation NOT found - ORPHANED!")
    
    print("\n" + "=" * 80)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
