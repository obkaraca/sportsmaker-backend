"""
Script to add welcome reviews from SportsMaker to all users
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")

async def add_welcome_reviews():
    """Add SportsMaker welcome review to all users"""
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    print(f"📊 Connected to database: {DB_NAME}")
    
    # SportsMaker system user ID (will create if not exists)
    sportsmaker_id = "sportsmaker-system"
    
    # Check if SportsMaker user exists, if not create it
    sportsmaker_user = await db.users.find_one({"id": sportsmaker_id})
    if not sportsmaker_user:
        sportsmaker_user = {
            "id": sportsmaker_id,
            "email": "system@sportsmaker.com",
            "full_name": "SportsMaker",
            "user_type": "admin",
            "is_verified": True,
            "is_system": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        await db.users.insert_one(sportsmaker_user)
        print(f"✅ SportsMaker system user created")
    
    # Get all users except SportsMaker
    users = await db.users.find({"id": {"$ne": sportsmaker_id}}).to_list(None)
    print(f"📊 Found {len(users)} users to add welcome reviews")
    
    added_count = 0
    skipped_count = 0
    
    for user in users:
        user_id = user.get("id")
        if not user_id:
            continue
            
        # Check if user already has a welcome review from SportsMaker
        existing_review = await db.reviews.find_one({
            "reviewer_user_id": sportsmaker_id,
            "target_user_id": user_id,
            "related_id": "welcome"
        })
        
        if existing_review:
            skipped_count += 1
            continue
        
        # Create welcome review
        review = {
            "id": str(uuid.uuid4()),
            "reviewer_user_id": sportsmaker_id,
            "reviewer_name": "SportsMaker",
            "target_user_id": user_id,
            "target_type": "user",
            "related_id": "welcome",
            "related_type": "welcome",
            "rating": 5,
            "comment": "SportsMaker'a hoşgeldiniz. Puanınızı yüksek seviyede kalmasını dileriz.",
            "skills_rating": 5,
            "communication_rating": 5,
            "punctuality_rating": 5,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.reviews.insert_one(review)
        
        # Update user's rating
        user_reviews = await db.reviews.find({"target_user_id": user_id}).to_list(None)
        if user_reviews:
            total_rating = sum(r.get("rating", 0) for r in user_reviews)
            avg_rating = total_rating / len(user_reviews)
            
            await db.users.update_one(
                {"id": user_id},
                {"$set": {
                    "rating": round(avg_rating, 1),
                    "rating_count": len(user_reviews),
                    "review_count": len(user_reviews)
                }}
            )
        
        added_count += 1
        print(f"✅ Added welcome review for user: {user.get('full_name', user_id)}")
    
    print(f"\n📊 Summary:")
    print(f"   - Total users: {len(users)}")
    print(f"   - Reviews added: {added_count}")
    print(f"   - Skipped (already has): {skipped_count}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(add_welcome_reviews())
