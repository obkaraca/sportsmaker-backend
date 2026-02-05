"""
Cancellation Request System
- Users can request cancellation with 10% fee (up to 24h before event)
- Providers can accept/reject cancellation requests
- Single-sided cancellations result in 1-star automatic review
- All cancellations notify admins
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import uuid
import logging

from auth import get_current_user

router = APIRouter(prefix="/api/cancellation-requests", tags=["Cancellation"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global db reference
db = None

def set_cancellation_db(database):
    """Set database reference for cancellation endpoints"""
    global db
    db = database
    logger.info(f"✅ Cancellation DB set: {db is not None}")


class CancellationRequestCreate(BaseModel):
    item_type: str  # 'reservation', 'facility_reservation', 'event_participation'
    item_id: str
    reason: Optional[str] = None


class CancellationRequestResponse(BaseModel):
    accept: bool
    reason: Optional[str] = None


async def get_item_details(item_type: str, item_id: str):
    """Get item details based on type - ASYNC version for motor"""
    global db
    if db is None:
        return None
    
    def clean_mongo_doc(doc):
        """MongoDB dökümanından _id alanını kaldır"""
        if doc and '_id' in doc:
            doc = dict(doc)
            del doc['_id']
        return doc
        
    if item_type == "reservation":
        # Person reservation (coach, referee, player) OR facility reservation in reservations collection
        item = await db.reservations.find_one({"id": item_id})
        if item:
            item = clean_mongo_doc(item)
            # ✅ Tesis rezervasyonu kontrolü (reservations koleksiyonundaki type: facility)
            if item.get("type") == "facility":
                facility = await db.facilities.find_one({"id": item.get("facility_id")})
                facility = clean_mongo_doc(facility)
                owner_id = facility.get("owner_id") if facility else None
                facility_name = facility.get("name") if facility else "Tesis"
                
                # start_time hesapla
                start_time = item.get("date")
                if item.get("start_time"):
                    start_time = f"{item.get('date')} {item.get('start_time')}"
                
                # user_id dict olabilir
                user_id = item.get("user_id")
                if isinstance(user_id, dict):
                    user_id = user_id.get("id")
                
                return {
                    "item": item,
                    "provider_id": owner_id,
                    "requester_id": user_id,
                    "amount": item.get("total_price", 0),
                    "start_time": start_time,
                    "title": f"Tesis Rezervasyonu - {facility_name}"
                }
            elif item.get("type") == "coach" or item.get("reservation_type") == "coach":
                # ✅ Antrenör rezervasyonu
                coach_id = item.get("coach_id")
                
                # user_id dict olabilir
                user_id = item.get("user_id")
                if isinstance(user_id, dict):
                    user_id = user_id.get("id")
                
                # start_time hesapla
                start_time = item.get("date")
                if item.get("hour"):
                    start_time = f"{item.get('date')} {item.get('hour')}"
                
                # Coach bilgisini al
                coach = await db.users.find_one({"id": coach_id})
                coach = clean_mongo_doc(coach)
                coach_name = coach.get("full_name", "Antrenör") if coach else "Antrenör"
                
                return {
                    "item": item,
                    "provider_id": coach_id,
                    "requester_id": user_id,
                    "amount": item.get("total_price", 0),
                    "start_time": start_time,
                    "title": f"Antrenör Rezervasyonu - {coach_name}"
                }
            elif item.get("type") == "referee" or item.get("reservation_type") == "referee":
                # ✅ Hakem rezervasyonu
                referee_id = item.get("referee_id")
                
                # user_id dict olabilir
                user_id = item.get("user_id")
                if isinstance(user_id, dict):
                    user_id = user_id.get("id")
                
                # start_time hesapla
                start_time = item.get("date")
                if item.get("hour"):
                    start_time = f"{item.get('date')} {item.get('hour')}"
                
                # Referee bilgisini al
                referee = await db.users.find_one({"id": referee_id})
                referee = clean_mongo_doc(referee)
                referee_name = referee.get("full_name", "Hakem") if referee else "Hakem"
                
                return {
                    "item": item,
                    "provider_id": referee_id,
                    "requester_id": user_id,
                    "amount": item.get("total_price", 0),
                    "start_time": start_time,
                    "title": f"Hakem Rezervasyonu - {referee_name}"
                }
            elif item.get("type") == "player" or item.get("reservation_type") == "player":
                # ✅ Oyuncu rezervasyonu
                player_id = item.get("player_id")
                
                # user_id dict olabilir
                user_id = item.get("user_id")
                if isinstance(user_id, dict):
                    user_id = user_id.get("id")
                
                # start_time hesapla
                start_time = item.get("date")
                if item.get("hour"):
                    start_time = f"{item.get('date')} {item.get('hour')}"
                
                # Player bilgisini al
                player = await db.users.find_one({"id": player_id})
                player = clean_mongo_doc(player)
                player_name = player.get("full_name", "Oyuncu") if player else "Oyuncu"
                
                return {
                    "item": item,
                    "provider_id": player_id,
                    "requester_id": user_id,
                    "amount": item.get("total_price", 0),
                    "start_time": start_time,
                    "title": f"Oyuncu Rezervasyonu - {player_name}"
                }
            else:
                # Normal kişi rezervasyonu (fallback)
                # user_id dict olabilir
                user_id = item.get("user_id")
                if isinstance(user_id, dict):
                    user_id = user_id.get("id")
                
                requester_id = item.get("requester_id")
                if isinstance(requester_id, dict):
                    requester_id = requester_id.get("id")
                
                return {
                    "item": item,
                    "provider_id": item.get("provider_id"),
                    "requester_id": requester_id or user_id,
                    "amount": item.get("total_price", 0),
                    "start_time": item.get("date"),
                    "title": f"Rezervasyon - {item.get('service_type', 'Hizmet')}"
                }
    
    elif item_type == "facility_reservation":
        # ✅ facility_reservations koleksiyonundaki tesis rezervasyonları
        item = await db.facility_reservations.find_one({"id": item_id})
        if item:
            item = clean_mongo_doc(item)
            # Get facility owner
            facility = await db.facilities.find_one({"id": item.get("facility_id")})
            facility = clean_mongo_doc(facility)
            owner_id = facility.get("owner_id") if facility else None
            facility_name = facility.get("name") if facility else "Tesis"
            
            # start_time hesapla
            start_time = item.get("date")
            if item.get("start_time"):
                start_time = f"{item.get('date')} {item.get('start_time')}"
            
            return {
                "item": item,
                "provider_id": owner_id,
                "requester_id": item.get("user_id"),
                "amount": item.get("total_price", 0),
                "start_time": start_time,
                "title": f"Tesis Rezervasyonu - {facility_name}"
            }
        
        # ✅ Eğer facility_reservations'da bulunamazsa, reservations koleksiyonunda ara
        item = await db.reservations.find_one({"id": item_id, "type": "facility"})
        if item:
            item = clean_mongo_doc(item)
            facility = await db.facilities.find_one({"id": item.get("facility_id")})
            facility = clean_mongo_doc(facility)
            owner_id = facility.get("owner_id") if facility else None
            facility_name = facility.get("name") if facility else "Tesis"
            
            start_time = item.get("date")
            if item.get("start_time"):
                start_time = f"{item.get('date')} {item.get('start_time')}"
            
            return {
                "item": item,
                "provider_id": owner_id,
                "requester_id": item.get("user_id"),
                "amount": item.get("total_price", 0),
                "start_time": start_time,
                "title": f"Tesis Rezervasyonu - {facility_name}"
            }
    
    elif item_type == "event_participation":
        # Önce participations koleksiyonunda ara
        item = await db.participations.find_one({"id": item_id})
        if item:
            item = clean_mongo_doc(item)
            event = await db.events.find_one({"id": item.get("event_id")})
            event = clean_mongo_doc(event)
            if event:
                return {
                    "item": item,
                    "provider_id": event.get("organizer_id"),
                    "requester_id": item.get("user_id"),
                    "amount": item.get("amount_paid", 0),
                    "start_time": event.get("start_date"),
                    "title": f"Etkinlik - {event.get('title', 'Etkinlik')}",
                    "event": event
                }
        
        # event_participants koleksiyonunda ara
        item = await db.event_participants.find_one({"id": item_id})
        if item:
            item = clean_mongo_doc(item)
            event = await db.events.find_one({"id": item.get("event_id")})
            event = clean_mongo_doc(event)
            if event:
                return {
                    "item": item,
                    "provider_id": event.get("organizer_id"),
                    "requester_id": item.get("user_id"),
                    "amount": item.get("amount_paid", 0),
                    "start_time": event.get("start_date"),
                    "title": f"Etkinlik - {event.get('title', 'Etkinlik')}",
                    "event": event
                }
        
        # item_id event ID olabilir - event.participants içinde current user'ı ara
        event = await db.events.find_one({"id": item_id})
        if event:
            event = clean_mongo_doc(event)
            # ticket_info None olabilir, güvenli şekilde price'ı al
            ticket_info = event.get("ticket_info") or {}
            amount = ticket_info.get("price", 0) if isinstance(ticket_info, dict) else 0
            
            # Bu durumda requester_id'yi dışarıdan almamız gerekecek
            return {
                "item": {"id": f"event-{item_id}", "event_id": item_id, "status": "joined"},
                "provider_id": event.get("organizer_id"),
                "requester_id": None,  # Sonra set edilecek
                "amount": amount,
                "start_time": event.get("start_date"),
                "title": f"Etkinlik - {event.get('title', 'Etkinlik')}",
                "event": event,
                "is_event_direct": True  # Event'e direkt katılım
            }
    
    return None


# İptal kuralları sabitleri - REZERVASYONLAR İÇİN
SYSTEM_COMMISSION_RATE = 0.13  # %13 sistem komisyonu (rezervasyonlar)
CANCELLATION_RULES = {
    "24h_plus": {"refund_rate": 1.0, "penalty_rate": 0.0, "can_review": True, "description": "24 saatten önce iptal"},
    "6h_24h": {"refund_rate": 0.75, "penalty_rate": 0.25, "can_review": False, "description": "6-24 saat arası iptal"},
    "6h_minus": {"refund_rate": 0.50, "penalty_rate": 0.50, "can_review": False, "description": "6 saatten az kala iptal"},
    "no_show": {"refund_rate": 0.0, "penalty_rate": 1.0, "can_review": False, "description": "Gelmeme (No-show)"}
}

# ✅ YENİ: ETKİNLİK/KAMP İPTAL KURALLARI
EVENT_SYSTEM_COMMISSION_RATE = 0.30  # %30 sistem komisyonu (etkinlikler)
EVENT_ORGANIZER_RATE = 0.70  # %70 organizatör payı
EVENT_CANCELLATION_RULES = {
    "7d_plus": {"refund_rate": 1.0, "penalty_rate": 0.0, "can_review": True, "description": "7 günden önce iptal", "trust_penalty": 0},
    "3d_7d": {"refund_rate": 0.75, "penalty_rate": 0.25, "can_review": False, "description": "3-7 gün arası iptal", "trust_penalty": 0},
    "1d_3d": {"refund_rate": 0.50, "penalty_rate": 0.50, "can_review": False, "description": "1-3 gün arası iptal", "trust_penalty": 5},
    "24h_minus": {"refund_rate": 0.0, "penalty_rate": 1.0, "can_review": False, "description": "24 saatten az kala iptal", "trust_penalty": 10},
    "no_show": {"refund_rate": 0.0, "penalty_rate": 1.0, "can_review": False, "description": "Gelmeme (No-show)", "trust_penalty": 20}
}


def calculate_cancellation_tier(start_time, is_event: bool = False) -> dict:
    """Başlangıç saatine göre iptal kategorisini hesapla - Rezervasyon veya Etkinlik"""
    if not start_time:
        return None
    
    if isinstance(start_time, str):
        try:
            start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        except:
            return None
    
    now = datetime.utcnow()
    if start_time.tzinfo:
        now = now.replace(tzinfo=start_time.tzinfo)
    
    time_until_start = start_time - now
    hours_until_start = time_until_start.total_seconds() / 3600
    days_until_start = hours_until_start / 24
    
    if is_event:
        # ✅ ETKİNLİK İPTAL KURALLARI (gün bazlı)
        if days_until_start >= 7:
            tier = "7d_plus"
        elif days_until_start >= 3:
            tier = "3d_7d"
        elif days_until_start >= 1:
            tier = "1d_3d"
        elif hours_until_start > 0:
            tier = "24h_minus"
        else:
            tier = "no_show"
        
        rule = EVENT_CANCELLATION_RULES[tier]
        return {
            "tier": tier,
            "hours_until_start": hours_until_start,
            "days_until_start": days_until_start,
            "refund_rate": rule["refund_rate"],
            "penalty_rate": rule["penalty_rate"],
            "can_review": rule["can_review"],
            "description": rule["description"],
            "trust_penalty": rule["trust_penalty"],
            "is_event": True
        }
    else:
        # REZERVASYON İPTAL KURALLARI (saat bazlı)
        if hours_until_start >= 24:
            tier = "24h_plus"
        elif hours_until_start >= 6:
            tier = "6h_24h"
        elif hours_until_start > 0:
            tier = "6h_minus"
        else:
            tier = "no_show"
        
        rule = CANCELLATION_RULES[tier]
        return {
            "tier": tier,
            "hours_until_start": hours_until_start,
            "refund_rate": rule["refund_rate"],
            "penalty_rate": rule["penalty_rate"],
            "can_review": rule["can_review"],
            "description": rule["description"],
            "is_event": False
        }


def calculate_refund_amounts(total_amount: float, tier_info: dict) -> dict:
    """İade ve kesinti tutarlarını hesapla - Etkinlik veya Rezervasyon"""
    penalty_amount = total_amount * tier_info["penalty_rate"]
    refund_amount = total_amount * tier_info["refund_rate"]
    
    # Etkinlik mi rezervasyon mu?
    is_event = tier_info.get("is_event", False)
    
    if is_event:
        # Etkinlik: %30 sisteme, %70 organizatöre
        system_commission = penalty_amount * EVENT_SYSTEM_COMMISSION_RATE
        provider_amount = penalty_amount * EVENT_ORGANIZER_RATE
    else:
        # Rezervasyon: %13 sisteme, %87 sağlayıcıya
        system_commission = penalty_amount * SYSTEM_COMMISSION_RATE
        provider_amount = penalty_amount - system_commission
    
    return {
        "total_amount": total_amount,
        "refund_amount": refund_amount,
        "penalty_amount": penalty_amount,
        "system_commission": system_commission,
        "provider_amount": provider_amount,
        "refund_rate": tier_info["refund_rate"] * 100,
        "penalty_rate": tier_info["penalty_rate"] * 100,
        "is_event": is_event
    }


async def check_repeated_cancellations(user_id: str) -> dict:
    """Son 30 günde tekrar eden iptalleri kontrol et"""
    global db
    if db is None:
        return {"has_penalty": False}
    
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
    
    # Son 30 gün içindeki iptalleri say
    cancellations = await db.cancellation_requests.find({
        "requester_id": user_id,
        "status": "accepted",
        "created_at": {"$gte": thirty_days_ago}
    }).to_list(100)
    
    short_notice_count = 0  # <6 saat iptaller
    no_show_count = 0
    
    for c in cancellations:
        tier = c.get("cancellation_tier", "")
        if tier == "6h_minus":
            short_notice_count += 1
        elif tier == "no_show":
            no_show_count += 1
    
    result = {
        "has_penalty": False,
        "short_notice_count": short_notice_count,
        "no_show_count": no_show_count,
        "extra_penalty_rate": 0,
        "restrictions": []
    }
    
    # 3 kez <6 saat iptal → %10 ek kesinti
    if short_notice_count >= 3:
        result["has_penalty"] = True
        result["extra_penalty_rate"] = 0.10
        result["restrictions"].append("Son 30 günde 3+ kısa süreli iptal nedeniyle %10 ek kesinti")
    
    # 2 No-show → Ön ödeme oranı %100, kampanyalardan çıkarma
    if no_show_count >= 2:
        result["has_penalty"] = True
        result["restrictions"].append("2+ No-show nedeniyle kampanyalardan çıkarıldınız")
    
    return result


def can_request_cancellation(start_time, is_event: bool = False) -> tuple:
    """Check if cancellation can be requested - etkinlik veya rezervasyon"""
    if not start_time:
        return False, "Başlangıç zamanı bulunamadı", None
    
    if isinstance(start_time, str):
        try:
            start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        except:
            return False, "Geçersiz tarih formatı", None
    
    now = datetime.utcnow()
    if start_time.tzinfo:
        now = now.replace(tzinfo=start_time.tzinfo)
    
    time_until_start = start_time - now
    
    # Geçmiş tarih kontrolü
    if time_until_start.total_seconds() < 0:
        return False, "Geçmiş tarihlere iptal talebi yapılamaz", None
    
    # İptal kategorisini hesapla (etkinlik veya rezervasyon)
    tier_info = calculate_cancellation_tier(start_time, is_event=is_event)
    
    return True, "", tier_info


async def apply_trust_penalty(user_id: str, penalty_points: int, reason: str):
    """Kullanıcının güven puanını düşür - No-show veya geç iptal için"""
    global db
    if db is None or penalty_points <= 0:
        return
    
    # Kullanıcıyı bul ve güven puanını güncelle
    user = await db.users.find_one({"id": user_id})
    if not user:
        return
    
    current_trust_score = user.get("trust_score", 100)  # Varsayılan 100 puan
    new_trust_score = max(0, current_trust_score - penalty_points)  # 0'ın altına düşmesin
    
    # No-show sayısını artır
    no_show_count = user.get("no_show_count", 0)
    
    await db.users.update_one(
        {"id": user_id},
        {
            "$set": {
                "trust_score": new_trust_score,
                "updated_at": datetime.utcnow().isoformat()
            },
            "$inc": {"no_show_count": 1 if "no_show" in reason.lower() else 0}
        }
    )
    
    # Güven puanı kaydı oluştur
    trust_log = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "action": "penalty",
        "points": -penalty_points,
        "reason": reason,
        "previous_score": current_trust_score,
        "new_score": new_trust_score,
        "created_at": datetime.utcnow().isoformat()
    }
    await db.trust_logs.insert_one(trust_log)
    
    logger.info(f"⚠️ Trust penalty applied to {user_id}: -{penalty_points} points. New score: {new_trust_score}")


async def send_notification(user_id: str, title: str, message: str, notification_type: str = "cancellation", data: dict = None):
    """Send notification to user - ASYNC version"""
    global db
    if db is None:
        return None
        
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "data": data or {},
        "is_read": False,
        "created_at": datetime.utcnow()  # datetime objesi olarak kaydet
    }
    await db.notifications.insert_one(notification)
    logger.info(f"📩 Notification sent to {user_id}: {title}")
    return notification


async def send_admin_notification(title: str, message: str, data: dict = None):
    """Send notification to all admins - ASYNC version"""
    global db
    if db is None:
        return
        
    admin_users = db.users.find({"user_type": "admin"})
    async for admin in admin_users:
        await send_notification(admin["id"], title, message, "admin_cancellation", data)


async def create_automatic_review(target_user_id: str, reviewer_id: str, item_type: str, item_id: str):
    """Create automatic 1-star review for cancellation penalty - ASYNC version"""
    global db
    if db is None:
        return None
    
    # ✅ Sistem tarafından verilen değerlendirme - reviewer_id olarak "system" kullan
    review = {
        "id": str(uuid.uuid4()),
        "reviewer_id": "system",  # ✅ SportsMaker sistem değerlendirmesi
        "reviewer_name": "SportsMaker",  # ✅ Görünen isim
        "target_user_id": target_user_id,
        "target_type": "user",
        "rating": 1,
        "comment": "Tek taraflı rezervasyon iptali yapılmıştır.",
        "is_automatic": True,
        "is_system_review": True,  # ✅ Sistem değerlendirmesi flag
        "cancellation_item_type": item_type,
        "cancellation_item_id": item_id,
        "original_requester_id": reviewer_id,  # ✅ Orijinal müşteri ID'sini sakla
        "created_at": datetime.utcnow().isoformat()
    }
    await db.reviews.insert_one(review)
    
    # Update user's review stats
    await db.users.update_one(
        {"id": target_user_id},
        {
            "$inc": {"total_reviews": 1, "total_rating": 1},
            "$set": {"updated_at": datetime.utcnow().isoformat()}
        }
    )
    
    logger.info(f"⭐ Automatic 1-star review created by SportsMaker for user {target_user_id}")
    return review


async def record_commission(amount: float, description: str, item_type: str, item_id: str, user_id: str):
    """Record commission from cancellation fee - ASYNC version"""
    global db
    if db is None:
        return None
        
    transaction = {
        "id": str(uuid.uuid4()),
        "type": "cancellation_fee",
        "amount": amount,
        "description": description,
        "item_type": item_type,
        "item_id": item_id,
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat()
    }
    await db.commission_transactions.insert_one(transaction)
    logger.info(f"💰 Commission recorded: {amount} TL from {description}")
    return transaction


@router.post("")
async def create_cancellation_request(
    request: CancellationRequestCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a cancellation request with TIERED FEE SYSTEM - Kademeli İptal Sistemi"""
    global db
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    user_id = current_user["id"]
    
    logger.info(f"📝 CREATE CANCELLATION - item_type: {request.item_type}, item_id: {request.item_id}")
    logger.info(f"📝 Current user: {current_user}")
    
    # Get item details
    details = await get_item_details(request.item_type, request.item_id)
    logger.info(f"📝 Details received: {details is not None}")
    
    if not details:
        logger.error(f"❌ Item not found: {request.item_type}/{request.item_id}")
        raise HTTPException(status_code=404, detail="Öğe bulunamadı")
    
    logger.info(f"📝 Details: is_event_direct={details.get('is_event_direct')}, requester_id={details.get('requester_id')}")
    
    # is_event_direct durumunda requester_id'yi current user olarak set et
    if details.get("is_event_direct"):
        event = details.get("event")
        if event:
            participants = event.get("participants", [])
            user_in_participants = False
            for p in participants:
                if isinstance(p, str) and p == user_id:
                    user_in_participants = True
                    break
                elif isinstance(p, dict) and (p.get("id") == user_id or p.get("user_id") == user_id):
                    user_in_participants = True
                    break
            
            logger.info(f"📝 User in participants: {user_in_participants}")
            
            if user_in_participants:
                details["requester_id"] = user_id
    
    # Check if user is the requester
    if details["requester_id"] != user_id:
        logger.warning(f"❌ User {user_id} is not requester {details['requester_id']}")
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Check if already cancelled or has pending request
    existing = await db.cancellation_requests.find_one({
        "item_type": request.item_type,
        "item_id": request.item_id,
        "status": {"$in": ["pending", "accepted"]}
    })
    if existing:
        raise HTTPException(status_code=400, detail="Bu öğe için zaten bir iptal talebi var")
    
    # ✅ ETKİNLİK/KAMP TESPİTİ
    is_event = request.item_type == "event_participation" or details.get("is_event_direct", False)
    
    # ✅ YENİ KADEMELİ İPTAL SİSTEMİ - Etkinlik veya Rezervasyon
    can_cancel, error_msg, tier_info = can_request_cancellation(details["start_time"], is_event=is_event)
    if not can_cancel:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # ✅ Kademeli ücret hesaplaması
    total_amount = details["amount"] or 0
    refund_info = calculate_refund_amounts(total_amount, tier_info)
    
    cancellation_fee = refund_info["penalty_amount"]
    refund_amount = refund_info["refund_amount"]
    system_commission = refund_info["system_commission"]
    provider_amount = refund_info["provider_amount"]
    
    logger.info(f"💰 Cancellation tier: {tier_info['tier']}")
    logger.info(f"💰 Total amount: {total_amount}, Fee: {cancellation_fee}, Refund: {refund_amount}")
    logger.info(f"💰 System commission: {system_commission}, Provider amount: {provider_amount}")
    
    # Event ID'yi al (is_event_direct durumunda veya event varsa)
    event_id = None
    if details.get("is_event_direct"):
        event_id = details.get("event", {}).get("id") or request.item_id
    elif details.get("event"):
        event_id = details.get("event", {}).get("id")
    elif request.item_type == "event_participation":
        # item_id event ID olabilir
        event_id = request.item_id
    
    # ✅ Create cancellation request with tiered info
    cancellation_request = {
        "id": str(uuid.uuid4()),
        "item_type": request.item_type,
        "item_id": request.item_id,
        "event_id": event_id,  # Event ID'yi ayrıca sakla
        "requester_id": user_id,
        "provider_id": details["provider_id"],
        "total_amount": total_amount,
        "cancellation_fee": cancellation_fee,
        "refund_amount": refund_amount,
        # ✅ YENİ: Kademeli iptal bilgileri
        "cancellation_tier": tier_info["tier"],
        "tier_description": tier_info["description"],
        "refund_rate": tier_info["refund_rate"] * 100,
        "penalty_rate": tier_info["penalty_rate"] * 100,
        # ✅ YENİ: Kesinti dağılımı
        "system_commission": system_commission,
        "provider_amount": provider_amount,
        # ✅ YENİ: Etkinlik mi, güven puanı cezası
        "is_event": is_event,
        "trust_penalty": tier_info.get("trust_penalty", 0),
        # Diğer bilgiler
        "reason": request.reason,
        "status": "pending",
        "title": details["title"],
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    await db.cancellation_requests.insert_one(cancellation_request)
    
    # ✅ Response için _id'yi temizle (MongoDB tarafından eklenir)
    if '_id' in cancellation_request:
        del cancellation_request['_id']
    
    logger.info(f"✅ Cancellation request created with event_id: {event_id}, tier: {tier_info['tier']}, is_event: {is_event}")
    
    # Get requester name
    requester = await db.users.find_one({"id": user_id})
    requester_name = requester.get("full_name", "Kullanıcı") if requester else "Kullanıcı"
    
    # ✅ Bildirim mesajını kademeli sisteme göre oluştur
    tier_text = tier_info["description"]
    if cancellation_fee > 0:
        notification_message = f"{requester_name} '{details['title']}' için iptal talebinde bulundu. ({tier_text}) Kesinti: ₺{cancellation_fee:.2f}, İade: ₺{refund_amount:.2f}"
    else:
        notification_message = f"{requester_name} '{details['title']}' için iptal talebinde bulundu. ({tier_text}) Tam iade: ₺{total_amount:.2f}"
    
    # Send notification to provider
    await send_notification(
        details["provider_id"],
        "🔴 İptal Talebi",
        notification_message,
        "cancellation_request",
        {
            "cancellation_request_id": cancellation_request["id"],
            "item_type": request.item_type,
            "item_id": request.item_id,
            "cancellation_tier": tier_info["tier"]
        }
    )
    
    # Send notification to admins
    await send_admin_notification(
        "📋 Yeni İptal Talebi",
        notification_message,
        {
            "cancellation_request_id": cancellation_request["id"],
            "requester_id": user_id,
            "provider_id": details["provider_id"],
            "cancellation_tier": tier_info["tier"]
        }
    )
    
    logger.info(f"✅ Cancellation request created: {cancellation_request['id']}")
    
    return {
        "success": True,
        "message": "İptal talebiniz gönderildi",
        "cancellation_request": cancellation_request,
        "fee_info": {
            "total_amount": total_amount,
            "cancellation_fee": cancellation_fee,
            "refund_amount": refund_amount,
            "cancellation_tier": tier_info["tier"],
            "tier_description": tier_info["description"],
            "refund_rate": tier_info["refund_rate"] * 100,
            "penalty_rate": tier_info["penalty_rate"] * 100,
            "system_commission": system_commission,
            "provider_amount": provider_amount
        }
    }


@router.get("")
async def get_my_cancellation_requests(
    current_user: dict = Depends(get_current_user)
):
    """Get cancellation requests for current user (as requester or provider)"""
    global db
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    user_id = current_user["id"]
    
    requests_list = []
    cursor = db.cancellation_requests.find({
        "$or": [
            {"requester_id": user_id},
            {"provider_id": user_id}
        ]
    }).sort("created_at", -1)
    
    async for req in cursor:
        req.pop("_id", None)
        requester = await db.users.find_one({"id": req.get("requester_id")})
        provider = await db.users.find_one({"id": req.get("provider_id")})
        req["requester_name"] = requester.get("full_name") if requester else "Bilinmeyen"
        req["provider_name"] = provider.get("full_name") if provider else "Bilinmeyen"
        req["is_requester"] = req["requester_id"] == user_id
        requests_list.append(req)
    
    return {"success": True, "requests": requests_list}


@router.get("/pending")
async def get_pending_cancellation_requests(
    current_user: dict = Depends(get_current_user)
):
    """Get pending cancellation requests where user is the provider"""
    global db
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    user_id = current_user["id"]
    
    requests_list = []
    cursor = db.cancellation_requests.find({
        "provider_id": user_id,
        "status": "pending"
    }).sort("created_at", -1)
    
    async for req in cursor:
        req.pop("_id", None)
        requester = await db.users.find_one({"id": req.get("requester_id")})
        req["requester_name"] = requester.get("full_name") if requester else "Bilinmeyen"
        requests_list.append(req)
    
    return {"success": True, "requests": requests_list}


@router.put("/{request_id}/accept")
async def accept_cancellation_request(
    request_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Accept a cancellation request - KADEMELİ İPTAL SİSTEMİ ile kesinti dağılımı"""
    global db
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    user_id = current_user["id"]
    
    cancel_req = await db.cancellation_requests.find_one({"id": request_id})
    if not cancel_req:
        raise HTTPException(status_code=404, detail="İptal talebi bulunamadı")
    
    if cancel_req["provider_id"] != user_id:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    if cancel_req["status"] != "pending":
        raise HTTPException(status_code=400, detail="Bu talep zaten işlenmiş")
    
    # Update cancellation request status
    await db.cancellation_requests.update_one(
        {"id": request_id},
        {
            "$set": {
                "status": "accepted",
                "accepted_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    )
    
    # Cancel the actual item
    item_type = cancel_req["item_type"]
    item_id = cancel_req["item_id"]
    
    if item_type == "reservation":
        await db.reservations.update_one(
            {"id": item_id},
            {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow().isoformat()}}
        )
        await db.calendar_items.delete_many({"reservation_id": item_id})
        
    elif item_type == "facility_reservation":
        await db.facility_reservations.update_one(
            {"id": item_id},
            {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow().isoformat()}}
        )
        await db.calendar_items.delete_many({"reservation_id": item_id})
        
    elif item_type == "event_participation":
        # Cancellation request'ten event_id'yi al
        event_id = cancel_req.get("event_id") or item_id
        
        # item_id participation ID veya event ID olabilir
        participation = await db.participations.find_one({"id": item_id})
        
        if participation:
            # Participation kaydı varsa güncelle
            await db.participations.update_one(
                {"id": item_id},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow().isoformat()}}
            )
            event_id = participation.get("event_id") or event_id
        
        # Event_participants koleksiyonundaki kaydı da iptal et
        ep_result = await db.event_participants.update_many(
            {
                "user_id": cancel_req["requester_id"],
                "event_id": event_id
            },
            {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow().isoformat()}}
        )
        logger.info(f"📤 Cancelled {ep_result.modified_count} event_participants records for user {cancel_req['requester_id']}")
        
        # Event'in participants listesinden kullanıcıyı çıkar
        event = await db.events.find_one({"id": event_id})
        if event:
            participants = event.get("participants", [])
            new_participants = []
            for p in participants:
                if isinstance(p, str) and p != cancel_req["requester_id"]:
                    new_participants.append(p)
                elif isinstance(p, dict) and p.get("id") != cancel_req["requester_id"] and p.get("user_id") != cancel_req["requester_id"]:
                    new_participants.append(p)
            
            await db.events.update_one(
                {"id": event_id},
                {"$set": {"participants": new_participants}}
            )
            logger.info(f"📤 Removed user {cancel_req['requester_id']} from event {event_id} participants")
        
        # Event katılımcı sayısını güncelle
        if event_id:
            await db.events.update_one(
                {"id": event_id},
                {"$inc": {"current_participants": -1}}
            )
        
        # Kullanıcının takviminden etkinliği sil
        delete_result = await db.calendar_items.delete_many({
            "event_id": event_id, 
            "user_id": cancel_req["requester_id"]
        })
        
        logger.info(f"📅 Removed {delete_result.deleted_count} calendar items for event {event_id} from user {cancel_req['requester_id']}'s calendar")
    
    # ✅ YENİ: Kademeli kesinti dağılımı ile komisyon kaydı
    cancellation_fee = cancel_req.get("cancellation_fee", 0)
    is_event = cancel_req.get("is_event", False)
    
    # Etkinlik ise farklı komisyon oranı kullan
    if is_event:
        system_commission = cancel_req.get("system_commission", cancellation_fee * EVENT_SYSTEM_COMMISSION_RATE)
        provider_amount = cancel_req.get("provider_amount", cancellation_fee * EVENT_ORGANIZER_RATE)
        commission_desc = "Etkinlik iptal komisyonu (Sistem payı %30)"
        provider_desc = "Etkinlik iptal kesintisi (Organizatör payı %70)"
    else:
        system_commission = cancel_req.get("system_commission", cancellation_fee * SYSTEM_COMMISSION_RATE)
        provider_amount = cancel_req.get("provider_amount", cancellation_fee - system_commission)
        commission_desc = "İptal komisyonu (Sistem payı %13)"
        provider_desc = "İptal kesintisi (Sağlayıcı payı %87)"
    
    cancellation_tier = cancel_req.get("cancellation_tier", "unknown")
    trust_penalty = cancel_req.get("trust_penalty", 0)
    
    # ✅ YENİ: Güven puanı cezası uygula (sadece etkinlikler için ve ceza varsa)
    if is_event and trust_penalty > 0:
        await apply_trust_penalty(
            cancel_req["requester_id"],
            trust_penalty,
            f"Etkinlik iptali ({cancellation_tier}): {cancel_req['title']}"
        )
        logger.info(f"⚠️ Trust penalty applied: -{trust_penalty} points to user {cancel_req['requester_id']}")
    
    # Eğer kesinti varsa, sistem komisyonunu kaydet
    if cancellation_fee > 0:
        # Sistem komisyonunu kaydet
        await record_commission(
            system_commission,
            f"{commission_desc} - {cancel_req['title']} - {cancellation_tier}",
            item_type,
            item_id,
            cancel_req["requester_id"]
        )
        
        # Sağlayıcı payını kaydet
        provider_transaction = {
            "id": str(uuid.uuid4()),
            "type": "cancellation_provider_share",
            "amount": provider_amount,
            "description": f"{provider_desc} - {cancel_req['title']} - {cancellation_tier}",
            "item_type": item_type,
            "item_id": item_id,
            "user_id": cancel_req["provider_id"],
            "cancellation_request_id": request_id,
            "cancellation_tier": cancellation_tier,
            "is_event": is_event,
            "created_at": datetime.utcnow().isoformat()
        }
        await db.provider_transactions.insert_one(provider_transaction)
        logger.info(f"💰 Provider share recorded: {provider_amount} TL to {cancel_req['provider_id']}")
    
    # Get provider name
    provider = await db.users.find_one({"id": user_id})
    provider_name = provider.get("full_name", "Sağlayıcı") if provider else "Sağlayıcı"
    
    # ✅ Kademeli sisteme göre bildirim mesajı
    tier_text = cancel_req.get("tier_description", "")
    refund_amount = cancel_req.get("refund_amount", 0)
    
    if cancellation_fee > 0:
        notification_message = f"{provider_name} iptal talebinizi kabul etti. ({tier_text}) ₺{refund_amount:.2f} iade edilecektir. (₺{cancellation_fee:.2f} kesinti uygulandı)"
        if trust_penalty > 0:
            notification_message += f" Güven puanınız {trust_penalty} puan düşürüldü."
    else:
        notification_message = f"{provider_name} iptal talebinizi kabul etti. ₺{cancel_req.get('total_amount', 0):.2f} tam iade yapılacaktır."
    
    # Send notification to requester
    await send_notification(
        cancel_req["requester_id"],
        "✅ İptal Talebi Kabul Edildi",
        notification_message,
        "cancellation_accepted",
        {
            "cancellation_request_id": request_id,
            "cancellation_tier": cancellation_tier,
            "refund_amount": refund_amount,
            "cancellation_fee": cancellation_fee,
            "trust_penalty": trust_penalty
        }
    )
    
    # Send notification to admins
    admin_message = f"{provider_name} '{cancel_req['title']}' için iptal talebini kabul etti. ({tier_text}) Kesinti: ₺{cancellation_fee:.2f} (Sistem: ₺{system_commission:.2f}, {'Organizatör' if is_event else 'Sağlayıcı'}: ₺{provider_amount:.2f})"
    if trust_penalty > 0:
        admin_message += f" Kullanıcıya -{trust_penalty} güven puanı cezası verildi."
    
    await send_admin_notification(
        "✅ İptal Talebi Kabul Edildi",
        admin_message,
        {
            "cancellation_request_id": request_id,
            "cancellation_tier": cancellation_tier,
            "trust_penalty": trust_penalty
        }
    )
    
    logger.info(f"✅ Cancellation request accepted: {request_id}, tier: {cancellation_tier}, is_event: {is_event}")
    
    return {
        "success": True,
        "message": "İptal talebi kabul edildi",
        "refund_amount": refund_amount,
        "commission": cancellation_fee,
        "system_commission": system_commission,
        "provider_amount": provider_amount,
        "cancellation_tier": cancellation_tier
    }


@router.put("/{request_id}/reject")
async def reject_cancellation_request(
    request_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Reject a cancellation request"""
    global db
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    user_id = current_user["id"]
    
    cancel_req = await db.cancellation_requests.find_one({"id": request_id})
    if not cancel_req:
        raise HTTPException(status_code=404, detail="İptal talebi bulunamadı")
    
    if cancel_req["provider_id"] != user_id:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    if cancel_req["status"] != "pending":
        raise HTTPException(status_code=400, detail="Bu talep zaten işlenmiş")
    
    # Update cancellation request status
    await db.cancellation_requests.update_one(
        {"id": request_id},
        {
            "$set": {
                "status": "rejected",
                "rejected_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    )
    
    # Get provider name
    provider = await db.users.find_one({"id": user_id})
    provider_name = provider.get("full_name", "Sağlayıcı") if provider else "Sağlayıcı"
    
    # Send notification to requester
    await send_notification(
        cancel_req["requester_id"],
        "❌ İptal Talebi Reddedildi",
        f"{provider_name} iptal talebinizi reddetti.",
        "cancellation_rejected",
        {"cancellation_request_id": request_id}
    )
    
    logger.info(f"❌ Cancellation request rejected: {request_id}")
    
    return {"success": True, "message": "İptal talebi reddedildi"}


@router.post("/force-cancel")
async def force_cancel(
    request: CancellationRequestCreate,
    current_user: dict = Depends(get_current_user)
):
    """Force cancel by provider - results in 1-star penalty and full refund to customer"""
    global db
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    user_id = current_user["id"]
    
    # Get item details
    details = await get_item_details(request.item_type, request.item_id)
    if not details:
        raise HTTPException(status_code=404, detail="Öğe bulunamadı")
    
    # Check if user is the provider
    if details["provider_id"] != user_id:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    item_type = request.item_type
    item_id = request.item_id
    
    # Cancel the item
    if item_type == "reservation":
        await db.reservations.update_one(
            {"id": item_id},
            {"$set": {"status": "cancelled", "cancelled_by": "provider", "cancelled_at": datetime.utcnow().isoformat()}}
        )
        await db.calendar_items.delete_many({"reservation_id": item_id})
        
    elif item_type == "facility_reservation":
        await db.facility_reservations.update_one(
            {"id": item_id},
            {"$set": {"status": "cancelled", "cancelled_by": "provider", "cancelled_at": datetime.utcnow().isoformat()}}
        )
        await db.calendar_items.delete_many({"reservation_id": item_id})
        
    elif item_type == "event_participation":
        # This is when organizer cancels - different logic
        event = details.get("event")
        if event:
            await db.events.update_one(
                {"id": event["id"]},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow().isoformat()}}
            )
            # Cancel all participations
            await db.participations.update_many(
                {"event_id": event["id"]},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow().isoformat()}}
            )
            await db.calendar_items.delete_many({"event_id": event["id"]})
    
    # Create automatic 1-star review as penalty
    await create_automatic_review(
        target_user_id=user_id,
        reviewer_id=details["requester_id"],
        item_type=item_type,
        item_id=item_id
    )
    
    # Get provider name
    provider = await db.users.find_one({"id": user_id})
    provider_name = provider.get("full_name", "Sağlayıcı") if provider else "Sağlayıcı"
    
    # Send notification to customer about full refund
    await send_notification(
        details["requester_id"],
        "⚠️ Rezervasyon/Etkinlik İptal Edildi",
        f"{provider_name} '{details['title']}' için tek taraflı iptal yaptı. ₺{details['amount']:.2f} tam iade yapılacaktır.",
        "force_cancellation",
        {"item_type": item_type, "item_id": item_id}
    )
    
    # Send notification to admins
    await send_admin_notification(
        "⚠️ Tek Taraflı İptal",
        f"{provider_name} '{details['title']}' için tek taraflı iptal yaptı. Müşteriye tam iade: ₺{details['amount']:.2f}. Otomatik 1 yıldız cezası verildi.",
        {
            "provider_id": user_id,
            "requester_id": details["requester_id"],
            "item_type": item_type,
            "item_id": item_id
        }
    )
    
    logger.info(f"⚠️ Force cancellation by provider: {user_id} for {item_type}/{item_id}")
    
    return {
        "success": True,
        "message": "İptal edildi. Müşteriye tam iade yapılacak. 1 yıldız ceza puanı hesabınıza eklendi.",
        "refund_amount": details["amount"],
        "penalty_applied": True
    }


@router.get("/check-eligibility/{item_type}/{item_id}")
async def check_cancellation_eligibility(
    item_type: str,
    item_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Check if item is eligible for cancellation request - ETKİNLİK veya REZERVASYON KADEMELİ İPTAL SİSTEMİ"""
    global db
    
    logger.info(f"🔍 CHECK ELIGIBILITY - item_type: {item_type}, item_id: {item_id}")
    logger.info(f"🔍 Current user: {current_user}")
    
    if db is None:
        logger.error("❌ Database not initialized!")
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    user_id = current_user["id"]
    logger.info(f"🔍 User ID: {user_id}")
    
    details = await get_item_details(item_type, item_id)
    logger.info(f"🔍 Details: {details}")
    
    if not details:
        logger.warning(f"❌ Item not found: {item_type}/{item_id}")
        return {"eligible": False, "reason": "Öğe bulunamadı"}
    
    # ✅ ETKİNLİK/KAMP TESPİTİ - item_type veya event bilgisinden
    is_event = item_type == "event_participation" or details.get("is_event_direct", False)
    event_data = details.get("event")
    
    # is_event_direct durumunda requester_id'yi current user olarak set et
    if details.get("is_event_direct"):
        # Event'in participants listesinde kullanıcı var mı kontrol et
        event = details.get("event")
        if event:
            participants = event.get("participants", [])
            user_in_participants = False
            for p in participants:
                if isinstance(p, str) and p == user_id:
                    user_in_participants = True
                    break
                elif isinstance(p, dict) and (p.get("id") == user_id or p.get("user_id") == user_id):
                    user_in_participants = True
                    break
            
            if not user_in_participants:
                return {"eligible": False, "reason": "Bu etkinliğe katılmamışsınız"}
            
            # Requester ID'yi set et
            details["requester_id"] = user_id
            details["item"]["user_id"] = user_id
            details["item"]["status"] = "joined"  # Katılım durumu
    
    # Check if item status is valid (must be paid/confirmed/joined)
    item = details["item"]
    valid_statuses = ["paid", "confirmed", "approved", "completed", "joined"]
    
    logger.info(f"🔍 Item status: {item.get('status')}")
    logger.info(f"🔍 Valid statuses: {valid_statuses}")
    logger.info(f"🔍 Requester ID from details: {details.get('requester_id')}")
    logger.info(f"🔍 Provider ID from details: {details.get('provider_id')}")
    logger.info(f"🔍 Current user ID: {user_id}")
    logger.info(f"🔍 Is Event/Camp: {is_event}")
    
    if item.get("status") not in valid_statuses:
        logger.warning(f"❌ Status not valid: {item.get('status')}")
        return {"eligible": False, "reason": "Bu öğe iptal edilebilir durumda değil"}
    
    # Check if user is requester (customer)
    is_requester = details["requester_id"] == user_id
    is_provider = details["provider_id"] == user_id
    
    logger.info(f"🔍 is_requester: {is_requester}, is_provider: {is_provider}")
    
    if not is_requester and not is_provider:
        logger.warning(f"❌ User is neither requester nor provider")
        return {"eligible": False, "reason": "Bu işlem için yetkiniz yok"}
    
    # Check existing cancellation request
    existing = await db.cancellation_requests.find_one({
        "item_type": item_type,
        "item_id": item_id,
        "status": {"$in": ["pending", "accepted"]}
    })
    if existing:
        return {"eligible": False, "reason": "Bu öğe için zaten bir iptal talebi var", "existing_request": existing["id"]}
    
    # ✅ YENİ KADEMELİ İPTAL SİSTEMİ - Etkinlik veya Rezervasyon
    can_cancel, error_msg, tier_info = can_request_cancellation(details["start_time"], is_event=is_event)
    
    if not can_cancel:
        return {"eligible": False, "reason": error_msg}
    
    # Toplam tutarı al
    total_amount = details["amount"] or 0
    
    if is_requester:
        # ✅ Müşteri için kademeli iptal hesaplaması
        refund_info = calculate_refund_amounts(total_amount, tier_info)
        
        logger.info(f"💰 Cancellation tier: {tier_info['tier']}")
        logger.info(f"💰 Is Event: {is_event}")
        logger.info(f"💰 Refund rate: {tier_info['refund_rate']*100}%")
        logger.info(f"💰 Penalty rate: {tier_info['penalty_rate']*100}%")
        logger.info(f"💰 Refund amount: {refund_info['refund_amount']}")
        logger.info(f"💰 Penalty amount: {refund_info['penalty_amount']}")
        
        # ✅ Etkinlik için devir hakkı kontrolü
        can_transfer = False
        if is_event and tier_info.get("hours_until_start", 0) >= 24:
            can_transfer = True
        
        return {
            "eligible": True,
            "is_requester": True,
            "is_provider": False,
            "is_event": is_event,
            # ✅ Kademeli iptal bilgileri
            "cancellation_tier": tier_info["tier"],
            "tier_description": tier_info["description"],
            "hours_until_start": tier_info.get("hours_until_start", 0),
            "days_until_start": tier_info.get("days_until_start", tier_info.get("hours_until_start", 0) / 24),
            # ✅ Kesinti ve iade oranları (yüzde olarak)
            "refund_rate": refund_info["refund_rate"],  # 100, 75, 50, 0
            "penalty_rate": refund_info["penalty_rate"],  # 0, 25, 50, 100
            # ✅ Tutar hesaplamaları
            "total_amount": total_amount,
            "refund_amount": refund_info["refund_amount"],
            "cancellation_fee": refund_info["penalty_amount"],
            # ✅ Kesinti dağılımı (etkinlik: %30/%70, rezervasyon: %13/%87)
            "system_commission": refund_info["system_commission"],
            "provider_amount": refund_info["provider_amount"],
            # ✅ Güven puanı cezası (sadece etkinlikler için)
            "trust_penalty": tier_info.get("trust_penalty", 0),
            # ✅ Devir hakkı (sadece etkinlikler için, 24 saat önce)
            "can_transfer": can_transfer,
            # ✅ Uyarı mesajları
            "warning_message": _get_cancellation_warning(tier_info["tier"], refund_info, is_event)
        }
    else:
        # Provider can force cancel (always, with penalty)
        return {
            "eligible": True,
            "is_requester": False,
            "is_provider": True,
            "force_cancel_penalty": "1 yıldız otomatik değerlendirme",
            "full_refund_to_customer": total_amount
        }


def _get_cancellation_warning(tier: str, refund_info: dict, is_event: bool = False) -> str:
    """İptal kategorisine göre uyarı mesajı oluştur - Etkinlik veya Rezervasyon"""
    
    if is_event:
        # ✅ ETKİNLİK/KAMP İPTAL MESAJLARI (gün bazlı)
        if tier == "7d_plus":
            return "✅ 7 günden önce iptal: Tam iade alacaksınız, kesinti yapılmayacak."
        elif tier == "3d_7d":
            return f"⚠️ 3-7 gün arası iptal: %25 kesinti uygulanacak. ₺{refund_info['penalty_amount']:.2f} kesinti, ₺{refund_info['refund_amount']:.2f} iade alacaksınız."
        elif tier == "1d_3d":
            return f"🟠 1-3 gün arası iptal: %50 kesinti uygulanacak. ₺{refund_info['penalty_amount']:.2f} kesinti, ₺{refund_info['refund_amount']:.2f} iade alacaksınız. Güven puanınız düşecektir."
        elif tier == "24h_minus":
            return f"🔴 24 saatten az kala iptal: İade YOKTUR. ₺{refund_info['penalty_amount']:.2f} kesinti uygulanacak. Güven puanınız önemli ölçüde düşecektir."
        elif tier == "no_show":
            return f"❌ Etkinliğe katılmadınız (No-show): İade YOKTUR. Güven puanınız ciddi şekilde düşecektir."
        else:
            return "❌ Geçmiş tarihlere iptal talebi yapılamaz."
    else:
        # REZERVASYON İPTAL MESAJLARI (saat bazlı)
        if tier == "24h_plus":
            return "✅ 24 saatten önce iptal: Tam iade alacaksınız, kesinti yapılmayacak."
        elif tier == "6h_24h":
            return f"⚠️ 6-24 saat arası iptal: %25 kesinti uygulanacak. ₺{refund_info['penalty_amount']:.2f} kesinti, ₺{refund_info['refund_amount']:.2f} iade alacaksınız."
        elif tier == "6h_minus":
            return f"🔴 6 saatten az kala iptal: %50 kesinti uygulanacak. ₺{refund_info['penalty_amount']:.2f} kesinti, ₺{refund_info['refund_amount']:.2f} iade alacaksınız."
        elif tier == "no_show":
            return f"❌ Rezervasyona katılmadınız (No-show): İade YOKTUR."
        else:
            return "❌ Geçmiş tarihlere iptal talebi yapılamaz."



# ============================================================================
# KATILIMCI DEĞİŞİKLİĞİ (TRANSFER) ENDPOINTLERİ
# ============================================================================

class TransferRequest(BaseModel):
    event_id: str
    new_user_phone: str  # Yeni katılımcının telefon numarası


@router.post("/transfer-participation")
async def transfer_participation(
    request: TransferRequest,
    current_user: dict = Depends(get_current_user)
):
    """Etkinlik katılımını başka bir kullanıcıya devret - 24 saat öncesine kadar ücretsiz"""
    global db
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    user_id = current_user["id"]
    
    logger.info(f"🔄 TRANSFER REQUEST - event_id: {request.event_id}, from: {user_id}, to_phone: {request.new_user_phone}")
    
    # Etkinliği bul
    event = await db.events.find_one({"id": request.event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Kullanıcının katılımcı olup olmadığını kontrol et
    participants = event.get("participants", [])
    user_in_event = False
    for p in participants:
        if isinstance(p, str) and p == user_id:
            user_in_event = True
            break
        elif isinstance(p, dict) and (p.get("id") == user_id or p.get("user_id") == user_id):
            user_in_event = True
            break
    
    if not user_in_event:
        raise HTTPException(status_code=403, detail="Bu etkinliğe katılmamışsınız, devir yapamazsınız")
    
    # Etkinlik başlangıç zamanını kontrol et
    start_time = event.get("start_date") or event.get("date")
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    
    now = datetime.utcnow()
    if start_time.tzinfo:
        now = now.replace(tzinfo=start_time.tzinfo)
    
    time_until_start = start_time - now
    hours_until_start = time_until_start.total_seconds() / 3600
    
    # 24 saatten az kala devir yapılamaz
    if hours_until_start < 24:
        raise HTTPException(status_code=400, detail="Etkinliğe 24 saatten az kaldı, devir yapılamaz. İptal talebi gönderebilirsiniz.")
    
    # Yeni kullanıcıyı bul
    # Telefon numarasını temizle
    clean_phone = request.new_user_phone.replace(" ", "").replace("-", "")
    if not clean_phone.startswith("+"):
        if clean_phone.startswith("0"):
            clean_phone = "+9" + clean_phone
        else:
            clean_phone = "+90" + clean_phone
    
    new_user = await db.users.find_one({"phone": clean_phone})
    if not new_user:
        raise HTTPException(status_code=404, detail="Bu telefon numarasıyla kayıtlı kullanıcı bulunamadı")
    
    new_user_id = new_user["id"]
    
    # Yeni kullanıcı zaten katılımcı mı?
    for p in participants:
        p_id = p if isinstance(p, str) else (p.get("id") or p.get("user_id"))
        if p_id == new_user_id:
            raise HTTPException(status_code=400, detail="Bu kullanıcı zaten etkinliğe katılmış")
    
    # Katılımcıyı değiştir
    new_participants = []
    for p in participants:
        if isinstance(p, str):
            if p == user_id:
                new_participants.append(new_user_id)
            else:
                new_participants.append(p)
        elif isinstance(p, dict):
            if p.get("id") == user_id or p.get("user_id") == user_id:
                new_participants.append({"id": new_user_id, "user_type": p.get("user_type", "player")})
            else:
                new_participants.append(p)
    
    # Event'i güncelle
    await db.events.update_one(
        {"id": request.event_id},
        {"$set": {"participants": new_participants}}
    )
    
    # Event_participants koleksiyonunu güncelle
    await db.event_participants.update_one(
        {"event_id": request.event_id, "user_id": user_id},
        {"$set": {"status": "transferred", "transferred_to": new_user_id, "transferred_at": datetime.utcnow().isoformat()}}
    )
    
    # Yeni katılımcı için kayıt oluştur
    new_participation = {
        "id": str(uuid.uuid4()),
        "event_id": request.event_id,
        "user_id": new_user_id,
        "status": "confirmed",
        "transferred_from": user_id,
        "created_at": datetime.utcnow().isoformat()
    }
    await db.event_participants.insert_one(new_participation)
    
    # Eski kullanıcının takviminden sil
    await db.calendar_items.delete_many({
        "event_id": request.event_id,
        "user_id": user_id
    })
    
    # Yeni kullanıcının takvimine ekle
    calendar_item = {
        "id": str(uuid.uuid4()),
        "user_id": new_user_id,
        "event_id": request.event_id,
        "title": event.get("title", "Etkinlik"),
        "date": start_time.isoformat() if hasattr(start_time, 'isoformat') else start_time,
        "type": "event",
        "created_at": datetime.utcnow().isoformat()
    }
    await db.calendar_items.insert_one(calendar_item)
    
    # Transfer kaydı oluştur
    transfer_log = {
        "id": str(uuid.uuid4()),
        "event_id": request.event_id,
        "from_user_id": user_id,
        "to_user_id": new_user_id,
        "event_title": event.get("title", ""),
        "created_at": datetime.utcnow().isoformat()
    }
    await db.participation_transfers.insert_one(transfer_log)
    
    # Kullanıcı isimlerini al
    old_user = await db.users.find_one({"id": user_id})
    old_user_name = old_user.get("full_name", "Kullanıcı") if old_user else "Kullanıcı"
    new_user_name = new_user.get("full_name", "Kullanıcı")
    
    # Eski kullanıcıya bildirim
    await send_notification(
        user_id,
        "🔄 Katılım Devredildi",
        f"'{event.get('title', 'Etkinlik')}' etkinliğindeki yerinizi {new_user_name} adlı kullanıcıya devrettiniz.",
        "participation_transferred",
        {"event_id": request.event_id, "to_user_id": new_user_id}
    )
    
    # Yeni kullanıcıya bildirim
    await send_notification(
        new_user_id,
        "🎉 Yeni Etkinlik Katılımı",
        f"{old_user_name} size '{event.get('title', 'Etkinlik')}' etkinliğindeki yerini devretti. Takviminize eklendi!",
        "participation_received",
        {"event_id": request.event_id, "from_user_id": user_id}
    )
    
    # Organizatöre bildirim
    organizer_id = event.get("organizer_id") or event.get("created_by")
    if organizer_id:
        await send_notification(
            organizer_id,
            "🔄 Katılımcı Değişikliği",
            f"'{event.get('title', 'Etkinlik')}' etkinliğinde {old_user_name} yerini {new_user_name} adlı kullanıcıya devretti.",
            "participant_changed",
            {"event_id": request.event_id, "old_user_id": user_id, "new_user_id": new_user_id}
        )
    
    logger.info(f"✅ Participation transferred from {user_id} to {new_user_id} for event {request.event_id}")
    
    return {
        "success": True,
        "message": f"Katılımınız {new_user_name} adlı kullanıcıya başarıyla devredildi.",
        "transfer_log_id": transfer_log["id"],
        "new_participant": {
            "id": new_user_id,
            "name": new_user_name
        }
    }


@router.get("/can-transfer/{event_id}")
async def check_transfer_eligibility(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Katılımcı değişikliği yapılabilir mi kontrol et"""
    global db
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    user_id = current_user["id"]
    
    # Etkinliği bul
    event = await db.events.find_one({"id": event_id})
    if not event:
        return {"can_transfer": False, "reason": "Etkinlik bulunamadı"}
    
    # Kullanıcının katılımcı olup olmadığını kontrol et
    participants = event.get("participants", [])
    user_in_event = False
    for p in participants:
        if isinstance(p, str) and p == user_id:
            user_in_event = True
            break
        elif isinstance(p, dict) and (p.get("id") == user_id or p.get("user_id") == user_id):
            user_in_event = True
            break
    
    if not user_in_event:
        return {"can_transfer": False, "reason": "Bu etkinliğe katılmamışsınız"}
    
    # Etkinlik başlangıç zamanını kontrol et
    start_time = event.get("start_date") or event.get("date")
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    
    now = datetime.utcnow()
    if start_time.tzinfo:
        now = now.replace(tzinfo=start_time.tzinfo)
    
    time_until_start = start_time - now
    hours_until_start = time_until_start.total_seconds() / 3600
    
    if hours_until_start < 24:
        return {
            "can_transfer": False,
            "reason": "Etkinliğe 24 saatten az kaldı, devir yapılamaz",
            "hours_until_start": hours_until_start
        }
    
    return {
        "can_transfer": True,
        "hours_until_start": hours_until_start,
        "event_title": event.get("title", "Etkinlik"),
        "message": "Katılımınızı başka bir kullanıcıya devredebilirsiniz (ücretsiz)"
    }
