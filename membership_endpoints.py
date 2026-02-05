from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import uuid
import logging
import os

from auth import get_current_user
from iyzico_service import iyzico_service
from models import NotificationType, NotificationRelatedType

router = APIRouter()
logger = logging.getLogger(__name__)

# Pydantic Models
class MembershipCreate(BaseModel):
    facility_id: str
    membership_type: str  # "daily", "monthly", "yearly"
    promo_code: Optional[str] = None

class MembershipRenew(BaseModel):
    membership_type: str
    promo_code: Optional[str] = None

class PromoCodeCreate(BaseModel):
    code: str
    facility_id: Optional[str] = None  # None = all facilities
    discount_percentage: float  # 0-100
    valid_until: datetime
    usage_limit: Optional[int] = None

class PromoCodeValidate(BaseModel):
    code: str
    facility_id: str
    membership_type: str

# Helper Functions
def calculate_end_date(start_date: datetime, membership_type: str) -> datetime:
    """Calculate membership end date based on type"""
    if membership_type == "daily":
        return start_date + timedelta(days=1)
    elif membership_type == "monthly":
        return start_date + timedelta(days=30)
    elif membership_type == "yearly":
        return start_date + timedelta(days=365)
    else:
        raise ValueError(f"Invalid membership type: {membership_type}")

def get_membership_price(facility: dict, membership_type: str) -> float:
    """Get membership price from facility"""
    if membership_type == "daily":
        return facility.get("daily_membership_fee", 0)
    elif membership_type == "monthly":
        return facility.get("monthly_membership_fee", 0)
    elif membership_type == "yearly":
        return facility.get("yearly_membership_fee", 0)
    else:
        raise ValueError(f"Invalid membership type: {membership_type}")

async def apply_promo_code(db, promo_code: str, facility_id: str, original_price: float) -> tuple:
    """Apply promo code and return (discounted_price, promo_details)"""
    promo = await db.promo_codes.find_one({
        "code": promo_code,
        "is_active": True,
        "valid_until": {"$gte": datetime.utcnow()}
    })
    
    if not promo:
        raise HTTPException(status_code=400, detail="Geçersiz veya süresi dolmuş promosyon kodu")
    
    # Check if promo is for this facility or all facilities
    if promo.get("facility_id") and promo["facility_id"] != facility_id:
        raise HTTPException(status_code=400, detail="Bu promosyon kodu bu tesis için geçerli değil")
    
    # Check usage limit
    if promo.get("usage_limit"):
        usage_count = promo.get("usage_count", 0)
        if usage_count >= promo["usage_limit"]:
            raise HTTPException(status_code=400, detail="Promosyon kodu kullanım limiti doldu")
    
    # Calculate discount
    discount_percentage = promo["discount_percentage"]
    discount_amount = (original_price * discount_percentage) / 100
    final_price = max(0, original_price - discount_amount)
    
    return final_price, promo


# Endpoints
@router.get("/memberships/facilities")
async def get_membership_facilities(
    city: Optional[str] = None,
    sport: Optional[str] = None
):
    """Get facilities that allow membership (approved + allow_membership = true)"""
    from motor.motor_asyncio import AsyncIOMotorClient
    import os
    
    MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    DB_NAME = os.getenv("DB_NAME", "sports_management")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    query = {
        "status": "approved",
        "is_published": True,
        "allow_membership": True
    }
    
    if city:
        query["city"] = city
    
    if sport:
        query["sports.name"] = sport
    
    facilities = await db.facilities.find(query).to_list(100)
    
    for facility in facilities:
        facility.pop("_id", None)
        
        # Calculate min membership price
        prices = []
        if facility.get("daily_membership_fee"):
            prices.append(facility["daily_membership_fee"])
        if facility.get("monthly_membership_fee"):
            prices.append(facility["monthly_membership_fee"])
        if facility.get("yearly_membership_fee"):
            prices.append(facility["yearly_membership_fee"])
        
        facility["min_membership_price"] = min(prices) if prices else 0
    
    return {"facilities": facilities, "total": len(facilities)}


@router.get("/facilities/{facility_id}/membership-details")
async def get_facility_membership_details(
    facility_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Get facility details for membership page with reviews"""
    db = request.app.state.db
    
    facility = await db.facilities.find_one({"id": facility_id})
    if not facility:
        raise HTTPException(status_code=404, detail="Tesis bulunamadı")
    
    if not facility.get("allow_membership"):
        raise HTTPException(status_code=403, detail="Bu tesis üyelik kabul etmiyor")
    
    facility.pop("_id", None)
    
    # Get reviews from users who are members or have reservations
    reviews = await db.reviews.find({
        "facility_id": facility_id,
        "is_approved": True
    }).sort("created_at", -1).limit(50).to_list(50)
    
    for review in reviews:
        review.pop("_id", None)
        # Get reviewer info
        reviewer = await db.users.find_one({"id": review["user_id"]})
        if reviewer:
            review["reviewer_name"] = reviewer.get("full_name", "Anonim")
    
    # Check if user already has active membership
    active_membership = await db.memberships.find_one({
        "user_id": current_user["id"],
        "facility_id": facility_id,
        "status": "active",
        "end_date": {"$gte": datetime.utcnow()}
    })
    
    return {
        "facility": facility,
        "reviews": reviews,
        "has_active_membership": active_membership is not None,
        "active_membership": active_membership
    }


@router.post("/memberships/create")
async def create_membership(
    membership_data: MembershipCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Create new membership and initialize payment"""
    db = request.app.state.db
    
    try:
        # Get facility
        facility = await db.facilities.find_one({"id": membership_data.facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        if not facility.get("allow_membership"):
            raise HTTPException(status_code=403, detail="Bu tesis üyelik kabul etmiyor")
        
        # Check for active membership
        active_membership = await db.memberships.find_one({
            "user_id": current_user["id"],
            "facility_id": membership_data.facility_id,
            "status": "active",
            "end_date": {"$gte": datetime.utcnow()}
        })
        
        if active_membership:
            raise HTTPException(status_code=400, detail="Bu tesiste zaten aktif üyeliğiniz var")
        
        # Get price
        original_price = get_membership_price(facility, membership_data.membership_type)
        if original_price <= 0:
            raise HTTPException(status_code=400, detail="Bu üyelik türü için fiyat belirlenmemiş")
        
        final_price = original_price
        promo_details = None
        
        # Apply promo code if provided
        if membership_data.promo_code:
            final_price, promo_details = await apply_promo_code(
                db, 
                membership_data.promo_code,
                membership_data.facility_id,
                original_price
            )
        
        # Calculate dates
        start_date = datetime.utcnow()
        end_date = calculate_end_date(start_date, membership_data.membership_type)
        
        # Create membership record
        membership_id = str(uuid.uuid4())
        membership = {
            "id": membership_id,
            "user_id": current_user["id"],
            "facility_id": membership_data.facility_id,
            "membership_type": membership_data.membership_type,
            "original_price": original_price,
            "final_price": final_price,
            "promo_code": membership_data.promo_code,
            "promo_details": promo_details["id"] if promo_details else None,
            "start_date": start_date,
            "end_date": end_date,
            "status": "pending_payment",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.memberships.insert_one(membership)
        
        # Update promo code usage
        if promo_details:
            await db.promo_codes.update_one(
                {"id": promo_details["id"]},
                {"$inc": {"usage_count": 1}}
            )
        
        logger.info(f"✅ Membership created: {membership_id} for user {current_user['id']}")
        
        # Get user for payment
        user = await db.users.find_one({"id": current_user["id"]})
        
        # Initialize Iyzico payment
        conversation_id = str(uuid.uuid4())
        payment_id = str(uuid.uuid4())
        
        # Create payment record
        payment_data_doc = {
            "id": payment_id,
            "user_id": current_user["id"],
            "related_type": "membership",
            "related_id": membership_id,
            "amount": final_price,
            "currency": "TRY",
            "status": "pending",
            "iyzico_conversation_id": conversation_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.payments.insert_one(payment_data_doc)
        
        # Initialize iyzico checkout form
        # Get backend base URL from environment (MUST be public URL for Iyzico callback)
        backend_base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:3000")
        callback_url = f"{backend_base_url}/api/memberships/payment-callback"
        
        logger.info(f"💳 İyzico callback URL: {callback_url}")
        logger.info(f"🌐 Backend base URL: {backend_base_url}")
        
        membership_type_tr = {
            "daily": "Günlük",
            "monthly": "Aylık",
            "yearly": "Yıllık"
        }.get(membership_data.membership_type, membership_data.membership_type)
        
        result = iyzico_service.initialize_checkout_form(
            user={
                'id': user['id'],
                'email': user['email'],
                'full_name': user['full_name'],
                'phone_number': user.get('phone', '+905000000000'),
                'tc_kimlik': user.get('tckn', '11111111111'),
                'created_at': user.get('created_at', datetime.utcnow())
            },
            amount=final_price,
            related_type='membership',
            related_id=membership_id,
            related_name=f"{facility['name']} - {membership_type_tr} Üyelik",
            callback_url=callback_url
        )
        
        if result.get('status') == 'success':
            # Update payment with iyzico token
            await db.payments.update_one(
                {"id": payment_id},
                {
                    "$set": {
                        "iyzico_token": result.get("token"),
                        "status": "init_3ds",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            # İyzico'dan gelen URL'i al (farklı key isimleri deneyebilir)
            payment_url = result.get("paymentPageUrl") or result.get("payment_page_url")
            logger.info(f"✅ Returning payment URL to frontend: {payment_url}")
            
            return {
                "success": True,
                "membership_id": membership_id,
                "payment_id": payment_id,
                "payment_page_url": payment_url,
                "facility_name": facility["name"],
                "membership_type": membership_data.membership_type,
                "original_price": original_price,
                "final_price": final_price,
                "discount": original_price - final_price if promo_details else 0
            }
        else:
            raise Exception("Ödeme başlatılamadı")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Membership creation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memberships/promo-codes/validate")
async def validate_membership_promo_code(
    promo_data: PromoCodeValidate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Validate promo code and return discount info"""
    db = request.app.state.db
    
    try:
        facility = await db.facilities.find_one({"id": promo_data.facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        original_price = get_membership_price(facility, promo_data.membership_type)
        
        final_price, promo = await apply_promo_code(
            db,
            promo_data.code,
            promo_data.facility_id,
            original_price
        )
        
        return {
            "valid": True,
            "original_price": original_price,
            "final_price": final_price,
            "discount_amount": original_price - final_price,
            "discount_percentage": promo["discount_percentage"]
        }
        
    except HTTPException as e:
        return {
            "valid": False,
            "error": e.detail
        }


@router.post("/promo-codes/create")
async def create_promo_code(
    promo_data: PromoCodeCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Create promo code (admin or facility owner only)"""
    db = request.app.state.db
    
    # Check if user is admin or facility owner
    is_admin = current_user.get("user_type") == "admin"
    is_owner = False
    
    if promo_data.facility_id:
        facility = await db.facilities.find_one({"id": promo_data.facility_id})
        if facility:
            is_owner = facility.get("owner_id") == current_user["id"]
    
    if not is_admin and not is_owner:
        raise HTTPException(status_code=403, detail="Yetkiniz yok")
    
    # Check if code already exists
    existing = await db.promo_codes.find_one({"code": promo_data.code.upper()})
    if existing:
        raise HTTPException(status_code=400, detail="Bu promosyon kodu zaten kullanılıyor")
    
    promo_code = {
        "id": str(uuid.uuid4()),
        "code": promo_data.code.upper(),
        "facility_id": promo_data.facility_id,
        "discount_percentage": promo_data.discount_percentage,
        "valid_until": promo_data.valid_until,
        "usage_limit": promo_data.usage_limit,
        "usage_count": 0,
        "is_active": True,
        "created_by": current_user["id"],
        "created_at": datetime.utcnow()
    }
    
    await db.promo_codes.insert_one(promo_code)
    
    return {"success": True, "promo_code": promo_code}


@router.get("/memberships/my-memberships")
async def get_my_memberships(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Get user's memberships"""
    db = request.app.state.db
    
    memberships = await db.memberships.find({
        "user_id": current_user["id"]
    }).sort("created_at", -1).to_list(100)
    
    for membership in memberships:
        membership.pop("_id", None)
        
        # Get facility info
        facility = await db.facilities.find_one({"id": membership["facility_id"]})
        if facility:
            membership["facility_name"] = facility.get("name")
            membership["facility_city"] = facility.get("city")
    
    return {"memberships": memberships}


@router.get("/memberships/expiring-soon")
async def get_expiring_memberships(
    request: Request,
    days: int = 7
):
    """Get memberships expiring in X days (for cronjob notifications)"""
    db = request.app.state.db
    
    now = datetime.utcnow()
    future_date = now + timedelta(days=days)
    
    memberships = await db.memberships.find({
        "status": "active",
        "end_date": {
            "$gte": now,
            "$lte": future_date
        },
        "renewal_notification_sent": {"$ne": True}
    }).to_list(1000)
    
    return {"expiring_memberships": memberships, "total": len(memberships)}


@router.post("/memberships/send-renewal-reminders")
async def send_renewal_reminders(
    request: Request,
    days_before: int = 7
):
    """Send renewal reminders to users whose memberships are expiring soon (Cronjob endpoint)"""
    from models import NotificationType, NotificationRelatedType
    
    db = request.app.state.db
    
    try:
        now = datetime.utcnow()
        future_date = now + timedelta(days=days_before)
        
        # Süresi dolmak üzere olan aktif üyelikleri bul
        expiring_memberships = await db.memberships.find({
            "status": "active",
            "end_date": {
                "$gte": now,
                "$lte": future_date
            },
            "renewal_notification_sent": {"$ne": True}
        }).to_list(1000)
        
        notifications_sent = 0
        
        for membership in expiring_memberships:
            # Tesis bilgisini getir
            facility = await db.facilities.find_one({"id": membership["facility_id"]})
            if not facility:
                continue
            
            # Kullanıcıya bildirim gönder
            days_left = (membership["end_date"] - now).days
            
            notification_data = {
                "id": str(__import__('uuid').uuid4()),
                "user_id": membership["user_id"],
                "type": NotificationType.EVENT_REMINDER_1DAY.value,  # Genel reminder tipi kullanıyoruz
                "title": "Üyelik Yenileme Hatırlatması",
                "message": f"{facility['name']} tesisindeki üyeliğiniz {days_left} gün içinde sona eriyor. Yenilemek için hemen tıklayın!",
                "related_type": NotificationRelatedType.FACILITY.value,
                "related_id": facility["id"],
                "data": {
                    "membership_id": membership["id"],
                    "facility_id": facility["id"],
                    "facility_name": facility["name"],
                    "end_date": membership["end_date"].isoformat(),
                    "days_left": days_left
                },
                "read": False,
                "created_at": datetime.utcnow()
            }
            
            await db.notifications.insert_one(notification_data)
            
            # Üyeliğe hatırlatma gönderildi işareti koy
            await db.memberships.update_one(
                {"id": membership["id"]},
                {"$set": {"renewal_notification_sent": True}}
            )
            
            notifications_sent += 1
            logger.info(f"✅ Yenileme hatırlatması gönderildi: {membership['user_id']} - {facility['name']}")
        
        logger.info(f"📧 Toplam {notifications_sent} yenileme hatırlatması gönderildi")
        
        return {
            "success": True,
            "notifications_sent": notifications_sent,
            "message": f"{notifications_sent} kullanıcıya yenileme hatırlatması gönderildi"
        }
        
    except Exception as e:
        logger.error(f"❌ Yenileme hatırlatması gönderme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/memberships/{membership_id}/renew")
async def renew_membership(
    membership_id: str,
    renewal_data: MembershipRenew,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Renew membership with updated prices"""
    db = request.app.state.db
    
    membership = await db.memberships.find_one({"id": membership_id})
    if not membership:
        raise HTTPException(status_code=404, detail="Üyelik bulunamadı")
    
    if membership["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Bu üyeliğe erişim yetkiniz yok")
    
    # Get current prices from facility
    facility = await db.facilities.find_one({"id": membership["facility_id"]})
    if not facility:
        raise HTTPException(status_code=404, detail="Tesis bulunamadı")
    
    original_price = get_membership_price(facility, renewal_data.membership_type)
    final_price = original_price
    promo_details = None
    
    # Apply promo code if provided
    if renewal_data.promo_code:
        final_price, promo_details = await apply_promo_code(
            db,
            renewal_data.promo_code,
            membership["facility_id"],
            original_price
        )
    
    # Create new membership record for renewal
    new_membership_id = str(uuid.uuid4())
    start_date = membership["end_date"]  # Start from old end date
    end_date = calculate_end_date(start_date, renewal_data.membership_type)
    
    new_membership = {
        "id": new_membership_id,
        "user_id": current_user["id"],
        "facility_id": membership["facility_id"],
        "membership_type": renewal_data.membership_type,
        "original_price": original_price,
        "final_price": final_price,
        "promo_code": renewal_data.promo_code,
        "promo_details": promo_details["id"] if promo_details else None,
        "start_date": start_date,
        "end_date": end_date,
        "status": "pending_payment",
        "is_renewal": True,
        "previous_membership_id": membership_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.memberships.insert_one(new_membership)
    
    return {
        "success": True,
        "new_membership_id": new_membership_id,
        "original_price": original_price,
        "final_price": final_price,
        "start_date": start_date,
        "end_date": end_date
    }


# ==================== PAYMENT ENDPOINTS ====================

@router.post("/memberships/initialize-payment")
async def initialize_membership_payment(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Initialize membership payment with iyzico checkout form"""
    db = request.app.state.db
    
    try:
        body = await request.json()
        membership_id = body.get("membership_id")
        
        if not membership_id:
            raise HTTPException(status_code=400, detail="membership_id gerekli")
        
        # Get membership
        membership = await db.memberships.find_one({"id": membership_id})
        if not membership:
            raise HTTPException(status_code=404, detail="Üyelik bulunamadı")
        
        if membership["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Bu üyeliğe erişim yetkiniz yok")
        
        if membership["status"] != "pending_payment":
            raise HTTPException(status_code=400, detail="Bu üyelik zaten ödeme durumunda değil")
        
        # Get facility
        facility = await db.facilities.find_one({"id": membership["facility_id"]})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Get user
        user = await db.users.find_one({"id": current_user["id"]})
        if not user:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        
        # Prepare payment info
        amount = membership["final_price"]
        conversation_id = str(uuid.uuid4())
        
        logger.info(f"💳 Initializing membership payment: {membership_id}, amount: {amount} TRY")
        
        # Create payment record
        payment_id = str(uuid.uuid4())
        payment_data = {
            "id": payment_id,
            "user_id": current_user["id"],
            "related_type": "membership",
            "related_id": membership_id,
            "amount": amount,
            "currency": "TRY",
            "status": "pending",
            "iyzico_conversation_id": conversation_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.payments.insert_one(payment_data)
        
        # Initialize iyzico checkout form
        try:
            # Get backend base URL from environment (MUST be public URL for Iyzico callback)
            backend_base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:3000")
            callback_url = f"{backend_base_url}/api/memberships/payment-callback"
            
            logger.info(f"💳 İyzico callback URL: {callback_url}")
            logger.info(f"🌐 Backend base URL: {backend_base_url}")
            
            membership_type_tr = {
                "daily": "Günlük",
                "monthly": "Aylık",
                "yearly": "Yıllık"
            }.get(membership["membership_type"], membership["membership_type"])
            
            result = iyzico_service.initialize_checkout_form(
                user={
                    'id': user['id'],
                    'email': user['email'],
                    'full_name': user['full_name'],
                    'phone_number': user.get('phone', '+905000000000'),
                    'tc_kimlik': user.get('tckn', '11111111111'),
                    'created_at': user.get('created_at', datetime.utcnow())
                },
                amount=amount,
                related_type='membership',
                related_id=membership_id,
                related_name=f"{facility['name']} - {membership_type_tr} Üyelik",
                callback_url=callback_url
            )
            
            if result.get('status') == 'success':
                # Update payment with iyzico token
                await db.payments.update_one(
                    {"id": payment_id},
                    {
                        "$set": {
                            "iyzico_token": result.get("token"),
                            "status": "init_3ds",
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                logger.info(f"✅ Payment initialized successfully: {payment_id}")
                
                return {
                    "success": True,
                    "membership_id": membership_id,
                    "payment_id": payment_id,
                    "payment_page_url": result.get("paymentPageUrl"),
                    "token": result.get("token"),
                    "amount": amount
                }
            else:
                raise Exception("Iyzico checkout initialization failed")
                
        except Exception as e:
            logger.error(f"❌ Iyzico error: {str(e)}")
            await db.payments.update_one(
                {"id": payment_id},
                {"$set": {"status": "failure", "error_message": str(e), "updated_at": datetime.utcnow()}}
            )
            raise HTTPException(status_code=500, detail=f"Ödeme başlatılamadı: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Membership payment initialization error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memberships/payment-callback")
@router.get("/memberships/payment-callback")
async def membership_payment_callback(
    request: Request,
    token: str = None
):
    """Handle iyzico payment callback for membership"""
    db = request.app.state.db
    
    try:
        # Try to get token from query params or form data
        if not token:
            form_data = await request.form()
            token = form_data.get("token")
        
        if not token:
            logger.error("❌ Token not found in request")
            raise HTTPException(status_code=400, detail="Token parametresi eksik")
        
        logger.info(f"📥 Membership payment callback received, token: {token}")
        
        # Retrieve payment result from iyzico
        result = iyzico_service.retrieve_checkout_form_result(token)
        
        # Find payment record
        payment = await db.payments.find_one({"iyzico_token": token})
        if not payment:
            logger.error(f"❌ Payment not found for token: {token}")
            raise HTTPException(status_code=404, detail="Ödeme kaydı bulunamadı")
        
        membership_id = payment["related_id"]
        membership = await db.memberships.find_one({"id": membership_id})
        if not membership:
            raise HTTPException(status_code=404, detail="Üyelik bulunamadı")
        
        # Update payment status
        update_data = {
            "status": result.get("status"),
            "iyzico_payment_id": result.get("paymentId"),
            "updated_at": datetime.utcnow()
        }
        
        if result.get("status") == "success":
            update_data["status"] = "success"
            
            # Update membership status to active
            await db.memberships.update_one(
                {"id": membership_id},
                {
                    "$set": {
                        "status": "active",
                        "payment_id": payment["id"],
                        "paid_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"✅ Membership activated: {membership_id}")
            
            # Get facility and user info
            facility = await db.facilities.find_one({"id": membership["facility_id"]})
            user = await db.users.find_one({"id": membership["user_id"]})
            
            # Send notifications
            membership_type_tr = {
                "daily": "Günlük",
                "monthly": "Aylık",
                "yearly": "Yıllık"
            }.get(membership["membership_type"], membership["membership_type"])
            
            # 1. Notification to buyer
            buyer_notification = {
                "id": str(uuid.uuid4()),
                "user_id": membership["user_id"],
                "type": NotificationType.FACILITY_APPROVED.value,
                "title": "Üyelik Aktif Edildi",
                "message": f"{facility['name']} tesisine {membership_type_tr} üyeliğiniz başarıyla aktif edildi.",
                "related_type": NotificationRelatedType.FACILITY.value,
                "related_id": facility["id"],
                "data": {
                    "membership_id": membership_id,
                    "facility_id": facility["id"],
                    "facility_name": facility["name"],
                    "membership_type": membership_type_tr,
                    "start_date": membership["start_date"].isoformat(),
                    "end_date": membership["end_date"].isoformat(),
                    "price": membership["final_price"]
                },
                "read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(buyer_notification)
            logger.info(f"📧 Buyer notification sent to: {membership['user_id']}")
            
            # 2. Notification to facility owner
            if facility.get("owner_id"):
                owner_notification = {
                    "id": str(uuid.uuid4()),
                    "user_id": facility["owner_id"],
                    "type": NotificationType.RESERVATION_REQUEST.value,
                    "title": "Yeni Üye Kaydı",
                    "message": f"{user.get('full_name', 'Bir kullanıcı')} {membership_type_tr} üyelik satın aldı.",
                    "related_type": NotificationRelatedType.FACILITY.value,
                    "related_id": facility["id"],
                    "data": {
                        "membership_id": membership_id,
                        "user_id": user["id"],
                        "user_name": user.get("full_name"),
                        "membership_type": membership_type_tr,
                        "price": membership["final_price"]
                    },
                    "read": False,
                    "created_at": datetime.utcnow()
                }
                await db.notifications.insert_one(owner_notification)
                logger.info(f"📧 Owner notification sent to: {facility['owner_id']}")
            
            # 3. Notification to admin (Özgür Barış Karaca)
            # Önce telefon ile ara, bulamazsan isimle ara
            admin = await db.users.find_one({"phone_number": "+905324900472"})
            if not admin:
                admin = await db.users.find_one({"full_name": "Özgür Barış Karaca", "user_type": "admin"})
            
            if admin:
                admin_notification = {
                    "id": str(uuid.uuid4()),
                    "user_id": admin["id"],
                    "type": NotificationType.ADMIN_ACTION.value,
                    "title": "Yeni Üyelik Satışı",
                    "message": f"{facility['name']} - {user.get('full_name', 'Kullanıcı')} tarafından {membership_type_tr} üyelik satın alındı. Tutar: ₺{membership['final_price']}",
                    "related_type": NotificationRelatedType.FACILITY.value,
                    "related_id": facility["id"],
                    "data": {
                        "membership_id": membership_id,
                        "facility_id": facility["id"],
                        "facility_name": facility["name"],
                        "user_id": user["id"],
                        "user_name": user.get("full_name"),
                        "membership_type": membership_type_tr,
                        "price": membership["final_price"]
                    },
                    "read": False,
                    "created_at": datetime.utcnow()
                }
                await db.notifications.insert_one(admin_notification)
                logger.info(f"📧 Admin notification sent to: {admin['id']}")
            else:
                logger.warning("⚠️  Admin user not found with phone: +905324900472")
            
        else:
            update_data["status"] = "failure"
            update_data["error_message"] = result.get("errorMessage")
            
            # Update membership status to failed
            await db.memberships.update_one(
                {"id": membership_id},
                {"$set": {"status": "payment_failed", "updated_at": datetime.utcnow()}}
            )
            
            logger.error(f"❌ Membership payment failed: {membership_id}")
        
        await db.payments.update_one(
            {"id": payment["id"]},
            {"$set": update_data}
        )
        
        return {
            "success": result.get("status") == "success",
            "status": result.get("status"),
            "membership_id": membership_id,
            "message": "Ödeme başarılı" if result.get("status") == "success" else "Ödeme başarısız"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Membership payment callback error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memberships/{membership_id}/status")
async def get_membership_status(
    membership_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Get membership status (for polling)"""
    db = request.app.state.db
    
    membership = await db.memberships.find_one({"id": membership_id})
    if not membership:
        raise HTTPException(status_code=404, detail="Üyelik bulunamadı")
    
    if membership["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Bu üyeliğe erişim yetkiniz yok")
    
    return {
        "membership_id": membership_id,
        "status": membership["status"],
        "payment_status": "completed" if membership["status"] == "active" else "pending"
    }
