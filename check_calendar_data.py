"""
Check calendar items data
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client.sportsmaker

async def main():
    print("=" * 80)
    print("📅 CALENDAR ITEMS CHECK")
    print("=" * 80)
    
    # Tüm calendar items
    items = await db.calendar_items.find({}).to_list(None)
    print(f"\n✅ Total calendar items in DB: {len(items)}")
    
    if len(items) > 0:
        print("\n📋 Calendar Items Details:")
        for i, item in enumerate(items, 1):
            print(f"\n{i}. Calendar Item:")
            print(f"   ID: {item.get('id', 'N/A')}")
            print(f"   User ID: {item.get('user_id', 'N/A')}")
            print(f"   Title: {item.get('title', 'N/A')}")
            print(f"   Type: {item.get('type', 'N/A')}")
            print(f"   Date: {item.get('date', 'N/A')}")
            print(f"   is_read: {item.get('is_read', 'N/A')}")
            print(f"   Reservation ID: {item.get('reservation_id', 'N/A')}")
            
            # Check if user exists
            user_id = item.get('user_id')
            if user_id:
                user = await db.users.find_one({"id": user_id})
                if user:
                    print(f"   ✅ User exists: {user.get('full_name', 'N/A')} ({user.get('email', 'N/A')})")
                else:
                    print(f"   ❌ User NOT found - ORPHANED!")
            
            # Check if reservation exists
            res_id = item.get('reservation_id')
            if res_id:
                reservation = await db.reservations.find_one({"id": res_id})
                if reservation:
                    print(f"   ✅ Reservation exists: Status={reservation.get('status', 'N/A')}")
                else:
                    print(f"   ❌ Reservation NOT found - ORPHANED!")
    else:
        print("\n⚠️  No calendar items found in database")
    
    # Tüm reservations
    print("\n" + "=" * 80)
    reservations = await db.reservations.find({}).to_list(None)
    print(f"✅ Total reservations in DB: {len(reservations)}")
    
    if len(reservations) > 0:
        print("\n📋 Recent Reservations (last 5):")
        for i, res in enumerate(reservations[-5:], 1):
            print(f"\n{i}. Reservation:")
            print(f"   ID: {res.get('id', 'N/A')}")
            print(f"   Date: {res.get('date', 'N/A')}")
            print(f"   Status: {res.get('status', 'N/A')}")
            print(f"   User ID: {res.get('user_id', 'N/A')}")
            print(f"   Type: {res.get('type', 'N/A')}")
    
    # Tüm users
    print("\n" + "=" * 80)
    users = await db.users.find({}).to_list(None)
    print(f"✅ Total users in DB: {len(users)}")
    
    if len(users) > 0:
        print(f"\n📋 Users (showing first 5):")
        for i, user in enumerate(users[:5], 1):
            print(f"\n{i}. User:")
            print(f"   ID: {user.get('id', 'N/A')}")
            print(f"   Name: {user.get('full_name', 'N/A')}")
            print(f"   Email: {user.get('email', 'N/A')}")
            print(f"   Phone: {user.get('phone', 'N/A')}")
            print(f"   Type: {user.get('user_type', 'N/A')}")
    
    print("\n" + "=" * 80)
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
