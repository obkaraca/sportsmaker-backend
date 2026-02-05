"""
Support Ticket Endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List
from datetime import datetime
import uuid

from models import (
    SupportTicket,
    SupportTicketCreate,
    SupportTicketUpdate,
    SupportTicketStatus,
    SupportTicketCategory,
    NotificationType,
    NotificationRelatedType
)
from auth import get_current_user

support_router = APIRouter()

async def create_notification(db, user_id: str, title: str, message: str, related_id: str = None, related_type: str = None):
    """Helper function to create a notification"""
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "type": NotificationType.SUPPORT_TICKET.value,
        "title": title,
        "message": message,
        "related_id": related_id,
        "related_type": related_type,
        "read": False,
        "created_at": datetime.utcnow()
    }
    await db.notifications.insert_one(notification)
    return notification

@support_router.post("/support/tickets", response_model=SupportTicket)
async def create_support_ticket(
    request: Request,
    ticket_data: SupportTicketCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new support ticket"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    # Create ticket
    ticket_id = str(uuid.uuid4())
    ticket = {
        "id": ticket_id,
        "user_id": current_user_id,
        "category": ticket_data.category.value,
        "subject": ticket_data.subject,
        "description": ticket_data.description,
        "related_type": ticket_data.related_type,
        "related_id": ticket_data.related_id,
        "status": SupportTicketStatus.OPEN.value,
        "admin_response": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.support_tickets.insert_one(ticket)
    
    # Create notification for user
    category_labels = {
        "info_request": "Bilgi Talebi",
        "reservation_cancellation": "Rezervasyon İptali",
        "ticket_cancellation": "Bilet İptali",
        "event_cancellation": "Etkinlik İptali",
        "complaint": "Şikayet",
        "other": "Diğer"
    }
    
    category_label = category_labels.get(ticket_data.category.value, ticket_data.category.value)
    
    await create_notification(
        db,
        current_user_id,
        "Destek Talebiniz Alındı",
        f"{category_label} talebiniz başarıyla oluşturuldu. En kısa sürede yanıt vereceğiz.",
        ticket_id,
        NotificationRelatedType.SUPPORT_TICKET.value
    )
    
    # Get user info for admin notification
    user = await db.users.find_one({"id": current_user_id})
    user_name = user.get("full_name", "Kullanıcı") if user else "Kullanıcı"
    
    # Send notification to all admin users
    admin_users = await db.users.find({"user_type": "admin"}).to_list(100)
    for admin in admin_users:
        await create_notification(
            db,
            admin["id"],
            "Yeni Destek Talebi",
            f"{user_name} tarafından {category_label} kategorisinde yeni destek talebi: {ticket_data.subject}",
            ticket_id,
            NotificationRelatedType.SUPPORT_TICKET.value
        )
    
    # Yardım talebi log'u
    try:
        from auth_endpoints import log_user_activity
        await log_user_activity(current_user_id, "support_ticket_create", "success", {
            "ticket_id": ticket_id,
            "category": ticket_data.category.value,
            "subject": ticket_data.subject,
            "related_type": ticket_data.related_type,
            "related_id": ticket_data.related_id
        })
    except Exception as log_err:
        print(f"Log error: {log_err}")
    
    return SupportTicket(**ticket)

# Admin için tüm destek taleplerini listeleme
@support_router.get("/support/tickets", response_model=List[SupportTicket])
async def get_all_tickets(
    request: Request,
    status: str = None,
    current_user: dict = Depends(get_current_user)
):
    """Get all support tickets (admin only)"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    # Admin kontrolü
    user = await db.users.find_one({"id": current_user_id})
    if not user or user.get("user_type") != "admin":
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    query = {}
    if status:
        query["status"] = status
    
    tickets = await db.support_tickets.find(query).sort("created_at", -1).to_list(500)
    
    # Her ticket için kullanıcı bilgilerini ekle
    result = []
    for ticket in tickets:
        user_info = await db.users.find_one({"id": ticket.get("user_id")})
        ticket["user_name"] = user_info.get("full_name", "Bilinmeyen") if user_info else "Bilinmeyen"
        result.append(SupportTicket(**ticket))
    
    return result

@support_router.get("/support/tickets/my", response_model=List[SupportTicket])
async def get_my_tickets(
    request: Request,
    status: str = None,
    current_user: dict = Depends(get_current_user)
):
    """Get current user's support tickets"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    query = {"user_id": current_user_id}
    if status:
        query["status"] = status
    
    tickets = await db.support_tickets.find(query).sort("created_at", -1).to_list(100)
    
    return [SupportTicket(**ticket) for ticket in tickets]

@support_router.get("/support/tickets/{ticket_id}", response_model=SupportTicket)
async def get_ticket(
    request: Request,
    ticket_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific support ticket"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    # Check if user is admin
    user = await db.users.find_one({"id": current_user_id})
    is_admin = user and user.get("user_type") == "admin"
    
    # Admin can see all tickets, users can only see their own
    if is_admin:
        ticket = await db.support_tickets.find_one({"id": ticket_id})
    else:
        ticket = await db.support_tickets.find_one({"id": ticket_id, "user_id": current_user_id})
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Destek talebi bulunamadı")
    
    # Add user info for admin view
    if is_admin and ticket.get("user_id"):
        ticket_user = await db.users.find_one({"id": ticket["user_id"]})
        if ticket_user:
            ticket["user_name"] = ticket_user.get("full_name", "")
    
    return SupportTicket(**ticket)

@support_router.patch("/support/tickets/{ticket_id}", response_model=SupportTicket)
@support_router.put("/support/tickets/{ticket_id}", response_model=SupportTicket)
async def update_ticket(
    request: Request,
    ticket_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Update a support ticket (admin only for now)"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    # Check if user is admin
    user = await db.users.find_one({"id": current_user_id})
    is_admin = user and user.get("user_type") == "admin"
    
    # Only admin can update tickets
    if not is_admin:
        raise HTTPException(status_code=403, detail="Sadece yöneticiler destek taleplerini güncelleyebilir")
    
    ticket = await db.support_tickets.find_one({"id": ticket_id})
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Destek talebi bulunamadı")
    
    # Get body data
    body = await request.json()
    print(f"Received update data: {body}")
    
    # Build update dict
    update_dict = {"updated_at": datetime.utcnow()}
    
    if body.get("status"):
        update_dict["status"] = body["status"]
    
    if body.get("admin_response"):
        update_dict["admin_response"] = body["admin_response"]
        
        # Notify user about admin response
        notif_id = str(uuid.uuid4())
        notif_data = {
            "id": notif_id,
            "user_id": ticket["user_id"],
            "type": "support_ticket",
            "title": "Destek Talebinize Yanıt Verildi",
            "message": f"'{ticket['subject']}' konulu destek talebinize yanıt verildi.",
            "related_id": ticket_id,
            "related_type": "support_ticket",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notif_data)
    
    await db.support_tickets.update_one(
        {"id": ticket_id},
        {"$set": update_dict}
    )
    
    updated_ticket = await db.support_tickets.find_one({"id": ticket_id})
    
    # Ensure messages field exists
    if "messages" not in updated_ticket:
        updated_ticket["messages"] = []
    
    return SupportTicket(**updated_ticket)


# Destek talebine mesaj ekle
@support_router.post("/support/tickets/{ticket_id}/messages", response_model=SupportTicket)
async def add_ticket_message(
    request: Request,
    ticket_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Add a message to support ticket (bidirectional chat)"""
    db = request.app.state.db
    current_user_id = current_user["id"]
    
    # Get body
    body = await request.json()
    message_text = body.get("message", "").strip()
    
    if not message_text:
        raise HTTPException(status_code=400, detail="Mesaj boş olamaz")
    
    # Get ticket
    ticket = await db.support_tickets.find_one({"id": ticket_id})
    if not ticket:
        raise HTTPException(status_code=404, detail="Destek talebi bulunamadı")
    
    # Check if user is admin or ticket owner
    user = await db.users.find_one({"id": current_user_id})
    is_admin = user and user.get("user_type") == "admin"
    is_owner = ticket["user_id"] == current_user_id
    
    if not (is_admin or is_owner):
        raise HTTPException(status_code=403, detail="Bu destek talebine mesaj gönderemezsiniz")
    
    # Create message
    message_id = str(uuid.uuid4())
    message = {
        "id": message_id,
        "sender_id": current_user_id,
        "sender_name": user.get("full_name", "Kullanıcı"),
        "is_admin": is_admin,
        "message": message_text,
        "created_at": datetime.utcnow()
    }
    
    # Add message to ticket and reopen if closed
    update_data = {
        "updated_at": datetime.utcnow()
    }
    
    # Reopen ticket if it was closed/resolved
    if ticket["status"] in ["resolved", "closed"]:
        update_data["status"] = "open"
    
    await db.support_tickets.update_one(
        {"id": ticket_id},
        {
            "$push": {"messages": message},
            "$set": update_data
        }
    )
    
    # Send notification to other party
    if is_admin:
        # Admin sent message, notify user
        recipient_id = ticket["user_id"]
        notif_title = "Destek Talebinize Yeni Yanıt"
        notif_message = f"'{ticket['subject']}' konulu talebinize yeni yanıt verildi."
    else:
        # User sent message, notify all admins
        admins = await db.users.find({"user_type": "admin"}).to_list(100)
        for admin in admins:
            notif_id = str(uuid.uuid4())
            notif_data = {
                "id": notif_id,
                "user_id": admin["id"],
                "type": "support_ticket",
                "title": "Destek Talebine Yeni Mesaj",
                "message": f"{user.get('full_name', 'Kullanıcı')} tarafından '{ticket['subject']}' konulu talebe yeni mesaj.",
                "related_id": ticket_id,
                "related_type": "support_ticket",
                "read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(notif_data)
        
        # Return early for user
        updated_ticket = await db.support_tickets.find_one({"id": ticket_id})
        if "messages" not in updated_ticket:
            updated_ticket["messages"] = []
        return SupportTicket(**updated_ticket)
    
    # Send notification to user (if admin sent message)
    notif_id = str(uuid.uuid4())
    notif_data = {
        "id": notif_id,
        "user_id": recipient_id,
        "type": "support_ticket",
        "title": notif_title,
        "message": notif_message,
        "related_id": ticket_id,
        "related_type": "support_ticket",
        "read": False,
        "created_at": datetime.utcnow()
    }
    await db.notifications.insert_one(notif_data)
    
    # Return updated ticket
    updated_ticket = await db.support_tickets.find_one({"id": ticket_id})
    if "messages" not in updated_ticket:
        updated_ticket["messages"] = []
    
    return SupportTicket(**updated_ticket)
