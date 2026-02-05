"""
Yardımcı (Assistant) Yönetimi Endpoint'leri
Tesis sahipleri ve antrenörler için yardımcı atama ve yetki yönetimi
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel
import uuid
import logging

from auth import get_current_user

logger = logging.getLogger(__name__)

assistant_router = APIRouter(tags=["assistants"])

# Global db referansı
db = None

def set_database(database):
    """Database referansını ayarla"""
    global db
    db = database


# ==================== MODELLER ====================

class AssistantCreate(BaseModel):
    assistant_user_id: str  # Yardımcı olarak atanacak kullanıcı
    permissions: List[str]  # Verilen yetkiler

class AssistantUpdate(BaseModel):
    permissions: List[str]

# Mevcut yetki listesi
AVAILABLE_PERMISSIONS = {
    "reservation_management": {
        "id": "reservation_management",
        "label": "Rezervasyon Yönetimi",
        "description": "Rezervasyonları görüntüleme, onaylama ve reddetme",
        "icon": "calendar-outline"
    },
    "payment_view": {
        "id": "payment_view",
        "label": "Ödeme Görüntüleme",
        "description": "Ödemeleri ve mali bilgileri görme",
        "icon": "card-outline"
    },
    "member_management": {
        "id": "member_management",
        "label": "Üye Yönetimi",
        "description": "Üyeleri görme ve düzenleme",
        "icon": "people-outline"
    },
    "reports": {
        "id": "reports",
        "label": "Raporlar",
        "description": "Raporları görüntüleme",
        "icon": "stats-chart-outline"
    },
    "settings": {
        "id": "settings",
        "label": "Tesis/Profil Ayarları",
        "description": "Tesis veya profil bilgilerini düzenleme",
        "icon": "settings-outline"
    },
    "calendar_management": {
        "id": "calendar_management",
        "label": "Takvim Yönetimi",
        "description": "Takvim ve müsaitlik düzenleme",
        "icon": "time-outline"
    }
}


# ==================== ENDPOINT'LER ====================

@assistant_router.get("/assistants/permissions")
async def get_available_permissions():
    """Mevcut yetki listesini getir"""
    return {
        "success": True,
        "permissions": list(AVAILABLE_PERMISSIONS.values())
    }


@assistant_router.get("/assistants")
async def get_my_assistants(current_user: dict = Depends(get_current_user)):
    """Mevcut kullanıcının yardımcılarını listele"""
    try:
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        # Kullanıcının yardımcılarını bul
        assistants = await db.assistants.find({
            "owner_id": current_user_id,
            "is_active": True
        }).to_list(100)
        
        # Her yardımcı için kullanıcı bilgilerini ekle
        result = []
        for assistant in assistants:
            user = await db.users.find_one({"id": assistant["assistant_user_id"]})
            if user:
                result.append({
                    "id": assistant["id"],
                    "assistant_user_id": assistant["assistant_user_id"],
                    "assistant_name": user.get("full_name", ""),
                    "assistant_phone": user.get("phone", ""),
                    "assistant_email": user.get("email", ""),
                    "assistant_avatar": user.get("profile_image") or user.get("avatar"),
                    "permissions": assistant.get("permissions", []),
                    "created_at": assistant.get("created_at"),
                    "last_active": assistant.get("last_active")
                })
        
        return {
            "success": True,
            "assistants": result,
            "count": len(result)
        }
    except Exception as e:
        logger.error(f"Get assistants error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assistant_router.get("/assistants/my-owners")
async def get_my_owners(current_user: dict = Depends(get_current_user)):
    """Yardımcı olarak atandığım kullanıcıları listele"""
    try:
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        # Bu kullanıcının yardımcı olarak atandığı kayıtları bul
        assignments = await db.assistants.find({
            "assistant_user_id": current_user_id,
            "is_active": True
        }).to_list(100)
        
        # Her atama için owner bilgilerini ekle
        result = []
        for assignment in assignments:
            owner = await db.users.find_one({"id": assignment["owner_id"]})
            if owner:
                # Owner'ın tesislerini bul
                facilities = await db.facilities.find({"owner_id": assignment["owner_id"]}).to_list(10)
                facility_names = [f.get("name", "") for f in facilities]
                
                result.append({
                    "id": assignment["id"],
                    "owner_id": assignment["owner_id"],
                    "owner_name": owner.get("full_name", ""),
                    "owner_type": owner.get("user_type", ""),
                    "owner_avatar": owner.get("profile_image") or owner.get("avatar"),
                    "facilities": facility_names,
                    "permissions": assignment.get("permissions", []),
                    "created_at": assignment.get("created_at")
                })
        
        return {
            "success": True,
            "owners": result,
            "count": len(result)
        }
    except Exception as e:
        logger.error(f"Get my owners error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assistant_router.post("/assistants")
async def send_assistant_invitation(
    data: AssistantCreate,
    current_user: dict = Depends(get_current_user)
):
    """Yardımcı daveti gönder (onay bekleyecek)"""
    try:
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        # Kullanıcı tipini kontrol et (sadece tesis sahibi ve antrenör ekleyebilir)
        user = await db.users.find_one({"id": current_user_id})
        if not user:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        
        allowed_types = ["venue_owner", "facility_owner", "coach", "admin", "super_admin", "club_manager"]
        if user.get("user_type") not in allowed_types:
            raise HTTPException(status_code=403, detail="Yardımcı ekleme yetkiniz yok")
        
        # Yardımcı olarak eklenecek kullanıcıyı kontrol et
        assistant_user = await db.users.find_one({"id": data.assistant_user_id})
        if not assistant_user:
            raise HTTPException(status_code=404, detail="Yardımcı olarak eklenecek kullanıcı bulunamadı")
        
        # Kendini yardımcı olarak ekleyemez
        if data.assistant_user_id == current_user_id:
            raise HTTPException(status_code=400, detail="Kendinizi yardımcı olarak ekleyemezsiniz")
        
        # Zaten yardımcı mı kontrol et
        existing = await db.assistants.find_one({
            "owner_id": current_user_id,
            "assistant_user_id": data.assistant_user_id,
            "is_active": True
        })
        if existing:
            raise HTTPException(status_code=400, detail="Bu kullanıcı zaten yardımcınız")
        
        # Bekleyen davet var mı kontrol et
        pending_request = await db.assistant_requests.find_one({
            "owner_id": current_user_id,
            "assistant_user_id": data.assistant_user_id,
            "status": "pending"
        })
        if pending_request:
            raise HTTPException(status_code=400, detail="Bu kullanıcıya zaten davet gönderilmiş")
        
        # Yetkileri doğrula
        valid_permissions = [p for p in data.permissions if p in AVAILABLE_PERMISSIONS]
        
        # Davet kaydı oluştur
        request_id = str(uuid.uuid4())
        request_record = {
            "id": request_id,
            "owner_id": current_user_id,
            "owner_name": user.get("full_name", ""),
            "owner_type": user.get("user_type", ""),
            "assistant_user_id": data.assistant_user_id,
            "assistant_name": assistant_user.get("full_name", ""),
            "permissions": valid_permissions,
            "status": "pending",  # pending, accepted, rejected
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.assistant_requests.insert_one(request_record)
        
        # Yardımcıya onay bildirimi gönder
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": data.assistant_user_id,
            "type": "assistant_invitation",
            "title": "👥 Yardımcılık Daveti",
            "message": f"{user.get('full_name', 'Bir kullanıcı')} sizi yardımcı olarak eklemek istiyor.",
            "data": {
                "request_id": request_id,
                "owner_id": current_user_id,
                "owner_name": user.get("full_name", ""),
                "permissions": valid_permissions
            },
            "action_url": f"/assistant-invitations",
            "read": False,
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
        
        logger.info(f"👥 Assistant invitation sent: {data.assistant_user_id} from owner {current_user_id}")
        
        return {
            "success": True,
            "message": "Yardımcılık daveti gönderildi. Kullanıcı onayladığında yardımcınız olacak.",
            "request_id": request_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Send assistant invitation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assistant_router.get("/assistants/pending-invitations")
async def get_pending_invitations(current_user: dict = Depends(get_current_user)):
    """Bekleyen yardımcılık davetlerini listele (gelen davetler)"""
    try:
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        invitations = await db.assistant_requests.find({
            "assistant_user_id": current_user_id,
            "status": "pending"
        }).to_list(100)
        
        result = []
        for inv in invitations:
            # Owner bilgilerini ekle
            owner = await db.users.find_one({"id": inv["owner_id"]})
            result.append({
                "id": inv["id"],
                "owner_id": inv["owner_id"],
                "owner_name": inv.get("owner_name") or (owner.get("full_name") if owner else ""),
                "owner_type": inv.get("owner_type") or (owner.get("user_type") if owner else ""),
                "owner_avatar": owner.get("profile_image") or owner.get("avatar") if owner else None,
                "permissions": inv.get("permissions", []),
                "created_at": inv.get("created_at")
            })
        
        return {
            "success": True,
            "invitations": result,
            "count": len(result)
        }
    except Exception as e:
        logger.error(f"Get pending invitations error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assistant_router.get("/assistants/sent-invitations")
async def get_sent_invitations(current_user: dict = Depends(get_current_user)):
    """Gönderilen yardımcılık davetlerini listele"""
    try:
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        invitations = await db.assistant_requests.find({
            "owner_id": current_user_id,
            "status": "pending"
        }).to_list(100)
        
        result = []
        for inv in invitations:
            # Assistant bilgilerini ekle
            assistant_user = await db.users.find_one({"id": inv["assistant_user_id"]})
            result.append({
                "id": inv["id"],
                "assistant_user_id": inv["assistant_user_id"],
                "assistant_name": inv.get("assistant_name") or (assistant_user.get("full_name") if assistant_user else ""),
                "assistant_avatar": assistant_user.get("profile_image") or assistant_user.get("avatar") if assistant_user else None,
                "permissions": inv.get("permissions", []),
                "created_at": inv.get("created_at")
            })
        
        return {
            "success": True,
            "invitations": result,
            "count": len(result)
        }
    except Exception as e:
        logger.error(f"Get sent invitations error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assistant_router.post("/assistants/invitations/{invitation_id}/accept")
async def accept_invitation(
    invitation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Yardımcılık davetini kabul et"""
    try:
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        # Daveti bul
        invitation = await db.assistant_requests.find_one({
            "id": invitation_id,
            "assistant_user_id": current_user_id,
            "status": "pending"
        })
        
        if not invitation:
            raise HTTPException(status_code=404, detail="Davet bulunamadı veya zaten işlem yapılmış")
        
        # Daveti kabul edildi olarak işaretle
        await db.assistant_requests.update_one(
            {"id": invitation_id},
            {
                "$set": {
                    "status": "accepted",
                    "accepted_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Yardımcı kaydı oluştur
        assistant_user = await db.users.find_one({"id": current_user_id})
        assistant_record = {
            "id": str(uuid.uuid4()),
            "owner_id": invitation["owner_id"],
            "owner_name": invitation.get("owner_name", ""),
            "owner_type": invitation.get("owner_type", ""),
            "assistant_user_id": current_user_id,
            "permissions": invitation.get("permissions", []),
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.assistants.insert_one(assistant_record)
        
        # Kullanıcı tipini güncelle (eğer assistant değilse)
        if assistant_user and assistant_user.get("user_type") != "assistant":
            await db.users.update_one(
                {"id": current_user_id},
                {
                    "$set": {
                        "user_type": "assistant",
                        "previous_user_type": assistant_user.get("user_type"),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
        
        # Owner'a bildirim gönder
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": invitation["owner_id"],
            "type": "assistant_accepted",
            "title": "✅ Yardımcılık Daveti Kabul Edildi",
            "message": f"{assistant_user.get('full_name', 'Kullanıcı')} yardımcılık davetinizi kabul etti.",
            "read": False,
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
        
        logger.info(f"👥 Assistant invitation accepted: {invitation_id}")
        
        return {
            "success": True,
            "message": "Yardımcılık daveti kabul edildi"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Accept invitation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assistant_router.post("/assistants/invitations/{invitation_id}/reject")
async def reject_invitation(
    invitation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Yardımcılık davetini reddet"""
    try:
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        # Daveti bul
        invitation = await db.assistant_requests.find_one({
            "id": invitation_id,
            "assistant_user_id": current_user_id,
            "status": "pending"
        })
        
        if not invitation:
            raise HTTPException(status_code=404, detail="Davet bulunamadı veya zaten işlem yapılmış")
        
        # Daveti reddedildi olarak işaretle
        await db.assistant_requests.update_one(
            {"id": invitation_id},
            {
                "$set": {
                    "status": "rejected",
                    "rejected_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Owner'a bildirim gönder
        assistant_user = await db.users.find_one({"id": current_user_id})
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": invitation["owner_id"],
            "type": "assistant_rejected",
            "title": "❌ Yardımcılık Daveti Reddedildi",
            "message": f"{assistant_user.get('full_name', 'Kullanıcı') if assistant_user else 'Kullanıcı'} yardımcılık davetinizi reddetti.",
            "read": False,
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
        
        logger.info(f"👥 Assistant invitation rejected: {invitation_id}")
        
        return {
            "success": True,
            "message": "Yardımcılık daveti reddedildi"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reject invitation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assistant_router.delete("/assistants/invitations/{invitation_id}")
async def cancel_invitation(
    invitation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Gönderilen daveti iptal et"""
    try:
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        # Daveti bul (gönderen olarak)
        invitation = await db.assistant_requests.find_one({
            "id": invitation_id,
            "owner_id": current_user_id,
            "status": "pending"
        })
        
        if not invitation:
            raise HTTPException(status_code=404, detail="Davet bulunamadı")
        
        # Daveti sil
        await db.assistant_requests.delete_one({"id": invitation_id})
        
        logger.info(f"👥 Assistant invitation cancelled: {invitation_id}")
        
        return {
            "success": True,
            "message": "Davet iptal edildi"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel invitation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assistant_router.put("/assistants/{assistant_id}")
async def update_assistant_permissions(
    assistant_id: str,
    data: AssistantUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Yardımcının yetkilerini güncelle"""
    try:
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        # Yardımcı kaydını bul
        assistant = await db.assistants.find_one({
            "id": assistant_id,
            "owner_id": current_user_id,
            "is_active": True
        })
        
        if not assistant:
            raise HTTPException(status_code=404, detail="Yardımcı bulunamadı")
        
        # Yetkileri doğrula
        valid_permissions = [p for p in data.permissions if p in AVAILABLE_PERMISSIONS]
        
        # Güncelle
        await db.assistants.update_one(
            {"id": assistant_id},
            {
                "$set": {
                    "permissions": valid_permissions,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"👥 Assistant permissions updated: {assistant_id}")
        
        return {
            "success": True,
            "message": "Yetkiler güncellendi",
            "permissions": valid_permissions
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update assistant error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assistant_router.delete("/assistants/{assistant_id}")
async def remove_assistant(
    assistant_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Yardımcıyı kaldır"""
    try:
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        # Yardımcı kaydını bul
        assistant = await db.assistants.find_one({
            "id": assistant_id,
            "owner_id": current_user_id,
            "is_active": True
        })
        
        if not assistant:
            raise HTTPException(status_code=404, detail="Yardımcı bulunamadı")
        
        # Pasif yap (soft delete)
        await db.assistants.update_one(
            {"id": assistant_id},
            {
                "$set": {
                    "is_active": False,
                    "removed_at": datetime.utcnow()
                }
            }
        )
        
        # Eğer kullanıcının başka owner'ı yoksa, user_type'ı eski haline döndür
        other_assignments = await db.assistants.count_documents({
            "assistant_user_id": assistant["assistant_user_id"],
            "is_active": True,
            "id": {"$ne": assistant_id}
        })
        
        if other_assignments == 0:
            # Başka ataması yok, eski tipine döndür
            assistant_user = await db.users.find_one({"id": assistant["assistant_user_id"]})
            if assistant_user and assistant_user.get("user_type") == "assistant":
                previous_type = assistant_user.get("previous_user_type", "player")
                await db.users.update_one(
                    {"id": assistant["assistant_user_id"]},
                    {
                        "$set": {
                            "user_type": previous_type,
                            "updated_at": datetime.utcnow()
                        },
                        "$unset": {"previous_user_type": ""}
                    }
                )
        
        # Yardımcıya bildirim gönder
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": assistant["assistant_user_id"],
            "type": "assistant_removed",
            "title": "👥 Yardımcılık Kaldırıldı",
            "message": f"{assistant.get('owner_name', 'Bir kullanıcı')} sizi yardımcı listesinden çıkardı.",
            "read": False,
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
        
        logger.info(f"👥 Assistant removed: {assistant_id}")
        
        return {
            "success": True,
            "message": "Yardımcı kaldırıldı"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove assistant error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assistant_router.get("/assistants/search-users")
async def search_users_for_assistant(
    search: str,
    current_user: dict = Depends(get_current_user)
):
    """Yardımcı olarak eklenecek kullanıcıları ara"""
    try:
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        if not search or len(search) < 2:
            return {"success": True, "users": []}
        
        # Mevcut yardımcıları bul (hariç tutmak için)
        existing_assistants = await db.assistants.find({
            "owner_id": current_user_id,
            "is_active": True
        }).to_list(100)
        excluded_ids = [a["assistant_user_id"] for a in existing_assistants]
        excluded_ids.append(current_user_id)  # Kendini de hariç tut
        
        # Kullanıcıları ara
        query = {
            "id": {"$nin": excluded_ids},
            "$or": [
                {"full_name": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}}
            ]
        }
        
        users = await db.users.find(query).limit(20).to_list(20)
        
        result = []
        for user in users:
            result.append({
                "id": user["id"],
                "full_name": user.get("full_name", ""),
                "phone": user.get("phone", ""),
                "email": user.get("email", ""),
                "user_type": user.get("user_type", ""),
                "avatar": user.get("profile_image") or user.get("avatar"),
                "city": user.get("city", "")
            })
        
        return {
            "success": True,
            "users": result
        }
    except Exception as e:
        logger.error(f"Search users error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assistant_router.get("/assistants/check-permission/{owner_id}/{permission}")
async def check_assistant_permission(
    owner_id: str,
    permission: str,
    current_user: dict = Depends(get_current_user)
):
    """Yardımcının belirli bir yetkiye sahip olup olmadığını kontrol et"""
    try:
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        # Kendisi owner mı?
        if current_user_id == owner_id:
            return {"success": True, "has_permission": True, "is_owner": True}
        
        # Yardımcı kaydını bul
        assignment = await db.assistants.find_one({
            "owner_id": owner_id,
            "assistant_user_id": current_user_id,
            "is_active": True
        })
        
        if not assignment:
            return {"success": True, "has_permission": False, "is_owner": False}
        
        has_permission = permission in assignment.get("permissions", [])
        
        return {
            "success": True,
            "has_permission": has_permission,
            "is_owner": False,
            "all_permissions": assignment.get("permissions", [])
        }
    except Exception as e:
        logger.error(f"Check permission error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== YARDIMCI FONKSİYONLARI ====================

async def get_user_with_assistant_access(current_user_id: str, owner_id: str = None, required_permission: str = None):
    """
    Kullanıcının kendisi mi yoksa yardımcı mı olduğunu kontrol et
    Yardımcı ise belirtilen yetkiye sahip mi kontrol et
    
    Returns: (is_authorized, user_data, permission_source)
    """
    global db
    
    # Owner ID yoksa current_user'ın kendi bilgilerini döndür
    if not owner_id or owner_id == current_user_id:
        user = await db.users.find_one({"id": current_user_id})
        return (True, user, "owner")
    
    # Yardımcı kaydını kontrol et
    assignment = await db.assistants.find_one({
        "owner_id": owner_id,
        "assistant_user_id": current_user_id,
        "is_active": True
    })
    
    if not assignment:
        return (False, None, None)
    
    # Yetki kontrolü
    if required_permission and required_permission not in assignment.get("permissions", []):
        return (False, None, "no_permission")
    
    # Owner bilgilerini döndür
    owner = await db.users.find_one({"id": owner_id})
    return (True, owner, "assistant")
