"""
Promo Code Endpoints
Full-featured promotional code system for facility bookings
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import uuid
from auth import get_current_user

router = APIRouter()

# ============== Request/Response Models ==============

class PromoCodeCreate(BaseModel):
    code: str = Field(..., max_length=10, description="Promo code (max 10 chars, will be converted to uppercase)")
    facility_id: Optional[str] = None
    discount_percentage: float = Field(..., gt=0, le=100, description="Discount percentage (1-100)")
    valid_until: datetime
    usage_limit: Optional[int] = Field(None, gt=0, description="Maximum number of uses")
    
class PromoCodeUpdate(BaseModel):
    discount_percentage: Optional[float] = Field(None, gt=0, le=100)
    valid_until: Optional[datetime] = None
    usage_limit: Optional[int] = Field(None, gt=0)
    is_active: Optional[bool] = None

class PromoCodeValidate(BaseModel):
    code: str
    facility_id: Optional[str] = None
    reservation_amount: float = 0

class PromoCodeValidateResponse(BaseModel):
    valid: bool
    discount_percentage: float = 0
    discount_amount: float = 0
    final_amount: float = 0
    message: str

# ============== Helper Functions ==============

def get_db():
    """Get database connection"""
    from pymongo import MongoClient
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    client = MongoClient(mongo_url)
    return client.test_database

# ============== Endpoints ==============

@router.post("/promo-codes", status_code=201)
async def create_promo_code(
    promo_data: PromoCodeCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new promo code (facility_owner, club_manager, venue_owner and admin only)
    """
    user_id = current_user.get("id")
    user_type = current_user.get("user_type")
    
    # Check permission
    allowed_types = ["facility_owner", "club_manager", "venue_owner", "admin", "super_admin"]
    if user_type not in allowed_types:
        raise HTTPException(status_code=403, detail="Only facility owners, club managers and admins can create promo codes")
    
    db = get_db()
    
    # Convert code to uppercase
    code_upper = promo_data.code.upper().strip()
    
    # Check if code already exists
    existing_code = db.promo_codes.find_one({"code": code_upper})
    if existing_code:
        raise HTTPException(status_code=400, detail="Promo code already exists")
    
    # If facility_id provided, verify ownership (for venue_owner)
    if promo_data.facility_id and user_type == "venue_owner":
        facility = db.facilities.find_one({"id": promo_data.facility_id, "owner_id": user_id})
        if not facility:
            raise HTTPException(status_code=403, detail="You can only create promo codes for your own facilities")
    
    # Create promo code
    promo_code = {
        "id": str(uuid.uuid4()),
        "code": code_upper,
        "facility_id": promo_data.facility_id,
        "discount_percentage": promo_data.discount_percentage,
        "valid_until": promo_data.valid_until,
        "usage_limit": promo_data.usage_limit,
        "used_count": 0,
        "is_active": True,
        "created_by": user_id,
        "created_at": datetime.utcnow()
    }
    
    db.promo_codes.insert_one(promo_code)
    
    # Remove MongoDB _id for response
    promo_code.pop("_id", None)
    
    return {
        "message": "Promo code created successfully",
        "promo_code": promo_code
    }


@router.get("/promo-codes/my")
async def get_my_promo_codes(
    current_user: dict = Depends(get_current_user)
):
    """
    Get promo codes created by current user
    """
    user_id = current_user.get("id")
    
    db = get_db()
    
    # Get user's promo codes
    promo_codes = list(db.promo_codes.find({"created_by": user_id}))
    
    # Remove MongoDB _id
    for code in promo_codes:
        code.pop("_id", None)
    
    # Sort by created_at DESC
    promo_codes.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)
    
    return {
        "promo_codes": promo_codes,
        "total": len(promo_codes)
    }


@router.post("/promo-codes/validate")
async def validate_promo_code(
    validate_data: PromoCodeValidate
):
    """
    Validate a promo code and calculate discount
    Public endpoint - no auth required (used during booking)
    """
    import logging
    logging.info(f"Validating promo code: {validate_data.code}, facility_id: {validate_data.facility_id}, amount: {validate_data.reservation_amount}")
    
    db = get_db()
    
    # Find promo code
    code_upper = validate_data.code.upper().strip()
    promo_code = db.promo_codes.find_one({"code": code_upper})
    
    logging.info(f"Found promo code: {promo_code}")
    
    if not promo_code:
        return PromoCodeValidateResponse(
            valid=False,
            message="Promo kodu bulunamadı"
        )
    
    # Check if active
    if not promo_code.get("is_active"):
        return PromoCodeValidateResponse(
            valid=False,
            message="Bu promo kodu artık aktif değil"
        )
    
    # Check expiry date
    valid_until = promo_code.get("valid_until")
    if valid_until and datetime.utcnow() > valid_until:
        return PromoCodeValidateResponse(
            valid=False,
            message="Bu promo kodunun geçerlilik süresi dolmuş"
        )
    
    # Check usage limit
    usage_limit = promo_code.get("usage_limit")
    used_count = promo_code.get("used_count", 0)
    if usage_limit and used_count >= usage_limit:
        return PromoCodeValidateResponse(
            valid=False,
            message="Bu promo kodunun kullanım limiti dolmuş"
        )
    
    # Check facility restriction
    facility_id = promo_code.get("facility_id")
    if facility_id and facility_id != validate_data.facility_id:
        return PromoCodeValidateResponse(
            valid=False,
            message="Bu promo kodu sadece belirli bir tesiste geçerli"
        )
    
    # Calculate discount
    discount_percentage = promo_code.get("discount_percentage", 0)
    discount_amount = (validate_data.reservation_amount * discount_percentage) / 100
    final_amount = validate_data.reservation_amount - discount_amount
    
    return PromoCodeValidateResponse(
        valid=True,
        discount_percentage=discount_percentage,
        discount_amount=round(discount_amount, 2),
        final_amount=round(final_amount, 2),
        message=f"%{discount_percentage} indirim uygulandı"
    )


@router.post("/promo-codes/{code}/apply")
async def apply_promo_code(
    code: str,
    reservation_id: str
):
    """
    Apply promo code to a reservation and increment usage count
    Called after successful payment
    """
    db = get_db()
    
    # Find and update promo code usage
    code_upper = code.upper().strip()
    result = db.promo_codes.update_one(
        {"code": code_upper},
        {"$inc": {"used_count": 1}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Promo code not found")
    
    # Update reservation with promo code info
    db.reservations.update_one(
        {"id": reservation_id},
        {"$set": {"promo_code_used": code_upper}}
    )
    
    return {"message": "Promo code applied successfully"}


@router.get("/promo-codes")
async def list_all_promo_codes(
    skip: int = 0,
    limit: int = 50,
    facility_id: Optional[str] = None,
    active_only: bool = False,
    current_user: dict = Depends(get_current_user)
):
    """
    List all promo codes (facility_owner, club_manager, venue_owner and admin)
    """
    user_id = current_user.get("id")
    user_type = current_user.get("user_type")
    
    # Allowed user types
    allowed_types = ["facility_owner", "club_manager", "venue_owner", "admin", "super_admin"]
    if user_type not in allowed_types:
        raise HTTPException(status_code=403, detail="Bu sayfaya erişim yetkiniz yok")
    
    db = get_db()
    
    # Build query - non-admin users only see their own codes
    query = {}
    if user_type not in ["admin", "super_admin"]:
        query["created_by"] = user_id
    
    if facility_id:
        query["facility_id"] = facility_id
    if active_only:
        query["is_active"] = True
        query["valid_until"] = {"$gte": datetime.utcnow()}
    
    # Get promo codes
    promo_codes = list(db.promo_codes.find(query).skip(skip).limit(limit))
    total = db.promo_codes.count_documents(query)
    
    # Remove MongoDB _id
    for code in promo_codes:
        code.pop("_id", None)
    
    # Sort by created_at DESC
    promo_codes.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)
    
    return {
        "promo_codes": promo_codes,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.put("/promo-codes/{code_id}")
async def update_promo_code(
    code_id: str,
    update_data: PromoCodeUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update a promo code (creator or admin only)
    """
    user_id = current_user.get("id")
    user_type = current_user.get("user_type")
    
    db = get_db()
    
    # Find promo code
    promo_code = db.promo_codes.find_one({"id": code_id})
    if not promo_code:
        raise HTTPException(status_code=404, detail="Promo code not found")
    
    # Check permission
    if user_type not in ["admin", "super_admin"] and promo_code.get("created_by") != user_id:
        raise HTTPException(status_code=403, detail="You can only update your own promo codes")
    
    # Build update dict
    update_dict = {}
    if update_data.discount_percentage is not None:
        update_dict["discount_percentage"] = update_data.discount_percentage
    if update_data.valid_until is not None:
        update_dict["valid_until"] = update_data.valid_until
    if update_data.usage_limit is not None:
        update_dict["usage_limit"] = update_data.usage_limit
    if update_data.is_active is not None:
        update_dict["is_active"] = update_data.is_active
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Update promo code
    db.promo_codes.update_one(
        {"id": code_id},
        {"$set": update_dict}
    )
    
    # Get updated promo code
    updated_code = db.promo_codes.find_one({"id": code_id})
    updated_code.pop("_id", None)
    
    return {
        "message": "Promo code updated successfully",
        "promo_code": updated_code
    }


@router.delete("/promo-codes/{code_id}")
async def delete_promo_code(
    code_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a promo code (creator or admin only)
    """
    user_id = current_user.get("id")
    user_type = current_user.get("user_type")
    
    db = get_db()
    
    # Find promo code
    promo_code = db.promo_codes.find_one({"id": code_id})
    if not promo_code:
        raise HTTPException(status_code=404, detail="Promo code not found")
    
    # Check permission
    if user_type not in ["admin", "super_admin"] and promo_code.get("created_by") != user_id:
        raise HTTPException(status_code=403, detail="You can only delete your own promo codes")
    
    # Delete promo code
    db.promo_codes.delete_one({"id": code_id})
    
    return {"message": "Promo code deleted successfully"}
