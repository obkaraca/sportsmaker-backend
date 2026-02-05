"""
Lig Yönetim Sistemi - Backend Endpoints
Lig ayarları, turlar, puan durumu, terfi/düşme yönetimi
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum
import uuid
import logging
from bson import ObjectId

# Auth import
from auth import get_current_user

# Logger setup
logger = logging.getLogger(__name__)

# Router oluştur
league_management_router = APIRouter(prefix="/event-management", tags=["League Management"])

# Database reference
_db = None

def set_league_db(database):
    """Database referansını ayarla"""
    global _db
    _db = database
    logger.info(f"✅ League Management DB set: {_db is not None}")

def get_db():
    """Database referansını al - her zaman güncel referansı döndürür"""
    global _db
    if _db is None:
        # Eğer db hala None ise, server.py'den tekrar al
        try:
            import server
            _db = server.db
            if _db is not None:
                logger.info(f"✅ League Management DB imported from server module")
        except Exception as e:
            logger.error(f"❌ Failed to import db from server: {e}")
    return _db

# ================== ENUMS ==================

class GroupNamingType(str, Enum):
    """Grup/Alt Grup isimlendirme türü"""
    ALPHABETIC = "alphabetic"  # A, B, C, D...
    NUMERIC = "numeric"  # 1, 2, 3, 4...

class PromotionMethod(str, Enum):
    """Terfi/Düşme belirleme yöntemi"""
    BY_POINTS = "by_points"  # Puan sıralamasına göre
    BY_RANK = "by_rank"  # Lig derecesine göre (manuel seçim)

class NextRoundPointsAction(str, Enum):
    """Sonraki tura geçişte puan işlemi"""
    DELETE_POINTS = "delete_points"  # Puanları sil
    CARRY_OVER = "carry_over"  # Puanları taşı

# ================== PYDANTIC MODELS ==================

class MatchExclusionRule(BaseModel):
    """Eşleşme hariç tutma kuralı"""
    rank_a: int = Field(..., ge=1, description="İlk sıra")
    rank_b: int = Field(..., ge=1, description="İkinci sıra")

class RankBonusRule(BaseModel):
    """Sıralama bonus puanı kuralı"""
    rank: int = Field(..., ge=1, description="Sıra")
    bonus_points: int = Field(..., description="Bonus puanı (negatif olabilir)")

class LeagueSettingsUpdate(BaseModel):
    """Lig ayarları güncelleme modeli"""
    players_per_group: Optional[int] = Field(None, ge=2, le=20, description="Grup başına oyuncu sayısı")
    promote_count: Optional[int] = Field(None, ge=0, le=10, description="Üst gruba çıkacak oyuncu sayısı")
    relegate_count: Optional[int] = Field(None, ge=0, le=10, description="Alt gruba inecek oyuncu sayısı")
    promotion_method: Optional[PromotionMethod] = Field(None, description="Terfi/düşme belirleme yöntemi")
    allow_player_absence: Optional[bool] = Field(None, description="Oyuncu mazeretine izin ver")
    add_previous_points: Optional[bool] = Field(None, description="Önceki puanlara ilave et")
    group_naming: Optional[GroupNamingType] = Field(None, description="Grup isimlendirme türü (ABC veya 123)")
    has_subgroups: Optional[bool] = Field(None, description="Alt grup olacak mı")
    subgroup_naming: Optional[GroupNamingType] = Field(None, description="Alt grup isimlendirme türü")
    next_league_start_date: Optional[datetime] = Field(None, description="Yeni lig başlama tarihi")
    match_exclusion_enabled: Optional[bool] = Field(None, description="Eşleşme hariç tutma kuralları aktif mi")
    match_exclusion_rules: Optional[List[MatchExclusionRule]] = Field(None, description="Eşleşme hariç tutma kuralları")
    rank_bonus_enabled: Optional[bool] = Field(None, description="Sıralama bonus puanı aktif mi")
    rank_bonus_rules: Optional[List[RankBonusRule]] = Field(None, description="Sıralama bonus puanı kuralları")

class LeagueSettingsResponse(BaseModel):
    """Lig ayarları yanıt modeli"""
    event_id: str
    players_per_group: int = 6
    promote_count: int = 2
    relegate_count: int = 2
    promotion_method: str = "by_points"
    allow_player_absence: bool = True
    add_previous_points: bool = False
    group_naming: str = "alphabetic"
    has_subgroups: bool = False
    subgroup_naming: str = "numeric"
    next_league_start_date: Optional[datetime] = None
    current_round: int = 1
    total_rounds: int = 1
    match_exclusion_enabled: bool = False
    match_exclusion_rules: List[dict] = []
    rank_bonus_enabled: bool = False
    rank_bonus_rules: List[dict] = []
    created_at: datetime
    updated_at: datetime

class CreateNextRoundRequest(BaseModel):
    """Sonraki tur oluşturma isteği - Yeni etkinlik olarak"""
    points_action: NextRoundPointsAction = Field(..., description="Puanlarla ne yapılacak")
    start_date: datetime = Field(..., description="Yeni etkinlik başlangıç tarihi")
    custom_promotions: Optional[Dict[str, List[str]]] = Field(None, description="Manuel terfi/düşme listesi (grup_id -> oyuncu_id listesi)")
    custom_relegations: Optional[Dict[str, List[str]]] = Field(None, description="Manuel düşme listesi")

class CreateNewLeagueRequest(BaseModel):
    """Yeni lig kaydı oluşturma isteği"""
    league_name: str = Field(..., description="Yeni lig adı")
    start_date: datetime = Field(..., description="Başlangıç tarihi")
    copy_settings: bool = Field(True, description="Mevcut ayarları kopyala")
    copy_players: bool = Field(True, description="Mevcut oyuncuları kopyala")
    reset_points: bool = Field(True, description="Puanları sıfırla")

class PlayerAbsenceRequest(BaseModel):
    """Oyuncu mazeret bildirimi"""
    player_id: str
    round_id: Optional[str] = None
    reason: str = Field(..., min_length=3, max_length=500)
    absence_date: datetime

class LeagueRoundResponse(BaseModel):
    """Lig turu bilgisi"""
    round_id: str
    round_number: int
    event_id: str
    start_date: datetime
    end_date: Optional[datetime]
    status: str
    groups: List[Dict[str, Any]]
    standings: List[Dict[str, Any]]
    created_at: datetime

class LeagueStandingsResponse(BaseModel):
    """Puan durumu yanıtı"""
    event_id: str
    round_number: int
    groups: List[Dict[str, Any]]
    overall_standings: List[Dict[str, Any]]

# ================== HELPER FUNCTIONS ==================

def get_group_name(index: int, naming_type: str) -> str:
    """Grup adı oluştur"""
    if naming_type == "alphabetic":
        return chr(65 + index)  # A, B, C, D...
    else:
        return str(index + 1)  # 1, 2, 3, 4...

def calculate_standings(matches: List[Dict], players: List[str]) -> List[Dict]:
    """Maç sonuçlarından puan durumu hesapla"""
    standings = {}
    
    for player_id in players:
        standings[player_id] = {
            "player_id": player_id,
            "played": 0,
            "won": 0,
            "lost": 0,
            "sets_won": 0,
            "sets_lost": 0,
            "games_won": 0,
            "games_lost": 0,
            "points": 0
        }
    
    for match in matches:
        if match.get("status") != "completed":
            continue
            
        p1_id = match.get("participant1_id")
        p2_id = match.get("participant2_id")
        winner_id = match.get("winner_id")
        
        if p1_id in standings:
            standings[p1_id]["played"] += 1
        if p2_id in standings:
            standings[p2_id]["played"] += 1
            
        if winner_id:
            if winner_id in standings:
                standings[winner_id]["won"] += 1
                standings[winner_id]["points"] += 3  # Galibiyet 3 puan
            
            loser_id = p2_id if winner_id == p1_id else p1_id
            if loser_id in standings:
                standings[loser_id]["lost"] += 1
        
        # Set ve game skorlarını ekle
        scores = match.get("scores", [])
        for score in scores:
            if p1_id in standings:
                standings[p1_id]["games_won"] += score.get("participant1_score", 0)
                standings[p1_id]["games_lost"] += score.get("participant2_score", 0)
            if p2_id in standings:
                standings[p2_id]["games_won"] += score.get("participant2_score", 0)
                standings[p2_id]["games_lost"] += score.get("participant1_score", 0)
    
    # Sıralama: Puan > Galibiyet > Averaj
    sorted_standings = sorted(
        standings.values(),
        key=lambda x: (x["points"], x["won"], x["games_won"] - x["games_lost"]),
        reverse=True
    )
    
    # Sıra numarası ekle
    for i, standing in enumerate(sorted_standings):
        standing["rank"] = i + 1
    
    return sorted_standings

async def get_event_with_auth(event_id: str, user_id: str) -> Dict:
    """Etkinliği al ve yetki kontrolü yap"""
    db = get_db()
    if db is None:
        logger.error("❌ Database is None in get_event_with_auth")
        raise HTTPException(status_code=500, detail="Database bağlantısı kurulmadı")
    
    # Önce "id" field'ı ile ara, bulamazsan "_id" ile dene
    event = await db.events.find_one({"id": event_id})
    if not event:
        event = await db.events.find_one({"_id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Organizatör veya admin kontrolü
    is_organizer = event.get("organizer_id") == user_id
    is_admin = user_id in event.get("admin_ids", [])
    
    if not is_organizer and not is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    return event

# ================== ENDPOINTS ==================

@league_management_router.get("/{event_id}/league-settings", response_model=LeagueSettingsResponse)
async def get_league_settings(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Etkinliğin lig ayarlarını getir
    """
    try:
        logger.info(f"📊 Lig ayarları getiriliyor: event_id={event_id}, user={current_user['id']}")
        
        db = get_db()
        if db is None:
            logger.error("❌ DB is None!")
            raise HTTPException(status_code=500, detail="Database bağlantısı kurulmadı")
        
        event = await get_event_with_auth(event_id, current_user["id"])
        logger.info(f"✅ Event bulundu: {event.get('name', 'unknown')}")
        
        # Lig ayarlarını al veya varsayılan oluştur
        league_settings = await db.league_settings.find_one({"event_id": event_id})
        logger.info(f"📋 Mevcut lig ayarları: {league_settings is not None}")
        
        if not league_settings:
            # Varsayılan ayarlar oluştur
            league_settings = {
                "_id": str(uuid.uuid4()),
                "event_id": event_id,
                "players_per_group": 6,
                "promote_count": 2,
                "relegate_count": 2,
                "promotion_method": "by_points",
                "allow_player_absence": True,
                "add_previous_points": False,
                "group_naming": "alphabetic",
                "has_subgroups": False,
                "subgroup_naming": "numeric",
                "next_league_start_date": None,
                "current_round": 1,
                "total_rounds": 1,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            await get_db().league_settings.insert_one(league_settings)
            logger.info(f"✅ Varsayılan lig ayarları oluşturuldu")
        
        return LeagueSettingsResponse(
            event_id=event_id,
            players_per_group=league_settings.get("players_per_group", 6),
            promote_count=league_settings.get("promote_count", 2),
            relegate_count=league_settings.get("relegate_count", 2),
            promotion_method=league_settings.get("promotion_method", "by_points"),
            allow_player_absence=league_settings.get("allow_player_absence", True),
            add_previous_points=league_settings.get("add_previous_points", False),
            group_naming=league_settings.get("group_naming", "alphabetic"),
            has_subgroups=league_settings.get("has_subgroups", False),
            subgroup_naming=league_settings.get("subgroup_naming", "numeric"),
            next_league_start_date=league_settings.get("next_league_start_date"),
            current_round=league_settings.get("current_round", 1),
            total_rounds=league_settings.get("total_rounds", 1),
            match_exclusion_enabled=league_settings.get("match_exclusion_enabled", False),
            match_exclusion_rules=league_settings.get("match_exclusion_rules", []),
            rank_bonus_enabled=league_settings.get("rank_bonus_enabled", False),
            rank_bonus_rules=league_settings.get("rank_bonus_rules", []),
            created_at=league_settings.get("created_at", datetime.utcnow()),
            updated_at=league_settings.get("updated_at", datetime.utcnow())
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Lig ayarları getirme hatası: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lig ayarları getirilemedi: {str(e)}")

@league_management_router.put("/{event_id}/league-settings", response_model=LeagueSettingsResponse)
async def update_league_settings(
    event_id: str,
    settings: LeagueSettingsUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Etkinliğin lig ayarlarını güncelle
    """
    try:
        logger.info(f"📊 Lig ayarları güncelleniyor: event_id={event_id}, user={current_user['id']}")
        logger.info(f"📋 Gelen ayarlar: {settings}")
        
        db = get_db()
        if db is None:
            logger.error("❌ DB is None!")
            raise HTTPException(status_code=500, detail="Database bağlantısı kurulmadı")
            
        event = await get_event_with_auth(event_id, current_user["id"])
        logger.info(f"✅ Event bulundu: {event.get('name', 'unknown')}")
        
        # Mevcut ayarları al
        league_settings = await db.league_settings.find_one({"event_id": event_id})
        logger.info(f"📋 Mevcut ayarlar var mı: {league_settings is not None}")
        
        if not league_settings:
            # Yeni oluştur
            league_settings = {
                "_id": str(uuid.uuid4()),
                "event_id": event_id,
                "players_per_group": 6,
                "promote_count": 2,
                "relegate_count": 2,
                "promotion_method": "by_points",
                "allow_player_absence": True,
                "group_naming": "alphabetic",
                "has_subgroups": False,
                "subgroup_naming": "numeric",
                "next_league_start_date": None,
                "current_round": 1,
                "total_rounds": 1,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            await get_db().league_settings.insert_one(league_settings)
            logger.info(f"✅ Yeni lig ayarları oluşturuldu")
        
        # Güncelleme verilerini hazırla
        update_data = {"updated_at": datetime.utcnow()}
        
        if settings.players_per_group is not None:
            update_data["players_per_group"] = settings.players_per_group
        if settings.promote_count is not None:
            update_data["promote_count"] = settings.promote_count
        if settings.relegate_count is not None:
            update_data["relegate_count"] = settings.relegate_count
        if settings.promotion_method is not None:
            update_data["promotion_method"] = settings.promotion_method.value
        if settings.allow_player_absence is not None:
            update_data["allow_player_absence"] = settings.allow_player_absence
        if settings.add_previous_points is not None:
            update_data["add_previous_points"] = settings.add_previous_points
        if settings.group_naming is not None:
            update_data["group_naming"] = settings.group_naming.value
        if settings.has_subgroups is not None:
            update_data["has_subgroups"] = settings.has_subgroups
        if settings.subgroup_naming is not None:
            update_data["subgroup_naming"] = settings.subgroup_naming.value
        if settings.next_league_start_date is not None:
            update_data["next_league_start_date"] = settings.next_league_start_date
        if settings.match_exclusion_enabled is not None:
            update_data["match_exclusion_enabled"] = settings.match_exclusion_enabled
        if settings.match_exclusion_rules is not None:
            update_data["match_exclusion_rules"] = [{"rank_a": r.rank_a, "rank_b": r.rank_b} for r in settings.match_exclusion_rules]
        if settings.rank_bonus_enabled is not None:
            update_data["rank_bonus_enabled"] = settings.rank_bonus_enabled
        if settings.rank_bonus_rules is not None:
            update_data["rank_bonus_rules"] = [{"rank": r.rank, "bonus_points": r.bonus_points} for r in settings.rank_bonus_rules]
        
        logger.info(f"📋 Güncelleme verileri: {update_data}")
        
        # Güncelle
        await get_db().league_settings.update_one(
            {"event_id": event_id},
            {"$set": update_data}
        )
        logger.info(f"✅ Güncelleme tamamlandı")
        
        # Güncel ayarları getir
        updated_settings = await get_db().league_settings.find_one({"event_id": event_id})
        
        logger.info(f"✅ Lig ayarları güncellendi: event_id={event_id}")
        
        return LeagueSettingsResponse(
            event_id=event_id,
            players_per_group=updated_settings.get("players_per_group", 6),
            promote_count=updated_settings.get("promote_count", 2),
            relegate_count=updated_settings.get("relegate_count", 2),
            promotion_method=updated_settings.get("promotion_method", "by_points"),
            allow_player_absence=updated_settings.get("allow_player_absence", True),
            add_previous_points=updated_settings.get("add_previous_points", False),
            group_naming=updated_settings.get("group_naming", "alphabetic"),
            has_subgroups=updated_settings.get("has_subgroups", False),
            subgroup_naming=updated_settings.get("subgroup_naming", "numeric"),
            next_league_start_date=updated_settings.get("next_league_start_date"),
            current_round=updated_settings.get("current_round", 1),
            total_rounds=updated_settings.get("total_rounds", 1),
            match_exclusion_enabled=updated_settings.get("match_exclusion_enabled", False),
            match_exclusion_rules=updated_settings.get("match_exclusion_rules", []),
            rank_bonus_enabled=updated_settings.get("rank_bonus_enabled", False),
            rank_bonus_rules=updated_settings.get("rank_bonus_rules", []),
            created_at=updated_settings.get("created_at", datetime.utcnow()),
            updated_at=updated_settings.get("updated_at", datetime.utcnow())
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lig ayarları güncelleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lig ayarları güncellenemedi: {str(e)}")

@league_management_router.get("/{event_id}/league/standings")
async def get_league_standings(
    event_id: str,
    round_number: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Lig puan durumunu getir
    """
    try:
        event = await get_event_with_auth(event_id, current_user["id"])
        
        # Lig ayarlarını al
        league_settings = await get_db().league_settings.find_one({"event_id": event_id})
        current_round = round_number or (league_settings.get("current_round", 1) if league_settings else 1)
        
        # Grupları al
        groups = await get_db().groups.find({"event_id": event_id}).to_list(100)
        
        group_standings = []
        overall_standings = []
        
        for group in groups:
            group_id = group.get("_id")
            participant_ids = group.get("participant_ids", [])
            
            # Grup maçlarını al
            matches = await get_db().matches.find({
                "event_id": event_id,
                "group_id": group_id,
                "status": "completed"
            }).to_list(1000)
            
            # Puan durumunu hesapla
            standings = calculate_standings(matches, participant_ids)
            
            # Oyuncu bilgilerini ekle
            for standing in standings:
                player = await get_db().users.find_one({"_id": standing["player_id"]})
                if player:
                    standing["player_name"] = player.get("name", "Bilinmeyen")
                    standing["player_avatar"] = player.get("profile_image", "")
                else:
                    standing["player_name"] = "Bilinmeyen"
                    standing["player_avatar"] = ""
            
            group_standings.append({
                "group_id": group_id,
                "group_name": group.get("name", "Grup"),
                "standings": standings
            })
            
            overall_standings.extend(standings)
        
        # Genel sıralama
        overall_standings = sorted(
            overall_standings,
            key=lambda x: (x["points"], x["won"], x["games_won"] - x["games_lost"]),
            reverse=True
        )
        
        for i, standing in enumerate(overall_standings):
            standing["overall_rank"] = i + 1
        
        return {
            "event_id": event_id,
            "round_number": current_round,
            "groups": group_standings,
            "overall_standings": overall_standings
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Puan durumu getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Puan durumu getirilemedi: {str(e)}")

@league_management_router.post("/{event_id}/create-next-round")
async def create_next_round(
    event_id: str,
    request: CreateNextRoundRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Sonraki lig turunu YENİ ETKİNLİK olarak oluştur
    - Yeni etkinlik: "[Lig Adı] - [Başlangıç Tarihi]"
    - Tüm oyuncular yeni etkinliğe aktarılır
    - Gruplar kopyalanmaz (organizatör yeniden oluşturur)
    - Puanlar seçime göre taşınır veya sıfırlanır
    - Mevcut etkinlik "completed" olarak işaretlenir
    """
    logger.info(f"🔵 CREATE-NEXT-ROUND endpoint çağrıldı: event_id={event_id}, user={current_user.get('id', 'unknown')}")
    logger.info(f"🔵 Request: points_action={request.points_action}, start_date={request.start_date}")
    
    try:
        # Mevcut etkinliği al
        logger.info(f"🔵 Mevcut etkinlik alınıyor...")
        event = await get_event_with_auth(event_id, current_user["id"])
        logger.info(f"🟢 Mevcut etkinlik: {event.get('name', 'unknown')}")
        
        # Lig ayarlarını al
        league_settings = await get_db().league_settings.find_one({"event_id": event_id})
        current_round = league_settings.get("current_round", 1) if league_settings else 1
        
        # Mevcut grupları al (puan hesaplaması için)
        groups = await get_db().groups.find({"event_id": event_id}).to_list(100)
        
        # Her grup için puan durumunu hesapla
        group_standings = {}
        all_participants = set()
        for group in groups:
            group_id = group.get("_id")
            participant_ids = group.get("participant_ids", [])
            all_participants.update(participant_ids)
            
            matches = await get_db().matches.find({
                "event_id": event_id,
                "group_id": group_id,
                "status": "completed"
            }).to_list(1000)
            
            standings = calculate_standings(matches, participant_ids)
            group_standings[group_id] = standings
        
        # Ayrıca event_participants'tan da oyuncuları al
        event_participants = await get_db().event_participants.find({"event_id": event_id}).to_list(1000)
        for ep in event_participants:
            all_participants.add(ep.get("user_id"))
        
        all_participants = list(all_participants)
        logger.info(f"📊 Toplam {len(all_participants)} oyuncu aktarılacak")
        
        # ==================== KULLANICI BAZLI PUAN KAYDI ====================
        event_name = event.get("name", event.get("title", "Lig"))
        score_date = datetime.utcnow().strftime("%Y-%m-%d")
        score_label = f"{event_name} ({score_date})"
        
        logger.info(f"📊 Kullanıcı bazlı puan kaydı oluşturuluyor: {score_label}")
        
        for group in groups:
            group_id = group.get("_id")
            standings = group_standings.get(group_id, [])
            group_name = group.get("name", "")
            
            for standing in standings:
                player_id = standing.get("player_id")
                points = standing.get("points", 0)
                
                user_score_record = {
                    "_id": str(uuid.uuid4()),
                    "user_id": player_id,
                    "event_id": event_id,
                    "event_name": event_name,
                    "round_number": current_round,
                    "group_name": group_name,
                    "score_label": score_label,
                    "points": points,
                    "wins": standing.get("won", 0),
                    "losses": standing.get("lost", 0),
                    "matches_played": standing.get("played", 0),
                    "created_at": datetime.utcnow(),
                    "score_type": "league_round"
                }
                
                await get_db().user_scores.insert_one(user_score_record)
        
        logger.info(f"✅ Kullanıcı puanları kaydedildi")
        
        # ==================== YENİ ETKİNLİK OLUŞTUR ====================
        # Yeni etkinlik adı: "[Lig Adı] - [Başlangıç Tarihi]"
        start_date_str = request.start_date.strftime("%d %B %Y")
        # Türkçe ay isimleri
        month_names = {
            "January": "Ocak", "February": "Şubat", "March": "Mart", "April": "Nisan",
            "May": "Mayıs", "June": "Haziran", "July": "Temmuz", "August": "Ağustos",
            "September": "Eylül", "October": "Ekim", "November": "Kasım", "December": "Aralık"
        }
        for eng, tr in month_names.items():
            start_date_str = start_date_str.replace(eng, tr)
        
        base_name = event.get("name", event.get("title", "Lig"))
        # Eğer isimde zaten tarih varsa, sadece tarihi güncelle
        if " - " in base_name:
            base_name = base_name.split(" - ")[0]
        
        new_event_name = f"{base_name} - {start_date_str}"
        new_event_id = str(uuid.uuid4())
        
        logger.info(f"📝 Yeni etkinlik oluşturuluyor: {new_event_name}")
        
        # Mevcut etkinliğin TÜM ayarlarını kopyala
        # Kopyalanmayacak alanlar: _id, id, name, title, start_date, end_date, created_at, updated_at, status
        excluded_fields = {"_id", "id", "name", "title", "start_date", "end_date", "created_at", "updated_at", "status"}
        
        new_event = {}
        for key, value in event.items():
            if key not in excluded_fields:
                new_event[key] = value
        
        # Yeni değerleri ekle/güncelle
        new_event.update({
            "_id": new_event_id,
            "id": new_event_id,
            "name": new_event_name,
            "title": new_event_name,
            "start_date": request.start_date,
            "end_date": request.start_date + timedelta(days=7),  # Varsayılan 1 hafta
            "organizer_id": current_user["id"],
            "created_by": current_user["id"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "status": "upcoming",
            "parent_event_id": event_id,  # Kaynak etkinlik referansı
            "round_number": current_round + 1,
            "is_continuation": True
        })
        
        await get_db().events.insert_one(new_event)
        logger.info(f"✅ Yeni etkinlik oluşturuldu: {new_event_id}")
        
        # ==================== OYUNCULARI YENİ ETKİNLİĞE AKTAR ====================
        # Mevcut oyuncuların puan bilgilerini topla
        player_points = {}
        if request.points_action == NextRoundPointsAction.CARRY_OVER:
            # Puanları taşı - mevcut event_standings'den al
            existing_standings = await get_db().event_standings.find({"event_id": event_id}).to_list(1000)
            for standing in existing_standings:
                player_id = standing.get("player_id")
                player_points[player_id] = {
                    "points": standing.get("points", 0),
                    "custom_score": standing.get("custom_score", 0),
                    "wins": standing.get("wins", 0),
                    "losses": standing.get("losses", 0),
                    "scored": standing.get("scored", 0),
                    "conceded": standing.get("conceded", 0)
                }
        
        # Yeni event_participants kayıtları oluştur
        for player_id in all_participants:
            existing_participant = await get_db().event_participants.find_one({
                "event_id": event_id,
                "user_id": player_id
            })
            
            new_participant = {
                "_id": str(uuid.uuid4()),
                "event_id": new_event_id,
                "user_id": player_id,
                "status": "confirmed",
                "registration_date": datetime.utcnow(),
                "points": player_points.get(player_id, {}).get("points", 0) if request.points_action == NextRoundPointsAction.CARRY_OVER else 0,
                "gender": existing_participant.get("gender") if existing_participant else None,
                "age_group": existing_participant.get("age_group") if existing_participant else None,
                "team_id": existing_participant.get("team_id") if existing_participant else None
            }
            
            await get_db().event_participants.insert_one(new_participant)
        
        logger.info(f"✅ {len(all_participants)} oyuncu yeni etkinliğe aktarıldı")
        
        # ==================== PUANLARI YENİ ETKİNLİĞE AKTAR ====================
        if request.points_action == NextRoundPointsAction.CARRY_OVER:
            # event_standings'i kopyala
            for player_id, points_data in player_points.items():
                new_standing = {
                    "_id": str(uuid.uuid4()),
                    "event_id": new_event_id,
                    "player_id": player_id,
                    "points": points_data.get("points", 0),
                    "custom_score": points_data.get("custom_score", 0),
                    "wins": points_data.get("wins", 0),
                    "losses": points_data.get("losses", 0),
                    "scored": points_data.get("scored", 0),
                    "conceded": points_data.get("conceded", 0),
                    "matches_played": 0,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                await get_db().event_standings.insert_one(new_standing)
            
            # Sporcu ekranındaki puanlara da taşı (event_athlete_points tablosu)
            for player_id, points_data in player_points.items():
                total_points = points_data.get("points", 0) + points_data.get("custom_score", 0)
                
                # Mevcut sporcu puanını al
                existing_athlete_point = await get_db().event_athlete_points.find_one({
                    "event_id": event_id,
                    "participant_id": player_id
                })
                
                # Yeni etkinlik için sporcu puanı oluştur
                new_athlete_point = {
                    "_id": str(uuid.uuid4()),
                    "event_id": new_event_id,
                    "participant_id": player_id,
                    "points": total_points,
                    "base_points": points_data.get("points", 0),
                    "bonus_points": points_data.get("custom_score", 0),
                    "wins": points_data.get("wins", 0),
                    "losses": points_data.get("losses", 0),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "carried_from_event": event_id
                }
                
                await get_db().event_athlete_points.insert_one(new_athlete_point)
            
            logger.info(f"✅ Puanlar sporcu ekranına ve standings'e taşındı")
        
        # ==================== LİG AYARLARINI KOPYALA ====================
        if league_settings:
            new_league_settings = {
                "_id": str(uuid.uuid4()),
                "event_id": new_event_id,
                "current_round": 1,
                "total_rounds": league_settings.get("total_rounds", 10),
                "promote_count": league_settings.get("promote_count", 2),
                "relegate_count": league_settings.get("relegate_count", 2),
                "promotion_method": league_settings.get("promotion_method", "by_points"),
                "group_naming": league_settings.get("group_naming", "alphabetic"),
                "players_per_group": league_settings.get("players_per_group", 7),
                "add_previous_points": request.points_action == NextRoundPointsAction.CARRY_OVER,
                "created_at": datetime.utcnow(),
                "parent_event_id": event_id
            }
            await get_db().league_settings.insert_one(new_league_settings)
            logger.info(f"✅ Lig ayarları kopyalandı")
        
        # ==================== ESKİ ETKİNLİĞİ TAMAMLANDI OLARAK İŞARETLE ====================
        await get_db().events.update_one(
            {"id": event_id},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.utcnow(),
                    "next_event_id": new_event_id,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # _id ile de dene
        await get_db().events.update_one(
            {"_id": event_id},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.utcnow(),
                    "next_event_id": new_event_id,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"✅ Eski etkinlik 'completed' olarak işaretlendi")
        
        # ==================== SONUÇ ====================
        points_message = "Puanlar sıfırlandı" if request.points_action == NextRoundPointsAction.DELETE_POINTS else "Puanlar taşındı"
        
        logger.info(f"🎉 Yeni lig turu başarıyla oluşturuldu: {new_event_name}")
        
        return {
            "success": True,
            "message": f"Yeni lig oluşturuldu: {new_event_name}",
            "new_event_id": new_event_id,
            "new_event_name": new_event_name,
            "previous_event_id": event_id,
            "players_transferred": len(all_participants),
            "points_action": request.points_action.value,
            "points_message": points_message
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sonraki tur oluşturma hatası: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Sonraki tur oluşturulamadı: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Sonraki tur oluşturulamadı: {str(e)}")

@league_management_router.post("/{event_id}/league/create-new-league")
async def create_new_league(
    event_id: str,
    request: CreateNewLeagueRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Yeni lig kaydı oluştur
    - Mevcut etkinliği kopyala
    - Yeni etkinlik olarak kaydet
    - İsteğe bağlı oyuncu ve ayar kopyalama
    """
    try:
        event = await get_event_with_auth(event_id, current_user["id"])
        
        # Yeni etkinlik ID
        new_event_id = str(uuid.uuid4())
        
        # Mevcut etkinliği kopyala
        new_event = event.copy()
        new_event["_id"] = new_event_id
        new_event["name"] = request.league_name
        new_event["start_date"] = request.start_date
        new_event["created_at"] = datetime.utcnow()
        new_event["updated_at"] = datetime.utcnow()
        new_event["parent_event_id"] = event_id  # Kaynak etkinlik referansı
        new_event["is_new_season"] = True
        
        # Etkinliği kaydet
        await get_db().events.insert_one(new_event)
        
        # Ayarları kopyala
        if request.copy_settings:
            league_settings = await get_db().league_settings.find_one({"event_id": event_id})
            if league_settings:
                new_settings = league_settings.copy()
                new_settings["_id"] = str(uuid.uuid4())
                new_settings["event_id"] = new_event_id
                new_settings["current_round"] = 1
                new_settings["total_rounds"] = 1
                new_settings["next_league_start_date"] = None
                new_settings["created_at"] = datetime.utcnow()
                new_settings["updated_at"] = datetime.utcnow()
                await get_db().league_settings.insert_one(new_settings)
        
        # Oyuncuları kopyala
        if request.copy_players:
            # Grupları kopyala
            groups = await get_db().groups.find({"event_id": event_id}).to_list(100)
            for group in groups:
                new_group = group.copy()
                new_group["_id"] = str(uuid.uuid4())
                new_group["event_id"] = new_event_id
                new_group["created_at"] = datetime.utcnow()
                await get_db().groups.insert_one(new_group)
            
            # Katılımcıları kopyala
            participants = await get_db().event_participants.find({"event_id": event_id}).to_list(1000)
            for participant in participants:
                new_participant = participant.copy()
                new_participant["_id"] = str(uuid.uuid4())
                new_participant["event_id"] = new_event_id
                new_participant["points"] = 0 if request.reset_points else participant.get("points", 0)
                new_participant["created_at"] = datetime.utcnow()
                await get_db().event_participants.insert_one(new_participant)
        
        logger.info(f"✅ Yeni lig oluşturuldu: {request.league_name}, new_event_id={new_event_id}")
        
        return {
            "success": True,
            "message": f"Yeni lig '{request.league_name}' başarıyla oluşturuldu",
            "new_event_id": new_event_id,
            "league_name": request.league_name,
            "start_date": request.start_date.isoformat(),
            "settings_copied": request.copy_settings,
            "players_copied": request.copy_players,
            "points_reset": request.reset_points
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Yeni lig oluşturma hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Yeni lig oluşturulamadı: {str(e)}")

@league_management_router.post("/{event_id}/league/player-absence")
async def submit_player_absence(
    event_id: str,
    request: PlayerAbsenceRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Oyuncu mazeret bildirimi
    """
    try:
        event = await get_db().events.find_one({"_id": event_id})
        if not event:
            raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
        
        # Lig ayarlarını kontrol et
        league_settings = await get_db().league_settings.find_one({"event_id": event_id})
        if league_settings and not league_settings.get("allow_player_absence", True):
            raise HTTPException(status_code=400, detail="Bu ligde mazeret bildirimi kapalı")
        
        # Mazeret kaydı oluştur
        absence_record = {
            "_id": str(uuid.uuid4()),
            "event_id": event_id,
            "player_id": request.player_id,
            "round_id": request.round_id,
            "reason": request.reason,
            "absence_date": request.absence_date,
            "status": "pending",  # pending, approved, rejected
            "submitted_by": current_user["id"],
            "created_at": datetime.utcnow()
        }
        
        await get_db().player_absences.insert_one(absence_record)
        
        logger.info(f"✅ Mazeret bildirimi kaydedildi: player={request.player_id}, event={event_id}")
        
        return {
            "success": True,
            "message": "Mazeret bildirimi başarıyla kaydedildi",
            "absence_id": absence_record["_id"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mazeret bildirimi hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Mazeret bildirilemedi: {str(e)}")

@league_management_router.get("/{event_id}/league/player-absences")
async def get_player_absences(
    event_id: str,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Oyuncu mazeretlerini listele
    """
    try:
        await get_event_with_auth(event_id, current_user["id"])
        
        query = {"event_id": event_id}
        if status:
            query["status"] = status
        
        absences = await get_db().player_absences.find(query).sort("created_at", -1).to_list(100)
        
        # Oyuncu bilgilerini ekle
        for absence in absences:
            player = await get_db().users.find_one({"_id": absence["player_id"]})
            if player:
                absence["player_name"] = player.get("name", "Bilinmeyen")
                absence["player_avatar"] = player.get("profile_image", "")
        
        return {
            "absences": absences,
            "total": len(absences)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mazeretleri getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Mazeretler getirilemedi: {str(e)}")

@league_management_router.put("/{event_id}/league/player-absences/{absence_id}")
async def update_player_absence(
    event_id: str,
    absence_id: str,
    status: str = Query(..., regex="^(approved|rejected)$"),
    current_user: dict = Depends(get_current_user)
):
    """
    Oyuncu mazeretini onayla/reddet
    """
    try:
        await get_event_with_auth(event_id, current_user["id"])
        
        result = await get_db().player_absences.update_one(
            {"_id": absence_id, "event_id": event_id},
            {
                "$set": {
                    "status": status,
                    "reviewed_by": current_user["id"],
                    "reviewed_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Mazeret kaydı bulunamadı")
        
        return {
            "success": True,
            "message": f"Mazeret {'onaylandı' if status == 'approved' else 'reddedildi'}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mazeret güncelleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Mazeret güncellenemedi: {str(e)}")

@league_management_router.get("/{event_id}/league/rounds")
async def get_league_rounds(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Lig turlarını listele (geçmiş turlar)
    """
    try:
        await get_event_with_auth(event_id, current_user["id"])
        
        rounds = await get_db().league_rounds.find({"event_id": event_id}).sort("round_number", -1).to_list(100)
        
        return {
            "rounds": rounds,
            "total": len(rounds)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lig turlarını getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lig turları getirilemedi: {str(e)}")

@league_management_router.get("/{event_id}/league/promotion-preview")
async def get_promotion_preview(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Terfi/düşme önizlemesi - mevcut puan durumuna göre
    """
    try:
        await get_event_with_auth(event_id, current_user["id"])
        
        # Lig ayarlarını al
        league_settings = await get_db().league_settings.find_one({"event_id": event_id})
        if not league_settings:
            raise HTTPException(status_code=400, detail="Lig ayarları bulunamadı")
        
        promote_count = league_settings.get("promote_count", 2)
        relegate_count = league_settings.get("relegate_count", 2)
        
        # Grupları al
        groups = await get_db().groups.find({"event_id": event_id}).to_list(100)
        groups = sorted(groups, key=lambda x: x.get("name", ""))
        
        preview = []
        
        for i, group in enumerate(groups):
            group_id = group.get("_id")
            participant_ids = group.get("participant_ids", [])
            
            # Maçları al
            matches = await get_db().matches.find({
                "event_id": event_id,
                "group_id": group_id,
                "status": "completed"
            }).to_list(1000)
            
            # Puan durumunu hesapla
            standings = calculate_standings(matches, participant_ids)
            
            # Oyuncu bilgilerini ekle
            for standing in standings:
                player = await get_db().users.find_one({"_id": standing["player_id"]})
                if player:
                    standing["player_name"] = player.get("name", "Bilinmeyen")
            
            # Terfi/düşme durumunu belirle
            for j, standing in enumerate(standings):
                if i > 0 and j < promote_count:
                    standing["status"] = "promoting"
                    standing["status_text"] = "Üst gruba çıkacak"
                elif i < len(groups) - 1 and j >= len(standings) - relegate_count:
                    standing["status"] = "relegating"
                    standing["status_text"] = "Alt gruba inecek"
                else:
                    standing["status"] = "staying"
                    standing["status_text"] = "Grupta kalacak"
            
            preview.append({
                "group_id": group_id,
                "group_name": group.get("name", f"Grup {i + 1}"),
                "standings": standings,
                "promote_count": promote_count if i > 0 else 0,
                "relegate_count": relegate_count if i < len(groups) - 1 else 0
            })
        
        return {
            "event_id": event_id,
            "preview": preview,
            "settings": {
                "promote_count": promote_count,
                "relegate_count": relegate_count,
                "promotion_method": league_settings.get("promotion_method", "by_points")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Terfi önizleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Önizleme getirilemedi: {str(e)}")
