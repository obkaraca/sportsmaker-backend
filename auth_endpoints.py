"""
Authentication Endpoints Module
Handles: Login, OTP, Register, Session Management, Verification
"""
from fastapi import APIRouter, HTTPException, Depends, status, Request, Response
from datetime import datetime, timedelta
import uuid
import logging

from models import UserCreate, UserLogin, User, VerificationCode, VerifyRequest
from auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_user, decode_token
)
from verification_service import VerificationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])

# Database reference - will be set from server.py
db = None

def set_database(database):
    """Set database reference from main server"""
    global db
    db = database


async def log_user_activity(
    user_id: str,
    action_type: str,
    result: str,
    details: dict = None,
    ip_address: str = None
):
    """Kullanıcı aktivitesini logla"""
    try:
        if db is None:
            return None
        # Kullanıcı bilgilerini al
        user = await db.users.find_one({"id": user_id})
        
        log_entry = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "user_name": user.get("full_name", "Bilinmeyen") if user else "Bilinmeyen",
            "user_type": user.get("user_type", "unknown") if user else "unknown",
            "phone": user.get("phone", "") if user else "",
            "action_type": action_type,
            "result": result,
            "details": details or {},
            "ip_address": ip_address,
            "created_at": datetime.utcnow()
        }
        
        await db.user_activity_logs.insert_one(log_entry)
        logger.info(f"📝 Activity logged: {action_type} - {result} for user {user_id}")
        return log_entry
    except Exception as e:
        logger.error(f"Error logging user activity: {e}")
        return None


@router.post("/register", response_model=dict)
async def register(request: Request):
    """Register a new user"""
    try:
        user_data = await request.json()
        
        email = user_data.get('email')
        password = user_data.get('password')
        full_name = user_data.get('full_name')
        user_type = user_data.get('user_type', 'player')
        city = user_data.get('city', '')
        
        if not email or not password or not full_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email, password ve full_name gerekli"
            )
        
        # Negatif ücret kontrolü
        for rate_field in ['hourly_rate', 'daily_rate', 'monthly_rate', 'match_fee']:
            rate_value = user_data.get(rate_field)
            if rate_value is not None:
                try:
                    if float(rate_value) < 0:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"{rate_field} negatif olamaz"
                        )
                except (ValueError, TypeError):
                    pass
        
        existing_user = await db.users.find_one({"email": email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bu email zaten kayıtlı"
            )
        
        hashed_password = get_password_hash(password)
        
        user_dict = {
            "id": str(uuid.uuid4()),
            "email": email,
            "full_name": full_name,
            "user_type": user_type,
            "phone": user_data.get('phone'),
            "city": city,
            "district": user_data.get('district'),
            "date_of_birth": user_data.get('date_of_birth'),
            "profile_image": user_data.get('profile_image'),
            "hourly_rate": user_data.get('hourly_rate'),
            "daily_rate": user_data.get('daily_rate'),
            "monthly_rate": user_data.get('monthly_rate'),
            "availability": user_data.get('availability', {}),
            "instagram": user_data.get('instagram'),
            "website": user_data.get('website'),
            "languages": user_data.get('languages', []),
            "tckn": user_data.get('tckn'),
            "vk_no": user_data.get('vk_no'),
            "iban": user_data.get('iban'),
            "hashed_password": hashed_password,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Check if this is the super admin phone number
        if user_dict.get('phone') == "+905324900472" or user_dict.get('phone') == "905324900472":
            user_dict["user_type"] = "super_admin"
        
        await db.users.insert_one(user_dict)
        
        # Create welcome review from system
        welcome_review = {
            "id": str(uuid.uuid4()),
            "reviewer_user_id": "sportsmaker-system",
            "reviewer_name": "SportsMaker",
            "target_user_id": user_dict["id"],
            "target_type": "user",
            "related_id": "welcome",
            "related_type": "welcome",
            "rating": 5,
            "comment": "SportsMaker'a hoş geldiniz.",
            "skills_rating": 5,
            "communication_rating": 5,
            "punctuality_rating": 5,
            "is_system_review": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        await db.reviews.insert_one(welcome_review)
        
        # Update user's rating
        await db.users.update_one(
            {"id": user_dict["id"]},
            {"$set": {"rating": 5.0, "review_count": 1, "average_rating": 5.0}}
        )
        
        access_token = create_access_token(data={"sub": user_dict["id"]})
        
        # Kayıt log'u
        ip_address = request.client.host if request.client else None
        await log_user_activity(user_dict["id"], "register", "success", {
            "user_type": user_type,
            "city": city
        }, ip_address)
        
        # hashed_password'ı response'dan çıkar
        user_response = {k: v for k, v in user_dict.items() if k != "hashed_password"}
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user_response
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Kayıt hatası: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kayıt sırasında bir hata oluştu: {str(e)}"
        )


@router.post("/login")
async def login(user_data: UserLogin, request: Request):
    """Login user (legacy - email/password)"""
    ip_address = request.client.host if request.client else None
    
    user = await db.users.find_one({"email": user_data.email})
    if not user or not verify_password(user_data.password, user["hashed_password"]):
        # Başarısız giriş log'u
        if user:
            await log_user_activity(user["id"], "login", "failed", {"method": "email", "reason": "wrong_password"}, ip_address)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz email veya şifre"
        )
    
    # Başarılı giriş log'u
    await log_user_activity(user["id"], "login", "success", {"method": "email"}, ip_address)
    
    access_token = create_access_token(data={"sub": user["id"]})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": User(**{k: v for k, v in user.items() if k != "hashed_password"})
    }


@router.post("/request-login-otp")
async def request_login_otp(request: Request):
    """Request OTP code for phone login"""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    
    if not phone:
        raise HTTPException(status_code=400, detail="Telefon numarası gerekli")
    
    # Telefon numarasını normalize et - farklı formatları kontrol et
    phone_normalized = phone.replace("+", "").replace(" ", "").replace("-", "")
    phone_with_plus = "+" + phone_normalized if not phone.startswith("+") else phone
    
    # Farklı formatlarla ara
    user = await db.users.find_one({
        "$or": [
            {"phone": phone},
            {"phone": phone_normalized},
            {"phone": phone_with_plus},
            {"phone_number": phone},
            {"phone_number": phone_normalized},
            {"phone_number": phone_with_plus}
        ]
    })
    
    if not user:
        raise HTTPException(status_code=404, detail="Bu telefon numarasına ait hesap bulunamadı")
    
    code = VerificationService.generate_code(6)
    
    verification_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(minutes=2)
    
    verification_data = {
        "id": verification_id,
        "user_id": user["id"],
        "phone": phone_normalized,  # Normalize edilmiş hali kaydet
        "code": code,
        "verification_type": "login_otp",
        "expires_at": expires_at,
        "is_used": False,
        "created_at": datetime.utcnow()
    }
    
    await db.verification_codes.insert_one(verification_data)
    
    success = VerificationService.send_sms_verification(phone_normalized, code)
    if not success:
        raise HTTPException(status_code=500, detail="SMS gönderilemedi")
    
    return {
        "message": "Doğrulama kodu telefonunuza gönderildi",
        "expires_in_seconds": 120,
        "phone": phone_normalized
    }


@router.post("/login-with-otp")
async def login_with_otp(request: Request):
    """Login with phone and OTP code"""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    code = body.get("code")
    ip_address = request.client.host if request.client else None
    
    if not phone or not code:
        raise HTTPException(status_code=400, detail="Telefon ve kod gerekli")
    
    # Telefon numarasını normalize et
    phone_normalized = phone.replace("+", "").replace(" ", "").replace("-", "")
    phone_with_plus = "+" + phone_normalized if not phone.startswith("+") else phone
    
    # Farklı formatlarla kullanıcıyı ara
    user = await db.users.find_one({
        "$or": [
            {"phone": phone},
            {"phone": phone_normalized},
            {"phone": phone_with_plus},
            {"phone_number": phone},
            {"phone_number": phone_normalized},
            {"phone_number": phone_with_plus}
        ]
    })
    
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # MOCK MODE BYPASS
    from netgsm_service import netgsm_service
    if not netgsm_service.enabled and code == "123456":
        logger.info(f"✅ Mock mode bypass: Login code 123456 accepted for {phone}")
        # OTP giriş log'u
        await log_user_activity(user["id"], "login", "success", {"method": "otp", "mock_mode": True}, ip_address)
        access_token = create_access_token(data={"sub": user["id"]})
        user_data = {k: v for k, v in user.items() if k not in ["password_hash", "hashed_password", "_id"]}
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user_data
        }
    
    # Doğrulama kodunu kontrol et - normalize edilmiş telefon ile
    verification = await db.verification_codes.find_one({
        "$or": [
            {"phone": phone},
            {"phone": phone_normalized},
            {"phone": phone_with_plus}
        ],
        "code": code,
        "verification_type": "login_otp",
        "is_used": False,
        "expires_at": {"$gt": datetime.utcnow()}
    })
    
    if not verification:
        # Başarısız OTP log'u
        await log_user_activity(user["id"], "login", "failed", {"method": "otp", "reason": "invalid_code"}, ip_address)
        raise HTTPException(status_code=400, detail="Geçersiz veya süresi dolmuş kod")
    
    # Kodu kullanıldı olarak işaretle
    await db.verification_codes.update_one(
        {"id": verification["id"]},
        {"$set": {"is_used": True}}
    )
    
    # Başarılı OTP giriş log'u
    await log_user_activity(user["id"], "login", "success", {"method": "otp"}, ip_address)
    
    access_token = create_access_token(data={"sub": user["id"]})
    user_data = {k: v for k, v in user.items() if k not in ["password_hash", "hashed_password", "_id"]}
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_data
    }


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info"""
    current_user_id = current_user.get("id")
    
    user = await db.users.find_one({"id": current_user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    user_dict = {k: v for k, v in user.items() if k not in ["_id", "hashed_password", "password_hash"]}
    return user_dict


@router.post("/check-phone")
async def check_phone_exists(request: Request):
    """Check if phone number is already registered"""
    body = await request.json()
    phone = body.get("phone")
    
    if not phone:
        raise HTTPException(status_code=400, detail="Telefon numarası gerekli")
    
    # Telefon numarasını normalize et (90 ile başlamasını sağla)
    normalized_phone = phone
    if not phone.startswith('90') and not phone.startswith('+90'):
        normalized_phone = '90' + phone.lstrip('0')
    normalized_phone = normalized_phone.replace('+', '')
    
    # Farklı formatlarla kontrol et
    phone_variants = [
        phone,
        normalized_phone,
        phone.lstrip('0'),
        '0' + phone.lstrip('0'),
        '+90' + phone.lstrip('0').lstrip('90'),
    ]
    
    # Veritabanında telefon numarasını ara
    existing_user = await db.users.find_one({
        "phone": {"$in": phone_variants}
    })
    
    if existing_user:
        return {
            "exists": True,
            "message": "Bu telefon numarası zaten kayıtlı. Lütfen başka bir telefon numarası ile kayıt olunuz."
        }
    
    return {
        "exists": False,
        "message": "Telefon numarası kullanılabilir"
    }


@router.post("/send-verification")
async def send_verification_code(request: Request):
    """Send verification code via email or SMS"""
    body = await request.json()
    email = body.get("email")
    phone = body.get("phone")
    
    if not email and not phone:
        raise HTTPException(status_code=400, detail="Email veya telefon gerekli")
    
    code = VerificationService.generate_code(6)
    
    verification_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(minutes=2)
    
    verification_data = {
        "id": verification_id,
        "user_id": None,
        "email": email,
        "phone": phone,
        "code": code,
        "verification_type": "email" if email else "sms",
        "expires_at": expires_at,
        "is_used": False,
        "created_at": datetime.utcnow()
    }
    
    await db.verification_codes.insert_one(verification_data)
    
    if email:
        success = VerificationService.send_email_verification(email, code)
        if not success:
            # Log the failure but don't block registration - code is saved in DB
            logger.warning(f"📧 Email sending failed for {email}, but registration continues. Code: {code}")
        return {"message": "Verification code sent to email", "expires_in_seconds": 120}
    else:
        success = VerificationService.send_sms_verification(phone, code)
        if not success:
            raise HTTPException(status_code=500, detail="SMS gönderilemedi")
        return {"message": "Verification code sent to phone", "expires_in_seconds": 120}


@router.post("/verify-code")
async def verify_code(verify_request: VerifyRequest):
    """Verify the code"""
    query = {"code": verify_request.code, "is_used": False}
    
    if verify_request.email:
        query["email"] = verify_request.email
    elif verify_request.phone:
        query["phone"] = verify_request.phone
    else:
        raise HTTPException(status_code=400, detail="Email veya telefon gerekli")
    
    verification = await db.verification_codes.find_one(query)
    
    if not verification:
        raise HTTPException(status_code=400, detail="Geçersiz veya süresi dolmuş kod")
    
    if datetime.utcnow() > verification["expires_at"]:
        raise HTTPException(status_code=400, detail="Kod süresi doldu. Lütfen yeni bir kod isteyin")
    
    await db.verification_codes.update_one(
        {"id": verification["id"]},
        {"$set": {"is_used": True}}
    )
    
    return {"message": "Verification successful", "verified": True}


@router.post("/resend-verification")
async def resend_verification_code(request: Request):
    """Resend verification code"""
    body = await request.json()
    email = body.get("email")
    phone = body.get("phone")
    
    if not email and not phone:
        raise HTTPException(status_code=400, detail="Email veya telefon gerekli")
    
    query = {"is_used": False}
    if email:
        query["email"] = email
    else:
        query["phone"] = phone
    
    await db.verification_codes.update_many(query, {"$set": {"is_used": True}})
    
    class FakeRequest:
        async def json(self):
            return {"email": email, "phone": phone}
    
    return await send_verification_code(FakeRequest())
