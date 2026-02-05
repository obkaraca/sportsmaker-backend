"""
Notification Endpoints
Handles notification CRUD operations and push token registration
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List
from datetime import datetime
from bson import ObjectId
import logging

from models import (
    Notification, NotificationCreate, NotificationType,
    PushToken, PushTokenBase
)
from auth import get_current_user

notification_router = APIRouter()
logger = logging.getLogger(__name__)

async def create_notification_helper(db, notification_data: dict):
    """Helper function to create a notification"""
    notification_data["created_at"] = datetime.utcnow()
    result = await db.notifications.insert_one(notification_data)
    notification_data["id"] = str(result.inserted_id)
    notification_data.pop("_id", None)
    return notification_data

@notification_router.get("/notifications")
async def get_notifications(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    unread_only: bool = False,
    current_user: dict = Depends(get_current_user)
):
    """Get user's notifications with related entity details"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    query = {"user_id": current_user_id}
    if unread_only:
        query["read"] = False
    
    notifications = await db.notifications.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    # Log first 3 notification dates for debugging
    if notifications:
        logging.info(f"📬 First 3 notifications (newest first): {[(n.get('title'), n.get('created_at')) for n in notifications[:3]]}")
    
    # Enrich notifications with related entity details
    for notif in notifications:
        # _id'yi kaldır, eğer id yoksa _id'yi kullan
        mongo_id = notif.pop("_id", None)
        if "id" not in notif and mongo_id:
            notif["id"] = str(mongo_id)
        
        # Fetch related entity details
        related_details = None
        if notif.get("related_id") and notif.get("related_type"):
            related_type = notif["related_type"]
            related_id = notif["related_id"]
            
            try:
                # Case-insensitive comparison için upper() kullan
                related_type_upper = related_type.upper() if related_type else ""
                
                if related_type_upper == "EVENT":
                    event = await db.events.find_one({"id": related_id})
                    if event:
                        related_details = {
                            "name": event.get("title"),
                            "date": event.get("start_date"),
                            "sport": event.get("sport"),
                            "city": event.get("city")
                        }
                elif related_type_upper == "RESERVATION":
                    reservation = await db.reservations.find_one({"id": related_id})
                    if reservation:
                        related_details = {
                            "name": f"{reservation.get('type', '')} Rezervasyonu",
                            "date": reservation.get("date"),
                            "sport": reservation.get("sport"),
                            "city": reservation.get("city"),
                            "total_price": reservation.get("total_price")
                        }
                elif related_type_upper == "MESSAGE":
                    message = await db.messages.find_one({"id": related_id})
                    if message:
                        related_details = {
                            "name": "Yeni Mesaj",
                            "date": message.get("created_at")
                        }
                elif related_type_upper == "FACILITY":
                    facility = await db.facilities.find_one({"id": related_id})
                    if facility:
                        related_details = {
                            "name": facility.get("name"),
                            "city": facility.get("city"),
                            "status": facility.get("status", "pending")
                        }
            except Exception as e:
                print(f"Error fetching related details: {e}")
        
        notif["related_details"] = related_details
    
    # Get unread count
    unread_count = await db.notifications.count_documents({"user_id": current_user_id, "read": False})
    
    return {
        "notifications": notifications,
        "unread_count": unread_count,
        "total": len(notifications)
    }

@notification_router.get("/notifications/unread-count")
async def get_unread_count(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Get count of unread notifications"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    # Debug: Check all notifications
    all_notifs = await db.notifications.find({"user_id": current_user_id}).to_list(length=100)
    logger.info(f"🔍 User {current_user_id[:20]} - Total notifications in DB: {len(all_notifs)}")
    
    # CRITICAL: Support both 'read' and 'is_read' fields for backward compatibility
    count = await db.notifications.count_documents({
        "user_id": current_user_id,
        "$or": [
            {"read": False},
            {"is_read": False},
            {"read": {"$exists": False}, "is_read": {"$exists": False}}  # Legacy notifications without read field
        ]
    })
    logger.info(f"🔔 User {current_user_id[:20]} unread count: {count}")
    
    # Force return correct count
    return {"unread_count": count}

@notification_router.get("/notifications/{notification_id}")
async def get_notification_detail(
    notification_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Get single notification detail"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    try:
        # Try both _id (ObjectId) and id (string) fields
        notification = await db.notifications.find_one({
            "$or": [
                {"_id": ObjectId(notification_id) if len(notification_id) == 24 else notification_id},
                {"id": notification_id}
            ],
            "user_id": current_user_id
        })
    except Exception as e:
        logger.error(f"Error fetching notification {notification_id}: {str(e)}")
        # Try just by string id
        notification = await db.notifications.find_one({
            "id": notification_id,
            "user_id": current_user_id
        })
    
    if not notification:
        raise HTTPException(status_code=404, detail="Bildirim bulunamadı")
    
    # Convert ObjectId to string
    if "_id" in notification:
        notification["_id"] = str(notification["_id"])
    
    # Make sure we return both 'type' and 'notification_type' for compatibility
    if "notification_type" in notification and "type" not in notification:
        notification["type"] = notification["notification_type"]
    elif "type" in notification and "notification_type" not in notification:
        notification["notification_type"] = notification["type"]
    
    # Ensure is_read field exists (fallback to 'read' field)
    if "is_read" not in notification and "read" in notification:
        notification["is_read"] = notification["read"]
    
    return notification

@notification_router.put("/notifications/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Mark a notification as read"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    # Try both _id (ObjectId) and id (string) for compatibility
    try:
        # Try ObjectId first (old notifications)
        try:
            obj_id = ObjectId(notification_id)
            notification = await db.notifications.find_one({"_id": obj_id, "user_id": current_user_id})
        except:
            notification = None
        
        # If not found, try string id (new notifications)
        if not notification:
            notification = await db.notifications.find_one({"id": notification_id, "user_id": current_user_id})
        
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        # Update using the same field we found it with
        if "_id" in notification:
            # Update both 'read' and 'is_read' for consistency
            await db.notifications.update_one(
                {"_id": notification["_id"]},
                {"$set": {"read": True, "is_read": True}}
            )
        else:
            await db.notifications.update_one(
                {"id": notification_id},
                {"$set": {"read": True, "is_read": True}}
            )
        
        logger.info(f"✅ Notification {notification_id} marked as read by user {current_user_id}")
        return {"message": "Notification marked as read"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error marking notification as read: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating notification")

@notification_router.put("/notifications/read-all")
async def mark_all_notifications_as_read(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Mark all notifications as read"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    # Update both 'read' and 'is_read' for all unread notifications
    result = await db.notifications.update_many(
        {
            "user_id": current_user_id,
            "$or": [
                {"read": False},
                {"is_read": False}
            ]
        },
        {"$set": {"read": True, "is_read": True}}
    )
    
    logger.info(f"✅ Marked {result.modified_count} notifications as read for user {current_user_id}")
    return {"message": f"Marked {result.modified_count} notifications as read"}

@notification_router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Delete a notification"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    try:
        obj_id = ObjectId(notification_id)
    except:
        raise HTTPException(status_code=400, detail="Geçersiz bildirim ID")
    
    # Verify notification belongs to user
    notification = await db.notifications.find_one({"_id": obj_id})
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    if notification["user_id"] != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Delete
    await db.notifications.delete_one({"_id": obj_id})
    
    return {"message": "Notification deleted"}

@notification_router.post("/notifications/register-push-token")
async def register_push_token(
    token_data: PushTokenBase,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Register or update user's push notification token"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    # Check if token already exists for this user
    existing = await db.push_tokens.find_one({"user_id": current_user_id})
    
    if existing:
        # Update existing token
        await db.push_tokens.update_one(
            {"user_id": current_user_id},
            {
                "$set": {
                    "expo_push_token": token_data.expo_push_token,
                    "device_type": token_data.device_type,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return {"message": "Push token updated successfully"}
    else:
        # Create new token
        token_doc = {
            "user_id": current_user_id,
            "expo_push_token": token_data.expo_push_token,
            "device_type": token_data.device_type,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await db.push_tokens.insert_one(token_doc)
        return {"message": "Push token registered successfully", "id": str(result.inserted_id)}


# ==========================================
# ADMIN - Toplu Bildirim Yönetimi
# ==========================================

from pydantic import BaseModel
from typing import Optional
import uuid

class BulkNotificationFilters(BaseModel):
    sports: Optional[List[str]] = None
    user_types: Optional[List[str]] = None
    age_groups: Optional[List[str]] = None
    genders: Optional[List[str]] = None

class BulkNotificationRequest(BaseModel):
    notification_type: str  # 'push' veya 'text'
    title: str
    body: str
    filters: BulkNotificationFilters
    media_url: Optional[str] = None
    media_type: Optional[str] = None


@notification_router.post("/admin/notifications/send-bulk")
async def send_bulk_notification(
    request: Request,
    data: BulkNotificationRequest,
    current_user: dict = Depends(get_current_user)
):
    """Admin toplu bildirim gönderme"""
    db = request.app.state.db
    
    # Admin kontrolü
    if current_user.get("user_type") != "admin":
        raise HTTPException(status_code=403, detail="Bu işlem için admin yetkisi gerekiyor")
    
    try:
        # Kullanıcıları filtrele
        user_query = {"is_active": {"$ne": False}}
        
        filters = data.filters
        
        logger.info(f"📤 Bildirim gönderme isteği - Filtreler: {filters}")
        
        # Spor dalı filtresi (çoklu)
        if filters.sports and len(filters.sports) > 0:
            user_query["$or"] = [
                {"sports": {"$in": filters.sports}},
                {"preferred_sport": {"$in": filters.sports}},
                {"favorite_sports": {"$in": filters.sports}}
            ]
        
        # Kullanıcı türü filtresi (çoklu)
        if filters.user_types and len(filters.user_types) > 0:
            user_query["user_type"] = {"$in": filters.user_types}
        
        # Cinsiyet filtresi (çoklu)
        if filters.genders and len(filters.genders) > 0:
            user_query["gender"] = {"$in": filters.genders}
        
        # Yaş grubu filtresi - şimdilik basitleştirilmiş
        # TODO: Doğum tarihine göre daha detaylı filtreleme
        
        logger.info(f"📤 Kullanıcı sorgusu: {user_query}")
        
        # Hedef kullanıcıları getir
        target_users = await db.users.find(user_query, {"id": 1, "full_name": 1}).to_list(10000)
        
        logger.info(f"📤 Bulunan kullanıcı sayısı: {len(target_users)}")
        
        if not target_users:
            return {"message": "Filtrelere uyan kullanıcı bulunamadı", "sent_count": 0}
        
        # Her kullanıcıya bildirim oluştur
        notifications_to_insert = []
        for user in target_users:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": user.get("id"),
                "type": "admin_broadcast",
                "title": data.title,
                "body": data.body,
                "read": False,
                "created_at": datetime.utcnow(),
                "data": {
                    "notification_type": data.notification_type,
                    "media_url": data.media_url,
                    "media_type": data.media_type,
                }
            }
            notifications_to_insert.append(notification)
        
        # Toplu insert
        if notifications_to_insert:
            await db.notifications.insert_many(notifications_to_insert)
        
        # Push bildirim ise, push token'ları olan kullanıcılara gönder
        push_sent_count = 0
        if data.notification_type == "push":
            user_ids = [u.get("id") for u in target_users]
            push_tokens = await db.push_tokens.find({"user_id": {"$in": user_ids}}).to_list(10000)
            
            # TODO: Expo Push Notification API'ye gönder
            # Bu kısım gerçek push gönderimi için ayrı bir servisle yapılabilir
            push_sent_count = len(push_tokens)
            logger.info(f"📱 Push bildirim {push_sent_count} cihaza gönderilecek")
        
        # Gönderilmiş bildirimi kaydet
        sent_notification = {
            "id": str(uuid.uuid4()),
            "notification_type": data.notification_type,
            "title": data.title,
            "body": data.body,
            "filters": filters.dict(),
            "media_url": data.media_url,
            "media_type": data.media_type,
            "sent_count": len(target_users),
            "push_sent_count": push_sent_count,
            "sent_by": current_user.get("id"),
            "created_at": datetime.utcnow()
        }
        await db.admin_sent_notifications.insert_one(sent_notification)
        
        logger.info(f"✅ Toplu bildirim gönderildi: {len(target_users)} kullanıcı, {data.title}")
        
        return {
            "message": "Bildirim gönderildi",
            "sent_count": len(target_users),
            "push_sent_count": push_sent_count
        }
        
    except Exception as e:
        logger.error(f"❌ Toplu bildirim hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@notification_router.get("/admin/notifications/sent")
async def get_sent_notifications(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """Admin tarafından gönderilen bildirimleri listele"""
    db = request.app.state.db
    
    # Admin kontrolü
    if current_user.get("user_type") != "admin":
        raise HTTPException(status_code=403, detail="Bu işlem için admin yetkisi gerekiyor")
    
    try:
        notifications = await db.admin_sent_notifications.find().sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
        
        # ObjectId'yi string'e çevir
        for n in notifications:
            n.pop("_id", None)
        
        total = await db.admin_sent_notifications.count_documents({})
        
        return {
            "notifications": notifications,
            "total": total
        }
    except Exception as e:
        logger.error(f"❌ Gönderilmiş bildirimler listelenemedi: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

