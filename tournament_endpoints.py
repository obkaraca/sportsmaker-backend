from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import os
import uuid
from dotenv import load_dotenv
from pathlib import Path
from pydantic import BaseModel
from models import (
    TournamentConfig,
    TournamentSystemType,
    ScoringSystemConfig,
    MatchBase,
    MatchStatus
)
from auth import get_current_user
from fixture_generator import FixtureGenerator

# MongoDB connection
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

router = APIRouter()

# Define corrected models for tournament creation
class TournamentCreateRequest(BaseModel):
    event_id: str
    config: TournamentConfig

# Turnuva oluşturma
@router.post("/tournaments", response_model=dict)
async def create_tournament(
    tournament_data: TournamentCreateRequest,
    current_user_id: str = Depends(get_current_user)
):
    """
    Etkinlik için turnuva yönetim paneli oluşturur
    """
    # Etkinliğin var olup olmadığını kontrol et
    event = await db.events.find_one({"id": tournament_data.event_id})
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Etkinlik bulunamadı"
        )
    
    # Kullanıcının bu etkinliğin organizatörü olup olmadığını kontrol et
    if event.get("organizer_id") != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu etkinlik için turnuva oluşturamazsınız"
        )
    
    # Aynı etkinlik için zaten turnuva var mı kontrol et
    existing_tournament = await db.tournament_management.find_one({
        "event_id": tournament_data.event_id
    })
    if existing_tournament:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu etkinlik için zaten bir turnuva yönetimi mevcut"
        )
    
    # Yeni turnuva oluştur
    tournament_id = str(uuid.uuid4())
    tournament = {
        "id": tournament_id,
        "event_id": tournament_data.event_id,
        "organizer_id": current_user_id,
        "config": tournament_data.config.model_dump(),
        "status": "draft",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.tournament_management.insert_one(tournament)
    
    return {
        "message": "Turnuva yönetimi başarıyla oluşturuldu",
        "tournament_id": tournament_id
    }


# Kullanıcının turnuvalarını listele
@router.get("/tournaments/my", response_model=List[dict])
async def get_my_tournaments(
    current_user_id: str = Depends(get_current_user)
):
    """
    Kullanıcının organizatörü olduğu turnaları listeler
    """
    tournaments = await db.tournament_management.find({
        "organizer_id": current_user_id
    }).to_list(1000)
    
    result = []
    for tournament in tournaments:
        # Etkinlik bilgilerini ekle
        event = await db.events.find_one({"id": tournament["event_id"]})
        
        tournament_data = {
            "id": tournament.get("id", str(tournament.get("_id", ""))),
            "event_id": tournament["event_id"],
            "event_title": event.get("title", "") if event else "",
            "event_sport": event.get("sport", "") if event else "",
            "config": tournament["config"],
            "status": tournament["status"],
            "created_at": tournament["created_at"].isoformat(),
            "updated_at": tournament["updated_at"].isoformat()
        }
        result.append(tournament_data)
    
    return result


# Belirli bir turnuvayı getir
@router.get("/tournaments/{tournament_id}", response_model=dict)
async def get_tournament(
    tournament_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """
    Belirli bir turnuva yönetiminin detaylarını getirir
    """
    tournament = await db.tournament_management.find_one({
        "id": tournament_id
    })
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turnuva bulunamadı"
        )
    
    # Sadece organizatör görebilir
    if tournament["organizer_id"] != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu turnuvayı görüntüleme yetkiniz yok"
        )
    
    # Etkinlik bilgilerini ekle
    event = await db.events.find_one({"id": tournament["event_id"]})
    
    # Katılımcı bilgilerini ekle (participations collection kullan)
    participants = await db.participations.find({
        "event_id": tournament["event_id"]
    }).to_list(1000)
    
    participant_list = []
    for p in participants:
        user = await db.users.find_one({"id": p["user_id"]})
        if user:
            participant_list.append({
                "id": p["user_id"],
                "full_name": user.get("full_name", ""),
                "email": user.get("email", "")
            })
    
    return {
        "id": tournament.get("id", str(tournament.get("_id", ""))),
        "event_id": tournament["event_id"],
        "event_title": event.get("title", "") if event else "",
        "event_sport": event.get("sport", "") if event else "",
        "config": tournament["config"],
        "status": tournament["status"],
        "participants": participant_list,
        "created_at": tournament["created_at"].isoformat(),
        "updated_at": tournament["updated_at"].isoformat()
    }


# Turnuva konfigürasyonunu güncelle
@router.put("/tournaments/{tournament_id}", response_model=dict)
async def update_tournament(
    tournament_id: str,
    config: TournamentConfig,
    current_user_id: str = Depends(get_current_user)
):
    """
    Turnuva konfigürasyonunu günceller
    """
    tournament = await db.tournament_management.find_one({
        "id": tournament_id
    })
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turnuva bulunamadı"
        )
    
    # Sadece organizatör güncelleyebilir
    if tournament["organizer_id"] != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu turnuvayı güncelleme yetkiniz yok"
        )
    
    # Güncelle
    await db.tournament_management.update_one(
        {"id": tournament_id},
        {
            "$set": {
                "config": config.model_dump(),
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    return {"message": "Turnuva konfigürasyonu güncellendi"}


# Status update request model
class StatusUpdateRequest(BaseModel):
    status: str

# Turnuva durumunu güncelle (draft -> active -> completed)
@router.put("/tournaments/{tournament_id}/status", response_model=dict)
async def update_tournament_status(
    tournament_id: str,
    status_data: StatusUpdateRequest,
    current_user_id: str = Depends(get_current_user)
):
    """
    Turnuva durumunu günceller (draft, active, completed)
    """
    tournament_status = status_data.status
    if tournament_status not in ["draft", "active", "completed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz durum. Geçerli değerler: draft, active, completed"
        )
    
    tournament = await db.tournament_management.find_one({
        "id": tournament_id
    })
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turnuva bulunamadı"
        )
    
    # Sadece organizatör güncelleyebilir
    if tournament["organizer_id"] != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu turnuvayı güncelleme yetkiniz yok"
        )
    
    # Güncelle
    await db.tournament_management.update_one(
        {"id": tournament_id},
        {
            "$set": {
                "status": tournament_status,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    return {
        "message": f"Turnuva durumu '{tournament_status}' olarak güncellendi",
        "status": tournament_status
    }


# Turnuvayı sil
@router.delete("/tournaments/{tournament_id}", response_model=dict)
async def delete_tournament(
    tournament_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """
    Turnuva yönetimini siler
    """
    tournament = await db.tournament_management.find_one({
        "id": tournament_id
    })
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turnuva bulunamadı"
        )
    
    # Sadece organizatör silebilir
    if tournament["organizer_id"] != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu turnuvayı silme yetkiniz yok"
        )
    
    # Sil
    await db.tournament_management.delete_one({"id": tournament_id})
    
    return {"message": "Turnuva yönetimi başarıyla silindi"}


# Fikstür oluşturma
@router.post("/tournaments/{tournament_id}/generate-fixture", response_model=dict)
async def generate_tournament_fixture(
    tournament_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """
    Turnuva için fikstür oluşturur (maçları generate eder)
    """
    tournament = await db.tournament_management.find_one({
        "id": tournament_id
    })
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turnuva bulunamadı"
        )
    
    # Sadece organizatör fikstür oluşturabilir
    if tournament["organizer_id"] != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu turnuva için fikstür oluşturamazsınız"
        )
    
    # Katılımcıları al
    participants = await db.participations.find({
        "event_id": tournament["event_id"]
    }).to_list(1000)
    
    if len(participants) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fikstür oluşturmak için en az 2 katılımcı gerekli"
        )
    
    participant_ids = [p["user_id"] for p in participants]
    config = tournament["config"]
    system_type = config["system_type"]
    
    # Sistem tipine göre fikstür oluştur
    matches = []
    if system_type == "knockout":
        matches = FixtureGenerator.generate_single_elimination(participant_ids)
    elif system_type == "double_elimination":
        matches = FixtureGenerator.generate_double_elimination(participant_ids)
    elif system_type == "single_round_robin":
        matches = FixtureGenerator.generate_round_robin(participant_ids, double_round=False)
    elif system_type == "double_round_robin":
        matches = FixtureGenerator.generate_round_robin(participant_ids, double_round=True)
    elif system_type == "swiss":
        num_rounds = 5  # Default
        matches = FixtureGenerator.generate_swiss_system(participant_ids, num_rounds)
    elif system_type == "group_knockout":
        group_size = config.get("group_size", 4)
        matches = FixtureGenerator.generate_group_stage(participant_ids, group_size)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Desteklenmeyen turnuva sistemi: {system_type}"
        )
    
    # Mevcut maçları sil
    await db.matches.delete_many({"tournament_id": tournament_id})
    
    # Yeni maçları veritabanına kaydet
    match_documents = []
    for match in matches:
        match_doc = {
            "id": str(uuid.uuid4()),
            "tournament_id": tournament_id,
            "round": match["round"],
            "match_number": match["match_number"],
            "participant1_id": match.get("participant1_id"),
            "participant2_id": match.get("participant2_id"),
            "bracket_position": match.get("bracket_position"),
            "group_name": match.get("group_name"),
            "status": "scheduled",
            "scheduled_date": None,
            "scheduled_time": None,
            "field_number": None,
            "referee_id": None,
            "score1": None,
            "score2": None,
            "winner_id": None,
            "notes": None,
            "created_at": datetime.utcnow()
        }
        match_documents.append(match_doc)
    
    if match_documents:
        await db.matches.insert_many(match_documents)
    
    return {
        "message": "Fikstür başarıyla oluşturuldu",
        "matches_count": len(match_documents)
    }


# Turnuva maçlarını listele
@router.get("/tournaments/{tournament_id}/matches", response_model=List[dict])
async def get_tournament_matches(
    tournament_id: str,
    round: Optional[int] = None,
    current_user_id: str = Depends(get_current_user)
):
    """
    Turnuvaya ait maçları listeler
    """
    tournament = await db.tournament_management.find_one({
        "id": tournament_id
    })
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turnuva bulunamadı"
        )
    
    # Query oluştur
    query = {"tournament_id": tournament_id}
    if round is not None:
        query["round"] = round
    
    # Maçları al
    matches = await db.matches.find(query).sort("round", 1).sort("match_number", 1).to_list(1000)
    
    # Katılımcı bilgilerini ekle
    result = []
    for match in matches:
        match_data = {
            "id": match["id"],
            "round": match["round"],
            "match_number": match["match_number"],
            "participant1_id": match.get("participant1_id"),
            "participant2_id": match.get("participant2_id"),
            "participant1_name": None,
            "participant2_name": None,
            "scheduled_date": match.get("scheduled_date"),
            "scheduled_time": match.get("scheduled_time"),
            "field_number": match.get("field_number"),
            "status": match.get("status", "scheduled"),
            "score1": match.get("score1"),
            "score2": match.get("score2"),
            "winner_id": match.get("winner_id"),
            "bracket_position": match.get("bracket_position"),
            "group_name": match.get("group_name")
        }
        
        # Katılımcı isimlerini al
        if match.get("participant1_id"):
            user1 = await db.users.find_one({"id": match["participant1_id"]})
            if user1:
                match_data["participant1_name"] = user1.get("full_name", "")
        
        if match.get("participant2_id"):
            user2 = await db.users.find_one({"id": match["participant2_id"]})
            if user2:
                match_data["participant2_name"] = user2.get("full_name", "")
        
        result.append(match_data)
    
    return result


# Maç skorunu güncelleme için model
class MatchScoreUpdate(BaseModel):
    score1: int
    score2: int
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    field_number: Optional[int] = None


# Maç skorunu güncelle
@router.put("/matches/{match_id}", response_model=dict)
async def update_match_score(
    match_id: str,
    score_data: MatchScoreUpdate,
    current_user_id: str = Depends(get_current_user)
):
    """
    Maç skorunu günceller
    """
    match = await db.matches.find_one({"id": match_id})
    
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maç bulunamadı"
        )
    
    # Turnuvayı kontrol et
    tournament = await db.tournament_management.find_one({
        "id": match["tournament_id"]
    })
    
    if not tournament or tournament["organizer_id"] != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu maçı güncelleme yetkiniz yok"
        )
    
    # Kazananı belirle
    winner_id = None
    if score_data.score1 > score_data.score2:
        winner_id = match.get("participant1_id")
    elif score_data.score2 > score_data.score1:
        winner_id = match.get("participant2_id")
    
    # Güncelle
    update_data = {
        "score1": score_data.score1,
        "score2": score_data.score2,
        "winner_id": winner_id,
        "status": "completed"
    }
    
    if score_data.scheduled_date:
        update_data["scheduled_date"] = score_data.scheduled_date
    if score_data.scheduled_time:
        update_data["scheduled_time"] = score_data.scheduled_time
    if score_data.field_number:
        update_data["field_number"] = score_data.field_number
    
    await db.matches.update_one(
        {"id": match_id},
        {"$set": update_data}
    )
    
    return {
        "message": "Maç skoru güncellendi",
        "winner_id": winner_id
    }


# Puan tablosunu getir
@router.get("/tournaments/{tournament_id}/standings", response_model=List[dict])
async def get_tournament_standings(
    tournament_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """
    Turnuva puan tablosunu döndürür (lig sistemleri için)
    """
    tournament = await db.tournament_management.find_one({
        "id": tournament_id
    })
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turnuva bulunamadı"
        )
    
    # Tamamlanan maçları al
    matches = await db.matches.find({
        "tournament_id": tournament_id,
        "status": "completed",
        "winner_id": {"$ne": None}
    }).to_list(1000)
    
    # Puan hesaplama
    config = tournament["config"]
    scoring = config.get("scoring_config", {
        "win_points": 3,
        "draw_points": 1,
        "loss_points": 0
    })
    
    standings = {}
    
    for match in matches:
        p1_id = match.get("participant1_id")
        p2_id = match.get("participant2_id")
        
        if not p1_id or not p2_id:
            continue
        
        # Standings'i initialize et
        if p1_id not in standings:
            standings[p1_id] = {
                "participant_id": p1_id,
                "played": 0,
                "won": 0,
                "drawn": 0,
                "lost": 0,
                "goals_for": 0,
                "goals_against": 0,
                "goal_difference": 0,
                "points": 0
            }
        
        if p2_id not in standings:
            standings[p2_id] = {
                "participant_id": p2_id,
                "played": 0,
                "won": 0,
                "drawn": 0,
                "lost": 0,
                "goals_for": 0,
                "goals_against": 0,
                "goal_difference": 0,
                "points": 0
            }
        
        score1 = match.get("score1", 0)
        score2 = match.get("score2", 0)
        
        standings[p1_id]["played"] += 1
        standings[p2_id]["played"] += 1
        
        standings[p1_id]["goals_for"] += score1
        standings[p1_id]["goals_against"] += score2
        
        standings[p2_id]["goals_for"] += score2
        standings[p2_id]["goals_against"] += score1
        
        if score1 > score2:
            standings[p1_id]["won"] += 1
            standings[p1_id]["points"] += scoring["win_points"]
            standings[p2_id]["lost"] += 1
            standings[p2_id]["points"] += scoring["loss_points"]
        elif score2 > score1:
            standings[p2_id]["won"] += 1
            standings[p2_id]["points"] += scoring["win_points"]
            standings[p1_id]["lost"] += 1
            standings[p1_id]["points"] += scoring["loss_points"]
        else:
            standings[p1_id]["drawn"] += 1
            standings[p2_id]["drawn"] += 1
            standings[p1_id]["points"] += scoring["draw_points"]
            standings[p2_id]["points"] += scoring["draw_points"]
        
        standings[p1_id]["goal_difference"] = standings[p1_id]["goals_for"] - standings[p1_id]["goals_against"]
        standings[p2_id]["goal_difference"] = standings[p2_id]["goals_for"] - standings[p2_id]["goals_against"]
    
    # Sıralama: Puan > Averaj > Gol sayısı
    sorted_standings = sorted(
        standings.values(),
        key=lambda x: (x["points"], x["goal_difference"], x["goals_for"]),
        reverse=True
    )
    
    # Katılımcı isimlerini ekle
    result = []
    for idx, standing in enumerate(sorted_standings, 1):
        user = await db.users.find_one({"id": standing["participant_id"]})
        standing["rank"] = idx
        standing["participant_name"] = user.get("full_name", "") if user else ""
        result.append(standing)
    
    return result
