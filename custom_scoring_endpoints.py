"""
Özel Puanlama Sistemi - Backend Endpoints
Esnek, parametre tabanlı puanlama sistemi
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import logging

# Logger setup
logger = logging.getLogger(__name__)

# Router oluştur
custom_scoring_router = APIRouter(prefix="/custom-scoring", tags=["Custom Scoring"])

# Global db reference
db = None

def set_custom_scoring_db(database):
    """Database referansını ayarla"""
    global db
    db = database
    logger.info(f"✅ Custom Scoring DB set: {db is not None}")

# ================== PYDANTIC MODELS ==================

class MatchResultPoints(BaseModel):
    """Maç sonucu puanları"""
    win: int = 2  # Galibiyet
    loss: int = 0  # Mağlubiyet
    draw: int = 1  # Beraberlik
    forfeit_loss: int = -2  # Hükmen mağlubiyet
    forfeit_win: int = 2  # Hükmen galibiyet

class ScoreDifferenceBonus(BaseModel):
    """Puan farkı bonusları"""
    enabled: bool = True
    close_score_threshold: int = 2  # Yakın skor eşiği (fark <= bu değer)
    close_score_bonus: int = 10  # Yakın skor bonusu (kaybedene verilir)
    dominant_win_threshold: int = 5  # Baskın galibiyet eşiği (fark >= bu değer)
    dominant_win_bonus: int = 5  # Baskın galibiyet bonusu (kazanana verilir)

class SetDifferencePoints(BaseModel):
    """Set farkı puanlaması"""
    enabled: bool = False
    points_per_set: int = 1  # Her set farkı için puan (kazanana eklenir, kaybedenden düşülür)

class OpponentStrengthTier(BaseModel):
    """Rakip gücü puan farkı kademesi"""
    min_diff: int  # Minimum puan farkı
    max_diff: int  # Maximum puan farkı (999 = sınırsız)
    higher_wins: int  # Yüksek puanlı kazanırsa
    lower_wins: int  # Düşük puanlı kazanırsa
    higher_loses: int  # Yüksek puanlı kaybederse
    lower_loses: int  # Düşük puanlı kaybederse

class OpponentStrengthBonus(BaseModel):
    """Rakip gücü bonusu (Faz 2)"""
    enabled: bool = False
    beat_higher_ranked_bonus: int = 15  # Üst sıradaki rakibi yenme bonusu
    beat_much_higher_bonus: int = 25  # Çok üst sıradaki rakibi yenme bonusu (5+ sıra fark)
    lose_to_lower_penalty: int = -5  # Alt sıradaki rakibe kaybetme cezası
    use_tier_table: bool = False  # Kademe tablosu kullan
    tiers: List[OpponentStrengthTier] = [
        OpponentStrengthTier(min_diff=0, max_diff=5, higher_wins=0, lower_wins=5, higher_loses=-2, lower_loses=0),
        OpponentStrengthTier(min_diff=6, max_diff=10, higher_wins=0, lower_wins=10, higher_loses=-5, lower_loses=0),
        OpponentStrengthTier(min_diff=11, max_diff=20, higher_wins=0, lower_wins=15, higher_loses=-10, lower_loses=0),
        OpponentStrengthTier(min_diff=21, max_diff=999, higher_wins=0, lower_wins=25, higher_loses=-15, lower_loses=0)
    ]

class FairPlayPoints(BaseModel):
    """Adil oyun puanları (Faz 2)"""
    enabled: bool = False
    no_warnings_bonus: int = 5  # Uyarı almadan bitirme bonusu
    yellow_card_penalty: int = -5  # Sarı kart cezası
    red_card_penalty: int = -15  # Kırmızı kart cezası
    unsportsmanlike_penalty: int = -20  # Sportmenlik dışı davranış cezası

class ParticipationPoints(BaseModel):
    """Katılım puanları (Faz 2)"""
    enabled: bool = False
    attendance_bonus: int = 5  # Maça katılım bonusu
    streak_bonus: int = 10  # Ardışık katılım bonusu (3+ maç)
    no_show_penalty: int = -10  # Maça gelmeme cezası

class AbsencePenalty(BaseModel):
    """Lige katılmama puan cezası"""
    enabled: bool = False
    penalty_points: int = -10  # Varsayılan ceza puanı

class BonusPenaltyEvents(BaseModel):
    """Bonus ve ceza olayları (Faz 2)"""
    enabled: bool = False
    events: List[Dict[str, Any]] = []  # Özel olaylar listesi

class CustomScoringConfig(BaseModel):
    """Özel puanlama konfigürasyonu"""
    event_id: str
    enabled: bool = False
    version: int = 1
    
    # Temel modüller
    match_result: MatchResultPoints = MatchResultPoints()
    score_difference: ScoreDifferenceBonus = ScoreDifferenceBonus()
    set_difference: SetDifferencePoints = SetDifferencePoints()  # Yeni: Set farkı puanlaması
    
    # Gelişmiş modüller (Faz 2)
    opponent_strength: OpponentStrengthBonus = OpponentStrengthBonus()
    fair_play: FairPlayPoints = FairPlayPoints()
    participation: ParticipationPoints = ParticipationPoints()
    absence_penalty: AbsencePenalty = AbsencePenalty()  # Lige katılmama cezası
    bonus_penalty: BonusPenaltyEvents = BonusPenaltyEvents()
    
    # Beraberlik bozma kuralları
    tiebreaker_rules: List[str] = ["head_to_head", "score_difference", "fair_play", "participation"]
    
    # Meta bilgiler
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None

class CustomScoringConfigUpdate(BaseModel):
    """Güncelleme modeli"""
    enabled: Optional[bool] = None
    match_result: Optional[MatchResultPoints] = None
    score_difference: Optional[ScoreDifferenceBonus] = None
    opponent_strength: Optional[OpponentStrengthBonus] = None
    fair_play: Optional[FairPlayPoints] = None
    participation: Optional[ParticipationPoints] = None
    bonus_penalty: Optional[BonusPenaltyEvents] = None
    tiebreaker_rules: Optional[List[str]] = None

class MatchScoreInput(BaseModel):
    """Maç skoru girişi"""
    match_id: str
    event_id: str
    participant1_id: str
    participant2_id: str
    score1: int
    score2: int
    winner_id: Optional[str] = None
    is_forfeit: bool = False  # Hükmen mi?
    forfeit_by: Optional[str] = None  # Kim hükmen kaybetti?

class CalculatedPoints(BaseModel):
    """Hesaplanmış puanlar"""
    participant_id: str
    participant_name: Optional[str] = None
    total_points: int
    breakdown: Dict[str, int]  # Modül bazlı döküm
    explanation: str  # Açıklama

# ================== HELPER FUNCTIONS ==================

async def calculate_match_points(
    config: dict,
    match_input: MatchScoreInput,
    participant1_rank: int = 0,
    participant2_rank: int = 0
) -> tuple:
    """
    Maç puanlarını hesapla
    Returns: (participant1_points, participant2_points) as CalculatedPoints
    """
    global db
    
    p1_breakdown = {}
    p2_breakdown = {}
    p1_explanation = []
    p2_explanation = []
    
    match_result = config.get("match_result", {})
    score_diff = config.get("score_difference", {})
    
    score1 = match_input.score1
    score2 = match_input.score2
    difference = abs(score1 - score2)
    
    # 1. MAÇIN SONUCU PUANLARI
    if match_input.is_forfeit:
        # Hükmen sonuç
        if match_input.forfeit_by == match_input.participant1_id:
            p1_breakdown["match_result"] = match_result.get("forfeit_loss", -2)
            p2_breakdown["match_result"] = match_result.get("forfeit_win", 2)
            p1_explanation.append(f"Hükmen mağlubiyet: {p1_breakdown['match_result']} puan")
            p2_explanation.append(f"Hükmen galibiyet: {p2_breakdown['match_result']} puan")
        else:
            p1_breakdown["match_result"] = match_result.get("forfeit_win", 2)
            p2_breakdown["match_result"] = match_result.get("forfeit_loss", -2)
            p1_explanation.append(f"Hükmen galibiyet: {p1_breakdown['match_result']} puan")
            p2_explanation.append(f"Hükmen mağlubiyet: {p2_breakdown['match_result']} puan")
    elif score1 > score2:
        # Participant 1 kazandı
        p1_breakdown["match_result"] = match_result.get("win", 2)
        p2_breakdown["match_result"] = match_result.get("loss", 0)
        p1_explanation.append(f"Galibiyet: {p1_breakdown['match_result']} puan")
        p2_explanation.append(f"Mağlubiyet: {p2_breakdown['match_result']} puan")
    elif score2 > score1:
        # Participant 2 kazandı
        p1_breakdown["match_result"] = match_result.get("loss", 0)
        p2_breakdown["match_result"] = match_result.get("win", 2)
        p1_explanation.append(f"Mağlubiyet: {p1_breakdown['match_result']} puan")
        p2_explanation.append(f"Galibiyet: {p2_breakdown['match_result']} puan")
    else:
        # Beraberlik
        p1_breakdown["match_result"] = match_result.get("draw", 1)
        p2_breakdown["match_result"] = match_result.get("draw", 1)
        p1_explanation.append(f"Beraberlik: {p1_breakdown['match_result']} puan")
        p2_explanation.append(f"Beraberlik: {p2_breakdown['match_result']} puan")
    
    # 2. PUAN FARKI BONUSU
    if score_diff.get("enabled", True):
        close_threshold = score_diff.get("close_score_threshold", 2)
        close_bonus = score_diff.get("close_score_bonus", 10)
        dominant_threshold = score_diff.get("dominant_win_threshold", 5)
        dominant_bonus = score_diff.get("dominant_win_bonus", 5)
        
        if difference <= close_threshold and score1 != score2:
            # Yakın skor - kaybedene bonus
            if score1 > score2:
                p2_breakdown["close_score_bonus"] = close_bonus
                p2_explanation.append(f"Yakın skor bonusu (fark: {difference}): +{close_bonus} puan")
            else:
                p1_breakdown["close_score_bonus"] = close_bonus
                p1_explanation.append(f"Yakın skor bonusu (fark: {difference}): +{close_bonus} puan")
        
        if difference >= dominant_threshold:
            # Baskın galibiyet - kazanana bonus
            if score1 > score2:
                p1_breakdown["dominant_win_bonus"] = dominant_bonus
                p1_explanation.append(f"Baskın galibiyet bonusu (fark: {difference}): +{dominant_bonus} puan")
            elif score2 > score1:
                p2_breakdown["dominant_win_bonus"] = dominant_bonus
                p2_explanation.append(f"Baskın galibiyet bonusu (fark: {difference}): +{dominant_bonus} puan")
    
    # 3. RAKİP GÜCÜ BONUSU (Faz 2 - ileride aktif edilecek)
    opponent_strength = config.get("opponent_strength", {})
    if opponent_strength.get("enabled", False) and participant1_rank > 0 and participant2_rank > 0:
        rank_diff = abs(participant1_rank - participant2_rank)
        
        # P1 kazandıysa ve P2 daha üst sıradaysa
        if score1 > score2 and participant2_rank < participant1_rank:
            if rank_diff >= 5:
                bonus = opponent_strength.get("beat_much_higher_bonus", 25)
                p1_breakdown["opponent_strength_bonus"] = bonus
                p1_explanation.append(f"Çok üst sıradaki rakibi yenme bonusu: +{bonus} puan")
            else:
                bonus = opponent_strength.get("beat_higher_ranked_bonus", 15)
                p1_breakdown["opponent_strength_bonus"] = bonus
                p1_explanation.append(f"Üst sıradaki rakibi yenme bonusu: +{bonus} puan")
        
        # P2 kazandıysa ve P1 daha üst sıradaysa
        if score2 > score1 and participant1_rank < participant2_rank:
            if rank_diff >= 5:
                bonus = opponent_strength.get("beat_much_higher_bonus", 25)
                p2_breakdown["opponent_strength_bonus"] = bonus
                p2_explanation.append(f"Çok üst sıradaki rakibi yenme bonusu: +{bonus} puan")
            else:
                bonus = opponent_strength.get("beat_higher_ranked_bonus", 15)
                p2_breakdown["opponent_strength_bonus"] = bonus
                p2_explanation.append(f"Üst sıradaki rakibi yenme bonusu: +{bonus} puan")
    
    # Toplam puanları hesapla
    p1_total = sum(p1_breakdown.values())
    p2_total = sum(p2_breakdown.values())
    
    # Katılımcı isimlerini al
    p1_name = None
    p2_name = None
    if db is not None:
        p1_user = await db.users.find_one({"id": match_input.participant1_id})
        p2_user = await db.users.find_one({"id": match_input.participant2_id})
        p1_name = p1_user.get("full_name") if p1_user else None
        p2_name = p2_user.get("full_name") if p2_user else None
    
    p1_result = CalculatedPoints(
        participant_id=match_input.participant1_id,
        participant_name=p1_name,
        total_points=p1_total,
        breakdown=p1_breakdown,
        explanation=" | ".join(p1_explanation) if p1_explanation else "Puan yok"
    )
    
    p2_result = CalculatedPoints(
        participant_id=match_input.participant2_id,
        participant_name=p2_name,
        total_points=p2_total,
        breakdown=p2_breakdown,
        explanation=" | ".join(p2_explanation) if p2_explanation else "Puan yok"
    )
    
    return p1_result, p2_result

# ================== API ENDPOINTS ==================

@custom_scoring_router.get("/{event_id}")
async def get_custom_scoring_config(event_id: str):
    """Etkinlik için özel puanlama konfigürasyonunu getir"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    config = await db.custom_scoring_configs.find_one({"event_id": event_id})
    
    if not config:
        # Varsayılan konfigürasyon döndür
        return {
            "event_id": event_id,
            "enabled": False,
            "version": 1,
            "match_result": {
                "win": 2,
                "loss": 0,
                "draw": 1,
                "forfeit_loss": -2,
                "forfeit_win": 2
            },
            "score_difference": {
                "enabled": True,
                "close_score_threshold": 2,
                "close_score_bonus": 10,
                "dominant_win_threshold": 5,
                "dominant_win_bonus": 5
            },
            "opponent_strength": {
                "enabled": False,
                "beat_higher_ranked_bonus": 15,
                "beat_much_higher_bonus": 25,
                "lose_to_lower_penalty": -5
            },
            "fair_play": {
                "enabled": False,
                "no_warnings_bonus": 5,
                "yellow_card_penalty": -5,
                "red_card_penalty": -15,
                "unsportsmanlike_penalty": -20
            },
            "participation": {
                "enabled": False,
                "attendance_bonus": 5,
                "streak_bonus": 10,
                "no_show_penalty": -10
            },
            "tiebreaker_rules": ["head_to_head", "score_difference", "fair_play", "participation"]
        }
    
    # MongoDB _id'yi kaldır
    if "_id" in config:
        del config["_id"]
    
    return config

@custom_scoring_router.put("/{event_id}")
async def update_custom_scoring_config(event_id: str, update: CustomScoringConfigUpdate, request: Request):
    """Özel puanlama konfigürasyonunu güncelle"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    # Mevcut konfigürasyonu al veya yeni oluştur
    existing = await db.custom_scoring_configs.find_one({"event_id": event_id})
    
    update_data = update.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()
    
    if existing:
        # Güncelle
        await db.custom_scoring_configs.update_one(
            {"event_id": event_id},
            {"$set": update_data, "$inc": {"version": 1}}
        )
    else:
        # Yeni oluştur
        new_config = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "enabled": update_data.get("enabled", False),
            "version": 1,
            "match_result": update_data.get("match_result", {
                "win": 2, "loss": 0, "draw": 1, "forfeit_loss": -2, "forfeit_win": 2
            }),
            "score_difference": update_data.get("score_difference", {
                "enabled": True, "close_score_threshold": 2, "close_score_bonus": 10,
                "dominant_win_threshold": 5, "dominant_win_bonus": 5
            }),
            "set_difference": update_data.get("set_difference", {
                "enabled": False, "points_per_set": 1
            }),
            "opponent_strength": update_data.get("opponent_strength", {"enabled": False}),
            "fair_play": update_data.get("fair_play", {"enabled": False}),
            "participation": update_data.get("participation", {"enabled": False}),
            "absence_penalty": update_data.get("absence_penalty", {"enabled": False, "penalty_points": -10}),
            "bonus_penalty": update_data.get("bonus_penalty", {"enabled": False, "events": []}),
            "tiebreaker_rules": update_data.get("tiebreaker_rules", ["head_to_head", "score_difference"]),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        await db.custom_scoring_configs.insert_one(new_config)
    
    # Güncel konfigürasyonu döndür
    updated = await db.custom_scoring_configs.find_one({"event_id": event_id})
    if "_id" in updated:
        del updated["_id"]
    
    logger.info(f"✅ Custom scoring config updated for event {event_id}")
    return updated

@custom_scoring_router.post("/{event_id}/calculate")
async def calculate_points_for_match(event_id: str, match_input: MatchScoreInput):
    """Maç için puanları hesapla (önizleme)"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    # Konfigürasyonu al
    config = await db.custom_scoring_configs.find_one({"event_id": event_id})
    
    if not config or not config.get("enabled", False):
        # Özel puanlama aktif değil, standart puanlama kullan
        return {
            "custom_scoring_enabled": False,
            "message": "Özel puanlama aktif değil, standart puanlama kullanılıyor"
        }
    
    # Puanları hesapla
    p1_points, p2_points = await calculate_match_points(config, match_input)
    
    return {
        "custom_scoring_enabled": True,
        "participant1": p1_points.dict(),
        "participant2": p2_points.dict()
    }

@custom_scoring_router.post("/{event_id}/apply-to-match/{match_id}")
async def apply_custom_scoring_to_match(event_id: str, match_id: str, request: Request):
    """Maça özel puanlama uygula ve standings'i güncelle"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    # Konfigürasyonu al
    config = await db.custom_scoring_configs.find_one({"event_id": event_id})
    
    if not config or not config.get("enabled", False):
        return {"applied": False, "message": "Özel puanlama aktif değil"}
    
    # Maçı bul
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    # Skoru parse et
    score = match.get("score", "0-0")
    try:
        parts = score.split("-")
        score1 = int(parts[0].strip())
        score2 = int(parts[1].strip())
    except:
        score1, score2 = 0, 0
    
    # Match input oluştur
    match_input = MatchScoreInput(
        match_id=match_id,
        event_id=event_id,
        participant1_id=match.get("participant1_id"),
        participant2_id=match.get("participant2_id"),
        score1=score1,
        score2=score2,
        winner_id=match.get("winner_id"),
        is_forfeit=match.get("is_forfeit", False),
        forfeit_by=match.get("forfeit_by")
    )
    
    # Puanları hesapla
    p1_points, p2_points = await calculate_match_points(config, match_input)
    
    group_id = match.get("group_id")
    
    # Standings'i güncelle - Participant 1
    await db.event_standings.update_one(
        {"event_id": event_id, "group_id": group_id, "participant_id": match_input.participant1_id},
        {
            "$inc": {
                "custom_points": p1_points.total_points,
                "matches_played": 1,
                "wins": 1 if score1 > score2 else 0,
                "losses": 1 if score1 < score2 else 0,
                "draws": 1 if score1 == score2 else 0
            },
            "$set": {
                "last_match_breakdown": p1_points.breakdown,
                "updated_at": datetime.utcnow()
            },
            "$setOnInsert": {"points": 0}
        },
        upsert=True
    )
    
    # Standings'i güncelle - Participant 2
    await db.event_standings.update_one(
        {"event_id": event_id, "group_id": group_id, "participant_id": match_input.participant2_id},
        {
            "$inc": {
                "custom_points": p2_points.total_points,
                "matches_played": 1,
                "wins": 1 if score2 > score1 else 0,
                "losses": 1 if score2 < score1 else 0,
                "draws": 1 if score1 == score2 else 0
            },
            "$set": {
                "last_match_breakdown": p2_points.breakdown,
                "updated_at": datetime.utcnow()
            },
            "$setOnInsert": {"points": 0}
        },
        upsert=True
    )
    
    # Maça özel puanlama bilgisini kaydet
    await db.event_matches.update_one(
        {"id": match_id},
        {"$set": {
            "custom_scoring_applied": True,
            "custom_points": {
                "participant1": p1_points.dict(),
                "participant2": p2_points.dict()
            }
        }}
    )
    
    logger.info(f"✅ Custom scoring applied to match {match_id}: P1={p1_points.total_points}, P2={p2_points.total_points}")
    
    return {
        "applied": True,
        "participant1": p1_points.dict(),
        "participant2": p2_points.dict()
    }

@custom_scoring_router.get("/{event_id}/standings")
async def get_custom_standings(event_id: str, group_id: Optional[str] = None):
    """Özel puanlamaya göre sıralama getir"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    query = {"event_id": event_id}
    if group_id:
        query["group_id"] = group_id
    
    # custom_points'e göre sırala (yoksa points'e göre)
    standings = await db.event_standings.find(query).sort([
        ("custom_points", -1),
        ("points", -1),
        ("wins", -1)
    ]).to_list(200)
    
    # Katılımcı detaylarını ekle
    for standing in standings:
        if "_id" in standing:
            del standing["_id"]
        
        user = await db.users.find_one({"id": standing.get("participant_id")})
        standing["participant"] = {
            "id": standing.get("participant_id"),
            "name": user.get("full_name") if user else "Bilinmeyen",
            "avatar": user.get("profile_image") if user else None
        }
        
        # Toplam puanı belirle (custom_points varsa onu, yoksa points'i kullan)
        standing["display_points"] = standing.get("custom_points", standing.get("points", 0))
    
    return {"standings": standings}

@custom_scoring_router.get("/{event_id}/match/{match_id}/breakdown")
async def get_match_points_breakdown(event_id: str, match_id: str):
    """Maç puan dökümünü getir"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    custom_points = match.get("custom_points")
    if not custom_points:
        return {
            "has_custom_scoring": False,
            "message": "Bu maçta özel puanlama uygulanmamış"
        }
    
    return {
        "has_custom_scoring": True,
        "match_id": match_id,
        "score": match.get("score"),
        "participant1": custom_points.get("participant1"),
        "participant2": custom_points.get("participant2")
    }


@custom_scoring_router.post("/{event_id}/recalculate-all")
async def recalculate_all_matches(event_id: str):
    """Tüm tamamlanmış maçlar için özel puanlamayı yeniden hesapla"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    # Konfigürasyonu kontrol et
    config = await db.custom_scoring_configs.find_one({"event_id": event_id})
    if not config or not config.get("enabled", False):
        raise HTTPException(status_code=400, detail="Özel puanlama aktif değil")
    
    match_result = config.get("match_result", {})
    score_diff_config = config.get("score_difference", {})
    
    # Tüm standings'i sıfırla (scored ve conceded dahil)
    await db.event_standings.update_many(
        {"event_id": event_id},
        {"$set": {
            "points": 0,
            "custom_points": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "matches_played": 0,
            "scored": 0,
            "conceded": 0
        }}
    )
    
    # Tüm maçların standings_updated flag'ini temizle (yeniden hesaplanacak)
    await db.event_matches.update_many(
        {"event_id": event_id},
        {"$unset": {"standings_updated": ""}}
    )
    
    # Tüm tamamlanmış maçları bul
    completed_matches = await db.event_matches.find({
        "event_id": event_id,
        "status": "completed",
        "winner_id": {"$exists": True, "$ne": None}
    }).to_list(500)
    
    recalculated_count = 0
    
    for match in completed_matches:
        winner_id = match.get("winner_id")
        participant1_id = match.get("participant1_id")
        participant2_id = match.get("participant2_id")
        loser_id = participant1_id if winner_id == participant2_id else participant2_id
        group_id = match.get("group_id")
        
        if not winner_id or not loser_id:
            continue
        
        # Skoru parse et
        score = match.get("score", "0-0")
        try:
            parts = score.replace(" ", "").split("-")
            score1 = int(parts[0])
            score2 = int(parts[1])
        except:
            score1, score2 = 0, 0
        
        score_difference = abs(score1 - score2)
        is_forfeit = match.get("is_forfeit", False)
        forfeit_by = match.get("forfeit_by")
        
        # Puanları hesapla
        winner_points = 0
        loser_points = 0
        winner_breakdown = {}
        loser_breakdown = {}
        
        if is_forfeit:
            winner_points = match_result.get("forfeit_win", 2)
            loser_points = match_result.get("forfeit_loss", -2)
            winner_breakdown["match_result"] = winner_points
            loser_breakdown["match_result"] = loser_points
        else:
            winner_points = match_result.get("win", 2)
            loser_points = match_result.get("loss", 0)
            winner_breakdown["match_result"] = winner_points
            loser_breakdown["match_result"] = loser_points
            
            # Puan farkı bonusu
            if score_diff_config.get("enabled", True):
                close_threshold = score_diff_config.get("close_score_threshold", 2)
                close_bonus = score_diff_config.get("close_score_bonus", 10)
                dominant_threshold = score_diff_config.get("dominant_win_threshold", 5)
                dominant_bonus = score_diff_config.get("dominant_win_bonus", 5)
                
                if score_difference <= close_threshold:
                    loser_points += close_bonus
                    loser_breakdown["close_score_bonus"] = close_bonus
                
                if score_difference >= dominant_threshold:
                    winner_points += dominant_bonus
                    winner_breakdown["dominant_win_bonus"] = dominant_bonus
        
        # ==================== SET FARKI PUANLAMASI ====================
        set_diff_config = config.get("set_difference", {})
        if set_diff_config.get("enabled", False):
            points_per_set = set_diff_config.get("points_per_set", 1)
            set_diff_points = score_difference * points_per_set
            winner_points += set_diff_points
            winner_breakdown["set_difference_bonus"] = set_diff_points
            loser_points -= set_diff_points
            loser_breakdown["set_difference_penalty"] = -set_diff_points
        
        # ==================== RAKİP GÜCÜ - KADEME TABLOSU ====================
        opponent_strength_config = config.get("opponent_strength", {})
        if opponent_strength_config.get("enabled", False):
            # Oyuncuların SPORCU PUANLARINI al (event_athlete_points tablosundan)
            winner_athlete = await db.event_athlete_points.find_one({
                "event_id": event_id, "participant_id": winner_id
            })
            loser_athlete = await db.event_athlete_points.find_one({
                "event_id": event_id, "participant_id": loser_id
            })
            
            # Sporcu puanlarını al (yoksa 0)
            winner_rank_points = winner_athlete.get("points", 0) if winner_athlete else 0
            loser_rank_points = loser_athlete.get("points", 0) if loser_athlete else 0
            point_diff = abs(winner_rank_points - loser_rank_points)
            
            logger.info(f"📊 Opponent Strength (recalc): Winner points={winner_rank_points}, Loser points={loser_rank_points}, diff={point_diff}")
            
            if opponent_strength_config.get("use_tier_table", False):
                # Kademe tablosu kullan
                tiers = opponent_strength_config.get("tiers", [])
                for tier in tiers:
                    min_diff = tier.get("min_diff", 0)
                    max_diff = tier.get("max_diff", 999)
                    if min_diff <= point_diff <= max_diff:
                        if loser_rank_points > winner_rank_points:
                            # Düşük puanlı (zayıf) kazandı - sürpriz!
                            lower_wins_bonus = tier.get("lower_wins", 0)
                            higher_loses_penalty = tier.get("higher_loses", 0)
                            
                            if lower_wins_bonus != 0:
                                winner_points += lower_wins_bonus
                                winner_breakdown["tier_lower_wins"] = lower_wins_bonus
                            
                            # Ceza negatif olarak uygulanacak
                            if higher_loses_penalty != 0:
                                # Kullanıcı pozitif girdi ise negatife çevir
                                penalty = -abs(higher_loses_penalty)
                                loser_points += penalty
                                loser_breakdown["tier_higher_loses"] = penalty
                        else:
                            # Yüksek puanlı (güçlü) kazandı - beklenen
                            higher_wins_bonus = tier.get("higher_wins", 0)
                            lower_loses_penalty = tier.get("lower_loses", 0)
                            
                            if higher_wins_bonus != 0:
                                winner_points += higher_wins_bonus
                                winner_breakdown["tier_higher_wins"] = higher_wins_bonus
                            
                            # Ceza negatif olarak uygulanacak
                            if lower_loses_penalty != 0:
                                penalty = -abs(lower_loses_penalty)
                                loser_points += penalty
                                loser_breakdown["tier_lower_loses"] = penalty
                        break
            else:
                # Basit bonus/ceza sistemi
                if loser_rank_points > winner_rank_points:
                    if point_diff >= 10:
                        bonus = opponent_strength_config.get("beat_much_higher_bonus", 25)
                    else:
                        bonus = opponent_strength_config.get("beat_higher_ranked_bonus", 15)
                    winner_points += bonus
                    winner_breakdown["opponent_strength_bonus"] = bonus
                
                if winner_rank_points > loser_rank_points and point_diff >= 5:
                    penalty = opponent_strength_config.get("lose_to_lower_penalty", -5)
                    loser_points += penalty
                    loser_breakdown["lose_to_weaker_penalty"] = penalty
        
        # ==================== FAZ 2: ADİL OYUN PUANLARI ====================
        fair_play_config = config.get("fair_play", {})
        if fair_play_config.get("enabled", False):
            winner_warnings = match.get("warnings", {}).get(winner_id, 0)
            loser_warnings = match.get("warnings", {}).get(loser_id, 0)
            winner_yellow = match.get("yellow_cards", {}).get(winner_id, 0)
            loser_yellow = match.get("yellow_cards", {}).get(loser_id, 0)
            winner_red = match.get("red_cards", {}).get(winner_id, 0)
            loser_red = match.get("red_cards", {}).get(loser_id, 0)
            
            if winner_warnings == 0 and winner_yellow == 0 and winner_red == 0:
                bonus = fair_play_config.get("no_warnings_bonus", 5)
                winner_points += bonus
                winner_breakdown["fair_play_bonus"] = bonus
            if winner_yellow > 0:
                penalty = fair_play_config.get("yellow_card_penalty", -5) * winner_yellow
                winner_points += penalty
                winner_breakdown["yellow_card_penalty"] = penalty
            if winner_red > 0:
                penalty = fair_play_config.get("red_card_penalty", -15) * winner_red
                winner_points += penalty
                winner_breakdown["red_card_penalty"] = penalty
            
            if loser_warnings == 0 and loser_yellow == 0 and loser_red == 0:
                bonus = fair_play_config.get("no_warnings_bonus", 5)
                loser_points += bonus
                loser_breakdown["fair_play_bonus"] = bonus
            if loser_yellow > 0:
                penalty = fair_play_config.get("yellow_card_penalty", -5) * loser_yellow
                loser_points += penalty
                loser_breakdown["yellow_card_penalty"] = penalty
            if loser_red > 0:
                penalty = fair_play_config.get("red_card_penalty", -15) * loser_red
                loser_points += penalty
                loser_breakdown["red_card_penalty"] = penalty
        
        # ==================== FAZ 2: KATILIM BONUSU ====================
        participation_config = config.get("participation", {})
        if participation_config.get("enabled", False):
            attendance_bonus = participation_config.get("attendance_bonus", 5)
            winner_points += attendance_bonus
            winner_breakdown["attendance_bonus"] = attendance_bonus
            loser_points += attendance_bonus
            loser_breakdown["attendance_bonus"] = attendance_bonus
        
        # Atılan/Yenilen skorları hesapla
        winner_scored = score1 if participant1_id == winner_id else score2
        winner_conceded = score2 if participant1_id == winner_id else score1
        loser_scored = score2 if participant1_id == winner_id else score1
        loser_conceded = score1 if participant1_id == winner_id else score2
        
        # Standings güncelle - Kazanan
        await db.event_standings.update_one(
            {"event_id": event_id, "group_id": group_id, "participant_id": winner_id},
            {
                "$inc": {
                    "wins": 1,
                    "points": winner_points,
                    "custom_points": winner_points,
                    "matches_played": 1,
                    "scored": winner_scored,
                    "conceded": winner_conceded
                },
                "$set": {"last_match_breakdown": winner_breakdown},
                "$setOnInsert": {"losses": 0, "draws": 0}
            },
            upsert=True
        )
        
        # Standings güncelle - Kaybeden
        await db.event_standings.update_one(
            {"event_id": event_id, "group_id": group_id, "participant_id": loser_id},
            {
                "$inc": {
                    "losses": 1,
                    "points": loser_points,
                    "custom_points": loser_points,
                    "matches_played": 1,
                    "scored": loser_scored,
                    "conceded": loser_conceded
                },
                "$set": {"last_match_breakdown": loser_breakdown},
                "$setOnInsert": {"wins": 0, "draws": 0}
            },
            upsert=True
        )
        
        # Maça custom scoring bilgisi ekle
        await db.event_matches.update_one(
            {"id": match.get("id")},
            {"$set": {
                "custom_scoring_applied": True,
                "custom_points": {
                    "winner": {"points": winner_points, "breakdown": winner_breakdown},
                    "loser": {"points": loser_points, "breakdown": loser_breakdown}
                }
            }}
        )
        
        recalculated_count += 1
    
    logger.info(f"✅ Recalculated {recalculated_count} matches for event {event_id}")
    
    return {
        "status": "success",
        "message": f"{recalculated_count} maç yeniden hesaplandı",
        "recalculated_matches": recalculated_count
    }

# ================== MAZERET (EXCUSE) SİSTEMİ ==================

class ExcuseType(str):
    TOURNAMENT_MATCH = "tournament_match"  # Lig/Turnuva Maçlarım Var
    CANNOT_ATTEND = "cannot_attend"  # Gelemiyorum
    HEALTH_REPORT = "health_report"  # Sağlık Raporum Var

class ExcuseCreate(BaseModel):
    """Mazeret oluşturma modeli"""
    excuse_type: str  # tournament_match, cannot_attend, health_report
    description: Optional[str] = None
    file_url: Optional[str] = None  # Yüklenen dosya URL'i

class Excuse(BaseModel):
    """Mazeret modeli"""
    id: str
    event_id: str
    user_id: str
    user_name: Optional[str] = None
    excuse_type: str
    description: Optional[str] = None
    file_url: Optional[str] = None
    status: str = "pending"  # pending, approved, rejected
    penalty_applied: bool = False
    penalty_points: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    rejection_reason: Optional[str] = None

@custom_scoring_router.post("/{event_id}/excuses")
async def create_excuse(event_id: str, excuse_data: ExcuseCreate, request: Request):
    """Mazeret girişi oluştur"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    # Auth kontrolü
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Yetkisiz erişim")
    
    # Token'dan kullanıcıyı al
    user = await db.users.find_one({"session_token": token})
    if not user:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı")
    
    user_id = user.get("id")
    user_name = user.get("full_name", "Bilinmeyen")
    
    # Event kontrolü
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Mazeret ID oluştur
    excuse_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    # "Gelemiyorum" seçeneği için otomatik onay ve puan cezası
    auto_approved = excuse_data.excuse_type == "cannot_attend"
    penalty_applied = False
    penalty_points = 0
    
    if auto_approved:
        # Puan cezası al
        config = await db.custom_scoring_configs.find_one({"event_id": event_id})
        if config:
            absence_config = config.get("absence_penalty", {})
            if absence_config.get("enabled", False):
                penalty_points = absence_config.get("penalty_points", -10)
                penalty_applied = True
                
                # Kullanıcının standings'ine ceza uygula
                # Tüm gruplarda ara (kullanıcı birden fazla grupta olabilir)
                groups = await db.event_groups.find({"event_id": event_id}).to_list(100)
                for group in groups:
                    standing = await db.event_standings.find_one({
                        "event_id": event_id,
                        "group_id": group.get("id"),
                        "participant_id": user_id
                    })
                    if standing:
                        await db.event_standings.update_one(
                            {"event_id": event_id, "group_id": group.get("id"), "participant_id": user_id},
                            {
                                "$inc": {
                                    "points": penalty_points,
                                    "custom_points": penalty_points,
                                    "absence_penalty_total": penalty_points
                                },
                                "$set": {"updated_at": now}
                            }
                        )
                        logger.info(f"✅ Applied absence penalty {penalty_points} to user {user_id} in group {group.get('id')}")
    
    # Mazeret kaydını oluştur
    excuse = {
        "id": excuse_id,
        "event_id": event_id,
        "user_id": user_id,
        "user_name": user_name,
        "excuse_type": excuse_data.excuse_type,
        "description": excuse_data.description,
        "file_url": excuse_data.file_url,
        "status": "approved" if auto_approved else "pending",
        "penalty_applied": penalty_applied,
        "penalty_points": penalty_points,
        "created_at": now,
        "updated_at": now,
        "approved_by": "system" if auto_approved else None
    }
    
    await db.event_excuses.insert_one(excuse)
    
    # Organizatöre bildirim gönder
    organizer_id = event.get("organizer_id") or event.get("created_by")
    if organizer_id:
        excuse_type_labels = {
            "tournament_match": "Lig/Turnuva Maçlarım Var",
            "cannot_attend": "Gelemiyorum",
            "health_report": "Sağlık Raporum Var"
        }
        excuse_label = excuse_type_labels.get(excuse_data.excuse_type, excuse_data.excuse_type)
        
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": organizer_id,
            "type": "excuse_submitted",
            "title": "Yeni Mazeret Bildirimi",
            "message": f"{user_name} '{event.get('title', 'Etkinlik')}' etkinliği için '{excuse_label}' mazereti bildirdi." + 
                       (" (Otomatik onaylandı)" if auto_approved else ""),
            "data": {
                "event_id": event_id,
                "excuse_id": excuse_id,
                "user_id": user_id,
                "excuse_type": excuse_data.excuse_type,
                "auto_approved": auto_approved
            },
            "is_read": False,
            "created_at": now
        }
        await db.notifications.insert_one(notification)
        logger.info(f"📬 Excuse notification sent to organizer {organizer_id}")
    
    logger.info(f"✅ Excuse created: {excuse_id} by user {user_id} for event {event_id}")
    
    return {
        "status": "success",
        "excuse": excuse,
        "auto_approved": auto_approved,
        "penalty_applied": penalty_applied,
        "penalty_points": penalty_points
    }

@custom_scoring_router.get("/{event_id}/excuses")
async def get_excuses(event_id: str, request: Request):
    """Etkinliğin mazeretlerini listele"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    excuses = await db.event_excuses.find({"event_id": event_id}).sort("created_at", -1).to_list(500)
    
    # _id alanlarını temizle
    for excuse in excuses:
        if "_id" in excuse:
            del excuse["_id"]
    
    return {"excuses": excuses}

@custom_scoring_router.get("/{event_id}/excuses/my")
async def get_my_excuses(event_id: str, request: Request):
    """Kullanıcının kendi mazeretlerini listele"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    # Auth kontrolü
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Yetkisiz erişim")
    
    user = await db.users.find_one({"session_token": token})
    if not user:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı")
    
    user_id = user.get("id")
    
    excuses = await db.event_excuses.find({
        "event_id": event_id,
        "user_id": user_id
    }).sort("created_at", -1).to_list(100)
    
    for excuse in excuses:
        if "_id" in excuse:
            del excuse["_id"]
    
    return {"excuses": excuses}

@custom_scoring_router.put("/{event_id}/excuses/{excuse_id}/approve")
async def approve_excuse(event_id: str, excuse_id: str, request: Request):
    """Mazereti onayla (organizatör/yönetici için)"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    # Auth kontrolü
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Yetkisiz erişim")
    
    user = await db.users.find_one({"session_token": token})
    if not user:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı")
    
    # Event organizatör kontrolü
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    is_organizer = (
        user.get("id") == event.get("organizer_id") or 
        user.get("id") == event.get("created_by") or
        user.get("user_type") == "admin"
    )
    
    if not is_organizer:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Mazereti bul
    excuse = await db.event_excuses.find_one({"id": excuse_id, "event_id": event_id})
    if not excuse:
        raise HTTPException(status_code=404, detail="Mazeret bulunamadı")
    
    if excuse.get("status") == "approved":
        return {"status": "already_approved", "message": "Mazeret zaten onaylanmış"}
    
    now = datetime.utcnow()
    
    await db.event_excuses.update_one(
        {"id": excuse_id},
        {
            "$set": {
                "status": "approved",
                "approved_by": user.get("id"),
                "updated_at": now
            }
        }
    )
    
    # Kullanıcıya bildirim gönder
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": excuse.get("user_id"),
        "type": "excuse_approved",
        "title": "Mazeret Onaylandı",
        "message": f"'{event.get('title', 'Etkinlik')}' için mazeret talebiniz onaylandı.",
        "data": {"event_id": event_id, "excuse_id": excuse_id},
        "is_read": False,
        "created_at": now
    }
    await db.notifications.insert_one(notification)
    
    return {"status": "success", "message": "Mazeret onaylandı"}

@custom_scoring_router.put("/{event_id}/excuses/{excuse_id}/reject")
async def reject_excuse(event_id: str, excuse_id: str, request: Request):
    """Mazereti reddet (organizatör/yönetici için)"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    # Request body'den red gerekçesini al
    try:
        body = await request.json()
        rejection_reason = body.get("reason", "")
    except:
        rejection_reason = ""
    
    # Auth kontrolü
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Yetkisiz erişim")
    
    user = await db.users.find_one({"session_token": token})
    if not user:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı")
    
    # Event organizatör kontrolü
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    is_organizer = (
        user.get("id") == event.get("organizer_id") or 
        user.get("id") == event.get("created_by") or
        user.get("user_type") == "admin"
    )
    
    if not is_organizer:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    excuse = await db.event_excuses.find_one({"id": excuse_id, "event_id": event_id})
    if not excuse:
        raise HTTPException(status_code=404, detail="Mazeret bulunamadı")
    
    now = datetime.utcnow()
    
    await db.event_excuses.update_one(
        {"id": excuse_id},
        {
            "$set": {
                "status": "rejected",
                "rejection_reason": rejection_reason,
                "updated_at": now
            }
        }
    )
    
    # Kullanıcıya bildirim gönder
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": excuse.get("user_id"),
        "type": "excuse_rejected",
        "title": "Mazeret Reddedildi",
        "message": f"'{event.get('title', 'Etkinlik')}' için mazeret talebiniz reddedildi." + 
                   (f" Gerekçe: {rejection_reason}" if rejection_reason else ""),
        "data": {"event_id": event_id, "excuse_id": excuse_id},
        "is_read": False,
        "created_at": now
    }
    await db.notifications.insert_one(notification)
    
    return {"status": "success", "message": "Mazeret reddedildi"}

@custom_scoring_router.post("/{event_id}/apply-absence-penalty/{user_id}")
async def apply_manual_absence_penalty(event_id: str, user_id: str, request: Request):
    """Elle absence cezası uygula (yönetici için)"""
    global db
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database bağlantısı yok")
    
    # Auth kontrolü
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Yetkisiz erişim")
    
    admin_user = await db.users.find_one({"session_token": token})
    if not admin_user:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı")
    
    # Event organizatör kontrolü
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    is_organizer = (
        admin_user.get("id") == event.get("organizer_id") or 
        admin_user.get("id") == event.get("created_by") or
        admin_user.get("user_type") == "admin"
    )
    
    if not is_organizer:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Request body'den ceza puanını al
    try:
        body = await request.json()
        penalty_points = body.get("penalty_points")
    except:
        penalty_points = None
    
    # Eğer body'de yoksa config'den al
    if penalty_points is None:
        config = await db.custom_scoring_configs.find_one({"event_id": event_id})
        if config:
            absence_config = config.get("absence_penalty", {})
            penalty_points = absence_config.get("penalty_points", -10)
        else:
            penalty_points = -10
    
    # Negatif olmalı
    if penalty_points > 0:
        penalty_points = -penalty_points
    
    now = datetime.utcnow()
    
    # Kullanıcının tüm gruplarındaki standings'e ceza uygula
    groups = await db.event_groups.find({"event_id": event_id}).to_list(100)
    applied_count = 0
    
    for group in groups:
        standing = await db.event_standings.find_one({
            "event_id": event_id,
            "group_id": group.get("id"),
            "participant_id": user_id
        })
        if standing:
            await db.event_standings.update_one(
                {"event_id": event_id, "group_id": group.get("id"), "participant_id": user_id},
                {
                    "$inc": {
                        "points": penalty_points,
                        "custom_points": penalty_points,
                        "absence_penalty_total": penalty_points
                    },
                    "$set": {"updated_at": now}
                }
            )
            applied_count += 1
    
    # Log kaydı
    penalty_log = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "user_id": user_id,
        "penalty_type": "absence",
        "penalty_points": penalty_points,
        "applied_by": admin_user.get("id"),
        "created_at": now
    }
    await db.penalty_logs.insert_one(penalty_log)
    
    logger.info(f"✅ Manual absence penalty {penalty_points} applied to user {user_id} in {applied_count} groups")
    
    return {
        "status": "success",
        "message": f"Ceza uygulandı: {penalty_points} puan",
        "penalty_points": penalty_points,
        "groups_affected": applied_count
    }
