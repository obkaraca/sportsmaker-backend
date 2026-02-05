"""
Review/Rating Endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from datetime import datetime
import uuid
import logging

from models import (
    Review,
    ReviewCreate,
    ReviewUpdate,
    ReviewType,
    NotificationType,
    NotificationRelatedType
)
from auth import get_current_user

logger = logging.getLogger(__name__)

review_router = APIRouter()

# Global db reference
db = None

def set_review_db(database):
    """Set database reference for review endpoints"""
    global db
    db = database
    logger.info(f"✅ Review DB set: {db is not None}")

async def create_notification(db_ref, user_id: str, title: str, message: str, related_id: str = None, related_type: str = None):
    """Helper function to create a notification"""
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "type": NotificationType.REVIEW_RECEIVED.value,
        "title": title,
        "message": message,
        "related_id": related_id,
        "related_type": related_type,
        "read": False,
        "created_at": datetime.utcnow()
    }
    await db.notifications.insert_one(notification)
    return notification

@review_router.post("/reviews", response_model=Review)
async def create_review(
    request: Request,
    review_data: ReviewCreate,
    current_user_id: str = Depends(get_current_user)
):
    """Create a new review"""
    db = request.app.state.db
    
    # Check if user already reviewed this target for this event/reservation
    existing = await db.reviews.find_one({
        "reviewer_user_id": current_user_id,
        "target_user_id": review_data.target_user_id,
        "related_id": review_data.related_id
    })
    
    if existing:
        raise HTTPException(status_code=400, detail="Bu kullanıcıyı zaten puanladınız")
    
    # Check if trying to review self
    if current_user_id == review_data.target_user_id:
        raise HTTPException(status_code=400, detail="Kendinizi puanlayamazsınız")
    
    # Create review
    review_id = str(uuid.uuid4())
    review = {
        "id": review_id,
        "reviewer_user_id": current_user_id,
        "target_user_id": review_data.target_user_id,
        "target_type": review_data.target_type.value,
        "related_id": review_data.related_id,
        "related_type": review_data.related_type,
        "rating": review_data.rating,
        "comment": review_data.comment,
        "skills_rating": review_data.skills_rating,
        "communication_rating": review_data.communication_rating,
        "punctuality_rating": review_data.punctuality_rating,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.reviews.insert_one(review)
    
    # Get reviewer info for notification
    reviewer = await db.users.find_one({"id": current_user_id})
    reviewer_name = reviewer.get("full_name", "Bir kullanıcı") if reviewer else "Bir kullanıcı"
    
    # Send notification to reviewed user
    target_type_labels = {
        "event": "etkinlik",
        "venue": "tesis",
        "coach": "antrenör",
        "referee": "hakem",
        "player": "oyuncu"
    }
    type_label = target_type_labels.get(review_data.target_type.value, "")
    
    await create_notification(
        db,
        review_data.target_user_id,
        "Yeni Değerlendirme Aldınız",
        f"{reviewer_name} sizi {type_label} olarak {review_data.rating} yıldızla değerlendirdi.",
        review_id,
        "review"
    )
    
    return Review(**review)

@review_router.get("/user-reviews/{user_id}")
async def get_reviews_for_user(
    request: Request,
    user_id: str,
    target_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 20
):
    """Get all reviews for a specific user"""
    # Use request.app.state.db
    db_ref = request.app.state.db if hasattr(request.app.state, 'db') else None
    if db_ref is None:
        db_ref = db  # fallback to global
    
    logger.info(f"🔍 Getting reviews for user: {user_id}")
    
    if db_ref is None:
        logger.error("Database not initialized!")
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    # Support both field names: target_user_id and reviewed_user_id
    query = {"$or": [{"target_user_id": user_id}, {"reviewed_user_id": user_id}]}
    if target_type:
        query["target_type"] = target_type
    
    logger.info(f"🔍 Query: {query}")
    
    reviews = await db_ref.reviews.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    logger.info(f"🔍 Found {len(reviews)} reviews")
    
    # Convert ObjectId to string and return raw data
    result = []
    for review in reviews:
        review["_id"] = str(review["_id"]) if "_id" in review else None
        result.append(review)
    
    return result

@review_router.get("/reviews/by-user/{user_id}", response_model=List[Review])
async def get_reviews_by_user(
    request: Request,
    user_id: str,
    skip: int = 0,
    limit: int = 20
):
    """Get all reviews written by a specific user"""
    db = request.app.state.db
    
    reviews = await db.reviews.find({"reviewer_user_id": user_id}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    return [Review(**review) for review in reviews]

@review_router.get("/reviews/my", response_model=List[Review])
async def get_my_reviews(
    request: Request,
    current_user_id: str = Depends(get_current_user)
):
    """Get current user's received reviews"""
    return await get_reviews_for_user(request, current_user_id)

@review_router.get("/reviews/stats/{user_id}")
async def get_user_review_stats(
    request: Request,
    user_id: str,
    target_type: Optional[str] = None
):
    """Get review statistics for a user"""
    db = request.app.state.db
    
    query = {"target_user_id": user_id}
    if target_type:
        query["target_type"] = target_type
    
    logger.info(f"📊 Getting review stats for user: {user_id}, query: {query}")
    
    # Aggregate pipeline to calculate averages
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": None,
            "total_reviews": {"$sum": 1},
            "average_rating": {"$avg": "$rating"},
            "average_skills": {"$avg": "$skills_rating"},
            "average_communication": {"$avg": "$communication_rating"},
            "average_punctuality": {"$avg": "$punctuality_rating"},
        }}
    ]
    
    result = await db.reviews.aggregate(pipeline).to_list(1)
    logger.info(f"📊 Aggregate result: {result}")
    
    if not result:
        return {
            "total_reviews": 0,
            "average_rating": 0,
            "average_skills": 0,
            "average_communication": 0,
            "average_punctuality": 0
        }
    
    stats = result[0]
    stats.pop("_id", None)
    
    # Round averages
    for key in ["average_rating", "average_skills", "average_communication", "average_punctuality"]:
        if stats.get(key):
            stats[key] = round(stats[key], 1)
    
    logger.info(f"📊 Returning stats: {stats}")
    return stats

@review_router.get("/reviews/can-review/{target_user_id}")
async def can_review_user(
    request: Request,
    target_user_id: str,
    related_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Check if current user can review target user"""
    db = request.app.state.db
    
    # Check if already reviewed
    existing = await db.reviews.find_one({
        "reviewer_user_id": current_user_id,
        "target_user_id": target_user_id,
        "related_id": related_id
    })
    
    return {"can_review": existing is None}

@review_router.get("/reviews/event/{event_id}/pending")
async def get_pending_reviews_for_event(
    request: Request,
    event_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Get list of participants that user can review for a completed event"""
    db = request.app.state.db
    
    # Get the event
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Check if event has ended
    from datetime import datetime
    end_date = event.get("end_date")
    if end_date:
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        if end_date > datetime.utcnow():
            return {"pending_reviews": [], "message": "Etkinlik henüz bitmedi"}
    
    # Get participants
    participants = event.get("participants", [])
    participant_ids = []
    for p in participants:
        if isinstance(p, str):
            participant_ids.append(p)
        elif isinstance(p, dict):
            participant_ids.append(p.get("id") or p.get("user_id"))
    
    # Remove current user from list
    participant_ids = [pid for pid in participant_ids if pid and pid != current_user_id]
    
    # Check which ones user has already reviewed
    existing_reviews = await db.reviews.find({
        "reviewer_user_id": current_user_id,
        "related_id": event_id,
        "target_user_id": {"$in": participant_ids}
    }).to_list(1000)
    
    reviewed_user_ids = {r["target_user_id"] for r in existing_reviews}
    
    # Get user details for pending reviews
    pending_reviews = []
    for pid in participant_ids:
        if pid not in reviewed_user_ids:
            user = await db.users.find_one({"id": pid})
            if user:
                pending_reviews.append({
                    "user_id": pid,
                    "full_name": user.get("full_name", "Kullanıcı"),
                    "profile_image": user.get("profile_image") or user.get("profile_photo"),
                    "user_type": user.get("user_type", "player"),
                    "city": user.get("city")
                })
    
    return {
        "event_id": event_id,
        "event_title": event.get("title"),
        "pending_reviews": pending_reviews,
        "total_participants": len(participant_ids),
        "reviewed_count": len(reviewed_user_ids)
    }

@review_router.post("/reviews/event/{event_id}/participant")
async def create_participant_review(
    request: Request,
    event_id: str,
    review_data: dict,
    current_user_id: str = Depends(get_current_user)
):
    """Create a review for a participant after event ends"""
    db = request.app.state.db
    
    target_user_id = review_data.get("target_user_id")
    rating = review_data.get("rating")
    comment = review_data.get("comment", "")
    
    if not target_user_id or not rating:
        raise HTTPException(status_code=400, detail="Hedef kullanıcı ve puan gerekli")
    
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Puan 1-5 arasında olmalı")
    
    # Check if event exists and has ended
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    from datetime import datetime
    end_date = event.get("end_date")
    if end_date:
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        if end_date > datetime.utcnow():
            raise HTTPException(status_code=400, detail="Etkinlik henüz bitmedi, değerlendirme yapamazsınız")
    
    # Check if both users participated in the event
    participants = event.get("participants", [])
    participant_ids = []
    for p in participants:
        if isinstance(p, str):
            participant_ids.append(p)
        elif isinstance(p, dict):
            participant_ids.append(p.get("id") or p.get("user_id"))
    
    if current_user_id not in participant_ids:
        raise HTTPException(status_code=403, detail="Bu etkinliğe katılmadınız")
    
    if target_user_id not in participant_ids:
        raise HTTPException(status_code=400, detail="Hedef kullanıcı bu etkinliğe katılmadı")
    
    # Check if already reviewed
    existing = await db.reviews.find_one({
        "reviewer_user_id": current_user_id,
        "target_user_id": target_user_id,
        "related_id": event_id
    })
    
    if existing:
        raise HTTPException(status_code=400, detail="Bu kullanıcıyı zaten değerlendirdiniz")
    
    # Cannot review self
    if current_user_id == target_user_id:
        raise HTTPException(status_code=400, detail="Kendinizi değerlendiremezsiniz")
    
    # Create the review
    review_id = str(uuid.uuid4())
    review = {
        "id": review_id,
        "reviewer_user_id": current_user_id,
        "target_user_id": target_user_id,
        "target_type": "player",  # For event participant reviews
        "related_id": event_id,
        "related_type": "event",
        "rating": rating,
        "comment": comment,
        "skills_rating": review_data.get("skills_rating"),
        "communication_rating": review_data.get("communication_rating"),
        "punctuality_rating": review_data.get("punctuality_rating"),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.reviews.insert_one(review)
    
    # Send notification
    reviewer = await db.users.find_one({"id": current_user_id})
    reviewer_name = reviewer.get("full_name", "Bir katılımcı") if reviewer else "Bir katılımcı"
    
    await create_notification(
        db,
        target_user_id,
        "Yeni Değerlendirme Aldınız",
        f"{reviewer_name} sizi '{event.get('title', 'Etkinlik')}' etkinliğinde {rating} yıldızla değerlendirdi.",
        review_id,
        "review"
    )
    
    return {"success": True, "review_id": review_id, "message": "Değerlendirmeniz kaydedildi"}

@review_router.delete("/reviews/{review_id}")
async def delete_review(
    request: Request,
    review_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Delete a review (only by reviewer or admin)"""
    db = request.app.state.db
    
    review = await db.reviews.find_one({"id": review_id, "reviewer_user_id": current_user_id})
    
    if not review:
        raise HTTPException(status_code=404, detail="Yorum bulunamadı veya silme yetkiniz yok")
    
    await db.reviews.delete_one({"id": review_id})
    
    return {"message": "Yorum silindi"}



# ============================================================================
# YORUM CEVAPLAMA ENDPOINTLERİ
# ============================================================================

from pydantic import BaseModel

class ReviewReplyCreate(BaseModel):
    reply_text: str


@review_router.post("/reviews/{review_id}/reply")
async def reply_to_review(
    request: Request,
    review_id: str,
    reply_data: ReviewReplyCreate,
    current_user: dict = Depends(get_current_user)
):
    """Yoruma bir kereliğine cevap yaz - sadece yorum hedefi cevap yazabilir"""
    db = request.app.state.db
    
    # current_user dict olabilir
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    # Yorumu bul
    review = await db.reviews.find_one({"id": review_id})
    if not review:
        raise HTTPException(status_code=404, detail="Yorum bulunamadı")
    
    # Sadece yorum hedefi (reviewed user) cevap yazabilir
    target_user_id = review.get("target_user_id") or review.get("reviewed_user_id")
    
    logger.info(f"🔍 Reply check - current_user_id: {current_user_id}, target_user_id: {target_user_id}")
    
    if target_user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Sadece yorumun hedefi cevap yazabilir")
    
    # Zaten cevap verilmiş mi kontrol et
    if review.get("reply"):
        raise HTTPException(status_code=400, detail="Bu yoruma zaten cevap verilmiş")
    
    # Cevap metnini kontrol et
    reply_text = reply_data.reply_text.strip()
    if not reply_text:
        raise HTTPException(status_code=400, detail="Cevap metni boş olamaz")
    
    if len(reply_text) > 500:
        raise HTTPException(status_code=400, detail="Cevap metni 500 karakteri geçemez")
    
    # Cevabı kaydet
    reply = {
        "text": reply_text,
        "created_at": datetime.utcnow().isoformat(),
        "user_id": current_user_id
    }
    
    await db.reviews.update_one(
        {"id": review_id},
        {
            "$set": {
                "reply": reply,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    # Yorumu yapan kullanıcıya bildirim gönder
    reviewer_id = review.get("reviewer_user_id")
    if reviewer_id:
        replier = await db.users.find_one({"id": current_user_id})
        replier_name = replier.get("full_name", "Kullanıcı") if replier else "Kullanıcı"
        
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": reviewer_id,
            "type": "review_reply",
            "title": "Yorumunuza Cevap Geldi",
            "message": f"{replier_name} yorumunuza cevap verdi.",
            "related_id": review_id,
            "related_type": "review",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
    
    logger.info(f"✅ Review reply added: {review_id} by user {current_user_id}")
    
    return {
        "success": True,
        "message": "Cevabınız kaydedildi",
        "reply": reply
    }


@review_router.delete("/reviews/{review_id}/reply")
async def delete_review_reply(
    request: Request,
    review_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Yorum cevabını sil - sadece cevabı yazan silebilir"""
    db = request.app.state.db
    
    # current_user dict olabilir
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    # Yorumu bul
    review = await db.reviews.find_one({"id": review_id})
    if not review:
        raise HTTPException(status_code=404, detail="Yorum bulunamadı")
    
    # Cevap var mı kontrol et
    reply = review.get("reply")
    if not reply:
        raise HTTPException(status_code=404, detail="Bu yorumda cevap bulunmuyor")
    
    # Sadece cevabı yazan silebilir
    if reply.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Sadece kendi cevabınızı silebilirsiniz")
    
    # Cevabı sil
    await db.reviews.update_one(
        {"id": review_id},
        {
            "$unset": {"reply": ""},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    
    logger.info(f"✅ Review reply deleted: {review_id} by user {current_user_id}")
    
    return {"success": True, "message": "Cevabınız silindi"}


@review_router.get("/reviews/{review_id}/can-reply")
async def can_reply_to_review(
    request: Request,
    review_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Kullanıcı bu yoruma cevap verebilir mi kontrol et"""
    db = request.app.state.db
    
    # current_user dict olabilir
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    # Yorumu bul
    review = await db.reviews.find_one({"id": review_id})
    if not review:
        return {"can_reply": False, "reason": "Yorum bulunamadı"}
    
    # Sadece yorum hedefi cevap yazabilir
    target_user_id = review.get("target_user_id") or review.get("reviewed_user_id")
    if target_user_id != current_user_id:
        return {"can_reply": False, "reason": "Sadece yorumun hedefi cevap yazabilir"}
    
    # Zaten cevap verilmiş mi
    if review.get("reply"):
        return {"can_reply": False, "reason": "Bu yoruma zaten cevap verilmiş", "has_reply": True}
    
    return {"can_reply": True}
