"""
Clear all test data and start fresh
"""

import asyncio
import sys
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

# MongoDB connection
client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]

async def clear_all_test_data():
    """Clear all collections except admin users"""
    print("=" * 60)
    print("CLEARING ALL TEST DATA")
    print("=" * 60)
    print()
    
    try:
        # Keep admin users only
        admin_emails = ['obkaraca@gmail.com', 'admin@sportyconnect.com']
        
        # Delete all users except admins
        result = await db.users.delete_many({
            'email': {'$nin': admin_emails}
        })
        print(f"✓ Deleted {result.deleted_count} users (kept admins)")
        
        # Clear other collections
        collections_to_clear = [
            'venues',
            'events', 
            'tournament_management',
            'matches',
            'participations',
            'reservations',
            'support_tickets',
            'messages',
            'notifications'
        ]
        
        for collection in collections_to_clear:
            result = await db[collection].delete_many({})
            print(f"✓ Cleared {collection}: {result.deleted_count} documents")
        
        print()
        print("=" * 60)
        print("✓ ALL TEST DATA CLEARED!")
        print("=" * 60)
        print()
        print("Now run: python create_test_data.py")
        print()
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(clear_all_test_data())
