from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
import os
from auth import get_current_user
from datetime import datetime, timedelta

router = APIRouter()

# Database
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


@router.get("/management/my-facilities")
async def get_my_facilities_for_management(current_user: dict = Depends(get_current_user)):
    """Kullanıcının yönetim için tesislerini ve sahalarını getir"""
    try:
        user_id = current_user["id"]
        print(f"🏢 [Management] Kullanıcı {user_id} tesislerini getiriyor")
        
        # Kullanıcının approved tesislerini bul
        facilities = await db.facilities.find({
            "owner_id": user_id,
            "status": "approved"
        }).to_list(100)
        
        print(f"📋 [Management] Bulunan tesis sayısı: {len(facilities)}")
        
        result = []
        for facility in facilities:
            facility_id = facility["id"]
            
            # Bu tesisin sahalarını bul
            fields = await db.facility_fields.find({
                "facility_id": facility_id,
                "is_active": True
            }).to_list(100)
            
            # ObjectId'leri temizle
            for field in fields:
                field.pop("_id", None)
            
            # Her saha için süre kontrolü yap
            for field in fields:
                if field.get('active_session'):
                    session = field['active_session']
                    start_time_str = session['start_time']
                    # Timezone bilgisini kaldır
                    if 'T' in start_time_str:
                        start_time_str = start_time_str.split('+')[0].split('Z')[0].split('.')[0]
                    start_time = datetime.fromisoformat(start_time_str)
                    duration = session.get('duration_minutes', 60)
                    expected_end = start_time + timedelta(minutes=duration)
                    
                    # Süre aşımı kontrolü
                    now = datetime.utcnow()
                    is_overtime = now > expected_end
                    overtime_minutes = int((now - expected_end).total_seconds() / 60) if is_overtime else 0
                    
                    field['is_overtime'] = is_overtime
                    field['overtime_minutes'] = overtime_minutes
                    field['expected_end_time'] = expected_end.isoformat()
                else:
                    field['is_overtime'] = False
                    field['overtime_minutes'] = 0
            
            result.append({
                "id": facility_id,
                "name": facility["name"],
                "city": facility.get("city"),
                "district": facility.get("district"),
                "fields": fields
            })
        
        return {
            "success": True,
            "facilities": result
        }
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/management/fields/{field_id}/start-session")
async def start_field_session(
    field_id: str,
    session_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Saha için seans başlat"""
    try:
        # Başlangıç zamanını al (kullanıcı seçti)
        start_time_str = session_data.get('start_time')
        if start_time_str:
            start_time = datetime.fromisoformat(start_time_str)
        else:
            start_time = datetime.utcnow()
        
        duration_minutes = session_data.get('duration_minutes', 60)
        expected_end_time = start_time + timedelta(minutes=duration_minutes)
        
        active_session = {
            "player_names": session_data.get("player_names", []),
            "start_time": start_time.isoformat(),
            "expected_end_time": expected_end_time.isoformat(),
            "duration_minutes": duration_minutes,
            "base_price": session_data.get("price"),
            "payment_method": session_data.get("payment_method"),
            "is_paid": False,
            "overtime_price": 0,
            "total_collected": 0
        }
        
        result = await db.facility_fields.update_one(
            {"_id": field_id},
            {
                "$set": {
                    "is_occupied": True,
                    "active_session": active_session
                }
            }
        )
        
        return {"success": True, "message": "Seans başlatıldı"}
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/management/fields/{field_id}/end-session")
async def end_field_session(
    field_id: str,
    end_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Saha seansını bitir"""
    try:
        from bson import ObjectId
        
        # Saha bilgisini al - hem ObjectId hem UUID formatını destekle
        field = None
        try:
            field = await db.facility_fields.find_one({"_id": ObjectId(field_id)})
        except:
            pass
        
        if not field:
            field = await db.facility_fields.find_one({"id": field_id})
        if not field:
            field = await db.facility_fields.find_one({"_id": field_id})
        
        if not field or not field.get('active_session'):
            raise HTTPException(status_code=400, detail="Aktif seans bulunamadı")
        
        session = field['active_session']
        
        # Toplam tahsil edilen ücreti al
        total_collected = end_data.get('total_collected', session.get('base_price', 0))
        overtime_price = end_data.get('overtime_price', 0)
        payment_method = end_data.get('payment_method', session.get('payment_method', 'nakit'))
        
        # Update query hazırla
        update_query = {"_id": field.get("_id")} if field.get("_id") else {"id": field.get("id")}
        
        # Seansı güncelle ve bitir
        result = await db.facility_fields.update_one(
            update_query,
            {
                "$set": {
                    "is_occupied": False,
                    "active_session": None
                },
                "$push": {
                    "session_history": {
                        **session,
                        "end_time": datetime.utcnow().isoformat(),
                        "overtime_price": overtime_price,
                        "total_collected": total_collected,
                        "payment_method": payment_method,
                        "ended_by": current_user["id"]
                    }
                }
            }
        )
        
        print(f"✅ Seans bitirildi: {field_id}, Tutar: {total_collected} TL")
        
        return {
            "success": True, 
            "message": "Seans sonlandırıldı",
            "total_collected": total_collected
        }
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
