from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
import uuid
import logging

from models import (
    Facility, SportSettings, FacilitySport, FacilityAmenities, 
    FacilityPricing, WorkingHours, PricingRule, SpecialDayDiscount,
    DayType, Season, CustomerType, NotificationType, NotificationRelatedType,
    FacilityField
)
from auth import get_current_user

# Setup
router = APIRouter()
logger = logging.getLogger(__name__)

# Database
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Helper function for logging user activity
async def log_user_activity(user_id: str, action_type: str, details: dict = None):
    """Log user activity to user_logs collection"""
    try:
        log_entry = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "action_type": action_type,
            "details": details or {},
            "created_at": datetime.utcnow().isoformat(),
            "ip_address": None
        }
        await db.user_logs.insert_one(log_entry)
        logger.info(f"📝 Log created: {action_type} for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to log activity: {str(e)}")


# ==================== SPORT SETTINGS ENDPOINTS (Admin Only) ====================

@router.get("/admin/sport-settings")
async def get_sport_settings(
    current_user: dict = Depends(get_current_user)
):
    """Admin: Tüm spor ayarları şablonlarını getir"""
    try:
        # Admin kontrolü
        if current_user.get("user_type") not in ["admin", "super_admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için admin yetkisi gereklidir"
            )
        
        logger.info(f"🏃 Admin {current_user['id']} spor ayarlarını getiriyor")
        
        settings = await db.sport_settings.find({}).to_list(100)
        
        return {
            "success": True,
            "sport_settings": settings
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Spor ayarları getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/sport-settings")
async def create_sport_setting(
    sport_setting: SportSettings,
    current_user: dict = Depends(get_current_user)
):
    """Admin: Yeni spor ayarı şablonu oluştur"""
    try:
        # Admin kontrolü
        if current_user.get("user_type") not in ["admin", "super_admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için admin yetkisi gereklidir"
            )
        
        logger.info(f"🏃 Admin {current_user['id']} spor ayarı oluşturuyor: {sport_setting.sport_name}")
        
        # ID oluştur
        sport_setting.id = str(uuid.uuid4())
        sport_setting.created_at = datetime.utcnow()
        sport_setting.updated_at = datetime.utcnow()
        
        # Kaydet
        await db.sport_settings.insert_one(sport_setting.dict())
        
        return {
            "success": True,
            "message": "Spor ayarı başarıyla oluşturuldu",
            "sport_setting": sport_setting.dict()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Spor ayarı oluşturma hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/admin/sport-settings/{setting_id}")
async def update_sport_setting(
    setting_id: str,
    sport_setting: SportSettings,
    current_user: dict = Depends(get_current_user)
):
    """Admin: Spor ayarı şablonunu güncelle"""
    try:
        # Admin kontrolü
        if current_user.get("user_type") not in ["admin", "super_admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için admin yetkisi gereklidir"
            )
        
        logger.info(f"🏃 Admin {current_user['id']} spor ayarını güncelliyor: {setting_id}")
        
        # Güncelle
        sport_setting.id = setting_id
        sport_setting.updated_at = datetime.utcnow()
        
        result = await db.sport_settings.update_one(
            {"id": setting_id},
            {"$set": sport_setting.dict(exclude_unset=True)}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Spor ayarı bulunamadı")
        
        return {
            "success": True,
            "message": "Spor ayarı başarıyla güncellendi"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Spor ayarı güncelleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/sport-settings/{setting_id}")
async def delete_sport_setting(
    setting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Admin: Spor ayarı şablonunu sil"""
    try:
        # Admin kontrolü
        if current_user.get("user_type") not in ["admin", "super_admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için admin yetkisi gereklidir"
            )
        
        logger.info(f"🏃 Admin {current_user['id']} spor ayarını siliyor: {setting_id}")
        
        result = await db.sport_settings.delete_one({"id": setting_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Spor ayarı bulunamadı")
        
        return {
            "success": True,
            "message": "Spor ayarı başarıyla silindi"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Spor ayarı silme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== FACILITY ENDPOINTS (All Users) ====================

@router.get("/facilities/approved")
async def get_approved_facilities(
    city: Optional[str] = None,
    sport: Optional[str] = None
):
    """Onaylanmış tesisleri getir (rezervasyon için - auth gerekmez, misafir kullanıcılar da görebilir)"""
    try:
        logger.info(f"🏢 Onaylanmış tesisler getiriliyor - Şehir: {city}, Spor: {sport}")
        
        # Sadece approved VE is_published=true tesisler
        query = {
            "status": "approved",
            "is_published": True
        }
        
        if city:
            query["city"] = city
        
        facilities = await db.facilities.find(query).to_list(500)
        
        # Spor filtrelemesi
        if sport:
            filtered_facilities = []
            for f in facilities:
                sports = f.get("sports", [])
                # sports array'i string veya object olabilir
                sport_names = []
                for s in sports:
                    if isinstance(s, str):
                        sport_names.append(s)
                    elif isinstance(s, dict):
                        sport_names.append(s.get("name", "") or s.get("sport_type", "") or s.get("sport_name", ""))
                
                # Case-insensitive karşılaştırma
                if any(sport.lower() in sn.lower() for sn in sport_names):
                    filtered_facilities.append(f)
            
            facilities = filtered_facilities
        
        # Her tesis için en düşük saatlik ücreti hesapla
        for facility in facilities:
            facility.pop("_id", None)
            
            # Sahalardan en düşük fiyatı bul
            fields = await db.facility_fields.find({"facility_id": facility["id"]}).to_list(100)
            if fields:
                rates = [field.get("hourly_rate") for field in fields if field.get("hourly_rate")]
                if rates:
                    facility["min_hourly_rate"] = min(rates)
                else:
                    # Saha fiyatı yoksa tesis pricing'den al
                    pricing = facility.get("pricing", {})
                    facility["min_hourly_rate"] = pricing.get("hourly_rate", 0) if isinstance(pricing, dict) else 0
            else:
                # Saha yoksa tesisteki genel fiyatı kullan
                pricing = facility.get("pricing", {})
                facility["min_hourly_rate"] = pricing.get("hourly_rate", 0) if isinstance(pricing, dict) else 0
        
        logger.info(f"✅ {len(facilities)} onaylanmış tesis bulundu")
        return {
            "success": True,
            "facilities": facilities,
            "count": len(facilities)
        }
    
    except Exception as e:
        logger.error(f"❌ Onaylanmış tesis getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/facilities/my-facilities")
async def get_my_facilities(
    current_user: dict = Depends(get_current_user)
):
    """Kullanıcının kendi tesislerini getir (tesis yönetimi için)"""
    try:
        user_id = current_user["id"]
        user_type = current_user.get("user_type", "")
        logger.info(f"🏢 Kullanıcı {user_id} ({user_type}) tesislerini getiriyor")
        
        # DEBUG: Kullanıcı bilgilerini logla
        user = await db.users.find_one({"id": user_id})
        if user:
            logger.info(f"🔍 DEBUG - Kullanıcı: {user.get('full_name')}, Email: {user.get('email')}, Type: {user.get('user_type')}")
        else:
            logger.warning(f"⚠️ DEBUG - Kullanıcı bulunamadı: {user_id}")
        
        # Admin veya facility_owner ise kendi tesislerini getir
        # Kullanıcının sahibi olduğu tesisler
        facilities = await db.facilities.find({"owner_id": user_id}).to_list(100)
        logger.info(f"📋 DEBUG - owner_id={user_id} ile bulunan tesis sayısı: {len(facilities)}")
        
        # Admin ise ve tesis bulunamadıysa, user'ın email'iyle eşleşen owner'ları da kontrol et
        if len(facilities) == 0 and user and user.get("user_type") == "admin":
            # Belki owner_id farklı formatta saklanmış olabilir
            all_facilities = await db.facilities.find().to_list(100)
            logger.info(f"📋 DEBUG - Toplam tesis sayısı: {len(all_facilities)}")
            for f in all_facilities[:5]:  # İlk 5 tesisi logla
                logger.info(f"   - {f.get('name')}: owner_id={f.get('owner_id')}")
        
        # Kulüp yöneticisi ise kulübün tesislerini de ekle
        if user_type == "club_manager":
            # Kullanıcının yönettiği kulüpleri bul
            clubs = await db.clubs.find({
                "$or": [
                    {"owner_id": user_id},
                    {"manager_ids": user_id},
                    {"admin_ids": user_id}
                ]
            }).to_list(50)
            
            club_ids = [club.get("id") for club in clubs]
            
            if club_ids:
                # Kulüplere ait tesisleri bul
                club_facilities = await db.facilities.find({
                    "club_id": {"$in": club_ids}
                }).to_list(100)
                
                # Mevcut tesis ID'leri (duplikasyon önleme)
                existing_ids = {f.get("id") for f in facilities}
                
                for cf in club_facilities:
                    if cf.get("id") not in existing_ids:
                        facilities.append(cf)
        
        # Remove MongoDB _id field for JSON serialization
        for facility in facilities:
            facility.pop("_id", None)
        
        return {
            "success": True,
            "facilities": facilities
        }
    
    except Exception as e:
        logger.error(f"❌ Tesis getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/facilities/{facility_id}")
async def get_facility(facility_id: str):
    """Tesis detayını getir (herkese açık)"""
    try:
        logger.info(f"🏢 Tesis detayı getiriliyor: {facility_id}")
        
        facility = await db.facilities.find_one({"id": facility_id})
        
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Görüntülenme sayısını artır
        await db.facilities.update_one(
            {"id": facility_id},
            {"$inc": {"views_count": 1}}
        )
        
        # Remove MongoDB _id field for JSON serialization
        facility.pop("_id", None)
        
        # working_hours'u available_hours formatına çevir (rezervasyon uyumluluğu için)
        if facility.get("working_hours") and not facility.get("available_hours"):
            working_hours = facility["working_hours"]
            available_hours = {}
            
            # Eğer working_hours object ise
            if isinstance(working_hours, dict):
                for day, hours in working_hours.items():
                    # hours format: "09:00-22:00" veya ["09:00-22:00"]
                    if isinstance(hours, str):
                        available_hours[day.lower()] = [hours]
                    elif isinstance(hours, list):
                        available_hours[day.lower()] = hours
            
            facility["available_hours"] = available_hours
        
        # Tesisin sahalarını da ekle (rezervasyon için)
        fields = await db.facility_fields.find({"facility_id": facility_id}).to_list(100)
        for field in fields:
            field.pop("_id", None)
        
        facility["fields"] = fields
        
        # En düşük saatlik ücreti hesapla
        if fields:
            rates = [field.get("hourly_rate") for field in fields if field.get("hourly_rate")]
            if rates:
                facility["min_hourly_rate"] = min(rates)
            else:
                pricing = facility.get("pricing", {})
                facility["min_hourly_rate"] = pricing.get("hourly_rate", 0) if isinstance(pricing, dict) else 0
        else:
            pricing = facility.get("pricing", {})
            facility["min_hourly_rate"] = pricing.get("hourly_rate", 0) if isinstance(pricing, dict) else 0
        
        return {
            "success": True,
            "facility": facility
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Tesis detayı getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/facilities")
async def get_published_facilities(
    city: Optional[str] = None,
    sport: Optional[str] = None,
    skip: int = 0,
    limit: int = 20
):
    """Yayınlanmış tesisleri getir (herkese açık)"""
    try:
        logger.info(f"🏢 Yayınlanmış tesisler getiriliyor")
        
        query = {"is_published": True}
        
        if city:
            query["city"] = city
        
        if sport:
            query["sports.sport_name"] = sport
        
        facilities = await db.facilities.find(query).skip(skip).limit(limit).to_list(limit)
        total = await db.facilities.count_documents(query)
        
        # _id alanlarını kaldır
        for facility in facilities:
            facility.pop("_id", None)
        
        return {
            "success": True,
            "facilities": facilities,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    
    except Exception as e:
        logger.error(f"❌ Tesisler getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def auto_create_fields_from_sports(db, facility_id: str, sports: list):
    """Tesisteki spor dallarına göre otomatik sahalar oluştur"""
    try:
        logger.info(f"🏗️ Otomatik saha oluşturma: {facility_id}")
        created_count = 0
        
        for sport in sports:
            # Sport string veya FacilitySport object olabilir
            if isinstance(sport, dict):
                sport_name = sport.get('sport_name', sport.get('name', ''))
                area_count = sport.get('area_count', sport.get('field_count', 1))
            elif isinstance(sport, str):
                sport_name = sport
                area_count = 1
            else:
                continue
            
            # Her spor için area_count kadar saha oluştur
            for i in range(1, area_count + 1):
                field_id = str(uuid.uuid4())
                field_data = {
                    "id": field_id,
                    "facility_id": facility_id,
                    "field_name": f"{sport_name} Sahası {i}" if area_count > 1 else f"{sport_name} Sahası",
                    "sport_type": sport_name,
                    "field_type": "standard",
                    "is_occupied": False,
                    "is_available_for_booking": True,
                    "hourly_rate": None,  # Kullanıcı sonra girecek
                    "discount_percentage": 0.0,
                    "current_reservation": None,
                    "active_session": None,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "is_active": True
                }
                
                await db.facility_fields.insert_one(field_data)
                created_count += 1
                logger.info(f"  ✅ Saha oluşturuldu: {field_data['field_name']}")
        
        logger.info(f"✅ Toplam {created_count} saha oluşturuldu")
        return created_count
    except Exception as e:
        logger.error(f"❌ Otomatik saha oluşturma hatası: {str(e)}")
        return 0


@router.post("/facilities")
async def create_facility(
    facility: Facility,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Yeni tesis oluştur"""
    try:
        db = request.app.state.db
        
        logger.info(f"🏢 Kullanıcı {current_user['id']} yeni tesis oluşturuyor: {facility.name}")
        print(f"🏢 DEBUG: Kullanıcı {current_user['id']} yeni tesis oluşturuyor: {facility.name}")
        
        # Negatif fiyat kontrolü
        facility_dict = facility.dict()
        for field_data in facility_dict.get("fields", []):
            if field_data.get("hourly_rate") is not None and field_data.get("hourly_rate") < 0:
                raise HTTPException(status_code=400, detail="Saha saatlik ücreti negatif olamaz")
            if field_data.get("price") is not None and field_data.get("price") < 0:
                raise HTTPException(status_code=400, detail="Saha fiyatı negatif olamaz")
        
        # ID oluştur ve owner_id ata
        facility.id = str(uuid.uuid4())
        facility.owner_id = current_user["id"]
        facility.created_at = datetime.utcnow()
        facility.updated_at = datetime.utcnow()
        facility.status = "pending"  # Varsayılan: onay bekliyor
        
        # Kaydet
        await db.facilities.insert_one(facility.dict())
        print(f"✅ DEBUG: Tesis kaydedildi: {facility.id}")
        
        # Otomatik sahalar oluştur
        if facility.sports and len(facility.sports) > 0:
            fields_created = await auto_create_fields_from_sports(db, facility.id, facility.sports)
            print(f"🏗️ DEBUG: {fields_created} saha otomatik oluşturuldu")
        
        # Admin'lere bildirim gönder
        admin_ids = await get_admin_users(db)
        print(f"👥 DEBUG: Admin IDs: {admin_ids}")
        
        notification_count = 0
        for admin_id in admin_ids:
            notification_data = {
                "id": str(uuid.uuid4()),
                "user_id": admin_id,
                "type": NotificationType.ADMIN_ACTION.value,
                "title": "Yeni Tesis Onay Bekliyor",
                "message": f"'{facility.name}' adlı yeni tesis onayınızı bekliyor.",
                "related_type": NotificationRelatedType.FACILITY.value,
                "related_id": facility.id,
                "data": {
                    "facility_id": facility.id,
                    "facility_name": facility.name,
                    "owner_id": current_user["id"]
                },
                "read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(notification_data)
            notification_count += 1
            print(f"📧 DEBUG: Bildirim gönderildi -> {admin_id}")
        
        logger.info(f"✅ Tesis oluşturuldu ve {notification_count} admin'e bildirim gönderildi")
        print(f"✅ DEBUG: TOPLAM {notification_count} admin'e bildirim gönderildi")
        
        return {
            "success": True,
            "message": "Tesis başarıyla oluşturuldu ve onay için gönderildi",
            "facility": facility.dict()
        }
    
    except Exception as e:
        logger.error(f"❌ Tesis oluşturma hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/facilities/{facility_id}/pricing-table")
async def get_facility_pricing_table(
    facility_id: str,
    request: Request
):
    """Tesisin tüm sahalar için fiyat tablosunu getir"""
    try:
        db = request.app.state.db
        
        # Tesisi al
        facility = await db.facilities.find_one({"id": facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Sahaları al
        fields_cursor = db.facility_fields.find({"facility_id": facility_id, "is_active": True})
        fields = await fields_cursor.to_list(100)
        
        # pricing_v2 al
        pricing_v2 = facility.get("pricing_v2", {})
        
        if not pricing_v2 or not pricing_v2.get("use_dynamic_pricing_v2"):
            # Dinamik fiyatlandırma yok, sabit fiyatlar göster
            pricing_table = []
            for field in fields:
                pricing_table.append({
                    "field_name": field.get("name") or field.get("field_name"),
                    "weekday": {
                        "morning": field.get("hourly_rate", 0),
                        "afternoon": field.get("hourly_rate", 0),
                        "evening": field.get("hourly_rate", 0),
                        "night": field.get("hourly_rate", 0),
                    },
                    "weekend": {
                        "morning": field.get("hourly_rate", 0),
                        "afternoon": field.get("hourly_rate", 0),
                        "evening": field.get("hourly_rate", 0),
                        "night": field.get("hourly_rate", 0),
                    }
                })
            return {"success": True, "pricing_table": pricing_table, "is_dynamic": False}
        
        # Dinamik fiyatlandırma var
        base_prices = pricing_v2.get("base_prices", {})
        same_for_all = pricing_v2.get("same_for_all_fields", True)
        field_multipliers = pricing_v2.get("field_multipliers", {})
        dead_period_mult = pricing_v2.get("dead_period_multiplier", 1.0)
        weekend_mult = pricing_v2.get("weekend_time_multipliers", {})
        
        pricing_table = []
        for idx, field in enumerate(fields, 1):
            # Saha çarpanı
            if same_for_all:
                field_mult = 1.0
            else:
                field_mult = float(field_multipliers.get(str(idx), 1.0))
            
            # Hafta içi fiyatlar
            weekday_prices = {
                "morning": round(float(base_prices.get("morning", 0)) * field_mult * dead_period_mult, 2),
                "afternoon": round(float(base_prices.get("afternoon", 0)) * field_mult * dead_period_mult, 2),
                "evening": round(float(base_prices.get("evening", 0)) * field_mult * dead_period_mult, 2),
                "night": round(float(base_prices.get("night", 0)) * field_mult * dead_period_mult, 2),
            }
            
            # Hafta sonu fiyatlar
            weekend_prices = {
                "morning": round(float(base_prices.get("morning", 0)) * field_mult * float(weekend_mult.get("morning", 1.0)) * dead_period_mult, 2),
                "afternoon": round(float(base_prices.get("afternoon", 0)) * field_mult * float(weekend_mult.get("afternoon", 1.0)) * dead_period_mult, 2),
                "evening": round(float(base_prices.get("evening", 0)) * field_mult * float(weekend_mult.get("evening", 1.0)) * dead_period_mult, 2),
                "night": round(float(base_prices.get("night", 0)) * field_mult * float(weekend_mult.get("night", 1.0)) * dead_period_mult, 2),
            }
            
            pricing_table.append({
                "field_name": field.get("name") or field.get("field_name"),
                "weekday": weekday_prices,
                "weekend": weekend_prices
            })
        
        return {
            "success": True,
            "pricing_table": pricing_table,
            "is_dynamic": True
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Pricing table error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/facilities/{facility_id}/pricing-v2")
async def update_facility_pricing_v2(
    facility_id: str,
    pricing_data: dict,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Tesisin yeni dinamik fiyatlandırmasını güncelle"""
    try:
        db = request.app.state.db
        
        # Tesis sahibi kontrolü
        facility = await db.facilities.find_one({"id": facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        if facility["owner_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        # pricing_v2 field'ını güncelle
        await db.facilities.update_one(
            {"id": facility_id},
            {"$set": {"pricing_v2": pricing_data, "updated_at": datetime.utcnow()}}
        )
        
        logger.info(f"✅ Tesis {facility_id} pricing_v2 güncellendi")
        
        return {
            "success": True,
            "message": "Fiyatlandırma başarıyla güncellendi"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Pricing V2 güncelleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/facilities/{facility_id}")
async def update_facility(
    facility_id: str,
    facility: Facility,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Tesisi güncelle"""
    logger.info(f"🚀 PUT /facilities/{facility_id} ENDPOINT BAŞLADI")
    try:
        db = request.app.state.db
        
        logger.info(f"🏢 Kullanıcı {current_user['id']} tesisi güncelliyor: {facility_id}")
        
        # Negatif fiyat kontrolü
        facility_dict = facility.dict()
        for field_data in facility_dict.get("fields", []):
            if field_data.get("hourly_rate") is not None and field_data.get("hourly_rate") < 0:
                raise HTTPException(status_code=400, detail="Saha saatlik ücreti negatif olamaz")
            if field_data.get("price") is not None and field_data.get("price") < 0:
                raise HTTPException(status_code=400, detail="Saha fiyatı negatif olamaz")
            if field_data.get("match_price") is not None and field_data.get("match_price") < 0:
                raise HTTPException(status_code=400, detail="Maç başı ücreti negatif olamaz")
        
        # Tesis sahibi kontrolü
        existing_facility = await db.facilities.find_one({"id": facility_id})
        
        if not existing_facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        if existing_facility["owner_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu tesisi güncelleme yetkiniz yok"
            )
        
        # Güncelle
        facility.id = facility_id
        facility.owner_id = current_user["id"]
        facility.updated_at = datetime.utcnow()
        
        # Eğer tesis reddedildiyse, düzenlemeden sonra tekrar pending yap
        if existing_facility.get("status") == "rejected":
            facility.status = "pending"
            facility.rejection_reason = None
            
            # Admin'lere tekrar bildirim gönder
            admin_ids = await get_admin_users(db)
            for admin_id in admin_ids:
                notification_data = {
                    "id": str(uuid.uuid4()),
                    "user_id": admin_id,
                    "type": NotificationType.ADMIN_ACTION.value,
                    "title": "Düzenlenen Tesis Tekrar Onay Bekliyor",
                    "message": f"'{facility.name}' adlı tesis düzenlendi ve tekrar onayınızı bekliyor.",
                    "related_type": NotificationRelatedType.FACILITY.value,
                    "related_id": facility.id,
                    "data": {
                        "facility_id": facility.id,
                        "facility_name": facility.name,
                        "owner_id": current_user["id"]
                    },
                    "read": False,
                    "created_at": datetime.utcnow()
                }
                await db.notifications.insert_one(notification_data)
        
        # Direkt güncelleme - Pydantic model'den dict'e çevir
        update_data = facility.dict(exclude_unset=True)  # CRITICAL: Sadece set edilen field'ları al
        update_data["updated_at"] = datetime.utcnow()
        
        # CRITICAL FIX: Eğer pricing gönderilmişse ama pricing_rules boşsa, mevcut kuralları koru
        if "pricing" in update_data:
            incoming_pricing = update_data["pricing"]
            # Eğer pricing_rules boş veya yok ama mevcut tesiste var ise, eski kuralları koru
            if not incoming_pricing.get("pricing_rules") and existing_facility.get("pricing", {}).get("pricing_rules"):
                logger.warning(f"⚠️ Pricing rules korunuyor! Frontend boş göndermiş.")
                update_data["pricing"]["pricing_rules"] = existing_facility["pricing"]["pricing_rules"]
        
        # CRITICAL: pricing_v2 field'ını da koru (yeni dinamik fiyatlandırma sistemi)
        if "pricing_v2" in update_data:
            logger.info(f"💰 Pricing V2 update: {update_data.get('pricing_v2')}")
        
        logger.info(f"🔧 Güncelleme datası: allow_membership={update_data.get('allow_membership')}, daily={update_data.get('daily_membership_fee')}, monthly={update_data.get('monthly_membership_fee')}, yearly={update_data.get('yearly_membership_fee')}")
        logger.info(f"💰 Pricing update: use_dynamic={update_data.get('pricing', {}).get('use_dynamic_pricing')}, rules_count={len(update_data.get('pricing', {}).get('pricing_rules', []))}")
        
        await db.facilities.update_one(
            {"id": facility_id},
            {"$set": update_data}
        )
        
        logger.info(f"✅ Veritabanı güncellendi")
        
        # CRITICAL: sports değişikliklerini algıla ve facility_fields'ı senkronize et
        if "sports" in update_data:
            logger.info(f"🔄 Sports değişti, facility_fields senkronize ediliyor...")
            
            new_sports = update_data.get("sports", [])
            old_sports = existing_facility.get("sports", [])
            
            # Mevcut sahaları al
            existing_fields = await db.facility_fields.find({
                "facility_id": facility_id, 
                "is_active": True
            }).to_list(1000)
            
            # Yeni sporlardan beklenen toplam saha sayısı
            expected_fields = []
            for sport in new_sports:
                if isinstance(sport, dict):
                    sport_name = sport.get('sport_name', '')
                    area_count = sport.get('area_count', 1)
                    for i in range(1, area_count + 1):
                        field_name = f"{sport_name} Sahası {i}" if area_count > 1 else f"{sport_name} Sahası"
                        expected_fields.append({
                            "sport_name": sport_name,
                            "field_name": field_name,
                            "index": i
                        })
            
            # Mevcut sahaları spor adına göre grupla
            existing_by_sport = {}
            for field in existing_fields:
                sport_type = field.get("sport_type") or field.get("sport", "")
                if sport_type not in existing_by_sport:
                    existing_by_sport[sport_type] = []
                existing_by_sport[sport_type].append(field)
            
            # Yeni sporları kontrol et, eksik sahaları ekle
            pricing = existing_facility.get("pricing", {})
            default_hourly_rate = pricing.get("hourly_rate", 100)
            
            for sport in new_sports:
                if isinstance(sport, dict):
                    sport_name = sport.get('sport_name', '')
                    area_count = sport.get('area_count', 1)
                    
                    # Bu spor için mevcut sahalar
                    current_sport_fields = existing_by_sport.get(sport_name, [])
                    current_count = len(current_sport_fields)
                    
                    if current_count < area_count:
                        # Eksik sahaları ekle
                        for i in range(current_count + 1, area_count + 1):
                            field_name = f"{sport_name} Sahası {i}" if area_count > 1 else f"{sport_name} Sahası"
                            field_doc = {
                                "id": str(uuid.uuid4()),
                                "facility_id": facility_id,
                                "name": field_name,
                                "field_name": field_name,
                                "sport": sport_name,
                                "sport_type": sport_name,
                                "field_type": "indoor",
                                "is_active": True,
                                "is_occupied": False,
                                "is_available_for_booking": True,
                                "hourly_rate": default_hourly_rate,
                                "discount_percentage": 0,
                                "created_at": datetime.utcnow()
                            }
                            await db.facility_fields.insert_one(field_doc)
                            logger.info(f"➕ Yeni saha eklendi: {field_name}")
                    elif current_count > area_count:
                        # Fazla sahaları deaktive et (sil değil)
                        fields_to_remove = current_sport_fields[area_count:]
                        for field in fields_to_remove:
                            await db.facility_fields.update_one(
                                {"id": field.get("id")},
                                {"$set": {"is_active": False}}
                            )
                            logger.info(f"🗑️ Saha deaktive edildi: {field.get('name')}")
            
            # Kaldırılan sporların sahalarını deaktive et
            new_sport_names = [s.get('sport_name', '') for s in new_sports if isinstance(s, dict)]
            for sport_name, fields in existing_by_sport.items():
                if sport_name not in new_sport_names:
                    for field in fields:
                        await db.facility_fields.update_one(
                            {"id": field.get("id")},
                            {"$set": {"is_active": False}}
                        )
                        logger.info(f"🗑️ Spor kaldırıldı, saha deaktive edildi: {field.get('name')}")
            
            logger.info(f"✅ Sports-fields senkronizasyonu tamamlandı")
        
        # CRITICAL: facility_fields koleksiyonunu da senkronize et (fields array ile)
        elif "fields" in update_data:
            logger.info(f"🔄 facility_fields koleksiyonu senkronize ediliyor...")
            
            # Güncel field ID'lerini al
            current_fields = update_data.get("fields", [])
            current_field_ids = [f.get("id") for f in current_fields if f.get("id")]
            
            # Mevcut facility_fields'daki bu tesise ait kayıtları sil
            delete_result = await db.facility_fields.delete_many({"facility_id": facility_id})
            logger.info(f"🗑️ Eski facility_fields silindi: {delete_result.deleted_count}")
            
            # Yeni field'ları ekle
            for field in current_fields:
                if field.get("id"):
                    field_doc = {
                        "id": field.get("id"),
                        "facility_id": facility_id,
                        "name": field.get("name"),
                        "sport_type": field.get("sport_type"),
                        "capacity": field.get("capacity", 10),
                        "hourly_price": field.get("hourly_price", 100),
                        "surface_type": field.get("surface_type", "Standart"),
                        "is_indoor": field.get("is_indoor", True),
                        "is_active": True,
                        "status": "active",
                        "amenities": field.get("amenities", []),
                        "description": field.get("description", "")
                    }
                    await db.facility_fields.insert_one(field_doc)
                    logger.info(f"➕ Saha eklendi: {field.get('name')}")
            
            logger.info(f"✅ facility_fields senkronizasyonu tamamlandı")
        
        return {
            "success": True,
            "message": "Tesis başarıyla güncellendi"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Tesis güncelleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/facilities/{facility_id}")
async def delete_facility(
    facility_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Tesisi sil"""
    try:
        logger.info(f"🏢 Kullanıcı {current_user['id']} tesisi siliyor: {facility_id}")
        
        # Tesis sahibi kontrolü
        existing_facility = await db.facilities.find_one({"id": facility_id})
        
        if not existing_facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        if existing_facility["owner_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu tesisi silme yetkiniz yok"
            )
        
        # Sil
        await db.facilities.delete_one({"id": facility_id})
        
        return {
            "success": True,
            "message": "Tesis başarıyla silindi"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Tesis silme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



# ==================== DYNAMIC PRICING CALCULATION ====================

@router.post("/facilities/{facility_id}/calculate-price")
async def calculate_dynamic_price(
    facility_id: str,
    sport_name: str,
    field_number: int,
    booking_date: str,  # "2025-12-25" formatında
    time_slot: str,  # "18:00-22:00" formatında
    customer_type: str = "general"  # general, student, trainer, retired, female
):
    """
    Dinamik fiyatlandırma hesaplama endpoint'i.
    Verilen parametrelere göre final fiyatı hesaplar.
    """
    try:
        logger.info(f"💰 Fiyat hesaplama: {facility_id}, {sport_name}, Saha {field_number}, {booking_date}, {time_slot}, {customer_type}")
        
        # Tesisi getir
        facility = await db.facilities.find_one({"id": facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        pricing = facility.get("pricing", {})
        
        # Basit fiyatlandırma mı yoksa dinamik mi?
        if not pricing.get("use_dynamic_pricing", False):
            # Basit fiyatlandırma
            base_price = pricing.get("hourly_rate", 0)
            return {
                "success": True,
                "pricing_type": "simple",
                "base_price": base_price,
                "final_price": base_price,
                "calculation_details": "Basit fiyatlandırma (saatlik fiyat)"
            }
        
        # Dinamik fiyatlandırma
        pricing_rules = pricing.get("pricing_rules", [])
        special_discounts = pricing.get("special_day_discounts", [])
        
        # Tarihi parse et
        from datetime import datetime as dt
        booking_dt = dt.strptime(booking_date, "%Y-%m-%d")
        
        # Gün tipini belirle (weekday/weekend)
        day_of_week = booking_dt.weekday()  # 0=Monday, 6=Sunday
        is_weekend = day_of_week >= 5  # 5=Saturday, 6=Sunday
        day_type = "weekend" if is_weekend else "weekday"
        
        # Sezonu belirle (aydan)
        month = booking_dt.month
        if 3 <= month <= 5:
            season = "spring"
        elif 6 <= month <= 8:
            season = "summer"
        elif 9 <= month <= 11:
            season = "fall"
        else:
            season = "winter"
        
        # İlgili kuralı bul
        matching_rule = None
        for rule in pricing_rules:
            if (rule.get("sport_name") == sport_name and
                rule.get("field_number") == field_number and
                rule.get("day_type") == day_type and
                rule.get("time_slot") == time_slot and
                rule.get("season") == season and
                rule.get("is_active", True)):
                matching_rule = rule
                break
        
        if not matching_rule:
            # Kural bulunamadı, varsayılan fiyat
            return {
                "success": False,
                "message": "Bu kombinasyon için fiyat kuralı bulunamadı",
                "pricing_type": "dynamic",
                "parameters": {
                    "sport": sport_name,
                    "field": field_number,
                    "day_type": day_type,
                    "time_slot": time_slot,
                    "season": season
                }
            }
        
        # Fiyat hesaplama
        base_price = matching_rule.get("base_price", 0)
        seasonal_multiplier = matching_rule.get("seasonal_multiplier", 1.0)
        
        # Sezon çarpanı uygula
        price_after_season = base_price * seasonal_multiplier
        
        # Kullanıcı tipi indirimi uygula
        customer_discounts = matching_rule.get("customer_discounts", {})
        discount_percentage = customer_discounts.get(customer_type, 0)
        discount_amount = price_after_season * (discount_percentage / 100)
        price_after_discount = price_after_season - discount_amount
        
        # Özel gün indirimi kontrol et
        special_discount = 0
        special_discount_desc = None
        for special_day in special_discounts:
            if (special_day.get("date") == booking_date and
                special_day.get("is_active", True)):
                special_discount = special_day.get("discount_percentage", 0)
                special_discount_desc = special_day.get("description", "Özel gün indirimi")
                break
        
        if special_discount > 0:
            special_discount_amount = price_after_discount * (special_discount / 100)
            final_price = price_after_discount - special_discount_amount
        else:
            final_price = price_after_discount
        
        # Hesaplama detayları
        calculation_details = {
            "base_price": base_price,
            "seasonal_multiplier": seasonal_multiplier,
            "price_after_season": price_after_season,
            "customer_type": customer_type,
            "customer_discount_percentage": discount_percentage,
            "price_after_customer_discount": price_after_discount,
            "special_discount_percentage": special_discount,
            "special_discount_description": special_discount_desc,
            "final_price": final_price
        }
        
        return {
            "success": True,
            "pricing_type": "dynamic",
            "final_price": round(final_price, 2),
            "calculation_details": calculation_details,
            "rule_used": {
                "sport": sport_name,
                "field_number": field_number,
                "day_type": day_type,
                "time_slot": time_slot,
                "season": season
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Fiyat hesaplama hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



# ==================== FACILITY APPROVAL ENDPOINTS (Admin Only) ====================

async def get_admin_users(db):
    """Admin ve super_admin tipindeki kullanıcıları getir"""
    try:
        # user_type='admin' veya 'super_admin' olan kullanıcıları bul
        admin_users = await db.users.find({
            "user_type": {"$in": ["admin", "super_admin"]}
        }).to_list(100)
        logger.info(f"🔍 Admin tipinde kullanıcı sayısı: {len(admin_users)}")
        
        admin_ids = [u["id"] for u in admin_users]
        logger.info(f"👥 Admin ID listesi: {admin_ids}")
        
        return admin_ids
    except Exception as e:
        logger.error(f"❌ Admin kullanıcıları getirme hatası: {str(e)}")
        return []


@router.post("/facilities/{facility_id}/approve")
async def approve_facility(
    facility_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Admin: Tesisi onayla"""
    try:
        db = request.app.state.db
        
        # Admin kontrolü
        admin_ids = await get_admin_users(db)
        if current_user["id"] not in admin_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için admin yetkisi gereklidir"
            )
        
        # Tesisi bul
        facility = await db.facilities.find_one({"id": facility_id})
        
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Onay işlemi
        await db.facilities.update_one(
            {"id": facility_id},
            {
                "$set": {
                    "status": "approved",
                    "approved_by": current_user["id"],
                    "approved_at": datetime.utcnow(),
                    "rejection_reason": None,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # OTOMATİK SAHA OLUŞTURMA - Tesis onaylandığında
        await _create_fields_for_facility(facility, db)
        
        # Tesis sahibine bildirim gönder
        notification_data = {
            "id": str(uuid.uuid4()),
            "user_id": facility["owner_id"],
            "type": NotificationType.FACILITY_APPROVED.value,
            "title": "Tesisiniz Onaylandı!",
            "message": f"'{facility['name']}' adlı tesisiniz yönetici tarafından onaylandı ve yayınlandı.",
            "related_type": NotificationRelatedType.FACILITY.value,
            "related_id": facility_id,
            "data": {"facility_id": facility_id, "facility_name": facility["name"]},
            "read": False,
            "created_at": datetime.utcnow()
        }
        
        await db.notifications.insert_one(notification_data)
        
        logger.info(f"✅ Tesis onaylandı: {facility_id} - Admin: {current_user['id']}")
        
        return {
            "success": True,
            "message": "Tesis başarıyla onaylandı",
            "facility_id": facility_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Tesis onaylama hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/facilities/{facility_id}/reject")
async def reject_facility(
    facility_id: str,
    rejection_reason: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Admin: Tesisi reddet"""
    try:
        db = request.app.state.db
        
        # Admin kontrolü
        admin_ids = await get_admin_users(db)
        if current_user["id"] not in admin_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için admin yetkisi gereklidir"
            )
        
        if not rejection_reason or rejection_reason.strip() == "":
            raise HTTPException(
                status_code=400,
                detail="Red sebebi belirtilmelidir"
            )
        
        # Tesisi bul
        facility = await db.facilities.find_one({"id": facility_id})
        
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Red işlemi
        await db.facilities.update_one(
            {"id": facility_id},
            {
                "$set": {
                    "status": "rejected",
                    "rejection_reason": rejection_reason,
                    "approved_by": None,
                    "approved_at": None,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Tesis sahibine bildirim gönder
        notification_data = {
            "id": str(uuid.uuid4()),
            "user_id": facility["owner_id"],
            "type": NotificationType.FACILITY_REJECTED.value,
            "title": "Tesisiniz Reddedildi",
            "message": f"'{facility['name']}' adlı tesisiniz reddedildi. Sebep: {rejection_reason}",
            "related_type": NotificationRelatedType.FACILITY.value,
            "related_id": facility_id,
            "data": {
                "facility_id": facility_id,
                "facility_name": facility["name"],
                "rejection_reason": rejection_reason
            },
            "read": False,
            "created_at": datetime.utcnow()
        }
        
        await db.notifications.insert_one(notification_data)
        
        logger.info(f"❌ Tesis reddedildi: {facility_id} - Admin: {current_user['id']}")
        
        return {
            "success": True,
            "message": "Tesis reddedildi",
            "facility_id": facility_id,
            "rejection_reason": rejection_reason
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Tesis reddetme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/facilities/pending-approvals")
async def get_pending_facilities(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Admin: Onay bekleyen tesisleri getir"""
    try:
        db = request.app.state.db
        
        # Admin kontrolü
        admin_ids = await get_admin_users(db)
        if current_user["id"] not in admin_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için admin yetkisi gereklidir"
            )
        
        # Onay bekleyen tesisleri getir
        facilities = await db.facilities.find({"status": "pending"}).to_list(100)
        
        # Owner bilgilerini ekle
        for facility in facilities:
            owner = await db.users.find_one({"id": facility["owner_id"]})
            if owner:
                facility["owner_name"] = f"{owner.get('first_name', '')} {owner.get('last_name', '')}".strip()
                facility["owner_phone"] = owner.get("phone", "")
        
        logger.info(f"📋 Admin {current_user['id']} onay bekleyen {len(facilities)} tesisi getirdi")
        
        return {
            "success": True,
            "facilities": facilities,
            "count": len(facilities)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Onay bekleyen tesisler getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



# ==================== FACILITY FIELD/COURT MANAGEMENT ====================

@router.get("/facilities/{facility_id}/fields")
async def get_facility_fields(
    facility_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Tesisin tüm alanlarını getir - YÖNETİM EKRANI İÇİN"""
    import sys
    try:
        # Use GLOBAL db from this module (facility_endpoints.py line 25)
        # NOT request.app.state.db which might be different
        global db
        
        debug_info = []
        debug_info.append(f"Query facility_id: {facility_id}")
        debug_info.append(f"User: {current_user.get('email')}")
        debug_info.append(f"Using global db: {type(db)}")
        
        # Direkt sahaları getir - owner kontrolü YOK (management için)
        query = {"facility_id": facility_id, "is_active": True}
        debug_info.append(f"MongoDB query: {query}")
        
        fields_cursor = db.facility_fields.find(query)
        fields = await fields_cursor.to_list(length=100)
        
        debug_info.append(f"MongoDB returned: {len(fields)} fields")
        
        if len(fields) == 0:
            # Debug: Tüm sahaları kontrol et
            all_fields = await db.facility_fields.find({}).to_list(length=100)
            debug_info.append(f"Total fields in DB: {len(all_fields)}")
            
            # Bu facility_id ile başka active olmayan sahalar var mı?
            inactive_fields = await db.facility_fields.find({"facility_id": facility_id}).to_list(length=100)
            debug_info.append(f"Fields with this facility_id (all): {len(inactive_fields)}")
            
            if len(all_fields) > 0:
                debug_info.append("Sample fields from DB:")
                for f in all_fields[:3]:
                    debug_info.append(f"  - fac_id: {f.get('facility_id')[:20]}... | active: {f.get('is_active')} | name: {f.get('name')}")
        else:
            for f in fields:
                debug_info.append(f"Found: {f.get('name')} | {f.get('sport')}")
        
        return {
            "success": True,
            "fields": fields,
            "count": len(fields),
            "debug": debug_info  # Frontend'de görmek için
        }
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return {
            "success": False,
            "fields": [],
            "count": 0,
            "error": str(e),
            "trace": error_trace
        }


@router.post("/facilities/{facility_id}/fields")
async def create_facility_field(
    facility_id: str,
    field: FacilityField,
    current_user: dict = Depends(get_current_user)
):
    """Yeni alan ekle"""
    try:
        # Tesisi kontrol et
        facility = await db.facilities.find_one({"id": facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Sadece tesis sahibi ekleyebilir
        if facility["owner_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu tesise alan ekleyemezsiniz"
            )
        
        # Alan oluştur
        field.id = str(uuid.uuid4())
        field.facility_id = facility_id
        field.created_at = datetime.utcnow()
        field.updated_at = datetime.utcnow()
        
        await db.facility_fields.insert_one(field.dict())
        
        logger.info(f"✅ Yeni alan eklendi: {field.field_name} - Facility: {facility_id}")
        
        return {
            "success": True,
            "message": "Alan başarıyla eklendi",
            "field": field.dict()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Alan ekleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/facilities/fields/{field_id}")
async def update_facility_field(
    field_id: str,
    field_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Alan bilgilerini güncelle (doluluk, ücret, indirim, rezerve edilebilir)"""
    try:
        # Alanı bul
        field = await db.facility_fields.find_one({"id": field_id})
        if not field:
            raise HTTPException(status_code=404, detail="Alan bulunamadı")
        
        # Tesisi kontrol et
        facility = await db.facilities.find_one({"id": field["facility_id"]})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Sadece tesis sahibi güncelleyebilir
        if facility["owner_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu alanı güncelleyemezsiniz"
            )
        
        # İzin verilen field'lar
        allowed_fields = [
            "is_occupied",
            "is_available_for_booking",
            "hourly_rate",
            "discount_percentage",
            "current_reservation",
            "field_name",
            "field_type"
        ]
        
        update_data = {k: v for k, v in field_data.items() if k in allowed_fields}
        update_data["updated_at"] = datetime.utcnow()
        
        await db.facility_fields.update_one(
            {"id": field_id},
            {"$set": update_data}
        )
        
        logger.info(f"✅ Alan güncellendi: {field_id}")
        
        return {
            "success": True,
            "message": "Alan başarıyla güncellendi",
            "field_id": field_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Alan güncelleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/facilities/fields/{field_id}")
async def delete_facility_field(
    field_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Alanı sil (soft delete)"""
    try:
        # Alanı bul
        field = await db.facility_fields.find_one({"id": field_id})
        if not field:
            raise HTTPException(status_code=404, detail="Alan bulunamadı")
        
        # Tesisi kontrol et
        facility = await db.facilities.find_one({"id": field["facility_id"]})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Sadece tesis sahibi silebilir
        if facility["owner_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu alanı silemezsiniz"
            )
        
        # Soft delete
        await db.facility_fields.update_one(
            {"id": field_id},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
        )
        
        logger.info(f"🗑️ Alan silindi: {field_id}")
        
        return {
            "success": True,
            "message": "Alan başarıyla silindi"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Alan silme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



# ==================== HELPER: OTOMATİK SAHA OLUŞTURMA ====================

async def _create_fields_for_facility(facility: dict, db):
    """
    Tesis onaylandığında otomatik olarak sahaları oluşturur.
    Tesisteki sports bilgisinden area_count'u alır ve o kadar saha oluşturur.
    """
    try:
        facility_id = facility["id"]
        sports = facility.get("sports", [])
        pricing = facility.get("pricing", {})
        
        # Var olan sahaları kontrol et
        existing_fields = await db.facility_fields.count_documents({"facility_id": facility_id})
        if existing_fields > 0:
            logger.info(f"⚠️ Tesis {facility_id} için zaten {existing_fields} saha var, yenisi oluşturulmayacak")
            return
        
        fields_to_create = []
        
        for sport in sports:
            if isinstance(sport, dict):
                sport_name = sport.get("sport_name")
                area_count = sport.get("area_count", 0)
            elif isinstance(sport, str):
                sport_name = sport
                area_count = 1  # Default 1 saha
            else:
                continue
            
            # Her spor için area_count kadar saha oluştur
            for i in range(1, area_count + 1):
                field = {
                    "_id": str(uuid.uuid4()),
                    "facility_id": facility_id,
                    "name": f"{sport_name} Sahası {i}",
                    "field_name": f"{sport_name} Sahası {i}",
                    "sport": sport_name,
                    "sport_type": sport_name,
                    "field_type": "indoor",  # Default
                    "is_active": True,
                    "is_occupied": False,
                    "is_available_for_booking": True,
                    "hourly_rate": pricing.get("base_price_per_hour"),  # Tesisten fiyat al
                    "discount_percentage": 0,
                    "active_session": None,
                    "created_at": datetime.utcnow()
                }
                fields_to_create.append(field)
        
        if len(fields_to_create) > 0:
            await db.facility_fields.insert_many(fields_to_create)
            logger.info(f"✅ Tesis {facility['name']} için {len(fields_to_create)} saha otomatik oluşturuldu")
        else:
            logger.warning(f"⚠️ Tesis {facility['name']} için saha oluşturulamadı - sports bilgisi eksik")
    
    except Exception as e:
        logger.error(f"❌ Otomatik saha oluşturma hatası: {str(e)}")
        # Hata olsa bile onay işlemini durdurma



# ==================== MÜSAİT SAHALAR ENDPOINT ====================

async def calculate_field_price_v2(
    facility: dict,
    field: dict,
    field_index: int,  # Saha sırası (1, 2, 3...)
    booking_date,  # datetime object
    start_time: str,
    end_time: str
) -> float:
    """
    YENİ V2 SİSTEM: Tesis bazlı dinamik fiyatlandırma
    1. Tesis ücretsizse -> 0 TL
    2. Dinamik fiyatlama yoksa -> Sabit saatlik fiyat
    3. Dinamik fiyatlama varsa -> Hesapla
    """
    try:
        from datetime import datetime as dt
        import pytz
        
        # 1. TESİS ÜCRETSİZ Mİ?
        pricing = facility.get("pricing", {})
        if pricing.get("is_free"):
            logger.info(f"💰 Saha {field.get('name')} - Ücretsiz tesis")
            return 0.0
        
        # GMT+3 timezone
        tz = pytz.timezone('Europe/Istanbul')
        if booking_date.tzinfo is None:
            booking_date = tz.localize(booking_date)
        
        # 2. DİNAMİK FİYATLANDIRMA VAR MI?
        pricing_v2 = facility.get("pricing_v2", {})
        
        if not pricing_v2 or not pricing_v2.get("use_dynamic_pricing_v2"):
            # Dinamik fiyatlandırma yok, STANDART saatlik fiyat kullan
            # Öncelik: 1. Saha fiyatı, 2. Tesis hourly_rate, 3. Varsayılan 80
            default_price = field.get("hourly_rate") or pricing.get("hourly_rate") or pricing.get("base_price_per_hour", 80)
            logger.info(f"💰 Saha {field.get('name')} - Standart fiyat: {default_price} TL (field={field.get('hourly_rate')}, pricing.hourly_rate={pricing.get('hourly_rate')})")
            return default_price
        
        # 1. Temel fiyat (base_prices)
        base_prices = pricing_v2.get("base_prices", {})
        start_hour = int(start_time.split(":")[0])
        
        # Zaman dilimine göre temel fiyat
        if start_hour < 12:
            time_key = "morning"
        elif start_hour < 17:
            time_key = "afternoon"
        elif start_hour < 22:
            time_key = "evening"
        else:
            time_key = "night"
        
        # Varsayılan fiyatı tesis hourly_rate'ten al
        default_hourly = pricing.get("hourly_rate", 80)
        base_price = float(base_prices.get(time_key, default_hourly))
        
        # 2. Saha çarpanı
        same_for_all = pricing_v2.get("same_for_all_fields", True)
        if same_for_all:
            field_mult = 1.0
        else:
            field_multipliers = pricing_v2.get("field_multipliers", {})
            field_mult = float(field_multipliers.get(str(field_index), 1.0))
        
        # 3. Ölü dönem çarpanı
        dead_period_mult = float(pricing_v2.get("dead_period_multiplier", 1.0))
        
        # 4. Gün tipi kontrolü
        day_of_week = booking_date.weekday()
        is_weekend = day_of_week >= 5
        
        # Özel gün kontrolü (GG.AA.YYYY formatında)
        special_days = pricing_v2.get("special_days", {})
        date_str = booking_date.strftime("%d.%m.%Y")
        is_special_day = date_str in special_days.get("dates", [])
        
        if is_special_day and special_days.get("apply_weekend_multiplier"):
            is_weekend = True
        
        # 5. Hafta sonu çarpanı
        if is_weekend:
            weekend_mult = pricing_v2.get("weekend_time_multipliers", {})
            time_mult = float(weekend_mult.get(time_key, 1.0))
        else:
            time_mult = 1.0
        
        # Final fiyat hesaplama
        final_price = base_price * field_mult * dead_period_mult * time_mult
        final_price = round(final_price, 2)
        
        logger.info(f"💰 Saha {field.get('name')} - Dinamik V2: {final_price} TL (base={base_price}, field_mult={field_mult}, dead={dead_period_mult}, time_mult={time_mult})")
        
        return final_price
        
    except Exception as e:
        logger.error(f"❌ Fiyat hesaplama hatası: {str(e)}")
        import traceback
        traceback.print_exc()
        # Öncelik: saha fiyatı -> tesis hourly_rate -> 80
        pricing = facility.get("pricing", {})
        return field.get("hourly_rate") or pricing.get("hourly_rate", 80)


@router.get("/facilities/{facility_id}/available-fields")
async def get_available_fields(
    facility_id: str,
    date: str,  # Format: YYYY-MM-DD
    start_time: str,  # Format: HH:MM
    end_time: str  # Format: HH:MM
):
    """Belirli tarih ve saat aralığında müsait sahaları getir"""
    try:
        from datetime import datetime, timedelta
        
        logger.info(f"🏟️ Müsait sahalar getiriliyor - Tesis: {facility_id}, Tarih: {date}, Saat: {start_time}-{end_time}")
        
        # Tarihi parse et
        try:
            selected_date = datetime.strptime(date, "%Y-%m-%d")
            day_name_en = selected_date.strftime("%A").lower()  # monday, tuesday, etc.
            
            # Türkçe gün isimleri map
            day_map = {
                'monday': 'pazartesi',
                'tuesday': 'salı',
                'wednesday': 'çarşamba',
                'thursday': 'perşembe',
                'friday': 'cuma',
                'saturday': 'cumartesi',
                'sunday': 'pazar'
            }
            day_name_tr = day_map.get(day_name_en, day_name_en)
        except:
            raise HTTPException(status_code=400, detail="Geçersiz tarih formatı (YYYY-MM-DD kullanın)")
        
        # Saatleri parse et
        try:
            start_hour = int(start_time.split(":")[0])
            end_hour = int(end_time.split(":")[0])
            requested_hours = list(range(start_hour, end_hour))
        except:
            raise HTTPException(status_code=400, detail="Geçersiz saat formatı (HH:MM kullanın)")
        
        # Tesisi getir (working_hours için)
        facility = await db.facilities.find_one({"id": facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Tesisin sahalarını facility_fields koleksiyonundan al
        # CRITICAL: Sahalar ayrı bir koleksiyonda (facility_fields), facility document'inde değil
        # CRITICAL: created_at'e göre sırala (payment endpoint ile AYNI sıralama)
        fields_cursor = db.facility_fields.find({
            "facility_id": facility_id,
            "is_active": True
        }).sort("created_at", 1)
        all_fields = await fields_cursor.to_list(100)
        
        logger.info(f"🏟️ Found {len(all_fields)} active fields for facility {facility_id}")
        
        if not all_fields:
            return {
                "success": True,
                "available_fields": [],
                "message": "Bu tesiste henüz saha bulunmuyor"
            }
        
        available_fields = []
        
        for field in all_fields:
            # CRITICAL: MongoDB'de _id var ama id yok, _id'yi id olarak kullan
            if "_id" in field and "id" not in field:
                field["id"] = field["_id"]
            field.pop("_id", None)
            
            field_id = field.get("id", "unknown")
            
            # 1. TESİSİN çalışma saatlerini kontrol et (sahada değil)
            working_hours = facility.get("working_hours", {})
            day_hours_obj = None
            
            # CRITICAL: working_hours iki format olabilir
            # Format 1 (eski): {"monday": {"open": "08:00", "close": "20:00"}}
            # Format 2 (yeni): [{"day": "monday", "opening_time": "08:00", "closing_time": "20:00"}]
            
            if isinstance(working_hours, dict):
                # Format 1 - dict
                day_hours_obj = working_hours.get(day_name_en, working_hours.get(day_name_tr))
            elif isinstance(working_hours, list):
                # Format 2 - array
                for wh in working_hours:
                    if wh.get("day") == day_name_en or wh.get("day") == day_name_tr:
                        if wh.get("is_open", True):
                            day_hours_obj = wh
                        break
            
            if not day_hours_obj:
                logger.warning(f"   Saha {field_id[:8] if isinstance(field_id, str) else field_id}... - {day_name_en} günü çalışma saati yok")
                continue  # Bu gün çalışmıyor
            
            # working_hours formatına göre open/close time çıkar
            if isinstance(day_hours_obj, dict):
                open_time = day_hours_obj.get("open") or day_hours_obj.get("opening_time")
                close_time = day_hours_obj.get("close") or day_hours_obj.get("closing_time")
                
                if not open_time or not close_time:
                    continue
                
                try:
                    range_start_hour = int(open_time.split(":")[0])
                    range_end_hour = int(close_time.split(":")[0])
                    
                    # Kullanıcının istediği saatler çalışma saatleri içinde mi?
                    if range_start_hour <= start_hour and end_hour <= range_end_hour:
                        is_field_working = True
                    else:
                        logger.info(f"   Saha {field.get('id')[:8]}... - İstenen saat ({start_hour}-{end_hour}) çalışma saatleri ({range_start_hour}-{range_end_hour}) dışında")
                        continue
                except Exception as e:
                    logger.error(f"   Saha {field.get('id')[:8]}... - Saat parse hatası: {e}")
                    continue
            else:
                logger.warning(f"   Saha {field.get('id')[:8]}... - working_hours formatı hatalı: {day_hours_obj}")
                continue
            
            # 2. O tarih ve saatlerde rezervasyon var mı kontrol et
            reservations = await db.reservations.find({
                "field_id": field["id"],
                "date": date,
                "status": {"$in": ["pending", "confirmed"]}  # İptal edilenler hariç
            }).to_list(100)
            
            # Rezerve edilmiş saatleri topla
            reserved_hours = set()
            for reservation in reservations:
                time_slots = reservation.get("time_slots", [])
                for slot in time_slots:
                    try:
                        hour = int(slot.split(":")[0])
                        reserved_hours.add(hour)
                    except:
                        continue
            
            # İstenen saatler müsait mi?
            is_available = all(hour not in reserved_hours for hour in requested_hours)
            
            if is_available:
                # 3. DİNAMİK FİYATLANDIRMA V2: Tesis bazlı fiyat hesaplama
                field_index = all_fields.index(field) + 1  # Saha numarası (1, 2, 3...)
                
                calculated_price = await calculate_field_price_v2(
                    facility=facility,
                    field=field,
                    field_index=field_index,
                    booking_date=selected_date,
                    start_time=start_time,
                    end_time=end_time
                )
                
                field["hourly_rate"] = calculated_price
                field["pricing_type"] = "dynamic_v2" if facility.get("pricing_v2", {}).get("use_dynamic_pricing_v2") else "fixed"
                
                available_fields.append(field)
        
        logger.info(f"✅ {len(available_fields)}/{len(all_fields)} saha müsait")
        
        return {
            "success": True,
            "available_fields": available_fields,
            "total_fields": len(all_fields),
            "available_count": len(available_fields)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Müsait saha getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SAHA DOLULUK VE MANUEL REZERVASYON ====================

@router.get("/facilities/{facility_id}/fields/{field_id}/schedule")
async def get_field_schedule(
    facility_id: str,
    field_id: str,
    date: str,
    current_user: dict = Depends(get_current_user)
):
    """Saha günlük doluluk programını getir"""
    try:
        # Tesisi kontrol et
        facility = await db.facilities.find_one({"id": facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Yetki kontrolü
        if facility.get("owner_id") != current_user["id"] and current_user.get("user_type") != "admin":
            raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
        
        # Sahayı bul - hem ObjectId hem UUID destekle
        from bson import ObjectId
        from bson.errors import InvalidId
        
        field = None
        try:
            # Önce ObjectId olarak dene
            field = await db.facility_fields.find_one({"_id": ObjectId(field_id)})
        except InvalidId:
            pass
        
        if not field:
            # UUID olarak dene
            field = await db.facility_fields.find_one({"id": field_id})
        
        if not field:
            # facility_id ile tüm sahaları al ve eşleştir
            all_fields = await db.facility_fields.find({"facility_id": facility_id}).to_list(100)
            for f in all_fields:
                if str(f.get("_id")) == field_id or f.get("id") == field_id:
                    field = f
                    break
        
        if not field:
            raise HTTPException(status_code=404, detail="Saha bulunamadı")
        
        # O günün rezervasyonlarını getir - saha bazlı filtrele
        reservations = await db.reservations.find({
            "facility_id": facility_id,
            "field_id": str(field.get("_id")) if field.get("_id") else field.get("id"),
            "date": date,
            "status": {"$in": ["confirmed", "pending", "paid"]}
        }).to_list(100)
        
        # Eğer field_id ile bulunamadıysa, eski kayıtlar için field_name ile dene
        if not reservations:
            reservations = await db.reservations.find({
                "facility_id": facility_id,
                "date": date,
                "status": {"$in": ["confirmed", "pending", "paid"]}
            }).to_list(100)
            # Saha adına göre filtrele
            field_name = field.get("name") or field.get("field_name")
            if field_name:
                reservations = [r for r in reservations if r.get("field_name") == field_name or r.get("field_id") == field_id]
        
        # Manuel rezervasyonları getir
        manual_reservations = await db.manual_reservations.find({
            "facility_id": facility_id,
            "field_id": field_id,
            "date": date
        }).to_list(100)
        
        # Seansları getir (session_history)
        sessions = field.get("session_history", [])
        day_sessions = []
        for session in sessions:
            if session.get("start_time"):
                session_date = session["start_time"][:10]
                if session_date == date:
                    day_sessions.append(session)
        
        # Aktif seansı kontrol et
        active_session = field.get("active_session")
        
        # Tüm rezervasyonları birleştir
        all_reservations = []
        for r in reservations:
            r.pop("_id", None)
            r["source"] = "online"
            all_reservations.append(r)
        
        for r in manual_reservations:
            r.pop("_id", None)
            r["source"] = "manual"
            all_reservations.append(r)
        
        return {
            "success": True,
            "date": date,
            "field_id": field_id,
            "field_name": field.get("name") or field.get("field_name"),
            "reservations": all_reservations,
            "sessions": day_sessions,
            "active_session": active_session
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Schedule getirme hatası: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/facilities/{facility_id}/manual-reservation")
async def create_manual_reservation(
    facility_id: str,
    reservation_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Tesis sahibi için manuel rezervasyon oluştur"""
    try:
        # Tesisi kontrol et
        facility = await db.facilities.find_one({"id": facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Yetki kontrolü
        if facility.get("owner_id") != current_user["id"] and current_user.get("user_type") != "admin":
            raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
        
        reservation = {
            "id": str(uuid.uuid4()),
            "facility_id": facility_id,
            "field_id": reservation_data.get("field_id"),
            "date": reservation_data.get("date"),
            "start_time": reservation_data.get("start_time"),
            "end_time": reservation_data.get("end_time"),
            "customer_name": reservation_data.get("customer_name"),
            "customer_phone": reservation_data.get("customer_phone"),
            "notes": reservation_data.get("notes"),
            "hourly_rate": reservation_data.get("hourly_rate", 0),
            "total_price": reservation_data.get("hourly_rate", 0) * (
                int(reservation_data.get("end_time", "0").split(":")[0]) - 
                int(reservation_data.get("start_time", "0").split(":")[0])
            ),
            "status": "confirmed",
            "source": "manual",
            "created_by": current_user["id"],
            "created_at": datetime.utcnow().isoformat()
        }
        
        await db.manual_reservations.insert_one(reservation)
        reservation.pop("_id", None)
        
        logger.info(f"✅ Manuel rezervasyon oluşturuldu: {reservation['id']}")
        
        return {
            "success": True,
            "reservation": reservation
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Manuel rezervasyon hatası: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/facilities/{facility_id}/fields/{field_id}/start-session")
async def start_field_session(
    facility_id: str,
    field_id: str,
    session_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Saha seansı başlat"""
    try:
        # Tesisi kontrol et
        facility = await db.facilities.find_one({"id": facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Yetki kontrolü
        if facility.get("owner_id") != current_user["id"] and current_user.get("user_type") != "admin":
            raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
        
        from bson import ObjectId
        from bson.errors import InvalidId
        
        # Sahayı bul - hem ObjectId hem de UUID/id formatını destekle
        field = None
        try:
            # Önce ObjectId olarak dene
            field = await db.facility_fields.find_one({"_id": ObjectId(field_id)})
        except InvalidId:
            # ObjectId değilse, id alanında ara
            field = await db.facility_fields.find_one({"id": field_id})
        
        if not field:
            # Hala bulunamadıysa facility_id + field index ile dene
            field = await db.facility_fields.find_one({
                "$or": [
                    {"_id": field_id},
                    {"id": field_id},
                    {"field_id": field_id}
                ]
            })
        
        if not field:
            raise HTTPException(status_code=404, detail=f"Saha bulunamadı: {field_id}")
        
        field_name = field.get("name", field.get("field_name", "Bilinmeyen Saha"))
        
        # Sahayı güncelle
        active_session = {
            "id": str(uuid.uuid4()),
            "start_time": session_data.get("start_time", datetime.utcnow().isoformat()),
            "player_names": session_data.get("player_names", []),
            "planned_duration": session_data.get("planned_duration", 1),
            "started_by": current_user["id"]
        }
        
        # Güncelleme query'sini field'ın _id'sine göre yap
        update_query = {"_id": field.get("_id")} if field.get("_id") else {"id": field.get("id")}
        
        await db.facility_fields.update_one(
            update_query,
            {
                "$set": {
                    "is_occupied": True,
                    "active_session": active_session
                }
            }
        )
        
        # Log kaydı oluştur
        await log_user_activity(
            user_id=current_user["id"],
            action_type="START_SESSION",
            details={
                "facility_id": facility_id,
                "facility_name": facility.get("name", "Bilinmeyen Tesis"),
                "field_id": field_id,
                "field_name": field_name,
                "session_id": active_session["id"],
                "start_time": active_session["start_time"],
                "player_names": active_session["player_names"],
                "planned_duration": active_session["planned_duration"]
            }
        )
        
        logger.info(f"✅ Seans başlatıldı: {field_id}")
        
        return {
            "success": True,
            "session": active_session
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Seans başlatma hatası: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/facilities/{facility_id}/fields/{field_id}/create-reservation")
async def create_field_reservation(
    facility_id: str,
    field_id: str,
    reservation_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Gelecek tarih için saha rezervasyonu oluştur (is_occupied'ı etkilemez)"""
    try:
        # Tesisi kontrol et
        facility = await db.facilities.find_one({"id": facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Yetki kontrolü
        if facility.get("owner_id") != current_user["id"] and current_user.get("user_type") != "admin":
            raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
        
        from bson import ObjectId
        from bson.errors import InvalidId
        
        # Sahayı bul
        field = None
        try:
            field = await db.facility_fields.find_one({"_id": ObjectId(field_id)})
        except InvalidId:
            field = await db.facility_fields.find_one({"id": field_id})
        
        if not field:
            field = await db.facility_fields.find_one({
                "$or": [
                    {"_id": field_id},
                    {"id": field_id},
                    {"field_id": field_id}
                ]
            })
        
        if not field:
            raise HTTPException(status_code=404, detail=f"Saha bulunamadı: {field_id}")
        
        field_name = field.get("name", field.get("field_name", "Bilinmeyen Saha"))
        
        # Yeni rezervasyon oluştur
        reservation = {
            "id": str(uuid.uuid4()),
            "start_time": reservation_data.get("start_time", datetime.utcnow().isoformat()),
            "player_names": reservation_data.get("player_names", []),
            "duration": reservation_data.get("planned_duration", 60),
            "created_by": current_user["id"],
            "created_at": datetime.utcnow().isoformat(),
            "status": "confirmed"
        }
        
        # Güncelleme query'sini field'ın _id'sine göre yap
        update_query = {"_id": field.get("_id")} if field.get("_id") else {"id": field.get("id")}
        
        # Rezervasyonu reservations array'ine ekle (is_occupied DEĞİŞMEZ)
        await db.facility_fields.update_one(
            update_query,
            {
                "$push": {
                    "reservations": reservation
                }
            }
        )
        
        # Log kaydı oluştur
        await log_user_activity(
            user_id=current_user["id"],
            action_type="CREATE_RESERVATION",
            details={
                "facility_id": facility_id,
                "facility_name": facility.get("name", "Bilinmeyen Tesis"),
                "field_id": field_id,
                "field_name": field_name,
                "reservation_id": reservation["id"],
                "start_time": reservation["start_time"],
                "player_names": reservation["player_names"],
                "duration": reservation["duration"]
            }
        )
        
        logger.info(f"✅ Rezervasyon oluşturuldu: {field_id} - {reservation['start_time']}")
        
        return {
            "success": True,
            "reservation": reservation
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Rezervasyon oluşturma hatası: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/facilities/{facility_id}/fields/{field_id}/end-session")
async def end_field_session(
    facility_id: str,
    field_id: str,
    session_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Saha seansını bitir"""
    try:
        # Tesisi kontrol et
        facility = await db.facilities.find_one({"id": facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Yetki kontrolü
        if facility.get("owner_id") != current_user["id"] and current_user.get("user_type") != "admin":
            raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
        
        from bson import ObjectId
        from dateutil import parser as date_parser
        
        # Sahayı bul - hem ObjectId hem UUID formatını destekle
        field = None
        try:
            field = await db.facility_fields.find_one({"_id": ObjectId(field_id)})
        except:
            pass
        
        if not field:
            field = await db.facility_fields.find_one({"id": field_id})
        if not field:
            field = await db.facility_fields.find_one({"_id": field_id})
        
        if not field:
            raise HTTPException(status_code=404, detail="Saha bulunamadı")
        
        active_session = field.get("active_session")
        if not active_session:
            raise HTTPException(status_code=400, detail="Aktif seans bulunamadı")
        
        # Seans süresini hesapla
        try:
            start_time = date_parser.parse(active_session["start_time"])
        except:
            start_time = datetime.fromisoformat(active_session["start_time"].replace("Z", "+00:00"))
        
        end_time_str = session_data.get("end_time", datetime.utcnow().isoformat())
        try:
            end_time = date_parser.parse(end_time_str)
        except:
            end_time = datetime.utcnow()
        
        # Timezone-naive karşılaştırma için
        if start_time.tzinfo is not None:
            start_time = start_time.replace(tzinfo=None)
        if end_time.tzinfo is not None:
            end_time = end_time.replace(tzinfo=None)
        
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
        if duration_minutes < 0:
            duration_minutes = abs(duration_minutes)
        
        duration_hours = duration_minutes / 60
        
        # Ücreti dakika bazlı hesapla
        hourly_rate = field.get("hourly_rate") or 0
        if hourly_rate is None:
            hourly_rate = 0
        total_collected = round((hourly_rate / 60) * duration_minutes) if hourly_rate > 0 else 0
        
        # Seansı tamamla
        completed_session = {
            **active_session,
            "end_time": end_time_str,
            "duration_minutes": duration_minutes,
            "duration_hours": round(duration_hours, 2),
            "total_collected": total_collected,
            "hourly_rate": hourly_rate,
            "ended_by": current_user["id"]
        }
        
        # Sahayı güncelle - hem ObjectId hem id ile dene
        update_query = {"_id": field.get("_id")} if field.get("_id") else {"id": field.get("id")}
        await db.facility_fields.update_one(
            update_query,
            {
                "$set": {
                    "is_occupied": False,
                    "active_session": None
                },
                "$push": {
                    "session_history": completed_session
                }
            }
        )
        
        # Log kaydı oluştur
        await log_user_activity(
            user_id=current_user["id"],
            action_type="END_SESSION",
            details={
                "facility_id": facility_id,
                "facility_name": facility.get("name", "Bilinmeyen Tesis"),
                "field_id": field_id,
                "field_name": field.get("name", "Bilinmeyen Saha"),
                "session_id": active_session.get("id"),
                "start_time": active_session.get("start_time"),
                "end_time": end_time_str,
                "duration_minutes": duration_minutes,
                "total_collected": total_collected,
                "player_names": active_session.get("player_names", [])
            }
        )
        
        logger.info(f"✅ Seans bitirildi: {field_id}, Süre: {duration_minutes} dakika, Tutar: {total_collected} TL")
        
        return {
            "success": True,
            "session": completed_session
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Seans bitirme hatası: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==================== TESİS FAVORİ ENDPOINTS ====================

@router.post("/facilities/{facility_id}/favorite")
async def add_facility_to_favorites(
    facility_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Tesisi favorilere ekle"""
    try:
        user_id = current_user["id"]
        
        # Tesisin var olduğunu kontrol et
        facility = await db.facilities.find_one({"id": facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # Zaten favorilerde mi kontrol et
        existing = await db.facility_favorites.find_one({
            "user_id": user_id,
            "facility_id": facility_id
        })
        
        if existing:
            return {"success": True, "message": "Zaten favorilerde", "is_favorite": True}
        
        # Favorilere ekle
        favorite = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "facility_id": facility_id,
            "created_at": datetime.utcnow().isoformat()
        }
        
        await db.facility_favorites.insert_one(favorite)
        
        # Tesisin favori sayısını güncelle
        await db.facilities.update_one(
            {"id": facility_id},
            {"$inc": {"favorite_count": 1}}
        )
        
        logger.info(f"❤️ Tesis favorilere eklendi: {facility_id} by {user_id}")
        
        return {"success": True, "message": "Favorilere eklendi", "is_favorite": True}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Favori ekleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/facilities/{facility_id}/favorite")
async def remove_facility_from_favorites(
    facility_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Tesisi favorilerden çıkar"""
    try:
        user_id = current_user["id"]
        
        result = await db.facility_favorites.delete_one({
            "user_id": user_id,
            "facility_id": facility_id
        })
        
        if result.deleted_count > 0:
            # Tesisin favori sayısını güncelle
            await db.facilities.update_one(
                {"id": facility_id},
                {"$inc": {"favorite_count": -1}}
            )
            logger.info(f"💔 Tesis favorilerden çıkarıldı: {facility_id} by {user_id}")
        
        return {"success": True, "message": "Favorilerden çıkarıldı", "is_favorite": False}
    
    except Exception as e:
        logger.error(f"❌ Favori çıkarma hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/facilities/{facility_id}/is-favorite")
async def check_facility_favorite(
    facility_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Tesisin favori olup olmadığını kontrol et"""
    try:
        user_id = current_user["id"]
        
        existing = await db.facility_favorites.find_one({
            "user_id": user_id,
            "facility_id": facility_id
        })
        
        return {"is_favorite": existing is not None}
    
    except Exception as e:
        logger.error(f"❌ Favori kontrol hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/facilities/favorites/list")
async def get_favorite_facilities(
    current_user: dict = Depends(get_current_user)
):
    """Kullanıcının favori tesislerini getir"""
    try:
        user_id = current_user["id"]
        
        # Favori tesis ID'lerini al
        favorites = await db.facility_favorites.find({"user_id": user_id}).to_list(length=100)
        facility_ids = [f["facility_id"] for f in favorites]
        
        if not facility_ids:
            return {"facilities": [], "facility_ids": []}
        
        # Tesisleri getir
        facilities = await db.facilities.find({
            "id": {"$in": facility_ids},
            "status": "approved"
        }).to_list(length=100)
        
        # ID'leri string olarak döndür
        for f in facilities:
            f.pop("_id", None)
        
        return {
            "facilities": facilities,
            "facility_ids": facility_ids
        }
    
    except Exception as e:
        logger.error(f"❌ Favori tesisleri getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/facilities/favorites/ids")
async def get_favorite_facility_ids(
    current_user: dict = Depends(get_current_user)
):
    """Kullanıcının favori tesis ID'lerini getir (hızlı kontrol için)"""
    try:
        user_id = current_user["id"]
        
        favorites = await db.facility_favorites.find({"user_id": user_id}).to_list(length=100)
        facility_ids = [f["facility_id"] for f in favorites]
        
        return {"facility_ids": facility_ids}
    
    except Exception as e:
        logger.error(f"❌ Favori ID'leri getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

