from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
import os
from auth import get_current_user
from datetime import datetime
from typing import Optional
import uuid

router = APIRouter()

# Database
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


@router.post("/reservations/create")
async def create_reservation(
    reservation_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Rezervasyon oluştur"""
    try:
        facility_id = reservation_data.get("facility_id")
        field_id = reservation_data.get("field_id")
        date = reservation_data.get("date")
        time_slot = reservation_data.get("time_slot")
        duration = reservation_data.get("duration", 60)
        
        if not all([facility_id, field_id, date, time_slot]):
            raise HTTPException(status_code=400, detail="Eksik bilgi")
        
        # Sahayı kontrol et
        field = await db.facility_fields.find_one({"id": field_id})
        if not field:
            raise HTTPException(status_code=404, detail="Saha bulunamadı")
        
        # Ücret hesapla
        hourly_rate = field.get("hourly_rate", field.get("price_per_hour", 100))
        total_price = (duration / 60) * hourly_rate
        
        # Rezervasyon oluştur
        reservation = {
            "id": str(uuid.uuid4()),
            "user_id": current_user["id"],
            "user_name": current_user.get("name", "Kullanıcı"),
            "facility_id": facility_id,
            "field_id": field_id,
            "field_name": field.get("name", field.get("field_name", "Saha")),
            "date": date,
            "time_slot": time_slot,
            "duration_minutes": duration,
            "hourly_rate": hourly_rate,
            "total_price": total_price,
            "status": "pending",  # pending, confirmed, cancelled, completed
            "payment_status": "pending",  # pending, paid, failed, refunded
            "payment_method": reservation_data.get("payment_method", "credit_card"),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        await db.reservations.insert_one(reservation)
        reservation.pop("_id", None)
        
        # Bildirim gönder (tesis sahibine ve kullanıcıya)
        await send_reservation_notification(reservation, "created")
        
        # Rezervasyon oluşturma log'u
        try:
            from auth_endpoints import log_user_activity
            await log_user_activity(current_user["id"], "reservation_create", "success", {
                "reservation_id": reservation["id"],
                "facility_id": facility_id,
                "field_name": reservation["field_name"],
                "date": date,
                "time_slot": time_slot,
                "total_price": total_price
            })
        except Exception as e:
            print(f"Log error: {e}")
        
        return {
            "success": True,
            "reservation": reservation,
            "message": "Rezervasyon oluşturuldu. Ödeme bekleniyor."
        }
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reservations/{reservation_id}/confirm-payment")
async def confirm_payment(
    reservation_id: str,
    payment_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Ödeme onaylama (Sports Maker kredi kartı entegrasyonu)"""
    try:
        # Rezervasyonu bul
        reservation = await db.reservations.find_one({"id": reservation_id})
        if not reservation:
            raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
        
        if reservation["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Yetkisiz erişim")
        
        # Sports Maker kredi kartı entegrasyonu (MOCK)
        # Gerçek entegrasyon için Sports Maker API'si kullanılmalı
        payment_success = True  # Mock olarak başarılı
        
        if payment_success:
            # Rezervasyonu onayla
            await db.reservations.update_one(
                {"id": reservation_id},
                {
                    "$set": {
                        "status": "confirmed",
                        "payment_status": "paid",
                        "payment_date": datetime.utcnow().isoformat(),
                        "payment_details": payment_data,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                }
            )
            
            # Bildirim gönder
            await send_reservation_notification(reservation, "confirmed")
            
            return {
                "success": True,
                "message": "Ödeme başarılı! Rezervasyonunuz onaylandı.",
                "reservation_id": reservation_id
            }
        else:
            await db.reservations.update_one(
                {"id": reservation_id},
                {"$set": {"payment_status": "failed"}}
            )
            raise HTTPException(status_code=400, detail="Ödeme başarısız")
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reservations/my-reservations")
async def get_my_reservations(
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Kullanıcının rezervasyonları"""
    try:
        query = {"user_id": current_user["id"]}
        if status:
            query["status"] = status
        
        reservations = await db.reservations.find(query).sort("created_at", -1).to_list(100)
        
        for r in reservations:
            r.pop("_id", None)
        
        return {
            "success": True,
            "reservations": reservations
        }
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


async def send_reservation_notification(reservation: dict, action: str):
    """Rezervasyon bildirimi gönder"""
    try:
        # Tesis bilgilerini al
        facility = await db.facilities.find_one({"id": reservation["facility_id"]})
        if not facility:
            return
        
        owner_id = facility.get("owner_id")
        
        # Tesis sahibine bildirim
        if owner_id:
            owner_notification = {
                "id": str(uuid.uuid4()),
                "user_id": owner_id,
                "type": "reservation",
                "title": "Yeni Rezervasyon" if action == "created" else "Rezervasyon Onaylandı",
                "message": f"{reservation['field_name']} için yeni rezervasyon: {reservation['date']} - {reservation['time_slot']}",
                "data": {
                    "reservation_id": reservation["id"],
                    "facility_id": reservation["facility_id"],
                    "field_id": reservation["field_id"]
                },
                "is_read": False,
                "created_at": datetime.utcnow().isoformat()
            }
            await db.notifications.insert_one(owner_notification)
        
        # Kullanıcıya bildirim
        user_notification = {
            "id": str(uuid.uuid4()),
            "user_id": reservation["user_id"],
            "type": "reservation",
            "title": "Rezervasyon Oluşturuldu" if action == "created" else "Rezervasyon Onaylandı",
            "message": f"Rezervasyonunuz oluşturuldu: {reservation['field_name']} - {reservation['date']} {reservation['time_slot']}",
            "data": {
                "reservation_id": reservation["id"],
                "facility_id": reservation["facility_id"],
                "field_id": reservation["field_id"]
            },
            "is_read": False,
            "created_at": datetime.utcnow().isoformat()
        }
        await db.notifications.insert_one(user_notification)
        
        print(f"✉️ Bildirimler gönderildi: {action} - {reservation['id']}")
    
    except Exception as e:
        print(f"Bildirim gönderme hatası: {str(e)}")
