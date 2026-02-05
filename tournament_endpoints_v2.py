"""
Advanced Tournament Management Endpoints
Complete tournament system with draw, scheduling, scoring, and standings
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

from models import (
    SportConfig, VenueField, Referee, RefereeCreate,
    ParticipantRemovalRequest, ParticipantRemovalRequestCreate, ParticipantRemovalRequestUpdate,
    TournamentParticipant, DrawConfig, BracketNode, Standing,
    MatchDetail, MatchScoreUpdate, ScoreProposal, ScoreConfirmation, ScheduleSlot, TournamentSchedule,
    ExtendedTournamentConfig, TournamentFull, MatchStatus
)
from auth import get_current_user, get_current_active_user
from tournament_service import TournamentService
from score_management import ScoreManagementService

router = APIRouter(tags=["Advanced Tournaments"])

async def get_db() -> AsyncIOMotorDatabase:
    from server import db
    return db

# ==================== TOURNAMENT CRUD ====================

@router.post("/{event_id}/create")
async def create_advanced_tournament(
    event_id: str,
    config: ExtendedTournamentConfig,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Create advanced tournament with full configuration"""
    
    # Verify event exists and user is organizer
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    tournament_id = str(uuid.uuid4())
    
    # Get participants from event
    participant_ids = event.get("participants", [])
    participants = []
    
    for user_id in participant_ids:
        user = await db.users.find_one({"id": user_id})
        if user:
            participant = {
                "id": str(uuid.uuid4()),
                "tournament_id": tournament_id,
                "user_id": user_id,
                "full_name": user.get("full_name"),
                "email": user.get("email"),
                "phone_number": user.get("phone_number"),
                "age": user.get("age"),
                "gender": user.get("gender"),
                "skill_level": user.get("skill_level"),  # Get from user profile
                "seed": None,  # Will be auto-assigned
                "group_name": None,  # Will be auto-assigned
                "is_bye": False,  # Will be auto-assigned
                "registration_date": datetime.utcnow(),
                "payment_status": "paid",
                "notes": None
            }
            participants.append(participant)
    
    # AUTO-ASSIGN seeding based on skill levels
    from tournament_service import TournamentService
    participants = TournamentService.auto_assign_seeding(participants, event)
    
    # AUTO-CREATE groups based on age/gender
    groups = TournamentService.auto_create_groups(participants, event)
    
    # AUTO-IDENTIFY bye participants for knockout systems
    if config.system_type in ['knockout', 'single_elimination', 'double_elimination']:
        bye_user_ids = TournamentService.identify_bye_participants(participants)
        config.bye_participants = bye_user_ids
    
    tournament = {
        "id": tournament_id,
        "event_id": event_id,
        "event_name": event.get("title"),
        "organizer_id": current_user_id,
        "config": config.dict(),
        "status": "draft",
        "visibility": "public",
        "participants": participants,
        "matches": [],
        "standings": [],
        "bracket": [],
        "referees": [],
        "schedule": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "draw_date": None,
        "start_date": None,
        "end_date": None
    }
    
    await db.tournaments_v2.insert_one(tournament)
    
    # Remove MongoDB _id field for JSON serialization
    tournament.pop("_id", None)
    
    return {"id": tournament_id, "message": "Tournament created", "tournament": tournament}

@router.get("")
async def get_tournaments(
    event_id: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get tournaments, optionally filtered by event_id"""
    
    query = {}
    if event_id:
        query["event_id"] = event_id
    
    tournaments = await db.tournaments_v2.find(query).to_list(100)
    
    # Remove MongoDB _id fields
    for tournament in tournaments:
        tournament.pop("_id", None)
    
    return tournaments

@router.get("/{tournament_id}")
async def get_tournament_details(
    tournament_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get full tournament details with all data"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    # Get event details to include sport and match format info
    event_id = tournament.get("event_id")
    if event_id:
        event = await db.events.find_one({"id": event_id})
        if event:
            # Add sport and match format info from event
            tournament["event_sport"] = event.get("sport")
            tournament["event_best_of_sets"] = event.get("best_of_sets")
            tournament["event_points_per_set"] = event.get("points_per_set")
            tournament["event_sets_to_win"] = event.get("sets_to_win")
    
    # Remove MongoDB _id field for JSON serialization
    tournament.pop("_id", None)
    return tournament

@router.put("/{tournament_id}/config")
async def update_tournament_config(
    tournament_id: str,
    config: ExtendedTournamentConfig,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Update tournament configuration"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if tournament.get("status") not in ["draft", "registration_open"]:
        raise HTTPException(status_code=400, detail="Cannot modify after draw")
    
    await db.tournaments_v2.update_one(
        {"id": tournament_id},
        {"$set": {"config": config.dict(), "updated_at": datetime.utcnow()}}
    )
    
    return {"message": "Configuration updated"}

@router.put("/{tournament_id}/visibility")
async def update_tournament_visibility(
    tournament_id: str,
    visibility: str,  # "public", "private", "hidden"
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Update tournament visibility (admin/organizer only)"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    # Check if user is organizer
    user = await db.users.find_one({"id": current_user_id})
    is_admin = user and user.get("user_type") in ["admin", "super_admin"]
    is_organizer = tournament.get("organizer_id") == current_user_id
    
    if not (is_admin or is_organizer):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.tournaments_v2.update_one(
        {"id": tournament_id},
        {"$set": {"visibility": visibility, "updated_at": datetime.utcnow()}}
    )
    
    return {"message": "Visibility updated"}

# ==================== PARTICIPANT MANAGEMENT ====================

@router.get("/{tournament_id}/participants")
async def get_tournament_participants(
    tournament_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get all tournament participants with details"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    # Get event participants
    event_id = tournament.get("event_id")
    event = await db.events.find_one({"id": event_id})
    
    if not event:
        return []
    
    participant_ids = event.get("participants", [])
    
    # Enrich with user details
    participants = []
    for user_id in participant_ids:
        user = await db.users.find_one({"id": user_id})
        if user:
            # Check if participant already exists in tournament with seed/group info
            tournament_participant = None
            if tournament.get("participants"):
                tournament_participant = next(
                    (p for p in tournament["participants"] if p.get("user_id") == user_id), 
                    None
                )
            
            participant = {
                "id": tournament_participant.get("id") if tournament_participant else str(uuid.uuid4()),
                "tournament_id": tournament_id,
                "user_id": user_id,
                "full_name": user.get("full_name"),
                "email": user.get("email"),
                "phone_number": user.get("phone_number"),
                "age": user.get("age"),
                "gender": user.get("gender"),
                "skill_level": tournament_participant.get("skill_level") if tournament_participant else user.get("skill_level"),
                "seed": tournament_participant.get("seed") if tournament_participant else None,
                "group_name": tournament_participant.get("group_name") if tournament_participant else None,
                "is_bye": tournament_participant.get("is_bye", False) if tournament_participant else False,
                "registration_date": tournament_participant.get("registration_date") if tournament_participant else datetime.utcnow(),
                "payment_status": tournament_participant.get("payment_status", "paid") if tournament_participant else "paid",
                "notes": tournament_participant.get("notes") if tournament_participant else None
            }
            participants.append(participant)
    
    return participants

@router.post("/{tournament_id}/participants/{user_id}/seed")
async def set_participant_seed(
    tournament_id: str,
    user_id: str,
    seed_data: dict,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Set seeding for a participant"""
    
    seed = seed_data.get("seed")
    if seed is None:
        raise HTTPException(status_code=400, detail="Seed value required")
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Update participant seed in tournament data
    participants = tournament.get("participants", [])
    for p in participants:
        if p.get("user_id") == user_id:
            p["seed"] = seed
            break
    
    await db.tournaments_v2.update_one(
        {"id": tournament_id},
        {"$set": {"participants": participants, "updated_at": datetime.utcnow()}}
    )
    
    return {"message": "Seed updated"}

@router.put("/{tournament_id}/participants/{user_id}")
async def update_participant_info(
    tournament_id: str,
    user_id: str,
    update_data: dict,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Update participant age_group and skill_level"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # First, update in users collection directly
    user_update = {}
    if "age_group" in update_data:
        user_update["age_group"] = update_data["age_group"]
    if "skill_level" in update_data:
        user_update["skill_level"] = update_data["skill_level"]
    
    if user_update:
        result = await db.users.update_one(
            {"id": user_id},
            {"$set": user_update}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
    
    # Also update in tournament participants if exists
    participants = tournament.get("participants", [])
    updated_in_tournament = False
    
    for p in participants:
        if p.get("user_id") == user_id:
            if "age_group" in update_data:
                p["age_group"] = update_data["age_group"]
            if "skill_level" in update_data:
                p["skill_level"] = update_data["skill_level"]
            updated_in_tournament = True
            break
    
    if updated_in_tournament:
        await db.tournaments_v2.update_one(
            {"id": tournament_id},
            {"$set": {"participants": participants, "updated_at": datetime.utcnow()}}
        )
    
    return {"message": "Participant updated"}

# ==================== REMOVAL REQUESTS ====================

@router.post("/{tournament_id}/participants/{user_id}/removal-request")
async def create_removal_request(
    tournament_id: str,
    user_id: str,
    request_data: ParticipantRemovalRequestCreate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Organizer requests to remove a participant (needs admin approval)"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    request_id = str(uuid.uuid4())
    removal_request = {
        "id": request_id,
        "event_id": request_data.event_id,
        "tournament_id": tournament_id,
        "participant_id": user_id,
        "requested_by": current_user_id,
        "reason": request_data.reason,
        "status": "pending",
        "admin_notes": None,
        "created_at": datetime.utcnow(),
        "reviewed_at": None,
        "reviewed_by": None
    }
    
    await db.removal_requests.insert_one(removal_request)
    
    # Create notification for admins
    admins = await db.users.find({"user_type": {"$in": ["admin", "super_admin"]}}).to_list(100)
    for admin in admins:
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": admin.get("id"),
            "type": "removal_request",
            "title": "Katılımcı Çıkarma Talebi",
            "message": f"Turnuva organizatörü bir katılımcıyı çıkarmak istiyor. Sebep: {request_data.reason}",
            "related_id": request_id,  # Request ID for handling
            "related_type": "removal_request",
            "data": {"request_id": request_id, "tournament_id": tournament_id},
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
    
    return {"message": "Removal request created", "request_id": request_id}

@router.get("/removal-requests")
async def get_removal_requests(
    status: Optional[str] = None,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get all removal requests (admin only)"""
    
    user = await db.users.find_one({"id": current_user_id})
    if not user or user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin only")
    
    query = {}
    if status:
        query["status"] = status
    
    requests = await db.removal_requests.find(query).to_list(1000)
    return requests

@router.put("/removal-requests/{request_id}")
async def update_removal_request(
    request_id: str,
    update_data: ParticipantRemovalRequestUpdate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Admin approves or rejects removal request"""
    
    user = await db.users.find_one({"id": current_user_id})
    if not user or user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin only")
    
    request = await db.removal_requests.find_one({"id": request_id})
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    await db.removal_requests.update_one(
        {"id": request_id},
        {
            "$set": {
                "status": update_data.status,
                "admin_notes": update_data.admin_notes,
                "reviewed_at": datetime.utcnow(),
                "reviewed_by": current_user_id
            }
        }
    )
    
    # If approved, remove participant from event
    if update_data.status == "approved":
        event_id = request.get("event_id")
        participant_id = request.get("participant_id")
        
        await db.events.update_one(
            {"id": event_id},
            {"$pull": {"participants": participant_id}}
        )
        
        # Notify organizer
        organizer_id = request.get("requested_by")
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": organizer_id,
            "type": "removal_approved",
            "title": "Çıkarma Talebi Onaylandı",
            "message": "Katılımcı çıkarma talebiniz onaylandı.",
            "data": {"request_id": request_id},
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
    
    # If rejected, notify organizer with admin user ID for messaging
    elif update_data.status == "rejected":
        organizer_id = request.get("requested_by")
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": organizer_id,
            "type": "removal_rejected",
            "title": "Çıkarma Talebi Reddedildi",
            "message": "Katılımcı çıkarma talebiniz reddedildi. Yönetici ile görüşmek için tıklayın.",
            "related_id": current_user_id,  # Admin user ID for chat
            "related_type": "user",
            "data": {"request_id": request_id},
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
    
    return {"message": "Request updated"}

# This file will be continued in next message with draw, scheduling, and scoring endpoints


# ==================== DRAW & SEEDING ====================

@router.post("/{tournament_id}/draw")
async def conduct_tournament_draw(
    tournament_id: str,
    draw_config: DrawConfig,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Conduct tournament draw and generate bracket/matches"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get participants - always load from event for fresh data
    participants = await get_tournament_participants(tournament_id, db)
    
    if len(participants) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 participants")
    
    config = tournament.get("config", {})
    system_type = config.get("system_type", "single_elimination")
    
    # Create participant map for names - use both id and user_id as keys
    participant_map = {}
    for p in participants:
        participant_map[p.get("id")] = p.get("full_name")
        participant_map[p.get("user_id")] = p.get("full_name")
    
    print(f"DEBUG Draw: Total participants: {len(participants)}")
    print(f"DEBUG Draw: Participant map size: {len(participant_map)}")
    if participants:
        print(f"DEBUG Draw: Sample participant keys: id={participants[0].get('id')}, user_id={participants[0].get('user_id')}")
    
    # Generate bracket/matches based on system type
    if system_type in ["single_elimination", "knockout"]:
        bracket = TournamentService.generate_single_elimination_bracket(participants, draw_config.method)
        # Convert bracket to matches
        matches = []
        for node in bracket:
            if node.get("participant1_id") and node.get("participant2_id"):
                match = {
                    "id": str(uuid.uuid4()),
                    "tournament_id": tournament_id,
                    "round": node.get("round", 1),
                    "match_number": node.get("match_number", 1),
                    "participant1_id": node.get("participant1_id"),
                    "participant2_id": node.get("participant2_id"),
                    "status": "pending",
                    "score_participant1": None,
                    "score_participant2": None,
                    "winner_id": None,
                    "scheduled_time": None,
                    "venue_field": None
                }
                matches.append(match)
        standings = []
    elif system_type == "double_elimination":
        bracket = TournamentService.generate_double_elimination_bracket(participants, draw_config.method)
        # Convert bracket to matches
        matches = []
        for node in bracket:
            if node.get("participant1_id") and node.get("participant2_id"):
                match = {
                    "id": str(uuid.uuid4()),
                    "tournament_id": tournament_id,
                    "round": node.get("round", 1),
                    "match_number": node.get("match_number", 1),
                    "bracket_type": node.get("bracket_type", "winners"),
                    "participant1_id": node.get("participant1_id"),
                    "participant2_id": node.get("participant2_id"),
                    "status": "pending",
                    "score_participant1": None,
                    "score_participant2": None,
                    "winner_id": None,
                    "scheduled_time": None,
                    "venue_field": None
                }
                matches.append(match)
        standings = []
    elif system_type in ["round_robin", "single_round_robin"]:
        bracket = []
        matches = TournamentService.generate_round_robin_schedule(participants, rounds=1)
        standings = TournamentService.calculate_standings([], participants, {"win": 3, "draw": 1, "loss": 0})
    elif system_type == "double_round_robin":
        bracket = []
        matches = TournamentService.generate_round_robin_schedule(participants, rounds=2)
        standings = TournamentService.calculate_standings([], participants, {"win": 3, "draw": 1, "loss": 0})
    elif system_type in ["group_stage", "group_knockout"]:
        num_groups = config.get("num_groups", 4)
        groups, matches = TournamentService.generate_group_stage_schedule(participants, num_groups)
        bracket = []
        standings = []
        # Generate standings for each group
        for group_name in groups.keys():
            group_standings = TournamentService.calculate_standings([], groups[group_name], {"win": 3, "draw": 1, "loss": 0})
            for s in group_standings:
                s["group_name"] = group_name
            standings.extend(group_standings)
    elif system_type == "swiss":
        # Swiss system needs round-by-round generation
        bracket = []
        matches = []
        standings = TournamentService.calculate_standings([], participants, {"win": 3, "draw": 1, "loss": 0})
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported system type: {system_type}")
    
    # Add participant names to ALL matches
    for match in matches:
        match["player1_id"] = match.get("participant1_id") or match.get("player1_id")
        match["player2_id"] = match.get("participant2_id") or match.get("player2_id")
        match["player1_name"] = participant_map.get(match["player1_id"], "TBA")
        match["player2_name"] = participant_map.get(match["player2_id"], "TBA")
        match["tournament_id"] = tournament_id
        match["status"] = match.get("status", "pending")
    
    # Update tournament
    await db.tournaments_v2.update_one(
        {"id": tournament_id},
        {
            "$set": {
                "participants": participants,
                "bracket": bracket,
                "matches": matches,
                "standings": standings,
                "status": "draw_completed",
                "draw_date": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    return {
        "message": "Draw completed",
        "bracket": bracket,
        "matches": matches,
        "standings": standings
    }

# ==================== REFEREE & SCHEDULING ====================

@router.post("/{tournament_id}/referees")
async def add_referee(
    tournament_id: str,
    referee_data: RefereeCreate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Add referee to tournament"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    user = await db.users.find_one({"id": referee_data.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    referee = {
        "id": str(uuid.uuid4()),
        "user_id": referee_data.user_id,
        "full_name": user.get("full_name"),
        "email": user.get("email"),
        "phone_number": user.get("phone_number"),
        "certification_level": referee_data.certification_level,
        "sports": referee_data.sports,
        "availability": referee_data.availability,
        "assigned_matches": [],
        "created_at": datetime.utcnow()
    }
    
    await db.tournaments_v2.update_one(
        {"id": tournament_id},
        {"$push": {"referees": referee}}
    )
    
    return {"message": "Referee added", "referee": referee}

@router.put("/{tournament_id}/matches/{match_id}/assign-referee")
async def assign_referee_to_match(
    tournament_id: str,
    match_id: str,
    referee_id: str,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Assign referee to match"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    matches = tournament.get("matches", [])
    for match in matches:
        if match.get("id") == match_id:
            match["referee_id"] = referee_id
            break
    
    referees = tournament.get("referees", [])
    for referee in referees:
        if referee.get("id") == referee_id:
            if match_id not in referee.get("assigned_matches", []):
                referee["assigned_matches"].append(match_id)
            break
    
    await db.tournaments_v2.update_one(
        {"id": tournament_id},
        {"$set": {"matches": matches, "referees": referees, "updated_at": datetime.utcnow()}}
    )
    
    return {"message": "Referee assigned"}

@router.put("/{tournament_id}/matches/{match_id}/score")
async def update_match_score(
    tournament_id: str,
    match_id: str,
    score_data: MatchScoreUpdate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Update match score - for admins, organizers, and referees"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    # Get event for additional checks
    event_id = tournament.get("event_id")
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Find the match
    matches = tournament.get("matches", [])
    match = next((m for m in matches if m.get("id") == match_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Use ScoreManagementService for authorization
    can_submit, reason = ScoreManagementService.can_submit_score(
        current_user_id, match, event, tournament
    )
    
    # Debug logging
    print("🔍 SCORE AUTHORIZATION DEBUG:")
    print(f"  - Current User ID: {current_user_id}")
    print(f"  - Event Organizer ID: {event.get('organizer_id')}")
    print(f"  - Tournament Organizer ID: {tournament.get('organizer_id')}")
    print(f"  - Match Referee ID: {match.get('referee_id')}")
    print(f"  - Match P1 ID: {match.get('participant1_id')} / {match.get('player1_id')}")
    print(f"  - Match P2 ID: {match.get('participant2_id')} / {match.get('player2_id')}")
    print(f"  - Can Submit: {can_submit}, Reason: {reason}")
    
    # For direct score update (PUT endpoint), only allow admins/organizers/referees
    # Players should use propose-score endpoint
    is_organizer = (event.get("organizer_id") == current_user_id or 
                    tournament.get("organizer_id") == current_user_id)
    is_referee = match.get("referee_id") == current_user_id
    
    print(f"  - Is Organizer: {is_organizer}")
    print(f"  - Is Referee: {is_referee}")
    print(f"  - Final Auth: {is_organizer or is_referee or can_submit}")
    
    if not (is_organizer or is_referee or can_submit):
        raise HTTPException(status_code=403, detail="Bu maça skor giremezsiniz. Lütfen skor öner özelliğini kullanın.")
    
    matches = tournament.get("matches", [])
    for match in matches:
        if match.get("id") == match_id:
            match["score_participant1"] = score_data.score_participant1
            match["score_participant2"] = score_data.score_participant2
            match["sets_scores"] = score_data.sets_scores
            match["winner_id"] = score_data.winner_id
            match["is_walkover"] = score_data.is_walkover
            match["notes"] = score_data.notes
            match["status"] = "completed"
            match["completed_at"] = datetime.utcnow()
            break
    
    bracket = tournament.get("bracket", [])
    if bracket:
        bracket = TournamentService.update_bracket_after_match(bracket, match_id, score_data.winner_id)
    
    standings = tournament.get("standings", [])
    participants = tournament.get("participants", [])
    config = tournament.get("config", {})
    
    # Get scoring system from event, not from tournament config
    event_id = tournament.get("event_id")
    event = await db.events.find_one({"id": event_id})
    
    if event and event.get("scoring_config"):
        scoring_system = event.get("scoring_config")
        print(f"🔵 Using scoring config from event: {scoring_system}")
    else:
        # Fallback to default
        scoring_system = {"win": 3, "draw": 1, "loss": 0}
        print(f"🟡 Using default scoring config: {scoring_system}")
    
    # Always recalculate standings after score update
    standings = TournamentService.calculate_standings(matches, participants, scoring_system)
    
    await db.tournaments_v2.update_one(
        {"id": tournament_id},
        {"$set": {"matches": matches, "bracket": bracket, "standings": standings, "updated_at": datetime.utcnow()}}
    )
    
    return {"message": "Score updated"}

@router.get("/{tournament_id}/bracket")
async def get_tournament_bracket(
    tournament_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get bracket"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    return tournament.get("bracket", [])

@router.get("/{tournament_id}/standings")
async def get_tournament_standings(
    tournament_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get standings"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    return tournament.get("standings", [])

@router.get("/{tournament_id}/matches")
async def get_tournament_matches(
    tournament_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get matches"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    return tournament.get("matches", [])


@router.post("/{tournament_id}/schedule/generate")
async def generate_tournament_schedule(
    tournament_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user_id: str = Depends(get_current_active_user)
):
    """Generate schedule for tournament matches with time slots and venue fields"""
    
    print(f"🟢 SCHEDULE FUNCTION CALLED: tournament_id={tournament_id}, user={current_user_id}")
    
    # Get tournament
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    print(f"🟢 TOURNAMENT FOUND: {tournament is not None}")
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    # Check if user is organizer
    if tournament.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Only organizer can generate schedule")
    
    # Get event to access venue fields and time slots
    event = await db.events.find_one({"id": tournament.get("event_id")})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Get venue fields and time slots from event or tournament config
    venue_fields = event.get("venue_fields", [])
    if not venue_fields:
        # Fallback to config if event doesn't have venue_fields
        config = tournament.get("config", {})
        venue_fields = config.get("venue_fields", [])
    
    # Final fallback - ensure at least one field
    if not venue_fields or len(venue_fields) == 0:
        venue_fields = ["Saha 1"]
    
    available_time_slots = event.get("available_time_slots", [])
    if not available_time_slots:
        # Fallback to config if event doesn't have time slots
        config = tournament.get("config", {})
        available_time_slots = config.get("available_time_slots", [])
    
    # If still no time slots, generate default ones
    if not available_time_slots:
        # Try both 'date' and 'start_date' fields
        event_date = event.get("start_date") or event.get("date")
        if event_date:
            # Handle both string and datetime objects
            if isinstance(event_date, str):
                start_date = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
            else:
                start_date = event_date
            # Generate hourly slots from 9 AM to 6 PM
            available_time_slots = []
            for hour in range(9, 18):
                slot_time = start_date.replace(hour=hour, minute=0, second=0, microsecond=0)
                available_time_slots.append(slot_time.isoformat())
            print(f"🟢 GENERATED {len(available_time_slots)} default time slots from {start_date}")
    
    # Get matches
    matches = tournament.get("matches", [])
    if not matches or len(matches) == 0:
        # Get more details for error message
        participants = await get_tournament_participants(tournament_id, db)
        raise HTTPException(
            status_code=400, 
            detail=f"No matches to schedule. Please draw first. (Event has {len(participants)} participants, Tournament has {len(matches)} matches)"
        )
    
    # Assign time slots and fields to matches
    time_slot_index = 0
    field_index = 0
    
    print(f"🔵 SCHEDULE DEBUG: About to schedule {len(matches)} matches")
    print(f"🔵 SCHEDULE DEBUG: Available venue_fields: {venue_fields} (count: {len(venue_fields)})")
    print(f"🔵 SCHEDULE DEBUG: Available time_slots: {len(available_time_slots)} slots")
    
    # Assign time slots and fields to matches
    for i, match in enumerate(matches):
        # Assign venue field (round-robin through available fields)
        match["venue_field"] = venue_fields[field_index % len(venue_fields)]
        
        # Assign time slot
        if time_slot_index < len(available_time_slots):
            match["scheduled_time"] = available_time_slots[time_slot_index]
        else:
            # If we run out of time slots, continue cycling through them
            match["scheduled_time"] = available_time_slots[time_slot_index % len(available_time_slots)]
        
        print(f"🟢 MATCH {i+1}: Assigned field '{match['venue_field']}' and time '{match['scheduled_time']}'")
        
        # Move to next field (distribute matches across fields)
        field_index += 1
        
        # Move to next time slot when we've used all fields once
        if field_index % len(venue_fields) == 0:
            time_slot_index += 1
    
    # Update tournament with scheduled matches
    await db.tournaments_v2.update_one(
        {"id": tournament_id},
        {
            "$set": {
                "matches": matches,
                "schedule": {
                    "generated": True,
                    "generated_at": datetime.utcnow(),
                    "venue_fields": venue_fields,
                    "time_slots_used": min(time_slot_index + 1, len(available_time_slots))
                },
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    print(f"✅ SCHEDULE COMPLETE: {len(matches)} matches scheduled using {min(time_slot_index + 1, len(available_time_slots))} time slots")
    
    return {
        "message": "Schedule generated successfully",
        "matches_scheduled": len(matches),
        "venue_fields": venue_fields,
        "time_slots_used": min(time_slot_index + 1, len(available_time_slots)),
        "total_time_slots_available": len(available_time_slots),
        "matches": matches
    }


# ==================== SCORE PROPOSAL & CONFIRMATION ====================

@router.post("/{tournament_id}/matches/{match_id}/propose-score")
async def propose_match_score(
    tournament_id: str,
    match_id: str,
    score_data: MatchScoreUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user_id: str = Depends(get_current_active_user)
):
    """
    Propose a score for a match
    - Referee can confirm immediately
    - Participant proposes and needs confirmation from opponent/referee
    """
    
    # Get tournament and event
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    event_id = tournament.get("event_id")
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Find match
    matches = tournament.get("matches", [])
    match = next((m for m in matches if m.get("id") == match_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Check if user can submit score
    can_submit, reason = ScoreManagementService.can_submit_score(
        current_user_id, match, event, tournament
    )
    
    if not can_submit:
        raise HTTPException(status_code=403, detail="You are not authorized to submit score for this match")
    
    # Check if referee (can confirm immediately)
    is_referee = match.get("referee_id") == current_user_id
    
    if is_referee:
        # Referee confirms immediately
        match["score_participant1"] = score_data.score_participant1
        match["score_participant2"] = score_data.score_participant2
        match["winner_id"] = score_data.winner_id
        match["status"] = "completed"
        match["completed_at"] = datetime.utcnow().isoformat()
        match["notes"] = score_data.notes
        match.pop("pending_score", None)  # Remove any pending proposal
        
        # Update matches in tournament
        for i, m in enumerate(matches):
            if m.get("id") == match_id:
                matches[i] = match
                break
        
        # Recalculate standings
        participants = tournament.get("participants", [])
        config = tournament.get("config", {})
        
        # Get scoring system from event
        if event and event.get("scoring_config"):
            scoring_system = event.get("scoring_config")
        else:
            scoring_system = {"win": 3, "draw": 1, "loss": 0}
        
        standings = TournamentService.calculate_standings(matches, participants, scoring_system)
        
        # Update tournament
        await db.tournaments_v2.update_one(
            {"id": tournament_id},
            {
                "$set": {
                    "matches": matches,
                    "standings": standings,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Send notifications to participants
        player1_id = match.get("player1_id")
        player2_id = match.get("player2_id")
        
        for player_id in [player1_id, player2_id]:
            if player_id:
                await db.notifications.insert_one({
                    "id": str(uuid.uuid4()),
                    "user_id": player_id,
                    "type": "match_score_confirmed",
                    "title": "Maç Sonucu Kesinleşti",
                    "message": f"Hakem {match.get('player1_name', 'Oyuncu 1')} vs {match.get('player2_name', 'Oyuncu 2')} maçının sonucunu onayladı.",
                    "data": {
                        "tournament_id": tournament_id,
                        "match_id": match_id,
                        "event_id": event_id
                    },
                    "created_at": datetime.utcnow(),
                    "read": False
                })
        
        return {
            "message": "Score confirmed by referee",
            "match": match,
            "status": "confirmed"
        }
    
    else:
        # Participant proposes - needs confirmation
        proposal = {
            "score_participant1": score_data.score_participant1,
            "score_participant2": score_data.score_participant2,
            "winner_id": score_data.winner_id,
            "proposed_by": current_user_id,
            "proposed_at": datetime.utcnow().isoformat(),
            "confirmed_by": [],
            "notes": score_data.notes
        }
        
        match["pending_score"] = proposal
        match["status"] = "pending_score"
        
        # Update matches in tournament
        for i, m in enumerate(matches):
            if m.get("id") == match_id:
                matches[i] = match
                break
        
        await db.tournaments_v2.update_one(
            {"id": tournament_id},
            {"$set": {"matches": matches, "updated_at": datetime.utcnow()}}
        )
        
        # Send notifications to people who need to confirm
        users_to_notify = ScoreManagementService.who_needs_to_confirm(current_user_id, match, tournament)
        
        # Get event organizer
        users_to_notify.append(event.get("organizer_id"))
        
        print(f"🔵 Pending score data: {proposal}")
        
        for user_id in set(users_to_notify):  # Remove duplicates
            if user_id and user_id != current_user_id:
                notification_data = {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "type": "score_proposal",
                    "title": "Maç Sonucu Onayı Bekleniyor",
                    "message": f"{match.get('player1_name', 'Oyuncu 1')} vs {match.get('player2_name', 'Oyuncu 2')} maçı için skor önerisi yapıldı. Onaylamanız bekleniyor.",
                    "data": {
                        "tournament_id": tournament_id,
                        "match_id": match_id,
                        "event_id": event_id,
                        "action": "confirm_score",
                        "proposed_score": {
                            "player1_name": match.get('player1_name', 'Oyuncu 1'),
                            "player2_name": match.get('player2_name', 'Oyuncu 2'),
                            "score_participant1": proposal.get("score_participant1"),
                            "score_participant2": proposal.get("score_participant2")
                        }
                    },
                    "created_at": datetime.utcnow(),
                    "read": False
                }
                
                print(f"🟢 Sending notification to user {user_id}")
                print(f"🟢 Notification data: {notification_data.get('data')}")
                
                await db.notifications.insert_one(notification_data)
        
        return {
            "message": "Score proposal sent for confirmation",
            "match": match,
            "status": "pending",
            "needs_confirmation_from": users_to_notify
        }


@router.post("/{tournament_id}/matches/{match_id}/confirm-score")
async def confirm_match_score(
    tournament_id: str,
    match_id: str,
    confirmation: ScoreConfirmation,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user_id: str = Depends(get_current_active_user)
):
    """
    Confirm or reject a proposed score
    """
    
    # Get tournament
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    event_id = tournament.get("event_id")
    event = await db.events.find_one({"id": event_id})
    
    # Find match
    matches = tournament.get("matches", [])
    match = next((m for m in matches if m.get("id") == match_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Check if there's a pending proposal
    pending_score = match.get("pending_score")
    if not pending_score:
        raise HTTPException(status_code=400, detail="No pending score proposal for this match")
    
    proposed_by = pending_score.get("proposed_by")
    
    # Check if user can confirm
    can_confirm = ScoreManagementService.can_confirm_score(current_user_id, proposed_by, match, tournament)
    
    # Or if user is event organizer
    if not can_confirm and event and event.get("organizer_id") == current_user_id:
        can_confirm = True
    
    if not can_confirm:
        raise HTTPException(status_code=403, detail="You are not authorized to confirm this score")
    
    if not confirmation.confirmed:
        # Rejected - remove proposal
        match.pop("pending_score", None)
        match["status"] = "scheduled"
        
        # Update matches
        for i, m in enumerate(matches):
            if m.get("id") == match_id:
                matches[i] = match
                break
        
        await db.tournaments_v2.update_one(
            {"id": tournament_id},
            {"$set": {"matches": matches, "updated_at": datetime.utcnow()}}
        )
        
        # Notify proposer
        await db.notifications.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": proposed_by,
            "type": "score_rejected",
            "title": "Maç Sonucu Reddedildi",
            "message": "Önerdiğiniz skor onaylanmadı. Lütfen tekrar kontrol edin.",
            "data": {
                "tournament_id": tournament_id,
                "match_id": match_id,
                "event_id": event_id
            },
            "created_at": datetime.utcnow(),
            "read": False
        })
        
        return {"message": "Score proposal rejected", "match": match}
    
    # Confirmed - apply score
    match["score_participant1"] = pending_score.get("score_participant1")
    match["score_participant2"] = pending_score.get("score_participant2")
    match["winner_id"] = pending_score.get("winner_id")
    match["status"] = "completed"
    match["completed_at"] = datetime.utcnow().isoformat()
    match["notes"] = pending_score.get("notes")
    match.pop("pending_score", None)
    
    # Update matches
    for i, m in enumerate(matches):
        if m.get("id") == match_id:
            matches[i] = match
            break
    
    # Recalculate standings
    participants = tournament.get("participants", [])
    
    # Get scoring system from event
    if event and event.get("scoring_config"):
        scoring_system = event.get("scoring_config")
    else:
        scoring_system = {"win": 3, "draw": 1, "loss": 0}
    
    standings = TournamentService.calculate_standings(matches, participants, scoring_system)
    
    # Update tournament
    await db.tournaments_v2.update_one(
        {"id": tournament_id},
        {
            "$set": {
                "matches": matches,
                "standings": standings,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    # Notify all parties
    player1_id = match.get("player1_id")
    player2_id = match.get("player2_id")
    referee_id = match.get("referee_id")
    
    notification_users = [player1_id, player2_id, referee_id, proposed_by]
    if event:
        notification_users.append(event.get("organizer_id"))
    
    for user_id in set(notification_users):  # Remove duplicates
        if user_id and user_id != current_user_id:
            await db.notifications.insert_one({
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "type": "score_confirmed",
                "title": "Maç Sonucu Onaylandı",
                "message": f"{match.get('player1_name', 'Oyuncu 1')} vs {match.get('player2_name', 'Oyuncu 2')} maçının sonucu kesinleşti.",
                "data": {
                    "tournament_id": tournament_id,
                    "match_id": match_id,
                    "event_id": event_id
                },
                "created_at": datetime.utcnow(),
                "read": False
            })
    
    return {
        "message": "Score confirmed successfully",
        "match": match,
        "standings": standings
    }

    for i, match in enumerate(matches):
        # Assign venue field
        match["venue_field"] = venue_fields[field_index % len(venue_fields)]
        
        # Assign time slot
        if time_slot_index < len(available_time_slots):
            match["scheduled_time"] = available_time_slots[time_slot_index]
            print(f"🔵 Match {i+1}: Assigned time slot {time_slot_index} -> {available_time_slots[time_slot_index]}, field: {match['venue_field']}")
        else:
            print(f"🔴 Match {i+1}: NO TIME SLOT AVAILABLE (time_slot_index={time_slot_index} >= {len(available_time_slots)})")
        
        # Update status to scheduled if not already set
        if match.get("status") == "pending":
            match["status"] = "scheduled"
        
        # Move to next field, if all fields used, move to next time slot
        field_index += 1
        if field_index % len(venue_fields) == 0:
            time_slot_index += 1
            print(f"🔵 All fields used, moving to time slot {time_slot_index}")
    
    # Update tournament with scheduled matches
    await db.tournaments_v2.update_one(
        {"id": tournament_id},
        {
            "$set": {
                "matches": matches,
                "status": "scheduled",
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    return {
        "message": "Schedule generated successfully",
        "total_matches": len(matches),
        "venue_fields_used": len(venue_fields),
        "time_slots_used": time_slot_index + 1
    }


# ============================================
# REFEREE MANAGEMENT - ENHANCED
# ============================================

@router.get("/{tournament_id}/available-referees")
async def get_available_referees(
    tournament_id: str,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get list of available referees (users with referee role + event participants)"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get event to access participants
    event_id = tournament.get("event_id")
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    available_referees = []
    
    # 1. Get users with 'referee' role
    referee_users = await db.users.find({
        "roles": {"$in": ["referee", "Hakem"]}
    }).to_list(1000)
    
    for user in referee_users:
        available_referees.append({
            "id": user.get("id"),
            "full_name": user.get("full_name"),
            "email": user.get("email"),
            "phone": user.get("phone"),
            "type": "referee",
            "referee_profile": user.get("referee_profile", {}),
            "sports": user.get("referee_profile", {}).get("sports", [])
        })
    
    # 2. Get event participants (players who can also be referees)
    participant_ids = event.get("participants", [])
    if participant_ids:
        participants = await db.users.find({
            "id": {"$in": participant_ids}
        }).to_list(1000)
        
        for participant in participants:
            if participant:  # Check if participant is not None
                # Check if not already in referee list
                if not any(r["id"] == participant.get("id") for r in available_referees):
                    player_profile = participant.get("player_profile") or {}
                    available_referees.append({
                        "id": participant.get("id"),
                        "full_name": participant.get("full_name"),
                        "email": participant.get("email"),
                        "phone": participant.get("phone"),
                        "type": "participant",
                        "player_profile": player_profile,
                        "sports": player_profile.get("sports", [])
                    })
    
    return {
        "referees": available_referees,
        "total": len(available_referees)
    }


@router.post("/{tournament_id}/referees/auto-assign")
async def auto_assign_referees(
    tournament_id: str,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Automatically assign referees to matches with conflict prevention and balanced distribution"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    referees = tournament.get("referees", [])
    matches = tournament.get("matches", [])
    
    if not referees:
        raise HTTPException(status_code=400, detail="No referees added to tournament")
    
    if not matches:
        raise HTTPException(status_code=400, detail="No matches available")
    
    # Sort matches by scheduled_time (if available)
    matches_with_time = [m for m in matches if m.get("scheduled_time")]
    matches_without_time = [m for m in matches if not m.get("scheduled_time")]
    
    # Initialize referee assignment tracking
    referee_load = {ref["id"]: [] for ref in referees}
    referee_match_times = {ref["id"]: [] for ref in referees}
    
    # Get match duration from config (default 90 minutes)
    match_duration = tournament.get("config", {}).get("match_duration_minutes", 90)
    
    def can_assign_referee(referee_id, match):
        """Check if referee can be assigned to match (no time conflicts)"""
        if not match.get("scheduled_time"):
            return True
        
        match_start = match["scheduled_time"]
        match_end = match_start + timedelta(minutes=match_duration)
        
        # Check if referee has any conflicting matches
        for assigned_time in referee_match_times[referee_id]:
            assigned_start, assigned_end = assigned_time
            # Check for overlap
            if not (match_end <= assigned_start or match_start >= assigned_end):
                return False
        
        # Check if referee is playing in this match
        if match.get("participant1_id") == referee_id or match.get("participant2_id") == referee_id:
            return False
        
        return True
    
    assignments_made = 0
    
    # Assign referees to matches with scheduled times first
    for match in matches_with_time:
        # Find available referee with minimum load
        available_referees = [
            ref_id for ref_id in referee_load.keys() 
            if can_assign_referee(ref_id, match)
        ]
        
        if available_referees:
            # Choose referee with minimum current load
            chosen_referee = min(available_referees, key=lambda r: len(referee_load[r]))
            
            # Assign referee
            match["referee_id"] = chosen_referee
            referee_load[chosen_referee].append(match["id"])
            
            # Track time slot
            match_start = match["scheduled_time"]
            match_end = match_start + timedelta(minutes=match_duration)
            referee_match_times[chosen_referee].append((match_start, match_end))
            
            # Update referee's assigned matches
            for ref in referees:
                if ref["id"] == chosen_referee:
                    if "assigned_matches" not in ref:
                        ref["assigned_matches"] = []
                    ref["assigned_matches"].append(match["id"])
                    break
            
            assignments_made += 1
    
    # Assign referees to matches without scheduled times (balanced distribution)
    for match in matches_without_time:
        # Find referees who are not playing in this match
        available_referees = [
            ref_id for ref_id in referee_load.keys()
            if match.get("participant1_id") != ref_id and match.get("participant2_id") != ref_id
        ]
        
        if available_referees:
            # Choose referee with minimum current load
            chosen_referee = min(available_referees, key=lambda r: len(referee_load[r]))
            
            # Assign referee
            match["referee_id"] = chosen_referee
            referee_load[chosen_referee].append(match["id"])
            
            # Update referee's assigned matches
            for ref in referees:
                if ref["id"] == chosen_referee:
                    if "assigned_matches" not in ref:
                        ref["assigned_matches"] = []
                    ref["assigned_matches"].append(match["id"])
                    break
            
            assignments_made += 1
    
    # Update tournament
    await db.tournaments_v2.update_one(
        {"id": tournament_id},
        {
            "$set": {
                "matches": matches,
                "referees": referees,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    # Calculate statistics
    referee_stats = []
    for referee in referees:
        assigned_count = len(referee.get("assigned_matches", []))
        referee_stats.append({
            "referee_name": referee.get("full_name"),
            "assigned_matches": assigned_count
        })
    
    return {
        "message": "Referees auto-assigned successfully",
        "total_matches": len(matches),
        "assignments_made": assignments_made,
        "referee_stats": referee_stats
    }


@router.delete("/{tournament_id}/referees/{referee_id}")
async def remove_referee(
    tournament_id: str,
    referee_id: str,
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Remove referee from tournament"""
    
    tournament = await db.tournaments_v2.find_one({"id": tournament_id})
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Remove referee from referee list
    referees = tournament.get("referees", [])
    referees = [r for r in referees if r.get("id") != referee_id]
    
    # Remove referee assignments from matches
    matches = tournament.get("matches", [])
    for match in matches:
        if match.get("referee_id") == referee_id:
            match["referee_id"] = None
    
    await db.tournaments_v2.update_one(
        {"id": tournament_id},
        {
            "$set": {
                "referees": referees,
                "matches": matches,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    return {"message": "Referee removed successfully"}

