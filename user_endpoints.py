"""
User Endpoints Module
Handles: User profile, stats, listings, batch operations
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from datetime import datetime, timezone
import logging

from models import User
from auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])

# Database reference
db = None

def set_database(database):
    """Set database reference from main server"""
    global db
    db = database


@router.get("/me")
async def get_user_me(current_user_id: str = Depends(get_current_user)):
    """Get current user info (alias for /auth/me)"""
    if isinstance(current_user_id, dict):
        user_id = current_user_id.get("id")
    else:
        user_id = current_user_id
    
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user_dict = {k: v for k, v in user.items() if k not in ["_id", "hashed_password", "password_hash"]}
    return user_dict


@router.get("/me/stats")
async def get_user_stats(current_user_id: str = Depends(get_current_user)):
    """Get user statistics"""
    if isinstance(current_user_id, dict):
        current_user_id = current_user_id.get("id")
    
    events_organized = await db.events.count_documents({"organizer_id": current_user_id})
    participations = await db.participations.count_documents({"user_id": current_user_id})
    tournaments = await db.tournament_management.count_documents({"organizer_id": current_user_id})
    reservations = await db.reservations.count_documents({"user_id": current_user_id})
    
    total_points = 0
    matches = await db.matches.find({
        "$or": [
            {"participant1_id": current_user_id},
            {"participant2_id": current_user_id}
        ],
        "status": "completed",
        "winner_id": {"$ne": None}
    }).to_list(1000)
    
    for match in matches:
        if match.get("winner_id") == current_user_id:
            total_points += 3
    
    return {
        "events_organized": events_organized,
        "events_joined": participations,
        "tournaments": tournaments,
        "reservations": reservations,
        "total_points": total_points,
        "matches_played": len(matches),
        "matches_won": sum(1 for m in matches if m.get("winner_id") == current_user_id)
    }


@router.put("/me")
async def update_profile(
    update_data: dict,
    current_user_id: str = Depends(get_current_user)
):
    """Update current user profile"""
    if isinstance(current_user_id, dict):
        user_id = current_user_id.get("id")
    else:
        user_id = current_user_id
    
    allowed_fields = [
        'full_name', 'phone', 'city', 'district', 'profile_image', 'avatar',
        'date_of_birth', 'tckn', 'vk_no', 'languages', 'bio',
        'instagram', 'twitter_x', 'youtube', 'linkedin', 'website',
        'match_fee', 'hourly_rate', 'daily_rate', 'monthly_membership',
        'financial_info', 'player_profile', 'coach_profile', 'referee_profile', 'venue_profile',
        'documents', 'club_organization', 'iban', 'availability', 'video_url', 'video_type', 'tc_kimlik_no'
    ]
    
    update_dict = {}
    for field in allowed_fields:
        if field in update_data:
            update_dict[field] = update_data[field]
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    
    existing_user = await db.users.find_one({"id": user_id})
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": update_dict}
    )
    
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found after update")
    
    user_data = {k: v for k, v in user.items() if k not in ["_id", "password_hash", "hashed_password"]}
    return user_data


@router.post("/push-token")
async def save_push_token(
    data: dict,
    current_user_id: str = Depends(get_current_user)
):
    """
    Save user's push notification token
    Used for sending push notifications to the user's device
    """
    if isinstance(current_user_id, dict):
        user_id = current_user_id.get("id")
    else:
        user_id = current_user_id
    
    push_token = data.get("push_token")
    device_type = data.get("device_type", "unknown")
    
    if not push_token:
        raise HTTPException(status_code=400, detail="Push token is required")
    
    # Kullanıcının push token'ını güncelle
    result = await db.users.update_one(
        {"id": user_id},
        {
            "$set": {
                "push_token": push_token,
                "device_type": device_type,
                "push_token_updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    logger.info(f"✅ Push token saved for user {user_id}: {push_token[:20]}...")
    
    return {
        "success": True,
        "message": "Push token saved successfully"
    }


@router.get("")
async def get_users(
    user_type: Optional[str] = None,
    city: Optional[str] = None,
    sport: Optional[str] = None,
    wants_to_earn: Optional[bool] = None,
    search: Optional[str] = None
):
    """Get users with optional filters"""
    try:
        query = {"is_verified": True}
        
        if user_type:
            query["user_type"] = user_type
        if city:
            query["city"] = city
        if sport:
            if user_type == "coach":
                query["coach_profile.sports"] = sport
            elif user_type == "referee":
                query["referee_profile.sport"] = sport
            elif user_type == "player":
                query["player_profile.sports"] = sport
        if wants_to_earn is not None:
            query["wants_to_earn"] = wants_to_earn
        
        if search:
            query["$or"] = [
                {"full_name": {"$regex": search, "$options": "i"}},
                {"first_name": {"$regex": search, "$options": "i"}},
                {"last_name": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}},
            ]
        
        if "user_type" not in query:
            query["user_type"] = {"$in": ["coach", "referee", "player"]}
        
        users = await db.users.find(query).to_list(1000)
        
        for user in users:
            user.pop("hashed_password", None)
            user.pop("password_hash", None)
            user.pop("_id", None)
        
        return users
    except Exception as e:
        logger.error(f"Get users error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}")
async def get_user_public(user_id: str):
    """Get single user public profile"""
    try:
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user.pop("hashed_password", None)
        user.pop("password_hash", None)
        user.pop("_id", None)
        
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
async def get_users_batch(request: dict):
    """Get multiple users by IDs"""
    try:
        user_ids = request.get("user_ids", [])
        if not user_ids:
            return {"users": []}
        
        users = []
        cursor = db.users.find({"id": {"$in": user_ids}})
        async for user in cursor:
            user.pop("hashed_password", None)
            user.pop("password_hash", None)
            user.pop("_id", None)
            users.append({
                "id": user.get("id"),
                "name": user.get("name", ""),
                "profile_photo": user.get("profile_photo"),
                "phone": user.get("phone"),
                "email": user.get("email"),
                "user_type": user.get("user_type"),
            })
        
        return {"users": users}
    except Exception as e:
        logger.error(f"Get users batch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{user_id}")
async def update_user_profile(
    user_id: str,
    profile_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update user profile - only owner can update"""
    try:
        current_user_id = current_user.get('id') if isinstance(current_user, dict) else current_user
        
        if user_id != current_user_id:
            raise HTTPException(status_code=403, detail="Can only update own profile")
        
        existing_user = await db.users.find_one({"id": user_id})
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        protected_fields = ["id", "email", "phone", "hashed_password", "password_hash", "_id", "created_at"]
        for field in protected_fields:
            profile_data.pop(field, None)
        
        profile_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        result = await db.users.update_one(
            {"id": user_id},
            {"$set": profile_data}
        )
        
        updated_user = await db.users.find_one({"id": user_id})
        if updated_user:
            updated_user.pop("hashed_password", None)
            updated_user.pop("password_hash", None)
            updated_user.pop("_id", None)
        
        logger.info(f"✅ User profile updated: {user_id}")
        return updated_user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user profile error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/stats")
async def get_user_statistics(user_id: str):
    """Get detailed statistics for a user"""
    try:
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        events_organized = await db.events.count_documents({"organizer_id": user_id})
        events_participated = await db.participations.count_documents({"user_id": user_id})
        
        matches = await db.matches.find({
            "$or": [
                {"participant1_id": user_id},
                {"participant2_id": user_id}
            ],
            "status": "completed"
        }).to_list(1000)
        
        wins = sum(1 for m in matches if m.get("winner_id") == user_id)
        losses = len(matches) - wins
        
        reviews = await db.reviews.find({"target_id": user_id}).to_list(100)
        avg_rating = sum(r.get("rating", 0) for r in reviews) / len(reviews) if reviews else 0
        
        return {
            "events_organized": events_organized,
            "events_participated": events_participated,
            "matches_played": len(matches),
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / len(matches) * 100) if matches else 0,
            "total_reviews": len(reviews),
            "average_rating": round(avg_rating, 1)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user statistics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/profile")
async def get_user_profile(user_id: str, current_user_id: str = Depends(get_current_user)):
    """Get user profile with additional details"""
    try:
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user.pop("hashed_password", None)
        user.pop("password_hash", None)
        user.pop("_id", None)
        
        reviews = await db.reviews.find({"target_id": user_id}).sort("created_at", -1).limit(10).to_list(10)
        stats = await get_user_statistics(user_id)
        
        return {
            **user,
            "recent_reviews": reviews,
            "statistics": stats
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user profile error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
