from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class UserType(str, Enum):
    PLAYER = "player"
    COACH = "coach"
    VENUE_OWNER = "venue_owner"
    PARENT = "parent"  # Veli
    ORGANIZER = "organizer"  # Organizatör
    REFEREE = "referee"  # Hakem
    STORE = "store"  # Malzeme Satıcısı / Mağaza
    CLUB = "club"  # Kulüp
    ADMIN = "admin"  # Yönetici
    ACCOUNTANT = "accountant"  # Muhasebe
    OPERATIONS = "operations"  # Operasyon Sorumlusu
    SUPER_ADMIN = "super_admin"  # Süper Yönetici (Mesaj Denetimi)
    ASSISTANT = "assistant"  # Yardımcı

class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"

class SkillLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    PROFESSIONAL = "professional"

class RefereeLevel(str, Enum):
    PROVINCIAL = "provincial"  # İl Hakemi
    NATIONAL = "national"  # Ulusal Hakem
    INTERNATIONAL = "international"  # Uluslararası Hakem

class EventType(str, Enum):
    MATCH = "match"
    TOURNAMENT = "tournament"
    LEAGUE = "league"
    CAMP = "camp"

class MatchFormat(str, Enum):
    GROUP = "group"
    ELIMINATION = "elimination"
    DOUBLE_ELIMINATION = "double_elimination"
    ROUND_ROBIN_SINGLE = "round_robin_single"
    ROUND_ROBIN_DOUBLE = "round_robin_double"
    SWISS = "swiss"
    GROUP_PLUS_ELIMINATION = "group_plus_elimination"

class PaymentProvider(str, Enum):
    STRIPE = "stripe"

class TeamPlayerRole(str, Enum):
    STARTER = "starter"  # Asıl kadro
    SUBSTITUTE = "substitute"  # Yedek
    CAPTAIN = "captain"  # Kaptan
    VICE_CAPTAIN = "vice_captain"  # Kaptan yardımcısı

    IYZICO = "iyzico"

class ReservationStatus(str, Enum):
    PENDING = "pending"  # Onay bekliyor
    APPROVED = "approved"  # Onaylandı
    REJECTED = "rejected"  # Reddedildi
    PAID = "paid"  # Ödendi
    COMPLETED = "completed"  # Tamamlandı
    CANCELLED = "cancelled"  # İptal edildi

class ReservationType(str, Enum):
    VENUE = "venue"
    COACH = "coach"
    REFEREE = "referee"
    VAKIFBANK = "vakifbank"

class NotificationType(str, Enum):
    MESSAGE_RECEIVED = "message_received"
    EVENT_REMINDER_1DAY = "event_reminder_1day"
    EVENT_REMINDER_1HOUR = "event_reminder_1hour"
    PARTICIPANT_JOINED = "participant_joined"
    EVENT_JOINED = "event_joined"  # Etkinliğe katıldığınızda
    RESERVATION_REQUEST = "reservation_request"  # Rezervasyon talebi
    RESERVATION_APPROVED = "reservation_approved"  # Rezervasyon onaylandı
    RESERVATION_REJECTED = "reservation_rejected"  # Rezervasyon reddedildi
    RATING_RECEIVED = "rating_received"  # Puan aldınız
    REVIEW_RECEIVED = "review_received"  # Yorum yapıldı
    MATCH_RESULT_ENTERED = "match_result_entered"  # Maç sonucu girildi
    SUPPORT_TICKET = "support_ticket"  # Destek talebi
    OFFER_RECEIVED = "offer_received"  # Yeni teklif alındı
    OFFER_ACCEPTED = "offer_accepted"  # Teklifiniz kabul edildi
    OFFER_REJECTED = "offer_rejected"  # Teklifiniz reddedildi
    OFFER_COUNTER = "offer_counter"  # Karşı teklif yapıldı
    OFFER_EXPIRING_SOON = "offer_expiring_soon"  # Teklif süresi bitiyor (1 saat kala)
    ADMIN_ACTION = "admin_action"  # Admin işlemi gerekiyor
    FACILITY_APPROVED = "facility_approved"  # Tesis onaylandı
    FACILITY_REJECTED = "facility_rejected"  # Tesis reddedildi

class NotificationRelatedType(str, Enum):
    EVENT = "event"
    RESERVATION = "reservation"
    MESSAGE = "message"
    PAYMENT = "payment"
    REVIEW = "review"
    SUPPORT_TICKET = "support_ticket"
    MARKETPLACE_OFFER = "marketplace_offer"
    MARKETPLACE_LISTING = "marketplace_listing"
    FACILITY = "facility"

class SupportTicketCategory(str, Enum):
    INFO_REQUEST = "info_request"  # Bilgi Talebi
    RESERVATION_CANCELLATION = "reservation_cancellation"  # Rezervasyon İptali
    TICKET_CANCELLATION = "ticket_cancellation"  # Bilet İptali
    EVENT_CANCELLATION = "event_cancellation"  # Etkinlik İptali
    COMPLAINT = "complaint"  # Şikayet
    OTHER = "other"  # Diğer

class SupportTicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

# Tournament Management Enums
class TournamentSystemType(str, Enum):
    SINGLE_ROUND_ROBIN = "single_round_robin"  # Tek tur round robin
    DOUBLE_ROUND_ROBIN = "double_round_robin"  # Çift tur round robin
    ROUND_ROBIN_SINGLE = "round_robin_single"  # Tek tur round robin (alias)
    ROUND_ROBIN_DOUBLE = "round_robin_double"  # Çift tur round robin (alias)
    GROUP_KNOCKOUT = "group_knockout"  # Grup + Eleme
    GROUP_STAGE = "group_stage"  # Grup + Eleme (alias)
    KNOCKOUT = "knockout"  # Eleme
    SINGLE_ELIMINATION = "single_elimination"  # Eleme (alias)
    DOUBLE_ELIMINATION = "double_elimination"  # Çift eleme
    SWISS = "swiss"  # İsviçre metodu

class MatchStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class ParticipantStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

    IN_PROGRESS = "in_progress"
    CLOSED = "closed"

# User Models
class UserFinancialInfo(BaseModel):
    tc_no: Optional[str] = None  # TC Kimlik No
    bank_account: Optional[str] = None
    iban: Optional[str] = None
    card_holder_name: Optional[str] = None
    bank_name: Optional[str] = None

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    user_type: UserType
    phone: Optional[str] = None
    city: str
    district: Optional[str] = None  # İlçe
    date_of_birth: Optional[str] = None  # YYYY-MM-DD format
    tckn: Optional[str] = None  # TC Kimlik Numarası (11 haneli)
    vk_no: Optional[str] = None  # Vergi Kimlik Numarası (10 haneli)
    is_corporate: Optional[bool] = False  # Kurumsal hesap mı? (Tüzel kişi)
    company_name: Optional[str] = None  # Şirket/Firma adı (kurumsal için)
    club_organization: Optional[str] = None  # Kulüp/Kuruluş adı
    profile_image: Optional[str] = None  # base64 or URL
    avatar: Optional[str] = None  # Avatar seçimi (avatar1, avatar2, etc.)
    languages: Optional[List[str]] = []  # ["Türkçe", "English", etc.]
    bio: Optional[str] = None  # Kısa tanıtım
    instagram: Optional[str] = None
    twitter_x: Optional[str] = None
    youtube: Optional[str] = None
    linkedin: Optional[str] = None
    website: Optional[str] = None
    documents: Optional[List[str]] = []  # Evrak URLs
    availability: Optional[Dict[str, List[str]]] = {}  # {"monday": ["09:00-12:00", "14:00-18:00"]}
    iban: Optional[str] = None  # IBAN numarası
    video_url: Optional[str] = None  # Video URL
    video_type: Optional[str] = None  # Video type (youtube, vimeo, file, etc.)
    match_fee: Optional[float] = None  # Maç ücreti
    hourly_rate: Optional[float] = None  # Saatlik ücret
    daily_rate: Optional[float] = None  # Günlük ücret
    monthly_membership: Optional[float] = None  # Aylık üyelik
    financial_info: Optional[UserFinancialInfo] = None
    
class PlayerProfile(BaseModel):
    age: Optional[int] = None
    gender: Optional[Gender] = None
    sports: Optional[List[str]] = []  # List of sports interested in
    skill_levels: Optional[Dict[str, SkillLevel]] = {}  # {"football": "intermediate", "basketball": "beginner"}
    current_team: Optional[str] = None  # Mevcut Takım/Kulüp
    height: Optional[int] = None  # Boy (cm)
    weight: Optional[int] = None  # Kilo (kg)
    equipment: Optional[str] = None  # Kullandığı Ekipman
    bio: Optional[str] = None
    rating: float = 0.0
    review_count: int = 0
    
class CoachProfile(BaseModel):
    sports: List[str]
    skill_levels: Dict[str, SkillLevel]
    specializations: List[str]  # Uzmanlık (Teknik, Kondisyon, Mental, Performans, Altyapı) - required
    license_number: str  # Lisans/Belge Numarası - required
    years_of_experience: Optional[int] = None  # Deneyim Süresi (yıl)
    age_groups: List[str]  # Yaş Grupları (Çocuklar, Gençler, Yetişkinler, Engelli) - min 1 required
    service_types: List[str]  # Hizmet Türü (Bireysel, Grup, Online, Takım) - min 1 required
    available_days: List[str]  # ["monday", "tuesday"]
    available_hours: List[str]  # ["09:00-12:00", "14:00-18:00"]
    cities: List[str]
    hourly_rate: float
    bio: Optional[str] = None
    certifications: Optional[List[str]] = None
    rating: float = 0.0
    review_count: int = 0
    
class VenueProfile(BaseModel):
    venue_name: Optional[str] = None  # Tesis/Kulüp/Kuruluş Adı
    sports: List[str] = []
    available_hours: Dict[str, List[str]] = {}  # {"monday": ["09:00-12:00"]}
    hourly_rate: Optional[float] = None
    facilities: List[str] = []  # Tesis özellikleri (kulüp üyeliği, lisans, aydınlatma, etc.)
    dimensions: Optional[str] = None
    capacity: Optional[int] = None  # Oyuncu kapasitesi
    spectator_capacity: Optional[int] = None  # Seyirci kapasitesi
    field_count: Optional[int] = None  # Oyun alanı sayısı
    founded_year: Optional[int] = None  # Kuruluş yılı
    address: Optional[str] = None
    google_maps_link: Optional[str] = None  # Google Maps linki
    location: Optional[Dict[str, float]] = None  # {"lat": 41.0082, "lng": 28.9784}
    website: Optional[str] = None  # Web sitesi
    logo: Optional[str] = None  # Kulüp logosu
    images: List[str] = []  # Fotoğraf/Video - base64 or URLs
    rating: float = 0.0
    review_count: int = 0

class RefereeSportProfile(BaseModel):
    """Hakem için her spor dalı bilgisi"""
    sport: str  # Spor türü
    level: RefereeLevel  # Hakemlik Kademesi (Yerel/Bölgesel/Ulusal/Uluslararası)
    license_number: str  # Lisans Numarası
    years_of_experience: Optional[int] = None  # Deneyim Süresi (yıl)
    match_count: Optional[int] = None  # Maç sayısı

class RefereeProfile(BaseModel):
    sports: List[RefereeSportProfile]  # Birden fazla spor dalı ekleyebilir
    bio: Optional[str] = None
    rating: float = 0.0
    review_count: int = 0

class UserCreate(UserBase):
    password: str
    player_profile: Optional[PlayerProfile] = None
    coach_profile: Optional[CoachProfile] = None
    venue_profile: Optional[VenueProfile] = None
    referee_profile: Optional[RefereeProfile] = None

class User(UserBase):
    id: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    player_profile: Optional[PlayerProfile] = None
    coach_profile: Optional[CoachProfile] = None
    venue_profile: Optional[VenueProfile] = None
    referee_profile: Optional[RefereeProfile] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Verification Models
class VerificationCode(BaseModel):
    id: str
    user_id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    code: str
    verification_type: str  # "email" or "sms"
    expires_at: datetime
    is_used: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

class VerifyRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    code: str

# Event Models
class TicketInfo(BaseModel):
    price: float
    total_slots: int
    available_slots: int
    currency: str = "TRY"
    prices: Optional[Dict[str, float]] = None  # Oyun türlerine göre fiyatlar {"single": 100, "double": 150, "team": 200}

class EventBase(BaseModel):
    title: str
    description: str
    event_type: EventType
    sport: str
    city: str
    venue_id: Optional[str] = None
    start_date: datetime
    end_date: datetime
    match_format: Optional[MatchFormat] = None
    tournament_system: Optional[str] = None  # Tournament system from create event page
    ticket_info: Optional[TicketInfo] = None
    images: List[str] = []  # base64
    max_participants: Optional[int] = None
    min_participants: Optional[int] = None
    skill_level: Optional[SkillLevel] = None
    gender_restriction: Optional[Gender] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    age_groups: Optional[List[str]] = None  # ['Open', 'Minik', 'Küçük', 'Genç', 'Büyük', 'Veteran', 'Engelli', 'Kadınlar']
    prize_money: Optional[float] = None  # Para ödülü (TL)
    venue_fee: Optional[float] = None  # Tesis ücreti (TL)
    scoring_config: Optional[Dict[str, int]] = None  # {"win": 3, "draw": 1, "loss": 0}
    
    # Match format details for sports (separate from tournament system)
    best_of_sets: Optional[int] = None  # Kaç set sisteminde oynanıyor (3, 5, 7)
    points_per_set: Optional[int] = None  # Her set kaç puana oynanıyor (11, 15, 21, 25)
    sets_to_win: Optional[int] = None  # Kazanmak için kaç set gerekli (2, 3, 4)
    
    # Yeni alanlar - Etkinlik oluşturma güncellemeleri
    genders: Optional[List[str]] = None  # ['Erkekler', 'Kadınlar']
    game_types: Optional[List[str]] = None  # ['open', 'tek', 'cift', 'karisik_cift', 'takim']
    selected_rule: Optional[Dict] = None  # Seçilen spor kuralları
    media: Optional[List[Dict]] = None  # Tanıtım medyası (fotoğraf/video)
    videos: Optional[List[str]] = None  # Video URL'leri
    event_duration: Optional[str] = None  # Etkinlik süresi (hourly, half_day, single_day, vb.)

class Event(EventBase):
    id: str
    organizer_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    participant_count: int = 0
    participants: List[str] = []  # User IDs who joined the event
    is_active: bool = True
    status: str = "pending"  # pending, active, rejected
    tournament_settings: Optional[Dict] = None  # Turnuva ayarları
    referees: Optional[List[Dict]] = None  # Etkinlik hakemleri

class EventCreate(EventBase):
    pass

# Venue Models
class VenueBase(BaseModel):
    name: str
    owner_id: str
    sports: List[str]
    city: str
    address: str
    location: Dict[str, float]
    available_hours: Dict[str, List[str]]  # {"monday": ["09:00-12:00", "14:00-18:00"]}
    hourly_rate: float
    facilities: List[str]
    dimensions: Optional[str] = None
    capacity: Optional[int] = None
    images: List[str] = []
    contact_info: Optional[Dict[str, str]] = None  # {"phone": "...", "email": "..."}

class Venue(VenueBase):
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    rating: float = 0.0
    review_count: int = 0
    is_active: bool = True
    approved: bool = False  # Yönetici onayı

class VenueCreate(VenueBase):
    pass

# Coach Listing Models
class CoachListingBase(BaseModel):
    user_id: str
    sports: List[str]
    cities: List[str]
    available_days: List[str]
    available_hours: List[str]
    hourly_rate: float
    bio: Optional[str] = None
    certifications: Optional[List[str]] = None

class CoachListing(CoachListingBase):
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    rating: float = 0.0
    review_count: int = 0
    is_active: bool = True

# Participation Models
class ParticipationBase(BaseModel):
    event_id: str
    user_id: str
    ticket_id: Optional[str] = None
    payment_status: str = "pending"  # pending, completed, failed
    payment_provider: Optional[PaymentProvider] = None

class Participation(ParticipationBase):
    id: str
    joined_at: datetime = Field(default_factory=datetime.utcnow)

# Ticket Models
class TicketBase(BaseModel):
    event_id: str
    user_id: str
    price: float
    currency: str = "TRY"
    payment_provider: PaymentProvider

class Ticket(TicketBase):
    id: str
    ticket_number: str
    purchased_at: datetime = Field(default_factory=datetime.utcnow)
    payment_status: str = "pending"
    payment_id: Optional[str] = None


# Reservation Models
class ReservationBase(BaseModel):
    reservation_type: ReservationType
    venue_id: Optional[str] = None
    coach_id: Optional[str] = None
    referee_id: Optional[str] = None
    user_id: str  # Who is making the reservation
    date: str  # YYYY-MM-DD
    time_slots: List[str]  # ["09:00", "10:00", "11:00"]
    total_hours: int
    hourly_rate: float
    total_price: float
    status: ReservationStatus = ReservationStatus.PENDING
    notes: Optional[str] = None
    
    # Venue location info (where the reservation takes place)
    venue_location_id: Optional[str] = None  # ID of existing venue
    venue_custom_name: Optional[str] = None  # Custom venue name if "Other"
    venue_custom_address: Optional[str] = None  # Custom venue address if "Other"

class Reservation(ReservationBase):
    id: str
    approved_time_slot: Optional[str] = None  # Owner approves only ONE slot
    payment_status: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ReservationCreate(BaseModel):
    reservation_type: ReservationType
    venue_id: Optional[str] = None
    date: str
    time_slots: List[str]
    notes: Optional[str] = None

# Review/Rating Models
class ReviewBase(BaseModel):
    target_id: str  # user_id, venue_id, or event_id
    target_type: str  # "user", "venue", "event"
    rating: int  # 1-5
    comment: Optional[str] = None

class Review(ReviewBase):
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

# Message Models
class MessageBase(BaseModel):
    receiver_id: str
    content: str
    is_read: bool = False

class Message(MessageBase):
    id: str
    sender_id: str
    sent_at: datetime = Field(default_factory=datetime.utcnow)


# Group Message Models
class GroupMessagePermission(str, Enum):
    EVERYONE = "everyone"  # Herkes mesaj gönderebilir
    ADMINS_ONLY = "admins_only"  # Sadece adminler mesaj gönderebilir

class GroupChatBase(BaseModel):
    name: str
    description: Optional[str] = None
    event_id: Optional[str] = None  # Linked event if this is an event group
    permission: str = "everyone"  # Changed from enum to string for flexibility
    
class GroupChat(GroupChatBase):
    id: str
    creator_id: str
    admin_ids: List[str] = []  # List of admin user IDs
    member_ids: List[str] = []  # List of all member user IDs
    invite_link: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
class GroupChatCreate(BaseModel):
    name: str
    description: Optional[str] = None
    event_id: Optional[str] = None
    member_ids: Optional[List[str]] = []

class GroupMessageBase(BaseModel):
    group_id: str
    content: str
    
class GroupMessage(GroupMessageBase):
    id: str
    sender_id: str
    sender_name: Optional[str] = None
    sent_at: Optional[datetime] = None
    read_by: Optional[List[str]] = []


# Payment Models for iyzico Integration
class PaymentStatus(str, Enum):
    PENDING = "pending"
    INIT_3DS = "init_3ds"
    SUCCESS = "success"
    FAILURE = "failure"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"

class PaymentBase(BaseModel):
    amount: float
    currency: str = "TRY"
    payment_method: Optional[str] = "credit_card"

class Payment(PaymentBase):
    id: str
    user_id: str
    related_type: str  # 'event', 'reservation'
    related_id: str  # event_id or reservation_id
    status: PaymentStatus = PaymentStatus.PENDING
    iyzico_payment_id: Optional[str] = None
    iyzico_conversation_id: Optional[str] = None
    iyzico_token: Optional[str] = None
    card_last_four: Optional[str] = None
    card_association: Optional[str] = None
    installment: int = 1
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class PaymentCreate(BaseModel):
    related_type: str  # 'event', 'reservation'
    related_id: str
    amount: float
    currency: str = "TRY"

    sender_name: Optional[str] = None
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    read_by: List[str] = []  # List of user IDs who read the message

# Ranking/Leaderboard Models
class RankingEntry(BaseModel):
    user_id: str
    sport: str
    city: Optional[str] = None
    age_group: Optional[str] = None
    gender: Optional[Gender] = None
    team_id: Optional[str] = None
    points: int = 0
    wins: int = 0
    losses: int = 0
    matches_played: int = 0

class Ranking(RankingEntry):
    id: str
    rank: int
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# Match/Score Models
class MatchScore(BaseModel):
    match_id: str
    event_id: str
    player1_id: str
    player2_id: str
    player1_score: int
    player2_score: int
    winner_id: str
    completed_at: datetime = Field(default_factory=datetime.utcnow)

# Match Result with Approval System
class MatchResultBase(BaseModel):
    event_id: str
    match_id: Optional[str] = None
    player1_id: str
    player2_id: str
    player1_score: int
    player2_score: int
    winner_id: str
    sport: str

class MatchResult(MatchResultBase):
    id: str
    submitted_by: str
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    admin_approved: bool = False
    admin_approved_by: Optional[str] = None
    admin_approved_at: Optional[datetime] = None
    status: str = "pending"  # pending, approved, disputed, admin_approved
    dispute_reason: Optional[str] = None

class MatchResultCreate(MatchResultBase):
    pass

class MatchResultApproval(BaseModel):
    match_result_id: str
    approved: bool
    dispute_reason: Optional[str] = None

# Player Statistics (auto-updated from match results)
class PlayerStats(BaseModel):
    user_id: str
    sport: str
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    points: int = 0
    ranking_score: float = 0.0
    city: Optional[str] = None
    age_group: Optional[str] = None
    gender: Optional[Gender] = None

# Platform Commission Models
class CommissionRate(BaseModel):
    rate: float = 0.10  # 10% default
    min_amount: float = 0.0

class PlatformCommission(BaseModel):
    id: str
    transaction_id: str
    user_id: str
    event_id: Optional[str] = None
    payment_amount: float
    commission_rate: float
    commission_amount: float
    platform_earnings: float
    user_earnings: float
    currency: str = "TRY"
    status: str  # pending, collected, paid_out
    created_at: datetime = Field(default_factory=datetime.utcnow)
    collected_at: Optional[datetime] = None

# Admin Action Logs
class AdminAction(BaseModel):
    id: str
    admin_id: str
    action_type: str  # approve_match, review_message, modify_payment, ban_user
    target_id: str
    target_type: str  # match_result, message, transaction, user
    details: dict
    created_at: datetime = Field(default_factory=datetime.utcnow)

# Search Request Models
class SearchRequest(BaseModel):
    query: Optional[str] = None
    sport: Optional[str] = None
    city: Optional[str] = None
    event_type: Optional[EventType] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    skill_level: Optional[SkillLevel] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None

# Notification Models
class NotificationBase(BaseModel):
    user_id: str
    type: NotificationType
    title: str
    message: str
    related_id: Optional[str] = None
    related_type: Optional[NotificationRelatedType] = None
    read: bool = False

class Notification(NotificationBase):
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class NotificationCreate(BaseModel):
    user_id: str
    type: NotificationType
    title: str
    message: str
    related_id: Optional[str] = None
    related_type: Optional[NotificationRelatedType] = None

# Push Token Model
class PushTokenBase(BaseModel):
    user_id: str
    expo_push_token: str
    device_type: Optional[str] = None

class PushToken(PushTokenBase):
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# Support Ticket Models
class SupportTicketMessage(BaseModel):
    id: str
    sender_id: str
    sender_name: str
    is_admin: bool
    message: str
    created_at: datetime

class SupportTicketBase(BaseModel):
    category: SupportTicketCategory
    subject: str
    description: str
    related_type: Optional[str] = None  # 'event', 'reservation', 'ticket'
    related_id: Optional[str] = None

class SupportTicket(SupportTicketBase):
    id: str
    user_id: str
    user_name: Optional[str] = None  # Kullanıcı adı (API tarafından eklenir)
    status: SupportTicketStatus = SupportTicketStatus.OPEN
    admin_response: Optional[str] = None  # Deprecated - use messages
    messages: List[SupportTicketMessage] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class SupportTicketCreate(SupportTicketBase):
    pass

class SupportTicketUpdate(BaseModel):
    status: Optional[SupportTicketStatus] = None
    admin_response: Optional[str] = None

class SupportTicketMessageCreate(BaseModel):
    message: str


# Review/Rating Models
class ReviewType(str, Enum):
    EVENT = "event"  # Etkinlik için
    VENUE = "venue"  # Tesis için
    COACH = "coach"  # Antrenör için
    REFEREE = "referee"  # Hakem için
    PLAYER = "player"  # Oyuncu için

class ReviewBase(BaseModel):
    target_user_id: str  # Puanlanan kullanıcı
    target_type: ReviewType  # Hangi rolde puanlanıyor

# Tournament Management Models
class ScoringSystemConfig(BaseModel):
    win_points: int = 3
    draw_points: int = 1
    loss_points: int = 0
    forfeit_loss_points: int = 0
    first_place_points: Optional[int] = None
    second_place_points: Optional[int] = None
    third_place_points: Optional[int] = None
    fourth_place_points: Optional[int] = None
    quarterfinalist_points: Optional[int] = None

class RefereeType(str, Enum):
    official = "official"  # Resmi hakem
    player = "player"  # Oyuncu hakem
    none = "none"  # Hakem yok

class TournamentConfig(BaseModel):
    event_id: str
    system_type: TournamentSystemType
    venue_id: Optional[str] = None
    field_count: int = 1
    group_size: Optional[int] = None  # Grup başına oyuncu sayısı
    match_duration_minutes: int = 90
    scoring_config: ScoringSystemConfig
    bye_participants: List[str] = []  # Bye alan katılımcılar
    group_winners_count: Optional[int] = None  # Her gruptan kaç kişi
    
    # Turnuva tarihleri ve saatleri
    tournament_start_date: Optional[str] = None  # YYYY-MM-DD
    tournament_end_date: Optional[str] = None  # YYYY-MM-DD
    daily_start_time: Optional[str] = None  # HH:MM (örn: "09:00")
    daily_break_time: Optional[str] = None  # HH:MM (örn: "12:00")
    daily_end_time: Optional[str] = None  # HH:MM (örn: "18:00")
    
    # Hakem ataması
    referee_type: RefereeType = RefereeType.none

class TournamentManagement(BaseModel):
    id: str
    event_id: str
    organizer_id: str
    config: TournamentConfig
    status: str = "draft"  # draft, active, completed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class TournamentCreate(BaseModel):
    event_id: str
    config: TournamentConfig

    related_id: Optional[str] = None  # İlgili etkinlik/rezervasyon ID
    related_type: Optional[str] = None  # 'event', 'reservation'
    rating: int = Field(ge=1, le=5)  # 1-5 yıldız
    comment: Optional[str] = None
    skills_rating: Optional[int] = Field(default=None, ge=1, le=5)  # Yetenek puanı
    communication_rating: Optional[int] = Field(default=None, ge=1, le=5)  # İletişim
    punctuality_rating: Optional[int] = Field(default=None, ge=1, le=5)  # Dakiklik

class Review(ReviewBase):
    pass

# Match Models
class MatchStatus(str, Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"

class MatchBase(BaseModel):
    tournament_id: str
    round: int  # Tur numarası (1, 2, 3...)
    match_number: int  # Maç numarası
    participant1_id: Optional[str] = None
    participant2_id: Optional[str] = None
    scheduled_date: Optional[str] = None  # YYYY-MM-DD
    scheduled_time: Optional[str] = None  # HH:MM
    field_number: Optional[int] = None
    referee_id: Optional[str] = None
    status: MatchStatus = MatchStatus.scheduled
    score1: Optional[int] = None
    score2: Optional[int] = None
    winner_id: Optional[str] = None
    notes: Optional[str] = None
    group_name: Optional[str] = None  # Grup sistemleri için (örn: "Grup A")
    bracket_position: Optional[str] = None  # Eleme sistemleri için (örn: "upper", "lower")

class MatchCreate(MatchBase):
    pass

class Match(MatchBase):
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ReviewCreate(ReviewBase):
    pass

class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    comment: Optional[str] = None
    skills_rating: Optional[int] = Field(default=None, ge=1, le=5)
    communication_rating: Optional[int] = Field(default=None, ge=1, le=5)
    punctuality_rating: Optional[int] = Field(default=None, ge=1, le=5)


# ==================== ADVANCED TOURNAMENT MANAGEMENT MODELS ====================

# Sport Configuration for different sports
class SportConfig(BaseModel):
    sport_type: str  # "football", "basketball", "tennis", "table_tennis", etc.
    scoring_system: Dict[str, Any]  # Flexible scoring: {"win": 3, "draw": 1, "loss": 0}
    match_duration: Optional[int] = None  # Minutes
    sets_to_win: Optional[int] = None  # For tennis, volleyball
    points_per_set: Optional[int] = None
    overtime_rules: Optional[Dict[str, Any]] = None
    field_type: str = "court"  # "court", "field", "table", "pitch"
    referee_required: bool = True
    
class VenueField(BaseModel):
    id: str
    name: str  # "Kort 1", "Masa 2", "Saha A"
    field_type: str  # "court", "table", "field"
    is_available: bool = True
    notes: Optional[str] = None

class Referee(BaseModel):
    id: str
    user_id: str
    full_name: str
    email: str
    phone_number: Optional[str] = None
    certification_level: Optional[str] = None
    sports: List[str] = []
    availability: List[Dict[str, Any]] = []  # [{"date": "2024-01-01", "time_slots": ["09:00-12:00"]}]
    assigned_matches: List[str] = []  # Match IDs
    created_at: datetime = Field(default_factory=datetime.utcnow)

class RefereeCreate(BaseModel):
    user_id: str
    sports: List[str] = []
    certification_level: Optional[str] = None
    availability: List[Dict[str, Any]] = []

# Participant removal request
class ParticipantRemovalRequest(BaseModel):
    id: str
    event_id: str
    tournament_id: Optional[str] = None
    participant_id: str
    requested_by: str  # Organizer ID
    reason: str
    status: str = "pending"  # pending, approved, rejected
    admin_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None  # Admin ID

class ParticipantRemovalRequestCreate(BaseModel):
    event_id: str
    tournament_id: Optional[str] = None
    participant_id: str
    reason: str

class ParticipantRemovalRequestUpdate(BaseModel):
    status: str  # "approved" or "rejected"
    admin_notes: Optional[str] = None

# Tournament Participant with detailed info
class TournamentParticipant(BaseModel):
    id: str
    tournament_id: str
    user_id: str
    full_name: str
    email: str
    phone_number: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    skill_level: Optional[str] = None
    seed: Optional[int] = None  # Seeding for bracket
    group_name: Optional[str] = None  # For group stages
    is_bye: bool = False  # Bye player
    registration_date: datetime = Field(default_factory=datetime.utcnow)
    payment_status: str = "pending"  # pending, paid, refunded
    notes: Optional[str] = None

# Draw/Seeding configuration
class DrawConfig(BaseModel):
    method: str  # "random", "seeded", "manual"
    seed_based_on: Optional[str] = None  # "ranking", "previous_results", "manual"
    protect_seeded_players: bool = True  # Seeded players avoid each other early
    
# Bracket node for elimination tournaments
class BracketNode(BaseModel):
    id: str
    tournament_id: str
    round: int
    match_number: int
    position: str  # "upper", "lower", "final", "third_place"
    participant1_id: Optional[str] = None
    participant2_id: Optional[str] = None
    winner_id: Optional[str] = None
    next_match_id: Optional[str] = None  # Winner goes to this match
    loser_next_match_id: Optional[str] = None  # For double elimination
    match_id: Optional[str] = None  # Reference to actual Match
    is_bye: bool = False

# Standing for league/round-robin
class Standing(BaseModel):
    id: str
    tournament_id: str
    group_name: Optional[str] = None
    participant_id: str
    participant_name: str
    matches_played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    points: int = 0
    goals_for: int = 0  # Or sets won, games won, etc.
    goals_against: int = 0
    goal_difference: int = 0
    rank: int = 0
    form: List[str] = []  # Last 5 results: ["W", "L", "D", "W", "W"]
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# Extended Match model with more details
class MatchDetail(BaseModel):
    id: str
    tournament_id: str
    round: int
    match_number: int
    match_type: str  # "group", "elimination", "final", "third_place"
    participant1_id: Optional[str] = None
    participant1_name: Optional[str] = None
    participant2_id: Optional[str] = None
    participant2_name: Optional[str] = None
    scheduled_datetime: Optional[datetime] = None
    field_id: Optional[str] = None
    field_name: Optional[str] = None
    referee_id: Optional[str] = None
    referee_name: Optional[str] = None
    status: MatchStatus = MatchStatus.scheduled
    
    # Detailed scoring
    score_participant1: Optional[int] = None
    score_participant2: Optional[int] = None
    sets_scores: Optional[List[Dict[str, int]]] = None  # [{"p1": 6, "p2": 4}, {...}]
    
    winner_id: Optional[str] = None
    is_walkover: bool = False
    notes: Optional[str] = None
    group_name: Optional[str] = None
    bracket_position: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

class MatchScoreUpdate(BaseModel):
    score_participant1: int
    score_participant2: int
    sets_scores: Optional[List[Dict[str, int]]] = None
    winner_id: str
    is_walkover: bool = False
    notes: Optional[str] = None

class ScoreProposal(BaseModel):
    """Score proposal that needs confirmation"""
    score_participant1: int
    score_participant2: int
    winner_id: str
    proposed_by: str  # user_id who proposed
    proposed_at: datetime = Field(default_factory=datetime.utcnow)
    confirmed_by: Optional[List[str]] = []  # List of user_ids who confirmed
    notes: Optional[str] = None

class ScoreConfirmation(BaseModel):
    """Confirmation response for a score proposal"""
    confirmed: bool
    notes: Optional[str] = None

# Schedule slot
class ScheduleSlot(BaseModel):
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    duration: int  # Minutes
    field_id: str
    is_available: bool = True
    match_id: Optional[str] = None

# Tournament Schedule
class TournamentSchedule(BaseModel):
    tournament_id: str
    slots: List[ScheduleSlot]
    conflicts: List[Dict[str, Any]] = []  # Detected conflicts
    
# Age group configuration
class AgeGroup(BaseModel):
    id: str
    name: str  # "U12", "U15", "U18", "Senior", etc.
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    participants: List[str] = []  # User IDs in this age group

# Extended Tournament Configuration
class ExtendedTournamentConfig(TournamentConfig):
    sport_config: Optional[SportConfig] = None
    age_restrictions: Optional[Dict[str, Any]] = None  # {"min": 18, "max": 35}
    gender_restrictions: Optional[str] = None  # "male", "female", "mixed", "any"
    max_participants: Optional[int] = None
    min_participants: Optional[int] = None
    registration_fee: Optional[float] = None
    prize_distribution: Optional[Dict[str, Any]] = None  # {"1st": 1000, "2nd": 500}
    venue_fields: List[VenueField] = []
    available_time_slots: List[Dict[str, Any]] = []  # [{"date": "2024-01-01", "slots": ["09:00", "10:00"]}]
    
    # Age group management
    enable_age_groups: bool = False
    age_groups: List[AgeGroup] = []  # Define age groups for automatic separation
    
# Full Tournament with all details
class TournamentFull(BaseModel):
    id: str
    event_id: str
    event_name: str
    organizer_id: str
    organizer_name: str
    config: ExtendedTournamentConfig
    status: str  # "draft", "registration_open", "draw_completed", "in_progress", "completed"
    visibility: str = "public"  # "public", "private", "hidden"
    participants: List[TournamentParticipant] = []
    matches: List[MatchDetail] = []
    standings: List[Standing] = []
    bracket: List[BracketNode] = []
    referees: List[Referee] = []
    schedule: Optional[TournamentSchedule] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    draw_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None



# ==================== TEAM MODELS ====================

class TeamPlayer(BaseModel):
    user_id: str
    user_name: str
    role: TeamPlayerRole  # starter, substitute, captain, vice_captain
    position: Optional[str] = None  # Spora göre pozisyon (kaleci, forvet, vb.)
    jersey_number: Optional[int] = None  # Forma numarası
    joined_at: datetime = Field(default_factory=datetime.utcnow)

class Team(BaseModel):
    id: str
    name: str
    sport: str  # Futbol, Basketbol, vb.
    logo: Optional[str] = None  # Base64 or URL
    description: Optional[str] = None
    creator_id: str  # Takımı oluşturan kullanıcı
    creator_name: str
    organization_id: Optional[str] = None  # Kulüp/Organizasyon ID
    
    # Oyuncular
    players: List[TeamPlayer] = []
    max_players: int = 20  # Maksimum oyuncu sayısı (spora göre değişir)
    
    # Takım istatistikleri (opsiyonel, gelecekte kullanılabilir)
    wins: int = 0
    losses: int = 0
    draws: int = 0
    
    # Grup sohbeti
    group_chat_id: Optional[str] = None
    
    # Görünürlük
    is_public: bool = True  # Herkese açık mı?
    
    # Tarihler
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class TeamCreateRequest(BaseModel):
    name: str
    sport: str
    logo: Optional[str] = None
    description: Optional[str] = None
    players: List[Dict[str, Any]]  # [{"user_id": "...", "role": "starter", "position": "..."}]
    create_group_chat: bool = True
    max_players: Optional[int] = 20

class TeamUpdateRequest(BaseModel):
    name: Optional[str] = None
    logo: Optional[str] = None
    description: Optional[str] = None
    players: Optional[List[Dict[str, Any]]] = None
    is_public: Optional[bool] = None


# ============================================
# MARKETPLACE MODELS
# ============================================

class ListingType(str, Enum):
    PRODUCT = "product"  # Ürün (satılık)
    RENTAL = "rental"    # Kiralık
    SERVICE = "service"  # Hizmet
    DEMAND = "demand"    # Talep ilanı

class ProductCondition(str, Enum):
    NEW = "new"  # Sıfır
    USED = "used"  # İkinci el
    RENTAL = "rental"  # Kiralık

class ProductConditionScale(str, Enum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"

class DeliveryMethod(str, Enum):
    CARGO = "cargo"  # Kargo
    HAND = "hand"  # Elden teslim
    VENUE = "venue"  # Tesis teslimi

class ListingStatus(str, Enum):
    ACTIVE = "active"
    SOLD = "sold"
    RENTED = "rented"
    RESERVED = "reserved"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class OfferStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTER_OFFERED = "counter_offered"
    EXPIRED = "expired"

class ServiceType(str, Enum):
    TRAINING = "training"  # Antrenörlük
    VENUE_RENTAL = "venue_rental"  # Tesis kiralama
    REFEREE = "referee"  # Hakemlik
    CAMP = "camp"  # Kamp
    TOURNAMENT = "tournament"  # Turnuva organizasyonu
    ANALYSIS = "analysis"  # Analiz
    NUTRITION = "nutrition"  # Beslenme
    CONDITIONING = "conditioning"  # Kondisyon

class MarketplaceCategory(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    sport: Optional[str] = None
    icon: Optional[str] = None

class ListingBase(BaseModel):
    title: str
    description: str
    listing_type: ListingType
    category_id: str
    price: float
    currency: str = "TRY"
    location: str
    images: List[str] = []
    tags: List[str] = []
    
    # Product specific
    condition: Optional[ProductCondition] = None
    condition_scale: Optional[ProductConditionScale] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    warranty: Optional[bool] = False
    warranty_months: Optional[int] = 0
    delivery_methods: List[DeliveryMethod] = []
    return_policy: Optional[str] = None
    stock_quantity: Optional[int] = 1
    
    # Service specific
    service_type: Optional[ServiceType] = None
    hourly_rate: Optional[float] = None
    session_duration: Optional[int] = None  # minutes
    availability_calendar: Optional[Dict[str, Any]] = None
    video_url: Optional[str] = None
    
    # Rental specific
    rental_duration_options: Optional[List[str]] = []  # ["hour", "day", "week", "month"]
    deposit_amount: Optional[float] = 0
    
    # Demand specific
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    needed_by: Optional[datetime] = None
    quantity_needed: Optional[int] = 1
    
    # Common
    is_negotiable: bool = True
    allow_offers: bool = True
    is_featured: bool = False
    views_count: int = 0

class ListingCreate(ListingBase):
    pass

class Listing(ListingBase):
    id: str
    seller_id: str
    seller_name: str
    seller_type: UserType
    seller_rating: Optional[float] = 0.0
    status: ListingStatus = ListingStatus.ACTIVE
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    offer_count: int = 0
    favorite_count: int = 0

class OfferBase(BaseModel):
    listing_id: str
    amount: float
    message: Optional[str] = None
    
    # For service/demand offers
    delivery_time: Optional[int] = None  # days
    additional_details: Optional[str] = None
    attachments: Optional[List[str]] = []

class OfferCreate(OfferBase):
    pass

class Offer(OfferBase):
    id: str
    buyer_id: str
    buyer_name: str
    seller_id: str
    status: OfferStatus = OfferStatus.PENDING
    counter_amount: Optional[float] = None
    counter_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    # Price lock fields (when accepted)
    price_locked_until: Optional[datetime] = None  # 12 saatlik süre
    price_locked_for_buyer: Optional[str] = None  # Kilit alıcı ID'si
    reminder_sent: bool = False  # 1 saat öncesi hatırlatma gönderildi mi

class RentalBooking(BaseModel):
    id: str
    listing_id: str
    renter_id: str
    owner_id: str
    start_date: datetime
    end_date: datetime
    total_price: float
    deposit_amount: float
    deposit_paid: bool = False
    deposit_refunded: bool = False
    payment_status: str = "pending"  # pending, paid, refunded
    status: str = "pending"  # pending, confirmed, active, completed, cancelled
    qr_code: Optional[str] = None
    pickup_verified: bool = False
    return_verified: bool = False
    condition_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class Transaction(BaseModel):
    id: str
    listing_id: str
    offer_id: Optional[str] = None
    buyer_id: str
    seller_id: str
    amount: float
    payment_method: str  # "card", "wallet", "transfer"
    payment_provider: str = "iyzico"
    payment_id: Optional[str] = None
    status: str = "pending"  # pending, completed, failed, refunded
    commission_rate: float = 0.05
    commission_amount: float
    seller_amount: float
    created_at: datetime
    completed_at: Optional[datetime] = None

class Review(BaseModel):
    id: str
    listing_id: str
    transaction_id: str
    reviewer_id: str
    reviewer_name: str
    reviewee_id: str
    rating: int  # 1-5
    comment: Optional[str] = None
    images: List[str] = []
    created_at: datetime

class MarketplaceStats(BaseModel):
    user_id: str
    total_listings: int = 0
    active_listings: int = 0
    sold_items: int = 0
    total_revenue: float = 0
    total_offers_received: int = 0
    total_offers_sent: int = 0
    average_rating: float = 0.0
    total_reviews: int = 0
    views_count: int = 0
    favorite_count: int = 0
    response_time_avg: Optional[int] = None  # minutes


# ==================== SPORT SETTINGS MODEL ====================
class SportSettings(BaseModel):
    """
    Admin tarafından oluşturulan spor dalı ayarları şablonu.
    Kullanıcılar tesis oluştururken bu şablonları kullanabilir.
    """
    id: Optional[str] = None
    sport_name: str  # Futbol, Basketbol, Voleybol, vb.
    
    # Saha ölçüleri
    field_length: Optional[float] = None  # metre
    field_width: Optional[float] = None  # metre
    field_height: Optional[float] = None  # metre (kapalı sporlar için)
    
    # Özel alanlar
    divided_area_count: Optional[int] = None  # Bölünmüş alan sayısı (halı saha gibi)
    table_count: Optional[int] = None  # Masa sayısı (masa tenisi, bilardo)
    
    # Maç bilgileri
    match_duration: Optional[int] = None  # dakika
    set_count: Optional[int] = None  # Set sayısı (voleybol, tenis için)
    referee_count: Optional[int] = None  # Hakem sayısı
    
    # Cezalar
    predefined_penalties: List[str] = []  # ["Sarı Kart", "Kırmızı Kart", "Faul"]
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ==================== FACILITY MODEL ====================
class WorkingHours(BaseModel):
    """Çalışma saatleri"""
    day: str  # "monday", "tuesday", vb.
    is_open: bool = True
    opening_time: Optional[str] = None  # "09:00"
    closing_time: Optional[str] = None  # "22:00"


class FacilitySport(BaseModel):
    """Tesiste mevcut olan bir spor dalı"""
    sport_name: str  # Futbol, Basketbol, vb.
    area_count: int = 1  # Bu spor için kaç alan var
    
    # SportSettings'ten alınabilecek bilgiler (kullanıcı özelleştirebilir)
    field_length: Optional[float] = None
    field_width: Optional[float] = None
    field_height: Optional[float] = None
    divided_area_count: Optional[int] = None
    table_count: Optional[int] = None
    match_duration: Optional[int] = None
    set_count: Optional[int] = None
    referee_count: Optional[int] = None
    custom_penalties: List[str] = []  # Kullanıcı ekleyebilir


class DayType(str, Enum):
    """Gün tipi"""
    WEEKDAY = "weekday"  # Hafta içi
    WEEKEND = "weekend"  # Hafta sonu
    SPECIAL = "special"  # Özel gün


class Season(str, Enum):
    """Mevsim"""
    SPRING = "spring"  # İlkbahar (Mart-Mayıs)
    SUMMER = "summer"  # Yaz (Haziran-Ağustos)
    FALL = "fall"  # Sonbahar (Eylül-Kasım)
    WINTER = "winter"  # Kış (Aralık-Şubat)


class CustomerType(str, Enum):
    """Müşteri tipi"""
    GENERAL = "general"  # Genel kullanıcı
    STUDENT = "student"  # Öğrenci
    TRAINER = "trainer"  # Antrenör
    RETIRED = "retired"  # Emekli
    FEMALE = "female"  # Kadın


class PricingRule(BaseModel):
    """
    Dinamik fiyatlandırma kuralı.
    Her kural bir spor, saha, zaman dilimi, sezon kombinasyonu için fiyat belirler.
    """
    rule_id: Optional[str] = None  # Otomatik oluşturulur
    
    # Hangi spor ve saha için?
    sport_name: str  # Futbol, Basketbol, vb.
    field_number: int  # Saha numarası (1, 2, 3, vb.)
    
    # Zaman bilgileri
    day_type: DayType  # weekday, weekend, special
    time_slot: str  # "08:00-12:00", "12:00-17:00", vb.
    season: Season  # spring, summer, fall, winter
    
    # Fiyat bilgileri
    base_price: float  # Temel fiyat (TL)
    seasonal_multiplier: float = 1.0  # Sezon çarpanı (1.0 = değişiklik yok, 1.2 = %20 artış)
    
    # Kullanıcı tipi indirimleri (%)
    customer_discounts: Dict[str, float] = {
        "general": 0,
        "student": 15,
        "trainer": 20,
        "retired": 10,
        "female": 10
    }
    
    is_active: bool = True  # Kural aktif mi?
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SpecialDayDiscount(BaseModel):
    """Özel gün indirimi"""
    date: str  # "2025-04-23" formatında
    discount_percentage: float  # İndirim yüzdesi
    description: Optional[str] = None  # "Çocuk Bayramı İndirimi"
    is_active: bool = True


class FacilityPricing(BaseModel):
    """Tesis ücretlendirme (Basit mod için - geriye dönük uyumluluk)"""
    is_free: bool = False  # Tesis ücretsiz mi?
    hourly_rate: Optional[float] = None  # Saatlik ücret
    match_rate: Optional[float] = None  # Maç başı ücret
    daily_rate: Optional[float] = None  # Günlük ücret
    monthly_rate: Optional[float] = None  # Aylık abonelik ücreti
    
    # Antrenör indirimi (eski sistem - geriye dönük uyumluluk)
    trainer_discount_10: bool = False  # %10 indirim
    trainer_discount_20: bool = False  # %20 indirim
    trainer_discount_30: bool = False  # %30 indirim
    
    # Yeni dinamik fiyatlandırma
    use_dynamic_pricing: bool = False  # True ise pricing_rules kullanılır
    pricing_rules: List[PricingRule] = []  # Dinamik fiyatlandırma kuralları
    special_day_discounts: List[SpecialDayDiscount] = []  # Özel gün indirimleri


class FacilityAmenities(BaseModel):
    """Tesis özellikleri"""
    parking: bool = False  # Otopark
    shower: bool = False  # Duş
    cafe: bool = False  # Cafe
    sauna: bool = False  # Sauna
    locker: bool = False  # Dolap
    toilet: bool = False  # Tuvalet
    reception: bool = False  # Resepsiyon
    card_access: bool = False  # Kartlı geçiş
    live_broadcast: bool = False  # Canlı yayın
    spectator_stand: bool = False  # Seyirci tribünü
    video_recording: bool = False  # Video kayıt


class Facility(BaseModel):
    """
    Kullanıcı tarafından oluşturulan tesis bilgileri.
    Bir kullanıcı birden fazla tesis yönetebilir.
    """
    id: Optional[str] = None
    owner_id: Optional[str] = None  # Tesis sahibi kullanıcı ID (endpoint'te set edilir)
    
    # Genel bilgiler
    name: str  # Tesis adı
    description: Optional[str] = None  # Açıklama
    
    # Sporlar ve alanlar
    sports: List[FacilitySport] = []  # Bu tesiste mevcut sporlar
    
    # Özellikler
    amenities: FacilityAmenities = Field(default_factory=FacilityAmenities)
    
    # Çalışma saatleri
    working_hours: List[WorkingHours] = []
    
    # İletişim bilgileri
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    
    # Adres
    address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    # Ücretlendirme
    pricing: FacilityPricing = Field(default_factory=FacilityPricing)
    
    # Yayınlama
    is_published: bool = False  # Kullanıcılara gösterilsin mi?
    
    # Üyelik Sistemi
    allow_membership: bool = False  # Kulüp üyeliği kabul edilsin mi?
    daily_membership_fee: Optional[float] = None  # Günlük üyelik ücreti
    monthly_membership_fee: Optional[float] = None  # Aylık üyelik ücreti
    yearly_membership_fee: Optional[float] = None  # Yıllık üyelik ücreti
    
    # Onay Sistemi
    status: str = "pending"  # "pending", "approved", "rejected"
    rejection_reason: Optional[str] = None  # Red sebebi
    approved_by: Optional[str] = None  # Onaylayan admin ID
    approved_at: Optional[datetime] = None  # Onay tarihi
    
    # Görseller
    images: List[str] = []  # Tesis fotoğrafları (base64)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    views_count: int = 0
    rating: float = 0.0
    review_count: int = 0




# ==================== FACILITY FIELD/COURT MANAGEMENT ====================

class FacilityField(BaseModel):
    """
    Tesis içindeki saha/alan/masa yönetimi
    Örnek: Saha 1, Kort 2, Masa 3
    """
    id: Optional[str] = None
    facility_id: str  # Hangi tesise ait
    
    # Alan bilgileri
    field_name: str  # "Saha 1", "Kort 2", "Masa 3"
    sport_type: str  # "Futbol", "Basketbol", "Tenis", vb.
    field_type: str  # "grass", "artificial_turf", "hardcourt", vb.
    
    # Kullanılabilirlik
    is_occupied: bool = False  # Şu anda dolu mu?
    is_available_for_booking: bool = True  # Online rezerve edilebilir mi?
    
    # Fiyatlandırma (manuel)
    hourly_rate: Optional[float] = None  # Saatlik ücret (TL)
    discount_percentage: float = 0.0  # İndirim yüzdesi
    
    # Aktif rezervasyon bilgisi (eski sistem)
    current_reservation: Optional[dict] = None  # {user_id, user_name, time_slot, date}
    
    # Aktif seans bilgisi (yeni sistem)
    active_session: Optional[dict] = None  # {player_names, start_time, end_time, duration_minutes, started_at, price, payment_method, is_paid}
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True


# ==================== SPORT CONFIGURATION SYSTEM ====================

class FieldType(str, Enum):
    """Saha/Alan Tipi"""
    GRASS = "grass"  # Çim
    ARTIFICIAL_TURF = "artificial_turf"  # Suni Çim
    HARDCOURT = "hardcourt"  # Sert Zemin
    CLAY = "clay"  # Kil Kort
    SAND = "sand"  # Kum
    WOOD = "wood"  # Parke
    INDOOR = "indoor"  # Kapalı Salon
    OUTDOOR = "outdoor"  # Açık Alan


class ScoringSystem(str, Enum):
    """Puanlama Sistemi"""
    POINTS = "points"  # Puan (Futbol, Basketbol)
    SETS_GAMES = "sets_games"  # Set-Oyun (Tenis)
    SETS_POINTS = "sets_points"  # Set-Puan (Voleybol)
    GOALS = "goals"  # Gol (Futbol, Hentbol)
    TIME_BASED = "time_based"  # Süre Bazlı (Atletizm)


class CompetitionFormat(str, Enum):
    """Yarışma Formatları"""
    KNOCKOUT = "knockout"  # Eleme
    GROUP_PLUS_KNOCKOUT = "group_plus_knockout"  # Grup+Eleme
    SINGLE_ROUND_ROBIN = "single_round_robin"  # Tek Tur Round Robin
    DOUBLE_ROUND_ROBIN = "double_round_robin"  # Çift Tur Round Robin
    SWISS_SYSTEM = "swiss_system"  # İsviçre Metodu
    LEAGUE_SYSTEM = "league_system"  # Lig Sistemi
    PLAYOFF = "playoff"  # Playoff
    CUP_SINGLE_ELIMINATION = "cup_single_elimination"  # Kupa Sistemi


class FieldDimensions(BaseModel):
    """Saha/Alan Boyutları"""
    length_min: Optional[float] = None  # metre
    length_max: Optional[float] = None
    width_min: Optional[float] = None
    width_max: Optional[float] = None
    height_min: Optional[float] = None  # Tavan yüksekliği (kapalı alanlar için)
    height_max: Optional[float] = None
    court_count: Optional[int] = 1  # Kort/Saha sayısı (Tenis vb.)


class GameDuration(BaseModel):
    """Oyun Süresi Bilgileri"""
    periods: int = 2  # Periyot/Devre sayısı
    period_duration_minutes: int = 45  # Her periyot süresi
    break_duration_minutes: int = 15  # Ara süresi
    overtime_minutes: Optional[int] = None  # Uzatma süresi
    timeout_count: Optional[int] = None  # Mola sayısı
    timeout_duration_seconds: Optional[int] = None  # Mola süresi


class PlayerCount(BaseModel):
    """Oyuncu Sayıları"""
    min_per_team: int
    max_per_team: int
    on_field_per_team: int  # Sahada oynayan oyuncu sayısı
    substitutes_per_team: Optional[int] = None  # Yedek oyuncu sayısı
    min_to_start: Optional[int] = None  # Maç başlatmak için minimum oyuncu


class SportRule(BaseModel):
    """Spor Kuralı"""
    rule_title: str
    rule_description: str
    is_official: bool = True  # Resmi kural mı, lokal kural mı?


class Equipment(BaseModel):
    """Ekipman"""
    name: str
    is_required: bool = True
    description: Optional[str] = None


class ApprovalStatus(str, Enum):
    """Onay Durumu"""
    PENDING = "pending"  # Onay bekliyor
    APPROVED = "approved"  # Onaylandı
    REJECTED = "rejected"  # Reddedildi


class MatchScoreSettings(BaseModel):
    """Maç Skoru Ayarları"""
    uses_sets: bool = False  # Set sistemi kullanılıyor mu?
    max_sets: int = 3  # Maksimum set sayısı (1, 3, 5, 7)
    points_per_set: Optional[int] = None  # Set başına puan (11, 15, 21, 25)
    allow_draw: bool = True  # Beraberlik olabilir mi?
    
class LeaguePointsSettings(BaseModel):
    """Lig/Turnuva Puanlama Ayarları"""
    win_points: int = 3  # Galibiyet puanı
    loss_points: int = 0  # Mağlubiyet puanı
    draw_points: int = 1  # Beraberlik puanı
    forfeit_win_points: int = 3  # Hükmen galibiyet puanı
    forfeit_loss_points: int = 0  # Hükmen mağlubiyet puanı


class SportConfiguration(BaseModel):
    """
    Merkezi Spor Yapılandırması
    Tüm spor dallarının detaylı bilgilerini tutar
    """
    id: Optional[str] = None
    
    # Temel Bilgiler
    sport_name: str  # Futbol, Basketbol, Tenis, vb.
    sport_name_en: Optional[str] = None  # İngilizce adı
    category: str  # Takım Sporu, Bireysel Spor, Raket Sporları, vb.
    description: Optional[str] = None
    
    # Saha/Alan Bilgileri
    field_type: List[FieldType] = []  # Birden fazla tip olabilir
    field_dimensions: Optional[FieldDimensions] = None
    
    # Oyuncu Bilgileri
    player_count: Optional[PlayerCount] = None
    
    # Oyun Süresi
    game_duration: Optional[GameDuration] = None
    
    # Puanlama Sistemi
    scoring_system: ScoringSystem = ScoringSystem.POINTS
    scoring_details: Optional[str] = None  # Detaylı açıklama
    
    # Yarışma Formatları (Yeni!)
    competition_formats: List[CompetitionFormat] = []  # En az bir format zorunlu
    
    # Maç Skoru Ayarları (Yeni!)
    match_score_settings: Optional[MatchScoreSettings] = None
    
    # Lig/Turnuva Puanlama Ayarları (Yeni!)
    league_points_settings: Optional[LeaguePointsSettings] = None
    
    # Kurallar
    rules: List[SportRule] = []
    
    # Ekipmanlar
    equipments: List[Equipment] = []
    
    # Özel Parametreler (JSON)
    custom_parameters: Dict[str, Any] = {}
    
    # Admin/Sistem Bilgileri
    is_system_default: bool = False  # Sistem tarafından tanımlı mı?
    created_by: Optional[str] = None  # User ID (admin)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    # Onay Sistemi Alanları
    approval_status: Optional[str] = "approved"  # pending, approved, rejected
    submitted_by: Optional[str] = None  # Değişikliği yapan kullanıcı ID
    submitted_by_name: Optional[str] = None  # Değişikliği yapan kullanıcı adı
    submitted_at: Optional[datetime] = None  # Değişiklik tarihi
    reviewed_by: Optional[str] = None  # Onaylayan/Reddeden admin ID
    reviewed_by_name: Optional[str] = None  # Onaylayan/Reddeden admin adı
    reviewed_at: Optional[datetime] = None  # Onay/Red tarihi
    review_note: Optional[str] = None  # Onay/Red notu
    pending_changes: Optional[Dict[str, Any]] = None  # Onay bekleyen değişiklikler (edit için)



# ==================== PROMO CODE MODEL ====================

class PromoCode(BaseModel):
    id: str
    code: str  # Max 10 karakter, uppercase
    facility_id: Optional[str] = None  # Eğer belirtilirse sadece o tesiste geçerli
    discount_percentage: float  # İndirim yüzdesi
    valid_until: datetime  # Geçerlilik süresi
    usage_limit: Optional[int] = None  # Kullanım limiti
    used_count: int = 0  # Kaç kez kullanıldı
    is_active: bool = True
    created_by: str  # Admin veya tesis sahibi user_id
    created_at: datetime = Field(default_factory=datetime.utcnow)

