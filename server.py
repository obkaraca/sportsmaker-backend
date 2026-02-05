from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, Request, Response, Body
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import uuid
import httpx
import jwt

from models import (
    User, UserCreate, UserLogin,
    Event, EventCreate, EventType,
    Venue, VenueCreate,
    Participation, ParticipationBase,
    Ticket, TicketBase,
    Review, ReviewBase,
    Message, MessageBase,
    Ranking, RankingEntry,
    SearchRequest, PaymentProvider,
    SkillLevel, Gender,
    Notification, NotificationCreate, NotificationType, NotificationRelatedType,
    PushToken, PushTokenBase,
    GroupChat, GroupChatCreate, GroupMessage, GroupMessageBase, GroupMessagePermission,
    Payment, PaymentCreate, PaymentStatus,
    Team, TeamCreateRequest, TeamUpdateRequest, TeamPlayer, TeamPlayerRole
)
from oauth_models import SessionData, UserSession, PaymentTransaction, StripeCheckoutRequest
from auth import (
    get_password_hash, verify_password, create_access_token, 
    get_current_user, get_current_user_optional, decode_token,
    SECRET_KEY, ALGORITHM
)
from payment_service import payment_service
# Stripe integration - using stripe library directly
import stripe
from push_notification_service import PushNotificationService
from background_scheduler import EventReminderScheduler
from notification_endpoints import notification_router, create_notification_helper
from support_endpoints import support_router
from review_endpoints import review_router, set_review_db
from tournament_endpoints import router as tournament_router
from tournament_endpoints_v2 import router as tournament_v2_router
from marketplace_endpoints import router as marketplace_router
from facility_endpoints import router as facility_router
from membership_endpoints import router as membership_router
from reservation_payment_endpoints import router as reservation_payment_router
from event_payment_endpoints import router as event_payment_router
from person_reservation_payment_endpoints import router as person_reservation_payment_router
from sport_config_endpoints import router as sport_config_router
from management_endpoints import router as management_router
from expense_endpoints import router as expense_router
from promo_code_endpoints import router as promo_code_router
from event_management_endpoints import event_management_router, set_database as set_event_management_db
from league_management_endpoints import league_management_router, set_league_db
from custom_scoring_endpoints import custom_scoring_router, set_custom_scoring_db
from system_tests import router as system_tests_router
from cancellation_endpoints import router as cancellation_router, set_cancellation_db
from workflow_endpoints import workflow_router, set_database as set_workflow_db, trigger_workflow
from assistant_endpoints import assistant_router, set_database as set_assistant_db
from ranking_management_endpoints import ranking_router, set_ranking_db

# Yeni modüler endpoint'ler
from auth_endpoints import router as auth_router, set_database as set_auth_db
from user_endpoints import router as user_router, set_database as set_user_db
from report_endpoints import router as report_router, set_database as set_report_db
from map_endpoints import router as map_router, set_database as set_map_db
from message_endpoints import router as message_router, set_database as set_message_db
from admin_endpoints import admin_router, set_database as set_admin_db
from commission_endpoints import router as commission_router, set_db as set_commission_db
from geliver_endpoints import router as geliver_router, set_db as set_geliver_db
from legal_endpoints import router as legal_router


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection settings
mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']

# Global variables - will be initialized in lifespan
client = None
db = None

# Initialize Push Notification Service
push_service = PushNotificationService()

# Initialize Stripe
stripe_api_key = os.getenv('STRIPE_API_KEY', 'sk_test_emergent')
stripe_checkout = None

def init_stripe(request: Request):
    global stripe_checkout
    if not stripe_checkout:
        host_url = str(request.base_url)
        webhook_url = f"{host_url}api/webhook/stripe"
        stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)
    return stripe_checkout

# Lifespan context manager for proper startup/shutdown
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - handles startup and shutdown"""
    global client, db
    
    # Startup
    logger.info("🚀 Starting application...")
    
    # Initialize MongoDB client in the correct event loop
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Test connection
    try:
        await client.admin.command('ping')
        logger.info("✅ MongoDB connection established")
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
    
    # Store db in app state
    app.state.db = db
    app.state.client = client
    
    # Modüllere database referansı gönder
    set_auth_db(db)
    set_user_db(db)
    set_report_db(db)
    set_map_db(db)
    set_message_db(db)
    set_event_management_db(db)
    set_admin_db(db)
    set_commission_db(db)
    set_geliver_db(db)
    set_review_db(db)
    set_cancellation_db(db)
    set_workflow_db(db)
    set_assistant_db(db)
    set_league_db(db)
    set_custom_scoring_db(db)
    set_ranking_db(db)
    
    # Push notification service'e db referansı ver
    push_service.set_db(db)
    
    logger.info("✅ Database references set for all modules")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down application...")
    if client:
        client.close()
        logger.info("✅ MongoDB connection closed")

# Create the main app with lifespan
app = FastAPI(title="SportyConnect API", lifespan=lifespan)

# Root health check endpoint for Kubernetes (without /api prefix)
@app.get("/health")
async def root_health_check():
    """Health check endpoint for Kubernetes liveness/readiness probes"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Socket.IO for real-time messaging - Will be integrated later
# Placeholder for now
# sio = socketio.AsyncServer(
#     async_mode='asgi',
#     cors_allowed_origins='*',
#     logger=True,
#     engineio_logger=True
# )
# socket_app = socketio.ASGIApp(sio, app)

# Create API router
api_router = APIRouter()

# Helper function to create notifications
async def create_notification(
    user_id: str,
    notification_type: NotificationType,
    title: str,
    message: str,
    related_id: Optional[str] = None,
    related_type: Optional[NotificationRelatedType] = None
):
    """Helper function to create a notification and send push notification"""
    try:
        notification_data = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": notification_type.value,
            "title": title,
            "message": message,
            "related_id": related_id,
            "related_type": related_type.value if related_type else None,
            "read": False,
            "created_at": datetime.utcnow()
        }
        
        # Save to database
        await db.notifications.insert_one(notification_data)
        
        # Send push notification
        try:
            await push_service.send_notification(
                user_id=user_id,
                title=title,
                body=message,
                data={
                    "type": notification_type.value,
                    "related_id": related_id,
                    "related_type": related_type.value if related_type else None
                }
            )
        except Exception as e:
            logging.warning(f"Failed to send push notification: {str(e)}")
        
        return notification_data
    except Exception as e:
        logging.error(f"Failed to create notification: {str(e)}")
        return None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== AUTHENTICATION ROUTES ====================
# NOTE: Temel auth endpoint'leri auth_endpoints.py modülüne taşındı
# Bu modül /api/auth prefix'i ile include ediliyor (satır 8649)
# Aşağıdaki endpoint'ler modüler dosyada olmayan özel endpoint'lerdir

# /auth/register -> auth_endpoints.py
# /auth/login -> auth_endpoints.py  
# /auth/request-login-otp -> auth_endpoints.py
# /auth/login-with-otp -> auth_endpoints.py
# /auth/me -> auth_endpoints.py
# /auth/send-verification -> auth_endpoints.py
# /auth/verify-code -> auth_endpoints.py
# /auth/resend-verification -> auth_endpoints.py

# Aşağıdaki endpoint'ler server.py'da kalıyor (modüler dosyada yok):
# /auth/oauth/session
# /auth/session
# /auth/logout

@api_router.get("/users/me")
async def get_user_me(current_user_id: str = Depends(get_current_user)):
    """Get current user info (alias for /auth/me)"""
    # current_user_id dict olabilir
    if isinstance(current_user_id, dict):
        user_id = current_user_id.get("id")
    else:
        user_id = current_user_id
    
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    user_dict = {k: v for k, v in user.items() if k not in ["_id", "hashed_password", "password_hash"]}
    return user_dict

@api_router.get("/users/me/stats")
async def get_user_stats(current_user_id: str = Depends(get_current_user)):
    """Get user statistics"""
    # Count events organized
    events_organized = await db.events.count_documents({"organizer_id": current_user_id})
    
    # Count participations (events joined)
    participations = await db.participations.count_documents({"user_id": current_user_id})
    
    # Count tournaments
    tournaments = await db.tournament_management.count_documents({"organizer_id": current_user_id})
    
    # Count reservations
    reservations = await db.reservations.count_documents({"user_id": current_user_id})
    
    # Calculate points (based on participations and wins)
    total_points = 0
    
    # Points from completed matches
    matches = await db.matches.find({
        "$or": [
            {"participant1_id": current_user_id},
            {"participant2_id": current_user_id}
        ],
        "status": "completed",
        "winner_id": {"$ne": None}
    }).to_list(1000)
    
    # 3 points per win
    for match in matches:
        if match.get("winner_id") == current_user_id:
            total_points += 3
    
    return {
        "events_organized": events_organized,
        "events_joined": participations,
        "tournaments": tournaments,
        "reservations": reservations,
        "total_points": total_points,
        "matches_played": len(matches),
        "matches_won": sum(1 for m in matches if m.get("winner_id") == current_user_id)
    }

@api_router.put("/users/me")
async def update_profile(
    update_data: dict,
    current_user_id: str = Depends(get_current_user)
):
    """Update current user profile"""
    print(f"🔧 Profile update - User ID: {current_user_id}, Type: {type(current_user_id)}")
    print(f"🔧 Update data fields: {list(update_data.keys())}")
    
    # Allowed fields to update
    allowed_fields = [
        'full_name', 'phone', 'city', 'district', 'profile_image', 'avatar',
        'date_of_birth', 'tckn', 'vk_no', 'languages', 'bio',
        'instagram', 'twitter_x', 'youtube', 'linkedin', 'website',
        'match_fee', 'hourly_rate', 'daily_rate', 'monthly_membership',
        'financial_info', 'player_profile', 'coach_profile', 'referee_profile', 'venue_profile',
        'documents', 'club_organization', 'iban', 'availability', 'video_url', 'video_type', 'tc_kimlik_no'
    ]
    
    update_dict = {}
    for field in allowed_fields:
        if field in update_data:
            update_dict[field] = update_data[field]
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    
    # current_user_id dictionary olabilir, extract edelim
    if isinstance(current_user_id, dict):
        user_id = current_user_id.get("id")
        print(f"🔧 Extracted user_id from dict: {user_id}")
    else:
        user_id = current_user_id
    
    # Check if user exists first
    existing_user = await db.users.find_one({"id": user_id})
    print(f"🔧 User found: {existing_user is not None}")
    if not existing_user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": update_dict}
    )
    
    print(f"🔧 Update result - matched: {result.matched_count}, modified: {result.modified_count}")
    
    # Get updated user
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found after update")
    
    # MongoDB'den _id'yi çıkar ve password alanlarını temizle
    user_data = {k: v for k, v in user.items() if k not in ["_id", "password_hash", "hashed_password"]}
    
    print(f"✅ Profile updated successfully for user: {user_id}")
    
    # Pydantic validation'ı bypass et, direkt dict döndür
    return user_data

# ==================== EVENT ROUTES ====================

@api_router.post("/events", response_model=Event)
async def create_event(event: EventCreate, current_user: dict = Depends(get_current_user)):
    """Create a new event (match, tournament, league, camp)"""
    try:
        # Extract user_id from current_user dict
        current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
        
        event_dict = event.dict()
        
        # Negatif fiyat kontrolü
        if event_dict.get("price", 0) < 0:
            raise HTTPException(status_code=400, detail="Fiyat negatif olamaz")
        
        # prices dict içindeki değerleri kontrol et
        prices = event_dict.get("prices", {})
        if prices:
            for price_type, price_value in prices.items():
                if price_value is not None and price_value < 0:
                    raise HTTPException(status_code=400, detail=f"{price_type} fiyatı negatif olamaz")
        
        # 15 dakika kontrolü - geçmiş tarihli etkinlik oluşturulamaz
        start_date = event_dict.get("start_date")
        if start_date:
            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            min_date = datetime.utcnow() + timedelta(minutes=15)
            if start_date.tzinfo:
                min_date = min_date.replace(tzinfo=start_date.tzinfo)
            if start_date < min_date:
                raise HTTPException(status_code=400, detail="Etkinlik en erken 15 dakika sonrasına oluşturulabilir")
        
        # Ücretli etkinlik kontrolü
        if event_dict.get("price", 0) > 0:
            organizer = await db.users.find_one({"id": current_user_id})
            if not organizer:
                raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
            
            if not organizer.get("tckn"):
                raise HTTPException(status_code=400, detail="Ücretli etkinlik oluşturmak için TC Kimlik Numaranızı profil ayarlarından girmeniz gerekmektedir.")
            
            if not organizer.get("financial_info", {}).get("iban"):
                raise HTTPException(status_code=400, detail="Ücretli etkinlik oluşturmak için IBAN numaranızı profil ayarlarından girmeniz gerekmektedir.")
        
        event_id = str(uuid.uuid4())
        event_dict["id"] = event_id
        event_dict["created_at"] = datetime.utcnow()
        event_dict["participant_count"] = 0
        event_dict["participants"] = []
        event_dict["is_active"] = True
        event_dict["status"] = "pending"
        event_dict["organizer_id"] = current_user_id
        
        db_event_dict = event_dict.copy()
        await db.events.insert_one(db_event_dict)
        
        # Admin notifications
        admins = await db.users.find({"user_type": {"$in": ["admin", "super_admin"]}}).to_list(length=None)
        for admin in admins:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": admin["id"],
                "type": "event_approval",
                "title": "Yeni Etkinlik Onay Bekliyor",
                "message": f"{event_dict['title']} etkinliği onayınızı bekliyor",
                "read": False,
                "created_at": datetime.utcnow(),
                "event_id": event_id,
                "data": {"event_id": event_id, "event_title": event_dict['title'], "organizer_id": current_user_id}
            }
            await db.notifications.insert_one(notification)
        
        # Group chat
        group_chat = {
            "id": str(uuid.uuid4()),
            "name": f"{event_dict['title']} - Grup Sohbeti",
            "description": f"{event_dict['sport']} etkinliği grup sohbeti",
            "event_id": event_id,
            "creator_id": current_user_id,
            "admin_ids": [current_user_id],
            "member_ids": [current_user_id],
            "permission": "everyone",
            "invite_link": None,
            "created_at": datetime.utcnow()
        }
        await db.group_chats.insert_one(group_chat)
        
        # Creator notification
        creator_notif = {
            "id": str(uuid.uuid4()),
            "user_id": current_user_id,
            "type": "event_created",
            "title": "Etkinliğiniz Oluşturuldu",
            "message": f"'{event_dict['title']}' etkinliğiniz başarıyla oluşturuldu!",
            "related_id": event_id,
            "related_type": "event",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(creator_notif)
        
        event_dict.pop('_id', None)
        print(f"✅ Event dict keys before return: {list(event_dict.keys())}")
        print(f"✅ Attempting to create Event model...")
        
        # Etkinlik oluşturma log'u
        from auth_endpoints import log_user_activity
        await log_user_activity(current_user_id, "event_create", "success", {
            "event_id": event_id,
            "event_title": event_dict.get("title"),
            "event_type": event_dict.get("event_type"),
            "sport": event_dict.get("sport"),
            "price": event_dict.get("price", 0)
        })
        
        result = Event(**event_dict)
        print(f"✅ Event model created successfully!")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Event creation error: {str(e)}")
        print(f"❌ Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Etkinlik oluşturulamadı: {str(e)}")

@api_router.get("/events", response_model=List[Event])
async def get_events(
    sport: Optional[str] = None,
    city: Optional[str] = None,
    event_type: Optional[EventType] = None,
    organizer: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    include_past: bool = True,  # Geçmiş etkinlikleri dahil et (varsayılan: evet)
    current_user_id: Optional[str] = Depends(get_current_user_optional)
):
    """Get all events with optional filters"""
    print(f"🔍 GET /events called - current_user_id: {current_user_id}")
    query = {}
    
    # If organizer=me, show all user's events (pending, active, rejected)
    # Otherwise, only show active events (public list)
    if organizer == "me" and current_user_id:
        # Kullanıcının organizatör, yönetici veya asistan olduğu TÜM etkinlikleri getir
        query["$or"] = [
            {"organizer_id": current_user_id},
            {"created_by": current_user_id},
            {"organizers": current_user_id},
            {"managers": current_user_id},
            {"assistants": current_user_id}
        ]
        # Don't filter by status - show all user's events
    elif organizer:
        query["organizer_id"] = organizer
        query["status"] = "active"  # Other users' events must be active
    else:
        # Public list - only show active events
        query["status"] = "active"
    
    if sport:
        query["sport"] = sport
    if city:
        query["city"] = city
    if event_type:
        query["event_type"] = event_type
    
    # Geçmiş etkinlikleri filtrele (include_past=False ise)
    # NOT: organizer=me ise kullanıcı kendi etkinliklerini yönetmek istiyor, geçmiş etkinlikleri de göster
    # NOT: Varsayılan olarak tüm aktif etkinlikleri göster (include_past varsayılan True)
    from datetime import datetime
    now = datetime.utcnow()
    
    # organizer=me ise veya include_past=True ise geçmiş etkinlikleri de göster
    # Varsayılan olarak tüm aktif etkinlikleri göster
    should_include_past = True  # Varsayılan olarak tüm etkinlikleri göster
    if include_past is False:  # Sadece açıkça False verilirse filtreleme yap
        should_include_past = False
    
    if not should_include_past:
        # Sadece gelecek etkinlikleri göster
        query["end_date"] = {"$gte": now}
        print(f"🔍 Showing only future events (end_date >= {now})")
    else:
        print(f"🔍 Showing ALL events including past (include_past=True or organizer=me)")
    
    print(f"🔍 Query: {query}")
    
    # Sıralama: organizer=me ise last_accessed'e göre (en son erişilen en üstte), değilse start_date'e göre
    if organizer == "me":
        # last_accessed yoksa created_at'e göre sırala
        events = await db.events.find(query).sort([("last_accessed", -1), ("created_at", -1)]).skip(skip).limit(limit).to_list(limit)
    else:
        events = await db.events.find(query).sort("start_date", 1).skip(skip).limit(limit).to_list(limit)
    
    print(f"🔍 Found {len(events)} events")
    
    if events:
        print(f"🔍 First event participants: {events[0].get('participants', [])}")
    
    # Remove MongoDB _id field before validation
    # Also fix participants field - ensure it's a list of strings, not dicts
    for event in events:
        event.pop('_id', None)
        
        # Fix participants field if it contains dicts instead of strings
        participants = event.get('participants', [])
        if participants:
            # Check if ANY participant is a dict (not just the first one)
            has_dict = any(isinstance(p, dict) for p in participants)
            if has_dict:
                # Extract just the IDs from the dict format
                event['participants'] = [p.get('id') if isinstance(p, dict) else p for p in participants]
                print(f"🔧 Fixed participants for event {event.get('title')}: {event['participants']}")
    
    print(f"🔍 Returning {len(events)} events")
    return [Event(**event) for event in events]

@api_router.get("/events/{event_id}", response_model=Event)
async def get_event(event_id: str):
    """Get event by ID"""
    logging.info(f"🔍 GET EVENT - Searching for event_id: '{event_id}' (len: {len(event_id)})")
    
    # Try to find by 'id' field first (UUID format)
    event = await db.events.find_one({"id": event_id})
    
    # If not found, try to find by '_id' (MongoDB ObjectId)
    if not event:
        try:
            from bson import ObjectId
            event = await db.events.find_one({"_id": ObjectId(event_id)})
        except:
            pass
    
    logging.info(f"🔍 GET EVENT - Found: {event is not None}")
    if not event:
        # Try to find ANY event to debug
        sample = await db.events.find_one({}, {"id": 1, "title": 1})
        if sample:
            logging.info(f"🔍 Sample event ID: '{sample.get('id')}' (len: {len(sample.get('id', ''))})")
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Son erişim zamanını güncelle (etkinlik yönetimi sıralaması için)
    from datetime import datetime
    await db.events.update_one(
        {"id": event_id},
        {"$set": {"last_accessed": datetime.utcnow()}}
    )
    
    # Remove MongoDB _id field
    event.pop('_id', None)
    
    # Fix participants field if it contains dicts instead of strings
    participants = event.get('participants', [])
    if participants:
        # Check if ANY participant is a dict (not just the first one)
        has_dict = any(isinstance(p, dict) for p in participants)
        if has_dict:
            event['participants'] = [p.get('id') if isinstance(p, dict) else p for p in participants]
    
    return Event(**event)


@api_router.patch("/events/{event_id}")
async def update_event_partial(event_id: str, updates: dict = Body(...)):
    """Partially update event fields"""
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Allowed fields to update
    allowed_fields = [
        "registration_deadline", "title", "description", "start_date", "end_date",
        "max_participants", "ticket_info", "status", "location"
    ]
    
    update_data = {}
    for field in allowed_fields:
        if field in updates:
            update_data[field] = updates[field]
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    
    update_data["updated_at"] = datetime.utcnow().isoformat()
    
    await db.events.update_one(
        {"id": event_id},
        {"$set": update_data}
    )
    
    return {"status": "success", "message": "Event updated", "updated_fields": list(update_data.keys())}


@api_router.put("/events/{event_id}")
async def update_event(
    event_id: str, 
    updates: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Update event - Only organizer or admin can update"""
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    current_user_id = current_user["id"]
    user_type = current_user.get("user_type", "")
    
    # Yetki kontrolü: organizer veya admin olmalı
    is_organizer = event.get("organizer_id") == current_user_id
    is_admin = user_type in ["admin", "super_admin"]
    
    if not is_organizer and not is_admin:
        raise HTTPException(status_code=403, detail="Bu etkinliği düzenleme yetkiniz yok")
    
    # Allowed fields to update - TÜM ALANLAR EKLENDİ
    allowed_fields = [
        "title", "description", "location", "city",
        "max_participants", "min_participants",
        "start_date", "end_date",
        "skill_level", "gender_restriction",
        "age_min", "age_max", "prize_money",
        "venue_id", "venue_fee"
    ]
    
    update_data = {}
    for field in allowed_fields:
        if field in updates and updates[field] is not None:
            update_data[field] = updates[field]
    
    if not update_data:
        raise HTTPException(status_code=400, detail="Güncellenecek alan bulunamadı")
    
    # =====================================================
    # ORGANİZATÖR DEĞİŞİKLİĞİ - ADMİN ONAYINA GÖNDERİLİR
    # =====================================================
    if is_organizer and not is_admin:
        # Değişiklikleri bekleyen onay olarak kaydet
        change_request = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "event_title": event.get("title", ""),
            "organizer_id": current_user_id,
            "requested_changes": update_data,
            "original_values": {field: event.get(field) for field in update_data.keys()},
            "status": "pending",  # pending, approved, rejected
            "created_at": datetime.utcnow().isoformat(),
            "reviewed_at": None,
            "reviewed_by": None,
            "rejection_reason": None
        }
        
        await db.event_change_requests.insert_one(change_request)
        
        # Organizatör bilgisini al
        organizer = await db.users.find_one({"id": current_user_id})
        organizer_name = organizer.get("full_name", "Organizatör") if organizer else "Organizatör"
        
        # Değişiklikleri okunabilir formatta hazırla
        changes_text = []
        field_labels = {
            "title": "Başlık",
            "description": "Açıklama",
            "location": "Konum",
            "city": "Şehir",
            "start_date": "Başlangıç Tarihi",
            "end_date": "Bitiş Tarihi",
            "max_participants": "Max Katılımcı",
            "min_participants": "Min Katılımcı",
            "skill_level": "Seviye",
            "gender_restriction": "Cinsiyet",
            "age_min": "Min Yaş",
            "age_max": "Max Yaş",
            "prize_money": "Ödül"
        }
        for field, new_value in update_data.items():
            label = field_labels.get(field, field)
            old_value = event.get(field, "Belirtilmemiş")
            changes_text.append(f"• {label}: {old_value} → {new_value}")
        
        # Tüm adminlere bildirim gönder
        admins = await db.users.find({"user_type": {"$in": ["admin", "super_admin"]}}).to_list(length=100)
        
        for admin in admins:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": admin["id"],
                "type": "event_change_request",
                "title": f"📝 Etkinlik Değişiklik Talebi",
                "message": f"{organizer_name} '{event.get('title')}' etkinliğinde değişiklik yapmak istiyor.\n\n" + "\n".join(changes_text),
                "data": {
                    "change_request_id": change_request["id"],
                    "event_id": event_id,
                    "event_title": event.get("title"),
                    "organizer_name": organizer_name,
                    "requested_changes": update_data
                },
                "read": False,
                "created_at": datetime.utcnow().isoformat()
            }
            await db.notifications.insert_one(notification)
            
            # Push notification
            if admin.get("push_token"):
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            "https://exp.host/--/api/v2/push/send",
                            json={
                                "to": admin["push_token"],
                                "title": "📝 Etkinlik Değişiklik Talebi",
                                "body": f"{organizer_name} '{event.get('title')}' etkinliğinde değişiklik yapmak istiyor",
                                "data": {"type": "event_change_request", "change_request_id": change_request["id"]}
                            }
                        )
                except Exception as e:
                    logger.warning(f"Push notification error: {e}")
        
        logger.info(f"📝 Event change request created: {change_request['id']} for event {event_id}")
        
        return {
            "status": "pending_approval",
            "message": "Değişiklik talebiniz yönetici onayına gönderildi",
            "change_request_id": change_request["id"],
            "requested_changes": list(update_data.keys())
        }
    
    # =====================================================
    # ADMİN DEĞİŞİKLİĞİ - DİREKT UYGULANIR
    # =====================================================
    
    # max_participants için ticket_info güncelle - TÜM ALANLARI KORU
    if "max_participants" in update_data:
        ticket_info = event.get("ticket_info") or {}
        # Mevcut alanları koru, sadece total_slots güncelle
        ticket_info["total_slots"] = update_data["max_participants"]
        # Eksik alanları varsayılan değerlerle doldur
        if "price" not in ticket_info:
            ticket_info["price"] = 0
        if "available_slots" not in ticket_info:
            ticket_info["available_slots"] = update_data["max_participants"]
        update_data["ticket_info"] = ticket_info
    
    if not update_data:
        raise HTTPException(status_code=400, detail="Güncellenecek alan bulunamadı")
    
    update_data["updated_at"] = datetime.utcnow().isoformat()
    
    # Tarih veya konum değişikliği kontrolü - Katılımcılara bildirim gönder
    date_changed = False
    location_changed = False
    changes_summary = []
    
    # Tarih değişikliği kontrolü
    old_start = event.get("start_date")
    old_end = event.get("end_date")
    new_start = update_data.get("start_date")
    new_end = update_data.get("end_date")
    
    if new_start and old_start != new_start:
        date_changed = True
        try:
            old_dt = datetime.fromisoformat(old_start.replace('Z', '+00:00')) if old_start else None
            new_dt = datetime.fromisoformat(new_start.replace('Z', '+00:00')) if new_start else None
            if old_dt and new_dt:
                changes_summary.append(f"Başlangıç tarihi: {old_dt.strftime('%d/%m/%Y %H:%M')} → {new_dt.strftime('%d/%m/%Y %H:%M')}")
        except:
            changes_summary.append("Başlangıç tarihi değiştirildi")
    
    if new_end and old_end != new_end:
        date_changed = True
        try:
            old_dt = datetime.fromisoformat(old_end.replace('Z', '+00:00')) if old_end else None
            new_dt = datetime.fromisoformat(new_end.replace('Z', '+00:00')) if new_end else None
            if old_dt and new_dt:
                changes_summary.append(f"Bitiş tarihi: {old_dt.strftime('%d/%m/%Y %H:%M')} → {new_dt.strftime('%d/%m/%Y %H:%M')}")
        except:
            changes_summary.append("Bitiş tarihi değiştirildi")
    
    # Konum değişikliği kontrolü
    old_location = event.get("location", "")
    old_city = event.get("city", "")
    new_location = update_data.get("location")
    new_city = update_data.get("city")
    
    if new_location and old_location != new_location:
        location_changed = True
        changes_summary.append(f"Konum: {old_location or 'Belirtilmemiş'} → {new_location}")
    
    if new_city and old_city != new_city:
        location_changed = True
        changes_summary.append(f"Şehir: {old_city or 'Belirtilmemiş'} → {new_city}")
    
    # Veritabanı güncelle
    await db.events.update_one(
        {"id": event_id},
        {"$set": update_data}
    )
    
    logger.info(f"✅ Event {event_id} updated by user {current_user_id}")
    
    # Tarih veya konum değiştiyse katılımcılara bildirim gönder
    notifications_sent = 0
    if date_changed or location_changed:
        try:
            # Katılımcıları bul
            participations = await db.event_participants.find({"event_id": event_id}).to_list(length=1000)
            participant_ids = [p.get("user_id") for p in participations if p.get("user_id")]
            
            # Ayrıca events.participants array'inden de al
            event_participants = event.get("participants", [])
            for p in event_participants:
                if isinstance(p, str) and p not in participant_ids:
                    participant_ids.append(p)
                elif isinstance(p, dict) and p.get("user_id") and p.get("user_id") not in participant_ids:
                    participant_ids.append(p.get("user_id"))
            
            # Organizatörü çıkar (kendine bildirim gönderme)
            organizer_id = event.get("organizer_id")
            if organizer_id in participant_ids:
                participant_ids.remove(organizer_id)
            
            if participant_ids:
                # Bildirim mesajı oluştur
                change_type = []
                if date_changed:
                    change_type.append("tarih")
                if location_changed:
                    change_type.append("konum")
                
                notification_title = f"📅 Etkinlik Güncellendi: {event.get('title', 'Etkinlik')}"
                notification_body = f"{' ve '.join(change_type).capitalize()} değişikliği yapıldı.\n" + "\n".join(changes_summary)
                
                # Her katılımcıya bildirim gönder
                for user_id in participant_ids:
                    notification = {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "type": "event_update",
                        "title": notification_title,
                        "message": notification_body,
                        "data": {
                            "event_id": event_id,
                            "event_title": event.get("title"),
                            "date_changed": date_changed,
                            "location_changed": location_changed,
                            "changes": changes_summary
                        },
                        "is_read": False,
                        "created_at": datetime.utcnow().isoformat()
                    }
                    await db.notifications.insert_one(notification)
                    notifications_sent += 1
                    
                    # Push notification gönder
                    try:
                        user = await db.users.find_one({"id": user_id})
                        if user and user.get("push_token"):
                            push_message = {
                                "to": user["push_token"],
                                "title": notification_title,
                                "body": notification_body[:200],
                                "data": {"event_id": event_id, "type": "event_update"}
                            }
                            # Push notification gönder (async)
                            import httpx
                            async with httpx.AsyncClient() as client:
                                await client.post(
                                    "https://exp.host/--/api/v2/push/send",
                                    json=push_message,
                                    headers={"Content-Type": "application/json"}
                                )
                    except Exception as push_err:
                        logger.warning(f"Push notification error for user {user_id}: {push_err}")
                
                logger.info(f"📬 Sent {notifications_sent} notifications for event update")
        except Exception as notif_err:
            logger.error(f"Error sending event update notifications: {notif_err}")
    
    return {
        "status": "success", 
        "message": "Etkinlik güncellendi", 
        "updated_fields": list(update_data.keys()),
        "notifications_sent": notifications_sent,
        "date_changed": date_changed,
        "location_changed": location_changed
    }


# =====================================================
# ETKİNLİK DEĞİŞİKLİK TALEBİ YÖNETİMİ (Admin)
# =====================================================

@api_router.get("/event-change-requests")
async def get_event_change_requests(
    status: str = "pending",
    current_user: dict = Depends(get_current_user)
):
    """Get all pending event change requests - Admin only"""
    user_type = current_user.get("user_type", "")
    if user_type not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    query = {}
    if status != "all":
        query["status"] = status
    
    requests = await db.event_change_requests.find(query).sort("created_at", -1).to_list(length=100)
    
    # Her talep için organizatör bilgisini ekle
    for req in requests:
        organizer = await db.users.find_one({"id": req.get("organizer_id")})
        req["organizer_name"] = organizer.get("full_name", "Bilinmiyor") if organizer else "Bilinmiyor"
        req["_id"] = str(req.get("_id", ""))
    
    return {"requests": requests, "count": len(requests)}


@api_router.post("/event-change-requests/{request_id}/approve")
async def approve_event_change_request(
    request_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Approve event change request and apply changes - Admin only"""
    user_type = current_user.get("user_type", "")
    if user_type not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Talebi bul
    change_request = await db.event_change_requests.find_one({"id": request_id})
    if not change_request:
        raise HTTPException(status_code=404, detail="Değişiklik talebi bulunamadı")
    
    if change_request.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Bu talep zaten işlenmiş")
    
    event_id = change_request.get("event_id")
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Değişiklikleri uygula
    update_data = change_request.get("requested_changes", {})
    
    # max_participants için ticket_info güncelle
    if "max_participants" in update_data:
        ticket_info = event.get("ticket_info", {})
        ticket_info["total_slots"] = update_data["max_participants"]
        update_data["ticket_info"] = ticket_info
    
    update_data["updated_at"] = datetime.utcnow().isoformat()
    
    await db.events.update_one(
        {"id": event_id},
        {"$set": update_data}
    )
    
    # Talebi güncelle
    await db.event_change_requests.update_one(
        {"id": request_id},
        {"$set": {
            "status": "approved",
            "reviewed_at": datetime.utcnow().isoformat(),
            "reviewed_by": current_user["id"]
        }}
    )
    
    # Organizatöre bildirim gönder
    organizer_id = change_request.get("organizer_id")
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": organizer_id,
        "type": "event_change_approved",
        "title": "✅ Değişiklik Onaylandı",
        "message": f"'{change_request.get('event_title')}' etkinliğindeki değişiklik talebiniz onaylandı.",
        "data": {
            "event_id": event_id,
            "event_title": change_request.get("event_title"),
            "approved_changes": list(update_data.keys())
        },
        "read": False,
        "created_at": datetime.utcnow().isoformat()
    }
    await db.notifications.insert_one(notification)
    
    # Tarih/konum değiştiyse katılımcılara bildirim gönder
    date_changed = "start_date" in update_data or "end_date" in update_data
    location_changed = "location" in update_data or "city" in update_data
    
    if date_changed or location_changed:
        # Katılımcılara bildirim
        participations = await db.event_participants.find({"event_id": event_id}).to_list(length=1000)
        participant_ids = [p.get("user_id") for p in participations if p.get("user_id")]
        
        # Organizatörü çıkar
        if organizer_id in participant_ids:
            participant_ids.remove(organizer_id)
        
        change_type = []
        if date_changed:
            change_type.append("tarih")
        if location_changed:
            change_type.append("konum")
        
        for user_id in participant_ids:
            notif = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "type": "event_update",
                "title": f"📅 Etkinlik Güncellendi: {event.get('title')}",
                "message": f"{' ve '.join(change_type).capitalize()} değişikliği yapıldı.",
                "data": {"event_id": event_id},
                "read": False,
                "created_at": datetime.utcnow().isoformat()
            }
            await db.notifications.insert_one(notif)
    
    logger.info(f"✅ Event change request {request_id} approved by {current_user['id']}")
    
    return {
        "status": "success",
        "message": "Değişiklik onaylandı ve uygulandı",
        "applied_changes": list(update_data.keys())
    }


@api_router.post("/event-change-requests/{request_id}/reject")
async def reject_event_change_request(
    request_id: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Reject event change request - Admin only"""
    user_type = current_user.get("user_type", "")
    if user_type not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    reason = data.get("reason", "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Red gerekçesi belirtmelisiniz")
    
    # Talebi bul
    change_request = await db.event_change_requests.find_one({"id": request_id})
    if not change_request:
        raise HTTPException(status_code=404, detail="Değişiklik talebi bulunamadı")
    
    if change_request.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Bu talep zaten işlenmiş")
    
    # Talebi güncelle
    await db.event_change_requests.update_one(
        {"id": request_id},
        {"$set": {
            "status": "rejected",
            "reviewed_at": datetime.utcnow().isoformat(),
            "reviewed_by": current_user["id"],
            "rejection_reason": reason
        }}
    )
    
    # Organizatöre bildirim gönder
    organizer_id = change_request.get("organizer_id")
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": organizer_id,
        "type": "event_change_rejected",
        "title": "❌ Değişiklik Reddedildi",
        "message": f"'{change_request.get('event_title')}' etkinliğindeki değişiklik talebiniz reddedildi.\n\nGerekçe: {reason}",
        "data": {
            "event_id": change_request.get("event_id"),
            "event_title": change_request.get("event_title"),
            "rejection_reason": reason
        },
        "read": False,
        "created_at": datetime.utcnow().isoformat()
    }
    await db.notifications.insert_one(notification)
    
    # Push notification
    organizer = await db.users.find_one({"id": organizer_id})
    if organizer and organizer.get("push_token"):
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://exp.host/--/api/v2/push/send",
                    json={
                        "to": organizer["push_token"],
                        "title": "❌ Değişiklik Reddedildi",
                        "body": f"'{change_request.get('event_title')}' değişiklik talebiniz reddedildi",
                        "data": {"type": "event_change_rejected"}
                    }
                )
        except Exception as e:
            logger.warning(f"Push notification error: {e}")
    
    logger.info(f"❌ Event change request {request_id} rejected by {current_user['id']}")
    
    return {
        "status": "success",
        "message": "Değişiklik talebi reddedildi"
    }


@api_router.post("/events/{event_id}/cancel")
async def cancel_event(
    event_id: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Cancel event - Only admin can cancel"""
    user_type = current_user.get("user_type", "")
    
    # Yetki kontrolü: sadece admin iptal edebilir
    if user_type not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Etkinlik iptal yetkisi sadece yöneticilerde")
    
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    if event.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Bu etkinlik zaten iptal edilmiş")
    
    reason = data.get("reason", "")
    if not reason:
        raise HTTPException(status_code=400, detail="İptal gerekçesi zorunludur")
    
    # Etkinliği iptal et
    await db.events.update_one(
        {"id": event_id},
        {"$set": {
            "status": "cancelled",
            "cancelled_at": datetime.utcnow().isoformat(),
            "cancelled_by": current_user["id"],
            "cancellation_reason": reason,
            "updated_at": datetime.utcnow().isoformat()
        }}
    )
    
    # Katılımcılara bildirim gönder
    participants = event.get("participants", [])
    for participant in participants:
        participant_id = participant.get("id") if isinstance(participant, dict) else participant
        if participant_id:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": participant_id,
                "type": "event_cancelled",
                "title": "Etkinlik İptal Edildi",
                "message": f"'{event.get('title')}' etkinliği iptal edilmiştir. Gerekçe: {reason}",
                "related_id": event_id,
                "related_type": "event",
                "read": False,
                "created_at": datetime.utcnow().isoformat()
            }
            await db.notifications.insert_one(notification)
    
    logger.info(f"❌ Event {event_id} cancelled by admin {current_user['id']}")
    
    # Etkinlik iptal log'u
    try:
        from auth_endpoints import log_user_activity
        await log_user_activity(current_user["id"], "event_cancel", "success", {
            "event_id": event_id,
            "event_title": event.get("title"),
            "reason": reason,
            "participant_count": len(participants)
        })
    except Exception as log_err:
        logger.error(f"Log error: {log_err}")
    
    return {"status": "success", "message": "Etkinlik iptal edildi"}


@api_router.get("/events/{event_id}/matches")
async def get_event_matches(event_id: str):
    """Get matches for an event (tournament)"""
    # Check if event exists
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Return matches from event data if they exist
    matches = event.get("matches", [])
    return matches

@api_router.get("/events/{event_id}/standings")
async def get_event_standings(event_id: str):
    """Get standings for an event (tournament)"""
    # Check if event exists
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Return standings from event data if they exist
    standings = event.get("standings", [])
    return standings

@api_router.post("/events/{event_id}/generate-fixture")
async def generate_event_fixture(
    event_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Generate fixture/matches for an event (tournament)"""
    # Check if event exists and user is organizer
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get participants
    participant_ids = event.get("participants", [])
    if len(participant_ids) < 2:
        raise HTTPException(status_code=400, detail="En az 2 katılımcı gerekli")
    
    # Fetch participant details
    participants = []
    for user_id in participant_ids:
        user = await db.users.find_one({"id": user_id})
        if user:
            participants.append({
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "full_name": user.get("full_name", "Unknown"),
                "email": user.get("email", ""),
            })
    
    # Generate matches based on tournament system
    tournament_system = event.get("tournament_system", "round_robin_single")
    matches = []
    
    if tournament_system in ["round_robin_single", "round_robin_double"]:
        # Simple round-robin schedule
        num_rounds = 1 if tournament_system == "round_robin_single" else 2
        for round_num in range(1, num_rounds + 1):
            for i in range(len(participants)):
                for j in range(i + 1, len(participants)):
                    match = {
                        "id": str(uuid.uuid4()),
                        "round": round_num,
                        "match_number": len(matches) + 1,
                        "player1_id": participants[i]["user_id"],
                        "player1_name": participants[i]["full_name"],
                        "player2_id": participants[j]["user_id"],
                        "player2_name": participants[j]["full_name"],
                        "status": "scheduled",
                        "winner_id": None,
                        "score": None,
                        "scheduled_time": None,
                        "completed_at": None,
                    }
                    matches.append(match)
    
    # Calculate initial standings
    standings = []
    for participant in participants:
        standings.append({
            "user_id": participant["user_id"],
            "full_name": participant["full_name"],
            "matches_played": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "points": 0,
            "goals_for": 0,
            "goals_against": 0,
            "goal_difference": 0,
        })
    
    # Update event with matches and standings
    await db.events.update_one(
        {"id": event_id},
        {
            "$set": {
                "matches": matches,
                "standings": standings,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    return {"message": "Fikstür oluşturuldu", "matches_count": len(matches)}

@api_router.get("/events/sports/with-counts")
async def get_sports_with_counts():
    """Get all sports with their event counts, sorted by count (descending)"""
    # Aggregate pipeline to count events per sport
    pipeline = [
        {"$match": {"is_active": True}},
        {"$group": {
            "_id": "$sport",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}},
        {"$project": {
            "sport": "$_id",
            "count": 1,
            "_id": 0
        }}
    ]
    
    result = await db.events.aggregate(pipeline).to_list(None)
    return result


@api_router.post("/events/search", response_model=List[Event])
async def search_events(search: SearchRequest):
    """Advanced event search"""
    query = {"is_active": True}
    
    if search.sport:
        query["sport"] = {"$regex": search.sport, "$options": "i"}
    if search.city:
        query["city"] = {"$regex": search.city, "$options": "i"}
    if search.event_type:
        query["event_type"] = search.event_type
    if search.skill_level:
        query["skill_level"] = search.skill_level
    if search.date_from:
        query["start_date"] = {"$gte": search.date_from}
    if search.date_to:
        query["end_date"] = {"$lte": search.date_to}
    
    events = await db.events.find(query).limit(50).to_list(50)
    return [Event(**event) for event in events]

# ==================== VENUE ROUTES ====================

@api_router.post("/venues", response_model=Venue)
async def create_venue(venue: VenueCreate, current_user_id: str = Depends(get_current_user)):
    """Create a new venue (requires admin approval)"""
    # Check if user is organizer, venue_owner, or admin
    user = await db.users.find_one({"id": current_user_id})
    if not user or user.get("user_type") not in ["organizer", "venue_owner", "admin"]:
        raise HTTPException(status_code=403, detail="Only organizers, venue owners, and admins can create venues")
    
    venue_dict = venue.dict()
    venue_dict["id"] = str(uuid.uuid4())
    venue_dict["created_at"] = datetime.utcnow()
    venue_dict["rating"] = 0.0
    venue_dict["review_count"] = 0
    venue_dict["is_active"] = True
    venue_dict["approved"] = False  # Requires admin approval
    venue_dict["owner_id"] = current_user_id
    
    await db.venues.insert_one(venue_dict)
    return Venue(**venue_dict)

@api_router.get("/venues")
async def get_venues(
    sport: Optional[str] = None,
    city: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """Get all approved venues with optional filters"""
    query = {"approved": True}  # Only show approved venues
    if sport:
        query["sports"] = sport
    if city:
        query["city"] = city
    
    venues = await db.venues.find(query).skip(skip).limit(limit).to_list(limit)
    
    # Remove _id field for JSON serialization
    result = []
    for venue in venues:
        venue_dict = dict(venue)
        venue_dict.pop("_id", None)
        result.append(venue_dict)
    
    return result

@api_router.get("/venues/{venue_id}", response_model=Venue)
async def get_venue(venue_id: str):
    """Get venue by ID"""
    venue = await db.venues.find_one({"id": venue_id})
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    return Venue(**venue)

# ==================== USER ROUTES ====================

@api_router.get("/users")
async def get_users(
    user_type: Optional[str] = None,
    city: Optional[str] = None,
    sport: Optional[str] = None,
    wants_to_earn: Optional[bool] = None,
    search: Optional[str] = None,
    include_all: Optional[bool] = None
):
    """Get users with optional filters (for coach/referee/player listing)"""
    try:
        # is_verified kontrolü kaldırıldı - tüm kullanıcılar listelenebilir
        query = {}
        
        if user_type:
            query["user_type"] = user_type
        if city:
            query["city"] = city
        if sport:
            if user_type == "coach":
                query["coach_profile.sports"] = sport
            elif user_type == "referee":
                query["referee_profile.sport"] = sport
            elif user_type == "player":
                query["player_profile.sports"] = sport
        if wants_to_earn is not None:
            query["wants_to_earn"] = wants_to_earn
        
        # Search by name or phone
        if search:
            query["$or"] = [
                {"full_name": {"$regex": search, "$options": "i"}},
                {"first_name": {"$regex": search, "$options": "i"}},
                {"last_name": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}},
            ]
        
        # Only return users that are coaches, referees, or players by default
        # Unless include_all is set (for admin messaging) OR wants_to_earn filter is applied
        if "user_type" not in query and not include_all and wants_to_earn is None:
            query["user_type"] = {"$in": ["coach", "referee", "player"]}
        
        users = await db.users.find(query).to_list(1000)
        
        # Get user IDs for batch review lookup
        user_ids = [u.get("id") for u in users if u.get("id")]
        
        # Batch get all reviews for these users (limited to prevent memory issues)
        all_reviews = await db.reviews.find({
            "$or": [
                {"target_user_id": {"$in": user_ids}},
                {"reviewed_user_id": {"$in": user_ids}}
            ]
        }).to_list(10000)
        
        # Group reviews by user
        reviews_by_user = {}
        for review in all_reviews:
            user_id = review.get("target_user_id") or review.get("reviewed_user_id")
            if user_id:
                if user_id not in reviews_by_user:
                    reviews_by_user[user_id] = []
                reviews_by_user[user_id].append(review)
        
        # Remove sensitive data and add ratings
        result = []
        for user in users:
            user.pop("hashed_password", None)
            user.pop("password_hash", None)
            user.pop("_id", None)
            
            # Add average rating
            user_id = user.get("id")
            user_reviews = reviews_by_user.get(user_id, [])
            if user_reviews:
                total_rating = sum(r.get("rating", 0) for r in user_reviews)
                user["average_rating"] = round(total_rating / len(user_reviews), 1)
                user["review_count"] = len(user_reviews)
            else:
                user["average_rating"] = 0
                user["review_count"] = 0
            
            result.append(user)
        
        return result
    except Exception as e:
        logging.error(f"Get users error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/users/{user_id}")
async def get_user_public(user_id: str):
    """Get single user public profile (for coach/referee detail)"""
    try:
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        
        # Remove sensitive data
        user.pop("hashed_password", None)
        user.pop("password_hash", None)
        user.pop("_id", None)
        
        # Add average rating from reviews
        reviews = await db.reviews.find({
            "$or": [
                {"target_user_id": user_id},
                {"reviewed_user_id": user_id}
            ]
        }).to_list(None)
        
        if reviews:
            total_rating = sum(r.get("rating", 0) for r in reviews)
            user["average_rating"] = round(total_rating / len(reviews), 1)
            user["review_count"] = len(reviews)
        else:
            user["average_rating"] = 0
            user["review_count"] = 0
        
        return user
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Get user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/users/batch")
async def get_users_batch(request: dict):
    """Get multiple users by IDs"""
    try:
        user_ids = request.get("user_ids", [])
        if not user_ids:
            return {"users": []}
        
        users = []
        cursor = db.users.find({"id": {"$in": user_ids}})
        async for user in cursor:
            # Remove sensitive data
            user.pop("hashed_password", None)
            user.pop("password_hash", None)
            user.pop("_id", None)
            users.append({
                "id": user.get("id"),
                "name": user.get("name", ""),
                "full_name": user.get("full_name", user.get("name", "")),
                "profile_photo": user.get("profile_photo"),
                "profile_image": user.get("profile_image"),
                "phone": user.get("phone"),
                "email": user.get("email"),
                "user_type": user.get("user_type"),
                "city": user.get("city"),
                "gender": user.get("gender"),
            })
        
        return {"users": users}
    except Exception as e:
        logging.error(f"Get users batch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/users/{user_id}")
async def update_user_profile(
    user_id: str,
    profile_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update user profile - only owner can update"""
    try:
        # Extract user ID from current_user dict
        current_user_id = current_user.get('id') if isinstance(current_user, dict) else current_user
        
        # Debug: Log user IDs with print for stdout visibility
        print(f"🔍 Update profile request:")
        print(f"   URL user_id: '{user_id}' (type: {type(user_id).__name__})")
        print(f"   Token current_user_id: '{current_user_id}' (type: {type(current_user_id).__name__})")
        print(f"   Match: {user_id == current_user_id}")
        
        # Verify user is updating their own profile
        if user_id != current_user_id:
            print(f"❌ User ID mismatch! URL: '{user_id}' vs Token: '{current_user_id}'")
            raise HTTPException(status_code=403, detail=f"Can only update own profile")
        
        # Get existing user
        existing_user = await db.users.find_one({"id": user_id})
        if not existing_user:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        
        # Remove fields that shouldn't be updated via this endpoint
        protected_fields = ["id", "email", "phone", "hashed_password", "password_hash", "_id", "created_at"]
        for field in protected_fields:
            profile_data.pop(field, None)
        
        # Add updated timestamp
        profile_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Update user
        result = await db.users.update_one(
            {"id": user_id},
            {"$set": profile_data}
        )
        
        if result.modified_count == 0:
            logging.warning(f"No changes made to user {user_id}")
        
        # Get updated user
        updated_user = await db.users.find_one({"id": user_id})
        if updated_user:
            updated_user.pop("hashed_password", None)
            updated_user.pop("password_hash", None)
            updated_user.pop("_id", None)
        
        logging.info(f"✅ User profile updated: {user_id}")
        return updated_user
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Update user profile error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== COACH ROUTES ====================

@api_router.get("/coaches")
async def get_coaches(
    sport: Optional[str] = None,
    city: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """Get all coaches with optional filters and average ratings"""
    query = {"user_type": "coach", "is_active": True}
    if sport:
        query["coach_profile.sports"] = sport
    if city:
        query["coach_profile.cities"] = city
    
    coaches = await db.users.find(query).skip(skip).limit(limit).to_list(limit)
    
    # Add average rating for each coach
    result = []
    for coach in coaches:
        coach_data = {k: v for k, v in coach.items() if k != "hashed_password"}
        
        # Get reviews for this coach
        reviews = await db.reviews.find({
            "$or": [
                {"target_user_id": coach.get("id")},
                {"reviewed_user_id": coach.get("id")}
            ]
        }).to_list(None)
        
        if reviews:
            total_rating = sum(r.get("rating", 0) for r in reviews)
            coach_data["average_rating"] = round(total_rating / len(reviews), 1)
            coach_data["review_count"] = len(reviews)
        else:
            coach_data["average_rating"] = 0
            coach_data["review_count"] = 0
        
        result.append(coach_data)
    
    return result

# ==================== PARTICIPATION ROUTES ====================

class JoinEventRequest(BaseModel):
    category: Optional[str] = None  # 'team', 'single', 'double', etc.
    team_id: Optional[str] = None  # Takım ID'si
    teamId: Optional[str] = None  # Frontend camelCase format
    partner_id: Optional[str] = None
    game_types: Optional[List[str]] = None  # Seçilen oyun türleri
    gameTypes: Optional[List[str]] = None  # Frontend camelCase format

@api_router.post("/events/{event_id}/join")
async def join_event(
    event_id: str,
    request: JoinEventRequest = None,
    current_user_id: str = Depends(get_current_user)
):
    """Join an event and create ticket"""
    # ✅ CRITICAL: current_user_id dict olabilir, extract et
    if isinstance(current_user_id, dict):
        actual_user_id = current_user_id.get("id")
    else:
        actual_user_id = current_user_id
    
    # Get event
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Check registration deadline
    registration_deadline = event.get("registration_deadline")
    if registration_deadline:
        from dateutil import parser
        try:
            deadline = parser.parse(registration_deadline) if isinstance(registration_deadline, str) else registration_deadline
            if datetime.utcnow() > deadline:
                raise HTTPException(
                    status_code=400, 
                    detail="Son katılım tarihi geçti. Düzenleyici ile iletişime geçin."
                )
        except Exception as e:
            logging.warning(f"Could not parse registration_deadline: {e}")
    
    # Check if already joined - use actual_user_id
    existing = await db.participations.find_one({
        "event_id": event_id,
        "user_id": actual_user_id
    })
    if existing:
        raise HTTPException(status_code=400, detail="Bu etkinliğe zaten katıldınız")
    
    # Check availability
    ticket_info = event.get("ticket_info")
    max_participants = event.get("max_participants", 0)
    current_participants = len(event.get("participants", []))
    
    # Check if event is full based on ticket_info or max_participants
    if ticket_info:
        total_slots = ticket_info.get("total_slots", 0)
        available_slots = ticket_info.get("available_slots", 0)
        # If total_slots > 0, check available_slots
        if total_slots > 0 and available_slots <= 0:
            raise HTTPException(status_code=400, detail="Event is full - no tickets available")
    
    # Also check max_participants if set
    if max_participants > 0 and current_participants >= max_participants:
        raise HTTPException(status_code=400, detail="Event is full - max participants reached")
    
    # Determine the price based on category
    category = request.category if request else None
    ticket_id = None
    payment_result = None
    actual_price = 0.0
    
    if ticket_info:
        prices = ticket_info.get("prices", {})
        base_price = ticket_info.get("price", 0)
        
        # Get price based on category
        if category and category in prices:
            actual_price = prices[category]
        elif prices:
            # If no category specified but prices exist, use first available
            actual_price = list(prices.values())[0] if prices else base_price
        else:
            actual_price = base_price
        
        # If price > 0, require payment
        if actual_price > 0:
            return {
                "status": "payment_required",
                "message": "Ödeme gerekli",
                "payment_info": {
                    "event_id": event_id,
                    "category": category,
                    "price": actual_price,
                    "currency": ticket_info.get("currency", "TRY"),
                    "event_title": event.get("title"),
                }
            }
        
        # Default to stripe for payment (will be configured with actual keys)
        payment_provider = PaymentProvider.STRIPE
        
        # Create payment
        metadata = {
            "event_id": event_id,
            "user_id": actual_user_id
        }
        
        if payment_provider == PaymentProvider.STRIPE:
            payment_result = await payment_service.create_payment_intent_stripe(
                ticket_info["price"],
                ticket_info.get("currency", "TRY"),
                metadata
            )
        elif payment_provider == PaymentProvider.IYZICO:
            user = await db.users.find_one({"id": actual_user_id})
            payment_result = await payment_service.create_payment_iyzico(
                ticket_info["price"],
                ticket_info.get("currency", "TRY"),
                {"email": user["email"], "name": user["full_name"]},
                metadata
            )
        elif payment_provider == PaymentProvider.VAKIFBANK:
            payment_result = await payment_service.create_payment_vakifbank(
                ticket_info["price"],
                ticket_info.get("currency", "TRY"),
                {},
                metadata
            )
        
        # Create ticket
        ticket_dict = {
            "id": str(uuid.uuid4()),
            "ticket_number": f"TK-{str(uuid.uuid4())[:8].upper()}",
            "event_id": event_id,
            "user_id": actual_user_id,
            "price": ticket_info["price"],
            "currency": ticket_info.get("currency", "TRY"),
            "payment_provider": payment_provider,
            "purchased_at": datetime.utcnow(),
            "payment_status": "pending",
            "payment_id": payment_result.get("payment_id") if payment_result else None
        }
        await db.tickets.insert_one(ticket_dict)
        ticket_id = ticket_dict["id"]
        
        # Update available slots
        await db.events.update_one(
            {"id": event_id},
            {"$inc": {"ticket_info.available_slots": -1}}
        )
    
    # Takım bilgisini işle (hem snake_case hem camelCase kabul et)
    team_id = None
    if request:
        team_id = request.team_id or request.teamId
        
        # Eğer takım ID varsa kullanıcıyı takıma ekle
        if team_id:
            team = await db.event_teams.find_one({"id": team_id, "event_id": event_id})
            if team:
                if actual_user_id not in team.get("member_ids", []):
                    await db.event_teams.update_one(
                        {"id": team_id},
                        {"$addToSet": {"member_ids": actual_user_id}}
                    )
                    logging.info(f"✅ User {actual_user_id} added to team {team_id}")
    
    # Seçilen oyun türlerini al
    game_types = []
    if request:
        game_types = request.game_types or request.gameTypes or []
    
    # Create participation
    participation_dict = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "user_id": actual_user_id,
        "ticket_id": ticket_id,
        "team_id": team_id,
        "game_types": game_types,
        "payment_status": "pending" if ticket_info else "not_required",
        "payment_provider": payment_provider.value if ticket_info else None,
        "joined_at": datetime.utcnow()
    }
    await db.participations.insert_one(participation_dict)
    
    # Update participant count AND add user to participants array
    await db.events.update_one(
        {"id": event_id},
        {
            "$inc": {"participant_count": 1},
            "$addToSet": {"participants": actual_user_id}  # Add user to participants array
        }
    )
    
    # Add user to event group chat
    group_chat = await db.group_chats.find_one({"event_id": event_id})
    if group_chat:
        await db.group_chats.update_one(
            {"id": group_chat["id"]},
            {"$addToSet": {"member_ids": actual_user_id}}
        )
        logging.info(f"User {actual_user_id} added to group chat {group_chat['id']}")
    
    # Create notifications and calendar items
    try:
        participant = await db.users.find_one({"id": actual_user_id})
        participant_name = participant.get("full_name", "Bir kullanıcı") if participant else "Bir kullanıcı"
        event_title = event.get("title", "Etkinlik")
        organizer_id = event.get("organizer_id")
        
        # Notification to participant (joined user)
        await create_notification(
            user_id=actual_user_id,
            notification_type=NotificationType.EVENT_JOINED,
            title="Etkinliğe Katıldınız",
            message=f"'{event_title}' etkinliğine başarıyla katıldınız",
            related_id=event_id,
            related_type=NotificationRelatedType.EVENT
        )
        
        # Calendar item for participant
        participant_calendar_item = {
            "id": str(uuid.uuid4()),
            "user_id": actual_user_id,
            "type": "event",
            "event_id": event_id,  # ✅ CRITICAL: Event ID ekle
            "title": event_title,
            "date": event.get("start_date"),
            "start_time": event.get("start_date"),
            "end_time": event.get("end_date"),
            "location": event.get("city", ""),
            "description": event.get("description", ""),
            "is_read": False,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        await db.calendar_items.insert_one(participant_calendar_item)
        logging.info(f"✅ Calendar item created for participant: {actual_user_id}")
        
        # Notification to organizer
        if organizer_id:
            await create_notification(
                user_id=organizer_id,
                notification_type=NotificationType.PARTICIPANT_JOINED,
                title="Yeni Katılımcı",
                message=f"{participant_name} '{event_title}' etkinliğinize katıldı",
                related_id=event_id,
                related_type=NotificationRelatedType.EVENT
            )
            
            # ✅ Calendar item for organizer - SADECE bir kez oluşturulmalı (etkinlik için)
            # Her katılımcı için ayrı calendar item oluşturMA, sadece henüz yoksa oluştur
            existing_organizer_calendar = await db.calendar_items.find_one({
                "user_id": organizer_id,
                "event_id": event_id,
                "type": "event"
            })
            
            if not existing_organizer_calendar:
                organizer_calendar_item = {
                    "id": str(uuid.uuid4()),
                    "user_id": organizer_id,
                    "type": "event",
                    "event_id": event_id,
                    "title": f"{event_title} (Organizatör)",
                    "date": event.get("start_date"),
                    "start_time": event.get("start_date"),
                    "end_time": event.get("end_date"),
                    "location": event.get("city", ""),
                    "description": event.get("description", ""),
                    "is_read": False,
                    "created_at": datetime.utcnow().isoformat() + "Z"
                }
                await db.calendar_items.insert_one(organizer_calendar_item)
                logging.info(f"✅ Calendar item created for organizer: {organizer_id}")
    except Exception as e:
        logging.error(f"Error creating participant notification/calendar: {str(e)}")
    
    # ✅ CRITICAL: Add user to group chat
    try:
        group_chat = await db.group_chats.find_one({"event_id": event_id})
        if group_chat:
            # Check if user is already a member
            member_ids = group_chat.get("member_ids", [])
            if actual_user_id not in member_ids:
                member_ids.append(actual_user_id)
                await db.group_chats.update_one(
                    {"event_id": event_id},
                    {"$set": {"member_ids": member_ids}}
                )
                logging.info(f"✅ User {actual_user_id} added to group chat for event {event_id}")
        else:
            logging.warning(f"⚠️ No group chat found for event {event_id}")
    except Exception as e:
        logging.error(f"Error adding user to group chat: {str(e)}")
    
    # Etkinliğe katılma log'u
    try:
        from auth_endpoints import log_user_activity
        await log_user_activity(actual_user_id, "event_join", "success", {
            "event_id": event_id,
            "event_title": event.get("title"),
            "event_type": event.get("event_type"),
            "category": category,
            "price": actual_price,
            "team_id": team_id
        })
    except Exception as e:
        logging.error(f"Error logging event join: {str(e)}")
    
    return {
        "message": "Successfully joined event",
        "participation_id": participation_dict["id"],
        "ticket_id": ticket_id,
        "payment_info": payment_result
    }

class EventPaymentRequest(BaseModel):
    event_id: str
    selected_game_types: List[str] = []
    total_price: float
    category: Optional[str] = None

@api_router.post("/events/initialize-payment")
async def initialize_event_payment(
    request: EventPaymentRequest,
    current_user: dict = Depends(get_current_user)
):
    """Initialize payment for event registration"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    # Get event
    event = await db.events.find_one({"id": request.event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Get user info
    user = await db.users.find_one({"id": current_user_id})
    if not user:
        raise HTTPException(status_code=404, detail=f"Kullanıcı bulunamadı: {current_user_id}")
    
    # Calculate price from ticket_info
    ticket_info = event.get("ticket_info", {})
    prices = ticket_info.get("prices", {})
    base_price = ticket_info.get("price", 0)
    
    # Calculate total based on selected game types
    calculated_price = 0.0
    if request.selected_game_types:
        for game_type in request.selected_game_types:
            if game_type == 'open':
                calculated_price += prices.get('open', base_price)
            elif game_type == 'tek':
                calculated_price += prices.get('single', base_price)
            elif game_type == 'cift':
                calculated_price += prices.get('double', base_price)
            elif game_type == 'karisik_cift':
                calculated_price += prices.get('mixed_double', base_price)
            elif game_type == 'takim':
                calculated_price += prices.get('team', base_price)
    else:
        # Use provided total_price or base_price
        calculated_price = request.total_price if request.total_price > 0 else base_price
    
    # Use the higher of calculated or provided price
    final_price = max(calculated_price, request.total_price)
    
    if final_price <= 0:
        raise HTTPException(status_code=400, detail="Bu etkinlik ücretsizdir")
    
    # Create payment record
    currency = ticket_info.get("currency", "TRY")
    
    # Önce geçici event_participants kaydı oluştur (ödeme bekliyor)
    participation_id = str(uuid.uuid4())
    
    # Ödeme kaydı oluştur
    payment_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    
    payment = {
        "id": payment_id,
        "user_id": current_user_id,
        "related_type": "event",
        "related_id": request.event_id,
        "event_id": request.event_id,  # Callback için ek alan
        "participation_id": participation_id,  # Callback'de güncellemek için
        "amount": final_price,
        "currency": currency,
        "status": PaymentStatus.PENDING.value,
        "selected_game_types": request.selected_game_types,
        "iyzico_conversation_id": conversation_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    await db.payments.insert_one(payment)
    
    # Event participants kaydı
    participation = {
        "id": participation_id,
        "event_id": request.event_id,
        "user_id": current_user_id,
        "status": "payment_pending",
        "payment_status": "pending",
        "payment_id": payment_id,
        "role": "participant",
        "game_types": request.selected_game_types,
        "price": final_price,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    await db.event_participants.insert_one(participation)
    logging.info(f"✅ Temporary participation created: {participation_id} for payment: {payment_id}")
    
    # Initialize iyzico payment
    try:
        result = iyzico_service.initialize_checkout_form(
            user={
                "id": current_user_id,
                "email": user.get("email", f"{current_user_id}@sportsmaker.app"),
                "full_name": user.get("full_name", "Kullanıcı"),
                "phone_number": user.get("phone", "+905000000000"),
                "city": user.get("city", "Istanbul"),
                "address": user.get("address", "Istanbul, Turkey"),
            },
            amount=final_price,
            related_type="event",
            related_id=request.event_id,
            related_name=event.get("title", "Etkinlik Katılımı"),
            callback_url=f"https://tourneys-portal.preview.emergentagent.com/api/payments/callback?payment_id={payment_id}"
        )
        
        if result.get("status") == "success":
            # Update payment with iyzico token
            await db.payments.update_one(
                {"id": payment_id},
                {"$set": {"iyzico_token": result.get("token")}}
            )
            
            return {
                "payment_id": payment_id,
                "payment_page_url": result.get("paymentPageUrl"),
                "token": result.get("token"),
                "amount": final_price,
                "currency": currency
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("errorMessage", "Ödeme başlatılamadı"))
    except ValueError as e:
        logging.error(f"Payment validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Payment initialization error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ödeme servisi hatası: {str(e)}")

# ================== ETKİNLİK TAKIM SİSTEMİ ==================

@api_router.get("/events/{event_id}/teams")
async def get_event_teams(event_id: str, current_user: dict = Depends(get_current_user)):
    """Etkinliğe kayıtlı takımları getir"""
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    teams = await db.event_teams.find({"event_id": event_id}).to_list(100)
    
    # Takım üyelerinin bilgilerini ekle
    for team in teams:
        team.pop("_id", None)
        member_ids = team.get("member_ids", [])
        members = []
        for mid in member_ids:
            u = await db.users.find_one({"id": mid})
            if u:
                members.append({
                    "id": u.get("id"),
                    "full_name": u.get("full_name"),
                    "profile_image": u.get("profile_image")
                })
        team["members"] = members
    
    return {"teams": teams}

@api_router.post("/events/{event_id}/teams/create-auto")
async def create_auto_team(
    event_id: str,
    request: dict,
    current_user: dict = Depends(get_current_user)
):
    """Otomatik takım oluştur (kullanıcı adıyla)"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    user = await db.users.find_one({"id": current_user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    team_name = request.get("team_name") or f"{user.get('full_name', 'Kullanıcı')} Takımı"
    
    # Zaten bu etkinlikte takım var mı kontrol et
    existing = await db.event_teams.find_one({
        "event_id": event_id,
        "creator_id": current_user_id
    })
    
    if existing:
        existing.pop("_id", None)
        return {"team": existing, "message": "Mevcut takımınız"}
    
    team = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "name": team_name,
        "creator_id": current_user_id,
        "member_ids": [current_user_id],
        "max_members": event.get("team_size", 2),
        "status": "open",  # open = yeni üye alabilir
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.event_teams.insert_one(team)
    team.pop("_id", None)
    
    return {"team": team, "message": "Takım oluşturuldu"}

@api_router.post("/events/{event_id}/teams/{team_id}/join")
async def request_join_team(
    event_id: str,
    team_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Takıma katılma talebi gönder (onay gerektirir)"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    team = await db.event_teams.find_one({"id": team_id, "event_id": event_id})
    if not team:
        raise HTTPException(status_code=404, detail="Takım bulunamadı")
    
    user = await db.users.find_one({"id": current_user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Zaten üye mi kontrol et
    if current_user_id in team.get("member_ids", []):
        raise HTTPException(status_code=400, detail="Zaten bu takımın üyesisiniz")
    
    # Takım dolu mu kontrol et
    max_members = team.get("max_members", 2)
    if len(team.get("member_ids", [])) >= max_members:
        raise HTTPException(status_code=400, detail="Takım dolu")
    
    # Daha önce talep gönderilmiş mi kontrol et
    existing_request = await db.team_join_requests.find_one({
        "team_id": team_id,
        "requester_id": current_user_id,
        "status": "pending"
    })
    
    if existing_request:
        raise HTTPException(status_code=400, detail="Bu takıma zaten bekleyen bir talebiniz var")
    
    # Takım sahibini bul
    creator_id = team.get("creator_id")
    creator = await db.users.find_one({"id": creator_id})
    
    # Talep oluştur
    request_id = str(uuid.uuid4())
    join_request = {
        "id": request_id,
        "event_id": event_id,
        "team_id": team_id,
        "team_name": team.get("name"),
        "requester_id": current_user_id,
        "requester_name": user.get("full_name"),
        "creator_id": creator_id,
        "status": "pending",  # pending, accepted, rejected
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.team_join_requests.insert_one(join_request)
    
    # Takım sahibine bildirim gönder
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": creator_id,
        "type": "team_join_request",
        "title": "🤝 Takım Katılma Talebi",
        "message": f"{user.get('full_name', 'Bir kullanıcı')} '{team.get('name')}' takımınıza katılmak istiyor",
        "data": {
            "request_id": request_id,
            "event_id": event_id,
            "team_id": team_id,
            "requester_id": current_user_id,
            "requester_name": user.get("full_name"),
            "requester_image": user.get("profile_image")
        },
        "is_read": False,
        "created_at": datetime.utcnow()
    }
    await db.notifications.insert_one(notification)
    
    return {
        "success": True,
        "request_id": request_id,
        "message": f"'{team.get('name')}' takımına katılma talebiniz gönderildi. Takım sahibinin onayı bekleniyor."
    }

@api_router.post("/events/{event_id}/teams/{team_id}/respond")
async def respond_team_join_request(
    event_id: str,
    team_id: str,
    request: dict,
    current_user: dict = Depends(get_current_user)
):
    """Takım katılma talebini onayla veya reddet"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    request_id = request.get("request_id")
    action = request.get("action")  # "accept" veya "reject"
    
    if not request_id or action not in ["accept", "reject"]:
        raise HTTPException(status_code=400, detail="Geçersiz istek parametreleri")
    
    # Talebi bul
    join_request = await db.team_join_requests.find_one({"id": request_id})
    if not join_request:
        raise HTTPException(status_code=404, detail="Talep bulunamadı")
    
    # Takımı bul
    team = await db.event_teams.find_one({"id": team_id, "event_id": event_id})
    if not team:
        raise HTTPException(status_code=404, detail="Takım bulunamadı")
    
    # Sadece takım sahibi cevap verebilir
    if team.get("creator_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Sadece takım sahibi taleplere cevap verebilir")
    
    # Zaten cevaplanmış mı kontrol et
    if join_request.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Bu talep zaten cevaplanmış")
    
    requester_id = join_request.get("requester_id")
    requester = await db.users.find_one({"id": requester_id})
    creator = await db.users.find_one({"id": current_user_id})
    
    if action == "accept":
        # Takım hala dolu değilse kabul et
        max_members = team.get("max_members", 2)
        if len(team.get("member_ids", [])) >= max_members:
            raise HTTPException(status_code=400, detail="Takım artık dolu")
        
        # Talebi onayla
        await db.team_join_requests.update_one(
            {"id": request_id},
            {"$set": {"status": "accepted", "responded_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
        )
        
        # Takıma ekle
        creator_name = creator.get("full_name", "Takım") if creator else "Takım"
        new_name = f"{creator_name} & {requester.get('full_name', 'Üye')}"
        
        await db.event_teams.update_one(
            {"id": team_id},
            {
                "$push": {"member_ids": requester_id},
                "$set": {
                    "name": new_name,
                    "status": "full" if len(team.get("member_ids", [])) + 1 >= max_members else "open",
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Talep sahibine bildirim gönder
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": requester_id,
            "type": "team_join_accepted",
            "title": "✅ Takım Talebi Kabul Edildi",
            "message": f"{creator.get('full_name', 'Takım sahibi')} takıma katılma talebinizi kabul etti. Artık '{new_name}' takımının üyesisiniz!",
            "data": {
                "event_id": event_id,
                "team_id": team_id,
                "team_name": new_name
            },
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
        
        updated_team = await db.event_teams.find_one({"id": team_id})
        updated_team.pop("_id", None)
        
        return {"success": True, "team": updated_team, "message": f"Talep kabul edildi. {requester.get('full_name')} artık takımda."}
    
    else:  # reject
        # Talebi reddet
        await db.team_join_requests.update_one(
            {"id": request_id},
            {"$set": {"status": "rejected", "responded_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
        )
        
        # Talep sahibine bildirim gönder
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": requester_id,
            "type": "team_join_rejected",
            "title": "❌ Takım Talebi Reddedildi",
            "message": f"{creator.get('full_name', 'Takım sahibi')} '{team.get('name')}' takımına katılma talebinizi reddetti.",
            "data": {
                "event_id": event_id,
                "team_id": team_id,
                "team_name": team.get("name")
            },
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
        
        return {"success": True, "message": "Talep reddedildi."}

@api_router.get("/events/{event_id}/teams/{team_id}/pending-requests")
async def get_pending_team_requests(
    event_id: str,
    team_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Takım için bekleyen katılma taleplerini getir"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    team = await db.event_teams.find_one({"id": team_id, "event_id": event_id})
    if not team:
        raise HTTPException(status_code=404, detail="Takım bulunamadı")
    
    # Sadece takım sahibi talepleri görebilir
    if team.get("creator_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Sadece takım sahibi talepleri görebilir")
    
    requests = await db.team_join_requests.find({
        "team_id": team_id,
        "status": "pending"
    }).to_list(50)
    
    # Talep sahiplerinin bilgilerini ekle
    for req in requests:
        req.pop("_id", None)
        requester = await db.users.find_one({"id": req.get("requester_id")})
        if requester:
            req["requester"] = {
                "id": requester.get("id"),
                "full_name": requester.get("full_name"),
                "profile_image": requester.get("profile_image"),
                "city": requester.get("city")
            }
    
    return {"requests": requests}

@api_router.get("/users/my-team-requests")
async def get_my_team_requests(
    current_user: dict = Depends(get_current_user)
):
    """Kullanıcının gönderdiği takım taleplerini getir"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    requests = await db.team_join_requests.find({
        "requester_id": current_user_id
    }).sort("created_at", -1).to_list(50)
    
    for req in requests:
        req.pop("_id", None)
    
    return {"requests": requests}

@api_router.get("/events/{event_id}/participants")
async def get_event_participants(event_id: str, current_user_id: str = Depends(get_current_user)):
    """Get all participants of an event with their basic info"""
    # Check if event exists
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # ÖNCE event_participants collection'dan al (birincil kaynak)
    event_participant_records = await db.event_participants.find({"event_id": event_id}).to_list(1000)
    
    # Eğer event_participants'ta kayıt yoksa, event.participants array'inden al (geriye uyumluluk)
    participant_ids = []
    
    if event_participant_records:
        # event_participants collection'dan user_id'leri al
        participant_ids = [p.get("user_id") for p in event_participant_records if p.get("user_id")]
    else:
        # Fallback: event.participants array'inden al
        participant_data = event.get("participants", [])
        for p in participant_data:
            if isinstance(p, str):
                participant_ids.append(p)
            elif isinstance(p, dict) and p.get("id"):
                participant_ids.append(p.get("id"))
    
    participants_list = []
    for user_id in participant_ids:
        if user_id:
            user = await db.users.find_one({"id": user_id})
            if user:
                # Get player profile for additional info
                player_profile = await db.player_profiles.find_one({"user_id": user_id})
                
                # Try to get participation date from participations collection
                participation = await db.participations.find_one({"event_id": event_id, "user_id": user_id})
                # Also check event_participants
                if not participation:
                    participation = await db.event_participants.find_one({"event_id": event_id, "user_id": user_id})
                
                participants_list.append({
                    "id": user.get("id"),
                    "full_name": user.get("full_name"),
                    "avatar": user.get("avatar"),
                    "profile_image": user.get("profile_image"),
                    "city": user.get("city"),
                    "gender": user.get("gender"),
                    "date_of_birth": user.get("date_of_birth") or user.get("birth_date"),
                    "rating": user.get("rating", 0),
                    "sports": user.get("sports", []) or (player_profile.get("sports", []) if player_profile else []),
                    "participation_date": participation.get("created_at") if participation else None
                })
    
    return {
        "event_id": event_id,
        "event_name": event.get("title"),
        "total_participants": len(participants_list),
        "participants": participants_list
    }

@api_router.get("/my-events", response_model=List[Event])
async def get_my_events(current_user_id: str = Depends(get_current_user)):
    """Get events user has joined or is organizer of"""
    # Katılımcı olduğu etkinlikler
    participations = await db.participations.find({"user_id": current_user_id}).to_list(1000)
    event_ids = [p["event_id"] for p in participations]
    
    # Organizatör, yönetici veya asistan olduğu etkinlikler
    organizer_events = await db.events.find({
        "$or": [
            {"organizer_id": current_user_id},
            {"created_by": current_user_id},
            {"organizers": current_user_id},
            {"managers": current_user_id},
            {"assistants": current_user_id}
        ]
    }).to_list(1000)
    
    organizer_event_ids = [e["id"] for e in organizer_events]
    
    # Tüm event ID'lerini birleştir (unique)
    all_event_ids = list(set(event_ids + organizer_event_ids))
    
    events = await db.events.find({"id": {"$in": all_event_ids}}).to_list(1000)
    return [Event(**event) for event in events]

@api_router.get("/my-tickets")
async def get_my_tickets(current_user_id: str = Depends(get_current_user)):
    """Get user's tickets"""
    tickets = await db.tickets.find({"user_id": current_user_id}).to_list(1000)
    # Convert MongoDB documents to JSON-serializable format
    serialized_tickets = []
    for ticket in tickets:
        # Remove MongoDB ObjectId fields and convert to dict
        ticket_dict = {k: v for k, v in ticket.items() if k != "_id"}
        serialized_tickets.append(ticket_dict)
    return serialized_tickets


# ==================== TOURNAMENT SETTINGS ENDPOINTS ====================

@api_router.post("/events/{event_id}/tournament-settings")
async def create_tournament_settings(
    event_id: str,
    settings: dict,
    current_user_id: str = Depends(get_current_user)
):
    """Create or update tournament settings for an event"""
    try:
        # Verify event exists
        event = await db.events.find_one({"id": event_id})
        if not event:
            raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
        
        # TODO: Production'da yetkilendirme kontrolü eklenecek
        # Şimdilik herkes ayar yapabilir (geliştirme aşaması)
        
        # Check if settings already exist
        existing_settings = await db.event_tournament_settings.find_one({"event_id": event_id})
        
        settings_id = existing_settings["id"] if existing_settings else str(uuid.uuid4())
        
        tournament_settings = {
            "id": settings_id,
            "event_id": event_id,
            "groups": settings.get("groups", []),
            "general_settings": {
                "total_courts": settings.get("general_settings", {}).get("total_courts", 4),
                "match_duration": settings.get("general_settings", {}).get("match_duration", 30),
                "break_duration": settings.get("general_settings", {}).get("break_duration", 5),
                "start_datetime": settings.get("general_settings", {}).get("start_datetime"),
                "end_datetime": settings.get("general_settings", {}).get("end_datetime")
            },
            "created_at": existing_settings.get("created_at") if existing_settings else datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        if existing_settings:
            # Update existing
            await db.event_tournament_settings.update_one(
                {"event_id": event_id},
                {"$set": tournament_settings}
            )
            logging.info(f"✅ Tournament settings updated for event {event_id}")
        else:
            # Create new
            await db.event_tournament_settings.insert_one(tournament_settings)
            logging.info(f"✅ Tournament settings created for event {event_id}")
        
        tournament_settings.pop("_id", None)
        return {
            "success": True,
            "message": "Turnuva ayarları kaydedildi",
            "settings": tournament_settings
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error creating tournament settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Turnuva ayarları kaydedilemedi: {str(e)}")


@api_router.get("/events/{event_id}/tournament-settings")
async def get_tournament_settings(event_id: str):
    """Get tournament settings for an event"""
    try:
        settings = await db.event_tournament_settings.find_one({"event_id": event_id})
        
        if not settings:
            # Return default settings
            return {
                "success": True,
                "settings": None,
                "message": "Henüz turnuva ayarları yapılmamış"
            }
        
        settings.pop("_id", None)
        return {
            "success": True,
            "settings": settings
        }
        
    except Exception as e:
        logging.error(f"Error fetching tournament settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Turnuva ayarları alınamadı: {str(e)}")


@api_router.delete("/events/{event_id}/tournament-settings")
async def delete_tournament_settings(
    event_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Delete tournament settings for an event"""
    try:
        # Verify event exists and user is organizer
        event = await db.events.find_one({"id": event_id})
        if not event:
            raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
        
        # Admin veya etkinlik sahibi silme yetkisine sahip
        user = await db.users.find_one({"id": current_user_id})
        is_admin = user and user.get("user_type") in ["admin", "super_admin"]
        
        if not is_admin and event.get("organizer_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Bu etkinliği sadece düzenleyen kullanıcı silebilir")
        
        result = await db.event_tournament_settings.delete_one({"event_id": event_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Silinecek turnuva ayarları bulunamadı")
        
        return {
            "success": True,
            "message": "Turnuva ayarları silindi"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting tournament settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Turnuva ayarları silinemedi: {str(e)}")



@api_router.get("/statistics/{user_id}")
async def get_user_statistics(user_id: str):
    """Get user statistics"""
    # Get all match results for user
    match_results = await db.match_results.find({
        "$or": [
            {"player1_id": user_id},
            {"player2_id": user_id}
        ],
        "status": {"$in": ["approved", "admin_approved"]}
    }).to_list(1000)
    
    stats = {
        "matches_played": len(match_results),
        "wins": len([m for m in match_results if m.get("winner_id") == user_id]),
        "losses": len([m for m in match_results if m.get("winner_id") != user_id and m.get("winner_id")]),
        "points": 0,
        "ranking": 0,
        "win_rate": 0.0,
        "sports": {}
    }
    
    stats["points"] = stats["wins"] * 3 + (stats["matches_played"] - stats["wins"] - stats["losses"])
    if stats["matches_played"] > 0:
        stats["win_rate"] = (stats["wins"] / stats["matches_played"]) * 100
    
    # Group by sports
    for match in match_results:
        sport = match.get("sport", "Unknown")
        if sport not in stats["sports"]:
            stats["sports"][sport] = {"played": 0, "wins": 0, "losses": 0}
        
        stats["sports"][sport]["played"] += 1
        if match.get("winner_id") == user_id:
            stats["sports"][sport]["wins"] += 1
        elif match.get("winner_id"):
            stats["sports"][sport]["losses"] += 1
    
    # Get ranking
    all_stats = await db.rankings.find({"user_id": user_id}).to_list(1000)
    if all_stats:
        stats["ranking"] = all_stats[0].get("rank", 0)
    
    return stats

@api_router.get("/users/{user_id}/profile")
async def get_user_profile(user_id: str, current_user_id: str = Depends(get_current_user)):
    """Get detailed user profile including sports, rankings, and achievements"""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Get player profile
    player_profile = await db.player_profiles.find_one({"user_id": user_id})
    
    # Get user's rankings (if any)
    rankings = await db.rankings.find({"user_id": user_id}).to_list(None)
    
    # Get user's achievements (if any)
    achievements = await db.achievements.find({"user_id": user_id}).to_list(None)
    
    return {
        "id": user.get("id"),
        "full_name": user.get("full_name"),
        "avatar": user.get("avatar"),
        "city": user.get("city"),
        "gender": user.get("gender"),
        "birth_date": user.get("birth_date"),
        "phone_number": user.get("phone_number"),
        "bio": user.get("bio"),
        "sports": player_profile.get("sports", []) if player_profile else [],
        "skill_levels": player_profile.get("skill_levels", []) if player_profile else [],
        "rankings": rankings,
        "achievements": achievements,
        "created_at": user.get("created_at")
    }

# ==================== REVIEW/RATING ROUTES ====================

@api_router.post("/reviews", response_model=Review)
async def create_review(review: ReviewBase, current_user_id: str = Depends(get_current_user)):
    """Create a review for user, venue, or event"""
    review_dict = review.dict()
    review_dict["id"] = str(uuid.uuid4())
    review_dict["reviewer_id"] = current_user_id
    review_dict["created_at"] = datetime.utcnow()
    
    await db.reviews.insert_one(review_dict)
    
    # Update average rating
    target_type = review.target_type
    target_id = review.target_id
    
    reviews = await db.reviews.find({
        "target_id": target_id,
        "target_type": target_type
    }).to_list(1000)
    
    avg_rating = sum(r["rating"] for r in reviews) / len(reviews)
    
    if target_type == "venue":
        await db.venues.update_one(
            {"id": target_id},
            {"$set": {"rating": avg_rating, "review_count": len(reviews)}}
        )
    elif target_type == "user":
        await db.users.update_one(
            {"id": target_id},
            {"$set": {"coach_profile.rating": avg_rating, "coach_profile.review_count": len(reviews)}}
        )
    
    return Review(**review_dict)

@api_router.get("/reviews/target/{target_type}/{target_id}", response_model=List[Review])
async def get_reviews(target_type: str, target_id: str):
    """Get reviews for a target"""
    reviews = await db.reviews.find({
        "target_type": target_type,
        "target_id": target_id
    }).to_list(1000)
    return [Review(**review) for review in reviews]

# ==================== MESSAGE ROUTES ====================

@api_router.get("/messages")
async def get_messages(current_user: dict = Depends(get_current_user)):
    """Get all messages for current user (excluding hidden conversations)"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    print(f"📩 GET /messages called for user: {current_user_id}")
    messages = await db.messages.find({
        "$and": [
            {
                "$or": [
                    {"sender_id": current_user_id},
                    {"receiver_id": current_user_id}
                ]
            },
            {
                "$or": [
                    {"deleted_for": {"$exists": False}},
                    {"deleted_for": {"$nin": [current_user_id]}}
                ]
            }
        ]
    }).sort("sent_at", -1).to_list(1000)
    print(f"📩 Returning {len(messages)} messages")
    
    # Fix sender_id and receiver_id if they are dicts
    for msg in messages:
        if isinstance(msg.get('sender_id'), dict):
            msg['sender_id'] = msg['sender_id'].get('id')
        if isinstance(msg.get('receiver_id'), dict):
            msg['receiver_id'] = msg['receiver_id'].get('id')
        # MongoDB _id'yi çıkar
        msg.pop('_id', None)
    
    # Pydantic validation bypass - direkt dict döndür
    return messages

@api_router.get("/messages/unread-counts")
async def get_unread_message_counts(current_user: dict = Depends(get_current_user)):
    """Get unread message counts for individual and group chats"""
    current_user_id = current_user.get("id")
    logging.info(f"🔵 Getting unread counts for user: {current_user_id}")
    
    # Individual messages - count unread messages from each sender
    pipeline = [
        {
            "$match": {
                "receiver_id": current_user_id,
                "is_read": False
            }
        },
        {
            "$group": {
                "_id": "$sender_id",
                "count": {"$sum": 1}
            }
        }
    ]
    
    individual_unread = await db.messages.aggregate(pipeline).to_list(None)
    total_individual = sum(item["count"] for item in individual_unread)
    
    logging.info(f"🔵 Individual unread messages: {total_individual}")
    logging.info(f"🔵 Individual unread breakdown: {individual_unread}")
    
    # Group messages - count unread messages in all groups user is member of
    user_groups = await db.group_chats.find({
        "member_ids": current_user_id  # Changed from members array with user_id
    }).to_list(None)
    
    logging.info(f"🔵 User is member of {len(user_groups)} groups")
    
    group_ids = [group["id"] for group in user_groups]
    
    # Count unread group messages
    group_unread_count = await db.group_messages.count_documents({
        "group_id": {"$in": group_ids},
        "sender_id": {"$ne": current_user_id},  # Not sent by me
        "read_by": {"$ne": current_user_id}  # Not read by me
    })
    
    logging.info(f"🔵 Group unread messages: {group_unread_count}")
    
    result = {
        "individual_unread": total_individual,
        "group_unread": group_unread_count,
        "total_unread": total_individual + group_unread_count
    }
    
    logging.info(f"🟢 Returning unread counts: {result}")
    
    return result

@api_router.get("/messages/conversations-with-unread")
async def get_conversations_with_unread(current_user: dict = Depends(get_current_user)):
    """Get list of conversations with unread message counts per conversation"""
    current_user_id = current_user.get("id")
    print(f"🔍 DEBUG: conversations-with-unread endpoint called for user: {current_user_id}")
    
    try:
        # Simple test first
        print(f"🔍 DEBUG: Starting conversations-with-unread processing")
        
        # Get user info for debugging
        user_info = await db.users.find_one({"id": current_user_id})
        if user_info:
            print(f"👤 DEBUG: Current user: {user_info.get('full_name', 'Unknown')} ({user_info.get('email', 'Unknown')})")
        
        # First check total messages in database
        total_messages = await db.messages.count_documents({})
        print(f"📊 DEBUG: Total messages in database: {total_messages}")
        
        # Check messages for this user
        user_messages = await db.messages.count_documents({
            "$or": [
                {"sender_id": current_user_id},
                {"receiver_id": current_user_id}
            ]
        })
        print(f"📬 DEBUG: Messages involving user {current_user_id}: {user_messages}")
        
        # Check unread messages for this user
        unread_count = await db.messages.count_documents({
            "receiver_id": current_user_id,
            "is_read": False
        })
        print(f"📨 DEBUG: Unread messages for this user: {unread_count}")
        
        # Pipeline to get unread counts per sender
        pipeline = [
            {
                "$match": {
                    "receiver_id": current_user_id,
                    "is_read": False
                }
            },
            {
                "$group": {
                    "_id": "$sender_id",
                    "unread_count": {"$sum": 1}
                }
            }
        ]
        
        print(f"🔍 DEBUG: Running aggregation pipeline")
        unread_by_sender = await db.messages.aggregate(pipeline).to_list(None)
        print(f"🔍 DEBUG: Aggregation result: {unread_by_sender}")
        
        # Convert to dictionary for easy lookup and get sender names
        unread_dict = {}
        for item in unread_by_sender:
            sender_id = item["_id"]
            count = item["unread_count"]
            unread_dict[sender_id] = count
            
            # Get sender name for debugging
            sender_info = await db.users.find_one({"id": sender_id})
            if sender_info:
                print(f"  └─ DEBUG: {count} okunmamış mesaj: {sender_info.get('full_name', 'Unknown')} ({sender_id})")
        
        print(f"✅ DEBUG: Final unread counts by sender for {current_user_id}: {unread_dict}")
        result = {"unread_by_user": unread_dict}
        print(f"✅ DEBUG: Returning result: {result}")
        
        return result
    except Exception as e:
        print(f"❌ DEBUG ERROR in conversations-with-unread: {str(e)}")
        import traceback
        traceback.print_exc()
        error_result = {"unread_by_user": {}}
        print(f"❌ DEBUG: Returning error result: {error_result}")
        return error_result

@api_router.get("/messages/{other_user_id}", response_model=List[Message])
async def get_conversation(other_user_id: str, current_user: dict = Depends(get_current_user)):
    """Get conversation between two users (excluding messages deleted by current user)"""
    current_user_id = current_user.get("id")
    
    # Silinen mesajları hariç tut
    messages = await db.messages.find({
        "$and": [
            {
                "$or": [
                    {"sender_id": current_user_id, "receiver_id": other_user_id},
                    {"sender_id": other_user_id, "receiver_id": current_user_id}
                ]
            },
            {
                "$or": [
                    {"deleted_for": {"$exists": False}},
                    {"deleted_for": {"$nin": [current_user_id]}}
                ]
            }
        ]
    }).sort("sent_at", 1).to_list(1000)
    
    # Fix sender_id and receiver_id if they are dicts
    for msg in messages:
        if isinstance(msg.get('sender_id'), dict):
            msg['sender_id'] = msg['sender_id'].get('id')
        if isinstance(msg.get('receiver_id'), dict):
            msg['receiver_id'] = msg['receiver_id'].get('id')
    
    return [Message(**msg) for msg in messages]

@api_router.put("/messages/{other_user_id}/mark-read")
async def mark_messages_as_read(other_user_id: str, current_user: dict = Depends(get_current_user)):
    """Mark all messages from a specific user as read"""
    current_user_id = current_user.get("id")
    result = await db.messages.update_many(
        {
            "sender_id": other_user_id,
            "receiver_id": current_user_id,
            "is_read": False
        },
        {
            "$set": {"is_read": True}
        }
    )
    logging.info(f"✅ Marked {result.modified_count} messages as read from {other_user_id} to {current_user_id}")
    return {"success": True, "marked_count": result.modified_count}

@api_router.delete("/messages/conversation/{other_user_id}")
async def hide_conversation(other_user_id: str, current_user: dict = Depends(get_current_user)):
    """Hide conversation for current user (soft delete - adds user to deleted_for array)"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    logging.info(f"🗑️ Attempting to hide conversation between {current_user_id} and {other_user_id}")
    
    # Add current user to deleted_for array for all messages in this conversation
    result = await db.messages.update_many(
        {
            "$or": [
                {"sender_id": current_user_id, "receiver_id": other_user_id},
                {"sender_id": other_user_id, "receiver_id": current_user_id}
            ]
        },
        {
            "$addToSet": {"deleted_for": current_user_id}
        }
    )
    
    logging.info(f"🗑️ Hidden conversation between {current_user_id} and {other_user_id} ({result.modified_count} messages)")
    return {"success": True, "hidden_count": result.modified_count}


# ==================== GROUP CHAT ROUTES ====================

@api_router.post("/group-chats", response_model=GroupChat)
async def create_group_chat(
    group_data: GroupChatCreate,
    current_user_id: str = Depends(get_current_user)
):
    """Create a new group chat"""
    import uuid
    
    group_id = str(uuid.uuid4())
    
    # Create group with creator as admin and member
    group = {
        "id": group_id,
        "name": group_data.name,
        "description": group_data.description,
        "event_id": group_data.event_id,
        "creator_id": current_user_id,
        "admin_ids": [current_user_id],
        "member_ids": [current_user_id] + (group_data.member_ids or []),
        "permission": GroupMessagePermission.EVERYONE.value,
        "invite_link": None,
        "created_at": datetime.utcnow()
    }
    
    await db.group_chats.insert_one(group)
    
    logging.info(f"Group chat created: {group_id} by {current_user_id}")
    return GroupChat(**group)

@api_router.get("/group-chats", response_model=List[GroupChat])
async def get_user_group_chats(current_user: dict = Depends(get_current_user)):
    """Get all group chats for current user"""
    current_user_id = current_user.get("id")
    
    groups = await db.group_chats.find({
        "member_ids": current_user_id
    }).to_list(100)
    
    # Fix member_ids if they contain dicts instead of strings
    for group in groups:
        member_ids = group.get('member_ids', [])
        if member_ids:
            # Check and fix ALL elements in the array, not just the first one
            group['member_ids'] = [m.get('id') if isinstance(m, dict) else m for m in member_ids]
        
        # Fix creator_id/created_by field mismatch
        if 'creator_id' not in group and 'created_by' in group:
            group['creator_id'] = group['created_by']
        elif 'creator_id' not in group:
            # Set a default if neither exists
            group['creator_id'] = group.get('member_ids', [None])[0] if group.get('member_ids') else None
        
        # Fix missing admin_ids
        if 'admin_ids' not in group:
            group['admin_ids'] = [group.get('creator_id')] if group.get('creator_id') else []
        
        # Fix missing id field (use _id as fallback)
        if 'id' not in group:
            group['id'] = str(group['_id'])
    
    return [GroupChat(**{**group, "_id": str(group["_id"])}) for group in groups]

@api_router.get("/group-chats/unread-per-group")
async def get_unread_counts_per_group(current_user: dict = Depends(get_current_user)):
    """Get unread message counts for each group the user is a member of"""
    current_user_id = current_user.get("id")
    
    # Get all groups user is member of
    user_groups = await db.group_chats.find({
        "member_ids": current_user_id
    }).to_list(None)
    
    group_ids = [group["id"] for group in user_groups]
    
    # Count unread messages per group
    unread_by_group = {}
    for group_id in group_ids:
        count = await db.group_messages.count_documents({
            "group_id": group_id,
            "sender_id": {"$ne": current_user_id},
            "read_by": {"$ne": current_user_id}
        })
        if count > 0:
            unread_by_group[group_id] = count
    
    logging.info(f"🔵 Unread counts by group for user {current_user_id}: {unread_by_group}")
    return {"unread_by_group": unread_by_group}

@api_router.get("/group-chats/{group_id}", response_model=GroupChat)
async def get_group_chat(
    group_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get group chat details"""
    current_user_id = current_user.get("id")
    
    group = await db.group_chats.find_one({"id": group_id})
    
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Fix member_ids - convert all to strings (handle mixed string/dict format)
    member_ids = group.get('member_ids', [])
    normalized_member_ids = []
    for m in member_ids:
        if isinstance(m, str):
            normalized_member_ids.append(m)
        elif isinstance(m, dict):
            normalized_member_ids.append(m.get('id') or m.get('user_id'))
    group['member_ids'] = [mid for mid in normalized_member_ids if mid]  # Filter out None values
    
    # Fix admin_ids - convert all to strings
    admin_ids = group.get('admin_ids', [])
    normalized_admin_ids = []
    for a in admin_ids:
        if isinstance(a, str):
            normalized_admin_ids.append(a)
        elif isinstance(a, dict):
            normalized_admin_ids.append(a.get('id') or a.get('user_id'))
    group['admin_ids'] = [aid for aid in normalized_admin_ids if aid]
    
    # Fix missing fields
    if 'creator_id' not in group and 'created_by' in group:
        group['creator_id'] = group['created_by']
    elif 'creator_id' not in group:
        group['creator_id'] = group.get('member_ids', [None])[0] if group.get('member_ids') else None
    
    if 'admin_ids' not in group or not group['admin_ids']:
        group['admin_ids'] = [group.get('creator_id')] if group.get('creator_id') else []
    
    if 'id' not in group:
        group['id'] = str(group['_id'])
    
    # Check if user is member
    if current_user_id not in group.get("member_ids", []):
        raise HTTPException(status_code=403, detail="Bu gruba erişim yetkiniz yok")
    
    # DEBUG: Log admin_ids before returning
    logging.info(f"🔵 GROUP CHAT DEBUG - Group ID: {group_id}")
    logging.info(f"🔵 Current User ID: {current_user_id}")
    logging.info(f"🔵 Creator ID: {group.get('creator_id')}")
    logging.info(f"🔵 Admin IDs: {group.get('admin_ids')}")
    logging.info(f"🔵 Is current user in admin_ids? {current_user_id in group.get('admin_ids', [])}")
    
    # Remove MongoDB ObjectId for JSON serialization
    group_dict = {k: v for k, v in group.items() if k != "_id"}
    return GroupChat(**group_dict)

@api_router.post("/group-chats/{group_id}/messages", response_model=GroupMessage)
async def send_group_message(
    group_id: str,
    message_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Send a message to a group"""
    import uuid
    current_user_id = current_user.get("id")
    
    # Get group
    group = await db.group_chats.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Check if user is member (handle both string and object formats)
    member_ids = group.get("member_ids", [])
    is_member = False
    for member in member_ids:
        if isinstance(member, str) and member == current_user_id:
            is_member = True
            break
        elif isinstance(member, dict) and (member.get("id") == current_user_id or member.get("user_id") == current_user_id):
            is_member = True
            break
    
    if not is_member:
        raise HTTPException(status_code=403, detail="Bu gruba mesaj gönderme yetkiniz yok")
    
    # Check if user is admin, creator, or organizer (they can always send messages)
    is_admin_or_creator = current_user_id in group.get("admin_ids", [])
    creator_id = group.get("creator_id") or group.get("created_by")
    
    if creator_id == current_user_id:
        is_admin_or_creator = True
    
    print(f"🔍 Group creator_id: {creator_id}")
    print(f"🔍 Current user: {current_user_id}")
    print(f"🔍 Admin IDs: {group.get('admin_ids', [])}")
    print(f"🔍 Is admin or creator: {is_admin_or_creator}")
    
    # Check if user is event organizer (for event-based groups)
    event_id = group.get("event_id")
    if event_id and not is_admin_or_creator:
        event = await db.events.find_one({"id": event_id})
        if event and event.get("organizer_id") == current_user_id:
            is_admin_or_creator = True
            print("✅ User is event organizer! Bypassing permission check")
    
    # Check permissions (admins/creators/organizers bypass this)
    if not is_admin_or_creator:
        permission = group.get("permission", "all_members")
        print(f"🔍 Permission: {permission}")
        if permission == "admins_only":
            print("❌ User not admin, blocking message")
            raise HTTPException(status_code=403, detail="Sadece yöneticiler mesaj gönderebilir")
        elif permission != "all_members" and permission != "everyone":
            print(f"⚠️ Unknown permission: {permission}, allowing message")
    else:
        print("✅ Admin/Creator/Organizer can send message")
    
    # Get sender name
    sender = await db.users.find_one({"id": current_user_id})
    sender_name = sender.get("full_name") if sender else "Bilinmeyen"
    
    # Create message
    message_id = str(uuid.uuid4())
    message = {
        "id": message_id,
        "group_id": group_id,
        "sender_id": current_user_id,
        "sender_name": sender_name,
        "content": message_data.get("content"),
        "sent_at": datetime.utcnow(),
        "read_by": [current_user_id]
    }
    
    await db.group_messages.insert_one(message)
    
    # NOTE: Group message notifications disabled - users check unread count badge instead
    # # Send notifications to all group members except sender
    # for member_id in group.get("member_ids", []):
    #     if member_id != current_user_id:
    #         notification = {
    #             "id": str(uuid.uuid4()),
    #             "user_id": member_id,
    #             "type": "group_message",
    #             "title": f"{group['name']}",
    #             "message": f"{sender_name}: {message_data.content[:50]}...",
    #             "related_id": group_id,
    #             "related_type": "group_chat",
    #             "read": False,
    #             "created_at": datetime.utcnow()
    #         }
    #         await db.notifications.insert_one(notification)
    
    return GroupMessage(**message)

@api_router.get("/group-chats/{group_id}/messages", response_model=List[GroupMessage])
async def get_group_messages(
    group_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all messages in a group"""
    current_user_id = current_user.get("id")
    
    # Check if user is member
    group = await db.group_chats.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    if current_user_id not in group.get("member_ids", []):
        raise HTTPException(status_code=403, detail="Bu gruba erişim yetkiniz yok")
    
    messages = await db.group_messages.find({
        "group_id": group_id
    }).sort("sent_at", 1).to_list(1000)
    
    # Populate sender names
    print(f"🔵 Populating sender names for {len(messages)} messages")
    for msg in messages:
        sender_id = msg.get("sender_id")
        current_name = msg.get("sender_name")
        print(f"🔵 Message sender_id: {sender_id}, current_name: {current_name}")
        
        if sender_id and not current_name:
            user = await db.users.find_one({"id": sender_id})
            print(f"🔵 Found user: {user.get('full_name') if user else 'None'}")
            if user:
                msg["sender_name"] = user.get("full_name", "Bilinmeyen")
                print(f"🔵 Set sender_name to: {msg['sender_name']}")
    
    print(f"🔵 Returning {len(messages)} messages")
    return [GroupMessage(**msg) for msg in messages]

@api_router.put("/group-chats/{group_id}/mark-read")
async def mark_group_messages_as_read(
    group_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Mark all messages in a group as read for the current user"""
    current_user_id = current_user.get("id")
    
    # Verify user is member of the group
    group = await db.group_chats.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    if current_user_id not in group.get("member_ids", []):
        raise HTTPException(status_code=403, detail="Bu grubun üyesi değilsiniz")
    
    # Add current user to read_by array for all messages in this group (if not already present)
    result = await db.group_messages.update_many(
        {
            "group_id": group_id,
            "sender_id": {"$ne": current_user_id},  # Don't mark own messages
            "read_by": {"$ne": current_user_id}  # Only if not already read
        },
        {
            "$addToSet": {"read_by": current_user_id}
        }
    )
    
    logging.info(f"✅ Marked {result.modified_count} group messages as read in group {group_id} for user {current_user_id}")
    return {"success": True, "marked_count": result.modified_count}

@api_router.put("/group-chats/{group_id}/toggle-mute")
async def toggle_group_mute(
    group_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Grup mesajlaşmayı aç/kapa - Grup admini veya event organizatörü yapabilir"""
    
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    group = await db.group_chats.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Yetki kontrolü - Grup admini veya event organizatörü olmalı
    is_group_admin = current_user_id in group.get("admin_ids", [])
    is_creator = current_user_id == group.get("creator_id")
    is_event_organizer = False
    
    if group.get("event_id"):
        event = await db.events.find_one({"id": group["event_id"]})
        if event and event.get("organizer_id") == current_user_id:
            is_event_organizer = True
    
    if not (is_group_admin or is_creator or is_event_organizer):
        raise HTTPException(status_code=403, detail="Bu grubu açma/kapama yetkiniz yok")
    
    # Toggle permission
    current_permission = group.get("permission", GroupMessagePermission.EVERYONE.value)
    new_permission = (
        GroupMessagePermission.ADMINS_ONLY.value 
        if current_permission == GroupMessagePermission.EVERYONE.value 
        else GroupMessagePermission.EVERYONE.value
    )
    
    await db.group_chats.update_one(
        {"id": group_id},
        {"$set": {"permission": new_permission}}
    )
    
    # Send notification to all members
    status_text = "kapatıldı" if new_permission == GroupMessagePermission.ADMINS_ONLY.value else "açıldı"
    admin_user = await db.users.find_one({"id": current_user_id})
    admin_name = admin_user.get("full_name", admin_user.get("name", "Admin")) if admin_user else "Admin"
    
    for member_id in group.get("member_ids", []):
        if member_id != current_user_id:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": member_id,
                "type": "group_update",
                "title": f"{group['name']}",
                "message": f"{admin_name} grubu {status_text}",
                "related_id": group_id,
                "related_type": "group_chat",
                "read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(notification)
    
    logging.info(f"Group {group_id} permission toggled to {new_permission} by {current_user_id}")
    
    return {
        "success": True,
        "permission": new_permission,
        "message": f"Grup {status_text}"
    }

@api_router.delete("/group-chats/{group_id}/members/{user_id}")
async def remove_group_member(
    group_id: str,
    user_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Organizatör üyeyi gruptan çıkarır - Sadece event organizatörü yapabilir"""
    
    group = await db.group_chats.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Check if user is event organizer
    if not group.get("event_id"):
        raise HTTPException(status_code=400, detail="Bu grup bir etkinlik grubu değil")
    
    event = await db.events.find_one({"id": group["event_id"]})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    if event.get("organizer_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Sadece etkinlik organizatörü üyeleri çıkarabilir")
    
    # Can't remove self
    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Kendinizi çıkaramazsınız")
    
    # Check if user is member
    if user_id not in group.get("member_ids", []):
        raise HTTPException(status_code=404, detail="Kullanıcı bu grupta değil")
    
    # Remove from member_ids and admin_ids
    await db.group_chats.update_one(
        {"id": group_id},
        {
            "$pull": {
                "member_ids": user_id,
                "admin_ids": user_id
            }
        }
    )
    
    # Send notification to removed user
    removed_user = await db.users.find_one({"id": user_id})
    organizer = await db.users.find_one({"id": current_user_id})
    organizer_name = organizer.get("full_name") if organizer else "Organizatör"
    
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "type": "group_removal",
        "title": f"{group['name']}",
        "message": f"{organizer_name} tarafından gruptan çıkarıldınız",
        "related_id": group_id,
        "related_type": "group_chat",
        "read": False,
        "created_at": datetime.utcnow()
    }
    await db.notifications.insert_one(notification)
    
    return {
        "success": True,
        "message": f"{removed_user.get('full_name', 'Kullanıcı')} gruptan çıkarıldı"
    }

    """Update group message permission (admin only)"""
    group = await db.group_chats.find_one({"id": group_id})
    
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Check if user is admin
    if current_user_id not in group.get("admin_ids", []):
        raise HTTPException(status_code=403, detail="Sadece yöneticiler izinleri değiştirebilir")
    
    await db.group_chats.update_one(
        {"id": group_id},
        {"$set": {"permission": permission.value}}
    )
    
    return {"message": "İzinler güncellendi", "permission": permission.value}

@api_router.delete("/group-chats/{group_id}/members/{member_id}")
async def remove_group_member(
    group_id: str,
    member_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Remove a member from group (admin only)"""
    group = await db.group_chats.find_one({"id": group_id})
    
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Check if user is admin
    if current_user_id not in group.get("admin_ids", []):
        raise HTTPException(status_code=403, detail="Sadece yöneticiler üye çıkarabilir")
    
    # Can't remove creator
    if member_id == group.get("creator_id"):
        raise HTTPException(status_code=400, detail="Grup kurucusu çıkarılamaz")
    
    # Remove from members and admins
    await db.group_chats.update_one(
        {"id": group_id},
        {
            "$pull": {
                "member_ids": member_id,
                "admin_ids": member_id
            }
        }
    )
    
    return {"message": "Üye gruptan çıkarıldı"}

@api_router.post("/group-chats/{group_id}/invite-link")
async def generate_invite_link(
    group_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Generate invite link for group (admin only)"""
    import uuid
    
    group = await db.group_chats.find_one({"id": group_id})
    
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Check if user is admin
    if current_user_id not in group.get("admin_ids", []):
        raise HTTPException(status_code=403, detail="Sadece yöneticiler davet linki oluşturabilir")
    
    # Generate unique invite code
    invite_code = str(uuid.uuid4())[:8]
    invite_link = f"sportco://group-invite/{invite_code}"
    
    # Store invite link
    await db.group_chats.update_one(
        {"id": group_id},
        {"$set": {"invite_link": invite_code}}
    )
    
    return {"invite_link": invite_link, "invite_code": invite_code}

@api_router.post("/group-chats/join/{invite_code}")
async def join_group_by_invite(
    invite_code: str,
    current_user_id: str = Depends(get_current_user)
):
    """Join group using invite link"""
    group = await db.group_chats.find_one({"invite_link": invite_code})
    
    if not group:
        raise HTTPException(status_code=404, detail="Geçersiz davet linki")
    
    # Check if already member
    if current_user_id in group.get("member_ids", []):
        return {"message": "Zaten grup üyesisiniz", "group_id": group["id"]}
    
    # Add to members
    await db.group_chats.update_one(
        {"id": group["id"]},
        {"$push": {"member_ids": current_user_id}}
    )
    
    return {"message": "Gruba katıldınız", "group_id": group["id"]}

@api_router.post("/group-chats/send-bulk-message")
async def send_bulk_message_to_members(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Toplu mesaj gönder - Antrenör/Tesis sahibi/Kulüp yöneticisi üyelerine mesaj gönderir"""
    import uuid
    
    # get_current_user dict veya string dönebilir
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    body = await request.json()
    member_ids = body.get("member_ids", [])
    message_content = body.get("message", "")
    
    if not member_ids:
        raise HTTPException(status_code=400, detail="En az bir üye seçmelisiniz")
    
    if not message_content.strip():
        raise HTTPException(status_code=400, detail="Mesaj içeriği boş olamaz")
    
    # Get sender info
    sender = await db.users.find_one({"id": current_user_id})
    if not sender:
        logging.error(f"Sender not found: {current_user_id}, current_user type: {type(current_user)}, current_user: {current_user}")
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    sender_name = sender.get("full_name", sender.get("name", "Bilinmeyen"))
    
    # Sadece antrenör, tesis sahibi ve kulüp yöneticisi toplu mesaj gönderebilir
    allowed_types = ["coach", "venue_owner", "facility_owner", "club_manager", "admin", "super_admin"]
    if sender.get("user_type") not in allowed_types:
        raise HTTPException(status_code=403, detail="Bu özelliği kullanma yetkiniz yok")
    
    # Grup sohbeti oluştur veya bul
    group_name = f"Toplu Mesaj - {sender_name} ({datetime.utcnow().strftime('%d/%m/%Y %H:%M')})"
    
    group_chat_id = str(uuid.uuid4())
    group_chat = {
        "id": group_chat_id,
        "name": group_name,
        "description": f"{sender_name} tarafından toplu mesaj",
        "event_id": None,
        "creator_id": current_user_id,
        "admin_ids": [current_user_id],
        "member_ids": [current_user_id] + member_ids,
        "permission": "admins_only",  # Sadece gönderen mesaj atabilir
        "invite_link": None,
        "created_at": datetime.utcnow()
    }
    
    await db.group_chats.insert_one(group_chat)
    logging.info(f"Bulk message group chat created: {group_chat_id} by {current_user_id}")
    
    # Mesajı gönder
    message_id = str(uuid.uuid4())
    message = {
        "id": message_id,
        "group_id": group_chat_id,
        "sender_id": current_user_id,
        "sender_name": sender_name,
        "content": message_content,
        "sent_at": datetime.utcnow(),
        "read_by": [current_user_id]
    }
    
    await db.group_messages.insert_one(message)
    
    # Badge zaten mesajlar sekmesinde görünüyor, ayrıca bildirim oluşturmaya gerek yok
    
    logging.info(f"Bulk message sent to {len(member_ids)} members by {current_user_id}")
    
    return {
        "success": True,
        "group_id": group_chat_id,
        "message": f"{len(member_ids)} üyeye mesaj gönderildi",
        "recipients_count": len(member_ids)
    }




# ==================== TEAM ROUTES ====================

@api_router.post("/teams/create", response_model=Team)
async def create_team(
    team_data: TeamCreateRequest,
    current_user_data: dict = Depends(get_current_user)
):
    """Takım oluştur"""
    import uuid
    
    # get_current_user returns dict with {"id": ..., "user_type": ...}
    current_user_id = current_user_data.get("id") if isinstance(current_user_data, dict) else current_user_data
    
    # Get creator info
    creator = await db.users.find_one({"id": current_user_id})
    if not creator:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    creator_name = creator.get("full_name", "Bilinmeyen")
    organization_id = creator.get("organization_id")
    
    # Create team
    team_id = str(uuid.uuid4())
    
    # Convert players to TeamPlayer format
    team_players = []
    for player_data in team_data.players:
        user = await db.users.find_one({"id": player_data["user_id"]})
        if user:
            team_players.append({
                "user_id": player_data["user_id"],
                "user_name": user.get("full_name", "Bilinmeyen"),
                "role": player_data.get("role", "starter"),
                "position": player_data.get("position"),
                "jersey_number": player_data.get("jersey_number"),
                "joined_at": datetime.utcnow()
            })
    
    # Create group chat if requested
    group_chat_id = None
    if team_data.create_group_chat:
        group_chat_id = str(uuid.uuid4())
        member_ids = [p["user_id"] for p in team_players]
        if current_user_id not in member_ids:
            member_ids.append(current_user_id)
        
        group_chat = {
            "id": group_chat_id,
            "name": f"{team_data.name} - Takım Sohbeti",
            "description": f"{team_data.name} takımı grup sohbeti",
            "event_id": None,
            "creator_id": current_user_id,
            "admin_ids": [current_user_id],
            "member_ids": member_ids,
            "permission": "all_members",
            "invite_link": None,
            "created_at": datetime.utcnow()
        }
        await db.group_chats.insert_one(group_chat)
        logging.info(f"Team group chat created: {group_chat_id} for team {team_id}")
    
    team = {
        "id": team_id,
        "name": team_data.name,
        "sport": team_data.sport,
        "logo": team_data.logo,
        "description": team_data.description,
        "creator_id": current_user_id,
        "creator_name": creator_name,
        "organization_id": organization_id,
        "players": team_players,
        "max_players": team_data.max_players or 20,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "group_chat_id": group_chat_id,
        "is_public": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.teams.insert_one(team)
    logging.info(f"Team created: {team_id} by {current_user_id}")
    
    return team

@api_router.get("/teams/my-teams")
async def get_my_teams(current_user_data: dict = Depends(get_current_user)):
    """Kullanıcının oluşturduğu veya üyesi olduğu takımlar"""
    
    # get_current_user returns dict with {"id": ..., "user_type": ...}
    current_user_id = current_user_data.get("id") if isinstance(current_user_data, dict) else current_user_data
    
    logging.info(f"🏀 /teams/my-teams called by user_id: {current_user_id}")
    
    # Oluşturduğu takımlar
    created_teams = await db.teams.find({
        "creator_id": current_user_id
    }).to_list(100)
    
    logging.info(f"🏀 Created teams: {len(created_teams)}")
    
    # Üyesi olduğu takımlar
    member_teams = await db.teams.find({
        "players.user_id": current_user_id
    }).to_list(100)
    
    logging.info(f"🏀 Member teams: {len(member_teams)}")
    
    # Birleştir ve tekrarları kaldır
    all_teams = {team["id"]: team for team in created_teams + member_teams}
    
    # Remove MongoDB ObjectId fields for JSON serialization
    serialized_teams = []
    for team in all_teams.values():
        team_dict = {k: v for k, v in team.items() if k != "_id"}
        serialized_teams.append(team_dict)
    
    logging.info(f"🏀 Returning {len(serialized_teams)} teams")
    
    return {
        "teams": serialized_teams,
        "total": len(serialized_teams)
    }

@api_router.get("/teams/public")
async def get_public_teams(
    sport: Optional[str] = None,
    search: Optional[str] = None
):
    """Herkese açık takımlar (kayıt için)"""
    
    query = {"is_public": True}
    
    if sport:
        query["sport"] = sport
    
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    
    teams = await db.teams.find(query).to_list(100)
    
    # Remove MongoDB ObjectId fields for JSON serialization
    serialized_teams = []
    for team in teams:
        team_dict = {k: v for k, v in team.items() if k != "_id"}
        serialized_teams.append(team_dict)
    
    return {
        "teams": serialized_teams,
        "total": len(serialized_teams)
    }

@api_router.get("/teams/{team_id}")
async def get_team_detail(team_id: str):
    """Takım detayı"""
    
    team = await db.teams.find_one({"id": team_id})
    if not team:
        raise HTTPException(status_code=404, detail="Takım bulunamadı")
    
    # Remove MongoDB ObjectId for JSON serialization
    team_dict = {k: v for k, v in team.items() if k != "_id"}
    return team_dict

@api_router.put("/teams/{team_id}")
async def update_team(
    team_id: str,
    update_data: TeamUpdateRequest,
    current_user_id: str = Depends(get_current_user)
):
    """Takım güncelle"""
    
    team = await db.teams.find_one({"id": team_id})
    if not team:
        raise HTTPException(status_code=404, detail="Takım bulunamadı")
    
    # Sadece takım kurucusu güncelleyebilir
    if team["creator_id"] != current_user_id:
        raise HTTPException(status_code=403, detail="Bu takımı güncelleme yetkiniz yok")
    
    update_fields = {}
    
    if update_data.name:
        update_fields["name"] = update_data.name
    
    if update_data.logo is not None:
        update_fields["logo"] = update_data.logo
    
    if update_data.description is not None:
        update_fields["description"] = update_data.description
    
    if update_data.is_public is not None:
        update_fields["is_public"] = update_data.is_public
    
    if update_data.players:
        # Convert players to TeamPlayer format
        team_players = []
        for player_data in update_data.players:
            user = await db.users.find_one({"id": player_data["user_id"]})
            if user:
                team_players.append({
                    "user_id": player_data["user_id"],
                    "user_name": user.get("full_name", "Bilinmeyen"),
                    "role": player_data.get("role", "starter"),
                    "position": player_data.get("position"),
                    "jersey_number": player_data.get("jersey_number"),
                    "joined_at": datetime.utcnow()
                })
        update_fields["players"] = team_players
        
        # Update group chat members if exists
        if team.get("group_chat_id"):
            member_ids = [p["user_id"] for p in team_players]
            if current_user_id not in member_ids:
                member_ids.append(current_user_id)
            
            await db.group_chats.update_one(
                {"id": team["group_chat_id"]},
                {"$set": {"member_ids": member_ids}}
            )
    
    update_fields["updated_at"] = datetime.utcnow()
    
    await db.teams.update_one(
        {"id": team_id},
        {"$set": update_fields}
    )
    
    logging.info(f"Team updated: {team_id} by {current_user_id}")
    
    # Return updated team
    updated_team = await db.teams.find_one({"id": team_id})
    return updated_team

@api_router.delete("/teams/{team_id}")
async def delete_team(
    team_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Takım sil"""
    
    team = await db.teams.find_one({"id": team_id})
    if not team:
        raise HTTPException(status_code=404, detail="Takım bulunamadı")
    
    # Sadece takım kurucusu silebilir
    if team["creator_id"] != current_user_id:
        raise HTTPException(status_code=403, detail="Bu takımı silme yetkiniz yok")
    
    # Delete group chat if exists
    if team.get("group_chat_id"):
        await db.group_chats.delete_one({"id": team["group_chat_id"]})
    
    await db.teams.delete_one({"id": team_id})
    
    logging.info(f"Team deleted: {team_id} by {current_user_id}")
    
    return {"message": "Takım silindi", "team_id": team_id}

@api_router.post("/teams/{team_id}/join")
async def join_team(
    team_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Takıma katıl (halka açık takımlar için)"""
    
    team = await db.teams.find_one({"id": team_id})
    if not team:
        raise HTTPException(status_code=404, detail="Takım bulunamadı")
    
    if not team.get("is_public"):
        raise HTTPException(status_code=403, detail="Bu takım halka açık değil")
    
    # Check if already a member
    current_players = team.get("players", [])
    if any(p["user_id"] == current_user_id for p in current_players):
        raise HTTPException(status_code=400, detail="Zaten bu takımın üyesisiniz")
    
    # Check max players
    if len(current_players) >= team.get("max_players", 20):
        raise HTTPException(status_code=400, detail="Takım kadrosu dolu")
    
    # Get user info
    user = await db.users.find_one({"id": current_user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Add player
    new_player = {
        "user_id": current_user_id,
        "user_name": user.get("full_name", "Bilinmeyen"),
        "role": "substitute",  # Default to substitute
        "position": None,
        "jersey_number": None,
        "joined_at": datetime.utcnow()
    }
    
    await db.teams.update_one(
        {"id": team_id},
        {
            "$push": {"players": new_player},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    
    # Add to group chat if exists
    if team.get("group_chat_id"):
        await db.group_chats.update_one(
            {"id": team["group_chat_id"]},
            {"$addToSet": {"member_ids": current_user_id}}
        )
    
    logging.info(f"User {current_user_id} joined team {team_id}")
    
    return {"message": "Takıma katıldınız", "team_id": team_id}


# ==================== PAYMENT ROUTES (iyzico Integration) ====================

from iyzico_service import iyzico_service

@api_router.post("/payments/initialize", response_model=dict)
async def initialize_payment(
    payment_data: PaymentCreate,
    current_user_id: str = Depends(get_current_user)
):
    """Initialize payment with iyzico checkout form"""
    import uuid
    
    # Get user information
    user = await db.users.find_one({"id": current_user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Get related item (event or reservation)
    related_item = None
    related_name = ""
    
    if payment_data.related_type == "event":
        related_item = await db.events.find_one({"id": payment_data.related_id})
        if related_item:
            related_name = related_item.get("title", "Event")
    elif payment_data.related_type == "reservation":
        # Get reservation details
        reservation = await db.reservations.find_one({"id": payment_data.related_id})
        if reservation:
            # Get related player/coach/venue name
            if reservation.get("player_id"):
                player = await db.users.find_one({"id": reservation["player_id"]})
                related_name = f"Player Reservation - {player.get('full_name', 'Player')}" if player else "Player Reservation"
            elif reservation.get("coach_id"):
                coach = await db.users.find_one({"id": reservation["coach_id"]})
                related_name = f"Coach Reservation - {coach.get('full_name', 'Coach')}" if coach else "Coach Reservation"
            elif reservation.get("venue_id"):
                venue = await db.venues.find_one({"id": reservation["venue_id"]})
                related_name = f"Venue Reservation - {venue.get('name', 'Venue')}" if venue else "Venue Reservation"
            else:
                related_name = "Reservation"
    
    if not related_item and payment_data.related_type == "event":
        raise HTTPException(status_code=404, detail=f"{payment_data.related_type} bulunamadı")
    
    # Create payment record
    payment_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    
    payment = {
        "id": payment_id,
        "user_id": current_user_id,
        "related_type": payment_data.related_type,
        "related_id": payment_data.related_id,
        "amount": payment_data.amount,
        "currency": payment_data.currency,
        "status": PaymentStatus.PENDING.value,
        "iyzico_conversation_id": conversation_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.payments.insert_one(payment)
    
    # Initialize iyzico checkout form
    try:
        callback_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/payment-callback"
        
        result = iyzico_service.initialize_checkout_form(
            user=user,
            amount=payment_data.amount,
            related_type=payment_data.related_type,
            related_id=payment_data.related_id,
            related_name=related_name,
            callback_url=callback_url
        )
        
        # Update payment with token
        await db.payments.update_one(
            {"id": payment_id},
            {
                "$set": {
                    "iyzico_token": result.get("token"),
                    "status": PaymentStatus.INIT_3DS.value,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return {
            "paymentId": payment_id,
            "token": result.get("token"),
            "checkoutFormContent": result.get("checkoutFormContent"),
            "paymentPageUrl": result.get("paymentPageUrl")
        }
        
    except ValueError as e:
        # API credentials not configured
        logging.warning(f"Iyzico credentials not configured: {str(e)}")
        raise HTTPException(status_code=503, detail="Ödeme sistemi henüz yapılandırılmamış. Lütfen sistem yöneticisiyle iletişime geçin.")
    except Exception as e:
        logging.error(f"Payment initialization failed: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Ödeme başlatılamadı: {str(e)}")

@api_router.post("/payments/callback")
async def payment_callback(request: Request):
    """Handle iyzico payment callback"""
    try:
        # Get callback data
        form_data = await request.form()
        token = form_data.get("token")
        
        if not token:
            raise HTTPException(status_code=400, detail="Token eksik")
        
        # Retrieve payment result from iyzico
        result = iyzico_service.retrieve_checkout_form_result(token)
        
        # Find payment by token
        payment = await db.payments.find_one({"iyzico_token": token})
        
        if not payment:
            raise HTTPException(status_code=404, detail="Ödeme kaydı bulunamadı")
        
        # Update payment status
        update_data = {
            "updated_at": datetime.utcnow()
        }
        
        if result.get("status") == "success" and result.get("paymentStatus") == "SUCCESS":
            update_data["status"] = PaymentStatus.SUCCESS.value
            update_data["iyzico_payment_id"] = result.get("paymentId")
            update_data["card_last_four"] = result.get("lastFourDigits")
            update_data["card_association"] = result.get("cardAssociation")
            update_data["installment"] = result.get("installment", 1)
            
            # Update related item status if needed
            if payment["related_type"] == "event":
                # Mark participation as paid
                await db.participations.update_many(
                    {
                        "event_id": payment["related_id"],
                        "user_id": payment["user_id"]
                    },
                    {"$set": {"payment_status": "paid"}}
                )
            elif payment["related_type"] == "reservation":
                # Mark reservation as paid
                await db.reservations.update_one(
                    {"id": payment["related_id"]},
                    {"$set": {"payment_status": "paid"}}
                )
            
            logging.info(f"Payment successful: {payment['id']}")
        else:
            update_data["status"] = PaymentStatus.FAILURE.value
            update_data["error_code"] = result.get("errorCode")
            update_data["error_message"] = result.get("errorMessage")
            logging.error(f"Payment failed: {payment['id']} - {result.get('errorMessage')}")
        
        await db.payments.update_one(
            {"id": payment["id"]},
            {"$set": update_data}
        )
        
        # Event için ek güncelleme - event_participants tablosu
        if payment.get("related_type") == "event" or payment.get("event_id"):
            event_id = payment.get("event_id") or payment.get("related_id")
            user_id = payment.get("user_id")
            
            if result.get("status") == "success" and result.get("paymentStatus") == "SUCCESS":
                # Event participant'ı onayla
                await db.event_participants.update_one(
                    {"event_id": event_id, "user_id": user_id},
                    {
                        "$set": {
                            "status": "confirmed",
                            "payment_status": "completed",
                            "confirmed_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                # Event'e katılımcı ekle
                await db.events.update_one(
                    {"id": event_id},
                    {
                        "$inc": {"participant_count": 1},
                        "$addToSet": {"participants": user_id}
                    }
                )
                logging.info(f"✅ Event participant confirmed: {user_id} for event {event_id}")
                
                # ✅ CRITICAL: Bildirimler gönder
                try:
                    event = await db.events.find_one({"id": event_id})
                    user = await db.users.find_one({"id": user_id})
                    
                    if event:
                        event_title = event.get("title", "Etkinlik")
                        organizer_id = event.get("organizer_id")
                        
                        # 1. Katılımcıya bildirim gönder
                        participant_notification = {
                            "id": str(uuid.uuid4()),
                            "user_id": user_id,
                            "type": "event_join_confirmed",
                            "title": "✅ Etkinlik Katılımı Onaylandı",
                            "message": f"'{event_title}' etkinliğine katılımınız onaylandı. Ödemeniz başarıyla alındı.",
                            "related_id": event_id,
                            "related_type": "event",
                            "data": {
                                "event_id": event_id,
                                "event_title": event_title,
                                "payment_id": payment.get("id"),
                                "amount": payment.get("amount")
                            },
                            "read": False,
                            "is_read": False,
                            "created_at": datetime.utcnow()
                        }
                        await db.notifications.insert_one(participant_notification)
                        logging.info(f"📩 Notification sent to participant {user_id}")
                        
                        # 2. Organizatöre bildirim gönder
                        if organizer_id and organizer_id != user_id:
                            user_name = user.get("full_name", "Bir kullanıcı") if user else "Bir kullanıcı"
                            organizer_notification = {
                                "id": str(uuid.uuid4()),
                                "user_id": organizer_id,
                                "type": "event_new_participant",
                                "title": "🎉 Yeni Katılımcı",
                                "message": f"{user_name} '{event_title}' etkinliğine katıldı.",
                                "related_id": event_id,
                                "related_type": "event",
                                "data": {
                                    "event_id": event_id,
                                    "event_title": event_title,
                                    "participant_id": user_id,
                                    "participant_name": user_name
                                },
                                "read": False,
                                "is_read": False,
                                "created_at": datetime.utcnow()
                            }
                            await db.notifications.insert_one(organizer_notification)
                            logging.info(f"📩 Notification sent to organizer {organizer_id}")
                            
                except Exception as notif_error:
                    logging.error(f"Error sending notifications: {str(notif_error)}")
                
                # ✅ CRITICAL: Kullanıcıyı grup sohbetine ekle
                try:
                    group_chat = await db.group_chats.find_one({"event_id": event_id})
                    if group_chat:
                        await db.group_chats.update_one(
                            {"id": group_chat["id"]},
                            {"$addToSet": {"member_ids": user_id}}
                        )
                        logging.info(f"✅ User {user_id} added to group chat for event {event_id}")
                    else:
                        logging.warning(f"⚠️ No group chat found for event {event_id}")
                except Exception as gc_error:
                    logging.error(f"Error adding user to group chat: {str(gc_error)}")
        
        # Redirect URL oluştur (web için)
        import os
        frontend_url = os.getenv('FRONTEND_URL', 'https://tourneys-portal.preview.emergentagent.com')
        event_id = payment.get("event_id") or payment.get("related_id", "")
        
        if result.get("status") == "success" and result.get("paymentStatus") == "SUCCESS":
            redirect_url = f"{frontend_url}/event/{event_id}?payment=success"
        else:
            redirect_url = f"{frontend_url}/event/{event_id}?payment=failed"
        
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=redirect_url, status_code=303)
        
    except Exception as e:
        logging.error(f"Payment callback error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@api_router.get("/payments/{payment_id}")
async def get_payment_status(
    payment_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Get payment status"""
    payment = await db.payments.find_one({
        "id": payment_id,
        "user_id": current_user_id
    })
    
    if not payment:
        raise HTTPException(status_code=404, detail="Ödeme bulunamadı")
    
    payment.pop("_id", None)
    return Payment(**payment)

@api_router.post("/payments/{payment_id}/refund")
async def refund_payment(
    payment_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Request refund for a payment"""
    payment = await db.payments.find_one({
        "id": payment_id,
        "user_id": current_user_id
    })
    
    if not payment:
        raise HTTPException(status_code=404, detail="Ödeme bulunamadı")
    
    if payment["status"] != PaymentStatus.SUCCESS.value:
        raise HTTPException(status_code=400, detail="Sadece başarılı ödemeler iade edilebilir")
    
    if not payment.get("iyzico_payment_id"):
        raise HTTPException(status_code=400, detail="İyzico ödeme ID bulunamadı")
    


# ==================== SUPER ADMIN - MESSAGE MODERATION ====================

async def verify_super_admin(current_user_id: str = Depends(get_current_user)):
    """Verify user is super admin"""
    user = await db.users.find_one({"id": current_user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    if user.get("user_type") != "super_admin":
        raise HTTPException(status_code=403, detail="Bu işlem için super admin yetkisi gereklidir")
    
    return current_user_id

# NOTE: Admin user search, messages, stats, and user management endpoints
# have been moved to admin_endpoints.py module
# The following endpoints are now handled by admin_router:
# - /admin/users/search
# - /admin/users/{user_id}/messages/personal
# - /admin/users/{user_id}/messages/groups
# - /admin/groups/{group_id}/messages
# - /admin/messages/{message_id}/flag
# - /admin/messages/{message_id} (DELETE)
# - /admin/stats
# - /admin/users
# - /admin/users/{user_id}/status

@api_router.get("/payments/user/history")
async def get_user_payments(
    current_user_id: str = Depends(get_current_user),
    skip: int = 0,
    limit: int = 50
):
    """Get user's payment history"""
    payments = await db.payments.find({
        "user_id": current_user_id
    }).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    for payment in payments:
        payment.pop("_id", None)
    
    return payments

# ==================== RANKING ROUTES ====================

@api_router.get("/rankings", response_model=List[Ranking])
async def get_rankings(
    sport: Optional[str] = None,
    city: Optional[str] = None,
    gender: Optional[Gender] = None,
    age_group: Optional[str] = None,
    limit: int = 50
):
    """Get rankings/leaderboard"""
    query = {}
    if sport:
        query["sport"] = sport
    if city:
        query["city"] = city
    if gender:
        query["gender"] = gender.value
    if age_group:
        query["age_group"] = age_group
    
    # Get users with their stats
    users = await db.users.find(query).limit(limit).to_list(limit)
    
    rankings = []
    for user in users:
        # Calculate user stats
        events_organized = await db.events.count_documents({"organizer_id": user["id"]})
        participations = await db.participations.count_documents({"user_id": user["id"]})
        
        # Calculate points from matches
        matches = await db.matches.find({
            "$or": [
                {"participant1_id": user["id"]},
                {"participant2_id": user["id"]}
            ],
            "status": "completed"
        }).to_list(1000)
        
        total_points = 0
        wins = 0
        for match in matches:
            if match.get("winner_id") == user["id"]:
                total_points += 3
                wins += 1
        
        ranking = Ranking(
            id=str(uuid.uuid4()),
            user_id=user["id"],
            sport=user.get("sport", sport or ""),
            city=user.get("city", ""),
            points=total_points,
            wins=wins,
            matches_played=len(matches),
            rank=0  # Will be set after sorting
        )
        rankings.append(ranking)
    
    # Sort by points (descending)
    rankings.sort(key=lambda x: x.points, reverse=True)
    
    # Set ranks
    for i, ranking in enumerate(rankings, 1):
        ranking.rank = i
    
    return rankings

# ==================== SOCKET.IO EVENTS ====================
# Socket.IO will be integrated when real-time messaging is implemented
# For now, using REST API for messages

# @sio.event
# async def connect(sid, environ):
#     logger.info(f"Client connected: {sid}")

# @sio.event
# async def disconnect(sid):
#     logger.info(f"Client disconnected: {sid}")

# @sio.event
# async def join_room(sid, data):
#     """Join a chat room"""
#     room = data.get("room")
#     await sio.enter_room(sid, room)
#     logger.info(f"Client {sid} joined room {room}")

# @sio.event
# async def send_message(sid, data):
#     """Send a message"""
#     sender_id = data.get("sender_id")
#     receiver_id = data.get("receiver_id")
#     content = data.get("content")
#     
#     # Save message to database
#     message_dict = {
#         "id": str(uuid.uuid4()),
#         "sender_id": sender_id,
#         "receiver_id": receiver_id,
#         "content": content,
#         "is_read": False,
#         "sent_at": datetime.utcnow()
#     }
#     await db.messages.insert_one(message_dict)
#     
#     # Emit to receiver's room
#     room = f"user_{receiver_id}"
#     await sio.emit("new_message", message_dict, room=room)
#     
#     logger.info(f"Message sent from {sender_id} to {receiver_id}")

# REST API endpoint for sending messages
@api_router.post("/messages/send", response_model=Message)
async def send_message_rest(message: MessageBase, current_user: dict = Depends(get_current_user)):
    """Send a message via REST API"""
    current_user_id = current_user.get("id")
    
    message_dict = message.dict()
    message_dict["id"] = str(uuid.uuid4())
    message_dict["sender_id"] = current_user_id
    message_dict["sent_at"] = datetime.utcnow()
    
    await db.messages.insert_one(message_dict)
    
    # NOTE: Message notifications disabled - users check unread count badge instead
    # # Create notification for receiver
    # try:
    #     sender = await db.users.find_one({"id": current_user_id})
    #     sender_name = sender.get("full_name", "Bir kullanıcı") if sender else "Bir kullanıcı"
    #     
    #     notification_data = {
    #         "id": str(uuid.uuid4()),
    #         "user_id": message.receiver_id,
    #         "type": "message_received",
    #         "title": "Yeni Mesaj",
    #         "message": f"{sender_name} size mesaj gönderdi",
    #         "related_id": message_dict["id"],
    #         "related_type": "message",
    #         "read": False,
    #         "created_at": datetime.utcnow()
    #     }
    #     await db.notifications.insert_one(notification_data)
    #     
    #     # Send push notification
    #     push_token_doc = await db.push_tokens.find_one({"user_id": message.receiver_id})
    #     if push_token_doc and push_token_doc.get("expo_push_token"):
    #         await push_service.send_push_notification(
    #             push_tokens=[push_token_doc["expo_push_token"]],
    #             title="Yeni Mesaj",
    #             body=f"{sender_name} size mesaj gönderdi",
    #             data={
    #                 "type": "message",
    #                 "message_id": message_dict["id"]
    #             }
    #         )
    # except Exception as e:
    #     logging.error(f"Error creating message notification: {str(e)}")
    
    return Message(**message_dict)

# ==================== OAUTH ROUTES ====================

@api_router.post("/auth/oauth/session")
async def process_oauth_session(request: Request, response: Response):
    """Process OAuth session from Emergent Auth"""
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        raise HTTPException(status_code=400, detail="Session ID required")
    
    try:
        # Call Emergent Auth API
        async with httpx.AsyncClient() as client:
            auth_response = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id}
            )
            
            if auth_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Geçersiz oturum")
            
            session_data = auth_response.json()
            
            # Check if user exists
            user = await db.users.find_one({"email": session_data["email"]})
            
            if not user:
                # Create new user
                user_dict = {
                    "id": str(uuid.uuid4()),
                    "email": session_data["email"],
                    "full_name": session_data["name"],
                    "profile_image": session_data.get("picture"),
                    "user_type": "player",
                    "city": "Istanbul",
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc),
                    "player_profile": {
                        "age": 25,
                        "gender": "male",
                        "sports": ["Football"],
                        "skill_levels": {"Football": "intermediate"}
                    }
                }
                await db.users.insert_one(user_dict)
                user = user_dict
            
            # Create session
            session_token = session_data["session_token"]
            expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            
            session_doc = {
                "user_id": user["id"],
                "session_token": session_token,
                "expires_at": expires_at,
                "created_at": datetime.now(timezone.utc)
            }
            await db.user_sessions.insert_one(session_doc)
            
            # Set cookie
            response.set_cookie(
                key="session_token",
                value=session_token,
                httponly=True,
                secure=True,
                samesite="none",
                max_age=7 * 24 * 60 * 60,
                path="/"
            )
            
            return {
                "user": User(**{k: v for k, v in user.items() if k != "hashed_password"}),
                "session_token": session_token
            }
    except Exception as e:
        logger.error(f"OAuth session error: {str(e)}")
        raise HTTPException(status_code=400, detail="OAuth session failed")

@api_router.get("/auth/session")
async def check_session(request: Request):
    """Check existing session from cookie or Authorization header"""
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            session_token = auth_header.replace("Bearer ", "")
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Kimlik doğrulanmadı")
    
    # Check session in database
    session = await db.user_sessions.find_one({"session_token": session_token})
    if not session:
        raise HTTPException(status_code=401, detail="Geçersiz oturum")
    
    # Check if expired
    if session["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    
    # Get user
    user = await db.users.find_one({"id": session["user_id"]})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    return User(**{k: v for k, v in user.items() if k != "hashed_password"})

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout and clear session"""
    session_token = request.cookies.get("session_token")
    
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
        response.delete_cookie(key="session_token", path="/")
    
    return {"message": "Logged out successfully"}

# ==================== STRIPE PAYMENT ROUTES ====================

# Package definitions (fixed prices - cannot be manipulated by frontend)
TICKET_PACKAGES = {
    "single": {"price": 50.0, "name": "Tek Bilet"},
    "double": {"price": 90.0, "name": "İkili Bilet (10% indirim)"},
    "team": {"price": 200.0, "name": "Takım Bileti (5 kişi)"}
}

@api_router.post("/payments/stripe/checkout")
async def create_stripe_checkout(
    request: Request,
    checkout_req: StripeCheckoutRequest,
    current_user_id: str = Depends(get_current_user)
):
    """Create Stripe checkout session for event ticket"""
    # Get event
    event = await db.events.find_one({"id": checkout_req.event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Validate package
    if checkout_req.package_type not in TICKET_PACKAGES:
        raise HTTPException(status_code=400, detail="Geçersiz paket türü")
    
    package = TICKET_PACKAGES[checkout_req.package_type]
    
    # Initialize Stripe
    stripe_client = init_stripe(request)
    
    # Create success and cancel URLs
    success_url = f"{checkout_req.origin_url}/payment-success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{checkout_req.origin_url}/events/{checkout_req.event_id}"
    
    # Create checkout session
    checkout_request = CheckoutSessionRequest(
        amount=package["price"],
        currency="try",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "event_id": checkout_req.event_id,
            "user_id": current_user_id,
            "package_type": checkout_req.package_type
        }
    )
    
    session: CheckoutSessionResponse = await stripe_client.create_checkout_session(checkout_request)
    
    # Create payment transaction record
    transaction_dict = {
        "id": str(uuid.uuid4()),
        "user_id": current_user_id,
        "event_id": checkout_req.event_id,
        "session_id": session.session_id,
        "amount": package["price"],
        "currency": "try",
        "payment_status": "initiated",
        "payment_provider": "stripe",
        "metadata": {
            "package_type": checkout_req.package_type,
            "package_name": package["name"]
        },
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    await db.payment_transactions.insert_one(transaction_dict)
    
    return {"checkout_url": session.url, "session_id": session.session_id}

@api_router.get("/payments/stripe/status/{session_id}")
async def check_stripe_payment_status(
    request: Request,
    session_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Check Stripe payment status"""
    stripe_client = init_stripe(request)
    
    # Get checkout status from Stripe
    status: CheckoutStatusResponse = await stripe_client.get_checkout_status(session_id)
    
    # Find transaction
    transaction = await db.payment_transactions.find_one({"session_id": session_id})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    # Update transaction if payment is complete and not already processed
    if status.payment_status == "paid" and transaction["payment_status"] != "completed":
        # Update transaction
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "payment_status": "completed",
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        # Create participation and ticket
        event_id = status.metadata.get("event_id")
        if event_id:
            # Create participation
            participation_dict = {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "user_id": current_user_id,
                "ticket_id": None,
                "payment_status": "completed",
                "payment_provider": "stripe",
                "joined_at": datetime.now(timezone.utc)
            }
            await db.participations.insert_one(participation_dict)
            
            # Create ticket
            ticket_dict = {
                "id": str(uuid.uuid4()),
                "ticket_number": f"TK-{str(uuid.uuid4())[:8].upper()}",
                "event_id": event_id,
                "user_id": current_user_id,
                "price": status.amount_total / 100,  # Convert from cents
                "currency": status.currency.upper(),
                "payment_provider": "stripe",
                "purchased_at": datetime.now(timezone.utc),
                "payment_status": "completed",
                "payment_id": session_id
            }
            await db.tickets.insert_one(ticket_dict)
            
            # Update participation with ticket_id
            await db.participations.update_one(
                {"id": participation_dict["id"]},
                {"$set": {"ticket_id": ticket_dict["id"]}}
            )
            
            # Update event participant count
            await db.events.update_one(
                {"id": event_id},
                {"$inc": {"participant_count": 1}}
            )
    
    elif status.status == "expired":
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "payment_status": "expired",
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
    
    return {
        "status": status.status,
        "payment_status": status.payment_status,
        "amount": status.amount_total / 100,
        "currency": status.currency
    }

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhooks"""
    body = await request.body()
    signature = request.headers.get("Stripe-Signature")
    
    stripe_client = init_stripe(request)
    
    try:
        webhook_response = await stripe_client.handle_webhook(body, signature)
        
        logger.info(f"Stripe webhook: {webhook_response.event_type} - {webhook_response.session_id}")
        
        # Process webhook event
        if webhook_response.event_type == "checkout.session.completed":
            # Payment was successful
            session_id = webhook_response.session_id
            
            # Update transaction if not already done
            transaction = await db.payment_transactions.find_one({"session_id": session_id})
            if transaction and transaction["payment_status"] != "completed":
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {
                        "$set": {
                            "payment_status": "completed",
                            "updated_at": datetime.now(timezone.utc)
                        }
                    }
                )
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        raise HTTPException(status_code=400, detail="Webhook processing failed")

# Health check
@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}

# ==================== VERIFICATION ROUTES ====================
# NOTE: Verification endpoint'leri auth_endpoints.py modülüne taşındı
# /auth/send-verification -> auth_endpoints.py
# /auth/verify-code -> auth_endpoints.py
# /auth/resend-verification -> auth_endpoints.py

# ==================== ADMIN ROUTES ====================

async def check_admin(current_user: dict = Depends(get_current_user)) -> str:
    """Check if current user is admin or super admin"""
    user_id = current_user.get("id")
    user = await db.users.find_one({"id": user_id})
    
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Allow both admin and super admin
    is_admin = user.get("user_type") == "admin"
    is_super_admin = (
        user.get("email") == SUPER_ADMIN_EMAIL or 
        user.get("is_super_admin") == True or
        user.get("user_type") == "super_admin"
    )
    
    if not (is_admin or is_super_admin):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return user_id

# NOTE: /admin/stats, /admin/users, and /admin/users/{user_id}/status
# endpoints are now served from admin_endpoints.py module

@api_router.put("/admin/users/{user_id}")
async def update_user_admin(
    user_id: str,
    update_data: dict,
    admin_id: str = Depends(check_admin)
):
    """Update user information (admin only)"""
    # Get current user
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Prepare update fields
    allowed_fields = [
        "full_name", "email", "phone", "user_type", "city",
        "tc_no", "tax_no", "club_organization_name", "skill_level",
        "date_of_birth", "sports"
    ]
    
    update_fields = {}
    for field in allowed_fields:
        if field in update_data:
            update_fields[field] = update_data[field]
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Update user
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": update_fields}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="No changes made")
    
    return {"message": "User updated successfully", "updated_fields": list(update_fields.keys())}


@api_router.post("/admin/impersonate/{user_id}")
async def impersonate_user(
    user_id: str,
    admin: dict = Depends(get_current_user)
):
    """
    Impersonate a user (admin/super_admin only)
    Returns a new token for the target user with impersonation metadata
    """
    # Get admin user from database to verify permissions
    admin_user = await db.users.find_one({"id": admin.get("id")})
    if not admin_user:
        raise HTTPException(status_code=404, detail="Admin user not found")
    
    # Check if user is admin or super admin
    is_admin = admin_user.get("user_type") == "admin"
    is_super_admin = (
        admin_user.get("email") == SUPER_ADMIN_EMAIL or 
        admin_user.get("is_super_admin") == True or
        admin_user.get("user_type") == "super_admin"
    )
    
    if not (is_admin or is_super_admin):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Get target user
    target_user = await db.users.find_one({"id": user_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")
    
    # Prevent impersonating another admin (unless you're super admin)
    if target_user.get("user_type") == "admin" and not is_super_admin:
        raise HTTPException(status_code=403, detail="Cannot impersonate admin users")
    
    if target_user.get("is_super_admin") and not is_super_admin:
        raise HTTPException(status_code=403, detail="Cannot impersonate super admin users")
    
    # Create impersonation token
    token_data = {
        "sub": target_user["id"],
        "user_type": target_user.get("user_type", "player"),
        "impersonated_by": admin.get("id"),  # Store who is impersonating
        "is_impersonation": True,
        "exp": datetime.utcnow() + timedelta(hours=2)  # Shorter expiration for security
    }
    
    impersonation_token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    logger.info(f"🎭 Admin {admin.get('id')} impersonating user {user_id}")
    
    return {
        "access_token": impersonation_token,
        "token_type": "bearer",
        "user": {
            "id": target_user["id"],
            "email": target_user["email"],
            "full_name": target_user["full_name"],
            "user_type": target_user.get("user_type", "player"),
            "phone": target_user.get("phone"),
        },
        "impersonation": {
            "is_impersonating": True,
            "admin_id": admin.get("id"),
            "admin_name": admin_user.get("full_name"),
        }
    }


@api_router.get("/admin/tickets")
async def get_all_tickets_admin(
    admin_id: str = Depends(check_admin),
    skip: int = 0,
    limit: int = 100
):
    """Get all tickets with user and event details (admin only)"""
    # Get all tickets
    tickets = await db.tickets.find({}).skip(skip).limit(limit).to_list(limit)
    
    # Enrich with user and event data
    enriched_tickets = []
    for ticket in tickets:
        ticket.pop("_id", None)
        
        # Get user info
        user = await db.users.find_one({"id": ticket.get("user_id")})
        if user:
            ticket["user_name"] = user.get("full_name")
            ticket["user_email"] = user.get("email")
            ticket["user_phone"] = user.get("phone")
        
        # Get event info
        event = await db.events.find_one({"id": ticket.get("event_id")})
        if event:
            ticket["event_title"] = event.get("title")
            ticket["event_date"] = event.get("start_date")
            ticket["event_city"] = event.get("city")
        
        enriched_tickets.append(ticket)
    
    total = await db.tickets.count_documents({})
    
    return {"tickets": enriched_tickets, "total": total}

@api_router.get("/admin/events")
async def get_all_events_admin(
    admin_id: str = Depends(check_admin),
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    event_type: Optional[str] = None
):
    """Get all events for admin"""
    query = {}
    if status:
        if status == "active":
            query["is_active"] = True
        elif status == "inactive":
            query["is_active"] = False
    if event_type:
        query["event_type"] = event_type
    
    events = await db.events.find(query).skip(skip).limit(limit).to_list(limit)
    total = await db.events.count_documents(query)
    
    # Clean MongoDB _id
    for event in events:
        event.pop("_id", None)
    
    return {"events": events, "total": total}

@api_router.delete("/admin/events/{event_id}")
async def delete_event_admin(
    event_id: str,
    admin_id: str = Depends(check_admin)
):
    """Delete an event (admin only)"""
    result = await db.events.delete_one({"id": event_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Also delete related data
    await db.participations.delete_many({"event_id": event_id})
    await db.tickets.delete_many({"event_id": event_id})
    
    return {"message": "Event deleted successfully"}

@api_router.get("/admin/payments")
async def get_all_payments(
    admin_id: str = Depends(check_admin),
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None
):
    """Get all payment transactions"""
    query = {}
    if status:
        query["status"] = status
    
    payments = await db.payments.find(query).skip(skip).limit(limit).to_list(limit)
    total = await db.payments.count_documents(query)
    
    # Clean MongoDB _id
    for payment in payments:
        payment.pop("_id", None)
    
    return {"payments": payments, "total": total}

@api_router.get("/admin/messages")
async def get_all_messages_admin(
    admin_id: str = Depends(check_admin),
    skip: int = 0,
    limit: int = 50
):
    """Get all messages for admin"""
    messages = await db.messages.find({}).skip(skip).limit(limit).to_list(limit)
    total = await db.messages.count_documents({})
    
    for message in messages:
        message.pop("_id", None)
    
    return {"messages": messages, "total": total}

# NOTE: DELETE /admin/messages/{message_id} is now served from admin_endpoints.py
# with improved soft-delete functionality

@api_router.get("/admin/venues")
async def get_all_venues_admin(
    admin_id: str = Depends(check_admin),
    approved: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50
):
    """Get all venues for admin (approved and pending)"""
    query = {}
    if approved is not None:
        query["approved"] = approved
    
    venues = await db.venues.find(query).skip(skip).limit(limit).to_list(limit)
    total = await db.venues.count_documents(query)
    
    for venue in venues:
        venue["id"] = str(venue.pop("_id", venue.get("id")))
    
    return {"venues": venues, "total": total}

@api_router.get("/admin/venues/pending")
async def get_pending_venues_admin(
    admin_id: str = Depends(check_admin),
    skip: int = 0,
    limit: int = 50
):
    """Get pending venues (waiting for approval)"""
    venues = await db.venues.find({"approved": False}).skip(skip).limit(limit).to_list(limit)
    total = await db.venues.count_documents({"approved": False})
    
    for venue in venues:
        venue["id"] = str(venue.pop("_id", venue.get("id")))
    
    return {"venues": venues, "total": total}

@api_router.put("/admin/venues/{venue_id}/approve")
async def approve_venue_admin(
    venue_id: str,
    admin_id: str = Depends(check_admin)
):
    """Approve a venue"""
    result = await db.venues.update_one(
        {"id": venue_id},
        {"$set": {"approved": True}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Venue not found")
    
    return {"message": "Venue approved successfully"}

@api_router.put("/admin/venues/{venue_id}/reject")
async def reject_venue_admin(
    venue_id: str,
    admin_id: str = Depends(check_admin)
):
    """Reject/disable a venue"""
    result = await db.venues.update_one(
        {"id": venue_id},
        {"$set": {"approved": False, "is_active": False}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Venue not found")
    
    return {"message": "Venue rejected successfully"}

# ==================== SUPER ADMIN ROUTES ====================

# Super admin email
SUPER_ADMIN_EMAIL = "obkaraca@gmail.com"

async def check_super_admin(current_user: dict = Depends(get_current_user)) -> str:
    """Check if current user is super admin"""
    user_id = current_user.get("id")
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Check if user is super admin by email or has super_admin flag
    is_super_admin = (
        user.get("email") == SUPER_ADMIN_EMAIL or 
        user.get("is_super_admin") == True or
        user.get("user_type") == "super_admin"
    )
    
    if not is_super_admin:
        raise HTTPException(status_code=403, detail="Super admin access required")
    
    return user_id

@api_router.get("/super-admin/check")
async def check_super_admin_status(current_user: dict = Depends(get_current_user)):
    """Check if current user is super admin"""
    user_id = current_user.get("id")
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    is_super_admin = (
        user.get("email") == SUPER_ADMIN_EMAIL or 
        user.get("is_super_admin") == True
    )
    
    # Also check user_type for super_admin
    if user.get("user_type") == "super_admin":
        is_super_admin = True
    
    return {"is_super_admin": is_super_admin}

@api_router.get("/super-admin/users")
async def get_all_users_super_admin(
    admin_id: str = Depends(check_super_admin),
    skip: int = 0,
    limit: int = 100,
    user_type: Optional[str] = None,
    search: Optional[str] = None
):
    """Get all users (super admin only)"""
    query = {}
    if user_type:
        query["user_type"] = user_type
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}}
        ]
    
    users = await db.users.find(query).skip(skip).limit(limit).to_list(limit)
    total = await db.users.count_documents(query)
    
    # Remove sensitive data
    for user in users:
        user.pop("hashed_password", None)
        user.pop("_id", None)
    
    return {"users": users, "total": total}

@api_router.put("/super-admin/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role_data: dict,
    admin_id: str = Depends(check_super_admin)
):
    """Update user role/type (super admin only)"""
    new_user_type = role_data.get("user_type")
    
    if not new_user_type:
        raise HTTPException(status_code=400, detail="user_type is required")
    
    # Validate user type
    valid_types = ["player", "coach", "venue_owner", "parent", "organizer", "referee", "admin", "accountant", "operations"]
    if new_user_type not in valid_types:
        raise HTTPException(status_code=400, detail="Geçersiz kullanıcı türü")
    
    # Update user
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"user_type": new_user_type}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    return {"message": "User role updated successfully", "new_role": new_user_type}


@api_router.delete("/super-admin/users/{user_id}")
async def delete_user(
    user_id: str,
    admin_user_id: str = Depends(check_super_admin)
):
    """Delete a user (super admin only)"""
    # Get target user
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Prevent deleting super admin
    if user.get("email") == SUPER_ADMIN_EMAIL or user.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Cannot delete super admin")
    
    # Prevent deleting yourself
    if user_id == admin_user_id:
        raise HTTPException(status_code=403, detail="Cannot delete yourself")
    
    # Delete user
    result = await db.users.delete_one({"id": user_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    logger.info(f"🗑️ User {user_id} deleted by admin {admin_user_id}")
    
    return {"message": "User deleted successfully"}

@api_router.put("/super-admin/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: str,
    permissions_data: dict,
    admin_id: str = Depends(check_super_admin)
):
    """Update user permissions (super admin only)"""
    # Get current user
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Prevent demoting super admin
    if user.get("email") == SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Cannot modify super admin permissions")
    
    # Update permissions
    update_data = {}
    
    # Set admin status
    if "is_admin" in permissions_data:
        update_data["user_type"] = "admin" if permissions_data["is_admin"] else user.get("user_type", "player")
    
    # Set super admin status (only super admin can promote others)
    if "is_super_admin" in permissions_data:
        update_data["is_super_admin"] = permissions_data["is_super_admin"]
    
    # Custom permissions array
    if "permissions" in permissions_data:
        update_data["permissions"] = permissions_data["permissions"]
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No permissions to update")
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": update_data}
    )
    
    return {"message": "Permissions updated successfully"}

@api_router.put("/super-admin/users/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    admin_id: str = Depends(check_super_admin)
):
    """Suspend a user (super admin only)"""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Prevent suspending super admin
    if user.get("email") == SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Cannot suspend super admin")
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"is_active": False, "suspended": True}}
    )
    
    return {"message": "User suspended successfully"}

@api_router.put("/super-admin/users/{user_id}/activate")
async def activate_user(
    user_id: str,
    admin_id: str = Depends(check_super_admin)
):
    """Activate a suspended user (super admin only)"""
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"is_active": True, "suspended": False}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    return {"message": "User activated successfully"}

@api_router.get("/super-admin/stats")
async def get_super_admin_stats(admin_id: str = Depends(check_super_admin)):
    """Get comprehensive platform statistics (super admin only)"""
    # User statistics
    total_users = await db.users.count_documents({})
    active_users = await db.users.count_documents({"is_active": True})
    suspended_users = await db.users.count_documents({"suspended": True})
    
    # User breakdown by type
    user_types = await db.users.aggregate([
        {"$group": {"_id": "$user_type", "count": {"$sum": 1}}}
    ]).to_list(20)
    
    # Event statistics
    total_events = await db.events.count_documents({})
    active_events = await db.events.count_documents({"is_active": True})
    
    # Venue statistics
    total_venues = await db.venues.count_documents({})
    approved_venues = await db.venues.count_documents({"approved": True})
    pending_venues = await db.venues.count_documents({"approved": False})
    
    # Admin users
    admin_users = await db.users.count_documents({"user_type": "admin"})
    super_admins = await db.users.count_documents({"is_super_admin": True})
    
    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "suspended": suspended_users,
            "by_type": {item["_id"]: item["count"] for item in user_types}
        },
        "events": {
            "total": total_events,
            "active": active_events
        },
        "venues": {
            "total": total_venues,
            "approved": approved_venues,
            "pending": pending_venues
        },
        "admins": {
            "regular_admins": admin_users,
            "super_admins": super_admins
        }
    }

# ==================== RESERVATION ROUTES ====================

@api_router.post("/reservations")
async def create_reservation(
    reservation_data: dict,
    current_user_id: str = Depends(get_current_user)
):
    """Create a new reservation request (venue, coach, or referee)"""
    
    # 15 dakika kontrolü - geçmiş tarihli rezervasyon oluşturulamaz
    reservation_date = reservation_data.get("date")
    reservation_hour = reservation_data.get("hour") or reservation_data.get("start_time", "00:00")
    
    if reservation_date:
        if isinstance(reservation_date, str) and "T" not in reservation_date:
            # Sadece tarih string ise, saat ile birleştir
            reservation_datetime_str = f"{reservation_date}T{reservation_hour}:00"
            try:
                reservation_datetime = datetime.fromisoformat(reservation_datetime_str)
            except:
                reservation_datetime = datetime.strptime(reservation_datetime_str, "%Y-%m-%dT%H:%M:00")
        else:
            reservation_datetime = datetime.fromisoformat(str(reservation_date).replace("Z", "+00:00")) if isinstance(reservation_date, str) else reservation_date
        
        min_datetime = datetime.utcnow() + timedelta(minutes=15)
        if reservation_datetime.tzinfo:
            min_datetime = min_datetime.replace(tzinfo=reservation_datetime.tzinfo)
        elif reservation_datetime.tzinfo is None and min_datetime.tzinfo:
            min_datetime = min_datetime.replace(tzinfo=None)
            
        if reservation_datetime < min_datetime:
            raise HTTPException(status_code=400, detail="Rezervasyon en erken 15 dakika sonrasına yapılabilir")
    
    reservation_id = str(uuid.uuid4())
    
    # Determine reservation type
    if "venue_id" in reservation_data:
        # Venue reservation
        venue = await db.venues.find_one({"id": reservation_data["venue_id"]})
        if not venue:
            raise HTTPException(status_code=404, detail="Venue not found")
        
        total_hours = len(reservation_data["time_slots"])
        hourly_rate = venue.get("hourly_rate", 0)
        total_price = total_hours * hourly_rate
        
        reservation = {
            "id": reservation_id,
            "reservation_type": "venue",
            "venue_id": reservation_data["venue_id"],
            "user_id": current_user_id,
            "date": reservation_data["date"],
            "time_slots": reservation_data["time_slots"],
            "total_hours": total_hours,
            "hourly_rate": hourly_rate,
            "total_price": total_price,
            "status": "pending",
            "notes": reservation_data.get("notes", ""),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.reservations.insert_one(reservation)
        
        # ✅ Talep eden kullanıcının bilgilerini al
        actual_user_id = current_user_id
        if isinstance(current_user_id, dict):
            actual_user_id = current_user_id.get("id")
        
        requester = await db.users.find_one({"id": actual_user_id})
        requester_name = requester.get("full_name", "Misafir") if requester else "Misafir"
        
        # Create notification for venue owner
        notification_data = {
            "id": str(uuid.uuid4()),
            "user_id": venue["owner_id"],
            "notification_type": "reservation_request",
            "title": "Yeni Rezervasyon Talebi",
            "message": f"{requester_name} - {reservation_data['date']} tarihinde {total_hours} saatlik rezervasyon talebi",
            "related_id": reservation_id,
            "related_type": "reservation",
            "is_read": False,
            "created_at": datetime.utcnow(),
            "data": {
                "reservation_id": reservation_id,
                "customer_name": requester_name,
                "customer_id": actual_user_id,
                "date": reservation_data['date'],
                "total_hours": total_hours
            }
        }
        await db.notifications.insert_one(notification_data)
        
        # Send push notification
        try:
            from push_notification_service import PushNotificationService
            push_service = PushNotificationService()
            await push_service.send_push_notification(
                db,
                venue["owner_id"],
                "Yeni Rezervasyon Talebi",
                f"{requester_name} - {reservation_data['date']} tarihinde {total_hours} saatlik rezervasyon talebi"
            )
        except Exception as e:
            print(f"Failed to send push notification: {e}")
        
    elif "coach_id" in reservation_data:
        # Coach reservation
        coach = await db.users.find_one({"id": reservation_data["coach_id"], "user_type": "coach"})
        if not coach:
            raise HTTPException(status_code=404, detail="Coach not found")
        
        # ✅ CRITICAL: hourly_rate direkt user objesinde, coach_profile içinde değil!
        # Önce direkt field'a bak, yoksa profile'a bak
        hourly_rate = coach.get("hourly_rate") or coach.get("coach_profile", {}).get("hourly_rate", 0)
        total_price = hourly_rate  # 1 hour session
        
        reservation = {
            "id": reservation_id,
            "type": "coach",  # ✅ Tutarlılık için hem type hem reservation_type
            "reservation_type": "coach",
            "coach_id": reservation_data["coach_id"],
            "user_id": current_user_id,
            "date": reservation_data["date"],
            "hour": reservation_data["hour"],
            "hourly_rate": hourly_rate,
            "total_price": total_price,
            "status": "pending",
            "notes": reservation_data.get("notes", ""),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.reservations.insert_one(reservation)
        
        # Talep eden kullanıcının bilgilerini al
        # CRITICAL: current_user_id bazen dict olabiliyor
        actual_user_id = current_user_id
        if isinstance(current_user_id, dict):
            actual_user_id = current_user_id.get("id")
        
        requester = await db.users.find_one({"id": actual_user_id})
        requester_name = requester.get("full_name", "İsimsiz Kullanıcı") if requester else "İsimsiz Kullanıcı"
        requester_phone = requester.get("phone_number", "") if requester else ""
        requester_id = actual_user_id
        
        # Kaydedilen reservation'dan total_price al
        saved_reservation = await db.reservations.find_one({"id": reservation_id})
        actual_total_price = saved_reservation.get("total_price", 0) if saved_reservation else 0
        
        # Create notification for coach
        notification_data = {
            "id": str(uuid.uuid4()),
            "user_id": reservation_data["coach_id"],
            "notification_type": "reservation_request",
            "title": "Yeni Antrenman Talebi",
            "message": f"{requester_name} {reservation_data['date']} tarihinde {reservation_data['hour']} saatinde antrenman talep ediyor",
            "related_id": reservation_id,
            "related_type": "reservation",
            "is_read": False,
            "created_at": datetime.utcnow(),
            "data": {
                "reservation_id": reservation_id,
                "customer_name": requester_name,
                "customer_phone": requester_phone,
                "customer_id": requester_id,
                "date": reservation_data.get("date"),
                "hour": reservation_data.get("hour"),
                "total_price": actual_total_price  # DB'den alınan gerçek fiyat
            }
        }
        await db.notifications.insert_one(notification_data)
        
        # Send push notification
        try:
            from push_notification_service import PushNotificationService
            push_service = PushNotificationService()
            await push_service.send_push_notification(
                db,
                reservation_data["coach_id"],
                "Yeni Antrenman Talebi",
                f"{requester_name} - {reservation_data['date']} tarihinde {reservation_data['hour']} saatinde antrenman talebi"
            )
        except Exception as e:
            print(f"Failed to send push notification: {e}")
        
    elif "referee_id" in reservation_data:
        # Referee reservation
        referee = await db.users.find_one({"id": reservation_data["referee_id"], "user_type": "referee"})
        if not referee:
            raise HTTPException(status_code=404, detail="Referee not found")
        
        # ✅ CRITICAL: hourly_rate direkt user objesinde, referee_profile içinde değil!
        # Önce direkt field'a bak, yoksa profile'a bak
        hourly_rate = referee.get("hourly_rate") or referee.get("referee_profile", {}).get("hourly_rate", 0)
        total_price = hourly_rate  # 1 hour session
        
        reservation = {
            "id": reservation_id,
            "type": "referee",  # ✅ Tutarlılık için hem type hem reservation_type
            "reservation_type": "referee",
            "referee_id": reservation_data["referee_id"],
            "user_id": current_user_id,
            "date": reservation_data["date"],
            "hour": reservation_data["hour"],
            "hourly_rate": hourly_rate,
            "total_price": total_price,
            "status": "pending",
            "notes": reservation_data.get("notes", ""),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.reservations.insert_one(reservation)
        
        # ✅ Talep eden kullanıcının bilgilerini al
        actual_user_id = current_user_id
        if isinstance(current_user_id, dict):
            actual_user_id = current_user_id.get("id")
        
        requester = await db.users.find_one({"id": actual_user_id})
        requester_name = requester.get("full_name", "Misafir") if requester else "Misafir"
        
        # Create notification for referee
        notification_data = {
            "id": str(uuid.uuid4()),
            "user_id": reservation_data["referee_id"],
            "notification_type": "reservation_request",
            "title": "Yeni Hakemlik Talebi",
            "message": f"{requester_name} - {reservation_data['date']} tarihinde {reservation_data['hour']} saatinde hakemlik talebi",
            "related_id": reservation_id,
            "related_type": "reservation",
            "is_read": False,
            "created_at": datetime.utcnow(),
            "data": {
                "reservation_id": reservation_id,
                "customer_name": requester_name,
                "customer_id": actual_user_id,
                "date": reservation_data.get("date"),
                "hour": reservation_data.get("hour")
            }
        }
        await db.notifications.insert_one(notification_data)
        
        # Send push notification
        try:
            from push_notification_service import PushNotificationService
            push_service = PushNotificationService()
            await push_service.send_push_notification(
                db,
                reservation_data["referee_id"],
                "Yeni Hakemlik Talebi",
                f"{requester_name} - {reservation_data['date']} tarihinde {reservation_data['hour']} saatinde hakemlik talebi"
            )
        except Exception as e:
            print(f"Failed to send push notification: {e}")
    
    elif "player_id" in reservation_data:
        # Player reservation
        player = await db.users.find_one({"id": reservation_data["player_id"], "user_type": "player"})
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        # Determine price based on price type
        price_type = reservation_data.get("price_type", "hourly")
        if price_type == "hourly":
            total_price = player.get("hourly_rate", 0)
        elif price_type == "match":
            total_price = player.get("match_fee", 0)
        elif price_type == "daily":
            total_price = player.get("daily_rate", 0)
        elif price_type == "monthly":
            total_price = player.get("monthly_membership", 0)
        else:
            total_price = 0
        
        reservation = {
            "id": reservation_id,
            "type": "player",  # ✅ Tutarlılık için hem type hem reservation_type
            "reservation_type": "player",
            "player_id": reservation_data["player_id"],
            "user_id": current_user_id,
            "price_type": price_type,
            "total_price": total_price,
            "selected_date": reservation_data.get("selected_date"),
            "selected_day": reservation_data.get("selected_day"),
            "selected_hour": reservation_data.get("selected_hour"),
            "status": "pending",
            "notes": reservation_data.get("notes", ""),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.reservations.insert_one(reservation)
        
        # ✅ Talep eden kullanıcının bilgilerini al
        actual_user_id = current_user_id
        if isinstance(current_user_id, dict):
            actual_user_id = current_user_id.get("id")
        
        requester = await db.users.find_one({"id": actual_user_id})
        requester_name = requester.get("full_name", "Misafir") if requester else "Misafir"
        
        # Create notification for player
        price_type_tr = {
            "hourly": "Saatlik",
            "match": "Maç",
            "daily": "Günlük",
            "monthly": "Aylık"
        }
        notification_data = {
            "id": str(uuid.uuid4()),
            "user_id": reservation_data["player_id"],
            "notification_type": "reservation_request",
            "title": "Yeni Oyuncu Rezervasyon Talebi",
            "message": f"{requester_name} - {price_type_tr.get(price_type, price_type)} üzerinden rezervasyon talebi ({total_price} TL)",
            "related_id": reservation_id,
            "related_type": "reservation",
            "is_read": False,
            "created_at": datetime.utcnow(),
            "data": {
                "reservation_id": reservation_id,
                "customer_name": requester_name,
                "customer_id": actual_user_id,
                "price_type": price_type,
                "total_price": total_price
            }
        }
        await db.notifications.insert_one(notification_data)
        
        # Send push notification
        try:
            from push_notification_service import PushNotificationService
            push_service = PushNotificationService()
            await push_service.send_push_notification(
                db,
                reservation_data["player_id"],
                "Yeni Oyuncu Rezervasyon Talebi",
                f"{requester_name} - {price_type_tr.get(price_type, price_type)} üzerinden rezervasyon talebi ({total_price} TL)"
            )
        except Exception as e:
            print(f"Failed to send push notification: {e}")
    else:
        raise HTTPException(status_code=400, detail="Invalid reservation type")
    
    reservation.pop("_id", None)
    return {"message": "Reservation created", "reservation": reservation}

@api_router.get("/participations/my")
async def get_my_participations(
    current_user: dict = Depends(get_current_user)
):
    """Get events the current user has joined"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    try:
        result = []
        added_event_ids = set()
        
        # 1. Old participations collection
        participations = await db.participations.find({"user_id": current_user_id}).to_list(1000)
        for participation in participations:
            event = await db.events.find_one({"id": participation["event_id"]})
            if event and event["id"] not in added_event_ids:
                event.pop("_id", None)
                result.append({
                    "participation_id": str(participation["_id"]),
                    "joined_at": participation.get("joined_at"),
                    "event": event
                })
                added_event_ids.add(event["id"])
        
        # 2. New event_participants (paid events)
        event_participants = await db.event_participants.find({
            "user_id": current_user_id,
            "status": {"$in": ["confirmed", "approved"]}
        }).to_list(1000)
        
        for participant in event_participants:
            event = await db.events.find_one({"id": participant["event_id"]})
            if event and event["id"] not in added_event_ids:
                event.pop("_id", None)
                result.append({
                    "participation_id": participant.get("id"),
                    "joined_at": participant.get("created_at"),
                    "status": participant.get("status"),
                    "payment_status": participant.get("payment_status"),
                    "event": event
                })
                added_event_ids.add(event["id"])
        
        # 3. Check events where user is in participants array (free events with direct join)
        # This handles cases where user joined via the old join system
        events_with_user = await db.events.find({
            "$or": [
                {"participants": current_user_id},  # String format
                {"participants.id": current_user_id},  # Object format with id
                {"participants.user_id": current_user_id}  # Object format with user_id
            ],
            "status": {"$in": ["active", "pending", "approved"]}
        }).to_list(1000)
        
        for event in events_with_user:
            if event["id"] not in added_event_ids:
                event.pop("_id", None)
                result.append({
                    "participation_id": f"event-{event['id']}",
                    "joined_at": event.get("created_at"),
                    "status": "joined",
                    "event": event
                })
                added_event_ids.add(event["id"])
        
        logging.info(f"📅 Found {len(result)} participations for user {current_user_id}")
        return result
    except Exception as e:
        logging.error(f"Error getting participations: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

@api_router.get("/events/{event_id}/check-participation")
async def check_event_participation(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Check if current user is a participant of the event"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    try:
        # 1. Event'in participants listesini kontrol et
        event = await db.events.find_one({"id": event_id})
        if event:
            participants = event.get("participants", [])
            for p in participants:
                # String olarak kontrol
                if isinstance(p, str) and p == current_user_id:
                    return {"is_participant": True, "source": "event_participants_string"}
                # Object olarak kontrol
                if isinstance(p, dict) and (p.get("id") == current_user_id or p.get("user_id") == current_user_id):
                    return {"is_participant": True, "source": "event_participants_object"}
        
        # 2. participations koleksiyonunu kontrol et (cancelled olmayanlar)
        participation = await db.participations.find_one({
            "event_id": event_id,
            "user_id": current_user_id,
            "status": {"$nin": ["cancelled"]}  # Cancelled olanları hariç tut
        })
        if participation:
            return {"is_participant": True, "source": "participations"}
        
        # 2b. participations'da user_id object olarak saklanmış olabilir
        all_participations = await db.participations.find({
            "event_id": event_id,
            "status": {"$nin": ["cancelled"]}
        }).to_list(100)
        for p in all_participations:
            user_id = p.get("user_id")
            if isinstance(user_id, dict) and (user_id.get("id") == current_user_id):
                return {"is_participant": True, "source": "participations_object"}
        
        # 3. event_participants koleksiyonunu kontrol et (ödeme yapılmış ve cancelled olmayan)
        event_participant = await db.event_participants.find_one({
            "event_id": event_id,
            "user_id": current_user_id,
            "status": {"$in": ["confirmed", "approved"]}  # Zaten sadece confirmed/approved kontrol ediliyor
        })
        if event_participant:
            return {"is_participant": True, "source": "event_participants_paid"}
        
        # 4. payments koleksiyonunu kontrol et (ödeme tamamlanmış)
        payment = await db.payments.find_one({
            "event_id": event_id,
            "user_id": current_user_id,
            "status": {"$in": ["completed", "payment_completed", "success"]}
        })
        if payment:
            # Ödeme var ama event_participants cancelled olmuş olabilir, kontrol et
            ep_cancelled = await db.event_participants.find_one({
                "event_id": event_id,
                "user_id": current_user_id,
                "status": "cancelled"
            })
            if ep_cancelled:
                return {"is_participant": False, "reason": "cancelled"}
            return {"is_participant": True, "source": "payments"}
        
        return {"is_participant": False}
    except Exception as e:
        logging.error(f"Error checking participation: {str(e)}")
        return {"is_participant": False, "error": str(e)}

@api_router.get("/participations/event/{event_id}")
async def get_event_participations(
    event_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Get all participants for an event"""
    try:
        # Verify user is the organizer
        event = await db.events.find_one({"id": event_id})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Get participations
        participations = await db.participations.find({"event_id": event_id}).to_list(1000)
        
        # Enrich with user data
        result = []
        for participation in participations:
            user = await db.users.find_one({"id": participation["user_id"]})
            if user:
                result.append({
                    "id": str(participation["_id"]),
                    "user_id": participation["user_id"],
                    "full_name": user.get("full_name", ""),
                    "email": user.get("email", ""),
                    "status": participation.get("status", "pending"),
                    "skill_level": participation.get("skill_level"),
                    "approved": participation.get("approved", False),
                })
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting event participants: {str(e)}")
        return []


@api_router.get("/venues/by-city/{city}")
async def get_venues_by_city(city: str):
    """Get active venues in a specific city"""
    try:
        venues = await db.venues.find({
            "city": city,
            "is_active": True,
            "approved": True
        }).to_list(100)
        
        # Remove sensitive data and add only necessary fields
        result = []
        for venue in venues:
            venue.pop("_id", None)
            venue.pop("owner_id", None)
            result.append({
                "id": venue.get("id"),
                "name": venue.get("name"),
                "address": venue.get("address"),
                "city": venue.get("city"),
                "sports": venue.get("sports", []),
            })
        
        return result
    except Exception as e:
        logging.error(f"Error getting venues by city: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/reservations/my")
async def get_my_reservations(
    current_user: dict = Depends(get_current_user)
):
    """Get current user's reservations (both made by user and made to user)"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    try:
        # Get user info to find reservations made TO this user
        current_user_obj = await db.users.find_one({"id": current_user_id})
        
        # Reservations made BY user
        # CRITICAL: user_id can be string OR dict {"id": "...", "user_type": "..."}
        my_requests = await db.reservations.find({
            "$or": [
                {"user_id": current_user_id},
                {"user_id.id": current_user_id}  # For dict format
            ]
        }).to_list(100)
        
        # Reservations made TO user (for players, coaches, referees, venues)
        reservations_to_me = []
        if current_user_obj:
            user_type = current_user.get("user_type")
            if user_type in ["player", "coach", "referee", "venue_owner"]:
                # Find reservations where this user is the provider
                reservations_to_me = await db.reservations.find({
                    "$or": [
                        {"player_id": current_user_id},
                        {"coach_id": current_user_id},
                        {"referee_id": current_user_id},
                        {"venue_id": current_user_id}
                    ]
                }).to_list(100)
        
        # Combine both lists
        all_reservations = my_requests + reservations_to_me
        
        # Enrich with venue/coach/referee/player data
        for reservation in all_reservations:
            reservation.pop("_id", None)
            
            # Venue enrichment
            if reservation.get("venue_id"):
                venue = await db.venues.find_one({"id": reservation["venue_id"]})
                if venue:
                    reservation["venue_name"] = venue.get("name")
                    reservation["venue_address"] = venue.get("address")
            
            # Player enrichment
            if reservation.get("player_id"):
                player = await db.users.find_one({"id": reservation["player_id"]})
                if player:
                    reservation["player_name"] = player.get("full_name")
            
            # Coach enrichment
            if reservation.get("coach_id"):
                coach = await db.users.find_one({"id": reservation["coach_id"]})
                if coach:
                    reservation["coach_name"] = coach.get("full_name")
            
            # Referee enrichment
            if reservation.get("referee_id"):
                referee = await db.users.find_one({"id": reservation["referee_id"]})
                if referee:
                    reservation["referee_name"] = referee.get("full_name")
        
        return all_reservations
    except Exception as e:
        logging.error(f"Error getting reservations: {str(e)}")
        return []

@api_router.get("/reservations/pending")
async def get_pending_reservations(
    current_user_id: str = Depends(get_current_user)
):
    """Get pending reservations for venue owner"""
    # Get venues owned by current user
    venues = await db.venues.find({"owner_id": current_user_id}).to_list(100)
    venue_ids = [v["id"] for v in venues]
    
    # Get pending reservations for these venues
    reservations = await db.reservations.find({
        "venue_id": {"$in": venue_ids},
        "status": "pending"
    }).to_list(100)
    
    # Enrich with user and venue data
    for reservation in reservations:
        reservation.pop("_id", None)
        
        # User data
        user = await db.users.find_one({"id": reservation["user_id"]})
        if user:
            reservation["user_name"] = user.get("full_name")
            reservation["user_phone"] = user.get("phone")
        
        # Venue data
        venue = await db.venues.find_one({"id": reservation["venue_id"]})
        if venue:
            reservation["venue_name"] = venue.get("name")
    
    return {"reservations": reservations}

@api_router.get("/calendar/upcoming-reminders")
async def get_upcoming_reminders(
    current_user_id: str = Depends(get_current_user)
):
    """Get upcoming events and reservations for reminder badges (24h and 1h)"""
    try:
        now = datetime.now(timezone.utc)
        within_24h_time = now + timedelta(hours=24)
        within_1h_time = now + timedelta(hours=1)
        
        within_24h = []
        within_1h = []
        
        # Get user's event participations
        participations = await db.participations.find({
            "user_id": current_user_id,
            "status": "approved"
        }).to_list(1000)
        
        for participation in participations:
            event = await db.events.find_one({"id": participation["event_id"]})
            if event and event.get("start_date"):
                event_time = datetime.fromisoformat(event["start_date"].replace('Z', '+00:00'))
                
                # Check if event is in the future
                if event_time > now:
                    hours_until = (event_time - now).total_seconds() / 3600
                    
                    if hours_until <= 1:
                        within_1h.append({
                            "id": event["id"],
                            "title": event.get("title", "Etkinlik"),
                            "type": "event",
                            "date": event["start_date"],
                            "hours_until": round(hours_until, 1),
                            "location": event.get("city"),
                        })
                    elif hours_until <= 24:
                        within_24h.append({
                            "id": event["id"],
                            "title": event.get("title", "Etkinlik"),
                            "type": "event",
                            "date": event["start_date"],
                            "hours_until": round(hours_until, 1),
                            "location": event.get("city"),
                        })
        
        # Get user's reservations (both made and received)
        current_user = await db.users.find_one({"id": current_user_id})
        
        # Reservations made BY user
        reservations = await db.reservations.find({
            "user_id": current_user_id,
            "status": "confirmed"
        }).to_list(1000)
        
        # Reservations made TO user
        if current_user:
            user_type = current_user.get("user_type")
            if user_type in ["player", "coach", "referee", "venue_owner"]:
                reservations_to_me = await db.reservations.find({
                    "$or": [
                        {"player_id": current_user_id},
                        {"coach_id": current_user_id},
                        {"referee_id": current_user_id},
                        {"venue_id": current_user_id}
                    ],
                    "status": "confirmed"
                }).to_list(1000)
                reservations.extend(reservations_to_me)
        
        for reservation in reservations:
            if reservation.get("date") and reservation.get("start_time"):
                # Combine date and start_time
                reservation_date = datetime.fromisoformat(reservation["date"].replace('Z', '+00:00'))
                start_time = datetime.fromisoformat(reservation["start_time"].replace('Z', '+00:00'))
                
                # Create full datetime
                reservation_datetime = datetime.combine(
                    reservation_date.date(),
                    start_time.time(),
                    tzinfo=timezone.utc
                )
                
                # Check if reservation is in the future
                if reservation_datetime > now:
                    hours_until = (reservation_datetime - now).total_seconds() / 3600
                    
                    # Get venue name if exists
                    venue_name = None
                    if reservation.get("venue_id"):
                        venue = await db.venues.find_one({"id": reservation["venue_id"]})
                        if venue:
                            venue_name = venue.get("name")
                    
                    reservation_item = {
                        "id": reservation["id"],
                        "title": f"Rezervasyon - {venue_name or 'Yer'}",
                        "type": "reservation",
                        "date": reservation["date"],
                        "start_time": reservation["start_time"],
                        "hours_until": round(hours_until, 1),
                        "venue_name": venue_name,
                    }
                    
                    if hours_until <= 1:
                        within_1h.append(reservation_item)
                    elif hours_until <= 24:
                        within_24h.append(reservation_item)
        
        total_count = len(within_24h) + len(within_1h)
        
        logging.info(f"📅 Calendar reminders for user {current_user_id}: 24h={len(within_24h)}, 1h={len(within_1h)}, total={total_count}")
        
        # Calendar items için okunmamış sayısını ekle
        # CRITICAL: current_user bazen dict olabilir, id'yi extract et
        user_id_for_query = current_user_id
        if isinstance(current_user_id, dict):
            user_id_for_query = current_user_id.get("id")
        
        logging.info(f"📅 Querying calendar items for user: {user_id_for_query}")
        
        # ✅ CRITICAL: Orphaned items'ları da filtrelememiz gerekiyor
        # Sadece geçerli rezervasyonu olan okunmamış item'ları sayalım
        valid_unread_count = 0  # ✅ Önce tanımla (exception durumu için)
        
        try:
            unread_calendar_items_cursor = db.calendar_items.find({
                "user_id": user_id_for_query,
                "is_read": False
            })
            
            unread_calendar_items_list = await unread_calendar_items_cursor.to_list(length=1000)
            
            # Reservation veya Event olan item'ları filtrele
            orphaned_ids = []  # Temizlenecek orphaned item'lar
            
            for item in unread_calendar_items_list:
                item_type = item.get("type")
                item_id = item.get("id", "unknown")
                
                logging.info(f"📅 Checking calendar item: {item_id}, type={item_type}")
                
                if item_type == "event":
                    # Event tipi - participation'ın hala var olup olmadığını kontrol et
                    event_id = item.get("event_id")
                    logging.info(f"📅 Event item {item_id}: event_id={event_id}")
                    if event_id:
                        participation = await db.participations.find_one({
                            "event_id": event_id,
                            "user_id": user_id_for_query
                        })
                        if participation:
                            logging.info(f"📅 Event item {item_id}: participation FOUND, status={participation.get('status')}")
                            valid_unread_count += 1
                        else:
                            # Participation silinmiş - orphaned item
                            orphaned_ids.append(item.get("_id"))
                            logging.warning(f"⚠️ Orphaned calendar item - no participation: {item_id}")
                    else:
                        # event_id yok - muhtemelen orphaned
                        orphaned_ids.append(item.get("_id"))
                        logging.warning(f"⚠️ Event calendar item without event_id: {item_id}")
                elif item_type == "match":
                    # Match tipi - event_id varsa participation kontrolü yap
                    event_id = item.get("event_id")
                    if event_id:
                        participation = await db.participations.find_one({
                            "event_id": event_id,
                            "user_id": user_id_for_query
                        })
                        if participation:
                            valid_unread_count += 1
                        else:
                            # Match için participation yok - orphaned
                            orphaned_ids.append(item.get("_id"))
                            logging.warning(f"⚠️ Orphaned match calendar item - no participation: {item.get('id')}")
                    else:
                        # event_id yok - orphaned
                        orphaned_ids.append(item.get("_id"))
                        logging.warning(f"⚠️ Match calendar item without event_id: {item.get('id')}")
                else:
                    # Reservation tipi - rezervasyonun var olup olmadığını kontrol et
                    reservation_id = item.get("reservation_id")
                    if reservation_id:
                        reservation = await db.reservations.find_one({"id": reservation_id})
                        if reservation:
                            valid_unread_count += 1
                        else:
                            orphaned_ids.append(item.get("_id"))
                            logging.warning(f"⚠️ Orphaned calendar item (badge count) - no reservation: {item.get('id')}")
                    else:
                        # reservation_id yok ama type da event değil - orphaned olabilir
                        orphaned_ids.append(item.get("_id"))
                        logging.warning(f"⚠️ Calendar item without reservation_id or event type: {item.get('id')}")
            
            # Orphaned item'ları otomatik olarak okundu işaretle
            if orphaned_ids:
                await db.calendar_items.update_many(
                    {"_id": {"$in": orphaned_ids}},
                    {"$set": {"is_read": True}}
                )
                logging.info(f"🧹 Auto-marked {len(orphaned_ids)} orphaned calendar items as read")
            
            logging.info(f"📅 Calendar unread items: {valid_unread_count} (filtered from {len(unread_calendar_items_list)} total)")
        except Exception as count_error:
            logging.error(f"❌ Error counting unread calendar items: {str(count_error)}")
            valid_unread_count = 0
        
        return {
            "within_24h": within_24h,
            "within_1h": within_1h,
            "total_count": total_count,
            "unread_count": valid_unread_count  # ✅ Filtered unread count (orphaned items excluded)
        }
    except Exception as e:
        logging.error(f"Error getting calendar reminders: {str(e)}")
        return {
            "within_24h": [],
            "within_1h": [],
            "total_count": 0,
            "unread_count": 0
        }



@api_router.get("/calendar/items")
async def get_calendar_items(
    current_user: dict = Depends(get_current_user)
):
    """
    Get all calendar items for the current user
    Includes: person reservations (coach, referee, player)
    """
    try:
        user_id = current_user.get("id")
        
        logging.info(f"📅 Fetching calendar items for user: {user_id}")
        
        # Calendar items'ları al (ödeme sonrası eklenen rezervasyonlar)
        calendar_items_cursor = db.calendar_items.find({
            "user_id": user_id
        }).sort("created_at", -1)  # En yeni önce
        
        calendar_items = await calendar_items_cursor.to_list(length=1000)
        
        logging.info(f"📅 Found {len(calendar_items)} calendar items")
        
        # Format ve enrich et
        result_items = []
        for item in calendar_items:
            item_type = item.get("type")
            
            # Event tipi item'lar için reservation kontrolü yapmadan direkt ekle
            if item_type == "event":
                # Event'in gerçek ID'sini bul
                event_id = item.get("event_id")
                
                # Event bilgilerini al (isteğe bağlı - zenginleştirmek için)
                event = None
                if event_id:
                    event = await db.events.find_one({"id": event_id})
                
                formatted_item = {
                    "id": item.get("id"),  # Calendar item ID
                    "type": item_type,
                    "title": item.get("title"),
                    "date": item.get("date"),
                    "start_time": item.get("start_time"),
                    "end_time": item.get("end_time"),
                    "location": item.get("location"),
                    "description": item.get("description"),
                    "is_read": item.get("is_read", False),
                    "created_at": item.get("created_at"),
                    "event_id": event_id,  # ✅ CRITICAL: Event ID'sini ekle
                }
                
                # Event bilgisi varsa, ek detaylar ekle
                if event:
                    formatted_item["event_title"] = event.get("title")
                    formatted_item["event_city"] = event.get("city")
                
                result_items.append(formatted_item)
                logging.info(f"✅ Added event calendar item: {item.get('title')} (event_id: {event_id})")
                continue
            
            # Reservation tipi item'lar için detayları al
            # TİPLER: "reservation" (facility rezervasyonu), "reservation_out" (kişi rezervasyonu - giden), "reservation_in" (kişi rezervasyonu - gelen)
            reservation_id = item.get("reservation_id")
            reservation = None
            if reservation_id:
                reservation = await db.reservations.find_one({"id": reservation_id})
            
            logging.info(f"🔍 Processing calendar item: type={item_type}, title={item.get('title')[:30]}, has_reservation={reservation is not None}")
            
            # ✅ FACILITY RESERVATION: Eğer type "reservation" ise (facility_fields rezervasyonu), direkt ekle
            if item_type == "reservation":
                logging.info(f"  ➡️ Processing as FACILITY RESERVATION")
                
                # Tarih formatlarını düzenle - frontend için ISO string
                date_str = item.get("date")
                start_time_str = item.get("start_time")
                end_time_str = item.get("end_time")
                
                # Eğer sadece tarih varsa (YYYY-MM-DD), ISO formatına çevir
                if date_str and isinstance(date_str, str) and len(date_str) == 10:
                    date_str = f"{date_str}T00:00:00"
                
                # Eğer sadece saat varsa (HH:MM), bugünün tarihiyle birleştir
                if start_time_str and isinstance(start_time_str, str) and len(start_time_str) <= 5:
                    start_time_str = f"{item.get('date')}T{start_time_str}:00"
                if end_time_str and isinstance(end_time_str, str) and len(end_time_str) <= 5:
                    end_time_str = f"{item.get('date')}T{end_time_str}:00"
                
                formatted_item = {
                    "id": item.get("id"),
                    "type": "facility_reservation",  # Frontend için belirgin tip
                    "title": item.get("title"),
                    "date": date_str,
                    "start_time": start_time_str,
                    "end_time": end_time_str,
                    "location": item.get("location"),
                    "description": item.get("description"),
                    "is_read": item.get("is_read", False),
                    "created_at": item.get("created_at"),
                    "reservation_id": reservation_id,
                    # ✅ Müşteri bilgilerini ekle (tesis sahibi için)
                    "customer_name": item.get("customer_name"),
                    "customer_phone": item.get("customer_phone"),
                    "customer_id": item.get("customer_id"),
                }
                
                # Reservation detaylarını ekle (eğer varsa)
                if reservation:
                    formatted_item["reservation_status"] = reservation.get("status")
                    formatted_item["payment_status"] = reservation.get("payment_status")
                    formatted_item["total_price"] = reservation.get("total_price")
                    formatted_item["facility_id"] = reservation.get("facility_id")
                    formatted_item["field_id"] = reservation.get("field_id")
                    
                    # Eğer calendar item'da müşteri bilgisi yoksa, reservation'dan al
                    if not formatted_item.get("customer_name") and reservation.get("user_id"):
                        customer = await db.users.find_one({"id": reservation.get("user_id")})
                        if customer:
                            formatted_item["customer_name"] = customer.get("full_name", "")
                            formatted_item["customer_phone"] = customer.get("phone", "") or customer.get("phone_number", "")
                            formatted_item["customer_id"] = reservation.get("user_id")
                    
                    logging.info(f"  ✅ Added reservation details: status={reservation.get('status')}, customer={formatted_item.get('customer_name')}")
                else:
                    logging.warning(f"  ⚠️ No reservation found for reservation_id={reservation_id}")
                
                result_items.append(formatted_item)
                logging.info(f"✅ Added facility reservation calendar item: {item.get('title')}")
                continue
            
            # ✅ CRITICAL: Eğer reservation yoksa (orphaned item), skip et (sadece person reservation için)
            if not reservation:
                logging.warning(f"⚠️ Orphaned calendar item found - no reservation: {item.get('id')}")
                continue
            
            # User bilgilerini al (karşı taraf için)
            other_user = None
            if reservation:
                # Eğer giden rezervasyon ise (reservation_out), karşı tarafı bul
                if item.get("type") == "reservation_out":
                    # Coach, referee, veya player ID'sini bul
                    res_type = reservation.get("type") or reservation.get("reservation_type")
                    if res_type:
                        other_user_id = reservation.get(f"{res_type}_id")
                        if other_user_id:
                            other_user = await db.users.find_one({"id": other_user_id})
                # Eğer gelen rezervasyon ise (reservation_in), talep edeni bul
                elif item.get("type") == "reservation_in":
                    requester_id = reservation.get("user_id")
                    if isinstance(requester_id, dict):
                        requester_id = requester_id.get("id")
                    if requester_id:
                        other_user = await db.users.find_one({"id": requester_id})
            
            formatted_item = {
                "id": item.get("id"),
                "type": item.get("type"),
                "title": item.get("title"),
                "date": item.get("date"),
                "hour": item.get("hour"),
                "is_read": item.get("is_read", False),
                "created_at": item.get("created_at"),
                "reservation_id": reservation_id,
            }
            
            # Reservation detaylarını ekle
            if reservation:
                formatted_item["reservation_status"] = reservation.get("status")
                formatted_item["payment_status"] = reservation.get("payment_status")
                formatted_item["total_price"] = reservation.get("total_price")
            
            # Karşı taraf bilgilerini ekle
            if other_user:
                formatted_item["other_user"] = {
                    "id": other_user.get("id"),
                    "full_name": other_user.get("full_name"),
                    "phone": other_user.get("phone"),
                    "user_type": other_user.get("user_type")
                }
            
            # MongoDB _id'yi kaldır
            formatted_item.pop("_id", None)
            
            result_items.append(formatted_item)
        
        logging.info(f"📅 Returning {len(result_items)} formatted calendar items")
        
        # ✅ DEBUG: Log is_read values
        for item in result_items[:3]:  # İlk 3 item
            logging.info(f"📅 DEBUG Item: id={item.get('id')[:8]}..., is_read={item.get('is_read')}, title={item.get('title')}")
        
        # ✅ CRITICAL DEBUG: Eğer boş liste döndürüyorsa nedenini logla
        if len(result_items) == 0 and len(calendar_items) > 0:
            logging.error(f"❌ CRITICAL: {len(calendar_items)} calendar items bulundu ama hepsi filtrelendi!")
            for item in calendar_items[:3]:
                res_id = item.get("reservation_id")
                res = await db.reservations.find_one({"id": res_id}) if res_id else None
                logging.error(f"   Calendar Item: {item.get('id')[:15]}... | Res ID: {res_id[:15] if res_id else 'None'}... | Res Exists: {res is not None} | Res Type: {res.get('type') if res else 'N/A'}")
        
        return {
            "success": True,
            "items": result_items,
            "total": len(result_items)
        }
        
    except Exception as e:
        logging.error(f"❌ Error fetching calendar items: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/calendar/items/{item_id}/mark-read")
async def mark_calendar_item_read(
    item_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Mark a calendar item as read"""
    try:
        user_id = current_user.get("id")
        
        logging.info(f"📅 Marking calendar item as read: item_id={item_id}, user_id={user_id}")
        
        # Calendar item'ı bul ve kullanıcıya ait olduğunu kontrol et
        item = await db.calendar_items.find_one({"id": item_id, "user_id": user_id})
        if not item:
            logging.warning(f"❌ Calendar item not found: {item_id} for user {user_id}")
            # Item bulunamadıysa, belki event_id veya başka bir şekilde arayalım
            item = await db.calendar_items.find_one({"id": item_id})
            if item:
                logging.warning(f"⚠️ Calendar item found but belongs to user {item.get('user_id')}, not {user_id}")
            raise HTTPException(status_code=404, detail="Calendar item bulunamadı")
        
        logging.info(f"✅ Calendar item found, current is_read={item.get('is_read')}")
        
        # Okundu olarak işaretle
        result = await db.calendar_items.update_one(
            {"id": item_id},
            {"$set": {"is_read": True}}
        )
        
        logging.info(f"✅ Update result: matched={result.matched_count}, modified={result.modified_count}")
        
        return {"success": True, "message": "Calendar item okundu olarak işaretlendi"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ Error marking calendar item as read: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/calendar/mark-all-read")
async def mark_all_calendar_items_read(
    current_user: dict = Depends(get_current_user)
):
    """Mark all calendar items as read for current user"""
    try:
        user_id = current_user.get("id")
        
        logging.info(f"📅 Marking all calendar items as read for user: {user_id}")
        
        # Tüm okunmamış item'ları okundu olarak işaretle
        result = await db.calendar_items.update_many(
            {"user_id": user_id, "is_read": False},
            {"$set": {"is_read": True}}
        )
        
        logging.info(f"📅 Marked {result.modified_count} calendar items as read")
        
        return {
            "success": True,
            "message": f"{result.modified_count} takvim öğesi okundu olarak işaretlendi",
            "modified_count": result.modified_count
        }
    except Exception as e:
        logging.error(f"❌ Error marking all calendar items as read: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/calendar/cleanup-orphaned")
async def cleanup_orphaned_calendar_items(
    current_user: dict = Depends(get_current_user)
):
    """Cleanup orphaned calendar items (mark as read) for current user"""
    try:
        user_id = current_user.get("id")
        
        logging.info(f"🧹 Cleaning up orphaned calendar items for user: {user_id}")
        
        # Kullanıcının tüm okunmamış calendar item'larını bul
        unread_items = await db.calendar_items.find({
            "user_id": user_id,
            "is_read": False
        }).to_list(length=1000)
        
        orphaned_count = 0
        cleaned_ids = []
        
        for item in unread_items:
            item_type = item.get("type")
            item_id = item.get("id")
            is_orphaned = False
            
            if item_type == "event":
                # Event için participation kontrol et
                event_id = item.get("event_id")
                if event_id:
                    participation = await db.participations.find_one({
                        "event_id": event_id,
                        "user_id": user_id
                    })
                    if not participation:
                        # Event var mı kontrol et
                        event = await db.events.find_one({"id": event_id})
                        if not event:
                            is_orphaned = True
                            logging.info(f"🧹 Orphaned event calendar item (no event): {item_id}")
                        else:
                            # Event var ama participation yok - belki eski katılım
                            is_orphaned = True
                            logging.info(f"🧹 Orphaned event calendar item (no participation): {item_id}")
                else:
                    # event_id yok
                    is_orphaned = True
                    logging.info(f"🧹 Orphaned event calendar item (no event_id): {item_id}")
                    
            elif item_type == "match":
                # Match için event ve participation kontrol et
                event_id = item.get("event_id")
                if event_id:
                    participation = await db.participations.find_one({
                        "event_id": event_id,
                        "user_id": user_id
                    })
                    if not participation:
                        is_orphaned = True
                        logging.info(f"🧹 Orphaned match calendar item: {item_id}")
                else:
                    is_orphaned = True
                    
            else:
                # Reservation tipi
                reservation_id = item.get("reservation_id")
                if reservation_id:
                    reservation = await db.reservations.find_one({"id": reservation_id})
                    if not reservation:
                        is_orphaned = True
                        logging.info(f"🧹 Orphaned reservation calendar item: {item_id}")
                else:
                    is_orphaned = True
                    logging.info(f"🧹 Calendar item without reservation_id: {item_id}")
            
            if is_orphaned:
                orphaned_count += 1
                cleaned_ids.append(item.get("_id"))
        
        # Orphaned item'ları okundu işaretle
        if cleaned_ids:
            result = await db.calendar_items.update_many(
                {"_id": {"$in": cleaned_ids}},
                {"$set": {"is_read": True}}
            )
            logging.info(f"🧹 Marked {result.modified_count} orphaned calendar items as read")
        
        return {
            "success": True,
            "message": f"{orphaned_count} orphaned calendar item temizlendi",
            "orphaned_count": orphaned_count,
            "total_unread_checked": len(unread_items)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ Error cleaning up orphaned calendar items: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/cleanup-orphaned-data")
async def cleanup_orphaned_data(
    admin_id: str = Depends(check_admin)
):
    """
    🧹 COMPREHENSIVE Orphaned Data Cleanup Endpoint (Admin Only)
    Mevcut olmayan kullanıcılara ait TÜM verileri temizler:
    - Reservations
    - Calendar Items
    - Notifications
    - Participations
    - Messages
    """
    try:
        logging.info("🧹 Starting COMPREHENSIVE orphaned data cleanup...")
        
        # Mevcut tüm kullanıcı ID'lerini al
        users = await db.users.find({}, {"id": 1}).to_list(None)
        valid_user_ids = set([u["id"] for u in users])
        logging.info(f"✅ Found {len(valid_user_ids)} active users in system")
        
        deleted_reservations = 0
        deleted_calendar_items = 0
        deleted_notifications = 0
        deleted_participations = 0
        deleted_messages = 0
        
        # 1. Orphaned Reservations Cleanup
        logging.info("🔍 Checking reservations...")
        reservations = await db.reservations.find({}).to_list(None)
        for res in reservations:
            user_id = res.get("user_id")
            
            # user_id bazen dict olabiliyor
            if isinstance(user_id, dict):
                user_id = user_id.get("id")
            
            if user_id and user_id not in valid_user_ids:
                logging.warning(f"   ❌ Orphaned reservation: {res.get('id', 'no-id')[:15]}... (user: {user_id[:8]}...)")
                await db.reservations.delete_one({"_id": res["_id"]})
                deleted_reservations += 1
        
        # 2. Orphaned Calendar Items Cleanup
        logging.info("🔍 Checking calendar items...")
        # Önce mevcut rezervasyon ID'lerini al
        reservations = await db.reservations.find({}, {"id": 1}).to_list(None)
        valid_reservation_ids = set([r["id"] for r in reservations])
        
        calendar_items = await db.calendar_items.find({}).to_list(None)
        for item in calendar_items:
            user_id = item.get("user_id")
            reservation_id = item.get("reservation_id")
            
            should_delete = False
            reason = ""
            
            if user_id and user_id not in valid_user_ids:
                should_delete = True
                reason = "user not found"
            
            if not should_delete and reservation_id and reservation_id not in valid_reservation_ids:
                should_delete = True
                reason = "reservation not found"
            
            if should_delete:
                logging.warning(f"   ❌ Orphaned calendar item: {item.get('id', 'no-id')[:15]}... - {reason}")
                await db.calendar_items.delete_one({"_id": item["_id"]})
                deleted_calendar_items += 1
        
        # 3. Orphaned Notifications Cleanup
        logging.info("🔍 Checking notifications...")
        notifications = await db.notifications.find({}).to_list(None)
        for notif in notifications:
            user_id = notif.get("user_id")
            
            if user_id and user_id not in valid_user_ids:
                logging.warning(f"   ❌ Orphaned notification: {notif.get('id', 'no-id')[:15]}... (user: {user_id[:8]}...)")
                await db.notifications.delete_one({"_id": notif["_id"]})
                deleted_notifications += 1
        
        # 4. Orphaned Participations Cleanup
        logging.info("🔍 Checking participations...")
        participations = await db.participations.find({}).to_list(None)
        for part in participations:
            user_id = part.get("user_id")
            
            if user_id and user_id not in valid_user_ids:
                logging.warning(f"   ❌ Orphaned participation: {part.get('id', 'no-id')[:15]}... (user: {user_id[:8]}...)")
                await db.participations.delete_one({"_id": part["_id"]})
                deleted_participations += 1
        
        # 5. Orphaned Messages Cleanup
        logging.info("🔍 Checking messages...")
        messages = await db.messages.find({}).to_list(None)
        for msg in messages:
            sender_id = msg.get("sender_id")
            receiver_id = msg.get("receiver_id")
            
            if (sender_id and sender_id not in valid_user_ids) or \
               (receiver_id and receiver_id not in valid_user_ids):
                logging.warning(f"   ❌ Orphaned message: {msg.get('id', 'no-id')[:15]}...")
                await db.messages.delete_one({"_id": msg["_id"]})
                deleted_messages += 1
        
        total_deleted = (deleted_reservations + deleted_calendar_items + 
                        deleted_notifications + deleted_participations + deleted_messages)
        
        logging.info(f"✅ COMPREHENSIVE cleanup complete: {total_deleted} total items deleted")
        
        return {
            "success": True,
            "message": "Comprehensive orphaned data cleanup tamamlandı",
            "deleted_reservations": deleted_reservations,
            "deleted_calendar_items": deleted_calendar_items,
            "deleted_notifications": deleted_notifications,
            "deleted_participations": deleted_participations,
            "deleted_messages": deleted_messages,
            "total_deleted": total_deleted
        }
        
    except Exception as e:
        logging.error(f"❌ Error during cleanup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/reservations/{reservation_id}")
async def get_reservation_by_id(
    reservation_id: str,
    current_user: dict = Depends(get_current_user)  # ✅ Dict olarak al
):
    """Get reservation details by ID"""
    try:
        # ✅ current_user dict'ten id'yi extract et
        current_user_id = current_user.get("id")
        
        reservation = await db.reservations.find_one({"id": reservation_id})
        
        if not reservation:
            raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
        
        # Check if user is authorized (creator or receiver)
        user = await db.users.find_one({"id": current_user_id})
        
        # ✅ CRITICAL: user_id, player_id, coach_id, referee_id bazen dictionary olabiliyor!
        # Önce extract edelim
        res_user_id = reservation.get("user_id")
        if isinstance(res_user_id, dict):
            res_user_id = res_user_id.get("id")
        
        res_player_id = reservation.get("player_id")
        if isinstance(res_player_id, dict):
            res_player_id = res_player_id.get("id")
            
        res_coach_id = reservation.get("coach_id")
        if isinstance(res_coach_id, dict):
            res_coach_id = res_coach_id.get("id")
            
        res_referee_id = reservation.get("referee_id")
        if isinstance(res_referee_id, dict):
            res_referee_id = res_referee_id.get("id")
        
        # Admin kullanıcıları tüm rezervasyonlara erişebilir
        is_admin = user and user.get("user_type") == "admin"
        
        is_authorized = (
            is_admin or
            res_user_id == current_user_id or
            res_player_id == current_user_id or
            res_coach_id == current_user_id or
            res_referee_id == current_user_id or
            reservation.get("venue_id") in [v.get("id") for v in await db.venues.find({"owner_id": current_user_id}).to_list(100)]
        )
        
        # Also check if user owns the facility
        if reservation.get("facility_id"):
            facility = await db.facilities.find_one({"id": reservation["facility_id"]})
            if facility and facility.get("owner_id") == current_user_id:
                is_authorized = True
        
        if not is_authorized:
            # ✅ DEBUG: Auth fail durumunda detaylı log
            logging.error(f"❌ AUTH FAILED - User: {current_user_id}, Reservation: {reservation_id}")
            logging.error(f"   res_user_id: {res_user_id}, res_player_id: {res_player_id}")
            logging.error(f"   res_coach_id: {res_coach_id}, res_referee_id: {res_referee_id}")
            logging.error(f"   Matches: user={res_user_id == current_user_id}, player={res_player_id == current_user_id}, coach={res_coach_id == current_user_id}, referee={res_referee_id == current_user_id}")
            raise HTTPException(status_code=403, detail="Bu rezervasyona erişim yetkiniz yok")
        
        # Enrich with facility and field details
        if reservation.get("facility_id"):
            facility = await db.facilities.find_one({"id": reservation["facility_id"]})
            if facility:
                facility.pop("_id", None)
                reservation["facility"] = facility
        
        if reservation.get("field_id"):
            field = await db.facility_fields.find_one({"id": reservation["field_id"]})
            if field:
                field.pop("_id", None)
                reservation["field"] = field
        
        reservation.pop("_id", None)
        return reservation
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting reservation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



# Reservation detail endpoints - MUST BE BEFORE /reservations/my and /reservations/pending
@api_router.patch("/reservations/{reservation_id}/approve")
async def approve_reservation_request(
    reservation_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Approve a pending reservation"""
    try:
        reservation = await db.reservations.find_one({"id": reservation_id})
        
        if not reservation:
            raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
        
        # Check if user is the receiver or admin
        user = await db.users.find_one({"id": current_user_id})
        is_admin = user and user.get("user_type") in ["admin", "super_admin"]
        is_receiver = (
            is_admin or  # Admin her rezervasyonu onaylayabilir
            reservation.get("player_id") == current_user_id or
            reservation.get("coach_id") == current_user_id or
            reservation.get("referee_id") == current_user_id or
            reservation.get("venue_id") in [v.get("id") for v in await db.venues.find({"owner_id": current_user_id}).to_list(100)]
        )
        
        if not is_receiver:
            raise HTTPException(status_code=403, detail="Bu rezervasyonu onaylama yetkiniz yok")
        
        if reservation.get("status") != "pending":
            raise HTTPException(status_code=400, detail="Sadece bekleyen rezervasyonlar onaylanabilir")
        
        # Update reservation status
        await db.reservations.update_one(
            {"id": reservation_id},
            {"$set": {"status": "confirmed", "updated_at": datetime.utcnow()}}
        )
        
        # Send notification to requester
        notification_data = {
            "id": str(uuid.uuid4()),
            "user_id": reservation["user_id"],
            "type": "reservation_approved",
            "title": "Rezervasyon Onaylandı",
            "message": "Rezervasyonunuz onaylandı",
            "related_id": reservation_id,
            "related_type": "reservation",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification_data)
        
        # Also notify the approver
        approver_notification = {
            "id": str(uuid.uuid4()),
            "user_id": current_user_id,
            "type": "reservation_approved",
            "title": "Rezervasyon Onaylandı",
            "message": "Rezervasyonu onayladınız",
            "related_id": reservation_id,
            "related_type": "reservation",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(approver_notification)
        
        # ✅ HER İKİ TARAF İÇİN DE CALENDAR'A EKLE (hakem, oyuncu, antrenör için)
        try:
            reservation_type = reservation.get("type") or reservation.get("reservation_type")
            buyer_id = reservation.get("user_id")  # Talep eden
            
            # Seller ID (hizmet sağlayan) - tip'e göre belirle
            seller_id = None
            if reservation.get("player_id"):
                seller_id = reservation.get("player_id")
                reservation_type = "player"
            elif reservation.get("coach_id"):
                seller_id = reservation.get("coach_id")
                reservation_type = "coach"
            elif reservation.get("referee_id"):
                seller_id = reservation.get("referee_id")
                reservation_type = "referee"
            
            # user_id bazen dictionary olabiliyor
            if isinstance(buyer_id, dict):
                buyer_id = buyer_id.get("id")
            if isinstance(seller_id, dict):
                seller_id = seller_id.get("id")
            
            reservation_date = reservation.get("date") or reservation.get("selected_date")
            reservation_hour = reservation.get("hour") or reservation.get("selected_hour") or reservation.get("time_slot")
            
            # 1. Talep edene calendar item ekle
            if buyer_id:
                calendar_item_buyer = {
                    "id": str(uuid.uuid4()),
                    "user_id": buyer_id,
                    "reservation_id": reservation_id,
                    "type": "reservation_out",
                    "title": f"{reservation_type.capitalize() if reservation_type else 'Rezervasyon'}",
                    "date": reservation_date,
                    "hour": reservation_hour,
                    "is_read": False,
                    "created_at": datetime.utcnow().isoformat()
                }
                await db.calendar_items.insert_one(calendar_item_buyer)
                logging.info(f"📅 Calendar item created for buyer: {buyer_id}")
            
            # 2. Hizmet sağlayıcıya calendar item ekle
            if seller_id:
                calendar_item_seller = {
                    "id": str(uuid.uuid4()),
                    "user_id": seller_id,
                    "reservation_id": reservation_id,
                    "type": "reservation_in",
                    "title": f"Gelen {reservation_type.capitalize() if reservation_type else 'Rezervasyon'}",
                    "date": reservation_date,
                    "hour": reservation_hour,
                    "is_read": False,
                    "created_at": datetime.utcnow().isoformat()
                }
                await db.calendar_items.insert_one(calendar_item_seller)
                logging.info(f"📅 Calendar item created for seller: {seller_id}")
                
        except Exception as cal_error:
            logging.error(f"❌ Calendar item creation error (approve): {str(cal_error)}")
            # Hata olsa bile approve işlemi başarılı sayılsın
        
        return {"message": "Rezervasyon onaylandı"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error approving reservation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/reservations/{reservation_id}/reject")
async def reject_reservation_request(
    reservation_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Reject a pending reservation"""
    try:
        reservation = await db.reservations.find_one({"id": reservation_id})
        
        if not reservation:
            raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
        
        # Check if user is the receiver
        user = await db.users.find_one({"id": current_user_id})
        is_admin = user and user.get("user_type") in ["admin", "super_admin"]
        is_receiver = (
            is_admin or  # Admin her rezervasyonu reddedebilir
            reservation.get("player_id") == current_user_id or
            reservation.get("coach_id") == current_user_id or
            reservation.get("referee_id") == current_user_id or
            reservation.get("venue_id") in [v.get("id") for v in await db.venues.find({"owner_id": current_user_id}).to_list(100)]
        )
        
        if not is_receiver:
            raise HTTPException(status_code=403, detail="Bu rezervasyonu reddetme yetkiniz yok")
        
        if reservation.get("status") != "pending":
            raise HTTPException(status_code=400, detail="Sadece bekleyen rezervasyonlar reddedilebilir")
        
        # Update reservation status
        await db.reservations.update_one(
            {"id": reservation_id},
            {"$set": {"status": "rejected", "updated_at": datetime.utcnow()}}
        )
        
        # Send notification to requester
        notification_data = {
            "id": str(uuid.uuid4()),
            "user_id": reservation["user_id"],
            "type": "reservation_rejected",
            "title": "Rezervasyon Reddedildi",
            "message": "Rezervasyonunuz reddedildi",
            "related_id": reservation_id,
            "related_type": "reservation",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification_data)
        
        return {"message": "Rezervasyon reddedildi"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error rejecting reservation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/reservations/{reservation_id}/approve")
async def approve_reservation(
    reservation_id: str,
    approval_data: dict,
    current_user_id: str = Depends(get_current_user)
):
    """Approve reservation - owner selects ONE time slot"""
    reservation = await db.reservations.find_one({"id": reservation_id})
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    # Verify ownership
    venue = await db.venues.find_one({"id": reservation["venue_id"]})
    if not venue or venue["owner_id"] != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    approved_slot = approval_data.get("approved_time_slot")
    if approved_slot not in reservation["time_slots"]:
        raise HTTPException(status_code=400, detail="Invalid time slot")
    
    # Update reservation
    await db.reservations.update_one(
        {"id": reservation_id},
        {
            "$set": {
                "status": "approved",
                "approved_time_slot": approved_slot,
                "total_hours": 1,
                "total_price": reservation["hourly_rate"],
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    # Notify user
    notification_data = {
        "id": str(uuid.uuid4()),
        "user_id": reservation["user_id"],
        "type": "reservation_approved",
        "title": "Rezervasyon Onaylandı",
        "message": f"Rezervasyonunuz {approved_slot} saati için onaylandı. Ödeme yapabilirsiniz.",
        "related_id": reservation_id,
        "related_type": "reservation",
        "is_read": False,
        "created_at": datetime.utcnow()
    }
    await db.notifications.insert_one(notification_data)
    
    return {"message": "Reservation approved", "approved_time_slot": approved_slot}

@api_router.put("/reservations/{reservation_id}/reject")
async def reject_reservation(
    reservation_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Reject reservation"""
    reservation = await db.reservations.find_one({"id": reservation_id})
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    # Verify ownership
    venue = await db.venues.find_one({"id": reservation["venue_id"]})
    if not venue or venue["owner_id"] != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.reservations.update_one(
        {"id": reservation_id},
        {"$set": {"status": "rejected", "updated_at": datetime.utcnow()}}
    )
    
    # Notify user
    notification_data = {
        "id": str(uuid.uuid4()),
        "user_id": reservation["user_id"],
        "type": "reservation_rejected",
        "title": "Rezervasyon Reddedildi",
        "message": "Rezervasyon talebiniz reddedildi.",
        "related_id": reservation_id,
        "related_type": "reservation",
        "is_read": False,
        "created_at": datetime.utcnow()
    }
    await db.notifications.insert_one(notification_data)
    
    return {"message": "Reservation rejected"}

@api_router.patch("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Cancel reservation"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    reservation = await db.reservations.find_one({"id": reservation_id})
    if not reservation:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    
    # Check if user is owner of reservation, facility owner, or admin
    user_id = reservation.get("user_id")
    if isinstance(user_id, dict):
        user_id = user_id.get("id")
    
    # Get facility to check ownership
    facility = await db.facilities.find_one({"id": reservation.get("facility_id")})
    facility_owner_id = facility.get("owner_id") if facility else None
    
    # Check current user info
    user_info = await db.users.find_one({"id": current_user_id})
    is_admin = user_info.get("user_type") == "admin" if user_info else False
    
    # Authorization check
    if user_id != current_user_id and facility_owner_id != current_user_id and not is_admin:
        raise HTTPException(status_code=403, detail="Bu rezervasyonu iptal etme yetkiniz yok")
    
    # Check if already cancelled
    if reservation.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Rezervasyon zaten iptal edilmiş")
    
    # Update reservation status
    await db.reservations.update_one(
        {"id": reservation_id},
        {
            "$set": {
                "status": "cancelled",
                "cancelled_at": datetime.utcnow(),
                "cancelled_by": current_user_id,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    # Notify reservation owner if cancelled by facility owner or admin
    if user_id != current_user_id:
        notification_data = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "reservation_cancelled",
            "title": "Rezervasyon İptal Edildi",
            "message": f"Rezervasyonunuz iptal edildi.",
            "related_id": reservation_id,
            "related_type": "reservation",
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification_data)
    
    # Notify facility owner if cancelled by user
    if facility_owner_id and facility_owner_id != current_user_id:
        notification_data = {
            "id": str(uuid.uuid4()),
            "user_id": facility_owner_id,
            "type": "reservation_cancelled",
            "title": "Rezervasyon İptal Edildi",
            "message": f"Bir rezervasyon iptal edildi.",
            "related_id": reservation_id,
            "related_type": "reservation",
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification_data)
    
    return {"message": "Rezervasyon iptal edildi", "reservation_id": reservation_id}

@api_router.post("/reservations/{reservation_id}/pay")
async def pay_reservation(
    reservation_id: str,
    payment_data: dict,
    current_user_id: str = Depends(get_current_user)
):
    """Process reservation payment (mock)"""
    reservation = await db.reservations.find_one({"id": reservation_id})
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    if reservation["user_id"] != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if reservation["status"] != "approved":
        raise HTTPException(status_code=400, detail="Reservation not approved")
    
    # Mock payment - in real app, integrate with Stripe/Iyzico
    await db.reservations.update_one(
        {"id": reservation_id},
        {
            "$set": {
                "status": "paid",
                "payment_status": "completed",
                "payment_method": payment_data.get("method", "mock"),
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    # Notify venue owner
    venue = await db.venues.find_one({"id": reservation["venue_id"]})
    if venue:
        notification_data = {
            "id": str(uuid.uuid4()),
            "user_id": venue["owner_id"],
            "type": "reservation_paid",
            "title": "Rezervasyon Ödemesi Alındı",
            "message": f"₺{reservation['total_price']} ödeme alındı.",
            "related_id": reservation_id,
            "related_type": "reservation",
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification_data)
    
    return {"message": "Payment successful", "status": "paid"}


# ==================== MEMBERSHIP MANAGEMENT ROUTES ====================

class InviteMemberRequest(BaseModel):
    user_name: str

class UpdateMembershipDetailsRequest(BaseModel):
    membership_date: str = ""
    member_number: str = ""
    sport_branch: str = ""
    membership_package_type: str = ""
    membership_fee: float = 0.0
    work_days: str = ""
    work_hours: str = ""
    coaches: list[str] = []
    health_report: str = ""
    blood_type: str = ""
    emergency_contact_name: str = ""
    emergency_contact_phone: str = ""
    notes: str = ""

class CreatePaymentRequestBody(BaseModel):
    member_ids: list[str]
    amount: float
    description: str
    period_type: str = "one_time"  # one_time, monthly, quarterly, yearly

class PayPaymentRequestBody(BaseModel):
    payment_token: str

@api_router.post("/memberships/invite")
async def invite_member(
    request: InviteMemberRequest,
    current_user_data: dict = Depends(get_current_user)
):
    """Send membership invitation to a user"""
    try:
        user_name = request.user_name
        
        # get_current_user returns dict with {"id": ..., "user_type": ...}
        current_user_id = current_user_data.get("id") if isinstance(current_user_data, dict) else current_user_data
        
        # Check if current user is venue_owner, coach, facility_owner, club_manager or has coach_profile
        current_user = await db.users.find_one({"id": current_user_id})
        
        # Allowed user types - admin de dahil
        allowed_types = ["venue_owner", "coach", "facility_owner", "club_manager", "admin", "super_admin"]
        
        # Check if user has permission (either by user_type or by having coach_profile)
        has_permission = (
            current_user and (
                current_user.get("user_type") in allowed_types or
                current_user.get("coach_profile") is not None  # Koç profili varsa da izin ver
            )
        )
        
        logging.info(f"🔵 /memberships/invite - user_id: {current_user_id}, user_type: {current_user.get('user_type') if current_user else 'N/A'}, has_permission: {has_permission}")
        
        if not has_permission:
            raise HTTPException(status_code=403, detail="Sadece tesis sahipleri, kulüp yöneticileri ve antrenörler üye ekleyebilir")
        
        # Search for user by name (case insensitive)
        target_user = await db.users.find_one({
            "full_name": {"$regex": f"^{user_name}$", "$options": "i"}
        })
        
        if not target_user:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        
        # Check if already a member or invitation pending
        existing = await db.memberships.find_one({
            "organization_id": current_user_id,
            "member_id": target_user["id"]
        })
        
        if existing:
            if existing.get("status") == "active":
                raise HTTPException(status_code=400, detail="User is already a member")
            elif existing.get("status") == "pending":
                raise HTTPException(status_code=400, detail="Invitation already sent")
        
        # Create membership invitation
        membership = {
            "id": str(uuid.uuid4()),
            "organization_id": current_user_id,
            "organization_name": current_user.get("full_name"),
            "organization_type": current_user.get("user_type"),
            "member_id": target_user["id"],
            "member_name": target_user.get("full_name"),
            "status": "pending",
            "invited_at": datetime.utcnow(),
            "created_at": datetime.utcnow()
        }
        
        await db.memberships.insert_one(membership)
        
        # Send notification to target user
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": target_user["id"],
            "type": "membership_invitation",
            "title": "Üyelik Daveti",
            "message": f"{current_user.get('full_name')} sizi üye olarak eklemek istiyor.",
            "related_id": membership["id"],
            "related_type": "membership",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
        
        logging.info(f"Membership invitation sent: {current_user_id} -> {target_user['id']}")
        
        return {"message": "Invitation sent", "membership_id": membership["id"]}
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error inviting member: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/memberships/{membership_id}/accept")
async def accept_membership(
    membership_id: str,
    current_user_data: dict = Depends(get_current_user)
):
    """Accept membership invitation"""
    try:
        # get_current_user returns dict with {"id": ..., "user_type": ...}
        current_user_id = current_user_data.get("id") if isinstance(current_user_data, dict) else current_user_data
        
        membership = await db.memberships.find_one({"id": membership_id})
        
        if not membership:
            raise HTTPException(status_code=404, detail="Invitation not found")
        
        if membership["member_id"] != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        if membership["status"] != "pending":
            raise HTTPException(status_code=400, detail="Invitation already processed")
        
        # Update membership status
        await db.memberships.update_one(
            {"id": membership_id},
            {"$set": {
                "status": "active",
                "accepted_at": datetime.utcnow()
            }}
        )
        
        # Update user's club info
        await db.users.update_one(
            {"id": current_user_id},
            {"$set": {
                "club_organization": membership["organization_name"]
            }}
        )
        
        # Notify organization owner
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": membership["organization_id"],
            "type": "membership_accepted",
            "title": "Üyelik Onaylandı",
            "message": f"{membership['member_name']} üyelik davetini kabul etti.",
            "related_id": membership_id,
            "related_type": "membership",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
        
        # Auto-add member to club management
        member = await db.users.find_one({"id": current_user_id})
        if member:
            athlete_data = {
                "id": str(uuid.uuid4()),
                "organization_id": membership["organization_id"],
                "name": member.get("full_name", ""),
                "birth_date": member.get("birth_date", ""),
                "sport_branch": member.get("sport_branch", ""),
                "age_group": "",
                "license_number": "",
                "gender": member.get("gender", ""),
                "license_renewal_date": "",
                "contract_status": False,
                "contract_date": "",
                "membership_fee": 0.0,
                "documents_status": "Beklemede",
                "tc_id": "",
                "phone": member.get("phone_number", ""),
                "email": member.get("email", ""),
                "address": "",
                "parent_name": "",
                "parent_phone": "",
                "blood_type": "",
                "athlete_type": "Amatör",
                "health_report_status": "Beklemede",
                "notes": f"Üyelik tarihi: {datetime.utcnow().strftime('%Y-%m-%d')}",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            await db.club_athletes.insert_one(athlete_data)
            logging.info(f"Auto-added member {member.get('full_name')} to club athletes")
        
        return {"message": "Membership accepted"}
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error accepting membership: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/memberships/{membership_id}/reject")
async def reject_membership(
    membership_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Reject membership invitation"""
    try:
        membership = await db.memberships.find_one({"id": membership_id})
        
        if not membership:
            raise HTTPException(status_code=404, detail="Invitation not found")
        
        if membership["member_id"] != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        # Update membership status
        await db.memberships.update_one(
            {"id": membership_id},
            {"$set": {"status": "rejected"}}
        )
        
        return {"message": "Invitation rejected"}
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error rejecting membership: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/memberships/my-members")
async def get_my_members(
    current_user_data: dict = Depends(get_current_user)
):
    """Get all members of my organization"""
    try:
        # get_current_user returns dict with {"id": ..., "user_type": ...}
        current_user_id = current_user_data.get("id") if isinstance(current_user_data, dict) else current_user_data
        
        logging.info(f"🔵 /memberships/my-members called by user: {current_user_id}")
        
        # creator_id veya organization_id ile ara
        memberships = await db.memberships.find({
            "$or": [
                {"creator_id": current_user_id},
                {"organization_id": current_user_id}
            ],
            "status": "active"
        }).to_list(1000)
        
        logging.info(f"🟢 Found {len(memberships)} memberships for user {current_user_id}")
        
        # Enrich with user data
        for membership in memberships:
            membership.pop("_id", None)
            user = await db.users.find_one({"id": membership["member_id"]})
            if user:
                membership["member_email"] = user.get("email")
                membership["member_phone"] = user.get("phone")
                membership["member_avatar"] = user.get("avatar")
        
        return {"members": memberships}
    
    except Exception as e:
        logging.error(f"Error getting members: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/memberships/search-users")
async def search_users_for_membership(
    query: str,
    current_user_data: dict = Depends(get_current_user)
):
    """Search users by name for membership invitation"""
    try:
        # get_current_user returns dict with {"id": ..., "user_type": ...}
        current_user_id = current_user_data.get("id") if isinstance(current_user_data, dict) else current_user_data
        
        if len(query) < 2:
            return {"users": []}
        
        users = await db.users.find({
            "full_name": {"$regex": query, "$options": "i"},
            "id": {"$ne": current_user_id}
        }).to_list(20)
        
        result = []
        for user in users:
            result.append({
                "id": user["id"],
                "full_name": user.get("full_name"),
                "email": user.get("email"),
                "avatar": user.get("avatar")
            })
        
        return {"users": result}
    
    except Exception as e:
        logging.error(f"Error searching users: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ADMIN REVIEWS ROUTES ====================

@api_router.get("/admin/reviews")
async def get_all_reviews_admin(
    current_user: dict = Depends(get_current_user)
):
    """Get all reviews for admin management"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    # Check if admin
    user = await db.users.find_one({"id": current_user_id})
    if not user or user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    reviews = []
    
    # Get reviews from reviews collection
    review_docs = await db.reviews.find({}).sort("created_at", -1).to_list(1000)
    
    for review in review_docs:
        # Get reviewer info - check multiple possible fields
        reviewer_id = review.get("reviewer_id") or review.get("reviewer_user_id") or review.get("user_id")
        reviewer_name = review.get("reviewer_name") or review.get("user_name") or "Anonim"
        
        # If reviewer_name not in review, try to get from users collection
        if reviewer_name in ["Anonim", None, ""] and reviewer_id:
            reviewer = await db.users.find_one({"id": reviewer_id})
            if reviewer:
                reviewer_name = reviewer.get("full_name", reviewer.get("name", "Anonim"))
        
        # Get reviewed entity info - check multiple possible fields
        reviewed_id = review.get("target_user_id") or review.get("reviewed_user_id") or review.get("facility_id") or review.get("event_id") or review.get("product_id")
        reviewed_type = review.get("target_type") or review.get("type") or "user"
        reviewed_name = "Bilinmiyor"
        
        # Determine reviewed entity name based on type
        if review.get("target_user_id") or review.get("reviewed_user_id"):
            target_id = review.get("target_user_id") or review.get("reviewed_user_id")
            target_user = await db.users.find_one({"id": target_id})
            if target_user:
                reviewed_name = target_user.get("full_name", target_user.get("name", "Bilinmiyor"))
            reviewed_type = "user"
        elif review.get("facility_id"):
            facility = await db.facilities.find_one({"id": review.get("facility_id")})
            if facility:
                reviewed_name = facility.get("name", "Bilinmiyor")
            reviewed_type = "facility"
        elif review.get("event_id"):
            event = await db.events.find_one({"id": review.get("event_id")})
            if event:
                reviewed_name = event.get("title", "Bilinmiyor")
            reviewed_type = "event"
        elif review.get("product_id"):
            product = await db.products.find_one({"id": review.get("product_id")})
            if product:
                reviewed_name = product.get("title", "Bilinmiyor")
            reviewed_type = "product"
        
        # Parse created_at - handle both string and datetime
        created_at = review.get("created_at")
        if isinstance(created_at, str):
            created_at_str = created_at
        elif created_at:
            created_at_str = created_at.isoformat()
        else:
            created_at_str = datetime.utcnow().isoformat()
        
        reviews.append({
            "id": review.get("id", str(review.get("_id", ""))),
            "reviewer_id": reviewer_id or "",
            "reviewer_name": reviewer_name or "Anonim",
            "reviewed_id": reviewed_id or "",
            "reviewed_name": reviewed_name,
            "reviewed_type": reviewed_type,
            "rating": review.get("rating", 0),
            "comment": review.get("comment", review.get("text", "")),
            "created_at": created_at_str
        })
    
    logging.info(f"Admin reviews: Returning {len(reviews)} reviews")
    return reviews


@api_router.delete("/admin/reviews/{review_id}")
async def delete_review_admin(
    review_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a review (admin only)"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    # Check if admin
    user = await db.users.find_one({"id": current_user_id})
    if not user or user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    logging.info(f"Attempting to delete review: {review_id}")
    
    # Try to find and delete the review by id field
    result = await db.reviews.delete_one({"id": review_id})
    logging.info(f"Delete by id result: {result.deleted_count}")
    
    if result.deleted_count == 0:
        # Try with _id as ObjectId
        try:
            from bson import ObjectId
            result = await db.reviews.delete_one({"_id": ObjectId(review_id)})
            logging.info(f"Delete by _id ObjectId result: {result.deleted_count}")
        except Exception as e:
            logging.error(f"ObjectId conversion error: {e}")
    
    if result.deleted_count == 0:
        # Try with _id as string
        result = await db.reviews.delete_one({"_id": review_id})
        logging.info(f"Delete by _id string result: {result.deleted_count}")
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Yorum bulunamadı")
    
    logging.info(f"Review {review_id} deleted by admin {current_user_id}")
    
    return {"message": "Yorum silindi", "review_id": review_id}


# ==================== PAYMENT REQUEST ROUTES ====================

@api_router.post("/payment-requests/create")
async def create_payment_request(
    request: CreatePaymentRequestBody,
    current_user_data: dict = Depends(get_current_user)
):
    """Create payment request(s) for member(s)"""
    # get_current_user returns dict with {"id": ..., "user_type": ...}
    current_user_id = current_user_data.get("id") if isinstance(current_user_data, dict) else current_user_data
    
    member_ids = request.member_ids
    amount = request.amount
    description = request.description
    period_type = request.period_type
    try:
        current_user = await db.users.find_one({"id": current_user_id})
        if not current_user:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        
        payment_requests = []
        
        for member_id in member_ids:
            # Verify membership
            membership = await db.memberships.find_one({
                "organization_id": current_user_id,
                "member_id": member_id,
                "status": "active"
            })
            
            if not membership:
                continue
            
            # Create payment request
            payment_request = {
                "id": str(uuid.uuid4()),
                "organization_id": current_user_id,
                "organization_name": current_user.get("full_name"),
                "member_id": member_id,
                "member_name": membership.get("member_name"),
                "amount": amount,
                "description": description,
                "period_type": period_type,
                "status": "pending",  # pending, paid, overdue
                "created_at": datetime.utcnow(),
                "due_date": datetime.utcnow() + timedelta(days=3),
                "paid_at": None
            }
            
            await db.payment_requests.insert_one(payment_request)
            payment_requests.append(payment_request)
            
            # Send notification to member
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": member_id,
                "type": "payment_request",
                "title": "Ödeme Talebi",
                "message": f"{current_user.get('full_name')} tarafından {amount}₺ ödeme talebi oluşturuldu.",
                "related_id": payment_request["id"],
                "related_type": "payment_request",
                "read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(notification)
            
            logging.info(f"Payment request created: {payment_request['id']} for {member_id}")
        
        return {
            "message": "Payment requests created",
            "count": len(payment_requests),
            "requests": [{"id": pr["id"], "member_id": pr["member_id"]} for pr in payment_requests]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error creating payment request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/memberships/member-reports")
async def get_member_reports(
    gender: str = None,
    sport_branch: str = None,
    coach_id: str = None,
    sort_by: str = "member_name",
    sort_direction: str = "asc",
    current_user_id: str = Depends(get_current_user)
):
    """Get member reports with filters and sorting"""
    try:
        query = {"organization_id": current_user_id, "status": "active"}
        
        # Get memberships
        memberships = await db.memberships.find(query).to_list(1000)
        
        # Enrich with user data
        reports = []
        for membership in memberships:
            user = await db.users.find_one({"id": membership["member_id"]})
            if user:
                # Get coach names
                coach_names = []
                if membership.get("coaches"):
                    for coach_id in membership["coaches"]:
                        coach = await db.users.find_one({"id": coach_id})
                        if coach:
                            coach_names.append(coach.get("full_name", ""))
                
                report = {
                    "member_name": user.get("full_name", ""),
                    "gender": user.get("gender", ""),
                    "birth_date": user.get("birth_date", ""),
                    "sport_branch": membership.get("sport_branch", ""),
                    "phone": user.get("phone_number", ""),
                    "membership_date": membership.get("membership_date", ""),
                    "membership_fee": membership.get("membership_fee", 0),
                    "coaches": coach_names,
                    "work_days": membership.get("work_days", ""),
                    "work_hours": membership.get("work_hours", ""),
                }
                
                # Apply filters
                if gender and report["gender"] != gender:
                    continue
                if sport_branch and report["sport_branch"] != sport_branch:
                    continue
                if coach_id and coach_id not in membership.get("coaches", []):
                    continue
                
                reports.append(report)
        
        # Sort
        reverse = sort_direction == "desc"
        if sort_by in reports[0] if reports else {}:
            reports.sort(key=lambda x: x.get(sort_by, ""), reverse=reverse)
        
        return {"reports": reports, "total": len(reports)}
    
    except Exception as e:
        logging.error(f"Error getting member reports: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/payment-requests/reports")
async def get_payment_reports(
    start_date: str = None,
    end_date: str = None,
    member_name: str = None,
    status: str = None,
    current_user_id: str = Depends(get_current_user)
):
    """Get payment reports with filters"""
    try:
        # Build query
        query = {"organization_id": current_user_id}
        
        # Date filter
        if start_date or end_date:
            date_query = {}
            if start_date:
                date_query["$gte"] = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if end_date:
                # Add one day to include the end date
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                date_query["$lte"] = end_dt + timedelta(days=1)
            query["created_at"] = date_query
        
        # Status filter
        if status and status != 'all':
            query["status"] = status
        
        # Get all requests
        requests = await db.payment_requests.find(query).sort("created_at", -1).to_list(1000)
        
        # Member name filter (case-insensitive)
        if member_name:
            requests = [r for r in requests if member_name.lower() in r.get('member_name', '').lower()]
        
        # Calculate statistics
        total_requests = len(requests)
        total_pending = sum(1 for r in requests if r.get('status') == 'pending')
        total_paid = sum(1 for r in requests if r.get('status') == 'paid')
        total_amount_pending = sum(r.get('amount', 0) for r in requests if r.get('status') == 'pending')
        total_amount_paid = sum(r.get('amount', 0) for r in requests if r.get('status') == 'paid')
        
        # Remove _id field
        for req in requests:
            req.pop("_id", None)
        
        return {
            "requests": requests,
            "statistics": {
                "total_requests": total_requests,
                "total_pending": total_pending,
                "total_paid": total_paid,
                "total_amount_pending": total_amount_pending,
                "total_amount_paid": total_amount_paid
            }
        }
    
    except Exception as e:
        logging.error(f"Error getting payment reports: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/payment-requests/my-requests")
async def get_my_payment_requests(
    current_user_id: str = Depends(get_current_user)
):
    """Get all payment requests I sent"""
    try:
        requests = await db.payment_requests.find({
            "organization_id": current_user_id
        }).sort("created_at", -1).to_list(1000)
        
        for req in requests:
            req.pop("_id", None)
        
        return {"requests": requests}
    
    except Exception as e:
        logging.error(f"Error getting payment requests: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/payment-requests/my-dues")
async def get_my_dues(
    current_user_id: str = Depends(get_current_user)
):
    """Get all payment requests sent to me"""
    try:
        requests = await db.payment_requests.find({
            "member_id": current_user_id
        }).sort("created_at", -1).to_list(1000)
        
        for req in requests:
            req.pop("_id", None)
        
        return {"requests": requests}
    
    except Exception as e:
        logging.error(f"Error getting dues: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/payment-requests/{request_id}")
async def get_payment_request(
    request_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Get payment request details"""
    try:
        # ✅ CRITICAL: current_user_id dict olabilir
        if isinstance(current_user_id, dict):
            actual_user_id = current_user_id.get("id")
        else:
            actual_user_id = current_user_id
        
        payment_request = await db.payment_requests.find_one({"id": request_id})
        
        if not payment_request:
            raise HTTPException(status_code=404, detail="Payment request not found")
        
        # Only member or organization can view
        member_id = payment_request.get("member_id")
        organization_id = payment_request.get("organization_id")
        
        # Yetki kontrolü - admin her şeyi görebilir
        user = await db.users.find_one({"id": actual_user_id})
        is_admin = user and user.get("user_type") == "admin"
        
        if not is_admin and member_id != actual_user_id and organization_id != actual_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        payment_request.pop("_id", None)
        return payment_request
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting payment request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/payment-requests/{request_id}/pay")
async def pay_payment_request(
    request_id: str,
    request: PayPaymentRequestBody,
    current_user_id: str = Depends(get_current_user)
):
    """Pay a payment request - This is called after Iyzico callback confirms payment"""
    try:
        # ✅ CRITICAL: current_user_id dict olabilir
        if isinstance(current_user_id, dict):
            actual_user_id = current_user_id.get("id")
        else:
            actual_user_id = current_user_id
        
        payment_token = request.payment_token
        
        # Get payment request
        payment_request = await db.payment_requests.find_one({"id": request_id})
        
        if not payment_request:
            raise HTTPException(status_code=404, detail="Payment request not found")
        
        if payment_request["member_id"] != actual_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        if payment_request["status"] == "paid":
            raise HTTPException(status_code=400, detail="Already paid")
        
        # ✅ Verify Iyzico payment if token provided
        if payment_token and payment_token.startswith("iyzico_"):
            try:
                # Verify with Iyzico
                result = iyzico_service.retrieve_checkout_form_result(payment_token.replace("iyzico_", ""))
                if result.get("status") != "success" and result.get("paymentStatus") != "SUCCESS":
                    raise HTTPException(status_code=400, detail="Ödeme doğrulanamadı")
            except Exception as e:
                logging.error(f"Iyzico verification error: {e}")
                # Continue anyway if iyzico not configured
        
        # ✅ Calculate commission
        amount = payment_request["amount"]
        commission_rate = float(os.getenv("PLATFORM_COMMISSION_RATE", "0.05"))  # %5 varsayılan
        commission_amount = amount * commission_rate
        net_amount = amount - commission_amount
        
        # Update payment request
        await db.payment_requests.update_one(
            {"id": request_id},
            {"$set": {
                "status": "paid",
                "paid_at": datetime.utcnow(),
                "payment_token": payment_token,
                "gross_amount": amount,
                "commission_rate": commission_rate,
                "commission_amount": commission_amount,
                "net_amount": net_amount
            }}
        )
        
        # ✅ Create payment record for tracking
        payment_record = {
            "id": str(uuid.uuid4()),
            "type": "payment_request",
            "related_id": request_id,
            "payer_id": actual_user_id,
            "payer_name": payment_request.get("member_name", ""),
            "receiver_id": payment_request["organization_id"],
            "receiver_name": payment_request.get("organization_name", ""),
            "gross_amount": amount,
            "commission_rate": commission_rate,
            "commission_amount": commission_amount,
            "net_amount": net_amount,
            "currency": "TRY",
            "status": "completed",
            "payment_method": "iyzico" if payment_token else "manual",
            "iyzico_token": payment_token,
            "description": payment_request.get("description", "Ödeme talebi"),
            "created_at": datetime.utcnow()
        }
        await db.payments.insert_one(payment_record)
        
        # ✅ Update organization's earnings
        await db.users.update_one(
            {"id": payment_request["organization_id"]},
            {
                "$inc": {
                    "total_earnings": net_amount,
                    "pending_balance": net_amount
                }
            }
        )
        
        # ✅ Add transaction to ledger
        ledger_entry = {
            "id": str(uuid.uuid4()),
            "user_id": payment_request["organization_id"],
            "type": "income",
            "category": "payment_request",
            "amount": net_amount,
            "gross_amount": amount,
            "commission": commission_amount,
            "description": f"{payment_request.get('member_name', 'Üye')} - {payment_request.get('description', 'Ödeme')}",
            "related_id": request_id,
            "status": "completed",
            "created_at": datetime.utcnow()
        }
        await db.ledger.insert_one(ledger_entry)
        
        # ✅ Add payer's expense record
        payer_ledger = {
            "id": str(uuid.uuid4()),
            "user_id": actual_user_id,
            "type": "expense",
            "category": "payment_request",
            "amount": amount,
            "description": f"{payment_request.get('organization_name', 'Organizasyon')} - {payment_request.get('description', 'Ödeme')}",
            "related_id": request_id,
            "status": "completed",
            "created_at": datetime.utcnow()
        }
        await db.ledger.insert_one(payer_ledger)
        
        # Notify organization
        org_notification = {
            "id": str(uuid.uuid4()),
            "user_id": payment_request["organization_id"],
            "type": "payment_completed",
            "title": "💰 Ödeme Alındı",
            "message": f"{payment_request['member_name']} {amount}₺ ödeme yaptı. Komisyon sonrası: {net_amount:.2f}₺",
            "related_id": request_id,
            "related_type": "payment_request",
            "read": False,
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(org_notification)
        
        # Notify payer (confirmation)
        payer_notification = {
            "id": str(uuid.uuid4()),
            "user_id": actual_user_id,
            "type": "payment_sent",
            "title": "✅ Ödemeniz Tamamlandı",
            "message": f"{payment_request['organization_name']} için {amount}₺ ödeme başarıyla gerçekleşti.",
            "related_id": request_id,
            "related_type": "payment_request",
            "read": False,
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(payer_notification)
        
        # Notify all admins
        admins = await db.users.find({"user_type": "admin"}).to_list(100)
        for admin in admins:
            if admin["id"] != actual_user_id and admin["id"] != payment_request["organization_id"]:
                admin_notification = {
                    "id": str(uuid.uuid4()),
                    "user_id": admin["id"],
                    "type": "payment_completed",
                    "title": "💰 Ödeme Tamamlandı",
                    "message": f"{payment_request['member_name']} → {payment_request['organization_name']}: {amount}₺ (Komisyon: {commission_amount:.2f}₺)",
                    "related_id": request_id,
                    "related_type": "payment_request",
                    "read": False,
                    "is_read": False,
                    "created_at": datetime.utcnow()
                }
                await db.notifications.insert_one(admin_notification)
        
        logging.info(f"✅ Payment completed: {request_id} - {amount}₺ paid by {actual_user_id}, commission: {commission_amount}₺")
        
        # If period_type is recurring, create next payment request
        if payment_request.get("period_type") and payment_request["period_type"] != "one_time":
            next_due = datetime.utcnow()
            if payment_request["period_type"] == "monthly":
                next_due += timedelta(days=30)
            elif payment_request["period_type"] == "quarterly":
                next_due += timedelta(days=90)
            elif payment_request["period_type"] == "yearly":
                next_due += timedelta(days=365)
            
            next_request = {
                "id": str(uuid.uuid4()),
                "organization_id": payment_request["organization_id"],
                "organization_name": payment_request["organization_name"],
                "member_id": payment_request["member_id"],
                "member_name": payment_request["member_name"],
                "amount": payment_request["amount"],
                "description": payment_request["description"],
                "period_type": payment_request["period_type"],
                "status": "pending",
                "created_at": datetime.utcnow(),
                "due_date": next_due + timedelta(days=3),
                "paid_at": None
            }
            await db.payment_requests.insert_one(next_request)
            logging.info(f"Next payment request created: {next_request['id']}")
        
        return {"message": "Payment successful", "status": "paid", "net_amount": net_amount}
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error processing payment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ✅ NEW: Initialize Iyzico payment for payment request
@api_router.post("/payment-requests/{request_id}/initialize-iyzico")
async def initialize_payment_request_iyzico(
    request_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Initialize Iyzico checkout form for payment request"""
    try:
        # ✅ CRITICAL: current_user_id dict olabilir
        if isinstance(current_user_id, dict):
            actual_user_id = current_user_id.get("id")
        else:
            actual_user_id = current_user_id
        
        # Get payment request
        payment_request = await db.payment_requests.find_one({"id": request_id})
        
        if not payment_request:
            raise HTTPException(status_code=404, detail="Ödeme talebi bulunamadı")
        
        if payment_request["member_id"] != actual_user_id:
            raise HTTPException(status_code=403, detail="Bu ödeme talebine erişim yetkiniz yok")
        
        if payment_request["status"] == "paid":
            raise HTTPException(status_code=400, detail="Bu ödeme zaten yapılmış")
        
        # Get user info
        user = await db.users.find_one({"id": actual_user_id})
        if not user:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        
        amount = payment_request["amount"]
        description = payment_request.get("description", "Ödeme Talebi")
        organization_name = payment_request.get("organization_name", "")
        
        # Create conversation ID
        conversation_id = str(uuid.uuid4())
        
        # Try to initialize Iyzico
        try:
            callback_url = f"{os.getenv('FRONTEND_URL', 'https://app.emergent.sh')}/payment-request-callback?request_id={request_id}"
            
            result = iyzico_service.initialize_checkout_form(
                user=user,
                amount=amount,
                related_type="payment_request",
                related_id=request_id,
                related_name=f"{organization_name} - {description}",
                callback_url=callback_url
            )
            
            # Update payment request with Iyzico token
            await db.payment_requests.update_one(
                {"id": request_id},
                {"$set": {
                    "iyzico_token": result.get("token"),
                    "iyzico_conversation_id": conversation_id,
                    "status": "awaiting_payment",
                    "updated_at": datetime.utcnow()
                }}
            )
            
            logging.info(f"✅ Iyzico initialized for payment request: {request_id}")
            
            return {
                "success": True,
                "payment_page_url": result.get("paymentPageUrl"),
                "checkout_form_content": result.get("checkoutFormContent"),
                "token": result.get("token"),
                "request_id": request_id
            }
            
        except ValueError as e:
            # Iyzico not configured - return info for manual payment
            logging.warning(f"Iyzico not configured: {e}")
            raise HTTPException(
                status_code=503, 
                detail="Ödeme sistemi henüz yapılandırılmamış. Lütfen manuel ödeme yapın veya yönetici ile iletişime geçin."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error initializing payment request Iyzico: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ✅ NEW: Handle Iyzico callback for payment request
@api_router.post("/payment-requests/iyzico-callback")
async def payment_request_iyzico_callback(request: Request):
    """Handle Iyzico callback for payment request"""
    try:
        form_data = await request.form()
        token = form_data.get("token")
        
        if not token:
            logging.error("No token in Iyzico callback")
            return {"status": "error", "message": "Token bulunamadı"}
        
        # Find payment request by token
        payment_request = await db.payment_requests.find_one({"iyzico_token": token})
        
        if not payment_request:
            logging.error(f"Payment request not found for token: {token}")
            return {"status": "error", "message": "Ödeme talebi bulunamadı"}
        
        # Verify payment with Iyzico
        result = iyzico_service.retrieve_checkout_form_result(token)
        
        if result.get("status") == "success" or result.get("paymentStatus") == "SUCCESS":
            # Payment successful - call pay endpoint logic
            request_id = payment_request["id"]
            member_id = payment_request["member_id"]
            
            # Calculate commission
            amount = payment_request["amount"]
            commission_rate = float(os.getenv("PLATFORM_COMMISSION_RATE", "0.05"))
            commission_amount = amount * commission_rate
            net_amount = amount - commission_amount
            
            # Update payment request
            await db.payment_requests.update_one(
                {"id": request_id},
                {"$set": {
                    "status": "paid",
                    "paid_at": datetime.utcnow(),
                    "payment_token": f"iyzico_{token}",
                    "iyzico_payment_id": result.get("paymentId"),
                    "gross_amount": amount,
                    "commission_rate": commission_rate,
                    "commission_amount": commission_amount,
                    "net_amount": net_amount
                }}
            )
            
            # Create payment record
            payment_record = {
                "id": str(uuid.uuid4()),
                "type": "payment_request",
                "related_id": request_id,
                "payer_id": member_id,
                "payer_name": payment_request.get("member_name", ""),
                "receiver_id": payment_request["organization_id"],
                "receiver_name": payment_request.get("organization_name", ""),
                "gross_amount": amount,
                "commission_rate": commission_rate,
                "commission_amount": commission_amount,
                "net_amount": net_amount,
                "currency": "TRY",
                "status": "completed",
                "payment_method": "iyzico",
                "iyzico_payment_id": result.get("paymentId"),
                "description": payment_request.get("description", "Ödeme talebi"),
                "created_at": datetime.utcnow()
            }
            await db.payments.insert_one(payment_record)
            
            # Update earnings
            await db.users.update_one(
                {"id": payment_request["organization_id"]},
                {"$inc": {"total_earnings": net_amount, "pending_balance": net_amount}}
            )
            
            # Add ledger entries
            await db.ledger.insert_one({
                "id": str(uuid.uuid4()),
                "user_id": payment_request["organization_id"],
                "type": "income",
                "category": "payment_request",
                "amount": net_amount,
                "gross_amount": amount,
                "commission": commission_amount,
                "description": f"{payment_request.get('member_name', 'Üye')} - {payment_request.get('description', 'Ödeme')}",
                "related_id": request_id,
                "status": "completed",
                "created_at": datetime.utcnow()
            })
            
            await db.ledger.insert_one({
                "id": str(uuid.uuid4()),
                "user_id": member_id,
                "type": "expense",
                "category": "payment_request",
                "amount": amount,
                "description": f"{payment_request.get('organization_name', '')} - {payment_request.get('description', 'Ödeme')}",
                "related_id": request_id,
                "status": "completed",
                "created_at": datetime.utcnow()
            })
            
            # Send notifications
            await db.notifications.insert_one({
                "id": str(uuid.uuid4()),
                "user_id": payment_request["organization_id"],
                "type": "payment_completed",
                "title": "💰 Ödeme Alındı",
                "message": f"{payment_request['member_name']} {amount}₺ ödeme yaptı. Komisyon sonrası: {net_amount:.2f}₺",
                "related_id": request_id,
                "related_type": "payment_request",
                "read": False,
                "is_read": False,
                "created_at": datetime.utcnow()
            })
            
            await db.notifications.insert_one({
                "id": str(uuid.uuid4()),
                "user_id": member_id,
                "type": "payment_sent",
                "title": "✅ Ödemeniz Tamamlandı",
                "message": f"{payment_request['organization_name']} için {amount}₺ ödeme başarıyla gerçekleşti.",
                "related_id": request_id,
                "related_type": "payment_request",
                "read": False,
                "is_read": False,
                "created_at": datetime.utcnow()
            })
            
            logging.info(f"✅ Payment request paid via Iyzico: {request_id}")
            return {"status": "success", "request_id": request_id}
        else:
            # Payment failed
            await db.payment_requests.update_one(
                {"id": payment_request["id"]},
                {"$set": {"status": "failed", "error_message": result.get("errorMessage")}}
            )
            logging.error(f"Payment request Iyzico failed: {result.get('errorMessage')}")
            return {"status": "error", "message": result.get("errorMessage")}
            
    except Exception as e:
        logging.error(f"Payment request Iyzico callback error: {str(e)}")
        return {"status": "error", "message": str(e)}


@api_router.put("/memberships/{membership_id}/details")
async def update_membership_details(
    membership_id: str,
    request: UpdateMembershipDetailsRequest,
    current_user_id: str = Depends(get_current_user)
):
    """Update membership details"""
    try:
        membership = await db.memberships.find_one({"id": membership_id})
        
        if not membership:
            raise HTTPException(status_code=404, detail="Membership not found")
        
        # Only organization owner can update
        if membership["organization_id"] != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        # Update membership
        update_data = {k: v for k, v in request.dict().items() if v is not None and v != "" and v != []}
        update_data["updated_at"] = datetime.utcnow()
        
        await db.memberships.update_one(
            {"id": membership_id},
            {"$set": update_data}
        )
        
        return {"message": "Membership details updated"}
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating membership details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/memberships/{membership_id}")
async def get_membership_details(
    membership_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Get membership details with user profile info"""
    try:
        membership = await db.memberships.find_one({"id": membership_id})
        
        if not membership:
            raise HTTPException(status_code=404, detail="Membership not found")
        
        # Only member or organization owner can view
        if membership["member_id"] != current_user_id and membership["organization_id"] != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        # Get user profile information
        user = await db.users.find_one({"id": membership["member_id"]})
        
        membership.pop("_id", None)
        
        # Add user profile data
        if user:
            user.pop("_id", None)
            user.pop("password", None)  # Never send password
            membership["user_profile"] = {
                "full_name": user.get("full_name", ""),
                "email": user.get("email", ""),
                "phone_number": user.get("phone_number", ""),
                "birth_date": user.get("birth_date", ""),
                "gender": user.get("gender", ""),
                "address": user.get("address", ""),
                "profile_picture": user.get("profile_picture", ""),
                "bio": user.get("bio", ""),
                "user_type": user.get("user_type", ""),
            }
        
        return membership
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting membership details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== TRAINING MANAGEMENT ROUTES ====================

@api_router.get("/training-members")
async def get_training_members(
    current_user_id: str = Depends(get_current_user)
):
    """Get members for training management"""
    try:
        # Get user id from dict if needed
        user_id = current_user_id.get("id") if isinstance(current_user_id, dict) else current_user_id
        
        logging.info(f"🔵 /training-members called by user: {user_id}")
        
        # Get all active AND pending memberships for current user (organization)
        # Use same logic as /memberships/my-members - check both creator_id and organization_id
        memberships = await db.memberships.find({
            "$or": [
                {"creator_id": user_id},
                {"organization_id": user_id}
            ],
            "status": {"$in": ["active", "pending"]}
        }).to_list(None)
        
        logging.info(f"🟢 Found {len(memberships)} memberships for training")
        
        members_list = []
        
        for membership in memberships:
            member_id = membership.get("member_id")
            if not member_id:
                continue
            
            # Get member user data
            member_user = await db.users.find_one({"id": member_id})
            if not member_user:
                continue
            
            # Get membership details
            membership_details = membership.get("membership_details", {})
            sport = membership_details.get("sport", "")
            
            # Get skill level from membership or player profile
            skill_level = None
            if membership_details.get("skill_level"):
                skill_level = membership_details.get("skill_level")
            elif member_user.get("player_profile", {}).get("skill_levels"):
                skill_levels = member_user.get("player_profile", {}).get("skill_levels", {})
                if sport and sport in skill_levels:
                    skill_level = skill_levels[sport]
                elif skill_levels:
                    # Get first skill level if sport-specific not found
                    skill_level = list(skill_levels.values())[0] if skill_levels else None
            
            # Get coach information
            coach_name = None
            coach_ids = membership_details.get("coach_ids", [])
            if coach_ids and len(coach_ids) > 0:
                coach = await db.users.find_one({"id": coach_ids[0]})
                if coach:
                    coach_name = coach.get("full_name")
            
            member_data = {
                "id": member_id,
                "full_name": member_user.get("full_name", ""),
                "coach_name": coach_name,
                "date_of_birth": member_user.get("date_of_birth"),
                "gender": member_user.get("gender"),
                "sport": sport,
                "skill_level": skill_level,
                "avatar": member_user.get("avatar"),
                "membership_status": membership.get("status", "active")  # Üyelik durumu
            }
            
            members_list.append(member_data)
        
        return {
            "members": members_list,
            "total": len(members_list)
        }
    except Exception as e:
        logging.error(f"Error fetching training members: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



class CreateTrainingProgramBody(BaseModel):
    member_id: Optional[str] = None  # None for templates
    is_template: bool = False  # True for reusable program templates
    program_type: str  # Günlük, Haftalık, Aylık, Kamp
    title: str
    skill_target: str  # Hız, Dayanıklılık, Teknik, Taktik, etc.
    description: str
    duration: str  # Duration in minutes
    sets: Optional[int] = None
    repetitions: Optional[int] = None
    video_url: Optional[str] = None
    video_type: Optional[str] = "link"  # 'file' or 'link'
    difficulty_level: int = 3  # 1-5
    start_date: Optional[str] = None
    end_date: Optional[str] = None

@api_router.post("/training-programs/create")
async def create_training_program(
    body: CreateTrainingProgramBody,
    current_user_id: str = Depends(get_current_user)
):
    """Create a new training program for a member or as a template"""
    try:
        # Get user id from dict if needed
        user_id = current_user_id.get("id") if isinstance(current_user_id, dict) else current_user_id
        
        logging.info(f"Creating training program - User: {user_id}, Is Template: {body.is_template}, Title: {body.title}")
        
        # If not a template, verify member permission
        if not body.is_template and body.member_id:
            membership = await db.memberships.find_one({
                "$or": [
                    {"creator_id": user_id},
                    {"organization_id": user_id}
                ],
                "member_id": body.member_id,
                "status": {"$in": ["active", "pending"]}
            })
            
            if not membership:
                raise HTTPException(
                    status_code=403,
                    detail="Bu sporcu için program oluşturma yetkiniz yok"
                )
        
        # Create training program document
        program_id = str(uuid.uuid4())
        program = {
            "id": program_id,
            "organization_id": user_id,
            "creator_id": user_id,
            "member_id": body.member_id,  # None for templates
            "is_template": body.is_template,
            "program_type": body.program_type,
            "title": body.title,
            "skill_target": body.skill_target,
            "description": body.description,
            "duration": body.duration,
            "sets": body.sets,
            "repetitions": body.repetitions,
            "video_url": body.video_url,
            "video_type": body.video_type,
            "difficulty_level": body.difficulty_level,
            "start_date": body.start_date,
            "end_date": body.end_date,
            "status": "active" if not body.is_template else "template",  # active, completed, cancelled, template
            "player_feedback": {
                "completed": False,
                "learned": "",
                "challenges": "",
                "media": []  # Array of uploaded photos/videos by player
            },
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        await db.training_programs.insert_one(program)
        
        # Create notification only if assigned to a member (not template)
        if not body.is_template and body.member_id:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": body.member_id,
                "type": "training_program_assigned",
                "title": "Yeni Antrenman Programı",
                "message": f"Size yeni bir antrenman programı atandı: {body.title}",
                "related_type": "training_program",
                "related_id": program_id,
                "data": {
                    "program_id": program_id,
                    "program_type": body.program_type,
                    "title": body.title
                },
                "read": False,
                "created_at": datetime.utcnow().isoformat()
            }
            await db.notifications.insert_one(notification)
        
        return {
            "success": True,
            "program_id": program_id,
            "is_template": body.is_template,
            "message": "Program template created successfully" if body.is_template else "Training program created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error creating training program: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/training-programs/templates")
async def get_program_templates(
    current_user_id: str = Depends(get_current_user)
):
    """Get all program templates created by current user"""
    try:
        # Get user id from dict if needed
        user_id = current_user_id.get("id") if isinstance(current_user_id, dict) else current_user_id
        
        logging.info(f"Fetching templates for user: {user_id}")
        templates = await db.training_programs.find({
            "$or": [
                {"organization_id": user_id},
                {"creator_id": user_id}
            ],
            "is_template": True
        }).sort("created_at", -1).to_list(None)
        
        logging.info(f"Found {len(templates)} templates")
        
        for template in templates:
            template.pop("_id", None)
        
        return {
            "templates": templates,
            "total": len(templates)
        }
    except Exception as e:
        logging.error(f"Error fetching program templates: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/training-programs/{member_id}")
async def get_member_training_programs(
    member_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Get all training programs for a specific member"""
    try:
        # Verify permission
        membership = await db.memberships.find_one({
            "organization_id": current_user_id,
            "member_id": member_id
        })
        
        if not membership:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to view this member's programs"
            )
        
        # Get all programs
        programs = await db.training_programs.find({
            "member_id": member_id,
            "organization_id": current_user_id
        }).sort("created_at", -1).to_list(None)
        
        for program in programs:
            program.pop("_id", None)
        
        return {
            "programs": programs,
            "total": len(programs)
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching training programs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/training-programs/detail/{program_id}")
async def get_program_detail(
    program_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Get detailed information about a training program"""
    try:
        program = await db.training_programs.find_one({"id": program_id})
        
        if not program:
            raise HTTPException(status_code=404, detail="Program not found")
        
        # Verify user has permission (either member or organization owner)
        if program.get("member_id") != current_user_id and program.get("organization_id") != current_user_id:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to view this program"
            )
        
        program.pop("_id", None)
        
        return {"program": program}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching program detail: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

class CompleteProgramBody(BaseModel):
    completed: bool
    learned: str = ""
    challenges: str = ""
    rating: int = 0

@api_router.patch("/training-programs/{program_id}/complete")
async def complete_training_program(
    program_id: str,
    body: CompleteProgramBody,
    current_user_id: str = Depends(get_current_user)
):
    """Player completes a training program and provides feedback"""
    try:
        program = await db.training_programs.find_one({"id": program_id})
        
        if not program:
            raise HTTPException(status_code=404, detail="Program not found")
        
        # Verify the current user is the member assigned to this program
        if program.get("member_id") != current_user_id:
            raise HTTPException(
                status_code=403,
                detail="You can only update your own program feedback"
            )
        
        # Update program with feedback
        update_data = {
            "player_feedback.completed": body.completed,
            "player_feedback.learned": body.learned,
            "player_feedback.challenges": body.challenges,
            "player_feedback.rating": body.rating,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if body.completed:
            update_data["status"] = "completed"
        
        await db.training_programs.update_one(
            {"id": program_id},
            {"$set": update_data}
        )
        
        # Get member (player) info
        member = await db.users.find_one({"id": current_user_id})
        member_name = member.get("full_name", "Sporcu") if member else "Sporcu"
        
        # Send notification to coach/organization owner
        if body.completed and program.get("organization_id"):
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": program.get("organization_id"),
                "type": "training_program_completed",
                "title": "Antrenman Programı Tamamlandı",
                "message": f"{member_name} '{program.get('title')}' programını tamamladı ve {body.rating}/5 puan verdi",
                "data": {
                    "program_id": program_id,
                    "member_id": current_user_id,
                    "member_name": member_name,
                    "program_title": program.get("title"),
                    "rating": body.rating
                },
                "related_type": "training_program",
                "related_id": program_id,
                "read": False,
                "created_at": datetime.utcnow().isoformat()
            }
            await db.notifications.insert_one(notification)
            logging.info(f"Notification sent to coach {program.get('organization_id')} for completed program {program_id}")
        
        return {
            "success": True,
            "message": "Program feedback updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error completing program: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

        if program.get("member_id") != current_user_id:
            raise HTTPException(
                status_code=403,
                detail="You can only update your own program feedback"
            )
        
        update_data = {}
        if completed is not None:
            update_data["player_feedback.completed"] = completed
        if learned is not None:
            update_data["player_feedback.learned"] = learned
        if challenges is not None:
            update_data["player_feedback.challenges"] = challenges
        
        update_data["updated_at"] = datetime.utcnow().isoformat()
        
        await db.training_programs.update_one(
            {"id": program_id},
            {"$set": update_data}
        )
        
        return {"success": True, "message": "Feedback updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating program feedback: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



class AssignTemplateBody(BaseModel):
    template_id: str
    member_id: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None

@api_router.post("/training-programs/assign-template")
async def assign_template_to_member(
    body: AssignTemplateBody,
    current_user_id: str = Depends(get_current_user)
):
    """Assign a program template to a member"""
    try:
        # Get user id from dict if needed
        user_id = current_user_id.get("id") if isinstance(current_user_id, dict) else current_user_id
        
        logging.info(f"🔵 Assigning template {body.template_id} to member {body.member_id} by user {user_id}")
        
        # Get the template - check both organization_id and creator_id
        template = await db.training_programs.find_one({
            "id": body.template_id,
            "$or": [
                {"organization_id": user_id},
                {"creator_id": user_id}
            ],
            "is_template": True
        })
        
        if not template:
            logging.error(f"❌ Template not found: {body.template_id}")
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")
        
        # Verify member permission - check both creator_id and organization_id
        membership = await db.memberships.find_one({
            "$or": [
                {"creator_id": user_id},
                {"organization_id": user_id}
            ],
            "member_id": body.member_id,
            "status": {"$in": ["active", "pending"]}
        })
        
        if not membership:
            logging.error(f"❌ No membership found for member {body.member_id}")
            raise HTTPException(
                status_code=403,
                detail="Bu sporcuya program atama yetkiniz yok"
            )
        
        # Get member info for notification
        member = await db.users.find_one({"id": body.member_id})
        if not member:
            raise HTTPException(status_code=404, detail="Sporcu bulunamadı")
        
        # Get assigner info
        assigner = await db.users.find_one({"id": user_id})
        assigner_name = assigner.get("full_name", "Antrenör") if assigner else "Antrenör"
        
        # Create new program from template
        program_id = str(uuid.uuid4())
        program = {
            "id": program_id,
            "organization_id": user_id,
            "creator_id": user_id,
            "member_id": body.member_id,
            "is_template": False,
            "template_id": body.template_id,  # Reference to original template
            "program_type": template.get("program_type"),
            "title": template.get("title"),
            "skill_target": template.get("skill_target"),
            "description": template.get("description"),
            "duration": template.get("duration"),
            "sets": template.get("sets"),
            "repetitions": template.get("repetitions"),
            "video_url": template.get("video_url"),
            "video_type": template.get("video_type"),
            "video_filename": template.get("video_filename"),
            "difficulty_level": template.get("difficulty_level"),
            "start_date": body.start_date or template.get("start_date"),
            "end_date": body.end_date or template.get("end_date"),
            "status": "active",
            "player_feedback": {
                "completed": False,
                "learned": "",
                "challenges": "",
                "media": []
            },
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        await db.training_programs.insert_one(program)
        logging.info(f"✅ Program created: {program_id}")
        
        # ==================== İŞ AKIŞI TETİKLEME ====================
        # Workflow trigger context
        workflow_context = {
            "user_id": body.member_id,
            "member_id": body.member_id,
            "member_name": member.get("full_name", ""),
            "assigner_id": user_id,
            "assigner_name": assigner_name,
            "program_id": program_id,
            "program_title": template.get("title", ""),
            "program_type": template.get("program_type", ""),
            "template_id": body.template_id
        }
        
        # Try to trigger workflow first
        try:
            workflow_result = await trigger_workflow("on_training_program_assigned", workflow_context)
            logging.info(f"📋 Workflow trigger result: {workflow_result}")
        except Exception as wf_error:
            logging.warning(f"⚠️ Workflow trigger error: {wf_error}")
        
        # Always send default notification (workflow can send additional ones)
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": body.member_id,
            "type": "training_program_assigned",
            "title": "Yeni Antrenman Programı",
            "message": f"{assigner_name} size yeni bir antrenman programı atadı: {template.get('title')}",
            "related_type": "training_program",
            "related_id": program_id,
            "data": {
                "program_id": program_id,
                "program_type": template.get("program_type"),
                "title": template.get("title"),
                "assigner_id": user_id,
                "assigner_name": assigner_name
            },
            "read": False,
            "created_at": datetime.utcnow().isoformat()
        }
        await db.notifications.insert_one(notification)
        logging.info(f"📬 Notification sent to {body.member_id}")
        
        return {
            "success": True,
            "program_id": program_id,
            "message": "Program sporcuya başarıyla atandı"
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ Error assigning template: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==================== VIDEO UPLOAD ROUTES ====================

# Temporary storage for video chunks
video_chunks_storage = {}

class VideoChunkBody(BaseModel):
    upload_id: str
    chunk_index: int
    total_chunks: int
    chunk_data: str  # Base64 encoded
    filename: str
    mime_type: str = "video/mp4"

class VideoFinalizeBody(BaseModel):
    upload_id: str
    filename: str

@api_router.post("/upload/video-chunk")
async def upload_video_chunk(
    body: VideoChunkBody,
    current_user_id: str = Depends(get_current_user)
):
    """Upload a video chunk"""
    try:
        upload_key = f"{current_user_id}_{body.upload_id}"
        
        if upload_key not in video_chunks_storage:
            video_chunks_storage[upload_key] = {
                "chunks": {},
                "total_chunks": body.total_chunks,
                "filename": body.filename,
                "mime_type": body.mime_type,
                "user_id": current_user_id
            }
        
        # Store chunk
        video_chunks_storage[upload_key]["chunks"][body.chunk_index] = body.chunk_data
        
        logging.info(f"Received chunk {body.chunk_index + 1}/{body.total_chunks} for upload {upload_key}")
        
        return {
            "success": True,
            "chunk_index": body.chunk_index,
            "received_chunks": len(video_chunks_storage[upload_key]["chunks"])
        }
    except Exception as e:
        logging.error(f"Error uploading video chunk: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/upload/video-finalize")
async def finalize_video_upload(
    body: VideoFinalizeBody,
    current_user_id: str = Depends(get_current_user)
):
    """Finalize video upload and combine chunks"""
    try:
        upload_key = f"{current_user_id}_{body.upload_id}"
        
        if upload_key not in video_chunks_storage:
            raise HTTPException(status_code=404, detail="Upload not found")
        
        upload_data = video_chunks_storage[upload_key]
        
        # Check all chunks received
        if len(upload_data["chunks"]) != upload_data["total_chunks"]:
            raise HTTPException(
                status_code=400,
                detail=f"Missing chunks. Received {len(upload_data['chunks'])}/{upload_data['total_chunks']}"
            )
        
        # Combine chunks in order
        combined_base64 = ""
        for i in range(upload_data["total_chunks"]):
            if i not in upload_data["chunks"]:
                raise HTTPException(status_code=400, detail=f"Missing chunk {i}")
            combined_base64 += upload_data["chunks"][i]
        
        # Generate unique filename
        file_ext = body.filename.split('.')[-1] if '.' in body.filename else 'mp4'
        unique_filename = f"{current_user_id}_{body.upload_id}.{file_ext}"
        
        # Save to database (or file system)
        # For now, we'll store in MongoDB as base64 with a reference
        video_doc = {
            "id": body.upload_id,
            "user_id": current_user_id,
            "filename": body.filename,
            "unique_filename": unique_filename,
            "mime_type": upload_data["mime_type"],
            "video_data": combined_base64,  # In production, save to S3/Cloud Storage
            "size": len(combined_base64),
            "created_at": datetime.utcnow().isoformat()
        }
        
        await db.videos.insert_one(video_doc)
        
        # Clean up chunks from memory
        del video_chunks_storage[upload_key]
        
        # Return video URL (in this case, the upload_id to retrieve it)
        video_url = f"/api/videos/{body.upload_id}"
        
        logging.info(f"Video upload finalized: {unique_filename}, size: {len(combined_base64)} bytes")
        
        return {
            "success": True,
            "video_url": video_url,
            "video_id": body.upload_id,
            "filename": unique_filename
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error finalizing video upload: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/videos/{video_id}")
async def get_video(
    video_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Get video data"""
    try:
        video = await db.videos.find_one({"id": video_id})
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # In production, return signed URL from S3/Cloud Storage
        # For now, return base64 data
        return {
            "id": video.get("id"),
            "filename": video.get("filename"),
            "mime_type": video.get("mime_type"),
            "video_data": video.get("video_data"),
            "created_at": video.get("created_at")
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting video: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logging.error(f"Error assigning template: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# CLUB ATHLETES MANAGEMENT
# ============================================

class AthleteData(BaseModel):
    name: str
    birth_date: str
    sport_branch: str
    age_group: str = ""
    license_number: str = ""
    gender: str = ""
    license_renewal_date: str = ""
    contract_status: bool = False
    contract_date: str = ""
    membership_fee: float = 0.0
    documents_status: str = ""
    tc_id: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    parent_name: str = ""
    parent_phone: str = ""
    blood_type: str = ""
    athlete_type: str = ""
    health_report_status: str = ""
    notes: str = ""


@api_router.get("/club-athletes")
async def get_club_athletes(current_user_data: dict = Depends(get_current_user)):
    """Get all athletes for current organization - includes both club_athletes and memberships"""
    try:
        # get_current_user returns dict with {"id": ..., "user_type": ...}
        current_user_id = current_user_data.get("id") if isinstance(current_user_data, dict) else current_user_data
        
        logging.info(f"🏃 /club-athletes called by user_id: {current_user_id}")
        
        # First, get club_athletes (detailed athlete records)
        athletes = await db.club_athletes.find({
            "organization_id": current_user_id
        }).sort("name", 1).to_list(1000)
        
        for athlete in athletes:
            athlete.pop("_id", None)
        
        logging.info(f"🏃 Found {len(athletes)} club_athletes")
        
        # If no club athletes found, fetch from memberships and convert to athlete format
        if len(athletes) == 0:
            memberships = await db.memberships.find({
                "organization_id": current_user_id,
                "status": "active"
            }).to_list(1000)
            
            logging.info(f"🏃 Found {len(memberships)} active memberships")
            
            # Enrich with member data
            for membership in memberships:
                member = await db.users.find_one({"id": membership["member_id"]})
                if member:
                    # Get player profile data
                    player_profile = member.get("player_profile", {}) or {}
                    
                    # Translate gender to Turkish
                    gender_raw = player_profile.get("gender", "")
                    gender_tr = ""
                    if gender_raw:
                        if gender_raw.lower() in ["male", "erkek"]:
                            gender_tr = "Erkek"
                        elif gender_raw.lower() in ["female", "kadın", "kadin"]:
                            gender_tr = "Kadın"
                        else:
                            gender_tr = gender_raw
                    
                    # Get sports as comma-separated string
                    sports_list = player_profile.get("sports", []) or []
                    sport_branch = ", ".join(sports_list) if sports_list else ""
                    
                    # Convert membership to athlete format
                    athlete = {
                        "id": membership.get("id", str(uuid.uuid4())),
                        "name": member.get("full_name", ""),
                        "birth_date": player_profile.get("date_of_birth", "") or member.get("birth_date", ""),
                        "sport_branch": sport_branch,
                        "age_group": player_profile.get("age_group", ""),
                        "license_number": player_profile.get("license_number", ""),
                        "gender": gender_tr,
                        "license_renewal_date": "",
                        "contract_status": False,
                        "contract_date": "",
                        "membership_fee": membership.get("fee", 0.0) or 0.0,
                        "documents_status": "Yok",
                        "tc_id": member.get("tc_id", ""),
                        "phone": member.get("phone", ""),
                        "email": member.get("email", ""),
                        "address": member.get("address", ""),
                        "parent_name": "",
                        "parent_phone": "",
                        "blood_type": player_profile.get("blood_type", ""),
                        "athlete_type": "Amatör",
                        "health_report_status": "",
                        "notes": f"Üyelik ID: {membership['member_id']}"
                    }
                    athletes.append(athlete)
        
        logging.info(f"🏃 Returning {len(athletes)} total athletes")
        return {"athletes": athletes}
    except Exception as e:
        logging.error(f"Error getting athletes: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/club-athletes")
async def create_athlete(
    data: AthleteData,
    current_user_data: dict = Depends(get_current_user)
):
    """Create new athlete"""
    try:
        # get_current_user returns dict with {"id": ..., "user_type": ...}
        current_user_id = current_user_data.get("id") if isinstance(current_user_data, dict) else current_user_data
        
        athlete = {
            "id": str(uuid.uuid4()),
            "organization_id": current_user_id,
            **data.dict(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.club_athletes.insert_one(athlete)
        athlete.pop("_id", None)
        
        return athlete
    except Exception as e:
        logging.error(f"Error creating athlete: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/club-athletes/{athlete_id}")
async def update_athlete(
    athlete_id: str,
    data: AthleteData,
    current_user_id: str = Depends(get_current_user)
):
    """Update athlete"""
    try:
        athlete = await db.club_athletes.find_one({
            "id": athlete_id,
            "organization_id": current_user_id
        })
        
        if not athlete:
            raise HTTPException(status_code=404, detail="Athlete not found")
        
        await db.club_athletes.update_one(
            {"id": athlete_id},
            {"$set": {
                **data.dict(),
                "updated_at": datetime.utcnow()
            }}
        )
        
        return {"message": "Athlete updated"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating athlete: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/club-athletes/{athlete_id}")
async def delete_athlete(
    athlete_id: str,
    current_user_id: str = Depends(get_current_user)
):
    """Delete athlete"""
    try:
        result = await db.club_athletes.delete_one({
            "id": athlete_id,
            "organization_id": current_user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Athlete not found")
        
        return {"message": "Athlete deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting athlete: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ADMIN EVENT APPROVAL ROUTES ====================

@api_router.get("/admin/events/pending", response_model=List[Event])
async def get_pending_events(current_user_id: str = Depends(get_current_user)):
    """Get all events pending approval (Admin only)"""
    user = await db.users.find_one({"id": current_user_id})
    if not user or user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    events = await db.events.find({"status": "pending"}).sort("created_at", -1).to_list(100)
    return [Event(**event) for event in events]

@api_router.post("/admin/events/{event_id}/approve")
async def approve_event(event_id: str, current_user: dict = Depends(get_current_user)):
    """Approve a pending event (Admin only)"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    user = await db.users.find_one({"id": current_user_id})
    if not user or user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Event is not pending approval")
    
    # Update event status
    await db.events.update_one(
        {"id": event_id},
        {"$set": {"status": "active"}}
    )
    
    # Notify event organizer
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": event["organizer_id"],
        "type": "event_approved",
        "title": "Etkinlik Onaylandı",
        "message": f"'{event['title']}' etkinliğiniz onaylandı ve yayında!",
        "read": False,
        "created_at": datetime.utcnow(),
        "event_id": event_id,
        "data": {
            "event_id": event_id,
            "event_title": event['title']
        }
    }
    await db.notifications.insert_one(notification)
    
    return {"message": "Event approved successfully", "event_id": event_id}

@api_router.post("/admin/events/{event_id}/reject")
async def reject_event(
    event_id: str,
    reason: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """Reject a pending event (Admin only)"""
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    user = await db.users.find_one({"id": current_user_id})
    if not user or user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Event is not pending approval")
    
    # Update event status
    await db.events.update_one(
        {"id": event_id},
        {"$set": {"status": "rejected"}}
    )
    
    # Notify event organizer
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": event["organizer_id"],
        "type": "event_rejected",
        "title": "Etkinlik Reddedildi",
        "message": f"'{event['title']}' etkinliğiniz reddedildi. Sebep: {reason}",
        "read": False,
        "created_at": datetime.utcnow(),
        "event_id": event_id,
        "data": {
            "event_id": event_id,
            "event_title": event['title'],
            "reason": reason
        }
    }
    await db.notifications.insert_one(notification)
    
    return {"message": "Event rejected successfully", "event_id": event_id}

# ==================== PARTNER REQUEST ENDPOINTS ====================

class PartnerRequestCreate(BaseModel):
    target_user_id: str
    event_id: str
    game_type: str
    message: Optional[str] = None

@api_router.post("/partner-requests")
async def create_partner_request(
    request_data: PartnerRequestCreate,
    current_user: dict = Depends(get_current_user)
):
    """Çift/Partner isteği gönder"""
    requester_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    target_id = request_data.target_user_id
    event_id = request_data.event_id
    game_type = request_data.game_type
    
    print(f"🤝 Partner request: {requester_id} -> {target_id} for event {event_id}")
    
    if requester_id == target_id:
        raise HTTPException(status_code=400, detail="Kendinize partner isteği gönderemezsiniz")
    
    target_user = await db.users.find_one({"id": target_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="Hedef kullanıcı bulunamadı")
    
    requester = await db.users.find_one({"id": requester_id})
    if not requester:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # CİNSİYET KONTROLÜ
    requester_gender = requester.get("gender", "").lower()
    target_gender = target_user.get("gender", "").lower()
    
    if game_type == "cift":
        # Çift: Aynı cinsiyetten olmalı
        if requester_gender and target_gender and requester_gender != target_gender:
            raise HTTPException(status_code=400, detail="Çift kategorisi için aynı cinsiyetten partner seçmelisiniz")
    elif game_type == "karisik_cift":
        # Karışık Çift: Farklı cinsiyetten olmalı
        if requester_gender and target_gender and requester_gender == target_gender:
            raise HTTPException(status_code=400, detail="Karışık çift kategorisi için farklı cinsiyetten partner seçmelisiniz")
    
    # Zaten eşleşmiş mi kontrol et (game_type bazında - aynı kullanıcı farklı game_type'larda eşleşebilir)
    existing_match = await db.partner_requests.find_one({
        "event_id": event_id,
        "game_type": game_type,
        "status": "accepted",
        "$or": [
            {"requester_id": requester_id},
            {"target_id": requester_id},
            {"requester_id": target_id},
            {"target_id": target_id}
        ]
    })
    
    if existing_match:
        if existing_match["requester_id"] == requester_id or existing_match["target_id"] == requester_id:
            raise HTTPException(status_code=400, detail="Bu etkinlikte zaten bir partneriniz var")
        else:
            raise HTTPException(status_code=400, detail="Seçtiğiniz kullanıcının bu etkinlikte zaten bir partneri var")
    
    # Bekleyen istek var mı
    pending_request = await db.partner_requests.find_one({
        "event_id": event_id,
        "game_type": game_type,
        "requester_id": requester_id,
        "target_id": target_id,
        "status": "pending"
    })
    
    if pending_request:
        raise HTTPException(status_code=400, detail="Bu kullanıcıya zaten bekleyen bir isteğiniz var")
    
    # Partner isteği oluştur
    request_id = str(uuid.uuid4())
    
    game_type_labels = {'cift': 'Çift', 'karisik_cift': 'Karışık Çift', 'takim': 'Takım'}
    game_label = game_type_labels.get(game_type, game_type)
    
    partner_request = {
        "id": request_id,
        "requester_id": requester_id,
        "requester_name": requester.get("full_name", "Bilinmiyor"),
        "target_id": target_id,
        "target_name": target_user.get("full_name", "Bilinmiyor"),
        "event_id": event_id,
        "event_title": event.get("title", "Etkinlik"),
        "game_type": game_type,
        "game_type_label": game_label,
        "message": request_data.message,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.partner_requests.insert_one(partner_request)
    print(f"✅ Partner request created: {request_id}")
    
    # Hedef kullanıcıya bildirim gönder
    notification = {
        "id": f"notif_partner_{request_id}",
        "user_id": target_id,
        "type": "partner_request",
        "title": "🤝 Partner İsteği",
        "message": f"{requester.get('full_name', 'Bir kullanıcı')} sizi '{event.get('title', 'Etkinlik')}' etkinliğinde {game_label} kategorisi için partner olarak seçti.",
        "data": {
            "request_id": request_id,
            "requester_id": requester_id,
            "requester_name": requester.get("full_name"),
            "event_id": event_id,
            "event_title": event.get("title"),
            "game_type": game_type,
            "action_required": True
        },
        "is_read": False,
        "created_at": datetime.utcnow()
    }
    
    await db.notifications.insert_one(notification)
    print(f"🔔 Notification sent to {target_id}")
    
    return {"status": "success", "message": "Partner isteği gönderildi", "request_id": request_id}

@api_router.post("/partner-requests/{request_id}/accept")
async def accept_partner_request(
    request_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Partner isteğini kabul et"""
    user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    partner_request = await db.partner_requests.find_one({"id": request_id})
    if not partner_request:
        raise HTTPException(status_code=404, detail="Partner isteği bulunamadı")
    
    if partner_request["target_id"] != user_id:
        raise HTTPException(status_code=403, detail="Bu isteği kabul etme yetkiniz yok")
    
    if partner_request["status"] != "pending":
        status_messages = {
            "accepted": "Bu istek zaten kabul edilmiş",
            "rejected": "Bu istek zaten reddedilmiş", 
            "cancelled": "Bu istek iptal edildi. Gönderen kişi başka biriyle eşleşmiş olabilir.",
            "expired": "Bu isteğin süresi dolmuş"
        }
        message = status_messages.get(partner_request["status"], f"Bu istek zaten {partner_request['status']} durumunda")
        raise HTTPException(status_code=400, detail=message)
    
    # Kabul eden kullanıcının başka eşleşmesi var mı
    existing_match = await db.partner_requests.find_one({
        "event_id": partner_request["event_id"],
        "game_type": partner_request["game_type"],
        "status": "accepted",
        "$or": [{"requester_id": user_id}, {"target_id": user_id}]
    })
    
    if existing_match:
        raise HTTPException(status_code=400, detail="Bu etkinlikte zaten bir partneriniz var")
    
    # Kabul et
    await db.partner_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "accepted", "responded_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
    )
    
    print(f"✅ Partner request accepted: {request_id}")
    
    # Gönderene bildirim
    target_user = await db.users.find_one({"id": user_id})
    notification = {
        "id": f"notif_partner_accepted_{request_id}",
        "user_id": partner_request["requester_id"],
        "type": "partner_request_accepted",
        "title": "✅ Partner İsteği Kabul Edildi",
        "message": f"{target_user.get('full_name', 'Kullanıcı')} partner isteğinizi kabul etti! '{partner_request.get('event_title', 'Etkinlik')}' etkinliğinde eşleştiniz.",
        "data": {
            "request_id": request_id,
            "partner_id": user_id,
            "partner_name": target_user.get("full_name"),
            "event_id": partner_request["event_id"],
            "game_type": partner_request["game_type"]
        },
        "is_read": False,
        "created_at": datetime.utcnow()
    }
    await db.notifications.insert_one(notification)
    
    # Orijinal partner request bildirimini güncelle - action_required = False
    await db.notifications.update_one(
        {"id": f"notif_partner_{request_id}"},
        {"$set": {"data.action_required": False, "data.processed": True, "data.processed_result": "accepted"}}
    )
    
    # Diğer bekleyen istekleri iptal et
    await db.partner_requests.update_many(
        {
            "event_id": partner_request["event_id"],
            "game_type": partner_request["game_type"],
            "status": "pending",
            "$or": [
                {"requester_id": partner_request["requester_id"]},
                {"target_id": partner_request["requester_id"]},
                {"requester_id": user_id},
                {"target_id": user_id}
            ],
            "id": {"$ne": request_id}
        },
        {"$set": {"status": "cancelled", "cancel_reason": "Başka eşleşme kabul edildi", "updated_at": datetime.utcnow()}}
    )
    
    return {"status": "success", "message": "Partner isteği kabul edildi", "partner": {"id": partner_request["requester_id"], "name": partner_request["requester_name"]}}

@api_router.post("/partner-requests/{request_id}/reject")
async def reject_partner_request(
    request_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Partner isteğini reddet"""
    user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    partner_request = await db.partner_requests.find_one({"id": request_id})
    if not partner_request:
        raise HTTPException(status_code=404, detail="Partner isteği bulunamadı")
    
    if partner_request["target_id"] != user_id:
        raise HTTPException(status_code=403, detail="Bu isteği reddetme yetkiniz yok")
    
    if partner_request["status"] != "pending":
        status_messages = {
            "accepted": "Bu istek zaten kabul edilmiş",
            "rejected": "Bu istek zaten reddedilmiş", 
            "cancelled": "Bu istek iptal edildi. Gönderen kişi başka biriyle eşleşmiş olabilir.",
            "expired": "Bu isteğin süresi dolmuş"
        }
        message = status_messages.get(partner_request["status"], f"Bu istek zaten {partner_request['status']} durumunda")
        raise HTTPException(status_code=400, detail=message)
    
    # Reddet
    await db.partner_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "rejected", "responded_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
    )
    
    print(f"❌ Partner request rejected: {request_id}")
    
    # Gönderene bildirim
    target_user = await db.users.find_one({"id": user_id})
    notification = {
        "id": f"notif_partner_rejected_{request_id}",
        "user_id": partner_request["requester_id"],
        "type": "partner_request_rejected",
        "title": "❌ Partner İsteği Reddedildi",
        "message": f"{target_user.get('full_name', 'Kullanıcı')} partner isteğinizi reddetti.",
        "data": {"request_id": request_id, "event_id": partner_request["event_id"], "game_type": partner_request["game_type"]},
        "is_read": False,
        "created_at": datetime.utcnow()
    }
    await db.notifications.insert_one(notification)
    
    # Orijinal partner request bildirimini güncelle - action_required = False
    await db.notifications.update_one(
        {"id": f"notif_partner_{request_id}"},
        {"$set": {"data.action_required": False, "data.processed": True, "data.processed_result": "rejected"}}
    )
    
    return {"status": "success", "message": "Partner isteği reddedildi"}

@api_router.get("/partner-requests/my")
async def get_my_partner_requests(
    event_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Kullanıcının partner isteklerini getir"""
    user_id = current_user.get("id") if isinstance(current_user, dict) else current_user
    
    query = {"$or": [{"requester_id": user_id}, {"target_id": user_id}]}
    if event_id:
        query["event_id"] = event_id
    
    requests = await db.partner_requests.find(query).sort("created_at", -1).to_list(length=100)
    
    incoming = []
    outgoing = []
    for req in requests:
        req["_id"] = str(req.get("_id", ""))
        if req["target_id"] == user_id:
            incoming.append(req)
        else:
            outgoing.append(req)
    
    return {"incoming": incoming, "outgoing": outgoing, "total": len(requests)}

@api_router.get("/partner-requests/event/{event_id}/matches")
async def get_event_matches(event_id: str, game_type: Optional[str] = None):
    """Etkinlikteki onaylanmış eşleşmeleri getir"""
    query = {"event_id": event_id, "status": "accepted"}
    if game_type:
        query["game_type"] = game_type
    
    matches = await db.partner_requests.find(query).to_list(length=100)
    
    result = []
    for match in matches:
        result.append({
            "id": match["id"],
            "player1_id": match["requester_id"],
            "player1_name": match["requester_name"],
            "player2_id": match["target_id"],
            "player2_name": match["target_name"],
            "game_type": match["game_type"],
            "game_type_label": match.get("game_type_label", match["game_type"]),
            "matched_at": match.get("responded_at")
        })
    
    return {"matches": result, "total": len(result)}

@api_router.get("/partner-requests/event/{event_id}/matched-users")
async def get_matched_user_ids(event_id: str, game_type: str):
    """Eşleşmiş kullanıcı ID'lerini getir"""
    matches = await db.partner_requests.find({
        "event_id": event_id,
        "game_type": game_type,
        "status": "accepted"
    }).to_list(length=100)
    
    matched_ids = set()
    for match in matches:
        matched_ids.add(match["requester_id"])
        matched_ids.add(match["target_id"])
    
    return {"matched_user_ids": list(matched_ids)}


# =====================================================
# KULLANICI LOG YÖNETİMİ
# =====================================================

async def log_user_activity(
    user_id: str,
    action_type: str,
    result: str,
    details: dict = None,
    ip_address: str = None
):
    """Kullanıcı aktivitesini logla"""
    try:
        # Kullanıcı bilgilerini al
        user = await db.users.find_one({"id": user_id})
        
        log_entry = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "user_name": user.get("full_name", "Bilinmeyen") if user else "Bilinmeyen",
            "user_type": user.get("user_type", "unknown") if user else "unknown",
            "phone": user.get("phone", "") if user else "",
            "action_type": action_type,
            "result": result,  # success, failed, error, warning, info
            "details": details or {},
            "ip_address": ip_address,
            "created_at": datetime.utcnow()
        }
        
        await db.user_activity_logs.insert_one(log_entry)
        return log_entry
    except Exception as e:
        logger.error(f"Error logging user activity: {e}")
        return None


@api_router.get("/admin/user-logs")
async def get_user_logs(
    period: str = "daily",  # daily, weekly, monthly, yearly, all
    user_type: str = None,
    user_name: str = None,
    action_type: str = None,
    action_types: str = None,  # Virgülle ayrılmış birden fazla action_type
    result: str = None,
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """Kullanıcı loglarını getir - Sadece admin"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    query = {}
    
    # Zaman filtresi
    now = datetime.utcnow()
    if period == "daily":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        start_date = now - timedelta(days=7)
    elif period == "monthly":
        start_date = now - timedelta(days=30)
    elif period == "yearly":
        start_date = now - timedelta(days=365)
    else:
        start_date = None
    
    if start_date:
        query["created_at"] = {"$gte": start_date}
    
    # Kullanıcı tipi filtresi
    if user_type and user_type != "all":
        query["user_type"] = user_type
    
    # Kullanıcı adı filtresi (kısmi arama)
    if user_name:
        query["user_name"] = {"$regex": user_name, "$options": "i"}
    
    # Birden fazla işlem tipi filtresi (action_types)
    if action_types:
        types_list = [t.strip() for t in action_types.split(',') if t.strip()]
        if types_list:
            query["action_type"] = {"$in": types_list}
    # Tek işlem tipi filtresi
    elif action_type and action_type != "all":
        query["action_type"] = action_type
    
    # Sonuç filtresi
    if result and result != "all":
        query["result"] = result
    
    # Logları getir
    logs = await db.user_activity_logs.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    # _id'yi string'e çevir
    for log in logs:
        log["_id"] = str(log.get("_id", ""))
        if isinstance(log.get("created_at"), datetime):
            log["created_at"] = log["created_at"].isoformat()
    
    # Toplam sayı
    total = await db.user_activity_logs.count_documents(query)
    
    # İstatistikler
    stats = {
        "total_logs": total,
        "success_count": await db.user_activity_logs.count_documents({**query, "result": "success"}),
        "failed_count": await db.user_activity_logs.count_documents({**query, "result": "failed"}),
        "error_count": await db.user_activity_logs.count_documents({**query, "result": "error"}),
    }
    
    return {
        "logs": logs,
        "total": total,
        "stats": stats,
        "skip": skip,
        "limit": limit
    }


@api_router.get("/admin/user-logs/action-types")
async def get_action_types(current_user: dict = Depends(get_current_user)):
    """Mevcut işlem tiplerini getir"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    action_types = await db.user_activity_logs.distinct("action_type")
    return {"action_types": action_types}


@api_router.post("/admin/user-logs/generate-sample")
async def generate_sample_logs(current_user: dict = Depends(get_current_user)):
    """Örnek loglar oluştur - Test amaçlı"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Kullanıcıları al
    users = await db.users.find().limit(20).to_list(20)
    
    action_types = [
        "login", "logout", "register", "profile_update", "password_change",
        "event_join", "event_leave", "event_create", "reservation_create",
        "payment_success", "payment_failed", "message_send", "review_create"
    ]
    
    results = ["success", "failed", "error", "warning", "info"]
    
    import random
    
    logs_created = 0
    for user in users:
        # Her kullanıcı için 1-5 arası log oluştur
        for _ in range(random.randint(1, 5)):
            action = random.choice(action_types)
            result = random.choices(results, weights=[70, 15, 5, 5, 5])[0]
            
            # Rastgele tarih (son 30 gün)
            days_ago = random.randint(0, 30)
            hours_ago = random.randint(0, 23)
            created_at = datetime.utcnow() - timedelta(days=days_ago, hours=hours_ago)
            
            log_entry = {
                "id": str(uuid.uuid4()),
                "user_id": user.get("id"),
                "user_name": user.get("full_name", "Bilinmeyen"),
                "user_type": user.get("user_type", "unknown"),
                "phone": user.get("phone", ""),
                "action_type": action,
                "result": result,
                "details": {"auto_generated": True},
                "ip_address": f"192.168.1.{random.randint(1, 255)}",
                "created_at": created_at
            }
            
            await db.user_activity_logs.insert_one(log_entry)
            logs_created += 1
    
    return {"status": "success", "logs_created": logs_created}


# Include routers
# CRITICAL: membership_router MUST come before api_router to avoid route conflicts
# api_router has /memberships/{membership_id} which would match /memberships/facilities
app.include_router(membership_router, prefix="/api", tags=["memberships"])
app.include_router(api_router, prefix="/api")
app.include_router(notification_router, prefix="/api", tags=["notifications"])
app.include_router(support_router, prefix="/api", tags=["support"])
app.include_router(review_router, prefix="/api", tags=["reviews"])
app.include_router(tournament_router, prefix="/api", tags=["tournaments"])
app.include_router(tournament_v2_router, prefix="/api/tournaments-v2", tags=["tournaments-v2"])
app.include_router(marketplace_router, prefix="/api/marketplace", tags=["marketplace"])
app.include_router(facility_router, prefix="/api", tags=["facilities"])
app.include_router(reservation_payment_router, prefix="/api", tags=["reservation-payment"])
app.include_router(event_payment_router, prefix="/api", tags=["event-payments"])
app.include_router(person_reservation_payment_router, prefix="/api", tags=["person-reservation-payment"])
app.include_router(sport_config_router, prefix="/api", tags=["sport-configs"])
app.include_router(promo_code_router, prefix="/api", tags=["promo-codes"])

# Management endpoints
from management_endpoints import router as management_router
app.include_router(management_router, prefix="/api", tags=["management"])
app.include_router(expense_router, prefix="/api", tags=["expenses"])

# Event Management endpoints
set_event_management_db(db)
app.include_router(event_management_router, prefix="/api", tags=["event-management"])

# League Management endpoints
# Note: DB is set during startup event, not here
app.include_router(league_management_router, prefix="/api", tags=["league-management"])

# Custom Scoring endpoints
app.include_router(custom_scoring_router, prefix="/api", tags=["custom-scoring"])

# System Tests endpoints
app.include_router(system_tests_router, prefix="/api", tags=["system-tests"])

# ==================== TEST REPORTS ====================

test_reports_router = APIRouter(tags=["test-reports"])

@test_reports_router.post("/test-reports")
async def save_test_report(
    report_data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Save a test report"""
    try:
        current_user_id = current_user.get("id")
        user = await db.users.find_one({"id": current_user_id})
        
        report = {
            "id": str(uuid.uuid4()),
            "report_type": report_data.get("report_type", "coach"),  # coach, player, facility, etc.
            "user_id": current_user_id,
            "user_name": user.get("full_name") if user else "Bilinmeyen",
            "tester_name": report_data.get("tester_name", ""),
            "test_items": report_data.get("test_items", []),
            "stats": report_data.get("stats", {}),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.test_reports.insert_one(report)
        report.pop("_id", None)
        
        logging.info(f"✅ Test report saved by user {current_user_id}: {report['id']}")
        return {"message": "Test raporu kaydedildi", "report_id": report["id"]}
    except Exception as e:
        logging.error(f"Error saving test report: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@test_reports_router.get("/test-reports")
async def get_test_reports(
    report_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """Get all test reports (public - anyone can view)"""
    try:
        query = {}
        if report_type:
            query["report_type"] = report_type
        
        reports = await db.test_reports.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
        
        for report in reports:
            report.pop("_id", None)
        
        total = await db.test_reports.count_documents(query)
        
        return {
            "reports": reports,
            "total": total
        }
    except Exception as e:
        logging.error(f"Error getting test reports: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@test_reports_router.get("/test-reports/{report_id}")
async def get_test_report_by_id(report_id: str):
    """Get a specific test report by ID (public)"""
    try:
        report = await db.test_reports.find_one({"id": report_id})
        
        if not report:
            raise HTTPException(status_code=404, detail="Test raporu bulunamadı")
        
        report.pop("_id", None)
        return report
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting test report: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@test_reports_router.get("/test-reports/latest/{report_type}")
async def get_latest_test_report(report_type: str):
    """Get the latest test report of a specific type (public)"""
    try:
        report = await db.test_reports.find_one(
            {"report_type": report_type},
            sort=[("created_at", -1)]
        )
        
        if not report:
            return None
        
        report.pop("_id", None)
        return report
    except Exception as e:
        logging.error(f"Error getting latest test report: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

app.include_router(test_reports_router, prefix="/api")

# Yeni modüler router'lar - NOT: Şu an server.py'daki endpoint'ler hala aktif
# Modüller tamamen entegre edildiğinde eski endpoint'ler kaldırılacak
# Modular routers - Auth and Users moved to separate files
app.include_router(auth_router, prefix="/api/auth", tags=["auth-modular"])
app.include_router(user_router, prefix="/api", tags=["users-modular"])
app.include_router(report_router, prefix="/api", tags=["reports-detailed"])
app.include_router(map_router, prefix="/api", tags=["map"])
app.include_router(message_router, prefix="/api", tags=["messages-modular"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin-modular"])
app.include_router(commission_router, prefix="/api", tags=["commission"])
app.include_router(geliver_router, prefix="/api", tags=["shipping"])
app.include_router(cancellation_router, tags=["cancellation"])
app.include_router(workflow_router, prefix="/api", tags=["workflow"])
app.include_router(assistant_router, prefix="/api", tags=["assistants"])
app.include_router(ranking_router, tags=["ranking-management"])
app.include_router(legal_router, prefix="/api", tags=["legal"])

# Admin users endpoint - doğrudan eklendi (router sorunu için)
@app.get("/api/admin/users-list")
async def get_all_users_direct(current_user: dict = Depends(get_current_user)):
    """Get all users - direct endpoint"""
    # Admin kontrolü
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    
    users = await db.users.find({}).to_list(200)
    result = []
    for user in users:
        user.pop("_id", None)
        user.pop("password_hash", None)
        user.pop("hashed_password", None)
        result.append(user)
    
    return {"users": result, "total": len(result)}

# ==================== USER ACTIVITY HISTORY ====================
@app.get("/api/user/activity-history")
async def get_user_activity_history(
    current_user: dict = Depends(get_current_user)
):
    """Kullanıcının katıldığı etkinlikler ve yaptığı rezervasyonları getirir"""
    try:
        user_id = current_user.get("id")
        
        # 1. Katıldığı etkinlikler
        participated_events = await db.event_participants.find({
            "user_id": user_id,
            "status": {"$in": ["confirmed", "pending", "completed"]}
        }).sort("created_at", -1).to_list(50)
        
        events_list = []
        for participation in participated_events:
            event = await db.events.find_one({"id": participation.get("event_id")})
            if event:
                event.pop("_id", None)
                is_past = True
                if event.get("date"):
                    try:
                        is_past = datetime.strptime(event.get("date"), "%Y-%m-%d") < datetime.utcnow()
                    except:
                        pass
                events_list.append({
                    "id": event.get("id"),
                    "type": "event",
                    "title": event.get("title"),
                    "date": event.get("date"),
                    "start_time": event.get("start_time"),
                    "end_time": event.get("end_time"),
                    "location": event.get("location"),
                    "sport_type": event.get("sport_type"),
                    "status": participation.get("status"),
                    "payment_status": participation.get("payment_status"),
                    "image": event.get("image"),
                    "venue_name": event.get("venue_name"),
                    "created_at": participation.get("created_at"),
                    "is_past": is_past
                })
        
        # 2. Tesis rezervasyonları
        facility_reservations = await db.facility_reservations.find({
            "user_id": user_id
        }).sort("created_at", -1).to_list(50)
        
        facility_list = []
        for reservation in facility_reservations:
            reservation.pop("_id", None)
            facility = await db.facilities.find_one({"id": reservation.get("facility_id")})
            facility_name = facility.get("name") if facility else "Tesis"
            
            reservation_date = reservation.get("date")
            is_past = True
            if reservation_date:
                try:
                    if isinstance(reservation_date, str):
                        is_past = datetime.strptime(reservation_date, "%Y-%m-%d") < datetime.utcnow()
                    else:
                        is_past = reservation_date < datetime.utcnow()
                except:
                    pass
            
            facility_list.append({
                "id": reservation.get("id"),
                "type": "facility_reservation",
                "title": f"{facility_name} Rezervasyonu",
                "date": reservation_date,
                "start_time": reservation.get("start_time"),
                "end_time": reservation.get("end_time"),
                "facility_name": facility_name,
                "field_name": reservation.get("field_name"),
                "status": reservation.get("status"),
                "payment_status": reservation.get("payment_status"),
                "total_price": reservation.get("total_price"),
                "created_at": reservation.get("created_at"),
                "is_past": is_past
            })
        
        # 3. Kişi rezervasyonları (antrenör, hakem, oyuncu)
        person_reservations = await db.reservations.find({
            "$or": [
                {"user_id": user_id},
                {"requester_id": user_id}
            ]
        }).sort("created_at", -1).to_list(50)
        
        person_list = []
        for reservation in person_reservations:
            reservation.pop("_id", None)
            
            # Kişi bilgisini al
            person_id = reservation.get("person_id") or reservation.get("coach_id") or reservation.get("referee_id")
            person = await db.users.find_one({"id": person_id}) if person_id else None
            person_name = person.get("full_name") if person else "Kişi"
            
            reservation_type = reservation.get("type", "person")
            type_label = {
                "coach": "Antrenör",
                "referee": "Hakem",
                "player": "Oyuncu",
                "facility": "Tesis"
            }.get(reservation_type, "Rezervasyon")
            
            reservation_date = reservation.get("date")
            is_past = True
            if reservation_date:
                try:
                    if isinstance(reservation_date, str):
                        is_past = datetime.strptime(reservation_date, "%Y-%m-%d") < datetime.utcnow()
                    else:
                        is_past = reservation_date < datetime.utcnow()
                except:
                    pass
            
            person_list.append({
                "id": reservation.get("id"),
                "type": f"{reservation_type}_reservation",
                "title": f"{type_label} - {person_name}",
                "date": reservation_date,
                "start_time": reservation.get("start_time"),
                "end_time": reservation.get("end_time"),
                "person_name": person_name,
                "person_type": reservation_type,
                "status": reservation.get("status"),
                "payment_status": reservation.get("payment_status"),
                "total_price": reservation.get("total_price") or reservation.get("price"),
                "created_at": reservation.get("created_at"),
                "is_past": is_past
            })
        
        # Tüm listeyi birleştir ve tarihe göre sırala
        all_activities = events_list + facility_list + person_list
        
        # created_at'e göre sırala (en yeni en üstte)
        all_activities.sort(key=lambda x: x.get("created_at") or datetime.min, reverse=True)
        
        return {
            "activities": all_activities,
            "events_count": len(events_list),
            "facility_reservations_count": len(facility_list),
            "person_reservations_count": len(person_list),
            "total": len(all_activities)
        }
        
    except Exception as e:
        logging.error(f"Error getting user activity history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize scheduler
scheduler = EventReminderScheduler(db, push_service)

@app.on_event("startup")
async def startup_event():
    """Start the background scheduler on app startup"""
    scheduler.start()
    
    # Start reminder scheduler
    from reminder_scheduler import start_reminder_scheduler
    start_reminder_scheduler(db)
    
    # Re-set database references for all modules (ensures they work after hot reload)
    set_event_management_db(db)
    set_league_db(db)

    logging.info("Application started with background scheduler")

@app.on_event("shutdown")
async def shutdown_db_client():
    """Stop scheduler and close DB on shutdown"""
    scheduler.stop()
    client.close()
    logging.info("Application shutdown complete")
