"""
Message Endpoints Module
Handles: Direct Messages, Group Chats, Unread Counts
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime
import uuid
import logging

from models import Message, MessageBase, GroupChat, GroupChatCreate, GroupMessage, GroupMessageBase, GroupMessagePermission
from auth import get_current_user
from api_response import success_response, error_response, ErrorMessages

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Messages"])

# Database reference
db = None

def set_database(database):
    """Set database reference from main server"""
    global db
    db = database


# ==================== DIRECT MESSAGES ====================

@router.get("/messages")
async def get_messages(current_user: dict = Depends(get_current_user)):
    """Get all messages for current user (excluding hidden conversations)"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    messages = await db.messages.find({
        "$and": [
            {
                "$or": [
                    {"sender_id": current_user_id},
                    {"receiver_id": current_user_id}
                ]
            },
            {
                "$or": [
                    {"deleted_for": {"$exists": False}},
                    {"deleted_for": {"$nin": [current_user_id]}}
                ]
            }
        ]
    }).sort("sent_at", -1).to_list(1000)
    
    for msg in messages:
        if isinstance(msg.get('sender_id'), dict):
            msg['sender_id'] = msg['sender_id'].get('id')
        if isinstance(msg.get('receiver_id'), dict):
            msg['receiver_id'] = msg['receiver_id'].get('id')
        msg.pop('_id', None)
    
    return messages


@router.get("/messages/unread-counts")
async def get_unread_message_counts(current_user: dict = Depends(get_current_user)):
    """Get unread message counts for individual and group chats"""
    current_user_id = current_user.get("id")
    
    # Individual messages
    pipeline = [
        {"$match": {"receiver_id": current_user_id, "is_read": False}},
        {"$group": {"_id": "$sender_id", "count": {"$sum": 1}}}
    ]
    
    individual_unread = await db.messages.aggregate(pipeline).to_list(None)
    total_individual = sum(item["count"] for item in individual_unread)
    
    # Group messages
    user_groups = await db.group_chats.find({"member_ids": current_user_id}).to_list(None)
    group_ids = [group["id"] for group in user_groups]
    
    group_unread_count = await db.group_messages.count_documents({
        "group_id": {"$in": group_ids},
        "sender_id": {"$ne": current_user_id},
        "read_by": {"$ne": current_user_id}
    })
    
    return {
        "individual_unread": total_individual,
        "group_unread": group_unread_count,
        "total_unread": total_individual + group_unread_count
    }


@router.get("/messages/conversations-with-unread")
async def get_conversations_with_unread(current_user: dict = Depends(get_current_user)):
    """Get list of conversations with unread message counts"""
    current_user_id = current_user.get("id")
    
    try:
        pipeline = [
            {"$match": {"receiver_id": current_user_id, "is_read": False}},
            {"$group": {"_id": "$sender_id", "unread_count": {"$sum": 1}}}
        ]
        
        unread_by_sender = await db.messages.aggregate(pipeline).to_list(None)
        unread_dict = {item["_id"]: item["unread_count"] for item in unread_by_sender}
        
        return {"unread_by_user": unread_dict}
    except Exception as e:
        logger.error(f"Error in conversations-with-unread: {str(e)}")
        return {"unread_by_user": {}}


@router.get("/messages/{other_user_id}")
async def get_conversation(other_user_id: str, current_user: dict = Depends(get_current_user)):
    """Get conversation between two users"""
    current_user_id = current_user.get("id")
    
    messages = await db.messages.find({
        "$and": [
            {
                "$or": [
                    {"sender_id": current_user_id, "receiver_id": other_user_id},
                    {"sender_id": other_user_id, "receiver_id": current_user_id}
                ]
            },
            {
                "$or": [
                    {"deleted_for": {"$exists": False}},
                    {"deleted_for": {"$nin": [current_user_id]}}
                ]
            }
        ]
    }).sort("sent_at", 1).to_list(1000)
    
    for msg in messages:
        if isinstance(msg.get('sender_id'), dict):
            msg['sender_id'] = msg['sender_id'].get('id')
        if isinstance(msg.get('receiver_id'), dict):
            msg['receiver_id'] = msg['receiver_id'].get('id')
    
    return [Message(**msg) for msg in messages]


@router.put("/messages/{other_user_id}/mark-read")
async def mark_messages_as_read(other_user_id: str, current_user: dict = Depends(get_current_user)):
    """Mark all messages from a specific user as read"""
    current_user_id = current_user.get("id")
    
    result = await db.messages.update_many(
        {"sender_id": other_user_id, "receiver_id": current_user_id, "is_read": False},
        {"$set": {"is_read": True}}
    )
    
    return success_response(data={"marked_count": result.modified_count})


@router.delete("/messages/conversation/{other_user_id}")
async def hide_conversation(other_user_id: str, current_user: dict = Depends(get_current_user)):
    """Hide conversation for current user (soft delete)"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    result = await db.messages.update_many(
        {
            "$or": [
                {"sender_id": current_user_id, "receiver_id": other_user_id},
                {"sender_id": other_user_id, "receiver_id": current_user_id}
            ]
        },
        {"$addToSet": {"deleted_for": current_user_id}}
    )
    
    return success_response(data={"hidden_count": result.modified_count})


@router.post("/messages")
async def send_message(message: MessageBase, current_user: dict = Depends(get_current_user)):
    """Send a direct message"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    message_id = str(uuid.uuid4())
    
    message_data = {
        "id": message_id,
        "sender_id": current_user_id,
        "receiver_id": message.receiver_id,
        "content": message.content,
        "sent_at": datetime.utcnow(),
        "is_read": False
    }
    
    await db.messages.insert_one(message_data)
    
    return Message(**message_data)


# ==================== GROUP CHATS ====================

@router.post("/group-chats")
async def create_group_chat(group_data: GroupChatCreate, current_user_id: str = Depends(get_current_user)):
    """Create a new group chat"""
    if isinstance(current_user_id, dict):
        current_user_id = current_user_id.get("id")
    
    group_id = str(uuid.uuid4())
    
    group = {
        "id": group_id,
        "name": group_data.name,
        "description": group_data.description,
        "event_id": group_data.event_id,
        "creator_id": current_user_id,
        "admin_ids": [current_user_id],
        "member_ids": [current_user_id] + (group_data.member_ids or []),
        "permission": GroupMessagePermission.EVERYONE.value,
        "invite_link": None,
        "created_at": datetime.utcnow()
    }
    
    await db.group_chats.insert_one(group)
    return GroupChat(**group)


@router.get("/group-chats")
async def get_user_group_chats(current_user: dict = Depends(get_current_user)):
    """Get all group chats for current user"""
    current_user_id = current_user.get("id")
    
    groups = await db.group_chats.find({"member_ids": current_user_id}).to_list(100)
    
    for group in groups:
        member_ids = group.get('member_ids', [])
        if member_ids:
            group['member_ids'] = [m.get('id') if isinstance(m, dict) else m for m in member_ids]
        
        if 'creator_id' not in group and 'created_by' in group:
            group['creator_id'] = group['created_by']
        elif 'creator_id' not in group:
            group['creator_id'] = group.get('member_ids', [None])[0] if group.get('member_ids') else None
        
        if 'admin_ids' not in group:
            group['admin_ids'] = [group.get('creator_id')] if group.get('creator_id') else []
        
        if 'id' not in group:
            group['id'] = str(group['_id'])
    
    return [GroupChat(**{**group, "_id": str(group["_id"])}) for group in groups]


@router.get("/group-chats/unread-per-group")
async def get_unread_counts_per_group(current_user: dict = Depends(get_current_user)):
    """Get unread message counts for each group"""
    current_user_id = current_user.get("id")
    
    user_groups = await db.group_chats.find({"member_ids": current_user_id}).to_list(None)
    group_ids = [group["id"] for group in user_groups]
    
    unread_by_group = {}
    for group_id in group_ids:
        count = await db.group_messages.count_documents({
            "group_id": group_id,
            "sender_id": {"$ne": current_user_id},
            "read_by": {"$ne": current_user_id}
        })
        if count > 0:
            unread_by_group[group_id] = count
    
    return {"unread_by_group": unread_by_group}


@router.get("/group-chats/{group_id}")
async def get_group_chat(group_id: str, current_user: dict = Depends(get_current_user)):
    """Get group chat details"""
    current_user_id = current_user.get("id")
    
    group = await db.group_chats.find_one({"id": group_id})
    
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Fix member_ids and admin_ids
    member_ids = group.get('member_ids', [])
    if member_ids and isinstance(member_ids[0], dict):
        group['member_ids'] = [m.get('id') if isinstance(m, dict) else m for m in member_ids]
    
    admin_ids = group.get('admin_ids', [])
    if admin_ids and isinstance(admin_ids[0], dict):
        group['admin_ids'] = [a.get('id') if isinstance(a, dict) else a for a in admin_ids]
    
    if 'creator_id' not in group and 'created_by' in group:
        group['creator_id'] = group['created_by']
    elif 'creator_id' not in group:
        group['creator_id'] = group.get('member_ids', [None])[0] if group.get('member_ids') else None
    
    if 'admin_ids' not in group:
        group['admin_ids'] = [group.get('creator_id')] if group.get('creator_id') else []
    
    if 'id' not in group:
        group['id'] = str(group['_id'])
    
    if current_user_id not in group.get("member_ids", []):
        raise HTTPException(status_code=403, detail="Bu gruba erişim yetkiniz yok")
    
    group_dict = {k: v for k, v in group.items() if k != "_id"}
    return GroupChat(**group_dict)


@router.post("/group-chats/{group_id}/messages")
async def send_group_message(group_id: str, message_data: dict, current_user: dict = Depends(get_current_user)):
    """Send a message to a group"""
    current_user_id = current_user.get("id")
    
    group = await db.group_chats.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    if current_user_id not in group.get("member_ids", []):
        raise HTTPException(status_code=403, detail="Bu gruba mesaj gönderme yetkiniz yok")
    
    # Check permissions
    is_admin_or_creator = current_user_id in group.get("admin_ids", [])
    
    if not is_admin_or_creator:
        permission = group.get("permission", "all_members")
        if permission == "admins_only":
            raise HTTPException(status_code=403, detail="Sadece yöneticiler mesaj gönderebilir")
    
    sender = await db.users.find_one({"id": current_user_id})
    sender_name = sender.get("full_name") if sender else "Bilinmeyen"
    
    message_id = str(uuid.uuid4())
    message = {
        "id": message_id,
        "group_id": group_id,
        "sender_id": current_user_id,
        "sender_name": sender_name,
        "content": message_data.get("content"),
        "sent_at": datetime.utcnow(),
        "read_by": [current_user_id]
    }
    
    await db.group_messages.insert_one(message)
    return GroupMessage(**message)


@router.get("/group-chats/{group_id}/messages")
async def get_group_messages(group_id: str, current_user: dict = Depends(get_current_user)):
    """Get all messages in a group"""
    current_user_id = current_user.get("id")
    
    group = await db.group_chats.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    if current_user_id not in group.get("member_ids", []):
        raise HTTPException(status_code=403, detail="Bu gruba erişim yetkiniz yok")
    
    messages = await db.group_messages.find({"group_id": group_id}).sort("sent_at", 1).to_list(1000)
    
    for msg in messages:
        sender_id = msg.get("sender_id")
        if sender_id and not msg.get("sender_name"):
            user = await db.users.find_one({"id": sender_id})
            if user:
                msg["sender_name"] = user.get("full_name", "Bilinmeyen")
    
    return [GroupMessage(**msg) for msg in messages]


@router.put("/group-chats/{group_id}/mark-read")
async def mark_group_messages_as_read(group_id: str, current_user: dict = Depends(get_current_user)):
    """Mark all messages in a group as read for current user"""
    current_user_id = current_user.get("id")
    
    group = await db.group_chats.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    if current_user_id not in group.get("member_ids", []):
        raise HTTPException(status_code=403, detail="Bu grubun üyesi değilsiniz")
    
    result = await db.group_messages.update_many(
        {
            "group_id": group_id,
            "sender_id": {"$ne": current_user_id},
            "read_by": {"$ne": current_user_id}
        },
        {"$addToSet": {"read_by": current_user_id}}
    )
    
    return success_response(data={"marked_count": result.modified_count})
