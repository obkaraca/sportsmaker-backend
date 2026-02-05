"""
Admin Endpoints Module
Handles: Super admin operations, user management, content moderation
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
import logging
import uuid
from datetime import datetime
from auth import get_current_user

# Router oluştur
admin_router = APIRouter(tags=["admin"])

# Global db referansı
db = None

def set_database(database):
    """Database referansını ayarla"""
    global db
    db = database

# Log helper function
async def log_admin_activity(
    admin_id: str,
    target_user_id: str,
    action_type: str,
    result: str,
    details: dict = None
):
    """Admin aktivitesini logla"""
    try:
        if db is None:
            return None
        
        # Admin bilgilerini al
        admin = await db.users.find_one({"id": admin_id})
        # Hedef kullanıcı bilgilerini al
        target_user = await db.users.find_one({"id": target_user_id})
        
        log_entry = {
            "id": str(uuid.uuid4()),
            "user_id": admin_id,
            "user_name": admin.get("full_name", "Admin") if admin else "Admin",
            "user_type": admin.get("user_type", "admin") if admin else "admin",
            "phone": admin.get("phone", "") if admin else "",
            "action_type": action_type,
            "result": result,
            "details": {
                **(details or {}),
                "target_user_id": target_user_id,
                "target_user_name": target_user.get("full_name", "Bilinmeyen") if target_user else "Bilinmeyen"
            },
            "ip_address": None,
            "created_at": datetime.utcnow()
        }
        
        await db.user_activity_logs.insert_one(log_entry)
        logging.info(f"📝 Admin activity logged: {action_type} - {result}")
        return log_entry
    except Exception as e:
        logging.error(f"Error logging admin activity: {e}")
        return None

# ================== HELPER FUNCTIONS ==================

async def verify_super_admin(current_user_id: str = Depends(get_current_user)):
    """Verify user is super admin"""
    global db
    user = await db.users.find_one({"id": current_user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    if user.get("user_type") != "super_admin":
        raise HTTPException(status_code=403, detail="Bu işlem için super admin yetkisi gereklidir")
    
    return current_user_id

async def verify_admin_or_super(current_user_id: str = Depends(get_current_user)):
    """Verify user is admin or super admin"""
    global db
    user = await db.users.find_one({"id": current_user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    if user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Bu işlem için admin yetkisi gereklidir")
    
    return current_user_id

# ================== USER SEARCH ==================

@admin_router.get("/users/search")
async def admin_search_users(
    query: str,
    admin_id: str = Depends(verify_super_admin)
):
    """Search users by name, email, or phone (super admin only)"""
    global db
    
    logging.info(f"🔍 Admin search request: query='{query}', admin_id={admin_id}")
    
    # Search by name, email, or phone
    if query.strip():
        users = await db.users.find({
            "$or": [
                {"full_name": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}},
                {"phone_number": {"$regex": query, "$options": "i"}}
            ]
        }).limit(50).to_list(50)
    else:
        # Empty query = return all users
        users = await db.users.find({}).limit(100).to_list(100)
    
    # Return only necessary fields (exclude super_admin users from results)
    result = []
    for user in users:
        # Skip super_admin users in search results
        if user.get("user_type") == "super_admin":
            continue
            
        result.append({
            "id": user.get("id"),
            "full_name": user.get("full_name"),
            "email": user.get("email"),
            "phone_number": user.get("phone_number"),
            "user_type": user.get("user_type"),
            "created_at": user.get("created_at")
        })
    
    logging.info(f"Admin {admin_id} searched users with query: {query}, found {len(result)} users")
    return result

# ================== USER MESSAGES ==================

@admin_router.get("/users/{user_id}/messages/personal")
async def admin_get_user_personal_messages(
    user_id: str,
    admin_id: str = Depends(verify_super_admin),
    limit: int = 100
):
    """Get all personal (1-1) messages for a user (super admin only)"""
    global db
    
    # Get all messages where user is sender or receiver
    messages = await db.messages.find({
        "$or": [
            {"sender_id": user_id},
            {"receiver_id": user_id}
        ]
    }).sort("sent_at", -1).limit(limit).to_list(limit)
    
    # Enrich with sender/receiver names
    for msg in messages:
        if msg.get("sender_id"):
            sender = await db.users.find_one({"id": msg["sender_id"]})
            msg["sender_name"] = sender.get("full_name") if sender else "Unknown"
        
        if msg.get("receiver_id"):
            receiver = await db.users.find_one({"id": msg["receiver_id"]})
            msg["receiver_name"] = receiver.get("full_name") if receiver else "Unknown"
        
        msg.pop("_id", None)
    
    logging.warning(f"🔍 Admin {admin_id} accessed personal messages of user {user_id}")
    return messages

@admin_router.get("/users/{user_id}/messages/groups")
async def admin_get_user_group_messages(
    user_id: str,
    admin_id: str = Depends(verify_super_admin),
    limit: int = 100
):
    """Get all group messages from groups where user is a member (super admin only)"""
    global db
    
    # Get all groups where user is a member
    groups = await db.group_chats.find({
        "members": user_id
    }).to_list(100)
    
    group_ids = [g.get("id") for g in groups]
    
    # Get all messages from these groups
    messages = await db.group_messages.find({
        "group_id": {"$in": group_ids}
    }).sort("sent_at", -1).limit(limit).to_list(limit)
    
    # Enrich with sender names and group names
    for msg in messages:
        if msg.get("sender_id"):
            sender = await db.users.find_one({"id": msg["sender_id"]})
            msg["sender_name"] = sender.get("full_name") if sender else "Unknown"
        
        if msg.get("group_id"):
            group = next((g for g in groups if g.get("id") == msg["group_id"]), None)
            msg["group_name"] = group.get("name") if group else "Unknown Group"
        
        msg.pop("_id", None)
    
    logging.warning(f"🔍 Admin {admin_id} accessed group messages of user {user_id}")
    return messages

# ================== GROUP MESSAGES ==================

@admin_router.get("/groups/{group_id}/messages")
async def admin_get_group_messages(
    group_id: str,
    admin_id: str = Depends(verify_super_admin),
    limit: int = 100
):
    """Get all messages from a specific group (super admin only)"""
    global db
    
    # Get group
    group = await db.group_chats.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Get messages
    messages = await db.group_messages.find({
        "group_id": group_id
    }).sort("sent_at", -1).limit(limit).to_list(limit)
    
    # Enrich with sender names
    for msg in messages:
        if msg.get("sender_id"):
            sender = await db.users.find_one({"id": msg["sender_id"]})
            msg["sender_name"] = sender.get("full_name") if sender else "Unknown"
        
        msg["group_name"] = group.get("name")
        msg.pop("_id", None)
    
    logging.warning(f"🔍 Admin {admin_id} accessed messages of group {group_id}")
    return messages

# ================== MESSAGE MODERATION ==================

@admin_router.post("/messages/{message_id}/flag")
async def admin_flag_message(
    message_id: str,
    reason: str = Query(..., description="Reason for flagging"),
    admin_id: str = Depends(verify_super_admin)
):
    """Flag a message for review (super admin only)"""
    global db
    
    # Try personal messages first
    message = await db.messages.find_one({"id": message_id})
    collection = "messages"
    
    if not message:
        # Try group messages
        message = await db.group_messages.find_one({"id": message_id})
        collection = "group_messages"
    
    if not message:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı")
    
    # Update message with flag
    update_data = {
        "flagged": True,
        "flag_reason": reason,
        "flagged_by": admin_id,
        "flagged_at": datetime.utcnow().isoformat()
    }
    
    if collection == "messages":
        await db.messages.update_one({"id": message_id}, {"$set": update_data})
    else:
        await db.group_messages.update_one({"id": message_id}, {"$set": update_data})
    
    logging.warning(f"🚩 Admin {admin_id} flagged message {message_id}: {reason}")
    return {"status": "success", "message": "Mesaj işaretlendi"}

@admin_router.delete("/messages/{message_id}")
async def admin_delete_message(
    message_id: str,
    admin_id: str = Depends(verify_super_admin)
):
    """Delete a message (super admin only)"""
    global db
    
    # Try personal messages first
    result = await db.messages.delete_one({"id": message_id})
    
    if result.deleted_count == 0:
        # Try group messages
        result = await db.group_messages.delete_one({"id": message_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı")
    
    logging.warning(f"🗑️ Admin {admin_id} deleted message {message_id}")
    return {"status": "success", "message": "Mesaj silindi"}

# ================== ADMIN STATS ==================

@admin_router.get("/stats")
async def admin_get_stats(admin_id: str = Depends(verify_admin_or_super)):
    """Get admin dashboard statistics (admin or super admin)"""
    global db
    
    # Count various entities
    total_users = await db.users.count_documents({})
    total_events = await db.events.count_documents({})
    total_venues = await db.venues.count_documents({})
    total_messages = await db.messages.count_documents({})
    total_groups = await db.group_chats.count_documents({})
    
    # Active users (logged in within last 30 days)
    from datetime import timedelta
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
    active_users = await db.users.count_documents({
        "last_login": {"$gte": thirty_days_ago}
    })
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_events": total_events,
        "total_venues": total_venues,
        "total_messages": total_messages,
        "total_groups": total_groups
    }

# ================== USER MANAGEMENT ==================

@admin_router.get("/users")
async def admin_get_users(
    admin_id: str = Depends(verify_admin_or_super),
    skip: int = 0,
    limit: int = 100,
    search: str = None,
    user_type: str = None
):
    """Get all users with pagination and filtering (admin or super admin)"""
    global db
    
    logger.info(f"📋 Admin users endpoint called by: {admin_id}")
    
    query = {}
    
    # Search filter
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}}
        ]
    
    # User type filter
    if user_type:
        query["user_type"] = user_type
    
    users = await db.users.find(query).skip(skip).limit(limit).to_list(limit)
    total = await db.users.count_documents(query)
    
    result = []
    for user in users:
        user.pop("_id", None)
        user.pop("password_hash", None)
        user.pop("hashed_password", None)
        result.append(user)
    
    return {"users": result, "total": total}

@admin_router.put("/users/{user_id}/status")
async def admin_update_user_status(
    user_id: str,
    status: str = Query(..., description="New status (active, suspended, banned)"),
    admin_id: str = Depends(verify_super_admin)
):
    """Update user status (super admin only)"""
    global db
    
    valid_statuses = ["active", "suspended", "banned"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Geçersiz durum. Geçerli değerler: {valid_statuses}")
    
    # Hedef kullanıcının mevcut durumunu al
    target_user = await db.users.find_one({"id": user_id})
    old_status = target_user.get("status", "active") if target_user else "unknown"
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"status": status, "updated_at": datetime.utcnow().isoformat()}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Aktiviteyi logla
    status_labels = {
        "active": "Aktif",
        "suspended": "Askıya Alındı",
        "banned": "Yasaklandı"
    }
    
    await log_admin_activity(
        admin_id=admin_id,
        target_user_id=user_id,
        action_type="user_status_change",
        result="success",
        details={
            "old_status": old_status,
            "new_status": status,
            "action": f"Kullanıcı durumu {status_labels.get(old_status, old_status)} → {status_labels.get(status, status)} olarak değiştirildi"
        }
    )
    
    logging.warning(f"👤 Admin {admin_id} updated user {user_id} status to {status}")
    return {"status": "success", "message": f"Kullanıcı durumu {status} olarak güncellendi"}
