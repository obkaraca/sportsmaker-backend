from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List
import logging
from auth import get_current_user
from models import SportConfiguration, FieldType, ScoringSystem, CompetitionFormat, FieldDimensions, GameDuration, PlayerCount, SportRule, Equipment
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sport-configs")
async def get_all_sport_configs(request: Request):
    """Tüm spor yapılandırmalarını getir (aktif olanlar)"""
    try:
        db = request.app.state.db
        configs = await db.sport_configurations.find({"is_active": True}).to_list(100)
        
        # ObjectId'yi string'e çevir
        for config in configs:
            if "_id" in config:
                config["_id"] = str(config["_id"])
        
        return {"success": True, "configs": configs}
    
    except Exception as e:
        logger.error(f"❌ Sport configs listesi alınırken hata: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ONAY SİSTEMİ ENDPOİNTLERİ (Statik route'lar önce!) ====================

@router.get("/sport-configs/pending-approvals")
async def get_pending_approvals(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Onay bekleyen spor yapılandırmalarını getir (Sadece admin)"""
    try:
        db = request.app.state.db
        
        # Admin kontrolü
        if current_user.get("user_type") != "admin":
            raise HTTPException(status_code=403, detail="Bu işlem için yönetici yetkisi gerekli")
        
        # Onay bekleyen config'leri bul (yeni eklenen veya düzenlenen)
        pending_configs = await db.sport_configurations.find({
            "approval_status": "pending"
        }).to_list(100)
        
        # ObjectId'yi string'e çevir
        for config in pending_configs:
            if "_id" in config:
                config["_id"] = str(config["_id"])
        
        return {"success": True, "pending_configs": pending_configs, "count": len(pending_configs)}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Pending approvals getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sport-configs/by-name/{sport_name}")
async def get_sport_config_by_name(sport_name: str, request: Request):
    """Spor adına göre yapılandırmayı getir (match_score_settings için kullanılır)"""
    try:
        db = request.app.state.db
        
        # Spor adına göre konfigürasyonu bul (case-insensitive arama)
        config = await db.sport_configurations.find_one({
            "sport_name": {"$regex": f"^{sport_name}$", "$options": "i"},
            "is_active": True
        })
        
        if not config:
            # Alternatif olarak İngilizce isimle ara
            config = await db.sport_configurations.find_one({
                "sport_name_en": {"$regex": f"^{sport_name}$", "$options": "i"},
                "is_active": True
            })
        
        if not config:
            # Spor bulunamadıysa varsayılan ayarları döndür
            return {
                "success": True, 
                "config": None,
                "match_score_settings": {
                    "uses_sets": False,
                    "max_sets": 3,
                    "points_per_set": None,
                    "allow_draw": True
                },
                "message": f"'{sport_name}' için özel yapılandırma bulunamadı, varsayılan ayarlar kullanılacak"
            }
        
        if "_id" in config:
            config["_id"] = str(config["_id"])
        
        return {
            "success": True, 
            "config": config,
            "match_score_settings": config.get("match_score_settings", {
                "uses_sets": False,
                "max_sets": 3,
                "points_per_set": None,
                "allow_draw": True
            })
        }
    
    except Exception as e:
        logger.error(f"❌ Sport config by name getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sport-configs/{config_id}")
async def get_sport_config(config_id: str, request: Request):
    """Belirli bir spor yapılandırmasını getir"""
    try:
        db = request.app.state.db
        # Hem aktif hem de pending sporları göster (rejected olanları hariç tut)
        config = await db.sport_configurations.find_one({
            "id": config_id,
            "$or": [
                {"is_active": True},
                {"approval_status": "pending"}
            ]
        })
        
        if not config:
            raise HTTPException(status_code=404, detail="Spor yapılandırması bulunamadı")
        
        if "_id" in config:
            config["_id"] = str(config["_id"])
        
        return {"success": True, "config": config}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Sport config getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sport-configs")
async def create_sport_config(
    request: Request,
    config: SportConfiguration,
    current_user: dict = Depends(get_current_user)
):
    """Yeni spor yapılandırması oluştur - Admin dışındakiler için onaya düşer"""
    try:
        db = request.app.state.db
        
        # Yarışma formatları zorunlu kontrolü
        if not config.competition_formats or len(config.competition_formats) == 0:
            raise HTTPException(
                status_code=400,
                detail="En az bir yarışma formatı seçmelisiniz"
            )
        
        # Kullanıcı admin mi kontrol et
        is_admin = current_user.get("user_type") == "admin"
        
        # ID oluştur
        config_id = str(uuid.uuid4())
        config_data = config.dict()
        config_data["id"] = config_id
        config_data["created_by"] = current_user["id"]
        config_data["created_at"] = datetime.utcnow()
        config_data["updated_at"] = datetime.utcnow()
        
        # Onay sistemi alanları
        config_data["submitted_by"] = current_user["id"]
        config_data["submitted_by_name"] = current_user.get("name") or current_user.get("email", "Bilinmiyor")
        config_data["submitted_at"] = datetime.utcnow()
        
        if is_admin:
            # Admin ise direkt onaylı olarak kaydet
            config_data["approval_status"] = "approved"
            config_data["reviewed_by"] = current_user["id"]
            config_data["reviewed_by_name"] = current_user.get("name") or current_user.get("email", "Admin")
            config_data["reviewed_at"] = datetime.utcnow()
        else:
            # Admin değilse onay bekleyen olarak kaydet
            config_data["approval_status"] = "pending"
            config_data["is_active"] = False  # Onay beklerken aktif değil
        
        # Aynı isimde spor var mı kontrol et
        existing = await db.sport_configurations.find_one({
            "sport_name": config.sport_name,
            "is_active": True
        })
        
        if existing:
            raise HTTPException(status_code=400, detail="Bu isimde bir spor zaten mevcut")
        
        await db.sport_configurations.insert_one(config_data)
        
        # Admin değilse adminlere bildirim gönder
        if not is_admin:
            # Tüm adminleri bul
            admins = await db.users.find({"user_type": "admin"}).to_list(100)
            for admin in admins:
                notification = {
                    "id": str(uuid.uuid4()),
                    "user_id": admin["id"],
                    "title": "🏆 Yeni Spor Ekleme Talebi",
                    "message": f"{config_data['submitted_by_name']} yeni bir spor eklemek istiyor: {config.sport_name}",
                    "type": "sport_config_approval",
                    "data": {
                        "config_id": config_id,
                        "sport_name": config.sport_name,
                        "submitted_by": current_user["id"],
                        "action": "create"
                    },
                    "read": False,
                    "created_at": datetime.utcnow()
                }
                await db.notifications.insert_one(notification)
            
            logger.info(f"📤 Yeni spor ekleme talebi gönderildi: {config.sport_name} - Kullanıcı: {current_user['id']}")
            
            return {
                "success": True,
                "message": "Spor ekleme talebiniz yönetici onayına gönderildi",
                "config_id": config_id,
                "approval_status": "pending"
            }
        
        logger.info(f"✅ Yeni spor yapılandırması oluşturuldu: {config.sport_name}")
        
        return {
            "success": True,
            "message": "Spor yapılandırması oluşturuldu",
            "config_id": config_id,
            "approval_status": "approved"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Sport config oluşturma hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/sport-configs/{config_id}")
async def update_sport_config(
    config_id: str,
    request: Request,
    config: SportConfiguration,
    current_user: dict = Depends(get_current_user)
):
    """Spor yapılandırmasını güncelle - Admin dışındakiler için onaya düşer"""
    try:
        db = request.app.state.db
        
        # Yarışma formatları zorunlu kontrolü
        if not config.competition_formats or len(config.competition_formats) == 0:
            raise HTTPException(
                status_code=400,
                detail="En az bir yarışma formatı seçmelisiniz"
            )
        
        # Mevcut config'i bul
        existing = await db.sport_configurations.find_one({"id": config_id})
        
        if not existing:
            raise HTTPException(status_code=404, detail="Spor yapılandırması bulunamadı")
        
        # Kullanıcı admin mi kontrol et
        is_admin = current_user.get("user_type") == "admin"
        
        config_data = config.dict()
        config_data["updated_at"] = datetime.utcnow()
        
        # ID ve created_at değişmesin
        config_data.pop("id", None)
        config_data.pop("created_at", None)
        config_data.pop("created_by", None)
        
        if is_admin:
            # Admin ise direkt güncelle
            await db.sport_configurations.update_one(
                {"id": config_id},
                {"$set": config_data}
            )
            
            logger.info(f"✅ Spor yapılandırması güncellendi (Admin): {config_id}")
            
            return {
                "success": True,
                "message": "Spor yapılandırması güncellendi",
                "approval_status": "approved"
            }
        else:
            # Admin değilse pending_changes olarak kaydet
            pending_changes = config_data.copy()
            pending_changes["submitted_by"] = current_user["id"]
            pending_changes["submitted_by_name"] = current_user.get("name") or current_user.get("email", "Bilinmiyor")
            pending_changes["submitted_at"] = datetime.utcnow().isoformat()
            
            await db.sport_configurations.update_one(
                {"id": config_id},
                {
                    "$set": {
                        "pending_changes": pending_changes,
                        "approval_status": "pending",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            # Adminlere bildirim gönder
            admins = await db.users.find({"user_type": "admin"}).to_list(100)
            for admin in admins:
                notification = {
                    "id": str(uuid.uuid4()),
                    "user_id": admin["id"],
                    "title": "✏️ Spor Düzenleme Talebi",
                    "message": f"{pending_changes['submitted_by_name']} '{existing.get('sport_name', 'Spor')}' sporunu düzenlemek istiyor",
                    "type": "sport_config_approval",
                    "data": {
                        "config_id": config_id,
                        "sport_name": existing.get("sport_name"),
                        "submitted_by": current_user["id"],
                        "action": "update"
                    },
                    "read": False,
                    "created_at": datetime.utcnow()
                }
                await db.notifications.insert_one(notification)
            
            logger.info(f"📤 Spor düzenleme talebi gönderildi: {config_id} - Kullanıcı: {current_user['id']}")
            
            return {
                "success": True,
                "message": "Düzenleme talebiniz yönetici onayına gönderildi",
                "approval_status": "pending"
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Sport config güncelleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sport-configs/{config_id}")
async def delete_sport_config(
    config_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Spor yapılandırmasını sil (soft delete)"""
    try:
        db = request.app.state.db
        
        existing = await db.sport_configurations.find_one({"id": config_id})
        
        if not existing:
            raise HTTPException(status_code=404, detail="Spor yapılandırması bulunamadı")
        
        # Sistem tanımlı ise silinemez
        if existing.get("is_system_default", False):
            raise HTTPException(status_code=403, detail="Sistem tanımlı sporlar silinemez")
        
        # Soft delete
        await db.sport_configurations.update_one(
            {"id": config_id},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
        )
        
        logger.info(f"✅ Spor yapılandırması silindi: {config_id}")
        
        return {
            "success": True,
            "message": "Spor yapılandırması silindi"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Sport config silme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sport-configs/{config_id}/approve")
async def approve_sport_config(
    config_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Spor yapılandırmasını onayla (Sadece admin)"""
    try:
        db = request.app.state.db
        
        # Veritabanından user_type'ı doğrula
        db_user = await db.users.find_one({"id": current_user["id"]})
        user_type = db_user.get("user_type", "player") if db_user else current_user.get("user_type", "player")
        
        logger.info(f"📋 Approve request - config_id: {config_id}, user_id: {current_user['id']}, user_type: {user_type}")
        
        # Admin kontrolü
        if user_type != "admin":
            logger.warning(f"❌ Admin değil - user_type: {user_type}")
            raise HTTPException(status_code=403, detail="Bu işlem için yönetici yetkisi gerekli")
        
        # Config'i bul
        config = await db.sport_configurations.find_one({"id": config_id})
        
        if not config:
            raise HTTPException(status_code=404, detail="Spor yapılandırması bulunamadı")
        
        if config.get("approval_status") != "pending":
            raise HTTPException(status_code=400, detail="Bu yapılandırma onay bekliyor değil")
        
        # Pending changes varsa (düzenleme) uygula
        pending_changes = config.get("pending_changes")
        submitted_by = config.get("submitted_by") if not pending_changes else pending_changes.get("submitted_by")
        
        # Admin bilgilerini al
        admin_name = db_user.get("name") or db_user.get("email", "Admin") if db_user else "Admin"
        
        update_data = {
            "approval_status": "approved",
            "is_active": True,
            "reviewed_by": current_user["id"],
            "reviewed_by_name": admin_name,
            "reviewed_at": datetime.utcnow(),
            "pending_changes": None  # Temizle
        }
        
        # Eğer pending_changes varsa (düzenleme onayı), bu değişiklikleri uygula
        if pending_changes:
            # pending_changes'dan zaman bilgilerini kaldır
            pending_changes.pop("submitted_by", None)
            pending_changes.pop("submitted_by_name", None)
            pending_changes.pop("submitted_at", None)
            update_data.update(pending_changes)
        
        await db.sport_configurations.update_one(
            {"id": config_id},
            {"$set": update_data}
        )
        
        # Talep sahibine bildirim gönder
        if submitted_by:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": submitted_by,
                "title": "✅ Spor Talebiniz Onaylandı",
                "message": f"'{config.get('sport_name', 'Spor')}' için yaptığınız değişiklik yönetici tarafından onaylandı.",
                "type": "sport_config_approved",
                "data": {
                    "config_id": config_id,
                    "sport_name": config.get("sport_name"),
                    "approved_by": current_user["id"]
                },
                "read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(notification)
        
        logger.info(f"✅ Spor yapılandırması onaylandı: {config_id} - Admin: {current_user['id']}")
        
        return {
            "success": True,
            "message": "Spor yapılandırması onaylandı"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Sport config onaylama hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


from pydantic import BaseModel as PydanticBaseModel

class RejectRequest(PydanticBaseModel):
    reason: str = None


@router.post("/sport-configs/{config_id}/reject")
async def reject_sport_config(
    config_id: str,
    request: Request,
    reject_data: RejectRequest = None,
    current_user: dict = Depends(get_current_user)
):
    """Spor yapılandırmasını reddet (Sadece admin)"""
    try:
        db = request.app.state.db
        
        # Veritabanından user_type'ı doğrula
        db_user = await db.users.find_one({"id": current_user["id"]})
        user_type = db_user.get("user_type", "player") if db_user else current_user.get("user_type", "player")
        
        logger.info(f"📋 Reject request - config_id: {config_id}, user_id: {current_user['id']}, user_type: {user_type}")
        
        # Admin kontrolü
        if user_type != "admin":
            logger.warning(f"❌ Admin değil - user_type: {user_type}")
            raise HTTPException(status_code=403, detail="Bu işlem için yönetici yetkisi gerekli")
        
        # Config'i bul
        config = await db.sport_configurations.find_one({"id": config_id})
        
        if not config:
            raise HTTPException(status_code=404, detail="Spor yapılandırması bulunamadı")
        
        if config.get("approval_status") != "pending":
            raise HTTPException(status_code=400, detail="Bu yapılandırma onay bekliyor değil")
        
        # Pending changes varsa (düzenleme reddi)
        pending_changes = config.get("pending_changes")
        submitted_by = config.get("submitted_by") if not pending_changes else pending_changes.get("submitted_by")
        
        reason = reject_data.reason if reject_data else None
        admin_name = db_user.get("name") or db_user.get("email", "Admin") if db_user else "Admin"
        
        if pending_changes:
            # Düzenleme reddi - sadece pending_changes'ı temizle, mevcut config kalır
            await db.sport_configurations.update_one(
                {"id": config_id},
                {
                    "$set": {
                        "approval_status": "approved",  # Eski hali onaylı kalır
                        "pending_changes": None,
                        "review_note": reason,
                        "reviewed_by": current_user["id"],
                        "reviewed_by_name": admin_name,
                        "reviewed_at": datetime.utcnow()
                    }
                }
            )
        else:
            # Yeni ekleme reddi - config'i sil veya rejected olarak işaretle
            await db.sport_configurations.update_one(
                {"id": config_id},
                {
                    "$set": {
                        "approval_status": "rejected",
                        "is_active": False,
                        "review_note": reason,
                        "reviewed_by": current_user["id"],
                        "reviewed_by_name": admin_name,
                        "reviewed_at": datetime.utcnow()
                    }
                }
            )
        
        # Talep sahibine bildirim gönder
        if submitted_by:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": submitted_by,
                "title": "❌ Spor Talebiniz Reddedildi",
                "message": f"'{config.get('sport_name', 'Spor')}' için yaptığınız değişiklik reddedildi." + (f" Sebep: {reason}" if reason else ""),
                "type": "sport_config_rejected",
                "data": {
                    "config_id": config_id,
                    "sport_name": config.get("sport_name"),
                    "rejected_by": current_user["id"],
                    "reason": reason
                },
                "read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(notification)
        
        logger.info(f"❌ Spor yapılandırması reddedildi: {config_id} - Admin: {current_user['id']}")
        
        return {
            "success": True,
            "message": "Spor yapılandırması reddedildi"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Sport config reddetme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sport-configs/seed-defaults")
async def seed_default_sports(request: Request, force: bool = False):
    """Varsayılan sporları veritabanına ekle"""
    try:
        db = request.app.state.db
        
        # Zaten varsa ve force=false ise ekleme
        existing_count = await db.sport_configurations.count_documents({"is_system_default": True})
        if existing_count > 0 and not force:
            return {"success": True, "message": "Varsayılan sporlar zaten mevcut", "count": existing_count}
        
        # Force=true ise önce eski sistem sporlarını sil
        if force:
            await db.sport_configurations.delete_many({"is_system_default": True})
            logger.info("🗑️ Eski sistem sporları silindi")
        
        default_sports = [
            {
                "id": str(uuid.uuid4()),
                "sport_name": "Futbol",
                "sport_name_en": "Football/Soccer",
                "category": "Takım Sporları",
                "description": "11'e 11 oynanan popüler bir takım sporu",
                "field_type": ["grass", "artificial_turf"],
                "field_dimensions": {
                    "length_min": 90.0,
                    "length_max": 120.0,
                    "width_min": 45.0,
                    "width_max": 90.0,
                    "court_count": 1
                },
                "player_count": {
                    "min_per_team": 7,
                    "max_per_team": 18,
                    "on_field_per_team": 11,
                    "substitutes_per_team": 7,
                    "min_to_start": 7
                },
                "game_duration": {
                    "periods": 2,
                    "period_duration_minutes": 45,
                    "break_duration_minutes": 15,
                    "overtime_minutes": 30,
                    "timeout_count": 0,
                    "timeout_duration_seconds": 0
                },
                "scoring_system": "goals",
                "scoring_details": "Topu rakip kaleye atarak gol sayılır",
                "competition_formats": ["knockout", "group_plus_knockout", "single_round_robin", "double_round_robin", "league_system", "cup_single_elimination"],
                "rules": [
                    {"rule_title": "Elle Oynama", "rule_description": "Kaleci dışında elle oynama yasaktır", "is_official": True},
                    {"rule_title": "Ofsayt", "rule_description": "Top oynandığında savunmanın son oyuncusunun arkasında olmamak", "is_official": True}
                ],
                "equipments": [
                    {"name": "Futbol Topu", "is_required": True, "description": "5 numara top"},
                    {"name": "Kaleci Eldiveni", "is_required": False, "description": "Kaleci için"}
                ],
                "is_system_default": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "id": str(uuid.uuid4()),
                "sport_name": "Basketbol",
                "sport_name_en": "Basketball",
                "category": "Takım Sporları",
                "description": "5'e 5 oynanan potaya atış sporu",
                "field_type": ["wood", "hardcourt", "indoor"],
                "field_dimensions": {
                    "length_min": 28.0,
                    "length_max": 28.0,
                    "width_min": 15.0,
                    "width_max": 15.0,
                    "height_min": 7.0,
                    "court_count": 1
                },
                "player_count": {
                    "min_per_team": 5,
                    "max_per_team": 12,
                    "on_field_per_team": 5,
                    "substitutes_per_team": 7,
                    "min_to_start": 5
                },
                "game_duration": {
                    "periods": 4,
                    "period_duration_minutes": 10,
                    "break_duration_minutes": 2,
                    "overtime_minutes": 5,
                    "timeout_count": 5,
                    "timeout_duration_seconds": 60
                },
                "scoring_system": "points",
                "scoring_details": "1, 2 veya 3 sayılık atışlar",
                "competition_formats": ["knockout", "group_plus_knockout", "single_round_robin", "double_round_robin", "league_system", "playoff"],
                "rules": [
                    {"rule_title": "Double Dribble", "rule_description": "Topu iki elle tutup tekrar sürme yasaktır", "is_official": True},
                    {"rule_title": "3 Saniye Kuralı", "rule_description": "Rakip potanın altında 3 saniyeden fazla kalamaz", "is_official": True}
                ],
                "equipments": [
                    {"name": "Basketbol Topu", "is_required": True, "description": "7 numara top"},
                    {"name": "Spor Ayakkabı", "is_required": True, "description": "Basketbol ayakkabısı"}
                ],
                "is_system_default": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "id": str(uuid.uuid4()),
                "sport_name": "Tenis",
                "sport_name_en": "Tennis",
                "category": "Raket Sporları",
                "description": "1'e 1 veya 2'ye 2 oynanan raket sporu",
                "field_type": ["clay", "hardcourt", "grass"],
                "field_dimensions": {
                    "length_min": 23.77,
                    "length_max": 23.77,
                    "width_min": 8.23,
                    "width_max": 10.97,
                    "court_count": 1
                },
                "player_count": {
                    "min_per_team": 1,
                    "max_per_team": 2,
                    "on_field_per_team": 1,
                    "substitutes_per_team": 0,
                    "min_to_start": 1
                },
                "game_duration": {
                    "periods": 3,
                    "period_duration_minutes": 0,
                    "break_duration_minutes": 2,
                    "overtime_minutes": 0,
                    "timeout_count": 0
                },
                "scoring_system": "sets_games",
                "scoring_details": "15, 30, 40, oyun. 6 oyun = 1 set",
                "competition_formats": ["knockout", "single_round_robin", "double_round_robin", "swiss_system"],
                "rules": [
                    {"rule_title": "Servis", "rule_description": "Top ağı geçmeli ve çapraz karşı kareye gelmeli", "is_official": True},
                    {"rule_title": "Ağa Dokunma", "rule_description": "Raket veya vücut ağa dokunmamalı", "is_official": True}
                ],
                "equipments": [
                    {"name": "Tenis Raketi", "is_required": True},
                    {"name": "Tenis Topu", "is_required": True}
                ],
                "is_system_default": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "id": str(uuid.uuid4()),
                "sport_name": "Voleybol",
                "sport_name_en": "Volleyball",
                "category": "Takım Sporları",
                "description": "6'ya 6 oynanan file sporu",
                "field_type": ["indoor", "sand"],
                "field_dimensions": {
                    "length_min": 18.0,
                    "length_max": 18.0,
                    "width_min": 9.0,
                    "width_max": 9.0,
                    "height_min": 7.0,
                    "court_count": 1
                },
                "player_count": {
                    "min_per_team": 6,
                    "max_per_team": 12,
                    "on_field_per_team": 6,
                    "substitutes_per_team": 6,
                    "min_to_start": 6
                },
                "game_duration": {
                    "periods": 5,
                    "period_duration_minutes": 0,
                    "break_duration_minutes": 3,
                    "timeout_count": 2,
                    "timeout_duration_seconds": 30
                },
                "scoring_system": "sets_points",
                "scoring_details": "25 sayı = 1 set, 3 set kazanan maçı alır",
                "competition_formats": ["knockout", "group_plus_knockout", "single_round_robin", "double_round_robin", "playoff"],
                "rules": [
                    {"rule_title": "3 Vuruş", "rule_description": "Topu en fazla 3 vuruşta karşı alana göndermek", "is_official": True},
                    {"rule_title": "Rotasyon", "rule_description": "Saha içinde rotasyon yapılmalı", "is_official": True}
                ],
                "equipments": [
                    {"name": "Voleybol Topu", "is_required": True},
                    {"name": "Dizlik", "is_required": False}
                ],
                "is_system_default": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "id": str(uuid.uuid4()),
                "sport_name": "Hentbol",
                "sport_name_en": "Handball",
                "category": "Takım Sporları",
                "description": "7'ye 7 oynanan hızlı tempolu takım sporu",
                "field_type": ["indoor", "wood"],
                "field_dimensions": {
                    "length_min": 40.0,
                    "length_max": 40.0,
                    "width_min": 20.0,
                    "width_max": 20.0,
                    "height_min": 7.0,
                    "court_count": 1
                },
                "player_count": {
                    "min_per_team": 7,
                    "max_per_team": 14,
                    "on_field_per_team": 7,
                    "substitutes_per_team": 7,
                    "min_to_start": 7
                },
                "game_duration": {
                    "periods": 2,
                    "period_duration_minutes": 30,
                    "break_duration_minutes": 10,
                    "overtime_minutes": 10,
                    "timeout_count": 3,
                    "timeout_duration_seconds": 60
                },
                "scoring_system": "goals",
                "scoring_details": "Topu rakip kaleye atarak gol sayılır",
                "competition_formats": ["knockout", "group_plus_knockout", "single_round_robin", "double_round_robin", "league_system", "cup_single_elimination"],
                "rules": [
                    {"rule_title": "3 Adım Kuralı", "rule_description": "Top tutuluyken en fazla 3 adım atılabilir", "is_official": True},
                    {"rule_title": "Çember Kuralı", "rule_description": "Kaleci çemberi içine sahadan giremez", "is_official": True},
                    {"rule_title": "Pasif Oyun", "rule_description": "Uzun süre gol atmaya çalışmamak yasaktır", "is_official": True}
                ],
                "equipments": [
                    {"name": "Hentbol Topu", "is_required": True, "description": "2 veya 3 numara"},
                    {"name": "Spor Ayakkabı", "is_required": True}
                ],
                "is_system_default": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "id": str(uuid.uuid4()),
                "sport_name": "Badminton",
                "sport_name_en": "Badminton",
                "category": "Raket Sporları",
                "description": "1'e 1 veya 2'ye 2 oynanan raket sporu",
                "field_type": ["indoor", "wood"],
                "field_dimensions": {
                    "length_min": 13.4,
                    "length_max": 13.4,
                    "width_min": 5.18,
                    "width_max": 6.1,
                    "height_min": 7.5,
                    "court_count": 1
                },
                "player_count": {
                    "min_per_team": 1,
                    "max_per_team": 2,
                    "on_field_per_team": 1,
                    "substitutes_per_team": 0,
                    "min_to_start": 1
                },
                "game_duration": {
                    "periods": 3,
                    "period_duration_minutes": 0,
                    "break_duration_minutes": 2,
                    "timeout_count": 0
                },
                "scoring_system": "sets_points",
                "scoring_details": "21 sayı = 1 set, 2 set kazanan maçı alır",
                "rules": [
                    {"rule_title": "Servis", "rule_description": "Servis çapraz karşı alana atılır", "is_official": True},
                    {"rule_title": "Ralli Sistemi", "rule_description": "Her ralli bir sayı kazandırır", "is_official": True}
                ],
                "equipments": [
                    {"name": "Badminton Raketi", "is_required": True},
                    {"name": "Badminton Topu (Shuttlecock)", "is_required": True}
                ],
                "is_system_default": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "id": str(uuid.uuid4()),
                "sport_name": "Masa Tenisi",
                "sport_name_en": "Table Tennis",
                "category": "Raket Sporları",
                "description": "1'e 1 veya 2'ye 2 oynanan masa üstü raket sporu",
                "field_type": ["indoor"],
                "field_dimensions": {
                    "length_min": 2.74,
                    "length_max": 2.74,
                    "width_min": 1.525,
                    "width_max": 1.525,
                    "court_count": 1
                },
                "player_count": {
                    "min_per_team": 1,
                    "max_per_team": 2,
                    "on_field_per_team": 1,
                    "substitutes_per_team": 0,
                    "min_to_start": 1
                },
                "game_duration": {
                    "periods": 5,
                    "period_duration_minutes": 0,
                    "break_duration_minutes": 1,
                    "timeout_count": 1,
                    "timeout_duration_seconds": 60
                },
                "scoring_system": "sets_points",
                "scoring_details": "11 sayı = 1 set, 3 set kazanan maçı alır",
                "rules": [
                    {"rule_title": "Servis", "rule_description": "Top kendi sahanıza bir sekmeli, rakip sahaya bir sekmeli düşmeli", "is_official": True},
                    {"rule_title": "2 Servis Kuralı", "rule_description": "Her 2 serviste servis hakkı değişir", "is_official": True},
                    {"rule_title": "Deuce", "rule_description": "10-10'da her sayı servis değişir", "is_official": True}
                ],
                "equipments": [
                    {"name": "Masa Tenisi Raketi", "is_required": True},
                    {"name": "Masa Tenisi Topu", "is_required": True}
                ],
                "is_system_default": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "id": str(uuid.uuid4()),
                "sport_name": "Yüzme",
                "sport_name_en": "Swimming",
                "category": "Bireysel Sporlar",
                "description": "Havuzda yarış veya mesafe yüzme",
                "field_type": ["indoor", "outdoor"],
                "field_dimensions": {
                    "length_min": 25.0,
                    "length_max": 50.0,
                    "width_min": 12.5,
                    "width_max": 25.0,
                    "court_count": 8
                },
                "player_count": {
                    "min_per_team": 1,
                    "max_per_team": 1,
                    "on_field_per_team": 1,
                    "substitutes_per_team": 0,
                    "min_to_start": 1
                },
                "game_duration": {
                    "periods": 1,
                    "period_duration_minutes": 0,
                    "break_duration_minutes": 0
                },
                "scoring_system": "time_based",
                "scoring_details": "En hızlı tamamlayan kazanır",
                "rules": [
                    {"rule_title": "Serbest Stil", "rule_description": "Herhangi bir stil kullanılabilir", "is_official": True},
                    {"rule_title": "Kurbağalama", "rule_description": "Kol ve bacak hareketleri simetrik olmalı", "is_official": True},
                    {"rule_title": "Sırtüstü", "rule_description": "Sırt üzeri yüzülmeli", "is_official": True},
                    {"rule_title": "Kelebek", "rule_description": "Kol ve bacak hareketleri eşzamanlı olmalı", "is_official": True}
                ],
                "equipments": [
                    {"name": "Mayo", "is_required": True},
                    {"name": "Bone", "is_required": True},
                    {"name": "Gözlük", "is_required": False}
                ],
                "is_system_default": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "id": str(uuid.uuid4()),
                "sport_name": "Atletizm",
                "sport_name_en": "Athletics",
                "category": "Bireysel Sporlar",
                "description": "Koşu, atlama, atma branşlarını içeren spor",
                "field_type": ["outdoor", "indoor"],
                "field_dimensions": {
                    "length_min": 100.0,
                    "length_max": 400.0,
                    "width_min": 50.0,
                    "width_max": 100.0,
                    "court_count": 8
                },
                "player_count": {
                    "min_per_team": 1,
                    "max_per_team": 1,
                    "on_field_per_team": 1,
                    "substitutes_per_team": 0,
                    "min_to_start": 1
                },
                "game_duration": {
                    "periods": 1,
                    "period_duration_minutes": 0,
                    "break_duration_minutes": 0
                },
                "scoring_system": "time_based",
                "scoring_details": "En hızlı/uzak/yüksek performans kazanır",
                "rules": [
                    {"rule_title": "Yanlış Çıkış", "rule_description": "İkinci yanlış çıkışta diskalifiye", "is_official": True},
                    {"rule_title": "Kulvar İhlali", "rule_description": "Kulvar dışına çıkmak yasaktır", "is_official": True},
                    {"rule_title": "Atlama Hakkı", "rule_description": "3 atlama veya atma hakkı vardır", "is_official": True}
                ],
                "equipments": [
                    {"name": "Koşu Ayakkabısı", "is_required": True},
                    {"name": "Spor Kıyafeti", "is_required": True}
                ],
                "is_system_default": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
        ]
        
        await db.sport_configurations.insert_many(default_sports)
        
        logger.info(f"✅ {len(default_sports)} varsayılan spor eklendi")
        
        return {
            "success": True,
            "message": f"{len(default_sports)} varsayılan spor eklendi",
            "count": len(default_sports)
        }
    
    except Exception as e:
        logger.error(f"❌ Varsayılan sporları ekleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
