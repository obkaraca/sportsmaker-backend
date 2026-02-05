"""
Etkinlik Yönetim Sistemi - Backend Endpoints
Turnuva, Grup, Fikstür, Maç, Hakem, Sıralama yönetimi
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum
import uuid
import random
import math
import logging

# Auth import
from auth import get_current_user

# Logger setup
logger = logging.getLogger(__name__)

# Router oluştur
event_management_router = APIRouter(prefix="/event-management", tags=["Event Management"])

# Helper function to find event by both id formats
async def find_event_by_id(db, event_id: str):
    """Find event by UUID id field or MongoDB ObjectId"""
    event = await db.events.find_one({"id": event_id})
    if not event:
        try:
            from bson import ObjectId
            event = await db.events.find_one({"_id": ObjectId(event_id)})
        except:
            pass
    return event

# ================== ENUMS ==================

class MatchSystemType(str, Enum):
    SINGLE_ELIMINATION = "single_elimination"  # Eleme
    DOUBLE_ELIMINATION = "double_elimination"  # Çift Eleme
    ROUND_ROBIN = "round_robin"  # Tek Tur Lig
    DOUBLE_ROUND_ROBIN = "double_round_robin"  # Çift Tur Lig
    GROUPS_KNOCKOUT = "groups_knockout"  # Grup + Eleme
    SWISS = "swiss"  # İsviçre Sistemi

class GroupStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"

class MatchStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    PENDING_CONFIRMATION = "pending_confirmation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

# ================== PYDANTIC MODELS ==================

class GroupCreate(BaseModel):
    name: str
    participant_ids: List[str] = []
    match_system: MatchSystemType = MatchSystemType.ROUND_ROBIN

class GroupUpdate(BaseModel):
    name: Optional[str] = None
    participant_ids: Optional[List[str]] = None
    match_system: Optional[MatchSystemType] = None
    bye_participant_id: Optional[str] = None
    bye_participant_ids: Optional[List[str]] = None  # Çoklu bay desteği

class ParticipantSeedUpdate(BaseModel):
    """Oyuncu sıralama/seed güncelleme modeli"""
    participant_id: str
    seed_number: int  # 1, 2, 3... (1 = en iyi oyuncu)
    
class BulkSeedUpdate(BaseModel):
    """Toplu oyuncu sıralama modeli"""
    seeds: List[ParticipantSeedUpdate]

class MergeCategoriesRequest(BaseModel):
    """Kategori birleştirme isteği modeli"""
    genders: List[str]
    age_groups: List[int]
    game_types: List[str]
    players_per_group: int = 4
    distribution_mode: str = "add_players"
    merged_category_name: str = "Birleşik Kategori"

class PartnerUpdateRequest(BaseModel):
    """Partner güncelleme isteği modeli"""
    partner_type: str  # "doubles" veya "mixed"
    new_partner_id: Optional[str] = None  # None ise partner kaldırılır
    force_transfer: bool = False  # True ise çakışma olsa bile transfer et

class MatchCreate(BaseModel):
    group_id: Optional[str] = None
    participant1_id: str
    participant2_id: str
    scheduled_time: datetime
    court_number: Optional[int] = None
    referee_id: Optional[str] = None

class MatchUpdate(BaseModel):
    scheduled_time: Optional[datetime] = None
    court_number: Optional[int] = None
    referee_id: Optional[str] = None
    live_stream_url: Optional[str] = None
    status: Optional[str] = None  # pending, playing, completed, etc.

class MatchResultSubmit(BaseModel):
    winner_id: str
    score: str  # "21-15, 21-18" gibi
    sets: Optional[List[Dict[str, int]]] = None  # [{"participant1": 21, "participant2": 15}, ...]
    submitted_by: str  # user_id

class MatchResultConfirm(BaseModel):
    confirmed: bool
    confirmed_by: str  # user_id (hakem veya diğer oyuncu)

class MatchResultConfirmFrontend(BaseModel):
    """Frontend uyumlu onay modeli"""
    confirmed: bool
    user_role: Optional[str] = None  # Frontend'den gelen rol bilgisi (opsiyonel)

class MatchScoreCorrection(BaseModel):
    """Maç skoru düzeltme modeli - sadece organizatör/yönetici kullanabilir"""
    new_winner_id: str
    new_score: str  # "3-1" gibi
    corrected_by: str  # user_id
    reason: Optional[str] = None  # Düzeltme sebebi (opsiyonel)

# ================== SPORCU YÖNETİMİ MODELLERİ ==================

class AthletePointUpdate(BaseModel):
    """Tek sporcu puan güncelleme"""
    participant_id: str
    points: float  # Puan değeri (ondalık destekli)

class CustomScoreUpdate(BaseModel):
    """Özel puan güncelleme"""
    participant_id: str
    custom_score: float
    custom_score_name: Optional[str] = "Özel Puan"

class BulkAthletePointsUpdate(BaseModel):
    """Toplu sporcu puan güncelleme - Excel benzeri hızlı giriş için"""
    updates: List[AthletePointUpdate]
    custom_score_updates: Optional[List[CustomScoreUpdate]] = None
    use_custom_scoring: Optional[bool] = False
    custom_scoring_name: Optional[str] = "Özel Puan"

class AthleteAdd(BaseModel):
    """Etkinliğe sporcu ekleme"""
    user_id: str
    initial_points: float = 0  # Başlangıç puanı (opsiyonel)

class TournamentSettings(BaseModel):
    event_id: Optional[str] = None  # URL'den alınacak, body'de opsiyonel
    group_count: Optional[int] = None  # None = otomatik
    match_system: MatchSystemType = MatchSystemType.ROUND_ROBIN
    court_count: int = 1
    match_duration_minutes: int = 30
    break_between_matches_minutes: int = 10
    start_time: Optional[str] = None  # String olarak da kabul et
    auto_referee_assignment: bool = False
    auto_court_assignment: bool = True

class DrawSettings(BaseModel):
    event_id: str
    draw_type: str = "auto"  # "auto" veya "manual"
    seed_top_players: bool = True
    separate_same_club: bool = False

# ================== BRACKET DÜZENLEME MODELLERİ ==================

class BracketSlot(BaseModel):
    """Bracket pozisyonu"""
    round_number: int
    match_order: int
    participant1_id: Optional[str] = None
    participant2_id: Optional[str] = None

class BracketUpdateRequest(BaseModel):
    """Bracket güncelleme isteği"""
    category: str  # "Open (Karma)", "Tekler - Erkekler" vb.
    slots: List[BracketSlot]

class BracketMatchCreateRequest(BaseModel):
    """Bracket'tan maç oluşturma isteği"""
    category: str
    create_all_rounds: bool = True  # Tüm turları oluştur
    scheduled_time: Optional[str] = None  # Maç başlangıç zamanı

# ================== HELPER FUNCTIONS ==================

def calculate_optimal_group_count(participant_count: int) -> int:
    """Katılımcı sayısına göre optimal grup sayısını hesapla"""
    if participant_count <= 4:
        return 1
    elif participant_count <= 8:
        return 2
    elif participant_count <= 16:
        return 4
    elif participant_count <= 32:
        return 8
    else:
        return math.ceil(participant_count / 4)

def generate_round_robin_matches(participants: List[str]) -> List[tuple]:
    """Round Robin (Tek Tur Lig) maç çiftlerini oluştur"""
    matches = []
    n = len(participants)
    
    # Tek sayıda katılımcı varsa BYE ekle
    if n % 2 == 1:
        participants = participants + ["BYE"]
        n += 1
    
    for round_num in range(n - 1):
        for i in range(n // 2):
            p1 = participants[i]
            p2 = participants[n - 1 - i]
            if p1 != "BYE" and p2 != "BYE":
                matches.append((p1, p2, round_num + 1))
        
        # Rotate participants (first stays fixed)
        participants = [participants[0]] + [participants[-1]] + participants[1:-1]
    
    return matches

def generate_double_round_robin_matches(participants: List[str]) -> List[tuple]:
    """Çift Tur Lig maç çiftlerini oluştur"""
    first_round = generate_round_robin_matches(participants)
    second_round = [(p2, p1, r + len(first_round) // len(participants) + 1) for p1, p2, r in first_round]
    return first_round + second_round

def generate_single_elimination_bracket(participants: List[str]) -> List[tuple]:
    """Tek eleme bracket oluştur"""
    matches = []
    n = len(participants)
    
    # 2'nin kuvvetine yuvarla
    bracket_size = 2 ** math.ceil(math.log2(n))
    
    # BYE ekle
    byes_needed = bracket_size - n
    seeded = participants + ["BYE"] * byes_needed
    
    # İlk tur maçları
    round_num = 1
    for i in range(0, bracket_size, 2):
        p1 = seeded[i]
        p2 = seeded[i + 1]
        if p1 != "BYE" and p2 != "BYE":
            matches.append((p1, p2, round_num))
    
    return matches

def generate_swiss_pairings(participants: List[Dict], round_num: int, previous_matches: List[tuple]) -> List[tuple]:
    """İsviçre sistemi eşleştirmesi"""
    # Puanlara göre sırala
    sorted_participants = sorted(participants, key=lambda x: x.get("points", 0), reverse=True)
    
    matches = []
    used = set()
    
    for p in sorted_participants:
        if p["id"] in used:
            continue
        
        # Benzer puanlı rakip bul
        for opponent in sorted_participants:
            if opponent["id"] in used or opponent["id"] == p["id"]:
                continue
            
            # Daha önce eşleşmediler mi kontrol et
            if (p["id"], opponent["id"]) not in previous_matches and (opponent["id"], p["id"]) not in previous_matches:
                matches.append((p["id"], opponent["id"], round_num))
                used.add(p["id"])
                used.add(opponent["id"])
                break
    
    return matches

def assign_courts_automatically(matches: List[Dict], court_count: int, match_duration: int, break_time: int, start_time: datetime) -> List[Dict]:
    """Sahaları otomatik ata"""
    court_availability = {i: start_time for i in range(1, court_count + 1)}
    
    for match in matches:
        # En erken müsait sahayı bul
        earliest_court = min(court_availability, key=court_availability.get)
        earliest_time = court_availability[earliest_court]
        
        match["court_number"] = earliest_court
        match["scheduled_time"] = earliest_time
        
        # Saha müsaitlik zamanını güncelle
        court_availability[earliest_court] = earliest_time + timedelta(minutes=match_duration + break_time)
    
    return matches

def smart_schedule_matches(
    matches: List[Dict], 
    court_count: int, 
    match_duration: int, 
    break_minutes: int, 
    start_time: datetime,
    min_rest_minutes: int = 10,
    prevent_overlap: bool = True,
    balance_courts: bool = True,
    end_time: datetime = None,
    has_break: bool = False,
    break_start_time: datetime = None,
    break_end_time: datetime = None,
    is_multi_day: bool = False,
    event_end_date: datetime = None,
    in_group_refereeing: bool = False,
    group_participants: Dict[str, List[str]] = None,  # {group_id: [participant_ids]}
    assign_groups_to_courts: bool = True,  # Her gruba bir saha ata
    scheduling_event_types: List[str] = None,  # Etkinlik türü önceliği: ['tek', 'cift', 'karisik']
    scheduling_genders: List[str] = None,  # Cinsiyet önceliği: ['male', 'female', 'all']
    scheduling_age_groups: List[str] = None  # Yaş grubu önceliği: ['U12', 'U14', 'U16', 'yetiskin']
) -> List[Dict]:
    """
    Akıllı Fikstür Planlama Algoritması
    
    Bu algoritma şunları optimize eder:
    1. Sporcu çakışmasını önleme - Bir oyuncu aynı anda iki maçta olamaz
    2. Dinlenme süreleri - Oyuncular arka arkaya maç yapmadan dinlenir
    3. Saha dengeleme - Tüm sahalar eşit kullanılır
    4. Minimum sürede maksimum maç - En verimli zamanlama
    5. Ara saatinde maç planlamama - Öğle arası vs.
    6. Bitiş saatini aşmama
    7. Çok günlü etkinliklerde (hafta sonu vb.) ertesi güne aktarma
    8. Grup içi hakemlik - Maçı olmayan grup üyeleri hakem olarak atanır
    9. Her gruba sabit saha atama - Aynı gruptaki tüm maçlar aynı sahada oynanır
    10. Öncelik sıralaması: Etkinlik türü → Yaş grubu → Cinsiyet
    """
    from collections import defaultdict
    
    total_slot_minutes = match_duration + break_minutes
    
    # Hakem atama takibi (grup içi hakemlik için)
    referee_busy_times = defaultdict(list)  # {referee_id: [(start_time, end_time), ...]}
    
    # Günlük başlangıç ve bitiş saatleri (saat ve dakika olarak sakla)
    daily_start_hour = start_time.hour
    daily_start_minute = start_time.minute
    daily_end_hour = end_time.hour if end_time else 18
    daily_end_minute = end_time.minute if end_time else 0
    
    # Günlük ara saatleri
    daily_break_start_hour = break_start_time.hour if break_start_time else 12
    daily_break_start_minute = break_start_time.minute if break_start_time else 0
    daily_break_end_hour = break_end_time.hour if break_end_time else 13
    daily_break_end_minute = break_end_time.minute if break_end_time else 0
    
    # Mevcut gün
    current_day = start_time.date()
    max_day = event_end_date.date() if event_end_date else current_day + timedelta(days=7)  # Varsayılan 1 hafta
    
    # Günün başlangıç ve bitiş zamanlarını hesapla
    def get_day_times(day_date):
        day_start = datetime.combine(day_date, datetime.min.time().replace(hour=daily_start_hour, minute=daily_start_minute))
        day_end = datetime.combine(day_date, datetime.min.time().replace(hour=daily_end_hour, minute=daily_end_minute))
        day_break_start = datetime.combine(day_date, datetime.min.time().replace(hour=daily_break_start_hour, minute=daily_break_start_minute))
        day_break_end = datetime.combine(day_date, datetime.min.time().replace(hour=daily_break_end_hour, minute=daily_break_end_minute))
        return day_start, day_end, day_break_start, day_break_end
    
    # Varsayılan bitiş saati
    if end_time is None:
        end_time = start_time + timedelta(hours=12)
    
    def is_in_break_time(check_time):
        """Verilen zaman ara saatinde mi? (herhangi bir günde)"""
        if not has_break:
            return False
        check_hour = check_time.hour
        check_minute = check_time.minute
        check_total = check_hour * 60 + check_minute
        break_start_total = daily_break_start_hour * 60 + daily_break_start_minute
        break_end_total = daily_break_end_hour * 60 + daily_break_end_minute
        return break_start_total <= check_total < break_end_total
    
    def get_next_available_time(current_time, current_end_time):
        """Ara saatini atlayarak sonraki uygun zamanı bul - ertesi güne geçebilir"""
        # Ara saatindeyse, ara bitişine atla
        if is_in_break_time(current_time):
            day_start, day_end, day_break_start, day_break_end = get_day_times(current_time.date())
            return day_break_end
        
        # Günün bitiş saatini aşıyorsa ve çok günlü etkinlikse
        if is_multi_day and current_time >= current_end_time:
            next_day = current_time.date() + timedelta(days=1)
            if next_day <= max_day:
                next_day_start, next_day_end, _, _ = get_day_times(next_day)
                logging.info(f"📅 Ertesi güne geçiliyor: {current_time.date()} -> {next_day}")
                return next_day_start
        
        return current_time
    
    def get_current_day_end(current_time):
        """Mevcut günün bitiş zamanını döndür"""
        _, day_end, _, _ = get_day_times(current_time.date())
        return day_end
    
    # ==================== GRUPLARA SAHA ATAMA ====================
    # Benzersiz grupları topla ve alfabetik sırala (A, B, C, ...)
    unique_groups = sorted(list(set(m.get("group_id") for m in matches if m.get("group_id"))), 
                          key=lambda g: next((m.get("group_name", "") for m in matches if m.get("group_id") == g), g or ""))
    logging.info(f"🏟️ Toplam {len(unique_groups)} grup için saha ataması yapılacak")
    
    # Gruplara saha ata - alfabetik sıra ile Saha 1'den başla
    # Grup A → Saha 1, Grup B → Saha 2, ...
    group_to_court = {}
    if assign_groups_to_courts and unique_groups:
        for idx, group_id in enumerate(unique_groups):
            # Saha 1'den başla, saha sayısını aşarsa döngüye gir
            assigned_court = (idx % court_count) + 1
            group_to_court[group_id] = assigned_court
            
        # Log group-court mapping
        for group_id, court in list(group_to_court.items())[:10]:
            group_name = next((m.get("group_name") for m in matches if m.get("group_id") == group_id), "?")
            logging.info(f"   🏟️ Grup '{group_name}' -> Saha {court}")
        
        if len(group_to_court) > 10:
            logging.info(f"   ... ve {len(group_to_court) - 10} grup daha")
    
    # Saha müsaitlik zamanları - her saha için ayrı takip
    court_availability = {i: start_time for i in range(1, court_count + 1)}
    
    # HER GRUP İÇİN AYRI SAHA MÜSAİTLİK TAKİBİ
    # Aynı gruptaki maçlar sırayla oynanacak
    group_court_availability = {group_id: start_time for group_id in unique_groups}
    
    # Oyuncu son maç bitiş zamanları (dinlenme kontrolü için)
    player_last_match_end = defaultdict(lambda: start_time - timedelta(minutes=min_rest_minutes + 1))
    
    # Saha kullanım sayıları (dengeleme için)
    court_usage_count = {i: 0 for i in range(1, court_count + 1)}
    
    # Zamanlanan maçlar
    scheduled_matches = []
    
    # ==================== ÖNCELİK SIRALAMA FONKSİYONLARI ====================
    
    def get_match_event_type_priority(match):
        """Etkinlik türü önceliğini belirle (tek, çift, karışık)"""
        group_name = (match.get('group_name') or '').lower()
        category = (match.get('category') or '').lower()
        event_type = (match.get('event_type') or '').lower()
        combined = f"{group_name} {category} {event_type}"
        
        is_mixed = 'karışık' in combined or 'mixed' in combined or 'mikst' in combined
        is_doubles = 'çift' in combined or 'double' in combined
        is_singles = 'tek' in combined or 'single' in combined
        
        detected_type = None
        if is_singles and not is_doubles and not is_mixed:
            detected_type = 'tek'
        elif is_doubles and not is_mixed:
            detected_type = 'cift'
        elif is_mixed:
            detected_type = 'karisik'
        else:
            detected_type = 'tek'  # Varsayılan
        
        # Kullanıcı sıralaması varsa onu kullan
        if scheduling_event_types and detected_type:
            # Türkçe/İngilizce eşleştirme
            type_mapping = {
                'tek': ['tek', 'single', 'singles'],
                'cift': ['cift', 'çift', 'double', 'doubles'],
                'karisik': ['karisik', 'karışık', 'mixed', 'mikst']
            }
            for idx, priority_type in enumerate(scheduling_event_types):
                priority_type_lower = priority_type.lower()
                for key, values in type_mapping.items():
                    if priority_type_lower in values and detected_type == key:
                        return idx
            return len(scheduling_event_types)  # Listede yoksa en sona
        
        # Varsayılan sıralama: TEK (0) -> ÇİFT (1) -> KARIŞIK (2)
        if detected_type == 'tek':
            return 0
        elif detected_type == 'cift':
            return 1
        else:
            return 2
    
    def get_match_age_group_priority(match):
        """Yaş grubu önceliğini belirle"""
        group_name = (match.get('group_name') or '').lower()
        category = (match.get('category') or '').lower()
        age_group = (match.get('age_group') or '').lower()
        combined = f"{group_name} {category} {age_group}"
        
        # Yaş gruplarını tespit et
        detected_age = None
        age_patterns = {
            'u10': ['u10', 'u-10', '10 yaş', 'minik'],
            'u12': ['u12', 'u-12', '12 yaş', 'küçük'],
            'u14': ['u14', 'u-14', '14 yaş', 'yıldız'],
            'u16': ['u16', 'u-16', '16 yaş', 'genç'],
            'u18': ['u18', 'u-18', '18 yaş'],
            'u21': ['u21', 'u-21', '21 yaş'],
            'yetiskin': ['yetişkin', 'yetiskin', 'adult', 'açık', 'open', 'genel']
        }
        
        for age_key, patterns in age_patterns.items():
            for pattern in patterns:
                if pattern in combined:
                    detected_age = age_key
                    break
            if detected_age:
                break
        
        # Sayısal yaş arama (30, 40, 50, 60, 70 vb.)
        detected_numeric_age = None
        import re
        age_numbers = re.findall(r'\b(\d{2})\b', combined)
        for num in age_numbers:
            num_int = int(num)
            if 10 <= num_int <= 80:
                detected_numeric_age = num_int
                break
        
        if not detected_age:
            detected_age = 'yetiskin'  # Varsayılan
        
        # Kullanıcı sıralaması varsa onu kullan
        if scheduling_age_groups:
            for idx, priority_age in enumerate(scheduling_age_groups):
                # Sayısal yaş kontrolü (70, 64, 60, 30, 40, 50 gibi)
                if isinstance(priority_age, (int, float)):
                    # Sayısal yaş eşleşmesi
                    if detected_numeric_age and abs(detected_numeric_age - priority_age) <= 5:
                        return idx
                else:
                    # String yaş kontrolü (u12, u14, yetiskin gibi)
                    priority_age_lower = str(priority_age).lower()
                    for age_key, patterns in age_patterns.items():
                        if priority_age_lower in patterns or priority_age_lower == age_key:
                            if detected_age == age_key:
                                return idx
            return len(scheduling_age_groups)  # Listede yoksa en sona
        
        # Varsayılan: Küçük yaştan büyüğe
        age_order = {'u10': 0, 'u12': 1, 'u14': 2, 'u16': 3, 'u18': 4, 'u21': 5, 'yetiskin': 6}
        return age_order.get(detected_age, 99)
    
    def get_match_gender_priority(match):
        """Cinsiyet önceliğini belirle"""
        group_name = (match.get('group_name') or '').lower()
        category = (match.get('category') or '').lower()
        gender = (match.get('gender') or '').lower()
        combined = f"{group_name} {category} {gender}"
        
        detected_gender = None
        if 'erkek' in combined or 'male' in combined or 'bay' in combined:
            detected_gender = 'male'
        elif 'kadın' in combined or 'kız' in combined or 'female' in combined or 'bayan' in combined:
            detected_gender = 'female'
        elif 'karışık' in combined or 'mixed' in combined:
            detected_gender = 'mixed'
        else:
            detected_gender = 'all'  # Varsayılan
        
        # Kullanıcı sıralaması varsa onu kullan
        if scheduling_genders:
            gender_mapping = {
                'male': ['male', 'erkek', 'bay'],
                'female': ['female', 'kadın', 'kız', 'bayan'],
                'mixed': ['mixed', 'karışık'],
                'all': ['all', 'hepsi', 'genel']
            }
            for idx, priority_gender in enumerate(scheduling_genders):
                priority_gender_lower = priority_gender.lower()
                for key, values in gender_mapping.items():
                    if priority_gender_lower in values or priority_gender_lower == key:
                        if detected_gender == key:
                            return idx
            return len(scheduling_genders)  # Listede yoksa en sona
        
        # Varsayılan sıralama: Erkek (0) -> Kadın (1) -> Karışık (2) -> Tümü (3)
        gender_order = {'male': 0, 'female': 1, 'mixed': 2, 'all': 3}
        return gender_order.get(detected_gender, 99)
    
    def get_combined_priority(match):
        """Tüm öncelikleri birleştir: (etkinlik_türü, yaş_grubu, cinsiyet, grup_adı, tur)"""
        return (
            get_match_event_type_priority(match),
            get_match_age_group_priority(match),
            get_match_gender_priority(match),
            match.get('group_name', ''),
            match.get('round_number', 1)
        )
    
    # Maçları öncelik sırasına göre grupla
    logging.info(f"🎯 Maçlar öncelik sıralamasına göre düzenleniyor...")
    logging.info(f"   Etkinlik türü önceliği: {scheduling_event_types or ['tek', 'cift', 'karisik']}")
    logging.info(f"   Yaş grubu önceliği: {scheduling_age_groups or ['varsayılan sıra']}")
    logging.info(f"   Cinsiyet önceliği: {scheduling_genders or ['male', 'female', 'mixed', 'all']}")
    
    # Maçları önceliğe göre sırala
    sorted_by_priority = sorted(matches, key=get_combined_priority)
    
    # Öncelik gruplarına ayır
    from collections import OrderedDict
    priority_groups = OrderedDict()
    for match in sorted_by_priority:
        priority_key = (
            get_match_event_type_priority(match),
            get_match_age_group_priority(match),
            get_match_gender_priority(match)
        )
        if priority_key not in priority_groups:
            priority_groups[priority_key] = []
        priority_groups[priority_key].append(match)
    
    logging.info(f"   {len(priority_groups)} farklı öncelik grubu oluşturuldu")
    
    # Maçları grup bazlı ve tur bazlı round-robin şeklinde sırala
    # Amaç: Grup A 1. maç → Grup B 1. maç → Grup C 1. maç → Grup A 2. maç → ...
    def sort_matches_round_robin(match_list):
        """
        Maçları gruplar arası round-robin şeklinde sırala.
        Her grupta aynı tur numarasındaki maçları ardışık değil, dönüşümlü planla.
        """
        if not match_list:
            return []
        
        # Maçları grup ve tur numarasına göre grupla
        from collections import defaultdict
        rounds_by_group = defaultdict(lambda: defaultdict(list))
        
        for match in match_list:
            group_id = match.get("group_id", "default")
            round_num = match.get("round_number", 1)
            rounds_by_group[group_id][round_num].append(match)
        
        # Tüm grupları ve turları bul
        all_groups = list(rounds_by_group.keys())
        all_rounds = sorted(set(
            r for group_matches in rounds_by_group.values() 
            for r in group_matches.keys()
        ))
        
        sorted_matches = []
        
        # Her tur için gruplar arasında dön
        for round_num in all_rounds:
            # Bu turdaki tüm grupların maçlarını topla
            round_matches_by_group = {}
            for group_id in all_groups:
                if round_num in rounds_by_group[group_id]:
                    round_matches_by_group[group_id] = rounds_by_group[group_id][round_num][:]
            
            # Round-robin: Her gruptan sırayla bir maç al
            while any(round_matches_by_group.values()):
                for group_id in all_groups:
                    if group_id in round_matches_by_group and round_matches_by_group[group_id]:
                        sorted_matches.append(round_matches_by_group[group_id].pop(0))
        
        logging.info(f"🔄 Round-robin sıralama: {len(all_groups)} grup, {len(all_rounds)} tur -> {len(sorted_matches)} maç")
        
        return sorted_matches
    
    def sort_matches_by_group_sequential(match_list):
        """
        Maçları grup bazlı ARDIŞIK sırala.
        Her grubun TÜM maçları sırayla listelenir, böylece aynı sahada peş peşe oynarlar.
        Grup A tüm maçları -> Grup B tüm maçları -> ...
        """
        if not match_list:
            return []
        
        from collections import defaultdict
        matches_by_group = defaultdict(list)
        
        for match in match_list:
            group_id = match.get("group_id", "default")
            matches_by_group[group_id].append(match)
        
        # Her grup içinde tur numarasına göre sırala
        for group_id in matches_by_group:
            matches_by_group[group_id].sort(key=lambda m: m.get("round_number", 1))
        
        # Grupları sırayla birleştir
        sorted_matches = []
        for group_id in sorted(matches_by_group.keys(), key=str):
            sorted_matches.extend(matches_by_group[group_id])
        
        logging.info(f"📋 Grup bazlı ardışık sıralama: {len(matches_by_group)} grup -> {len(sorted_matches)} maç")
        
        return sorted_matches
    
    # Her öncelik grubunu GRUP BAZLI ARDIŞIK şekilde sırala (round-robin DEĞİL)
    # Bu sayede her grup kendi sahasında peş peşe oynar
    pending_matches = []
    for priority_key, group_matches in priority_groups.items():
        pending_matches.extend(sort_matches_by_group_sequential(group_matches))
    
    # Çok günlü etkinlik için iteration limiti artır
    max_iterations = len(pending_matches) * court_count * (50 if is_multi_day else 20)
    iteration = 0
    
    logging.info(f"📅 Çok günlü planlama: is_multi_day={is_multi_day}, max_day={max_day}")
    
    while pending_matches and iteration < max_iterations:
        iteration += 1
        
        scheduled_this_round = False
        
        for match_idx, match in enumerate(pending_matches):
            group_id = match.get("group_id")
            group_name = (match.get("group_name") or "").lower()
            
            # Yarı final ve final maçları için ortadaki sahaları tercih et
            is_semifinal = "yarı final" in group_name or "semifinal" in group_name or "semi-final" in group_name
            is_final = ("final" in group_name and "yarı" not in group_name and "semi" not in group_name) or "şampiyon" in group_name or "grand final" in group_name
            is_important_match = is_semifinal or is_final
            
            if is_important_match:
                # Ortadaki sahaları hesapla (örn: 16 saha varsa 7,8,9,10)
                middle_start = max(1, (court_count // 2) - 1)
                middle_end = min(court_count, (court_count // 2) + 2)
                middle_courts = list(range(middle_start, middle_end + 1))
                
                # En erken müsait ortadaki sahayı bul
                target_court = min(middle_courts, key=lambda c: (court_availability.get(c, start_time), court_usage_count.get(c, 0)))
                logging.info(f"🏆 Önemli maç ({group_name}) -> Ortadaki sahalardan Saha {target_court} seçildi")
            # Gruba atanmış sahayı bul
            elif assign_groups_to_courts and group_id in group_to_court:
                target_court = group_to_court[group_id]
            else:
                # Grup ataması yoksa en az kullanılan sahayı seç
                if balance_courts:
                    target_court = min(court_availability.keys(), key=lambda c: (court_availability[c], court_usage_count[c]))
                else:
                    target_court = min(court_availability.keys(), key=lambda c: court_availability[c])
            
            court_time = court_availability[target_court]
            current_day_end = get_current_day_end(court_time)
            
            # GRUP İÇİ SIRA KONTROLÜ
            # Aynı gruptaki maçlar sırayla oynanmalı - grubun kendi sahasındaki son maç bitene kadar bekle
            if group_id and group_id in group_court_availability:
                group_last_time = group_court_availability[group_id]
                if group_last_time > court_time:
                    court_time = group_last_time
            
            # Ara saatini atla veya ertesi güne geç
            court_time = get_next_available_time(court_time, current_day_end)
            
            # Günün bitiş saatini kontrol et
            match_end = court_time + timedelta(minutes=match_duration)
            current_day_end = get_current_day_end(court_time)  # Yeni gün için tekrar hesapla
            
            if match_end > current_day_end:
                # Çok günlü etkinlikse ertesi güne geç
                if is_multi_day:
                    next_day = court_time.date() + timedelta(days=1)
                    if next_day <= max_day:
                        next_day_start, _, _, _ = get_day_times(next_day)
                        court_availability[target_court] = next_day_start
                        continue
                continue  # Bu saha bugün için dolu
            
            p1 = match.get("participant1_id")
            p2 = match.get("participant2_id")
            
            # Çift maçı için tüm oyuncuları kontrol et
            if match.get("is_doubles"):
                # pair_id formatı: "player1_player2" olabilir
                players = []
                if "_" in str(p1):
                    players.extend(p1.split("_"))
                else:
                    players.append(p1)
                if "_" in str(p2):
                    players.extend(p2.split("_"))
                else:
                    players.append(p2)
            else:
                players = [p1, p2]
            
            can_schedule = True
            
            if prevent_overlap:
                # Tüm oyuncuların dinlenme süresini kontrol et
                for player in players:
                    if player:
                        last_end = player_last_match_end[player]
                        required_rest_end = last_end + timedelta(minutes=min_rest_minutes)
                        if court_time < required_rest_end:
                            can_schedule = False
                            break
                
                # Grup içi hakemlik aktifse, hakem olarak görevli oyuncunun çakışmasını kontrol et
                if can_schedule and in_group_refereeing:
                    for player in players:
                        if player:
                            # Bu oyuncu bu saatte hakem mi?
                            for ref_time_start, ref_time_end in referee_busy_times.get(player, []):
                                if ref_time_start <= court_time < ref_time_end:
                                    can_schedule = False
                                    break
                        if not can_schedule:
                            break
            
            if can_schedule:
                # Maçı planla
                match["court_number"] = target_court
                match["scheduled_time"] = court_time
                
                match_end_time = court_time + timedelta(minutes=match_duration)
                
                # Grup içi hakemlik - hakem ata (SADECE AYNI GRUPTAN)
                if in_group_refereeing and group_participants:
                    if group_id and group_id in group_participants:
                        # Bu grubun oyuncularından uygun hakem bul
                        potential_referees = group_participants[group_id]
                        assigned_referee = None
                        
                        for ref_candidate in potential_referees:
                            # Maçta oynayan kişi hakem olamaz
                            if ref_candidate in players:
                                continue
                            
                            # Bu saatte başka görevi var mı?
                            is_busy = False
                            
                            # Hakem olarak başka maçta mı?
                            for ref_time_start, ref_time_end in referee_busy_times.get(ref_candidate, []):
                                if not (match_end_time <= ref_time_start or court_time >= ref_time_end):
                                    is_busy = True
                                    break
                            
                            # Oyuncu olarak başka maçta mı?
                            if not is_busy:
                                last_end = player_last_match_end.get(ref_candidate)
                                if last_end:
                                    required_rest_end = last_end + timedelta(minutes=min_rest_minutes)
                                    if court_time < required_rest_end:
                                        is_busy = True
                            
                            if not is_busy:
                                assigned_referee = ref_candidate
                                break
                        
                        if assigned_referee:
                            match["referee_id"] = assigned_referee
                            match["referee_is_player"] = True  # Bu hakem aynı zamanda gruptaki bir oyuncu
                            referee_busy_times[assigned_referee].append((court_time, match_end_time))
                            logging.debug(f"👨‍⚖️ Hakem atandı: {assigned_referee} -> Saha {target_court} @ {court_time.strftime('%H:%M')}")
                
                # Oyuncuların son maç zamanlarını güncelle
                for player in players:
                    if player:
                        player_last_match_end[player] = match_end_time
                
                # Saha müsaitliğini güncelle (ara saatini atlayarak veya ertesi güne geçerek)
                next_slot = court_time + timedelta(minutes=total_slot_minutes)
                current_day_end_for_update = get_current_day_end(next_slot)
                court_availability[target_court] = get_next_available_time(next_slot, current_day_end_for_update)
                court_usage_count[target_court] += 1
                
                # GRUP MÜSAİTLİK ZAMANINI GÜNCELLE
                # Aynı gruptaki sonraki maç, bu maç bittikten sonra başlayabilir
                if group_id and group_id in group_court_availability:
                    group_court_availability[group_id] = get_next_available_time(next_slot, current_day_end_for_update)
                
                scheduled_matches.append(match)
                pending_matches.pop(match_idx)
                scheduled_this_round = True
                break
        
        # Bu turda hiç maç planlanamadıysa, en erken saha zamanını ilerlet
        if not scheduled_this_round and pending_matches:
            # Bekleyen maçların gruplarına ait sahaları ilerlet
            for match in pending_matches[:1]:  # İlk bekleyen maç
                group_id = match.get("group_id")
                if assign_groups_to_courts and group_id in group_to_court:
                    target_court = group_to_court[group_id]
                else:
                    target_court = min(court_availability, key=court_availability.get)
                
                current = court_availability[target_court]
                current_day_end_for_advance = get_current_day_end(current)
                
                # Ara saatindeyse aradan sonraya atla
                if is_in_break_time(current):
                    _, _, _, day_break_end = get_day_times(current.date())
                    court_availability[target_court] = day_break_end
                # Günün bitiş saatini aşıyorsa ertesi güne geç
                elif is_multi_day and current >= current_day_end_for_advance:
                    next_day = current.date() + timedelta(days=1)
                    if next_day <= max_day:
                        next_day_start, _, _, _ = get_day_times(next_day)
                        court_availability[target_court] = next_day_start
                    else:
                        court_availability[target_court] = current + timedelta(minutes=1)
                else:
                    court_availability[target_court] = current + timedelta(minutes=1)
    
    # Planlanamayan maçları logla
    if pending_matches:
        logging.warning(f"⚠️ {len(pending_matches)} maç bitiş saati nedeniyle planlanamadı - zamansız olarak eklenecek")
        # Planlanamayan maçları da listeye ekle (scheduled_time = None)
        for match in pending_matches:
            match["scheduled_time"] = None
            match["court_number"] = None
            scheduled_matches.append(match)
    
    # Son istatistikleri logla (sadece zamanlanmış maçlar için)
    scheduled_with_time = [m for m in scheduled_matches if m.get("scheduled_time") is not None]
    if scheduled_with_time:
        first_match = min(scheduled_with_time, key=lambda m: m.get("scheduled_time"))
        last_match = max(scheduled_with_time, key=lambda m: m.get("scheduled_time"))
        duration = last_match["scheduled_time"] - first_match["scheduled_time"]
        
        logging.info(f"📊 Fikstür istatistikleri:")
        logging.info(f"   - Toplam maç: {len(scheduled_matches)}")
        logging.info(f"   - Zamanlanmış maç: {len(scheduled_with_time)}")
        logging.info(f"   - Zamansız maç: {len(scheduled_matches) - len(scheduled_with_time)}")
        logging.info(f"   - İlk maç: {first_match['scheduled_time'].strftime('%H:%M')}")
        logging.info(f"   - Son maç: {last_match['scheduled_time'].strftime('%H:%M')}")
        logging.info(f"   - Toplam süre: {duration}")
        logging.info(f"   - Saha kullanımı: {dict(court_usage_count)}")
        if has_break:
            logging.info(f"   - Ara: {break_start_time.strftime('%H:%M')}-{break_end_time.strftime('%H:%M')}")
        
        # Grup-saha dağılımını logla
        if assign_groups_to_courts:
            group_court_stats = defaultdict(set)
            for m in scheduled_with_time:
                group_court_stats[m.get("group_name", "?")].add(m.get("court_number"))
            logging.info(f"🏟️ Grup-Saha dağılımı:")
            for gname, courts in list(group_court_stats.items())[:10]:
                logging.info(f"   - {gname}: Saha {list(courts)}")
    
    return scheduled_matches

def assign_referees_automatically(matches: List[Dict], available_referees: List[str], participants: List[str]) -> List[Dict]:
    """Hakemleri otomatik ata - çakışma kontrolü ile"""
    referee_assignments = {ref: [] for ref in available_referees}
    
    for match in matches:
        match_time = match.get("scheduled_time")
        match_participants = [match.get("participant1_id"), match.get("participant2_id")]
        
        # Uygun hakem bul
        best_referee = None
        min_assignments = float("inf")
        
        for referee in available_referees:
            # Hakem bu maçta oyuncu mu?
            if referee in match_participants:
                continue
            
            # Hakem aynı saatte başka maçta mı?
            has_conflict = False
            for assigned_match in referee_assignments[referee]:
                if assigned_match.get("scheduled_time") == match_time:
                    has_conflict = True
                    break
            
            if has_conflict:
                continue
            
            # En az atama yapılan hakemi seç (dengeli dağıtım)
            if len(referee_assignments[referee]) < min_assignments:
                min_assignments = len(referee_assignments[referee])
                best_referee = referee
        
        if best_referee:
            match["referee_id"] = best_referee
            referee_assignments[best_referee].append(match)
    
    return matches

# ================== DATABASE HELPER ==================

# Bu fonksiyon server.py'den import edilecek
db = None

def set_database(database):
    global db
    db = database

# ================== ENDPOINTS ==================

@event_management_router.get("/{event_id}/overview")
async def get_event_management_overview(event_id: str, current_user: dict = None):
    """Etkinlik yönetim genel görünümü"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Grupları al
    groups = await db.event_groups.find({"event_id": event_id}).to_list(100)
    
    # Maçları al
    matches = await db.event_matches.find({"event_id": event_id}).to_list(500)
    
    # İstatistikler
    stats = {
        "total_participants": event.get("participant_count", 0),
        "total_groups": len(groups),
        "total_matches": len(matches),
        "completed_matches": len([m for m in matches if m.get("status") == "completed"]),
        "pending_matches": len([m for m in matches if m.get("status") == "scheduled"]),
        "in_progress_matches": len([m for m in matches if m.get("status") == "in_progress"]),
    }
    
    return {
        "event": event,
        "groups": groups,
        "stats": stats,
        "settings": event.get("tournament_settings", {})
    }

@event_management_router.post("/{event_id}/settings")
async def save_tournament_settings(event_id: str, request: Request, current_user: dict = None):
    """Turnuva ayarlarını kaydet"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Request body'yi al
    request_body = await request.json()
    
    # request_body'den settings oluştur - TÜM ALANLARI KAYDET
    settings_dict = {
        "event_id": event_id,
        "group_count": request_body.get("group_count"),
        "match_system": request_body.get("match_system", "round_robin"),
        "court_count": request_body.get("court_count", 1),
        "court_layout": request_body.get("court_layout", "1x1"),
        "match_duration_minutes": request_body.get("match_duration_minutes", 30),
        "break_between_matches_minutes": request_body.get("break_between_matches_minutes", 10),
        "start_time": request_body.get("start_time"),
        "auto_referee_assignment": request_body.get("auto_referee_assignment", False),
        "auto_court_assignment": request_body.get("auto_court_assignment", True),
        # Oyuncu ayarları
        "players_can_start_matches": request_body.get("players_can_start_matches", False),
        "in_group_refereeing": request_body.get("in_group_refereeing", False),
        # Maç Sıralaması Ayarları
        "scheduling_event_types": request_body.get("scheduling_event_types", ["open"]),
        "scheduling_genders": request_body.get("scheduling_genders", ["all"]),
        "scheduling_age_groups": request_body.get("scheduling_age_groups", []),
        "elimination_after_groups": request_body.get("elimination_after_groups", True),
        "allow_early_elimination": request_body.get("allow_early_elimination", False),
        "consolation_bracket": request_body.get("consolation_bracket", False),
        "optimize_match_times": request_body.get("optimize_match_times", True),
        "prevent_player_overlap": request_body.get("prevent_player_overlap", True),
        "min_rest_between_matches": request_body.get("min_rest_between_matches", 10),
        "prioritize_seeded_players": request_body.get("prioritize_seeded_players", True),
        "balance_court_usage": request_body.get("balance_court_usage", True),
        "updated_at": datetime.utcnow()
    }
    
    await db.events.update_one(
        {"id": event_id},
        {"$set": {"tournament_settings": settings_dict}}
    )
    
    return {"status": "success", "message": "Ayarlar kaydedildi", "settings": settings_dict}

# ================== HAKEM YÖNETİMİ ==================

@event_management_router.get("/{event_id}/referees")
async def get_event_referees(event_id: str):
    """Etkinliğe atanmış hakemleri getir"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    referees = event.get("referees", [])
    return {"referees": referees}

@event_management_router.post("/{event_id}/referees")
async def add_referee_to_event(event_id: str, request: Request):
    """Etkinliğe hakem ekle"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    data = await request.json()
    user_id = data.get("user_id")
    name = data.get("name", "")
    avatar = data.get("avatar")
    referee_level = data.get("referee_level", "Bölgesel")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id gerekli")
    
    # Hakem zaten ekli mi kontrol et
    existing_referees = event.get("referees", [])
    if any(r.get("id") == user_id for r in existing_referees):
        raise HTTPException(status_code=400, detail="Hakem zaten etkinliğe ekli")
    
    new_referee = {
        "id": user_id,
        "name": name,
        "avatar": avatar,
        "referee_level": referee_level,
        "added_at": datetime.utcnow().isoformat()
    }
    
    await db.events.update_one(
        {"id": event_id},
        {"$push": {"referees": new_referee}}
    )
    
    return {"status": "success", "message": "Hakem eklendi", "referee": new_referee}

@event_management_router.delete("/{event_id}/referees/{referee_id}")
async def remove_referee_from_event(event_id: str, referee_id: str):
    """Etkinlikten hakem çıkar"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Hakemi çıkar
    await db.events.update_one(
        {"id": event_id},
        {"$pull": {"referees": {"id": referee_id}}}
    )
    
    return {"status": "success", "message": "Hakem çıkarıldı"}

# ================== GRUP YÖNETİMİ ==================

# Oyun türü ve cinsiyet eşleştirmeleri
GAME_TYPE_LABELS = {
    "open": "Açık",
    "tek": "Tek",
    "single": "Tek",
    "singles": "Tek",
    "cift": "Çift",
    "double": "Çift",
    "doubles": "Çift",
    "karisik_cift": "Karışık Çift",
    "mixed_double": "Karışık Çift",
    "mixed_doubles": "Karışık Çift",
    "takim": "Takım",
    "team": "Takım"
}

GENDER_LABELS = {
    "Erkekler": "Erkekler",
    "Kadınlar": "Kadınlar",
    "male": "Erkekler",
    "female": "Kadınlar",
    "men": "Erkekler",
    "women": "Kadınlar",
    "Erkek": "Erkekler",
    "Kadın": "Kadınlar"
}

def get_category_name(gender: str, game_type: str) -> str:
    """Kategori adı oluştur: Erkekler Tek, Kadınlar Çift vb."""
    gender_label = GENDER_LABELS.get(gender, gender)
    game_label = GAME_TYPE_LABELS.get(game_type, game_type)
    
    # Açık kategoride cinsiyet belirtilmez
    if game_type in ["open", "açık"]:
        return "Açık"
    
    # Karışık çift'te cinsiyet belirtilmez
    if game_type in ["karisik_cift", "mixed_double", "mixed_doubles"]:
        return "Karışık Çift"
    
    return f"{gender_label} {game_label}"

async def get_participant_details(db, participant_ids: List[str]) -> Dict[str, dict]:
    """Katılımcı detaylarını toplu olarak al"""
    participants = {}
    users = await db.users.find({"id": {"$in": participant_ids}}).to_list(len(participant_ids))
    for user in users:
        participants[user["id"]] = {
            "id": user["id"],
            "name": user.get("full_name", "Bilinmeyen"),
            "gender": user.get("gender", "unknown"),
            "city": user.get("city"),
            "avatar": user.get("profile_image")
        }
    return participants

async def create_pairs_from_participants(
    db,
    event_uuid: str,
    participant_ids: List[str],
    game_type: str,  # "cift" veya "karisik_cift"
    exclude_singles: bool = True  # Eşi olmayanları hariç tut
) -> List[dict]:
    """
    Katılımcıları çift olarak grupla.
    Partner eşleştirmesine göre çiftleri oluştur.
    Alfabetik sıraya göre isimlendirme yap.
    
    Çiftin yaş grubu: İki oyuncudan DAHA GENÇ olanın yaş grubuna göre belirlenir.
    
    exclude_singles=True olduğunda, eşi olmayan oyuncular gruba dahil edilmez.
    
    Returns: [{"pair_id": "...", "player1_id": "...", "player2_id": "...", "pair_name": "Ahmet - Mehmet", "pair_age_group": 40}, ...]
    """
    from datetime import datetime
    current_year = datetime.now().year
    
    # Yaş aralıkları tanımı
    age_ranges = {
        30: (30, 39),
        40: (40, 49),
        50: (50, 59),
        60: (60, 64),
        65: (65, 69),
        70: (70, 74),
        75: (75, 200)  # 75 ve üzeri
    }
    
    def get_age_group(birth_year):
        """Doğum yılından yaş grubunu hesapla"""
        if not birth_year:
            return None
        try:
            age = current_year - int(birth_year)
            for bracket in sorted(age_ranges.keys()):
                min_age, max_age = age_ranges[bracket]
                if min_age <= age <= max_age:
                    return bracket
            return None
        except:
            return None
    
    # event_participants'tan partner bilgilerini al
    eps = await db.event_participants.find({
        "event_id": event_uuid,
        "user_id": {"$in": participant_ids}
    }).to_list(1000)
    
    ep_map = {ep["user_id"]: ep for ep in eps}
    
    # Kullanıcı isimlerini al
    users = await db.users.find({"id": {"$in": participant_ids}}).to_list(1000)
    users_map = {u["id"]: u for u in users}
    
    # Partner alanını belirle
    partner_field = "doubles_partner_id" if game_type in ["cift", "double", "doubles"] else "mixed_partner_id"
    
    pairs = []
    processed_ids = set()
    skipped_singles = []  # Eşi olmayan oyuncular (loglama için)
    
    for pid in participant_ids:
        if pid in processed_ids:
            continue
        
        ep = ep_map.get(pid, {})
        partner_id = ep.get(partner_field)
        
        if partner_id and partner_id in participant_ids and partner_id not in processed_ids:
            # Çift bulundu
            user1 = users_map.get(pid, {})
            user2 = users_map.get(partner_id, {})
            
            name1 = user1.get("full_name", "Bilinmeyen")
            name2 = user2.get("full_name", "Bilinmeyen")
            
            # Yaş gruplarını hesapla
            birth_year1 = user1.get("birth_year") or user1.get("birthYear")
            birth_year2 = user2.get("birth_year") or user2.get("birthYear")
            
            age_group1 = get_age_group(birth_year1)
            age_group2 = get_age_group(birth_year2)
            
            # Çiftin yaş grubu: DAHA GENÇ oyuncunun yaş grubu (daha düşük yaş grubu = daha genç)
            # Örnek: 40+ ve 50+ -> Çift 40+ grubunda
            pair_age_group = None
            if age_group1 and age_group2:
                pair_age_group = min(age_group1, age_group2)  # Daha genç olan
                if age_group1 != age_group2:
                    logging.info(f"🎾 Çift yaş grubu belirlendi: {name1} ({age_group1}+) ve {name2} ({age_group2}+) -> Çift yaş grubu: {pair_age_group}+ (genç oyuncuya göre)")
            elif age_group1:
                pair_age_group = age_group1
            elif age_group2:
                pair_age_group = age_group2
            
            # Alfabetik sıralama
            if name1 > name2:
                name1, name2 = name2, name1
                pid, partner_id = partner_id, pid
            
            pair_name = f"{name1} - {name2}"
            pair_id = f"{min(pid, partner_id)}_{max(pid, partner_id)}"
            
            pairs.append({
                "pair_id": pair_id,
                "player1_id": pid,
                "player2_id": partner_id,
                "pair_name": pair_name,
                "player1_name": name1,
                "player2_name": name2,
                "pair_age_group": pair_age_group,
                "player1_age_group": age_group1,
                "player2_age_group": age_group2
            })
            
            processed_ids.add(pid)
            processed_ids.add(partner_id)
        else:
            # Partneri olmayan veya partner listede değil
            user = users_map.get(pid, {})
            name = user.get("full_name", "Bilinmeyen")
            
            if exclude_singles:
                # Eşi olmayanları hariç tut, sadece logla
                skipped_singles.append(name)
                processed_ids.add(pid)
            else:
                # Eski davranış - tek başına ekle
                birth_year = user.get("birth_year") or user.get("birthYear")
                age_group = get_age_group(birth_year)
                
                pairs.append({
                    "pair_id": pid,
                    "player1_id": pid,
                    "player2_id": None,
                    "pair_name": f"{name} (Partner Yok)",
                    "player1_name": name,
                    "player2_name": None,
                    "pair_age_group": age_group,
                    "player1_age_group": age_group,
                    "player2_age_group": None
                })
                processed_ids.add(pid)
    
    if skipped_singles:
        logging.info(f"⚠️ Eşi olmayan {len(skipped_singles)} oyuncu gruplara dahil edilmedi: {', '.join(skipped_singles[:10])}{'...' if len(skipped_singles) > 10 else ''}")
    
    # Çift isimlerine göre alfabetik sırala
    pairs.sort(key=lambda x: x["pair_name"])
    
    return pairs

async def categorize_participants(
    db, 
    event: dict, 
    participant_ids: List,
    gender_filter: List[str] = None,
    age_group_filter: List[int] = None,
    game_type_filter: List[str] = None
) -> Dict[str, List[str]]:
    """
    Katılımcıları cinsiyet, yaş grubu ve oyun türüne göre kategorilere ayır
    
    Filtre parametreleri:
    - gender_filter: ['male', 'female'] - Sadece bu cinsiyetleri dahil et
    - age_group_filter: [30, 40, 50] - Sadece bu yaş gruplarını dahil et
    - game_type_filter: ['tek', 'cift', 'karisik_cift'] - Sadece bu oyun türlerini dahil et
    """
    from datetime import datetime
    
    # Participant ID'lerini normalize et (dict formatından string formatına)
    normalized_ids = []
    for pid in participant_ids:
        if isinstance(pid, dict):
            normalized_ids.append(pid.get("id", str(pid)))
        elif isinstance(pid, str):
            normalized_ids.append(pid)
        else:
            normalized_ids.append(str(pid))
    
    participant_ids = normalized_ids
    
    # Etkinlik ayarlarını al
    event_genders = event.get("genders", [])  # ['Erkekler', 'Kadınlar']
    event_game_types = event.get("game_types", [])  # ['tek', 'cift', 'karisik_cift']
    event_uuid = event.get("id", "")
    
    # Katılımcı detaylarını al (users koleksiyonundan)
    users = await db.users.find({"id": {"$in": participant_ids}}).to_list(1000)
    users_map = {u["id"]: u for u in users}
    
    # event_participants koleksiyonundan kayıtları al
    event_participants = await db.event_participants.find({"event_id": event_uuid}).to_list(1000)
    ep_map = {ep["user_id"]: ep for ep in event_participants}
    
    logging.info(f"📋 Kategorilendirme: {len(participant_ids)} katılımcı, filtreler: gender={gender_filter}, age={age_group_filter}, game_type={game_type_filter}")
    
    # Filtreleri uygula
    current_year = datetime.now().year
    
    # Kategori bazlı katılımcı listesi
    categories: Dict[str, List[str]] = {}
    
    # Oyun türlerini belirle - filtre varsa onu kullan, yoksa event'ten al
    active_game_types = game_type_filter if game_type_filter else event_game_types
    if not active_game_types:
        active_game_types = ["tek"]  # Varsayılan
    
    # OPEN modu: Etkinlik sadece "open" türündeyse ve filtre yoksa
    # TÜM oyuncuları tek bir "Açık" kategorisine koy
    # VEYA game_type_filter = ["open"] ise de open modda çalış
    is_open_mode = (
        "open" in event_game_types and 
        len(event_game_types) == 1 and
        not gender_filter and 
        not age_group_filter and
        not game_type_filter
    ) or (
        game_type_filter and 
        len(game_type_filter) == 1 and 
        "open" in game_type_filter
    )
    
    # Çift eleme veya eleme sistemi için de tüm oyuncuları tek kategoride grupla
    match_system = event.get("tournament_settings", {}).get("match_system", "")
    is_elimination_mode = match_system in ["double_elimination", "single_elimination", "swiss"]
    
    # Ayrıca game_types boşsa veya tanımsızsa da açık mod gibi davran
    is_no_game_types = not event_game_types or len(event_game_types) == 0
    
    if is_open_mode or (is_elimination_mode and not gender_filter and not age_group_filter and not game_type_filter) or (is_no_game_types and not gender_filter and not age_group_filter and not game_type_filter):
        logging.info(f"🌐 OPEN/ELIMINATION MODE: Tüm {len(participant_ids)} oyuncu tek kategoride gruplanacak (match_system={match_system}, game_types={event_game_types})")
        categories["Açık Kategori"] = list(participant_ids)
        return categories
    
    for pid in participant_ids:
        user = users_map.get(pid, {})
        ep = ep_map.get(pid, {})
        
        # Kullanıcı bilgilerini al
        user_gender = user.get("gender", "").lower()
        birth_year = user.get("birth_year") or user.get("birthYear")
        
        # birth_year yoksa date_of_birth'tan çıkar
        if not birth_year and user.get("date_of_birth"):
            dob = user.get("date_of_birth")
            if isinstance(dob, str):
                try:
                    birth_year = int(dob[:4])  # "1974-02-21T00:00:00.000Z" -> 1974
                except:
                    pass
        
        user_game_types = ep.get("game_types", [])
        
        # Cinsiyet filtresini uygula
        if gender_filter:
            if user_gender in ["erkek", "male", "m"]:
                if "male" not in gender_filter:
                    continue
            elif user_gender in ["kadın", "female", "f", "kadin"]:
                if "female" not in gender_filter:
                    continue
            else:
                continue  # Cinsiyet belirli değilse atla
        
        # Yaş grubu filtresini uygula
        # Yaş aralıkları: 30-39, 40-49, 50-59, 60-64, 65-69, 70-74, 75+
        # ÖNEMLİ: Çiftler için, eşleşmiş çiftin GENÇ oyuncusunun yaş grubuna göre filtrelenmeli
        # ÖNEMLİ: Her yaş grubu KENDİ ARALIĞINI temsil eder (50+ = 50-59, 60+ = 60-64, vb.)
        if age_group_filter:
            # birth_year yoksa bu kullanıcıyı atla (yaş belirlenemez)
            if not birth_year:
                logging.info(f"⚠️ YAŞ FİLTRE: {user.get('full_name', '?')} - birth_year YOK, atlanıyor")
                continue
            
            try:
                age = current_year - int(birth_year)
                
                # Yaş aralıkları tanımla (alt sınır, üst sınır)
                age_ranges = {
                    30: (30, 39),
                    40: (40, 49),
                    50: (50, 59),
                    60: (60, 64),
                    65: (65, 69),
                    70: (70, 74),
                    75: (75, 999)  # 75+ üst sınır yok
                }
                
                # Kullanıcının yaş grubu (SADECE KENDI ARALIĞINDA)
                user_age_bracket = None
                for bracket, (min_age, max_age) in sorted(age_ranges.items()):
                    if min_age <= age <= max_age:
                        user_age_bracket = bracket
                        break
                
                # Bu kullanıcının çift eşi var mı? Eşinin yaş grubunu da kontrol et
                partner_id = ep.get("doubles_partner_id") or ep.get("mixed_partner_id")
                partner_age_bracket = None
                
                if partner_id:
                    partner_user = users_map.get(partner_id, {})
                    partner_birth_year = partner_user.get("birth_year") or partner_user.get("birthYear")
                    if partner_birth_year:
                        try:
                            partner_age = current_year - int(partner_birth_year)
                            for bracket, (min_age, max_age) in sorted(age_ranges.items()):
                                if min_age <= partner_age <= max_age:
                                    partner_age_bracket = bracket
                                    break
                        except:
                            pass
                
                # Çiftin yaş grubu: genç olanın (düşük bracket) yaş grubu
                pair_age_bracket = user_age_bracket
                if partner_age_bracket and user_age_bracket:
                    pair_age_bracket = min(user_age_bracket, partner_age_bracket)
                elif partner_age_bracket:
                    pair_age_bracket = partner_age_bracket
                
                # Kullanıcının yaş grubu seçilen yaş gruplarından birine TAM OLARAK uyuyor mu?
                # NOT: 50+ filtresi = sadece 50 bracket (50-59 yaş arası), 60+ içermez!
                matches_age = False
                
                # Bireysel yaş grubunu kontrol et (tekler için)
                if user_age_bracket and user_age_bracket in age_group_filter:
                    matches_age = True
                
                # Çiftler için: çiftin (genç olan) yaş grubunu da kontrol et
                if pair_age_bracket and pair_age_bracket in age_group_filter:
                    matches_age = True
                
                # Debug log
                user_name = user.get("full_name", "?")
                if not matches_age:
                    logging.info(f"❌ YAŞ FİLTRE: {user_name} ({age} yaş, bracket={user_age_bracket}) filtre={age_group_filter} - DIŞLANDI")
                    continue
                else:
                    logging.info(f"✅ YAŞ FİLTRE: {user_name} ({age} yaş, bracket={user_age_bracket}) filtre={age_group_filter} - DAHİL")
            except Exception as e:
                logging.error(f"Yaş filtre hatası: {e}")
                pass  # Yaş hesaplanamadıysa atla
        
        # Oyun türü filtresini uygula
        if game_type_filter:
            if not user_game_types:
                continue
            # Kullanıcının oyun türleri ile filtre arasında kesişim var mı?
            if not any(gt in user_game_types for gt in game_type_filter):
                continue
        
        # Cinsiyeti Türkçeye çevir
        if user_gender in ["erkek", "male", "m"]:
            gender_text = "Erkekler"
        elif user_gender in ["kadın", "female", "f", "kadin"]:
            gender_text = "Kadınlar"
        else:
            gender_text = "Karma"
        
        # Yaş grubunu belirle (aralıklara göre)
        age_group_text = ""
        user_age_group = None
        if birth_year:
            try:
                age = current_year - int(birth_year)
                # Yaş aralıklarına göre yaş grubunu belirle
                age_ranges = {
                    30: (30, 39),
                    40: (40, 49),
                    50: (50, 59),
                    60: (60, 64),
                    65: (65, 69),
                    70: (70, 74),
                    75: (75, 999)
                }
                for bracket, (min_age, max_age) in sorted(age_ranges.items(), reverse=True):
                    if min_age <= age <= max_age:
                        user_age_group = bracket
                        break
                
                # ÖNEMLI: Eğer yaş filtresi varsa, kategori adı için FİLTRE değerini kullan
                # Bu sayede 60 yaşındaki bir oyuncu 50+ filtresinden geçmişse, 50+ kategorisine dahil olur
                if age_group_filter and len(age_group_filter) == 1:
                    # Tek bir yaş grubu filtresi seçilmişse, o yaş grubunu kullan
                    age_group_text = f"{age_group_filter[0]}+"
                elif user_age_group:
                    age_group_text = f"{user_age_group}+"
            except:
                pass
        
        # Her oyun türü için kategori oluştur
        for game_type in active_game_types:
            # Kullanıcı bu oyun türüne kayıtlı mı?
            if user_game_types and game_type not in user_game_types:
                continue
            
            # Oyun türü metnini belirle
            if game_type in ["tek", "single"]:
                game_text = "Tekler"
            elif game_type in ["cift", "double", "doubles"]:
                game_text = "Çiftler"
            elif game_type in ["karisik_cift", "mixed", "mixed_doubles"]:
                game_text = "Karışık Çift"
            else:
                game_text = game_type.capitalize()
            
            # ÇİFTLER İÇİN ÖZEL MANTIK:
            # Çift oyun türlerinde, çiftin yaş grubu = GENÇ OYUNCUNUN yaş grubu
            final_age_group_text = age_group_text
            final_age_group = user_age_group
            
            if game_type in ["cift", "double", "doubles", "karisik_cift", "mixed", "mixed_doubles"]:
                partner_id = ep.get("doubles_partner_id") if game_type in ["cift", "double", "doubles"] else ep.get("mixed_partner_id")
                
                if partner_id:
                    partner_user = users_map.get(partner_id, {})
                    partner_birth_year = partner_user.get("birth_year") or partner_user.get("birthYear")
                    
                    if partner_birth_year and birth_year:
                        try:
                            user_age = current_year - int(birth_year)
                            partner_age = current_year - int(partner_birth_year)
                            
                            # Her iki oyuncunun yaş gruplarını hesapla
                            def get_age_bracket(age):
                                age_ranges = {
                                    30: (30, 39),
                                    40: (40, 49),
                                    50: (50, 59),
                                    60: (60, 64),
                                    65: (65, 69),
                                    70: (70, 74),
                                    75: (75, 999)
                                }
                                for bracket, (min_age, max_age) in sorted(age_ranges.items()):
                                    if min_age <= age <= max_age:
                                        return bracket
                                return None
                            
                            user_bracket = get_age_bracket(user_age)
                            partner_bracket = get_age_bracket(partner_age)
                            
                            # Genç olanın (düşük bracket) yaş grubunu kullan
                            if user_bracket and partner_bracket:
                                pair_bracket = min(user_bracket, partner_bracket)
                                final_age_group = pair_bracket
                                final_age_group_text = f"{pair_bracket}+"
                                
                                if user_bracket != partner_bracket:
                                    user_name = user.get("full_name", "?")
                                    partner_name = partner_user.get("full_name", "?")
                                    logging.info(f"🎾 Çift yaş grubu düzeltmesi: {user_name} ({user_bracket}+) + {partner_name} ({partner_bracket}+) -> Kategori: {pair_bracket}+")
                        except:
                            pass
            
            # Kategori adı oluştur
            parts = [game_text, gender_text]
            if final_age_group_text:
                parts.append(final_age_group_text)
            category_name = " - ".join(parts)
            
            if category_name not in categories:
                categories[category_name] = []
            if pid not in categories[category_name]:
                categories[category_name].append(pid)
    
    logging.info(f"📊 Oluşturulan kategoriler: {list(categories.keys())}")
    for cat_name, cat_pids in categories.items():
        logging.info(f"  - {cat_name}: {len(cat_pids)} oyuncu")
    
    return categories

@event_management_router.post("/{event_id}/groups/auto-generate")
async def auto_generate_groups(
    event_id: str, 
    group_count_per_category: Optional[int] = Query(None, alias="group_count"),
    players_per_group: Optional[int] = Query(None),
    group_naming: Optional[str] = Query("alphabetic"),  # alphabetic veya numeric
    sort_by_points: Optional[bool] = Query(False),
    # Yeni filtre parametreleri
    selected_genders: Optional[str] = Query(None),  # virgülle ayrılmış: "male,female"
    selected_age_groups: Optional[str] = Query(None),  # virgülle ayrılmış: "30,40,50"
    selected_game_types: Optional[str] = Query(None),  # virgülle ayrılmış: "tek,cift,karisik_cift"
    distribution_mode: Optional[str] = Query("add_players"),  # "add_players" veya "reduce_groups"
    current_user: dict = None
):
    """
    Kategori bazlı grupları otomatik oluştur
    
    Yeni Parametreler:
    - selected_genders: Seçilen cinsiyetler (virgülle ayrılmış)
    - selected_age_groups: Seçilen yaş grupları (virgülle ayrılmış)
    - selected_game_types: Seçilen oyun türleri (virgülle ayrılmış)
    - distribution_mode: "add_players" (fazla oyuncuları gruplara ekle) veya "reduce_groups" (grup sayısını azalt)
    
    Lig sistemi parametreleri:
    - players_per_group: Grup başına oyuncu sayısı
    - group_naming: "alphabetic" (A,B,C) veya "numeric" (1,2,3)
    - sort_by_points: True ise oyuncuları puanlarına göre sırala
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Katılımcıları al
    participants = event.get("participants", [])
    if not participants:
        raise HTTPException(status_code=400, detail="Etkinlikte katılımcı yok")
    
    # Parse filter parameters
    gender_filter = selected_genders.split(",") if selected_genders else None
    age_group_filter = [int(x) for x in selected_age_groups.split(",") if x.isdigit()] if selected_age_groups else None
    game_type_filter = selected_game_types.split(",") if selected_game_types else None
    
    logging.info(f"🎯 Grup oluşturma filtreleri: gender={gender_filter}, age={age_group_filter}, game_type={game_type_filter}")
    
    # NOT: Mevcut grupları SİLMİYORUZ - yeni gruplar ekleniyor
    # Eğer kullanıcı tüm grupları silmek isterse "Tümünü Sil" butonunu kullanmalı
    
    # Katılımcıları kategorilere ayır (filtrelerle birlikte)
    categories = await categorize_participants(
        db, event, participants, 
        gender_filter=gender_filter,
        age_group_filter=age_group_filter,
        game_type_filter=game_type_filter
    )
    
    if not categories:
        raise HTTPException(status_code=400, detail="Kategori oluşturulamadı - katılımcı bilgileri eksik")
    
    all_groups = []
    category_summary = []
    
    # Event UUID'sini al
    event_uuid = event.get("id", event_id)
    
    for category_name, category_participants in categories.items():
        if not category_participants:
            continue
        
        # Kategorinin çift mi tek mi olduğunu belirle
        is_doubles = "Çiftler" in category_name or "Karışık" in category_name
        game_type_for_pairs = "cift" if "Çiftler" in category_name else "karisik_cift" if "Karışık" in category_name else None
        
        if is_doubles and game_type_for_pairs:
            # Çift kategorisi - partnerleri birleştir
            pairs = await create_pairs_from_participants(db, event_uuid, category_participants, game_type_for_pairs)
            
            # Çiftleri yaş gruplarına göre kategorilere ayır
            # Çiftin yaş grubu = GENÇ oyuncunun yaş grubu (pair_age_group)
            pairs_by_age_group: Dict[int, List] = {}
            for pair in pairs:
                pair_age = pair.get("pair_age_group")
                if pair_age:
                    if pair_age not in pairs_by_age_group:
                        pairs_by_age_group[pair_age] = []
                    pairs_by_age_group[pair_age].append(pair)
                else:
                    # Yaş grubu belirlenememiş çiftler "0" grubuna
                    if 0 not in pairs_by_age_group:
                        pairs_by_age_group[0] = []
                    pairs_by_age_group[0].append(pair)
            
            # Her yaş grubu için ayrı gruplar oluştur
            for age_group_key, age_group_pairs in sorted(pairs_by_age_group.items()):
                if not age_group_pairs:
                    continue
                
                participant_count = len(age_group_pairs)
                
                # Yaş grubu için kategori adını belirle
                if age_group_key and age_group_key > 0:
                    age_category_name = category_name.replace("+", "").strip()
                    # Kategori adında yaş grubu varsa güncelle, yoksa ekle
                    import re
                    if re.search(r'\d+\+', category_name):
                        # Mevcut yaş grubunu yenisiyle değiştir
                        age_category_name = re.sub(r'\d+\+', f'{age_group_key}+', category_name)
                    else:
                        # Yaş grubu yoksa ekle
                        if "Çiftler" in category_name or "Karışık" in category_name:
                            parts = category_name.split(" - ")
                            if len(parts) >= 1:
                                parts.insert(1, f"{age_group_key}+")
                                age_category_name = " - ".join(parts)
                            else:
                                age_category_name = f"{category_name} - {age_group_key}+"
                        else:
                            age_category_name = f"{category_name} - {age_group_key}+"
                else:
                    age_category_name = category_name
                
                # Çift kategorilerinde players_per_group aslında ÇİFT SAYISI olarak kullanılır
                pairs_per_group_target = players_per_group if players_per_group else 4
                
                # Grup sayısını hesapla (çift sayısına göre)
                if players_per_group and players_per_group > 0:
                    num_groups = max(1, math.ceil(participant_count / pairs_per_group_target))
                elif group_count_per_category:
                    num_groups = group_count_per_category
                else:
                    num_groups = calculate_optimal_group_count(participant_count)
                
                logging.info(f"🎾 Çift kategorisi ({age_group_key}+ yaş): {participant_count} çift, grup başına {pairs_per_group_target} çift hedefi, {num_groups} grup oluşturulacak")
                
                # ========== ÇİFTLER İÇİN PUAN TABANLI SERİ BAŞI DAĞITIMI ==========
                # Her çiftin puanını hesapla (iki oyuncunun puanlarının toplamı)
                pair_points = []
                for pair in age_group_pairs:
                    p1_id = pair["player1_id"]
                    p2_id = pair["player2_id"]
                    
                    # Her iki oyuncunun puanlarını al
                    p1_point_doc = await db.event_athlete_points.find_one({"event_id": event_id, "participant_id": p1_id})
                    p2_point_doc = await db.event_athlete_points.find_one({"event_id": event_id, "participant_id": p2_id})
                    
                    p1_points = float(p1_point_doc.get("points", 0)) if p1_point_doc else 0.0
                    p2_points = float(p2_point_doc.get("points", 0)) if p2_point_doc else 0.0
                    
                    total_points = p1_points + p2_points
                    pair_points.append((pair, total_points))
                
                # Puana göre sırala (yüksekten düşüğe)
                pair_points.sort(key=lambda x: x[1], reverse=True)
                sorted_pairs = [p[0] for p in pair_points]
                
                logging.info(f"📊 Çift puanları (yüksekten düşüğe):")
                for i, (pair, pts) in enumerate(pair_points[:5]):  # İlk 5 çifti göster
                    logging.info(f"  {i+1}. {pair['pair_name']}: {pts} puan")
                
                # Seri başı sayısı = grup sayısı
                num_seeds = min(num_groups, len(sorted_pairs))
                
                # En yüksek puanlı çiftler seri başı
                seeded_pairs = sorted_pairs[:num_seeds]
                non_seeded_pairs = sorted_pairs[num_seeds:]
                
                logging.info(f"🌟 {num_seeds} seri başı çift (puana göre otomatik):")
                for i, pair in enumerate(seeded_pairs):
                    pts = next((p[1] for p in pair_points if p[0] == pair), 0)
                    logging.info(f"   Seed #{i+1}: {pair['pair_name']} ({pts} puan)")
                
                # Grupları hazırla
                group_distributions = [[] for _ in range(num_groups)]
                
                # 1. Adım: Seri başı çiftleri farklı gruplara dağıt
                for idx, pair in enumerate(seeded_pairs):
                    group_idx = idx % num_groups
                    group_distributions[group_idx].append(pair)
                    group_letter = chr(65 + group_idx) if group_naming != "numeric" else str(group_idx + 1)
                    logging.info(f"  🌟 Seri başı #{idx+1} {pair['pair_name']} → Grup {group_letter}")
                
                # 2. Adım: Geri kalan çiftleri rastgele dağıt
                random.shuffle(non_seeded_pairs)
                non_seeded_idx = 0
                
                # Grup başına çift sayısı
                pairs_per_group = pairs_per_group_target if pairs_per_group_target else math.ceil(participant_count / num_groups)
                
                for group_idx in range(num_groups):
                    current_count = len(group_distributions[group_idx])
                    needed = pairs_per_group - current_count
                    
                    for _ in range(needed):
                        if non_seeded_idx < len(non_seeded_pairs):
                            group_distributions[group_idx].append(non_seeded_pairs[non_seeded_idx])
                            non_seeded_idx += 1
                
                # Kalan çiftleri de dağıt
                while non_seeded_idx < len(non_seeded_pairs):
                    for group_idx in range(num_groups):
                        if non_seeded_idx >= len(non_seeded_pairs):
                            break
                        if len(group_distributions[group_idx]) < pairs_per_group + 1:
                            group_distributions[group_idx].append(non_seeded_pairs[non_seeded_idx])
                            non_seeded_idx += 1
                
                # Alt gruplara kaydet
                for i in range(num_groups):
                    group_pairs = group_distributions[i]
                    
                    if not group_pairs:
                        continue
                    
                    # Grup adı
                    if num_groups > 1:
                        if group_naming == "numeric":
                            group_suffix = str(i + 1)
                        else:
                            group_suffix = chr(65 + i)
                        group_name = f"{age_category_name} - Grup {group_suffix}"
                    else:
                        group_name = age_category_name
                    
                    # Çiftlerden participant_ids oluştur (her iki oyuncuyu da ekle)
                    group_participant_ids = []
                    pair_data = []
                    for pair in group_pairs:
                        group_participant_ids.append(pair["player1_id"])
                        if pair["player2_id"]:
                            group_participant_ids.append(pair["player2_id"])
                        pair_data.append({
                            "pair_id": pair["pair_id"],
                            "pair_name": pair["pair_name"],
                            "player1_id": pair["player1_id"],
                            "player2_id": pair["player2_id"],
                            "pair_age_group": pair.get("pair_age_group")
                        })
                    
                    group = {
                        "id": str(uuid.uuid4()),
                        "event_id": event_id,
                        "category": age_category_name,
                        "name": group_name,
                        "participant_ids": group_participant_ids,
                        "pairs": pair_data,  # Çift bilgilerini sakla
                        "is_doubles": True,
                        "age_group": age_group_key if age_group_key > 0 else None,
                        "match_system": event.get("tournament_settings", {}).get("match_system", "round_robin"),
                        "status": "pending",
                        "bye_participant_id": None,
                        "sort_order": len(all_groups),
                        "created_at": datetime.now(),
                        "updated_at": datetime.now()
                    }
                    
                    await db.event_groups.insert_one(group)
                    all_groups.append(group)
                
                category_summary.append({
                    "category": age_category_name,
                    "participant_count": participant_count,  # Çift sayısı
                    "group_count": min(num_groups, participant_count),
                    "is_doubles": True,
                    "age_group": age_group_key if age_group_key > 0 else None
                })
            
            continue  # Çift kategorisi işlendi, döngünün geri kalanını atla
        else:
            # Tek kategorisi - normal işlem
            participant_count = len(category_participants)
        
        # Grup sayısını hesapla
        if players_per_group and players_per_group > 0:
            # Lig sistemi: grup başına oyuncu sayısına göre hesapla
            num_groups = math.ceil(participant_count / players_per_group)
        elif group_count_per_category:
            num_groups = group_count_per_category
        else:
            num_groups = calculate_optimal_group_count(participant_count)
        
        # Katılımcıları puanlarına göre sırala (her zaman)
        # Puanlar sporcular sayfasından gelir (event_athlete_points tablosu)
        participant_points = []
        for pid in category_participants:
            # event_athlete_points tablosundan puan al - participant_id ile ara
            athlete_point = await db.event_athlete_points.find_one({"event_id": event_id, "participant_id": pid})
            points = float(athlete_point.get("points", 0)) if athlete_point else 0.0
            
            # Kullanıcı adını da al (debug için)
            user = await db.users.find_one({"id": pid})
            user_name = user.get("full_name", "Bilinmeyen") if user else "Bilinmeyen"
            
            participant_points.append((pid, points, user_name))
        
        # Puana göre sırala (yüksekten düşüğe - en yüksek puanlı seri başı olacak)
        participant_points.sort(key=lambda x: x[1], reverse=True)
        sorted_participants = [p[0] for p in participant_points]
        
        logging.info(f"📊 Puana göre sıralama (yüksekten düşüğe):")
        for i, (pid, pts, name) in enumerate(participant_points[:10]):  # İlk 10'u göster
            logging.info(f"  {i+1}. {name}: {pts} puan")
        
        # ========== SERİ BAŞI (SEED) DAĞITIMI ==========
        # Seri başları artık OTOMATIK olarak puanlara göre belirlenir
        # En yüksek puanlı oyuncular seri başı olur ve farklı gruplara dağıtılır
        
        # Grup başına katılımcı sayısı
        if players_per_group and players_per_group > 0:
            participants_per_group = players_per_group
        else:
            participants_per_group = math.ceil(participant_count / num_groups)
        
        # ========== PUAN SIRALAMASINA GÖRE GRUPLAMA ==========
        # sort_by_points=True ise: Puan sıralamasına göre grupları doldur
        #   Grup A: En yüksek puanlı N oyuncu
        #   Grup B: Sonraki N oyuncu
        #   ...
        # sort_by_points=False ise: Seri başı (snake draft) dağıtımı
        #   Her gruba 1 seri başı, geri kalanlar rastgele
        
        if sort_by_points:
            # PUAN SIRALAMASINA GÖRE GRUPLAMA
            logging.info(f"📊 PUAN SIRALAMASINA GÖRE GRUPLAMA aktif - Oyuncular puan sırasına göre gruplara dağıtılacak")
            
            # Grupları hazırla - her grup için boş liste
            group_distributions = [[] for _ in range(num_groups)]
            
            # Oyuncuları sırayla gruplara dağıt
            for idx, (pid, points, name) in enumerate(participant_points):
                group_idx = idx // participants_per_group
                
                # Son grubu aşmamak için kontrol
                if group_idx >= num_groups:
                    group_idx = num_groups - 1
                
                group_distributions[group_idx].append(pid)
                group_letter = chr(65 + group_idx) if group_naming != "numeric" else str(group_idx + 1)
                
                if idx < 21:  # İlk 21 oyuncuyu logla
                    logging.info(f"  #{idx+1} {name} ({points:.1f} puan) → Grup {group_letter}")
            
            logging.info(f"✅ Puan sıralamasına göre {num_groups} grup oluşturuldu")
            for i in range(num_groups):
                group_letter = chr(65 + i) if group_naming != "numeric" else str(i + 1)
                logging.info(f"   Grup {group_letter}: {len(group_distributions[i])} oyuncu")
        
        else:
            # SERİ BAŞI (SNAKE DRAFT) DAĞITIMI
            # Seri başları artık OTOMATIK olarak puanlara göre belirlenir
            # En yüksek puanlı oyuncular seri başı olur ve farklı gruplara dağıtılır
            logging.info(f"🎯 SERİ BAŞI DAĞITIMI aktif - En yüksek puanlılar farklı gruplara dağıtılacak")
            
            # Seri başı sayısı = grup sayısı (her gruba 1 seri başı)
            num_seeds = min(num_groups, len(sorted_participants))
            
            # En yüksek puanlı oyuncular seri başı
            seeded_participants = []
            for i in range(num_seeds):
                pid, points, name = participant_points[i]
                seeded_participants.append({
                    "id": pid,
                    "seed_number": i + 1,
                    "points": points,
                    "name": name
                })
            
            # Seri başı olmayan oyuncular
            non_seeded_participants = sorted_participants[num_seeds:]
            
            if seeded_participants:
                logging.info(f"🌟 {len(seeded_participants)} seri başı (puana göre otomatik):")
                for s in seeded_participants:
                    logging.info(f"   Seed #{s['seed_number']}: {s['name']} ({s['points']} puan)")
            
            # Grupları hazırla - her grup için boş liste
            group_distributions = [[] for _ in range(num_groups)]
            
            # 1. Adım: Seri başlarını gruplara dağıt (her biri farklı gruba, 1. sıraya)
            for idx, seeded in enumerate(seeded_participants):
                group_idx = idx % num_groups  # Döngüsel dağıtım
                group_distributions[group_idx].append(seeded["id"])
                
                group_letter = chr(65 + group_idx) if group_naming != "numeric" else str(group_idx + 1)
                logging.info(f"  🌟 Seri başı #{seeded['seed_number']} {seeded['name']} → Grup {group_letter} (1. sıra)")
            
            # 2. Adım: Geri kalan oyuncuları rastgele dağıt
            random.shuffle(non_seeded_participants)
            non_seeded_idx = 0
            
            for group_idx in range(num_groups):
                current_count = len(group_distributions[group_idx])
                needed = participants_per_group - current_count
                
                for _ in range(needed):
                    if non_seeded_idx < len(non_seeded_participants):
                        group_distributions[group_idx].append(non_seeded_participants[non_seeded_idx])
                        non_seeded_idx += 1
            
            # Kalan oyuncuları da dağıt (grup sayısına tam bölünmezse)
            while non_seeded_idx < len(non_seeded_participants):
                for group_idx in range(num_groups):
                    if non_seeded_idx >= len(non_seeded_participants):
                        break
                    # Maksimum kapasiteyi aşmadan ekle
                    if len(group_distributions[group_idx]) < participants_per_group + 1:
                        group_distributions[group_idx].append(non_seeded_participants[non_seeded_idx])
                        non_seeded_idx += 1
        
        # Alt gruplara kaydet
        for i in range(num_groups):
            # Yeni seed tabanlı dağıtımı kullan
            group_participants = group_distributions[i]
            
            if not group_participants:
                continue
            
            # Grup adı: isimlendirme tipine göre
            if num_groups > 1:
                if group_naming == "numeric":
                    group_suffix = str(i + 1)  # 1, 2, 3...
                else:
                    group_suffix = chr(65 + i)  # A, B, C...
                group_name = f"{category_name} - Grup {group_suffix}"
            else:
                group_name = category_name
            
            group = {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "category": category_name,
                "name": group_name,
                "participant_ids": group_participants,
                "pairs": None,  # Tek kategorisinde çift yok
                "match_system": event.get("tournament_settings", {}).get("match_system", "round_robin"),
                "status": "pending",
                "bye_participant_id": None,
                "is_doubles": False,
                "sort_order": len(all_groups),
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            await db.event_groups.insert_one(group)
            all_groups.append(group)
            
            # Debug: Grup içeriğini logla
            logging.info(f"📦 Grup {group_suffix if num_groups > 1 else ''}: {len(group_participants)} oyuncu")
        
        category_summary.append({
            "category": category_name,
            "participant_count": participant_count,
            "group_count": num_groups,
            "is_doubles": False
        })
    
    # Not: Gruplar artık for döngüsü içinde tek tek kaydediliyor
    # insert_many kullanmıyoruz
    
    # Event'i güncelle
    await db.events.update_one(
        {"id": event_id},
        {"$set": {
            "groups_generated": True, 
            "group_count": len(all_groups),
            "categories": list(categories.keys())
        }}
    )
    
    # Remove MongoDB _id fields before returning
    for group in all_groups:
        group.pop("_id", None)
    
    logging.info(f"✅ Gruplar oluşturuldu: {len(all_groups)} grup, sort_by_points={sort_by_points}, naming={group_naming}")
    
    return {
        "status": "success", 
        "groups": all_groups, 
        "group_count": len(all_groups),
        "category_summary": category_summary,
        "message": f"{len(all_groups)} grup oluşturuldu ({len(categories)} kategori)"
    }

@event_management_router.get("/{event_id}/groups")
async def get_groups(event_id: str, current_user: dict = None):
    """Etkinlik gruplarını getir"""
    global db
    
    groups = await db.event_groups.find({"event_id": event_id}).to_list(100)
    
    # Her grup için katılımcı detaylarını ekle
    for group in groups:
        participant_details = []
        for pid in group.get("participant_ids", []):
            user = await db.users.find_one({"id": pid})
            if user:
                participant_details.append({
                    "id": pid,
                    "name": user.get("full_name", "Bilinmeyen"),
                    "avatar": user.get("profile_image"),
                    "city": user.get("city")
                })
        group["participants"] = participant_details
        
        # Serialize için _id kaldır
        if "_id" in group:
            del group["_id"]
    
    return {"groups": groups}

@event_management_router.put("/{event_id}/groups/{group_id}")
async def update_group(event_id: str, group_id: str, update: GroupUpdate, current_user: dict = None):
    """Grubu güncelle"""
    global db
    
    update_dict = {k: v for k, v in update.dict().items() if v is not None}
    update_dict["updated_at"] = datetime.utcnow()
    
    result = await db.event_groups.update_one(
        {"id": group_id, "event_id": event_id},
        {"$set": update_dict}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    return {"status": "success", "message": "Grup güncellendi"}

# NOT: move-participant endpoint'i aşağıda MoveParticipantRequest modeli ile tanımlı (satır ~2356)
# Bu basit versiyon kaldırıldı, request body kullanan versiyon aktif

# ================== FİKSTÜR YÖNETİMİ ==================

@event_management_router.get("/{event_id}/fixture/preview")
async def preview_fixture(event_id: str, current_user: dict = None):
    """Fikstür önizlemesi - oluşturulmadan önce maç sayısını ve detaylarını göster"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    settings = event.get("tournament_settings", {})
    match_system = settings.get("match_system", "round_robin")
    
    # Grupları al
    groups = await db.event_groups.find({"event_id": event_id}).to_list(100)
    
    # League settings'den eşleşme kurallarını al
    league_settings = await db.league_settings.find_one({"event_id": event_id})
    match_exclusion_enabled = False
    match_exclusion_rules = []
    
    if league_settings:
        match_exclusion_enabled = league_settings.get("match_exclusion_enabled", False)
        match_exclusion_rules = league_settings.get("match_exclusion_rules", [])
    
    # Kullanıcı isimlerini al
    user_ids = set()
    for group in groups:
        user_ids.update(group.get("participant_ids", []))
    
    users = await db.users.find({"id": {"$in": list(user_ids)}}).to_list(500)
    user_map = {u.get("id"): u.get("full_name", "Bilinmeyen") for u in users}
    
    total_matches = 0
    excluded_matches = 0
    group_details = []
    
    for group in groups:
        participants = group.get("participant_ids", [])
        group_system = group.get("match_system", match_system)
        
        # Hariç tutulacak çiftleri belirle
        excluded_pairs = set()
        if match_exclusion_enabled and match_exclusion_rules:
            for rule in match_exclusion_rules:
                rank_a = rule.get("rank_a", 0)
                rank_b = rule.get("rank_b", 0)
                if 1 <= rank_a <= len(participants) and 1 <= rank_b <= len(participants):
                    p_a = participants[rank_a - 1]
                    p_b = participants[rank_b - 1]
                    excluded_pairs.add((p_a, p_b))
                    excluded_pairs.add((p_b, p_a))
        
        # Maç çiftlerini hesapla
        if group_system == "round_robin":
            match_pairs = generate_round_robin_matches(participants.copy())
        elif group_system == "double_round_robin":
            match_pairs = generate_double_round_robin_matches(participants.copy())
        elif group_system == "single_elimination":
            match_pairs = generate_single_elimination_bracket(participants.copy())
        else:
            match_pairs = generate_round_robin_matches(participants.copy())
        
        # Hariç tutulanları say
        group_excluded = 0
        group_matches = 0
        excluded_match_details = []
        
        for p1, p2, round_num in match_pairs:
            if (p1, p2) in excluded_pairs or (p2, p1) in excluded_pairs:
                group_excluded += 1
                excluded_match_details.append({
                    "player1": user_map.get(p1, "Bilinmeyen"),
                    "player2": user_map.get(p2, "Bilinmeyen"),
                    "reason": "Eşleşme kuralı"
                })
            else:
                group_matches += 1
        
        total_matches += group_matches
        excluded_matches += group_excluded
        
        group_details.append({
            "group_name": group.get("name"),
            "participant_count": len(participants),
            "match_count": group_matches,
            "excluded_count": group_excluded,
            "match_system": group_system,
            "excluded_matches": excluded_match_details[:5]  # İlk 5 hariç tutulan maç
        })
    
    return {
        "status": "preview",
        "event_title": event.get("title"),
        "total_groups": len(groups),
        "total_matches": total_matches,
        "excluded_matches": excluded_matches,
        "match_exclusion_enabled": match_exclusion_enabled,
        "exclusion_rules_count": len(match_exclusion_rules),
        "group_details": group_details
    }

@event_management_router.post("/{event_id}/fixture/generate")
async def generate_fixture(
    event_id: str, 
    request: dict = Body(default={}),
    current_user: dict = None
):
    """Akıllı Fikstür Oluşturma Algoritması
    
    Bu algoritma şu parametreleri dikkate alır:
    - Maç başlangıç ve bitiş saatleri
    - Ara (mola) saati - bu aralıkta maç planlanmaz
    - Sporcu çakışmasını önleme
    - Dinlenme süreleri
    - Saha kullanım dengeleme
    - Etkinlik türü, cinsiyet ve yaş grubu öncelikleri
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Frontend'den gelen parametreler
    start_time_str = request.get("start_time", "09:00")
    end_time_str = request.get("end_time", "18:00")
    has_break = request.get("has_break", True)
    break_start_str = request.get("break_start", "12:00")
    break_end_str = request.get("break_end", "13:00")
    
    # Çok günlü etkinlik kontrolü - event_duration veya start/end date'ten
    event_duration = event.get("event_duration", "single_day")
    is_multi_day = event_duration in ["weekend", "weekly", "two_weeks", "seasonal"]
    
    # Etkinlik başlangıç ve bitiş tarihleri
    event_start_date = event.get("start_date")
    event_end_date = event.get("end_date")
    
    # Tarih bilgisini datetime'a çevir
    if event_start_date:
        if isinstance(event_start_date, str):
            try:
                event_start_date = datetime.fromisoformat(event_start_date.replace("Z", "+00:00")).replace(tzinfo=None)
            except:
                event_start_date = None
    
    if event_end_date:
        if isinstance(event_end_date, str):
            try:
                event_end_date = datetime.fromisoformat(event_end_date.replace("Z", "+00:00")).replace(tzinfo=None)
            except:
                event_end_date = None
    
    logging.info(f"📅 Etkinlik süresi: {event_duration}, Çok günlü: {is_multi_day}")
    logging.info(f"   - Başlangıç: {event_start_date}, Bitiş: {event_end_date}")
    
    # Ayarlardan alınan değerler - önce request'ten, yoksa tournament_settings'ten al
    tournament_settings = event.get("tournament_settings", {})
    match_duration = request.get("match_duration_minutes") or tournament_settings.get("match_duration_minutes") or 15
    break_minutes = request.get("break_minutes") or tournament_settings.get("break_between_matches_minutes") or 5
    court_count = request.get("court_count") or tournament_settings.get("court_count") or int(event.get("field_count", 4))
    
    # Optimizasyon ayarları - önce request'ten, yoksa tournament_settings'ten al
    scheduling_event_types = request.get("scheduling_event_types") or tournament_settings.get("scheduling_event_types", [])
    scheduling_genders = request.get("scheduling_genders") or tournament_settings.get("scheduling_genders", [])
    scheduling_age_groups = request.get("scheduling_age_groups") or tournament_settings.get("scheduling_age_groups", [])
    prevent_player_overlap = request.get("prevent_player_overlap", True)
    min_rest_between_matches = request.get("min_rest_between_matches", 10)
    balance_court_usage = request.get("balance_court_usage", True)
    prioritize_seeded_players = request.get("prioritize_seeded_players", False)
    in_group_refereeing = tournament_settings.get("in_group_refereeing", False)
    
    logging.info(f"📊 Öncelik sıralamaları:")
    logging.info(f"   - Etkinlik türleri: {scheduling_event_types}")
    logging.info(f"   - Cinsiyetler: {scheduling_genders}")
    logging.info(f"   - Yaş grupları: {scheduling_age_groups}")
    logging.info(f"   - request.scheduling_age_groups: {request.get('scheduling_age_groups')}")
    logging.info(f"   - tournament_settings.scheduling_age_groups: {tournament_settings.get('scheduling_age_groups')}")
    logging.info(f"   - Grup içi hakemlik: {in_group_refereeing}")
    
    # Saatleri datetime'a çevir
    today = datetime.now().date()
    
    def parse_time(time_str, default_hour=9, default_minute=0):
        try:
            parts = time_str.split(":")
            return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        except:
            return default_hour, default_minute
    
    start_h, start_m = parse_time(start_time_str, 9, 0)
    end_h, end_m = parse_time(end_time_str, 18, 0)
    break_start_h, break_start_m = parse_time(break_start_str, 12, 0)
    break_end_h, break_end_m = parse_time(break_end_str, 13, 0)
    
    start_time = datetime.combine(today, datetime.min.time().replace(hour=start_h, minute=start_m))
    end_time = datetime.combine(today, datetime.min.time().replace(hour=end_h, minute=end_m))
    break_start_time = datetime.combine(today, datetime.min.time().replace(hour=break_start_h, minute=break_start_m))
    break_end_time = datetime.combine(today, datetime.min.time().replace(hour=break_end_h, minute=break_end_m))
    
    logging.info(f"🗓️ Fikstür oluşturma: {start_time_str}-{end_time_str}, ara: {break_start_str}-{break_end_str if has_break else 'yok'}")
    logging.info(f"   Maç: {match_duration}dk, Ara: {break_minutes}dk, Saha: {court_count}")
    logging.info(f"   ⚠️ REQUEST PARAMS: court_count={request.get('court_count')}, match_duration={request.get('match_duration_minutes')}")
    
    settings = event.get("tournament_settings", {})
    match_system = settings.get("match_system", "round_robin")
    
    # Grupları al
    groups = await db.event_groups.find({"event_id": event_id}).to_list(1000)
    
    if not groups:
        raise HTTPException(status_code=400, detail="Önce gruplar oluşturulmalı")
    
    # ==================== KATILIMCI İSİMLERİNİ AL ====================
    # Tüm gruplardan katılımcı ID'lerini topla
    all_participant_ids = set()
    for group in groups:
        for pid in group.get("participant_ids", []):
            if isinstance(pid, dict):
                all_participant_ids.add(pid.get("id", str(pid)))
            else:
                all_participant_ids.add(str(pid))
    
    # Katılımcı isimlerini users koleksiyonundan al
    participant_names = {}
    if all_participant_ids:
        users = await db.users.find({"id": {"$in": list(all_participant_ids)}}).to_list(1000)
        for user in users:
            participant_names[user["id"]] = user.get("full_name") or user.get("name") or "Bilinmeyen"
    
    logging.info(f"📋 {len(participant_names)} katılımcı ismi yüklendi")
    
    # ==================== GRUPLARI ÖNCELİĞE GÖRE SIRALA ====================
    import re
    
    def extract_age_from_string(text: str) -> int:
        """Herhangi bir metinden yaş sayısını çıkar"""
        if not text:
            return 0
        text = str(text).lower()
        
        # "70 üstü", "70+", "70 over" formatları
        match = re.search(r'(\d+)\s*(?:\+|üstü|üzeri|over)', text)
        if match:
            return int(match.group(1))
        
        # "30-39", "64-69" formatları - ilk sayıyı al
        match = re.search(r'(\d+)\s*[-_]\s*(\d+)', text)
        if match:
            return int(match.group(1))
        
        # Sadece sayı
        match = re.search(r'(\d+)', text)
        if match:
            return int(match.group(1))
        
        return 0
    
    # scheduling_age_groups listesindeki string'leri sayılara çevir
    age_priority_list = []
    for age_str in scheduling_age_groups:
        age_num = extract_age_from_string(age_str)
        if age_num > 0:
            age_priority_list.append(age_num)
    
    logging.info(f"   - Yaş öncelik listesi (sayısal): {age_priority_list}")
    
    def get_group_priority(group):
        """Grubun öncelik sırasını hesapla"""
        priority = 0
        category = (group.get("category", "") or "").lower()
        group_name = (group.get("name", "") or "").lower()
        combined = f"{category} {group_name}"
        
        # Grup yaşını çıkar
        group_age = extract_age_from_string(combined)
        
        # Etkinlik türü belirleme (tek/çift/karışık)
        # 'tekler' kelimesini tam olarak kontrol et - 'çiftler' içinde 'tek' yok
        is_singles = ('tekler' in combined or 'single' in combined or 
                     (' tek ' in f' {combined} ') or combined.endswith(' tek') or combined.startswith('tek '))
        is_doubles = ('çiftler' in combined or 'double' in combined or 
                     (' çift ' in f' {combined} ') or combined.endswith(' çift') or combined.startswith('çift '))
        is_mixed = 'karışık' in combined or 'mixed' in combined or 'mikst' in combined
        
        # Detaylı log
        logging.info(f"   🔍 Grup analizi: '{group.get('name')}' -> is_singles={is_singles}, is_doubles={is_doubles}, is_mixed={is_mixed}")
        
        # Etkinlik türü önceliği - eşleşme bulunamazsa en sona at
        event_type_matched = False
        event_type_priority = 0
        
        for idx, event_type in enumerate(scheduling_event_types):
            et = str(event_type).lower()
            
            # Tek maçlar kontrolü
            if ('tek' in et or 'single' in et) and is_singles and not is_doubles:
                event_type_priority = idx * 10000
                event_type_matched = True
                logging.info(f"      ✅ TEK eşleşti: event_type='{event_type}' idx={idx} -> +{event_type_priority}")
                break
            # Çift maçlar kontrolü
            elif ('çift' in et or 'double' in et) and is_doubles and not is_mixed:
                event_type_priority = idx * 10000
                event_type_matched = True
                logging.info(f"      ✅ ÇİFT eşleşti: event_type='{event_type}' idx={idx} -> +{event_type_priority}")
                break
            # Karışık çift kontrolü
            elif ('karışık' in et or 'mixed' in et or 'mikst' in et) and is_mixed:
                event_type_priority = idx * 10000
                event_type_matched = True
                logging.info(f"      ✅ KARIŞIK eşleşti: event_type='{event_type}' idx={idx} -> +{event_type_priority}")
                break
        
        priority += event_type_priority
        
        # Eşleşme bulunamazsa en sona at
        if not event_type_matched:
            priority += 99 * 10000
            logging.info(f"      ❌ Etkinlik türü EŞLEŞMEDİ -> +990000")
        
        # Cinsiyet önceliği
        gender_matched = False
        gender_priority = 0
        for idx, gender in enumerate(scheduling_genders):
            g = str(gender).lower()
            if g == 'male' and 'erkek' in combined:
                gender_priority = idx * 1000
                gender_matched = True
                logging.info(f"      ✅ CİNSİYET eşleşti: ERKEK idx={idx} -> +{gender_priority}")
                break
            elif g == 'female' and ('kadın' in combined or 'kadin' in combined):
                gender_priority = idx * 1000
                gender_matched = True
                logging.info(f"      ✅ CİNSİYET eşleşti: KADIN idx={idx} -> +{gender_priority}")
                break
        
        priority += gender_priority
        
        # Yaş grubu önceliği - age_priority_list'teki sıraya göre
        age_priority = 0
        if age_priority_list and group_age > 0:
            for idx, age in enumerate(age_priority_list):
                if group_age == age or (group_age >= age and group_age < age + 10):
                    age_priority = idx * 100
                    logging.info(f"      ✅ YAŞ eşleşti: grup_yaş={group_age}, liste_yaş={age} idx={idx} -> +{age_priority}")
                    break
        
        priority += age_priority
        
        logging.info(f"      📊 TOPLAM: etkinlik={event_type_priority} + cinsiyet={gender_priority} + yaş={age_priority} = {priority}")
        
        return priority
    
    groups_sorted = sorted(groups, key=get_group_priority)
    
    # Sıralama sonucunu logla
    logging.info(f"📋 Grup sıralaması ({len(groups_sorted)} grup):")
    for idx, g in enumerate(groups_sorted[:15]):
        gname = g.get('name', '')
        gpriority = get_group_priority(g)
        gage = extract_age_from_string(gname)
        is_tek = 'tek' in gname.lower()
        is_cift = 'çift' in gname.lower()
        etype = "TEK" if is_tek else ("ÇİFT" if is_cift else "?")
        logging.info(f"   {idx+1}. {gname} ({etype}, yaş:{gage}, öncelik:{gpriority})")
    
    # ==================== EŞLEŞME KURALLARI ====================
    league_settings = await db.league_settings.find_one({"event_id": event_id})
    match_exclusion_enabled = False
    match_exclusion_rules = []
    
    if league_settings:
        match_exclusion_enabled = league_settings.get("match_exclusion_enabled", False)
        match_exclusion_rules = league_settings.get("match_exclusion_rules", [])
    
    all_matches = []
    excluded_count = 0
    
    # ==================== MAÇLARI OLUŞTUR ====================
    logging.info(f"📊 Toplam {len(groups_sorted)} grup işlenecek")
    
    for group in groups_sorted:
        participants = group.get("participant_ids", [])
        pairs = group.get("pairs", [])
        is_doubles = group.get("is_doubles", False)
        group_system = group.get("match_system", match_system)
        
        # Çift grubu ise pair'leri kullan
        if is_doubles and pairs:
            match_entities = [p["pair_id"] for p in pairs]
        else:
            match_entities = participants
        
        logging.info(f"   👥 Grup: {group.get('name')} - {len(match_entities)} katılımcı/çift, is_doubles={is_doubles}, system={group_system}")
        
        if len(match_entities) < 2:
            logging.warning(f"   ⚠️ Grup '{group.get('name')}' yetersiz katılımcı: {len(match_entities)}")
            continue
        
        # Hariç tutulan çiftler
        excluded_pairs = set()
        if match_exclusion_enabled and match_exclusion_rules:
            for rule in match_exclusion_rules:
                rank_a = rule.get("rank_a", 0)
                rank_b = rule.get("rank_b", 0)
                if 1 <= rank_a <= len(match_entities) and 1 <= rank_b <= len(match_entities):
                    p_a = match_entities[rank_a - 1]
                    p_b = match_entities[rank_b - 1]
                    excluded_pairs.add((p_a, p_b))
                    excluded_pairs.add((p_b, p_a))
        
        # Maç çiftlerini oluştur
        if group_system == "round_robin":
            match_pairs = generate_round_robin_matches(match_entities)
        elif group_system == "double_round_robin":
            match_pairs = generate_double_round_robin_matches(match_entities)
        elif group_system == "single_elimination":
            match_pairs = generate_single_elimination_bracket(match_entities)
        else:
            match_pairs = generate_round_robin_matches(match_entities)
        
        for p1, p2, round_num in match_pairs:
            if (p1, p2) in excluded_pairs or (p2, p1) in excluded_pairs:
                excluded_count += 1
                continue
            
            match = {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "group_id": group["id"],
                "group_name": group["name"],
                "category": group.get("category", ""),
                "round_number": round_num,
                "participant1_id": p1,
                "participant2_id": p2,
                "participant1_name": participant_names.get(p1, "Bilinmeyen"),
                "participant2_name": participant_names.get(p2, "Bilinmeyen"),
                "is_doubles": is_doubles,
                "status": "scheduled",
                "score": None,
                "sets": [],
                "winner_id": None,
                "court_number": None,
                "referee_id": None,
                "scheduled_time": None,
                "created_at": datetime.utcnow()
            }
            all_matches.append(match)
    
    # ==================== AKILLI SAHA VE ZAMAN ATAMA ====================
    # Grup içi hakemlik için grup katılımcıları sözlüğü oluştur
    group_participants = {}
    if in_group_refereeing:
        for group in groups:
            group_id = group.get("id")
            participants = group.get("participant_ids", [])
            # Participant ID'lerini düzelt
            clean_participants = []
            for p in participants:
                if isinstance(p, dict):
                    clean_participants.append(p.get("id"))
                else:
                    clean_participants.append(p)
            group_participants[group_id] = clean_participants
        logging.info(f"👨‍⚖️ Grup içi hakemlik aktif - {len(group_participants)} grup için katılımcı listesi hazırlandı")
    
    if prevent_player_overlap or balance_court_usage:
        all_matches = smart_schedule_matches(
            all_matches,
            court_count=court_count,
            match_duration=match_duration,
            break_minutes=break_minutes,
            start_time=start_time,
            min_rest_minutes=min_rest_between_matches,
            prevent_overlap=prevent_player_overlap,
            balance_courts=balance_court_usage,
            end_time=end_time,
            has_break=has_break,
            break_start_time=break_start_time,
            break_end_time=break_end_time,
            is_multi_day=is_multi_day,
            event_end_date=event_end_date,
            in_group_refereeing=in_group_refereeing,
            group_participants=group_participants,
            scheduling_event_types=scheduling_event_types,
            scheduling_genders=scheduling_genders,
            scheduling_age_groups=age_priority_list
        )
    else:
        # Basit sıralı atama
        all_matches = assign_courts_automatically(
            all_matches, court_count, match_duration, break_minutes, start_time
        )
    
    # Grup içi hakemlik için hakem isimlerini çöz
    if in_group_refereeing:
        # Hakem ID'lerinden isimleri çözmek için cache oluştur
        referee_ids = set(m.get("referee_id") for m in all_matches if m.get("referee_id"))
        referee_names = {}
        
        for ref_id in referee_ids:
            if ref_id:
                user = await db.users.find_one({"id": ref_id})
                if user:
                    referee_names[ref_id] = user.get("full_name") or user.get("name") or "Bilinmeyen"
                else:
                    referee_names[ref_id] = "Bilinmeyen"
        
        # Maçlara hakem isimlerini ekle
        for match in all_matches:
            ref_id = match.get("referee_id")
            if ref_id and ref_id in referee_names:
                match["referee_name"] = referee_names[ref_id]
        
        logging.info(f"👨‍⚖️ {len(referee_ids)} hakem ismi çözümlendi")
    
    # Mevcut maçları sil
    await db.event_matches.delete_many({"event_id": event_id})
    
    # Yeni maçları kaydet
    if all_matches:
        await db.event_matches.insert_many(all_matches)
    
    # Grup içi hakemlik bildirimleri gönder
    if in_group_refereeing:
        referee_matches = [m for m in all_matches if m.get("referee_id") and m.get("referee_is_player")]
        if referee_matches:
            # Benzersiz hakem-maç çiftlerini grupla
            referee_notifications = {}
            for match in referee_matches:
                ref_id = match.get("referee_id")
                if ref_id not in referee_notifications:
                    referee_notifications[ref_id] = []
                referee_notifications[ref_id].append(match)
            
            # Her hakeme bildirim gönder
            for ref_id, matches in referee_notifications.items():
                try:
                    # İlk maçın bilgilerini al
                    first_match = min(matches, key=lambda m: m.get("scheduled_time") or datetime.max)
                    match_time = first_match.get("scheduled_time")
                    court_number = first_match.get("court_number")
                    
                    notification = {
                        "id": str(uuid.uuid4()),
                        "user_id": ref_id,
                        "type": "referee_assignment",
                        "title": "👨‍⚖️ Hakemlik Görevi",
                        "message": f"'{event.get('title', 'Turnuva')}' etkinliğinde {len(matches)} maç için hakemlik görevi atandı.",
                        "data": {
                            "event_id": event_id,
                            "event_title": event.get("title"),
                            "match_count": len(matches),
                            "first_match_time": match_time.isoformat() if match_time else None,
                            "first_court": court_number
                        },
                        "read": False,
                        "created_at": datetime.utcnow()
                    }
                    await db.notifications.insert_one(notification)
                    logging.info(f"📢 Hakem bildirimi gönderildi: {ref_id} - {len(matches)} maç")
                except Exception as ne:
                    logging.warning(f"⚠️ Hakem bildirimi gönderilemedi: {ref_id}: {ne}")
            
            logging.info(f"👨‍⚖️ Toplam {len(referee_notifications)} hakeme bildirim gönderildi")
    
    # Event'i güncelle
    await db.events.update_one(
        {"id": event_id},
        {"$set": {"fixture_generated": True, "match_count": len(all_matches)}}
    )
    
    message = f"{len(all_matches)} maç oluşturuldu"
    if excluded_count > 0:
        message += f" ({excluded_count} maç eşleşme kurallarına göre hariç tutuldu)"
    
    return {
        "status": "success", 
        "message": message,
        "match_count": len(all_matches),
        "excluded_count": excluded_count
    }

@event_management_router.delete("/{event_id}/fixture")
async def delete_fixture(event_id: str, current_user: dict = None):
    """Fikstürü sil - tüm maçları ve puan durumlarını kaldır"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Tüm maçları sil
    match_result = await db.event_matches.delete_many({"event_id": event_id})
    deleted_matches = match_result.deleted_count
    
    # Puan durumlarını sil
    standings_result = await db.event_standings.delete_many({"event_id": event_id})
    deleted_standings = standings_result.deleted_count
    
    # Etkinlik fixture_generated durumunu güncelle
    await db.events.update_one(
        {"id": event_id},
        {"$set": {"fixture_generated": False, "match_count": 0}}
    )
    
    logging.info(f"✅ Fikstür silindi: event_id={event_id}, silinen_maç={deleted_matches}, silinen_standings={deleted_standings}")
    
    return {
        "status": "success",
        "message": f"{deleted_matches} maç ve {deleted_standings} puan kaydı silindi",
        "deleted_matches": deleted_matches,
        "deleted_standings": deleted_standings
    }

@event_management_router.get("/{event_id}/fixture")
async def get_fixture(event_id: str, group_id: Optional[str] = None, current_user: dict = None):
    """Fikstürü getir"""
    global db
    
    query = {"event_id": event_id}
    if group_id:
        query["group_id"] = group_id
    
    matches = await db.event_matches.find(query).sort("scheduled_time", 1).to_list(1000)
    
    # Çift maçları için pair bilgilerini önbelleğe al
    pair_cache = {}
    
    async def get_participant_name(pid: str, is_doubles: bool) -> dict:
        """Katılımcı veya çift ismini getir"""
        if not pid:
            return {"id": None, "name": "TBD", "avatar": None}
        
        # Önce user olarak dene
        user = await db.users.find_one({"id": pid})
        if user:
            return {
                "id": pid,
                "name": user.get("full_name") or user.get("name") or "Bilinmeyen",
                "avatar": user.get("profile_image")
            }
        
        # Çift maçı ise pair olarak dene
        if is_doubles:
            # Önbellekte var mı kontrol et
            if pid in pair_cache:
                return pair_cache[pid]
            
            # event_participants'tan çift bilgisini al
            pair_participant = await db.event_participants.find_one({
                "event_id": event_id,
                "$or": [
                    {"doubles_pair_id": pid},
                    {"mixed_pair_id": pid},
                    {"id": pid}
                ]
            })
            
            if pair_participant:
                # Çiftin her iki oyuncusunun ismini al
                player1_id = pair_participant.get("user_id")
                partner_id = pair_participant.get("doubles_partner_id") or pair_participant.get("mixed_partner_id")
                
                player1 = await db.users.find_one({"id": player1_id}) if player1_id else None
                partner = await db.users.find_one({"id": partner_id}) if partner_id else None
                
                player1_name = (player1.get("full_name") or player1.get("name") or "?") if player1 else "?"
                partner_name = (partner.get("full_name") or partner.get("name") or "?") if partner else "?"
                
                pair_name = f"{player1_name} / {partner_name}"
                result = {"id": pid, "name": pair_name, "avatar": None}
                pair_cache[pid] = result
                return result
            
            # Gruptan pair bilgisini al
            groups = await db.event_groups.find({"event_id": event_id}).to_list(100)
            for group in groups:
                pairs = group.get("pairs") or []
                for pair in pairs:
                    if pair and pair.get("pair_id") == pid:
                        pair_name = pair.get("pair_name") or f"{pair.get('player1_name', '?')} / {pair.get('player2_name', '?')}"
                        result = {"id": pid, "name": pair_name, "avatar": None}
                        pair_cache[pid] = result
                        return result
        
        return {"id": pid, "name": "Bilinmeyen", "avatar": None}
    
    # Katılımcı ve hakem detaylarını ekle
    for match in matches:
        # is_doubles kontrolü - birleşik ID'den de algıla
        p1_id = match.get("participant1_id", "")
        p2_id = match.get("participant2_id", "")
        is_doubles = match.get("is_doubles", False) or ("_" in str(p1_id)) or ("_" in str(p2_id))
        
        # Önce maçta kayıtlı ismi kontrol et (backend'den direkt gelen)
        p1_name_from_match = match.get("participant1_name", "")
        p2_name_from_match = match.get("participant2_name", "")
        
        # Katılımcı 1
        if p1_name_from_match and p1_name_from_match not in ["?", "TBD", "Bilinmeyen"] and not p1_name_from_match.startswith("Oyuncu"):
            match["participant1"] = {"id": p1_id, "name": p1_name_from_match, "avatar": None}
        else:
            match["participant1"] = await get_participant_name(p1_id, is_doubles)
        
        # Katılımcı 2
        if p2_name_from_match and p2_name_from_match not in ["?", "TBD", "Bilinmeyen"] and not p2_name_from_match.startswith("Oyuncu"):
            match["participant2"] = {"id": p2_id, "name": p2_name_from_match, "avatar": None}
        else:
            match["participant2"] = await get_participant_name(p2_id, is_doubles)
        
        # Hakem
        if match.get("referee_id"):
            referee = await db.users.find_one({"id": match.get("referee_id")})
            referee_name = (referee.get("full_name") or referee.get("name") or "Bilinmeyen") if referee else "Bilinmeyen"
            match["referee"] = {
                "id": match.get("referee_id"),
                "name": referee_name
            }
            match["referee_name"] = referee_name
        
        # _id kaldır
        if "_id" in match:
            del match["_id"]
    
    # Gruplara göre grupla
    grouped_matches = {}
    for match in matches:
        group_name = match.get("group_name", "Genel")
        if group_name not in grouped_matches:
            grouped_matches[group_name] = []
        grouped_matches[group_name].append(match)
    
    return {"matches": matches, "grouped_matches": grouped_matches}

# ================== MAÇ YÖNETİMİ ==================

@event_management_router.get("/{event_id}/matches/{match_id}")
async def get_match_detail(event_id: str, match_id: str, current_user: dict = None):
    """Maç detayını getir"""
    global db
    
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    # Detayları ekle
    event = await find_event_by_id(db, event_id)
    match["event_title"] = event.get("title") if event else "Bilinmeyen Etkinlik"
    
    # Katılımcılar
    p1 = await db.users.find_one({"id": match.get("participant1_id")})
    p2 = await db.users.find_one({"id": match.get("participant2_id")})
    match["participant1"] = {"id": match.get("participant1_id"), "name": p1.get("full_name") if p1 else "?", "avatar": p1.get("profile_image") if p1 else None}
    match["participant2"] = {"id": match.get("participant2_id"), "name": p2.get("full_name") if p2 else "?", "avatar": p2.get("profile_image") if p2 else None}
    
    # Hakem
    if match.get("referee_id"):
        ref = await db.users.find_one({"id": match.get("referee_id")})
        match["referee"] = {"id": match.get("referee_id"), "name": ref.get("full_name") if ref else "?"}
    
    if "_id" in match:
        del match["_id"]
    
    return match

@event_management_router.put("/{event_id}/matches/{match_id}")
async def update_match(event_id: str, match_id: str, update: MatchUpdate):
    """Maçı güncelle"""
    global db
    
    update_dict = {k: v for k, v in update.model_dump().items() if v is not None}
    update_dict["updated_at"] = datetime.utcnow()
    
    old_match = await db.event_matches.find_one({"id": match_id})
    
    result = await db.event_matches.update_one(
        {"id": match_id, "event_id": event_id},
        {"$set": update_dict}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    # Saat değiştiyse oyunculara bildirim gönder
    if update.scheduled_time and old_match:
        old_time = old_match.get("scheduled_time")
        if old_time != update.scheduled_time:
            for pid in [old_match.get("participant1_id"), old_match.get("participant2_id")]:
                if pid:
                    notification = {
                        "id": str(uuid.uuid4()),
                        "user_id": pid,
                        "type": "match_time_changed",
                        "title": "⏰ Maç Saati Değişti",
                        "message": f"Maç saatiniz değişti. Yeni saat: {update.scheduled_time}",
                        "data": {"match_id": match_id, "event_id": event_id},
                        "is_read": False,
                        "created_at": datetime.utcnow()
                    }
                    await db.notifications.insert_one(notification)
    
    return {"status": "success", "message": "Maç güncellendi"}


@event_management_router.post("/{event_id}/matches/{match_id}/start")
async def start_match(event_id: str, match_id: str, current_user: dict = Depends(get_current_user)):
    """Maçı başlat - hakem oyuncuya bildirim gönder"""
    global db
    
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Maç zaten başlamış mı?
    if match.get("status") in ["in_progress", "completed", "pending_confirmation"]:
        raise HTTPException(status_code=400, detail="Maç zaten başlamış veya tamamlanmış")
    
    # Maçı başlat
    await db.event_matches.update_one(
        {"id": match_id},
        {"$set": {
            "status": "in_progress",
            "started_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }}
    )
    
    # Hakeme bildirim gönder (eğer hakem bir oyuncuysa)
    referee_id = match.get("referee_id")
    if referee_id and match.get("referee_is_player"):
        court_number = match.get("court_number", "?")
        p1_name = match.get("participant1_name", "Oyuncu 1")
        p2_name = match.get("participant2_name", "Oyuncu 2")
        
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": referee_id,
            "type": "referee_match_started",
            "title": "🏓 Maç Başladı - Hakemlik Görevi",
            "message": f"Saha {court_number}: {p1_name} vs {p2_name} maçı başladı. Lütfen masaya gidin.",
            "data": {
                "match_id": match_id,
                "event_id": event_id,
                "court_number": court_number
            },
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(notification)
        logging.info(f"📢 Hakem maç başladı bildirimi: {referee_id} - Saha {court_number}")
    
    return {"status": "success", "message": "Maç başlatıldı"}


@event_management_router.post("/{event_id}/matches/{match_id}/assign-court")
async def assign_match_to_court(
    event_id: str, 
    match_id: str, 
    court_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Maçı belirli bir sahaya ata ve oyunculara + hakeme bildirim gönder
    
    Kurallar:
    1. Aynı grupta oynayan insanlar aynı sahada maç yapmalı
    2. Sıradaki maçlar saha sırasına göre ard arda verilmeli
    3. Maç erken bitmiş ise o gruptaki maç ilk sıraya yerleşmeli
    4. Sahaya maç ataması yapıldığında ilgili oyuncular ve hakeme bildirim gitmeli
    """
    global db
    
    court_number = court_data.get("court_number")
    if not court_number:
        raise HTTPException(status_code=400, detail="Saha numarası gerekli")
    
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Maç zaten oynuyor mu?
    if match.get("status") in ["in_progress", "completed", "pending_confirmation"]:
        raise HTTPException(status_code=400, detail="Maç zaten başlamış veya tamamlanmış")
    
    # Saha müsait mi kontrol et
    active_on_court = await db.event_matches.find_one({
        "event_id": event_id,
        "court_number": court_number,
        "status": {"$in": ["in_progress", "playing", "live"]}
    })
    
    if active_on_court:
        raise HTTPException(status_code=400, detail=f"Saha {court_number} şu anda meşgul")
    
    # Maçı sahaya ata ve başlat
    await db.event_matches.update_one(
        {"id": match_id},
        {"$set": {
            "court_number": court_number,
            "status": "in_progress",
            "started_at": datetime.utcnow(),
            "assigned_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }}
    )
    
    # Oyuncu ve hakem bilgilerini al
    p1_id = match.get("participant1_id")
    p2_id = match.get("participant2_id")
    referee_id = match.get("referee_id")
    p1_name = match.get("participant1_name", "Oyuncu 1")
    p2_name = match.get("participant2_name", "Oyuncu 2")
    group_name = match.get("group_name", "")
    round_number = match.get("round_number", 1)
    event_title = event.get("title", "Etkinlik")
    
    # Bildirim metni
    notification_title = f"🏓 Maçınız Başlıyor - Saha {court_number}"
    notification_message = f"{event_title}\n{group_name} - Tur {round_number}\n{p1_name} vs {p2_name}\n\n📍 Lütfen Saha {court_number}'e gidin!"
    
    # Oyunculara bildirim gönder
    for player_id in [p1_id, p2_id]:
        if player_id:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": player_id,
                "type": "match_court_assigned",
                "title": notification_title,
                "message": notification_message,
                "data": {
                    "match_id": match_id,
                    "event_id": event_id,
                    "court_number": court_number,
                    "opponent": p2_name if player_id == p1_id else p1_name
                },
                "read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(notification)
            logging.info(f"📢 Oyuncu bildirimi gönderildi: {player_id} - Saha {court_number}")
    
    # Hakeme bildirim gönder
    if referee_id:
        referee_notification = {
            "id": str(uuid.uuid4()),
            "user_id": referee_id,
            "type": "referee_match_assigned",
            "title": f"⚖️ Hakemlik Görevi - Saha {court_number}",
            "message": f"{event_title}\n{group_name} - Tur {round_number}\n{p1_name} vs {p2_name}\n\n📍 Lütfen Saha {court_number}'e gidin ve maçı yönetin!",
            "data": {
                "match_id": match_id,
                "event_id": event_id,
                "court_number": court_number
            },
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(referee_notification)
        logging.info(f"📢 Hakem bildirimi gönderildi: {referee_id} - Saha {court_number}")
    
    return {
        "status": "success", 
        "message": f"Maç Saha {court_number}'e atandı ve bildirimler gönderildi",
        "court_number": court_number
    }


@event_management_router.post("/{event_id}/auto-assign-courts")
async def auto_assign_courts(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Boş sahalara otomatik maç ata
    
    Kurallar:
    1. Aynı grupta oynayan insanlar aynı sahada maç yapmalı
    2. Sıradaki maçlar saha sırasına göre ard arda verilmeli (Saha 1 Grup A, Saha 2 Grup B, ...)
    3. Maç erken bitmiş ise o gruptaki maç ilk sıraya yerleşmeli
    4. Herhangi bir grubun maçı bitmiş ise sistem boş masalara atama için sormalı
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Turnuva ayarlarını al
    settings = event.get("tournament_settings", {})
    court_count = settings.get("court_count", 4)
    
    # Aktif maçları al (hangi sahalar dolu?)
    active_matches = await db.event_matches.find({
        "event_id": event_id,
        "status": {"$in": ["in_progress", "playing", "live"]}
    }).to_list(100)
    
    occupied_courts = set(m.get("court_number") for m in active_matches if m.get("court_number"))
    empty_courts = [i for i in range(1, court_count + 1) if i not in occupied_courts]
    
    if not empty_courts:
        return {"status": "info", "message": "Tüm sahalar dolu", "assigned": []}
    
    # Bekleyen maçları al
    pending_matches = await db.event_matches.find({
        "event_id": event_id,
        "status": {"$in": ["pending", "scheduled", "upcoming"]},
        "participant1_id": {"$exists": True, "$ne": None},
        "participant2_id": {"$exists": True, "$ne": None}
    }).to_list(1000)
    
    if not pending_matches:
        return {"status": "info", "message": "Bekleyen maç yok", "assigned": []}
    
    # Grupları ve son maç sahasını takip et
    # Kural: Her grup kendi sahasında oynamalı
    group_court_mapping = {}  # {group_id: preferred_court}
    
    # Önce tamamlanmış maçlardan grup-saha eşleşmesini öğren
    completed_matches = await db.event_matches.find({
        "event_id": event_id,
        "status": {"$in": ["completed", "finished"]},
        "court_number": {"$exists": True, "$ne": None}
    }).to_list(1000)
    
    for m in completed_matches:
        group_id = m.get("group_id") or m.get("group_name")
        court = m.get("court_number")
        if group_id and court:
            if group_id not in group_court_mapping:
                group_court_mapping[group_id] = court
    
    # Maçları gruba göre grupla ve sırala
    from collections import defaultdict
    matches_by_group = defaultdict(list)
    
    for m in pending_matches:
        group_id = m.get("group_id") or m.get("group_name") or "default"
        matches_by_group[group_id].append(m)
    
    # Her grubu round_number'a göre sırala
    for group_id in matches_by_group:
        matches_by_group[group_id].sort(key=lambda x: (x.get("round_number", 1), x.get("scheduled_time") or ""))
    
    # Boş sahalara round-robin şekilde maç ata
    assigned = []
    group_ids = sorted(matches_by_group.keys())
    
    for court_num in empty_courts:
        # Bu saha için en uygun grubu bul
        best_group = None
        
        # Önce bu sahaya daha önce atanmış grup var mı?
        for gid, preferred_court in group_court_mapping.items():
            if preferred_court == court_num and gid in matches_by_group and matches_by_group[gid]:
                best_group = gid
                break
        
        # Yoksa, henüz sahası olmayan bir grup bul
        if not best_group:
            for gid in group_ids:
                if gid not in group_court_mapping and matches_by_group.get(gid):
                    best_group = gid
                    group_court_mapping[gid] = court_num
                    break
        
        # Hala bulunamadıysa, herhangi bir grupta maç var mı?
        if not best_group:
            for gid in group_ids:
                if matches_by_group.get(gid):
                    best_group = gid
                    break
        
        if best_group and matches_by_group[best_group]:
            match = matches_by_group[best_group].pop(0)
            
            # Maçı sahaya ata
            await db.event_matches.update_one(
                {"id": match["id"]},
                {"$set": {
                    "court_number": court_num,
                    "status": "in_progress",
                    "started_at": datetime.utcnow(),
                    "assigned_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }}
            )
            
            # Bildirimleri gönder
            p1_id = match.get("participant1_id")
            p2_id = match.get("participant2_id")
            referee_id = match.get("referee_id")
            p1_name = match.get("participant1_name", "Oyuncu 1")
            p2_name = match.get("participant2_name", "Oyuncu 2")
            group_name = match.get("group_name", "")
            round_number = match.get("round_number", 1)
            event_title = event.get("title", "Etkinlik")
            
            notification_title = f"🏓 Maçınız Başlıyor - Saha {court_num}"
            notification_message = f"{event_title}\n{group_name} - Tur {round_number}\n{p1_name} vs {p2_name}\n\n📍 Lütfen Saha {court_num}'e gidin!"
            
            for player_id in [p1_id, p2_id]:
                if player_id:
                    await db.notifications.insert_one({
                        "id": str(uuid.uuid4()),
                        "user_id": player_id,
                        "type": "match_court_assigned",
                        "title": notification_title,
                        "message": notification_message,
                        "data": {"match_id": match["id"], "event_id": event_id, "court_number": court_num},
                        "read": False,
                        "created_at": datetime.utcnow()
                    })
            
            if referee_id:
                await db.notifications.insert_one({
                    "id": str(uuid.uuid4()),
                    "user_id": referee_id,
                    "type": "referee_match_assigned",
                    "title": f"⚖️ Hakemlik Görevi - Saha {court_num}",
                    "message": f"{event_title}\n{group_name} - Tur {round_number}\n{p1_name} vs {p2_name}\n\n📍 Saha {court_num}'de maçı yönetin!",
                    "data": {"match_id": match["id"], "event_id": event_id, "court_number": court_num},
                    "read": False,
                    "created_at": datetime.utcnow()
                })
            
            assigned.append({
                "match_id": match["id"],
                "court_number": court_num,
                "group": best_group,
                "players": f"{p1_name} vs {p2_name}"
            })
            
            logging.info(f"📍 Otomatik atama: {p1_name} vs {p2_name} -> Saha {court_num} ({best_group})")
    
    return {
        "status": "success",
        "message": f"{len(assigned)} maç sahaya atandı",
        "assigned": assigned,
        "remaining_empty_courts": len(empty_courts) - len(assigned)
    }


@event_management_router.get("/{event_id}/empty-courts-suggestion")
async def get_empty_courts_suggestion(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Boş sahalar için maç önerisi döndür
    Kural 4: Herhangi bir grubun maçı bitmiş ise sistem boş masalara atama için sormalı
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    settings = event.get("tournament_settings", {})
    court_count = settings.get("court_count", 4)
    
    # Aktif maçları al
    active_matches = await db.event_matches.find({
        "event_id": event_id,
        "status": {"$in": ["in_progress", "playing", "live"]}
    }).to_list(100)
    
    occupied_courts = set(m.get("court_number") for m in active_matches if m.get("court_number"))
    empty_courts = [i for i in range(1, court_count + 1) if i not in occupied_courts]
    
    # Bekleyen maçları al
    pending_matches = await db.event_matches.find({
        "event_id": event_id,
        "status": {"$in": ["pending", "scheduled", "upcoming"]},
        "participant1_id": {"$exists": True, "$ne": None},
        "participant2_id": {"$exists": True, "$ne": None}
    }).to_list(100)
    
    suggestions = []
    
    for court_num in empty_courts:
        if pending_matches:
            match = pending_matches[0]
            suggestions.append({
                "court_number": court_num,
                "suggested_match": {
                    "id": match["id"],
                    "group": match.get("group_name", ""),
                    "round": match.get("round_number", 1),
                    "player1": match.get("participant1_name", "Oyuncu 1"),
                    "player2": match.get("participant2_name", "Oyuncu 2")
                }
            })
            pending_matches = pending_matches[1:]
    
    return {
        "empty_courts": empty_courts,
        "total_courts": court_count,
        "pending_matches_count": len(pending_matches),
        "suggestions": suggestions,
        "should_prompt": len(empty_courts) > 0 and len(suggestions) > 0
    }


@event_management_router.post("/{event_id}/matches/{match_id}/submit-result")
async def submit_match_result(event_id: str, match_id: str, result: MatchResultSubmit):
    """Maç sonucunu gir"""
    global db
    
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    # Etkinliği kontrol et - gönderen kişi yönetici mi?
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # ==================== MİSAFİR VE YETKİ KONTROLÜ ====================
    # Kullanıcı bilgisini al
    submitter = await db.users.find_one({"id": result.submitted_by})
    if not submitter:
        raise HTTPException(status_code=403, detail="Kullanıcı bulunamadı")
    
    # Misafir kontrolü - misafirler skor giremez
    if submitter.get("user_type") == "guest" or submitter.get("is_guest") == True:
        raise HTTPException(status_code=403, detail="Misafir kullanıcılar maç sonucu giremez")
    
    # Yetki kontrolü: Sadece maçın oyuncuları, hakem, organizatör veya yöneticiler skor girebilir
    participant1_id = match.get("participant1_id")
    participant2_id = match.get("participant2_id")
    referee_id = match.get("referee_id")
    organizer_id = event.get("organizer_id")
    creator_id = event.get("created_by") or event.get("creator_id")
    admin_ids = event.get("admin_ids") or []
    organizer_ids = event.get("organizers") or []
    
    allowed_users = [participant1_id, participant2_id, referee_id, organizer_id, creator_id] + admin_ids + organizer_ids
    allowed_users = [u for u in allowed_users if u]  # None değerleri temizle
    
    if result.submitted_by not in allowed_users:
        raise HTTPException(status_code=403, detail="Bu maç için skor girme yetkiniz yok. Sadece oyuncular, hakem veya organizatörler skor girebilir.")
    # ==================== MİSAFİR VE YETKİ KONTROLÜ SONU ====================
    
    # Spor türüne göre skor kurallarını kontrol et
    sport_name = event.get("sport", "")
    if sport_name:
        # Spor yapılandırmasını al
        sport_config = await db.sport_configurations.find_one({
            "sport_name": {"$regex": f"^{sport_name}$", "$options": "i"},
            "is_active": True
        })
        
        if sport_config:
            match_score_settings = sport_config.get("match_score_settings", {})
            uses_sets = match_score_settings.get("uses_sets", False)
            max_sets = match_score_settings.get("max_sets", 5)
            allow_draw = match_score_settings.get("allow_draw", True)
            
            # Skor formatını doğrula (örn: "3-2", "3-1", "3-0")
            if result.score and uses_sets:
                try:
                    score_parts = result.score.split("-")
                    if len(score_parts) == 2:
                        score1 = int(score_parts[0].strip())
                        score2 = int(score_parts[1].strip())
                        
                        # Kazanmak için gereken set sayısı (max_sets'in yarısından fazlası)
                        # Örnek: max_sets=5 ise sets_to_win=3 (5//2+1=3)
                        sets_to_win = (max_sets // 2) + 1
                        
                        # ==================== YENİ VALİDASYON KURALLARI ====================
                        # Bir taraf sets_to_win'e ulaştığında maç biter!
                        # Geçerli skorlar (max_sets=5, sets_to_win=3): 3-0, 3-1, 3-2, 0-3, 1-3, 2-3
                        # Geçersiz skorlar: 4-1, 4-0, 5-0 vb. (kazanan 3'ten fazla alamaz)
                        
                        # Negatif skor kontrolü
                        if score1 < 0 or score2 < 0:
                            raise HTTPException(
                                status_code=400, 
                                detail=f"Geçersiz skor: Negatif değer girilemez. Girilen: {result.score}"
                            )
                        
                        # En az bir taraf tam olarak sets_to_win'e ulaşmalı (kazanan)
                        has_winner = (score1 == sets_to_win) or (score2 == sets_to_win)
                        if not has_winner:
                            raise HTTPException(
                                status_code=400, 
                                detail=f"Geçersiz skor: {sport_name} için kazanan tam olarak {sets_to_win} set almalı. Girilen: {result.score}. Geçerli skorlar: {sets_to_win}-0, {sets_to_win}-1, {sets_to_win}-2 veya tersi."
                            )
                        
                        # Kaybeden sets_to_win'den az set almış olmalı
                        loser_sets = score2 if score1 == sets_to_win else score1
                        if loser_sets >= sets_to_win:
                            raise HTTPException(
                                status_code=400, 
                                detail=f"Geçersiz skor: Kaybeden en fazla {sets_to_win - 1} set alabilir. Girilen: {result.score}"
                            )
                        
                        # Toplam set sayısı kontrolü (opsiyonel, yukarıdaki kurallar zaten bunu kapsar)
                        total_sets = score1 + score2
                        if total_sets > max_sets:
                            raise HTTPException(
                                status_code=400, 
                                detail=f"Geçersiz skor: {sport_name} için maksimum {max_sets} set oynanabilir. Toplam: {total_sets}"
                            )
                        
                        # Beraberlik kontrolü
                        if not allow_draw and score1 == score2:
                            raise HTTPException(
                                status_code=400, 
                                detail=f"Geçersiz skor: {sport_name} için beraberlik kabul edilmez"
                            )
                        # ==================== VALİDASYON SONU ====================
                        
                        logger.info(f"✅ Skor validasyonu geçti: {result.score} (max_sets={max_sets}, sets_to_win={sets_to_win})")
                        
                except ValueError:
                    # Skor parse edilemezse geçerli kabul et (farklı format olabilir)
                    logger.warning(f"⚠️ Skor parse edilemedi: {result.score}")
    
    is_admin = False
    if event:
        organizer_id = event.get("organizer_id")
        creator_id = event.get("created_by") or event.get("creator_id")
        admin_ids = event.get("admin_ids") or []
        organizer_ids = event.get("organizers") or []
        
        # Yönetici kontrolü
        if result.submitted_by:
            if result.submitted_by == organizer_id:
                is_admin = True
            elif result.submitted_by == creator_id:
                is_admin = True
            elif result.submitted_by in admin_ids:
                is_admin = True
            elif result.submitted_by in organizer_ids:
                is_admin = True
    
    # Eğer admin/yönetici giriyorsa direkt onaylı kabul et
    if is_admin:
        await db.event_matches.update_one(
            {"id": match_id},
            {"$set": {
                "winner_id": result.winner_id,
                "score": result.score,
                "sets": result.sets or [],
                "result_submitted_by": result.submitted_by,
                "status": "completed",  # Direkt tamamlandı
                "result_submitted_at": datetime.utcnow(),
                "result_confirmed_by": result.submitted_by,
                "result_confirmed_at": datetime.utcnow()
            }}
        )
        
        # Güncellenmiş maç bilgisini al
        updated_match = await db.event_matches.find_one({"id": match_id})
        if updated_match:
            updated_match["winner_id"] = result.winner_id  # Ensure winner_id is set
            # Puan tablosunu güncelle
            await update_standings(event_id, updated_match)
            
            # Çift eleme maçıysa özel ilerleme mantığı
            tournament_type = updated_match.get("tournament_type")
            if tournament_type == "double_elimination":
                await advance_double_elimination(db, event_id, updated_match)
            # Normal eleme maçıysa (ana veya teselli), kazananı bir sonraki tura yerleştir
            elif updated_match.get("bracket_position") in ["elimination", "consolation"]:
                await advance_winner_to_next_round(db, event_id, updated_match)
        
        logger.info(f"✅ Admin tarafından skor girildi ve onaylandı: {match_id}, Score: {result.score}")
        return {"status": "success", "message": "Skor kaydedildi ve puan tablosu güncellendi", "auto_confirmed": True}
    
    # Normal kullanıcı - onay bekle
    await db.event_matches.update_one(
        {"id": match_id},
        {"$set": {
            "winner_id": result.winner_id,
            "score": result.score,
            "sets": result.sets or [],
            "result_submitted_by": result.submitted_by,
            "status": "pending_confirmation",
            "result_submitted_at": datetime.utcnow()
        }}
    )
    
    # Onay için bildirim gönder (hakem veya diğer oyuncu)
    other_participant = match.get("participant1_id") if result.submitted_by == match.get("participant2_id") else match.get("participant2_id")
    referee_id = match.get("referee_id")
    
    notification_targets = [other_participant]
    if referee_id:
        notification_targets.append(referee_id)
    
    for target in notification_targets:
        if target:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": target,
                "type": "match_result_confirmation",
                "title": "📝 Maç Sonucu Onayı",
                "message": f"Maç sonucu girildi. Lütfen onaylayın: {result.score}",
                "data": {
                    "match_id": match_id,
                    "event_id": event_id,
                    "score": result.score,
                    "winner_id": result.winner_id,
                    "action_required": True
                },
                "is_read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(notification)
    
    return {"status": "success", "message": "Sonuç kaydedildi, onay bekleniyor", "auto_confirmed": False}

# confirm-score alias (frontend uyumluluğu için)
@event_management_router.post("/{event_id}/matches/{match_id}/confirm-score")
async def confirm_match_score_alias(event_id: str, match_id: str, confirmation: MatchResultConfirmFrontend, request: Request):
    """Maç sonucunu onayla (frontend uyumlu endpoint)"""
    global db
    
    # Request header'dan kullanıcı bilgisini al
    auth_header = request.headers.get("Authorization", "")
    user_id = None
    
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        # Token'dan user_id çıkar (basit implementasyon)
        try:
            # Token'ı decode et
            import jwt
            payload = jwt.decode(token, options={"verify_signature": False})
            user_id = payload.get("user_id") or payload.get("sub")
        except:
            pass
    
    # Header'da user-id varsa onu kullan
    if not user_id:
        user_id = request.headers.get("x-user-id")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Kullanıcı kimliği bulunamadı")
    
    # Maçı bul
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    # Status kontrolü - pending_confirmation veya in_progress olabilir
    if match.get("status") not in ["pending_confirmation", "in_progress"]:
        raise HTTPException(status_code=400, detail="Bu maç onay bekliyor durumunda değil")
    
    # Kullanıcı bilgisini al
    confirmer = await db.users.find_one({"id": user_id})
    if not confirmer:
        raise HTTPException(status_code=403, detail="Kullanıcı bulunamadı")
    
    # Misafir kontrolü
    if confirmer.get("user_type") == "guest" or confirmer.get("is_guest") == True:
        raise HTTPException(status_code=403, detail="Misafir kullanıcılar maç sonucu onaylayamaz")
    
    # Etkinlik bilgisini al
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yetki kontrolü
    participant1_id = match.get("participant1_id")
    participant2_id = match.get("participant2_id")
    referee_id = match.get("referee_id")
    organizer_id = event.get("organizer_id")
    creator_id = event.get("created_by") or event.get("creator_id")
    admin_ids = event.get("admin_ids") or []
    organizer_ids = event.get("organizers") or []
    
    allowed_users = [participant1_id, participant2_id, referee_id, organizer_id, creator_id] + admin_ids + organizer_ids
    allowed_users = [u for u in allowed_users if u]
    
    if user_id not in allowed_users:
        raise HTTPException(status_code=403, detail="Bu maç sonucunu onaylama yetkiniz yok")
    
    if confirmation.confirmed:
        # Onay ver
        logger.info(f"✅ Confirming match {match_id} by user {user_id}")
        await db.event_matches.update_one(
            {"id": match_id},
            {"$set": {
                "status": "completed",
                "result_confirmed_by": user_id,
                "result_confirmed_at": datetime.utcnow()
            }}
        )
        
        # Güncel match objesini al
        updated_match = await db.event_matches.find_one({"id": match_id})
        logger.info(f"📊 Updated match data: id={updated_match.get('id') if updated_match else 'None'}, winner_id={updated_match.get('winner_id') if updated_match else 'None'}, score={updated_match.get('score') if updated_match else 'None'}")
        
        # Puan tablosunu güncelle
        if updated_match and updated_match.get("winner_id"):
            await update_standings(event_id, updated_match)
            logger.info(f"📊 Standings updated for match {match_id}")
        else:
            logger.warning(f"⚠️ Skipping standings update - no winner_id in match {match_id}")
        
        return {"status": "success", "message": "Sonuç onaylandı"}
    else:
        # Red/İtiraz durumu
        await db.event_matches.update_one(
            {"id": match_id},
            {"$set": {
                "status": "disputed",
                "disputed_by": user_id,
                "disputed_at": datetime.utcnow()
            }}
        )
        return {"status": "success", "message": "Sonuca itiraz edildi"}

@event_management_router.post("/{event_id}/matches/{match_id}/confirm-result")
async def confirm_match_result(event_id: str, match_id: str, confirmation: MatchResultConfirm):
    """Maç sonucunu onayla"""
    global db
    
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    if match.get("status") != "pending_confirmation":
        raise HTTPException(status_code=400, detail="Bu maç onay bekliyor durumunda değil")
    
    # ==================== MİSAFİR VE YETKİ KONTROLÜ ====================
    # Kullanıcı bilgisini al
    confirmer = await db.users.find_one({"id": confirmation.confirmed_by})
    if not confirmer:
        raise HTTPException(status_code=403, detail="Kullanıcı bulunamadı")
    
    # Misafir kontrolü - misafirler onaylama yapamaz
    if confirmer.get("user_type") == "guest" or confirmer.get("is_guest") == True:
        raise HTTPException(status_code=403, detail="Misafir kullanıcılar maç sonucu onaylayamaz")
    
    # Etkinlik bilgisini al
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yetki kontrolü: Sadece maçın oyuncuları (skoru giren hariç), hakem, organizatör veya yöneticiler onaylayabilir
    participant1_id = match.get("participant1_id")
    participant2_id = match.get("participant2_id")
    referee_id = match.get("referee_id")
    result_submitted_by = match.get("result_submitted_by")  # Skoru giren kişi
    organizer_id = event.get("organizer_id")
    creator_id = event.get("created_by") or event.get("creator_id")
    admin_ids = event.get("admin_ids") or []
    organizer_ids = event.get("organizers") or []
    
    # Skoru giren kişi kendi sonucunu onaylayamaz (oyuncu ise)
    # Ama hakem veya yönetici kendi girdiği skoru onaylayabilir
    allowed_users = [referee_id, organizer_id, creator_id] + admin_ids + organizer_ids
    
    # Oyunculardan sadece skoru girmeyen kişi onaylayabilir
    if result_submitted_by == participant1_id:
        allowed_users.append(participant2_id)  # Sadece participant2 onaylayabilir
    elif result_submitted_by == participant2_id:
        allowed_users.append(participant1_id)  # Sadece participant1 onaylayabilir
    else:
        # Skoru giren ne participant1 ne participant2 ise (hakem/admin girdi), her iki oyuncu da onaylayabilir
        allowed_users.extend([participant1_id, participant2_id])
    
    allowed_users = [u for u in allowed_users if u]  # None değerleri temizle
    
    if confirmation.confirmed_by not in allowed_users:
        raise HTTPException(status_code=403, detail="Bu maç sonucunu onaylama yetkiniz yok. Sadece rakip oyuncu, hakem veya organizatörler onaylayabilir.")
    # ==================== MİSAFİR VE YETKİ KONTROLÜ SONU ====================
    
    if confirmation.confirmed:
        await db.event_matches.update_one(
            {"id": match_id},
            {"$set": {
                "status": "completed",
                "result_confirmed_by": confirmation.confirmed_by,
                "result_confirmed_at": datetime.utcnow()
            }}
        )
        
        # Güncel match objesini al (winner_id dahil)
        updated_match = await db.event_matches.find_one({"id": match_id})
        
        # Puan tablosunu güncelle
        if updated_match and updated_match.get("winner_id"):
            await update_standings(event_id, updated_match)
            logger.info(f"📊 Standings updated for match {match_id}")
        
        # Eleme maçıysa (ana veya teselli), kazananı bir sonraki tura yerleştir
        bracket_pos = updated_match.get("bracket_position") if updated_match else None
        if updated_match and bracket_pos in ["elimination", "consolation"]:
            await advance_winner_to_next_round(db, event_id, updated_match)
        
        return {"status": "success", "message": "Sonuç onaylandı"}
    else:
        # Reddedildi - tekrar sonuç girişi gerekiyor
        await db.event_matches.update_one(
            {"id": match_id},
            {"$set": {
                "status": "scheduled",
                "winner_id": None,
                "score": None,
                "sets": [],
                "result_submitted_by": None,
                "result_confirmed_by": None
            }}
        )
        return {"status": "success", "message": "Sonuç reddedildi, tekrar giriş gerekiyor"}


@event_management_router.post("/{event_id}/fix-standings")
async def fix_pending_standings(event_id: str):
    """
    Admin: pending_confirmation durumundaki maçları completed yap ve puan tablosunu güncelle
    Bu endpoint mevcut maçları düzeltmek için kullanılır.
    """
    global db
    
    # Önce mevcut standings'i temizle (yeniden hesaplanacak)
    await db.event_standings.delete_many({"event_id": event_id})
    logger.info(f"🗑️ Cleared existing standings for event {event_id}")
    
    # pending_confirmation veya completed durumundaki maçları bul
    matches_to_process = await db.event_matches.find({
        "event_id": event_id,
        "status": {"$in": ["pending_confirmation", "completed"]},
        "winner_id": {"$ne": None}
    }).to_list(500)
    
    logger.info(f"📊 Found {len(matches_to_process)} matches to process")
    
    processed = 0
    for match in matches_to_process:
        match_id = match["id"]
        winner_id = match.get("winner_id")
        
        if not winner_id:
            continue
            
        loser_id = match["participant1_id"] if winner_id == match["participant2_id"] else match["participant2_id"]
        group_id = match.get("group_id")
        
        # Maçı completed yap
        await db.event_matches.update_one(
            {"id": match_id},
            {"$set": {"status": "completed"}}
        )
        
        # Kazanan için puan ekle
        await db.event_standings.update_one(
            {"event_id": event_id, "group_id": group_id, "participant_id": winner_id},
            {
                "$inc": {"wins": 1, "points": 3, "matches_played": 1},
                "$setOnInsert": {"losses": 0, "draws": 0}
            },
            upsert=True
        )
        
        # Kaybeden için
        await db.event_standings.update_one(
            {"event_id": event_id, "group_id": group_id, "participant_id": loser_id},
            {
                "$inc": {"losses": 1, "matches_played": 1},
                "$setOnInsert": {"wins": 0, "draws": 0, "points": 0}
            },
            upsert=True
        )
        
        processed += 1
    
    # Sonuçları getir
    standings = await db.event_standings.find({"event_id": event_id}).sort("points", -1).to_list(100)
    
    logger.info(f"✅ Processed {processed} matches, created {len(standings)} standings")
    
    return {
        "status": "success",
        "message": f"{processed} maç işlendi, {len(standings)} oyuncu puan tablosuna eklendi",
        "processed_matches": processed,
        "standings_count": len(standings)
    }


async def update_standings(event_id: str, match: dict):
    """Puan tablosunu güncelle - Spor ayarlarından puan değerlerini al"""
    global db
    
    match_id = match.get("id")
    logger.info(f"📊 update_standings called: event_id={event_id}, match_id={match_id}")
    
    # ==================== ÇOKLU GÜNCELLEME KONTROLÜ ====================
    # Maçın standings'i zaten güncellendi mi kontrol et
    if match.get("standings_updated"):
        logger.info(f"⚠️ Standings already updated for match {match_id}, skipping")
        return
    
    # Maçı standings_updated olarak işaretle
    await db.event_matches.update_one(
        {"id": match_id},
        {"$set": {"standings_updated": True}}
    )
    # ==================== ÇOKLU GÜNCELLEME KONTROLÜ SONU ====================
    
    winner_id = match.get("winner_id")
    loser_id = match.get("participant1_id") if winner_id == match.get("participant2_id") else match.get("participant2_id")
    group_id = match.get("group_id")
    
    logger.info(f"📊 winner_id={winner_id}, loser_id={loser_id}, group_id={group_id}")
    
    if not winner_id:
        logger.warning(f"⚠️ No winner_id in match, skipping standings update")
        return
    
    if db is None:
        logger.error(f"❌ Database connection is None in update_standings!")
        return
    
    # Etkinliğin spor ayarlarını al
    event = await find_event_by_id(db, event_id)
    sport_name = event.get("sport") if event else None
    
    # ==================== ÖZEL PUANLAMA KONTROLÜ ====================
    custom_scoring_config = await db.custom_scoring_configs.find_one({"event_id": event_id})
    
    if custom_scoring_config and custom_scoring_config.get("enabled", False):
        # Özel puanlama aktif - custom_scoring_endpoints'den hesaplama yap
        logger.info(f"📊 Using CUSTOM SCORING for event {event_id}")
        
        match_result = custom_scoring_config.get("match_result", {})
        score_diff_config = custom_scoring_config.get("score_difference", {})
        
        # Maç skorunu parse et
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
        
        # Kazanan ve kaybeden puanlarını hesapla
        winner_points = 0
        loser_points = 0
        winner_breakdown = {}
        loser_breakdown = {}
        
        if is_forfeit:
            # Hükmen sonuç
            if forfeit_by == loser_id:
                winner_points = match_result.get("forfeit_win", 2)
                loser_points = match_result.get("forfeit_loss", -2)
                winner_breakdown["match_result"] = winner_points
                loser_breakdown["match_result"] = loser_points
            else:
                winner_points = match_result.get("forfeit_win", 2)
                loser_points = match_result.get("forfeit_loss", -2)
                winner_breakdown["match_result"] = winner_points
                loser_breakdown["match_result"] = loser_points
        else:
            # Normal maç sonucu
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
                
                # Yakın skor - kaybedene bonus
                if score_difference <= close_threshold:
                    loser_points += close_bonus
                    loser_breakdown["close_score_bonus"] = close_bonus
                    logger.info(f"📊 Close score bonus applied to loser: +{close_bonus}")
                
                # Baskın galibiyet - kazanana bonus
                if score_difference >= dominant_threshold:
                    winner_points += dominant_bonus
                    winner_breakdown["dominant_win_bonus"] = dominant_bonus
                    logger.info(f"📊 Dominant win bonus applied to winner: +{dominant_bonus}")
        
        # ==================== SET FARKI PUANLAMASI ====================
        set_diff_config = custom_scoring_config.get("set_difference", {})
        if set_diff_config.get("enabled", False):
            points_per_set = set_diff_config.get("points_per_set", 1)
            set_diff_points = score_difference * points_per_set
            winner_points += set_diff_points
            winner_breakdown["set_difference_bonus"] = set_diff_points
            loser_points -= set_diff_points
            loser_breakdown["set_difference_penalty"] = -set_diff_points
            logger.info(f"📊 Set difference points: winner +{set_diff_points}, loser -{set_diff_points}")
        
        # ==================== FAZ 2: RAKİP GÜCÜ BONUSU ====================
        opponent_strength_config = custom_scoring_config.get("opponent_strength", {})
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
            
            logger.info(f"📊 Opponent Strength: Winner points={winner_rank_points}, Loser points={loser_rank_points}, diff={point_diff}")
            
            # Kademe tablosu kullanılıyorsa
            if opponent_strength_config.get("use_tier_table", False):
                tiers = opponent_strength_config.get("tiers", [])
                for tier in tiers:
                    min_diff = tier.get("min_diff", 0)
                    max_diff = tier.get("max_diff", 999)
                    if min_diff <= point_diff <= max_diff:
                        if loser_rank_points > winner_rank_points:
                            # Düşük puanlı kazandı (sürpriz)
                            bonus = tier.get("lower_wins", 0)
                            if bonus != 0:
                                winner_points += bonus
                                winner_breakdown["tier_bonus_lower_wins"] = bonus
                                logger.info(f"📊 Tier table: lower wins bonus +{bonus}")
                            penalty = tier.get("higher_loses", 0)
                            if penalty != 0:
                                loser_points += penalty
                                loser_breakdown["tier_penalty_higher_loses"] = penalty
                                logger.info(f"📊 Tier table: higher loses penalty {penalty}")
                        else:
                            # Yüksek puanlı kazandı (beklenen)
                            bonus = tier.get("higher_wins", 0)
                            if bonus != 0:
                                winner_points += bonus
                                winner_breakdown["tier_bonus_higher_wins"] = bonus
                                logger.info(f"📊 Tier table: higher wins bonus +{bonus}")
                            penalty = tier.get("lower_loses", 0)
                            if penalty != 0:
                                loser_points += penalty
                                loser_breakdown["tier_penalty_lower_loses"] = penalty
                                logger.info(f"📊 Tier table: lower loses penalty {penalty}")
                        break
            else:
                # Eski sistem - basit bonus/ceza
                # Kaybeden daha yüksek puanlıysa (daha güçlü rakip)
                if loser_rank_points > winner_rank_points:
                    if point_diff >= 10:
                        bonus = opponent_strength_config.get("beat_much_higher_bonus", 25)
                        winner_points += bonus
                        winner_breakdown["opponent_strength_bonus"] = bonus
                        logger.info(f"📊 Beat much stronger opponent bonus: +{bonus}")
                    else:
                        bonus = opponent_strength_config.get("beat_higher_ranked_bonus", 15)
                        winner_points += bonus
                        winner_breakdown["opponent_strength_bonus"] = bonus
                        logger.info(f"📊 Beat stronger opponent bonus: +{bonus}")
                
                # Kaybeden daha düşük puanlıysa (daha zayıf rakibe kaybetme cezası)
                if winner_rank_points > loser_rank_points:
                    if point_diff >= 5:
                        penalty = opponent_strength_config.get("lose_to_lower_penalty", -5)
                        loser_points += penalty
                        loser_breakdown["lose_to_weaker_penalty"] = penalty
                        logger.info(f"📊 Lost to weaker opponent penalty: {penalty}")
        
        # ==================== FAZ 2: ADİL OYUN PUANLARI ====================
        fair_play_config = custom_scoring_config.get("fair_play", {})
        if fair_play_config.get("enabled", False):
            # Maçtaki kart/uyarı bilgilerini kontrol et
            winner_warnings = match.get("warnings", {}).get(winner_id, 0)
            loser_warnings = match.get("warnings", {}).get(loser_id, 0)
            winner_yellow = match.get("yellow_cards", {}).get(winner_id, 0)
            loser_yellow = match.get("yellow_cards", {}).get(loser_id, 0)
            winner_red = match.get("red_cards", {}).get(winner_id, 0)
            loser_red = match.get("red_cards", {}).get(loser_id, 0)
            
            # Kazanan için adil oyun
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
            
            # Kaybeden için adil oyun
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
        participation_config = custom_scoring_config.get("participation", {})
        if participation_config.get("enabled", False):
            attendance_bonus = participation_config.get("attendance_bonus", 5)
            # Her iki oyuncuya da katılım bonusu
            winner_points += attendance_bonus
            winner_breakdown["attendance_bonus"] = attendance_bonus
            loser_points += attendance_bonus
            loser_breakdown["attendance_bonus"] = attendance_bonus
            
            # Ardışık katılım bonusu kontrolü
            streak_bonus = participation_config.get("streak_bonus", 10)
            
            # Kazanan için streak kontrolü
            winner_matches = await db.event_matches.count_documents({
                "event_id": event_id,
                "status": "completed",
                "$or": [{"participant1_id": winner_id}, {"participant2_id": winner_id}]
            })
            if winner_matches >= 3 and winner_matches % 3 == 0:
                winner_points += streak_bonus
                winner_breakdown["streak_bonus"] = streak_bonus
                logger.info(f"📊 Winner streak bonus: +{streak_bonus}")
            
            # Kaybeden için streak kontrolü
            loser_matches = await db.event_matches.count_documents({
                "event_id": event_id,
                "status": "completed",
                "$or": [{"participant1_id": loser_id}, {"participant2_id": loser_id}]
            })
            if loser_matches >= 3 and loser_matches % 3 == 0:
                loser_points += streak_bonus
                loser_breakdown["streak_bonus"] = streak_bonus
                logger.info(f"📊 Loser streak bonus: +{streak_bonus}")
        
        # Atılan/Yenilen skorları hesapla (score1-score2 formatından)
        winner_scored = score1 if match.get("participant1_id") == winner_id else score2
        winner_conceded = score2 if match.get("participant1_id") == winner_id else score1
        loser_scored = score2 if match.get("participant1_id") == winner_id else score1
        loser_conceded = score1 if match.get("participant1_id") == winner_id else score2
        
        # Custom points ile standings güncelle
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
        
        # Maça özel puanlama bilgisini kaydet
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
        
        logger.info(f"📊 Custom scoring applied: winner={winner_points}, loser={loser_points}")
        return
    # ==================== ÖZEL PUANLAMA KONTROLÜ SONU ====================
    
    # Varsayılan puan değerleri (spor konfigürasyonundan)
    win_points = 3
    loss_points = 0
    
    if sport_name:
        # Spor konfigürasyonunu bul
        sport_config = await db.sport_configurations.find_one({"sport_name": sport_name})
        if sport_config:
            league_points = sport_config.get("league_points_settings", {})
            win_points = league_points.get("win_points", 3)
            loss_points = league_points.get("loss_points", 0)
            logger.info(f"📊 Using sport config for {sport_name}: win={win_points}, loss={loss_points}")
    
    # Maç skorunu parse et - set sayılarını al
    score = match.get("score", "0-0")
    try:
        parts = score.replace(" ", "").split("-")
        score1 = int(parts[0])
        score2 = int(parts[1])
    except:
        score1, score2 = 0, 0
    
    # Kazanan ve kaybeden set sayılarını belirle
    winner_sets = score1 if match.get("participant1_id") == winner_id else score2
    loser_sets = score2 if match.get("participant1_id") == winner_id else score1
    
    logger.info(f"📊 Score parsed: {score} -> winner_sets={winner_sets}, loser_sets={loser_sets}")
    
    # Kazanan için puan ekle
    await db.event_standings.update_one(
        {"event_id": event_id, "group_id": group_id, "participant_id": winner_id},
        {
            "$inc": {
                "wins": 1, 
                "points": win_points, 
                "matches_played": 1,
                "scored": winner_sets,
                "conceded": loser_sets
            },
            "$setOnInsert": {"losses": 0, "draws": 0}
        },
        upsert=True
    )
    
    # Kaybeden için
    await db.event_standings.update_one(
        {"event_id": event_id, "group_id": group_id, "participant_id": loser_id},
        {
            "$inc": {
                "losses": 1, 
                "points": loss_points, 
                "matches_played": 1,
                "scored": loser_sets,
                "conceded": winner_sets
            },
            "$setOnInsert": {"wins": 0, "draws": 0}
        },
        upsert=True
    )


async def reverse_standings(event_id: str, match: dict):
    """Bir maçın puan tablosu etkisini geri al"""
    global db
    
    old_winner_id = match.get("winner_id")
    if not old_winner_id:
        return  # Kazanan yoksa geri alınacak bir şey yok
    
    old_loser_id = match.get("participant1_id") if old_winner_id == match.get("participant2_id") else match.get("participant2_id")
    group_id = match.get("group_id")
    
    # Etkinliğin spor ayarlarını al
    event = await find_event_by_id(db, event_id)
    sport_name = event.get("sport") if event else None
    
    # Varsayılan puan değerleri
    win_points = 3
    loss_points = 0
    
    if sport_name:
        sport_config = await db.sport_configurations.find_one({"sport_name": sport_name})
        if sport_config:
            league_points = sport_config.get("league_points_settings", {})
            win_points = league_points.get("win_points", 3)
            loss_points = league_points.get("loss_points", 0)
    
    # Eski kazanandan puanları geri al
    await db.event_standings.update_one(
        {"event_id": event_id, "group_id": group_id, "participant_id": old_winner_id},
        {"$inc": {"wins": -1, "points": -win_points, "matches_played": -1}}
    )
    
    # Eski kaybedenden puanları geri al
    await db.event_standings.update_one(
        {"event_id": event_id, "group_id": group_id, "participant_id": old_loser_id},
        {"$inc": {"losses": -1, "points": -loss_points, "matches_played": -1}}
    )
    
    logger.info(f"📊 Reversed standings for match: old_winner={old_winner_id}, old_loser={old_loser_id}")


@event_management_router.post("/{event_id}/matches/{match_id}/correct-score")
async def correct_match_score(event_id: str, match_id: str, correction: MatchScoreCorrection):
    """
    Maç skorunu düzelt - SADECE ORGANİZATÖR VE YÖNETİCİLER
    
    Bu endpoint:
    1. Mevcut maçın puan tablosu etkisini geri alır
    2. Yeni skoru ve kazananı kaydeder
    3. Yeni puan tablosu etkisini uygular
    """
    global db
    
    # Maçı bul
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    # Etkinliği bul
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # ==================== YETKİ KONTROLÜ ====================
    # Kullanıcı bilgisini al
    corrector = await db.users.find_one({"id": correction.corrected_by})
    if not corrector:
        raise HTTPException(status_code=403, detail="Kullanıcı bulunamadı")
    
    # Misafir kontrolü
    if corrector.get("user_type") == "guest" or corrector.get("is_guest") == True:
        raise HTTPException(status_code=403, detail="Misafir kullanıcılar skor düzeltemez")
    
    # Sadece organizatör veya yöneticiler düzeltebilir
    organizer_id = event.get("organizer_id")
    creator_id = event.get("created_by") or event.get("creator_id")
    admin_ids = event.get("admin_ids") or []
    organizer_ids = event.get("organizers") or []
    
    allowed_users = [organizer_id, creator_id] + admin_ids + organizer_ids
    allowed_users = [u for u in allowed_users if u]
    
    if correction.corrected_by not in allowed_users:
        raise HTTPException(
            status_code=403, 
            detail="Skor düzeltme yetkisi yok. Sadece organizatör ve yöneticiler skor düzeltebilir."
        )
    # ==================== YETKİ KONTROLÜ SONU ====================
    
    # ==================== SKOR VALİDASYONU ====================
    sport_name = event.get("sport", "")
    if sport_name:
        sport_config = await db.sport_configurations.find_one({
            "sport_name": {"$regex": f"^{sport_name}$", "$options": "i"},
            "is_active": True
        })
        
        if sport_config:
            match_score_settings = sport_config.get("match_score_settings", {})
            uses_sets = match_score_settings.get("uses_sets", False)
            max_sets = match_score_settings.get("max_sets", 5)
            
            if correction.new_score and uses_sets:
                try:
                    score_parts = correction.new_score.split("-")
                    if len(score_parts) == 2:
                        score1 = int(score_parts[0].strip())
                        score2 = int(score_parts[1].strip())
                        sets_to_win = (max_sets // 2) + 1
                        
                        # Negatif skor kontrolü
                        if score1 < 0 or score2 < 0:
                            raise HTTPException(status_code=400, detail=f"Geçersiz skor: Negatif değer girilemez")
                        
                        # Kazanan tam olarak sets_to_win'e ulaşmalı
                        has_winner = (score1 == sets_to_win) or (score2 == sets_to_win)
                        if not has_winner:
                            raise HTTPException(
                                status_code=400, 
                                detail=f"Geçersiz skor: {sport_name} için kazanan tam olarak {sets_to_win} set almalı. Geçerli skorlar: {sets_to_win}-0, {sets_to_win}-1, {sets_to_win}-2 veya tersi."
                            )
                        
                        # Kaybeden sets_to_win'den az olmalı
                        loser_sets = score2 if score1 == sets_to_win else score1
                        if loser_sets >= sets_to_win:
                            raise HTTPException(status_code=400, detail=f"Geçersiz skor: Kaybeden en fazla {sets_to_win - 1} set alabilir")
                        
                except ValueError:
                    logger.warning(f"⚠️ Skor parse edilemedi: {correction.new_score}")
    # ==================== SKOR VALİDASYONU SONU ====================
    
    # Eski maç verilerini sakla
    old_winner_id = match.get("winner_id")
    old_score = match.get("score")
    old_status = match.get("status")
    
    # Eğer maç tamamlanmışsa ve puan tablosuna etki etmişse, önce geri al
    if old_status in ["completed", "pending_confirmation"] and old_winner_id:
        await reverse_standings(event_id, match)
        logger.info(f"📊 Reversed old standings for match {match_id}")
    
    # Yeni kazananı belirle (skor bazlı doğrulama)
    participant1_id = match.get("participant1_id")
    participant2_id = match.get("participant2_id")
    
    if correction.new_winner_id not in [participant1_id, participant2_id]:
        raise HTTPException(status_code=400, detail="Kazanan, maçın oyuncularından biri olmalı")
    
    # Maçı güncelle
    update_data = {
        "winner_id": correction.new_winner_id,
        "score": correction.new_score,
        "status": "completed",
        "score_corrected": True,
        "score_corrected_by": correction.corrected_by,
        "score_corrected_at": datetime.utcnow(),
        "correction_reason": correction.reason,
        "previous_score": old_score,
        "previous_winner_id": old_winner_id,
        "updated_at": datetime.utcnow()
    }
    
    await db.event_matches.update_one(
        {"id": match_id},
        {"$set": update_data}
    )
    
    # Yeni puan tablosunu uygula
    updated_match = await db.event_matches.find_one({"id": match_id})
    if updated_match:
        await update_standings(event_id, updated_match)
        logger.info(f"📊 Applied new standings for match {match_id}")
    
    # Düzeltme logunu kaydet
    correction_log = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "match_id": match_id,
        "type": "score_correction",
        "corrected_by": correction.corrected_by,
        "old_score": old_score,
        "new_score": correction.new_score,
        "old_winner_id": old_winner_id,
        "new_winner_id": correction.new_winner_id,
        "reason": correction.reason,
        "created_at": datetime.utcnow()
    }
    await db.event_logs.insert_one(correction_log)
    
    # Oyunculara bildirim gönder
    for participant_id in [participant1_id, participant2_id]:
        if participant_id:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": participant_id,
                "type": "match_score_corrected",
                "title": "📝 Maç Skoru Düzeltildi",
                "message": f"Maç sonucunuz düzeltildi. Eski skor: {old_score}, Yeni skor: {correction.new_score}",
                "data": {
                    "match_id": match_id,
                    "event_id": event_id,
                    "old_score": old_score,
                    "new_score": correction.new_score
                },
                "is_read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(notification)
    
    logger.info(f"✅ Score corrected for match {match_id}: {old_score} -> {correction.new_score}")
    
    return {
        "status": "success",
        "message": "Maç skoru düzeltildi ve puan tablosu güncellendi",
        "old_score": old_score,
        "new_score": correction.new_score,
        "old_winner_id": old_winner_id,
        "new_winner_id": correction.new_winner_id
    }


async def advance_winner_to_next_round(db, event_id: str, completed_match: dict):
    """
    Eleme maçı tamamlandığında kazananı bir sonraki tura yerleştir.
    
    Mantık:
    1. Tamamlanan maçın turunu ve kategorisini al
    2. Bir sonraki tur maçını bul (bracket_index kullanarak)
    3. Kazananı uygun pozisyona yerleştir
    """
    try:
        winner_id = completed_match.get("winner_id")
        if not winner_id:
            return
        
        category = completed_match.get("category")
        current_round = completed_match.get("round_number") or completed_match.get("bracket_round") or 1
        bracket_position = completed_match.get("bracket_position", "elimination")
        
        # bracket_index veya bracket_match_number kullan
        current_bracket_index = completed_match.get("bracket_index")
        if current_bracket_index is None:
            # bracket_match_number varsa kullan (1-indexed -> 0-indexed)
            bracket_match_num = completed_match.get("bracket_match_number", 1)
            current_bracket_index = bracket_match_num - 1
        
        logger.info(f"🏆 Advancing winner from R{current_round} bracket_index {current_bracket_index} to next round (category: {category}, position: {bracket_position})")
        
        # Kazananın ismini al - önce maçtaki kayıtlı ismi kontrol et
        is_doubles = completed_match.get("is_doubles", False) or ("_" in str(winner_id))
        
        winner_name = "Bilinmeyen"
        if completed_match.get("winner_id") == completed_match.get("participant1_id"):
            # Participant 1 kazandı - maçtaki ismi al
            winner_name = completed_match.get("participant1_name", "")
        else:
            # Participant 2 kazandı - maçtaki ismi al
            winner_name = completed_match.get("participant2_name", "")
        
        # Eğer isim hala geçersizse ve çift değilse user'dan al
        if not winner_name or winner_name in ["?", "TBD", "Bilinmeyen"]:
            if not is_doubles:
                winner_user = await db.users.find_one({"id": winner_id})
                winner_name = winner_user.get("full_name", "Bilinmeyen") if winner_user else "Bilinmeyen"
            else:
                # Çiftler için grup pairs'ten ara
                groups = await db.event_groups.find({"event_id": event_id}).to_list(100)
                for group in groups:
                    pairs = group.get("pairs") or []
                    for pair in pairs:
                        if pair and pair.get("pair_id") == winner_id:
                            winner_name = pair.get("pair_name") or f"{pair.get('player1_name', '?')} - {pair.get('player2_name', '?')}"
                            break
                    if winner_name and winner_name not in ["?", "TBD", "Bilinmeyen"]:
                        break
        
        logger.info(f"🏆 Winner name resolved: {winner_name} (is_doubles: {is_doubles})")
        
        # Kazanan için seed bilgisini bul
        winner_seed = None
        if completed_match.get("winner_id") == completed_match.get("participant1_id"):
            winner_seed = completed_match.get("participant1_seed")
        else:
            winner_seed = completed_match.get("participant2_seed")
        
        next_round = current_round + 1
        
        # Bir sonraki turda bu maçın kazananının gideceği bracket_index
        # bracket_index 0-1 -> next 0, bracket_index 2-3 -> next 1, etc.
        next_bracket_index = current_bracket_index // 2
        
        # Kazananın pozisyonu (participant1 veya participant2)
        # Çift bracket_index kazananları participant1, tek bracket_index kazananları participant2
        is_participant1 = (current_bracket_index % 2) == 0
        
        logger.info(f"📍 Winner goes to R{next_round}, bracket_index {next_bracket_index}, position {'P1' if is_participant1 else 'P2'}")
        
        # Bir sonraki tur maçını bul - birden fazla alan ile ara
        next_match = await db.event_matches.find_one({
            "event_id": event_id,
            "category": category,
            "bracket_position": bracket_position,
            "$or": [
                {"round_number": next_round},
                {"bracket_round": next_round}
            ],
            "bracket_index": next_bracket_index
        })
        
        # bracket_index ile bulamadıysak bracket_match_number ile dene
        if not next_match:
            next_match = await db.event_matches.find_one({
                "event_id": event_id,
                "category": category,
                "bracket_position": bracket_position,
                "$or": [
                    {"round_number": next_round},
                    {"bracket_round": next_round}
                ],
                "bracket_match_number": next_bracket_index + 1
            })
        
        if next_match:
            # Mevcut maçı güncelle
            update_field = "participant1_id" if is_participant1 else "participant2_id"
            update_name_field = "participant1_name" if is_participant1 else "participant2_name"
            update_seed_field = "participant1_seed" if is_participant1 else "participant2_seed"
            
            await db.event_matches.update_one(
                {"id": next_match["id"]},
                {"$set": {
                    update_field: winner_id,
                    update_name_field: winner_name,
                    update_seed_field: winner_seed,
                    "updated_at": datetime.utcnow()
                }}
            )
            logger.info(f"✅ Updated next round match: {winner_name} -> R{next_round} (bracket_index {next_bracket_index}, pos {'P1' if is_participant1 else 'P2'})")
            
            # Güncellenen maçı tekrar al
            updated_next_match = await db.event_matches.find_one({"id": next_match["id"]})
            
            # Her iki taraf da doluysa maçı "scheduled" yap
            if updated_next_match and updated_next_match.get("participant1_id") and updated_next_match.get("participant2_id"):
                await db.event_matches.update_one(
                    {"id": updated_next_match["id"]},
                    {"$set": {"status": "scheduled"}}
                )
                logger.info(f"✅ Next round match is ready: {updated_next_match.get('participant1_name')} vs {updated_next_match.get('participant2_name')}")
            
            # ========== YENİLEN OYUNCUYU BİR ÜST TURUN HAKEMİ YAP ==========
            # Ayarları kontrol et
            event = await db.events.find_one({"id": event_id})
            tournament_settings = event.get("tournament_settings", {}) if event else {}
            in_group_refereeing = tournament_settings.get("in_group_refereeing", False)
            
            if in_group_refereeing and next_match:
                # Yenilen oyuncuyu bul
                loser_id = completed_match.get("participant1_id") if winner_id == completed_match.get("participant2_id") else completed_match.get("participant2_id")
                loser_name = completed_match.get("participant1_name") if winner_id == completed_match.get("participant2_id") else completed_match.get("participant2_name")
                
                if loser_id:
                    # Bir üst turun maçına hakem olarak ata (eğer henüz hakem yoksa)
                    if not next_match.get("referee_id"):
                        await db.event_matches.update_one(
                            {"id": next_match["id"]},
                            {"$set": {
                                "referee_id": loser_id,
                                "referee_name": loser_name,
                                "referee_is_player": True,
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        logger.info(f"⚖️ Yenilen oyuncu hakem olarak atandı: {loser_name} -> R{next_round} maçı")
        else:
            logger.warning(f"⚠️ Could not find next round match for R{next_round}, bracket_index {next_bracket_index}")
            
    except Exception as e:
        logger.error(f"❌ Error advancing winner to next round: {e}")
        import traceback
        traceback.print_exc()


# ================== HAKEM YÖNETİMİ ==================

@event_management_router.get("/{event_id}/referees/available")
async def get_available_referees(event_id: str, current_user: dict = None):
    """Müsait hakemleri getir"""
    global db
    
    # Hakem rolündeki kullanıcılar
    referees = await db.users.find({"user_type": "referee"}).to_list(100)
    
    # Etkinlik katılımcıları da hakem olabilir
    event = await find_event_by_id(db, event_id)
    participants = event.get("participants", []) if event else []
    
    participant_users = await db.users.find({"id": {"$in": participants}}).to_list(100)
    
    all_referees = []
    seen_ids = set()
    
    for ref in referees:
        if ref["id"] not in seen_ids:
            all_referees.append({
                "id": ref["id"],
                "name": ref.get("full_name", "Bilinmeyen"),
                "is_referee": True,
                "is_participant": ref["id"] in participants
            })
            seen_ids.add(ref["id"])
    
    for user in participant_users:
        if user["id"] not in seen_ids:
            all_referees.append({
                "id": user["id"],
                "name": user.get("full_name", "Bilinmeyen"),
                "is_referee": False,
                "is_participant": True
            })
            seen_ids.add(user["id"])
    
    return {"referees": all_referees}

@event_management_router.post("/{event_id}/matches/{match_id}/assign-referee")
async def assign_referee_to_match(event_id: str, match_id: str, referee_id: str = Query(...), current_user: dict = None):
    """Maça hakem ata"""
    global db
    
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    # Hakem oyuncu mu kontrol et
    if referee_id in [match.get("participant1_id"), match.get("participant2_id")]:
        raise HTTPException(status_code=400, detail="Hakem bu maçta oyuncu olamaz")
    
    # Aynı saatte başka maçta hakem mi?
    scheduled_time = match.get("scheduled_time")
    if scheduled_time:
        conflict = await db.event_matches.find_one({
            "event_id": event_id,
            "referee_id": referee_id,
            "scheduled_time": scheduled_time,
            "id": {"$ne": match_id}
        })
        if conflict:
            raise HTTPException(status_code=400, detail="Hakem bu saatte başka bir maçta görevli")
    
    await db.event_matches.update_one(
        {"id": match_id},
        {"$set": {"referee_id": referee_id}}
    )
    
    return {"status": "success", "message": "Hakem atandı"}

# ================== SIRALAMA ==================

@event_management_router.get("/{event_id}/standings")
async def get_standings(event_id: str, group_id: Optional[str] = None, current_user: dict = None):
    """Puan durumunu getir"""
    global db
    
    query = {"event_id": event_id}
    if group_id:
        query["group_id"] = group_id
    
    standings = await db.event_standings.find(query).sort("points", -1).to_list(1000)
    
    # Lig ayarlarını kontrol et - önceki puanlar eklenecek mi?
    league_settings = await db.league_settings.find_one({"event_id": event_id})
    add_previous_points = league_settings.get("add_previous_points", False) if league_settings else False
    
    # Etkinlik bilgisini al - özel puanlama için
    event = await db.events.find_one({"id": event_id})
    use_custom_scoring = event.get("use_custom_scoring", False) if event else False
    custom_scoring_name = event.get("custom_scoring_name", "Özel Puan") if event else "Özel Puan"
    
    # Katılımcı detaylarını ekle
    for standing in standings:
        participant_id = standing.get("participant_id")
        user = await db.users.find_one({"id": participant_id})
        
        # Önceki puanları ve özel puanları al (event_athlete_points koleksiyonundan)
        previous_points = 0
        custom_score = 0
        athlete_points = await db.event_athlete_points.find_one({
            "event_id": event_id,
            "participant_id": participant_id
        })
        
        if athlete_points:
            if add_previous_points:
                previous_points = athlete_points.get("points", 0)
            if use_custom_scoring:
                custom_score = athlete_points.get("custom_score", 0)
        
        # Toplam puan hesapla
        match_points = standing.get("custom_points", standing.get("points", 0))
        total_points = match_points + previous_points
        
        standing["participant"] = {
            "id": participant_id,
            "name": user.get("full_name") if user else "Bilinmeyen",
            "avatar": user.get("profile_image") if user else None
        }
        standing["previous_points"] = previous_points
        standing["match_points"] = match_points
        standing["total_points"] = total_points
        standing["add_previous_points_enabled"] = add_previous_points
        standing["custom_score"] = custom_score
        standing["custom_score_name"] = custom_scoring_name
        
        if "_id" in standing:
            del standing["_id"]
    
    # Toplam puana göre yeniden sırala (eğer önceki puanlar eklendiyse)
    if add_previous_points:
        standings.sort(key=lambda x: x.get("total_points", 0), reverse=True)
    
    # Gruplara göre grupla
    if not group_id:
        grouped_standings = {}
        for s in standings:
            gid = s.get("group_id", "general")
            if gid not in grouped_standings:
                # Grup adını ve çift bilgisini al
                group = await db.event_groups.find_one({"id": gid})
                group_name = group.get("name") if group else "Genel"
                is_doubles = group.get("is_doubles", False) if group else False
                pairs = group.get("pairs", []) if group else []
                grouped_standings[gid] = {
                    "name": group_name, 
                    "standings": [], 
                    "add_previous_points": add_previous_points,
                    "is_doubles": is_doubles,
                    "pairs": pairs,
                    "use_custom_scoring": use_custom_scoring,
                    "custom_scoring_name": custom_scoring_name
                }
            
            # Çift gruplar için participant isimlerini pair_name'den al
            if grouped_standings[gid].get("is_doubles") and grouped_standings[gid].get("pairs"):
                participant_id = s.get("participant_id")
                pair_found = None
                for pair in grouped_standings[gid]["pairs"]:
                    if pair.get("pair_id") == participant_id:
                        pair_found = pair
                        break
                
                if pair_found:
                    s["participant"] = {
                        "id": participant_id,
                        "name": pair_found.get("pair_name") or f"{pair_found.get('player1_name', '')} - {pair_found.get('player2_name', '')}"
                    }
            
            grouped_standings[gid]["standings"].append(s)
        
        return {
            "grouped_standings": grouped_standings, 
            "add_previous_points_enabled": add_previous_points,
            "use_custom_scoring": use_custom_scoring,
            "custom_scoring_name": custom_scoring_name
        }
    
    return {
        "standings": standings, 
        "add_previous_points_enabled": add_previous_points,
        "use_custom_scoring": use_custom_scoring,
        "custom_scoring_name": custom_scoring_name
    }

@event_management_router.delete("/{event_id}/standings/{participant_id}")
async def delete_standing_entry(event_id: str, participant_id: str):
    """Belirli bir katılımcının standings kaydını sil (test/hatalı kayıtlar için)"""
    global db
    
    result = await db.event_standings.delete_many({
        "event_id": event_id,
        "participant_id": participant_id
    })
    
    logger.info(f"🗑️ Deleted {result.deleted_count} standings for participant {participant_id}")
    
    return {"status": "success", "deleted_count": result.deleted_count}

# ================== SAHA YÖNETİMİ ==================

@event_management_router.post("/{event_id}/courts/auto-assign")
async def auto_assign_courts(event_id: str, current_user: dict = None):
    """Sahaları otomatik ata"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    settings = event.get("tournament_settings", {})
    court_count = settings.get("court_count", 1)
    match_duration = settings.get("match_duration_minutes", 30)
    break_time = settings.get("break_between_matches_minutes", 10)
    start_time = settings.get("start_time") or event.get("start_date") or datetime.utcnow()
    
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    
    # Maçları al (saati olmayanlar)
    matches = await db.event_matches.find({
        "event_id": event_id,
        "status": "scheduled"
    }).to_list(500)
    
    # Saha ataması yap
    matches_list = [dict(m) for m in matches]
    updated_matches = assign_courts_automatically(matches_list, court_count, match_duration, break_time, start_time)
    
    # Güncelle
    for match in updated_matches:
        await db.event_matches.update_one(
            {"id": match["id"]},
            {"$set": {
                "court_number": match["court_number"],
                "scheduled_time": match["scheduled_time"]
            }}
        )
    
    return {"status": "success", "message": f"{len(updated_matches)} maça saha atandı"}

@event_management_router.get("/{event_id}/courts/availability")
async def get_court_availability(event_id: str, date: Optional[str] = None, current_user: dict = None):
    """Saha doluluk durumunu getir"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    settings = event.get("tournament_settings", {})
    court_count = settings.get("court_count", 1)
    
    # Maçları al
    query = {"event_id": event_id, "court_number": {"$ne": None}}
    matches = await db.event_matches.find(query).to_list(500)
    
    # Saha bazında gruplama
    court_schedule = {}
    for i in range(1, court_count + 1):
        court_schedule[i] = []
    
    for match in matches:
        court = match.get("court_number")
        if court and court in court_schedule:
            court_schedule[court].append({
                "match_id": match.get("id"),
                "time": match.get("scheduled_time"),
                "participant1": match.get("participant1_id"),
                "participant2": match.get("participant2_id"),
                "status": match.get("status")
            })
    
    return {"court_count": court_count, "schedule": court_schedule}

# ================== MANUEL KURA ==================

@event_management_router.post("/{event_id}/draw/manual")
async def manual_draw(event_id: str, assignments: Dict[str, List[str]], current_user: dict = None):
    """Manuel kura çekimi - assignments: {"group_id": ["participant_id1", "participant_id2", ...]}"""
    global db
    
    for group_id, participant_ids in assignments.items():
        await db.event_groups.update_one(
            {"id": group_id, "event_id": event_id},
            {"$set": {"participant_ids": participant_ids, "updated_at": datetime.utcnow()}}
        )
    
    return {"status": "success", "message": "Manuel kura kaydedildi"}

# ================== BAY OYUNCU YÖNETİMİ ==================

async def get_participant_ranking(db, participant_id: str, sport_type: str = None, event_id: str = None) -> int:
    """Katılımcının sıralamasını/puanını getir"""
    # Önce etkinlik bazlı manuel seed kontrolü
    if event_id:
        seed = await db.event_participant_seeds.find_one({
            "event_id": event_id,
            "participant_id": participant_id
        })
        if seed and seed.get("seed_number"):
            # Manuel seed varsa, ona göre yüksek skor ver (seed 1 = en yüksek skor)
            return 10000 - (seed.get("seed_number", 100) * 10)
    
    # Kullanıcı bilgisi
    user = await db.users.find_one({"id": participant_id})
    if not user:
        return 0
    
    # Kullanıcının tamamladığı maçları say
    total_wins = 0
    total_matches = 0
    
    # event_standings'den puan hesapla
    standings = await db.event_standings.find({"participant_id": participant_id}).to_list(100)
    for s in standings:
        total_wins += s.get("wins", 0)
        total_matches += s.get("matches_played", 0)
    
    # Kazanma oranı + toplam galibiyet bazlı skor
    win_rate = (total_wins / total_matches * 100) if total_matches > 0 else 0
    score = (total_wins * 10) + win_rate
    
    return int(score)


# ================== OYUNCU SIRALAMA (SEED) YÖNETİMİ ==================

@event_management_router.get("/{event_id}/participants/seeds")
async def get_participant_seeds(event_id: str, current_user: dict = None):
    """Etkinlik katılımcılarının sıralama (seed) bilgilerini getir"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    participant_ids = event.get("participants", [])
    sport_type = event.get("sport_type") or event.get("sport")
    
    # Tüm katılımcıların bilgilerini al
    participants = []
    for pid in participant_ids:
        user = await db.users.find_one({"id": pid})
        if user:
            # Manuel seed kontrolü
            seed_doc = await db.event_participant_seeds.find_one({
                "event_id": event_id,
                "participant_id": pid
            })
            seed_number = seed_doc.get("seed_number") if seed_doc else None
            
            # Otomatik skor hesapla
            auto_score = await get_participant_ranking(db, pid, sport_type)
            
            participants.append({
                "id": pid,
                "name": user.get("full_name", "Bilinmeyen"),
                "avatar": user.get("profile_image"),
                "seed_number": seed_number,
                "auto_score": auto_score,
                "is_seeded": seed_number is not None
            })
    
    # Sıralama: önce seed'li olanlar (küçükten büyüğe), sonra auto_score'a göre
    participants.sort(key=lambda x: (
        0 if x["seed_number"] else 1,  # Seed'li olanlar önce
        x["seed_number"] if x["seed_number"] else 999,  # Seed numarasına göre
        -x["auto_score"]  # Auto score'a göre (yüksekten düşüğe)
    ))
    
    return {
        "event_id": event_id,
        "total_participants": len(participants),
        "seeded_count": sum(1 for p in participants if p["is_seeded"]),
        "participants": participants
    }


@event_management_router.post("/{event_id}/participants/seeds")
async def set_participant_seeds(event_id: str, seeds_data: dict = Body(...)):
    """Katılımcıların sıralama (seed) numaralarını toplu güncelle"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    seeds = seeds_data.get("seeds", [])
    updated_count = 0
    for seed_update in seeds:
        participant_id = seed_update.get("participant_id")
        seed_number = seed_update.get("seed_number")
        
        if not participant_id or seed_number is None:
            continue
            
        # Upsert - varsa güncelle, yoksa oluştur
        await db.event_participant_seeds.update_one(
            {
                "event_id": event_id,
                "participant_id": participant_id
            },
            {
                "$set": {
                    "event_id": event_id,
                    "participant_id": participant_id,
                    "seed_number": seed_number,
                    "updated_at": datetime.utcnow()
                },
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        updated_count += 1
    
    return {
        "status": "success",
        "message": f"{updated_count} oyuncunun sıralaması güncellendi",
        "updated_count": updated_count
    }


@event_management_router.delete("/{event_id}/participants/{participant_id}/seed")
async def remove_participant_seed(event_id: str, participant_id: str, current_user: dict = None):
    """Katılımcının seed numarasını kaldır"""
    global db
    
    result = await db.event_participant_seeds.delete_one({
        "event_id": event_id,
        "participant_id": participant_id
    })
    
    if result.deleted_count == 0:
        return {"status": "info", "message": "Seed zaten yok"}
    
    return {"status": "success", "message": "Seed kaldırıldı"}

@event_management_router.post("/{event_id}/groups/auto-assign-byes")
async def auto_assign_byes(event_id: str, current_user: dict = None):
    """Tüm gruplara otomatik bay oyuncu ata - sıralamaya göre en iyi oyuncular bay olur"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    sport_type = event.get("sport_type") or event.get("sport")
    groups = await db.event_groups.find({"event_id": event_id}).to_list(100)
    
    updated_groups = []
    
    for group in groups:
        participant_ids = group.get("participant_ids", [])
        
        # Tek sayıda oyuncu varsa bay gerekli
        if len(participant_ids) % 2 == 1:
            # Her oyuncunun sıralamasını al
            rankings = []
            for pid in participant_ids:
                score = await get_participant_ranking(db, pid, sport_type)
                user = await db.users.find_one({"id": pid})
                rankings.append({
                    "id": pid,
                    "name": user.get("full_name") if user else "Bilinmeyen",
                    "score": score
                })
            
            # En yüksek skorlu oyuncuyu bay yap
            rankings.sort(key=lambda x: x["score"], reverse=True)
            bye_player = rankings[0] if rankings else None
            
            if bye_player:
                await db.event_groups.update_one(
                    {"id": group["id"]},
                    {"$set": {"bye_participant_id": bye_player["id"], "updated_at": datetime.utcnow()}}
                )
                updated_groups.append({
                    "group_id": group["id"],
                    "group_name": group.get("name"),
                    "bye_player": bye_player
                })
    
    return {
        "status": "success",
        "message": f"{len(updated_groups)} grupta bay oyuncu atandı",
        "updated_groups": updated_groups
    }


@event_management_router.post("/{event_id}/groups/assign-seed-byes")
async def assign_seed_byes(event_id: str, current_user: dict = None):
    """
    Puanı yüksek oyuncuları seri başı olarak gruplara ata.
    Her grupta tek sayıda oyuncu varsa, en yüksek puanlı oyuncu BYE olur.
    Çift/Mix kategorilerde iki oyuncunun toplam puanı dikkate alınır.
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    groups = await db.event_groups.find({"event_id": event_id}).to_list(500)
    if not groups:
        raise HTTPException(status_code=400, detail="Önce gruplar oluşturulmalı")
    
    assigned_byes = []
    
    for group in groups:
        participant_ids = group.get("participant_ids", [])
        category = group.get("category", "").lower()
        is_doubles = "çift" in category or "cift" in category or "mix" in category or "karışık" in category
        
        # Tek sayıda oyuncu/takım varsa BYE gerekli
        if len(participant_ids) % 2 == 1:
            # Her oyuncunun puanını al
            player_scores = []
            
            for pid in participant_ids:
                # event_participants'tan puanı al
                participant = await db.event_participants.find_one({
                    "event_id": event_id,
                    "user_id": pid
                })
                
                user = await db.users.find_one({"id": pid})
                player_name = user.get("full_name", "Bilinmeyen") if user else "Bilinmeyen"
                
                # Puan hesapla
                score = 0
                if participant:
                    score = participant.get("points", 0)
                    
                    # Çift kategorilerde partner puanını da ekle
                    if is_doubles:
                        partner_name = participant.get("doubles_partner") or participant.get("mixed_doubles_partner")
                        if partner_name:
                            # Partner'ı bul ve puanını ekle
                            partner_user = await db.users.find_one({"full_name": partner_name})
                            if partner_user:
                                partner_participant = await db.event_participants.find_one({
                                    "event_id": event_id,
                                    "user_id": partner_user.get("id")
                                })
                                if partner_participant:
                                    score += partner_participant.get("points", 0)
                
                player_scores.append({
                    "id": pid,
                    "name": player_name,
                    "score": score
                })
            
            # En yüksek skorlu oyuncuyu BYE yap
            player_scores.sort(key=lambda x: x["score"], reverse=True)
            bye_player = player_scores[0] if player_scores else None
            
            if bye_player:
                await db.event_groups.update_one(
                    {"id": group["id"]},
                    {"$set": {
                        "bye_participant_id": bye_player["id"],
                        "bye_reason": "seed",
                        "updated_at": datetime.utcnow()
                    }}
                )
                assigned_byes.append({
                    "group_id": group["id"],
                    "group_name": group.get("name", "Grup"),
                    "bye_player_id": bye_player["id"],
                    "bye_player_name": bye_player["name"],
                    "points": bye_player["score"]
                })
    
    return {
        "status": "success",
        "message": f"{len(assigned_byes)} grupta seri başı bye atandı",
        "assigned_byes": assigned_byes
    }


@event_management_router.post("/{event_id}/groups/merge")
async def merge_groups(event_id: str, request: dict = Body(...), current_user: dict = None):
    """
    Seçilen grupları birleştir.
    Az sayıda oyuncu olan grupları tek bir grupta toplar.
    """
    global db
    
    group_ids = request.get("group_ids", [])
    if len(group_ids) < 2:
        raise HTTPException(status_code=400, detail="En az 2 grup seçmelisiniz")
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Seçilen grupları al
    groups_to_merge = await db.event_groups.find({
        "id": {"$in": group_ids},
        "event_id": event_id
    }).to_list(100)
    
    if len(groups_to_merge) < 2:
        raise HTTPException(status_code=400, detail="Birleştirilecek gruplar bulunamadı")
    
    # İlk grubu ana grup olarak kullan
    main_group = groups_to_merge[0]
    merged_participant_ids = list(main_group.get("participant_ids", []))
    merged_group_names = [main_group.get("name", "Grup")]
    
    # Diğer grupların oyuncularını ana gruba ekle
    for group in groups_to_merge[1:]:
        merged_participant_ids.extend(group.get("participant_ids", []))
        merged_group_names.append(group.get("name", "Grup"))
    
    # Tekrar eden oyuncuları kaldır
    merged_participant_ids = list(set(merged_participant_ids))
    
    # Yeni birleşik grup adı
    new_group_name = f"Birleşik: {' + '.join(merged_group_names)}"
    
    # Ana grubu güncelle
    await db.event_groups.update_one(
        {"id": main_group["id"]},
        {"$set": {
            "name": new_group_name,
            "participant_ids": merged_participant_ids,
            "merged_from": group_ids,
            "updated_at": datetime.utcnow()
        }}
    )
    
    # Diğer grupları sil
    other_group_ids = [g["id"] for g in groups_to_merge[1:]]
    await db.event_groups.delete_many({"id": {"$in": other_group_ids}})
    
    # İlgili maçları da sil
    await db.matches.delete_many({"group_id": {"$in": other_group_ids}})
    
    return {
        "status": "success",
        "message": f"{len(groups_to_merge)} grup birleştirildi. Toplam {len(merged_participant_ids)} oyuncu.",
        "merged_group": {
            "id": main_group["id"],
            "name": new_group_name,
            "participant_count": len(merged_participant_ids)
        }
    }


@event_management_router.post("/{event_id}/groups/merge-categories")
async def merge_categories(event_id: str, genders: List[str] = Body(default=[]), age_groups: List[int] = Body(default=[]), game_types: List[str] = Body(default=[]), players_per_group: int = Body(4), distribution_mode: str = Body("add_players"), merged_category_name: str = Body("Birleşik Kategori"), current_user: dict = None):
    """
    Farklı yaş gruplarını tek bir kategori altında birleştirip gruplar oluştur.
    OPEN etkinliklerde yaş grubu seçimi gerekmez - tüm oyuncular tek kategoride gruplanır.
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Event'in game_types'ını kontrol et
    event_game_types = event.get("game_types", [])
    is_open_event = "open" in event_game_types and len(event_game_types) == 1
    
    # OPEN etkinlik değilse yaş grubu kontrolü yap
    if not is_open_event and len(age_groups) < 2:
        raise HTTPException(status_code=400, detail="En az 2 yaş grubu seçmelisiniz")
    
    # Eğer game_types boşsa ve event 'open' ise, 'open' kullan
    if not game_types:
        if is_open_event or len(event_game_types) == 0:
            game_types = ["open"]
            logger.info(f"⚠️ game_types boş, otomatik olarak 'open' kullanıldı")
    
    # Tüm katılımcıları al
    participant_ids = event.get("participants", [])
    if not participant_ids:
        raise HTTPException(status_code=400, detail="Etkinlikte katılımcı yok")
    
    # Participant ID'lerini normalize et (dict ise id al)
    normalized_ids = []
    for pid in participant_ids:
        if isinstance(pid, dict):
            normalized_ids.append(pid.get("id", str(pid)))
        else:
            normalized_ids.append(str(pid))
    participant_ids = normalized_ids
    
    # Event'in UUID id'sini al
    event_uuid = event.get("id", event_id)
    
    # event_participants koleksiyonundan katılımcı detaylarını al
    participants_cursor = db.event_participants.find({
        "event_id": event_uuid,
        "user_id": {"$in": participant_ids}
    })
    participants_list = await participants_cursor.to_list(length=1000)
    
    # Kullanıcı bilgilerini al
    users = await db.users.find({"id": {"$in": participant_ids}}).to_list(length=1000)
    users_map = {u["id"]: u for u in users}
    
    # event_participants koleksiyonunda veri yoksa, direkt participants listesinden oluştur
    if not participants_list:
        logger.info(f"⚠️ event_participants koleksiyonunda veri yok, direkt participants listesinden çekiliyor")
        participants_list = []
        for pid in participant_ids:
            user = users_map.get(pid, {})
            participants_list.append({
                "user_id": pid,
                "game_types": ["open"],  # OPEN etkinlik için varsayılan
                "points": 0
            })
    
    # Filtreleme: Seçilen cinsiyet, yaş grupları ve oyun türlerine göre
    filtered_participants = []
    
    for p in participants_list:
        user_id = p.get("user_id")
        user = users_map.get(user_id, {})
        
        # OPEN etkinlik ise filtre atlama - tüm oyuncuları dahil et
        if is_open_event:
            # Puan bilgisini al
            points = p.get("points", 0)
            filtered_participants.append({
                "user_id": user_id,
                "name": user.get("full_name", "Bilinmeyen"),
                "gender": user.get("gender", ""),
                "age_group": None,
                "game_types": ["open"],
                "points": points
            })
            continue
        
        # Normal etkinlik - filtreleri uygula
        # Cinsiyet kontrolü - genders boşsa filtre atla
        user_gender = user.get("gender", "")
        if genders and user_gender not in genders:
            continue
        
        # Oyun türü kontrolü - "open" seçildiyse tüm oyuncuları kabul et
        user_game_types = p.get("game_types", [])
        if game_types and "open" not in game_types:
            # Open değilse oyun türü kontrolü yap
            if not any(gt in user_game_types for gt in game_types):
                continue
        # "open" seçildiyse oyun türü filtresini atla (herkes katılabilir)
        
        # Yaş grubu kontrolü (birth_year'dan hesapla) - sadece age_groups seçilmişse uygula
        birth_year = user.get("birth_year") or user.get("birthYear")
        if age_groups and len(age_groups) > 0:
            # Yaş grubu filtresi aktif
            if birth_year:
                try:
                    current_year = datetime.now().year
                    age = current_year - int(birth_year)
                    
                    # Yaş aralıkları tanımla
                    age_ranges = {
                        30: (30, 39),
                        40: (40, 49),
                        50: (50, 59),
                        60: (60, 64),
                        65: (65, 69),
                        70: (70, 74),
                        75: (75, 999)
                    }
                    
                    # Kullanıcı seçilen yaş gruplarından birine mi giriyor?
                    user_in_selected_age = False
                    for ag in age_groups:
                        if ag in age_ranges:
                            min_age, max_age = age_ranges[ag]
                            if min_age <= age <= max_age:
                                user_in_selected_age = True
                                break
                    
                    if not user_in_selected_age:
                        continue
                except:
                    continue
            else:
                # birth_year yoksa ve yaş grubu filtresi aktifse atla
                continue
        
        # Puan bilgisini al
        points = p.get("points", 0)
        
        filtered_participants.append({
            "user_id": user_id,
            "name": user.get("full_name", "Bilinmeyen"),
            "gender": user_gender,
            "points": points,
            "game_types": user_game_types
        })
    
    if not filtered_participants:
        raise HTTPException(
            status_code=400, 
            detail=f"Seçilen kriterlere uyan katılımcı bulunamadı. (Cinsiyet: {genders}, Yaş: {age_groups}, Oyun Türü: {game_types})"
        )
    
    # Katılımcıları puanlarına göre sırala
    filtered_participants.sort(key=lambda x: x["points"], reverse=True)
    
    # Çift kategorisi mi kontrol et
    is_doubles_category = any(gt in ["cift", "double", "doubles", "karisik_cift", "mixed", "mixed_doubles"] for gt in game_types)
    
    # Grup sayısını hesapla
    total_players = len(filtered_participants)
    
    # Çift kategorilerinde önce çift sayısını hesapla, sonra grup sayısını belirle
    # players_per_group çift kategorilerinde "çift sayısı" olarak yorumlanır
    if is_doubles_category:
        # Çiftlerin oluşturulacağı için, önce tahmini çift sayısını hesapla
        # (eşi olmayanlar hariç tutulacak, bu yüzden kesin sayı sonra belli olacak)
        estimated_pairs = total_players // 2  # Tahmini çift sayısı
        pairs_per_group_target = players_per_group  # Kullanıcının girdiği değer = çift sayısı
        group_count = max(1, math.ceil(estimated_pairs / pairs_per_group_target) if pairs_per_group_target > 0 else 1)
        logging.info(f"🎾 Kategori Birleştir: Tahmini {estimated_pairs} çift, grup başına {pairs_per_group_target} çift hedefi")
    else:
        group_count = max(1, total_players // players_per_group)
    
    # Dağıtım moduna göre ayarla
    if distribution_mode == "reduce_groups":
        # Tam dolacak kadar grup oluştur
        if is_doubles_category:
            estimated_pairs = total_players // 2
            group_count = max(1, estimated_pairs // players_per_group)
        else:
            group_count = max(1, total_players // players_per_group)
    else:
        # Fazla oyuncuları gruplara ekle
        pass
    
    # Grupları oluştur
    created_groups = []
    group_names = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    
    for i in range(group_count):
        group_name = f"{merged_category_name} - Grup {group_names[i] if i < 26 else str(i+1)}"
        group_id = str(uuid.uuid4())
        
        group_doc = {
            "id": group_id,
            "event_id": event_id,
            "name": group_name,
            "category": merged_category_name,
            "participant_ids": [],
            "pairs": [] if is_doubles_category else None,
            "is_doubles": is_doubles_category,
            "merged_age_groups": age_groups,
            "merged_genders": genders,
            "game_types": game_types,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.event_groups.insert_one(group_doc)
        created_groups.append(group_doc)
    
    # Çift kategorisi ise önce partnerleri bul ve pairs oluştur
    if is_doubles_category:
        # Event UUID'sini al
        event_uuid = event.get("id", event_id)
        
        # Partner bilgilerini al
        participant_user_ids = [p["user_id"] for p in filtered_participants]
        eps = await db.event_participants.find({
            "event_id": event_uuid,
            "user_id": {"$in": participant_user_ids}
        }).to_list(1000)
        ep_map = {ep["user_id"]: ep for ep in eps}
        
        # Partner alanını belirle
        partner_field = "doubles_partner_id" if any(gt in ["cift", "double", "doubles"] for gt in game_types) else "mixed_partner_id"
        
        # Çiftleri oluştur - Eşi olmayanları hariç tut!
        pairs = []
        processed_ids = set()
        skipped_singles = []  # Eşi olmayan oyuncular
        
        for player in filtered_participants:
            pid = player["user_id"]
            if pid in processed_ids:
                continue
            
            ep = ep_map.get(pid, {})
            partner_id = ep.get(partner_field)
            
            if partner_id and partner_id in participant_user_ids and partner_id not in processed_ids:
                # Partner'ı bul
                partner_player = next((p for p in filtered_participants if p["user_id"] == partner_id), None)
                if partner_player:
                    name1 = player["name"]
                    name2 = partner_player["name"]
                    
                    # Alfabetik sıralama
                    if name1 > name2:
                        name1, name2 = name2, name1
                        pid, partner_id = partner_id, pid
                    
                    pair_name = f"{name1} - {name2}"
                    pair_id = f"{min(pid, partner_id)}_{max(pid, partner_id)}"
                    
                    pairs.append({
                        "pair_id": pair_id,
                        "pair_name": pair_name,
                        "player1_id": pid,
                        "player2_id": partner_id,
                        "player1_name": name1,
                        "player2_name": name2,
                        "points": player["points"] + partner_player["points"]
                    })
                    
                    processed_ids.add(pid)
                    processed_ids.add(partner_id)
            else:
                # Partneri olmayan oyuncu - Gruplara dahil etme!
                skipped_singles.append(player["name"])
                processed_ids.add(pid)
        
        if skipped_singles:
            logging.info(f"⚠️ Kategori Birleştir: Eşi olmayan {len(skipped_singles)} oyuncu gruplara dahil edilmedi: {', '.join(skipped_singles[:10])}{'...' if len(skipped_singles) > 10 else ''}")
        
        # Çiftleri puanlarına göre sırala
        pairs.sort(key=lambda x: x["points"], reverse=True)
        
        # Çiftleri gruplara dağıt
        for idx, pair in enumerate(pairs):
            cycle = idx // group_count
            position = idx % group_count
            
            if cycle % 2 == 1:
                group_idx = group_count - 1 - position
            else:
                group_idx = position
            
            # Grubu güncelle
            pair_data = {
                "pair_id": pair["pair_id"],
                "pair_name": pair["pair_name"],
                "player1_id": pair["player1_id"],
                "player2_id": pair["player2_id"],
                "player1_name": pair["player1_name"],
                "player2_name": pair["player2_name"]
            }
            
            update_data = {
                "$push": {
                    "pairs": pair_data,
                    "participant_ids": {"$each": [pair["player1_id"]] + ([pair["player2_id"]] if pair["player2_id"] else [])}
                }
            }
            
            await db.event_groups.update_one(
                {"id": created_groups[group_idx]["id"]},
                update_data
            )
        
        total_pairs = len(pairs)
        return {
            "status": "success",
            "message": f"'{merged_category_name}' kategorisi oluşturuldu. {total_pairs} çift {group_count} gruba dağıtıldı.",
            "category": merged_category_name,
            "total_players": total_pairs,
            "groups_created": group_count,
            "age_groups_merged": age_groups,
            "is_doubles": True
        }
    
    # Oyuncuları yılan sistemiyle gruplara dağıt (tek kategorisi)
    for idx, player in enumerate(filtered_participants):
        # Yılan sistemi: 0,1,2,3 -> 3,2,1,0 -> 0,1,2,3 ...
        cycle = idx // group_count
        position = idx % group_count
        
        if cycle % 2 == 1:
            # Ters yön
            group_idx = group_count - 1 - position
        else:
            # Normal yön
            group_idx = position
        
        # Grubu güncelle
        await db.event_groups.update_one(
            {"id": created_groups[group_idx]["id"]},
            {"$push": {"participant_ids": player["user_id"]}}
        )
    
    return {
        "status": "success",
        "message": f"'{merged_category_name}' kategorisi oluşturuldu. {total_players} oyuncu {group_count} gruba dağıtıldı.",
        "category": merged_category_name,
        "total_players": total_players,
        "groups_created": group_count,
        "age_groups_merged": age_groups
    }


@event_management_router.post("/{event_id}/groups/distribute-by-seed")
async def distribute_participants_by_seed(event_id: str, category: str = None, current_user: dict = None):
    """
    Aynı kategorideki alt gruplar arasında katılımcıları seed sırasına göre yılan şeklinde dağıt.
    SADECE aynı kategorideki gruplar etkilenir, farklı kategoriler karışmaz.
    
    Örnek: "Tekler - Erkekler" kategorisinde 2 alt grup varsa:
    - Grup A: seed 1, 4, 5, 8
    - Grup B: seed 2, 3, 6, 7
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    all_groups = await db.event_groups.find({"event_id": event_id}).to_list(100)
    if not all_groups:
        raise HTTPException(status_code=400, detail="Önce gruplar oluşturulmalı")
    
    sport_type = event.get("sport_type") or event.get("sport")
    
    # Grupları kategoriye göre grupla
    category_groups = {}
    for group in all_groups:
        cat = group.get("category") or group.get("name", "Diğer")
        if cat not in category_groups:
            category_groups[cat] = []
        category_groups[cat].append(group)
    
    # Belirli bir kategori seçildiyse sadece onu işle
    if category:
        if category not in category_groups:
            raise HTTPException(status_code=400, detail=f"'{category}' kategorisi bulunamadı")
        categories_to_process = {category: category_groups[category]}
    else:
        categories_to_process = category_groups
    
    result_summary = []
    total_distributed = 0
    
    for cat_name, groups in categories_to_process.items():
        # Bu kategorideki tüm katılımcıları topla
        category_participants = set()
        for group in groups:
            category_participants.update(group.get("participant_ids", []))
        
        if not category_participants:
            continue
        
        # Eğer sadece 1 grup varsa dağıtıma gerek yok
        if len(groups) <= 1:
            result_summary.append({
                "category": cat_name,
                "message": "Tek grup, dağıtım yapılmadı",
                "groups": [{"name": g.get("name"), "count": len(g.get("participant_ids", []))} for g in groups]
            })
            continue
        
        # Her katılımcının seed skorunu al
        participants_with_scores = []
        for pid in category_participants:
            score = await get_participant_ranking(db, pid, sport_type, event_id)
            user = await db.users.find_one({"id": pid})
            participants_with_scores.append({
                "id": pid,
                "name": user.get("full_name") if user else "Bilinmeyen",
                "score": score
            })
        
        # Score'a göre sırala (en yüksek önce)
        participants_with_scores.sort(key=lambda x: x["score"], reverse=True)
        
        # Yılan şeklinde dağıt (snake draft) - SADECE bu kategorideki gruplar arasında
        num_groups = len(groups)
        group_assignments = {g["id"]: [] for g in groups}
        group_list = [g["id"] for g in groups]
        
        direction = 1
        group_idx = 0
        
        for participant in participants_with_scores:
            group_id = group_list[group_idx]
            group_assignments[group_id].append(participant["id"])
            
            group_idx += direction
            if group_idx >= num_groups:
                group_idx = num_groups - 1
                direction = -1
            elif group_idx < 0:
                group_idx = 0
                direction = 1
        
        # Bu kategorideki grupları güncelle
        for group in groups:
            await db.event_groups.update_one(
                {"id": group["id"]},
                {"$set": {
                    "participant_ids": group_assignments[group["id"]],
                    "updated_at": datetime.utcnow()
                }}
            )
        
        total_distributed += len(category_participants)
        result_summary.append({
            "category": cat_name,
            "participant_count": len(category_participants),
            "groups": [{"name": g.get("name"), "count": len(group_assignments[g["id"]])} for g in groups]
        })
    
    return {
        "status": "success",
        "message": f"{total_distributed} katılımcı kategorilere göre dağıtıldı",
        "categories": result_summary
    }


@event_management_router.post("/{event_id}/groups/{group_id}/set-bye")
async def set_group_bye(
    event_id: str, 
    group_id: str, 
    participant_id: str = Query(..., description="Bay olacak oyuncunun ID'si, boş bırakılırsa bay kaldırılır"),
    current_user: dict = None
):
    """Gruba manuel bay oyuncu ata veya kaldır (tek bay - geriye uyumluluk)"""
    global db
    
    group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Eğer boş string veya "none" gönderildiyse bay'ı kaldır
    if not participant_id or participant_id.lower() == "none":
        await db.event_groups.update_one(
            {"id": group_id},
            {"$set": {"bye_participant_id": None, "bye_participant_ids": [], "updated_at": datetime.utcnow()}}
        )
        return {"status": "success", "message": "Bay oyuncu kaldırıldı"}
    
    # Oyuncu bu grupta mı kontrol et
    if participant_id not in group.get("participant_ids", []):
        raise HTTPException(status_code=400, detail="Bu oyuncu bu grupta değil")
    
    # Bay oyuncuyu ayarla (hem tek hem çoklu için)
    await db.event_groups.update_one(
        {"id": group_id},
        {"$set": {
            "bye_participant_id": participant_id, 
            "bye_participant_ids": [participant_id],
            "updated_at": datetime.utcnow()
        }}
    )
    
    # Oyuncu adını al
    user = await db.users.find_one({"id": participant_id})
    player_name = user.get("full_name") if user else "Bilinmeyen"
    
    return {
        "status": "success",
        "message": f"{player_name} bay oyuncu olarak atandı",
        "bye_participant_id": participant_id,
        "bye_participant_name": player_name
    }


class MultipleBayRequest(BaseModel):
    """Çoklu bay oyuncu seçimi modeli"""
    participant_ids: List[str]


@event_management_router.post("/{event_id}/groups/{group_id}/set-byes")
async def set_group_multiple_byes(
    event_id: str, 
    group_id: str, 
    data: MultipleBayRequest,
    current_user: dict = None
):
    """Gruba birden fazla bay oyuncu ata"""
    global db
    
    group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    group_participant_ids = group.get("participant_ids", [])
    
    # Tüm oyuncuların bu grupta olduğunu kontrol et
    invalid_ids = [pid for pid in data.participant_ids if pid not in group_participant_ids]
    if invalid_ids:
        raise HTTPException(status_code=400, detail=f"Bu oyuncular bu grupta değil: {invalid_ids}")
    
    # Bay oyuncuları ayarla
    await db.event_groups.update_one(
        {"id": group_id},
        {"$set": {
            "bye_participant_ids": data.participant_ids,
            "bye_participant_id": data.participant_ids[0] if data.participant_ids else None,  # Geriye uyumluluk
            "updated_at": datetime.utcnow()
        }}
    )
    
    # Oyuncu isimlerini al
    bay_names = []
    for pid in data.participant_ids:
        user = await db.users.find_one({"id": pid})
        if user:
            bay_names.append(user.get("full_name", "Bilinmeyen"))
    
    return {
        "status": "success",
        "message": f"{len(data.participant_ids)} oyuncu bay olarak atandı",
        "bye_participant_ids": data.participant_ids,
        "bye_participant_names": bay_names
    }


@event_management_router.post("/{event_id}/groups/{group_id}/toggle-bye")
async def toggle_group_bye(
    event_id: str, 
    group_id: str, 
    participant_id: str = Query(..., description="Bay durumu değiştirilecek oyuncunun ID'si"),
    current_user: dict = None
):
    """Oyuncunun bay durumunu toggle et (bay ise kaldır, değilse ekle)"""
    global db
    
    group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Oyuncu bu grupta mı kontrol et
    if participant_id not in group.get("participant_ids", []):
        raise HTTPException(status_code=400, detail="Bu oyuncu bu grupta değil")
    
    current_byes = group.get("bye_participant_ids", [])
    user = await db.users.find_one({"id": participant_id})
    player_name = user.get("full_name") if user else "Bilinmeyen"
    
    if participant_id in current_byes:
        # Bay'dan çıkar
        current_byes.remove(participant_id)
        message = f"{player_name} bay listesinden çıkarıldı"
        is_bye = False
    else:
        # Bay olarak ekle
        current_byes.append(participant_id)
        message = f"{player_name} bay olarak eklendi"
        is_bye = True
    
    # Güncelle
    await db.event_groups.update_one(
        {"id": group_id},
        {"$set": {
            "bye_participant_ids": current_byes,
            "bye_participant_id": current_byes[0] if current_byes else None,  # Geriye uyumluluk
            "updated_at": datetime.utcnow()
        }}
    )
    
    return {
        "status": "success",
        "message": message,
        "participant_id": participant_id,
        "is_bye": is_bye,
        "total_byes": len(current_byes),
        "bye_participant_ids": current_byes
    }

@event_management_router.get("/{event_id}/groups/{group_id}/bye-suggestions")
async def get_bye_suggestions(event_id: str, group_id: str, current_user: dict = None):
    """Grup için bay oyuncu önerilerini getir - sıralamaya göre"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    sport_type = event.get("sport_type") or event.get("sport")
    participant_ids = group.get("participant_ids", [])
    
    # Her oyuncunun sıralamasını al
    suggestions = []
    for pid in participant_ids:
        score = await get_participant_ranking(db, pid, sport_type)
        user = await db.users.find_one({"id": pid})
        suggestions.append({
            "id": pid,
            "name": user.get("full_name") if user else "Bilinmeyen",
            "avatar": user.get("profile_image") if user else None,
            "score": score,
            "wins": 0,
            "matches_played": 0
        })
        
        # İstatistikleri ekle
        standings = await db.event_standings.find({"participant_id": pid}).to_list(100)
        total_wins = sum(s.get("wins", 0) for s in standings)
        total_matches = sum(s.get("matches_played", 0) for s in standings)
        suggestions[-1]["wins"] = total_wins
        suggestions[-1]["matches_played"] = total_matches
    
    # Skora göre sırala (en yüksek = bay için en uygun)
    suggestions.sort(key=lambda x: x["score"], reverse=True)
    
    return {
        "group_id": group_id,
        "group_name": group.get("name"),
        "current_bye": group.get("bye_participant_id"),
        "suggestions": suggestions,
        "needs_bye": len(participant_ids) % 2 == 1
    }

# ================== ÇİFT/TAKIM EŞLEŞTİRME ENDPOİNTLERİ ==================

class PairCreate(BaseModel):
    """Çift/Takım oluşturma modeli"""
    player1_id: str
    player2_id: str
    team_name: Optional[str] = None

class PairUpdate(BaseModel):
    """Çift/Takım güncelleme modeli"""
    player1_id: Optional[str] = None
    player2_id: Optional[str] = None
    team_name: Optional[str] = None

@event_management_router.get("/{event_id}/groups/{group_id}/pairs")
async def get_group_pairs(event_id: str, group_id: str, current_user: dict = None):
    """Gruptaki çiftleri/takımları getir"""
    global db
    
    group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Çiftleri getir
    pairs = await db.event_pairs.find({
        "event_id": event_id,
        "group_id": group_id
    }).to_list(100)
    
    # Oyuncu bilgilerini ekle
    result = []
    for pair in pairs:
        pair.pop("_id", None)
        
        # Oyuncu 1 bilgisi
        player1 = await db.users.find_one({"id": pair.get("player1_id")})
        pair["player1"] = {
            "id": pair.get("player1_id"),
            "name": player1.get("full_name") if player1 else "Bilinmeyen",
            "avatar": player1.get("profile_image") if player1 else None,
            "gender": player1.get("gender") if player1 else None
        }
        
        # Oyuncu 2 bilgisi
        player2 = await db.users.find_one({"id": pair.get("player2_id")})
        pair["player2"] = {
            "id": pair.get("player2_id"),
            "name": player2.get("full_name") if player2 else "Bilinmeyen",
            "avatar": player2.get("profile_image") if player2 else None,
            "gender": player2.get("gender") if player2 else None
        }
        
        result.append(pair)
    
    # Eşleşmemiş oyuncuları bul
    paired_player_ids = set()
    for pair in pairs:
        paired_player_ids.add(pair.get("player1_id"))
        paired_player_ids.add(pair.get("player2_id"))
    
    unpaired_players = []
    for pid in group.get("participant_ids", []):
        if pid not in paired_player_ids:
            user = await db.users.find_one({"id": pid})
            if user:
                unpaired_players.append({
                    "id": pid,
                    "name": user.get("full_name"),
                    "avatar": user.get("profile_image"),
                    "gender": user.get("gender")
                })
    
    return {
        "group_id": group_id,
        "group_name": group.get("name"),
        "category": group.get("category"),
        "is_doubles": group.get("is_doubles", False),
        "is_mixed": group.get("is_mixed", False),
        "pairs": result,
        "unpaired_players": unpaired_players,
        "total_players": len(group.get("participant_ids", [])),
        "total_pairs": len(result)
    }

@event_management_router.post("/{event_id}/groups/{group_id}/pairs")
async def create_pair(event_id: str, group_id: str, pair_data: PairCreate):
    """Yeni çift/takım oluştur"""
    global db
    
    group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Oyuncuların grupta olduğunu kontrol et
    participant_ids = group.get("participant_ids", [])
    if pair_data.player1_id not in participant_ids:
        raise HTTPException(status_code=400, detail="Oyuncu 1 bu grupta değil")
    if pair_data.player2_id not in participant_ids:
        raise HTTPException(status_code=400, detail="Oyuncu 2 bu grupta değil")
    
    # Oyuncuların başka çiftte olmadığını kontrol et
    existing_pair = await db.event_pairs.find_one({
        "event_id": event_id,
        "group_id": group_id,
        "$or": [
            {"player1_id": pair_data.player1_id},
            {"player2_id": pair_data.player1_id},
            {"player1_id": pair_data.player2_id},
            {"player2_id": pair_data.player2_id}
        ]
    })
    
    if existing_pair:
        raise HTTPException(status_code=400, detail="Oyunculardan biri zaten bir çiftte")
    
    # Oyuncu bilgilerini al
    player1 = await db.users.find_one({"id": pair_data.player1_id})
    player2 = await db.users.find_one({"id": pair_data.player2_id})
    
    # Takım adı oluştur
    team_name = pair_data.team_name
    if not team_name:
        p1_name = player1.get("full_name", "Oyuncu 1") if player1 else "Oyuncu 1"
        p2_name = player2.get("full_name", "Oyuncu 2") if player2 else "Oyuncu 2"
        # İsimlerin ilk kelimelerini al
        p1_first = p1_name.split()[0] if p1_name else "?"
        p2_first = p2_name.split()[0] if p2_name else "?"
        team_name = f"{p1_first} & {p2_first}"
    
    pair_id = str(uuid.uuid4())
    pair = {
        "id": pair_id,
        "event_id": event_id,
        "group_id": group_id,
        "player1_id": pair_data.player1_id,
        "player2_id": pair_data.player2_id,
        "team_name": team_name,
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.event_pairs.insert_one(pair)
    pair.pop("_id", None)
    
    # Oyuncu bilgilerini ekle
    pair["player1"] = {
        "id": pair_data.player1_id,
        "name": player1.get("full_name") if player1 else "Bilinmeyen",
        "avatar": player1.get("profile_image") if player1 else None
    }
    pair["player2"] = {
        "id": pair_data.player2_id,
        "name": player2.get("full_name") if player2 else "Bilinmeyen",
        "avatar": player2.get("profile_image") if player2 else None
    }
    
    return {"success": True, "pair": pair, "message": f"'{team_name}' çifti oluşturuldu"}

@event_management_router.put("/{event_id}/groups/{group_id}/pairs/{pair_id}")
async def update_pair(event_id: str, group_id: str, pair_id: str, pair_data: PairUpdate, current_user: dict = None):
    """Çift/takımı güncelle"""
    global db
    
    pair = await db.event_pairs.find_one({"id": pair_id, "group_id": group_id})
    if not pair:
        raise HTTPException(status_code=404, detail="Çift bulunamadı")
    
    update_data = {"updated_at": datetime.utcnow()}
    
    if pair_data.team_name:
        update_data["team_name"] = pair_data.team_name
    
    if pair_data.player1_id:
        # Oyuncunun başka çiftte olmadığını kontrol et
        existing = await db.event_pairs.find_one({
            "event_id": event_id,
            "group_id": group_id,
            "id": {"$ne": pair_id},
            "$or": [
                {"player1_id": pair_data.player1_id},
                {"player2_id": pair_data.player1_id}
            ]
        })
        if existing:
            raise HTTPException(status_code=400, detail="Oyuncu 1 zaten başka bir çiftte")
        update_data["player1_id"] = pair_data.player1_id
    
    if pair_data.player2_id:
        existing = await db.event_pairs.find_one({
            "event_id": event_id,
            "group_id": group_id,
            "id": {"$ne": pair_id},
            "$or": [
                {"player1_id": pair_data.player2_id},
                {"player2_id": pair_data.player2_id}
            ]
        })
        if existing:
            raise HTTPException(status_code=400, detail="Oyuncu 2 zaten başka bir çiftte")
        update_data["player2_id"] = pair_data.player2_id
    
    await db.event_pairs.update_one({"id": pair_id}, {"$set": update_data})
    
    updated_pair = await db.event_pairs.find_one({"id": pair_id})
    updated_pair.pop("_id", None)
    
    return {"success": True, "pair": updated_pair, "message": "Çift güncellendi"}


class GroupUpdate(BaseModel):
    name: Optional[str] = None


@event_management_router.patch("/{event_id}/groups/{group_id}")
async def update_group(event_id: str, group_id: str, name: str = Body(..., embed=True), current_user: dict = None):
    """Grup bilgilerini güncelle (isim değiştir)"""
    global db
    
    # Grubu bul
    group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Grup adı boş olamaz")
    
    # Güncelle
    await db.event_groups.update_one(
        {"id": group_id},
        {"$set": {"name": name.strip()}}
    )
    
    return {"success": True, "message": "Grup güncellendi"}


@event_management_router.delete("/{event_id}/groups/all")
async def delete_all_groups(event_id: str, current_user: dict = None):
    """Etkinliğe ait tüm grupları sil - İlgili maçları ve çiftleri de siler"""
    global db
    
    # Etkinliği kontrol et
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Etkinliğe ait grupları bul
    groups = await db.event_groups.find({"event_id": event_id}).to_list(1000)
    group_count = len(groups)
    
    if group_count == 0:
        raise HTTPException(status_code=400, detail="Silinecek grup bulunamadı")
    
    # Tüm grup ID'lerini al
    group_ids = [g.get("id") for g in groups]
    
    # İlgili maçları sil
    matches_deleted = await db.matches.delete_many({"group_id": {"$in": group_ids}})
    
    # İlgili çiftleri sil
    pairs_deleted = await db.event_pairs.delete_many({"group_id": {"$in": group_ids}})
    
    # Tüm grupları sil
    groups_deleted = await db.event_groups.delete_many({"event_id": event_id})
    
    return {
        "success": True, 
        "message": f"{group_count} grup silindi",
        "deleted": {
            "groups": groups_deleted.deleted_count,
            "matches": matches_deleted.deleted_count,
            "pairs": pairs_deleted.deleted_count
        }
    }


@event_management_router.delete("/{event_id}/groups/{group_id}")
async def delete_group(event_id: str, group_id: str, current_user: dict = None):
    """Grubu sil - İlgili maçları ve çiftleri de siler"""
    global db
    
    # Grubu bul
    group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # İlgili maçları sil
    await db.matches.delete_many({"group_id": group_id})
    
    # İlgili çiftleri sil
    await db.event_pairs.delete_many({"group_id": group_id})
    
    # Grubu sil
    await db.event_groups.delete_one({"id": group_id})
    
    return {"success": True, "message": f"'{group.get('name', 'Grup')}' silindi"}


@event_management_router.delete("/{event_id}/groups/{group_id}/pairs/{pair_id}")
async def delete_pair(event_id: str, group_id: str, pair_id: str, current_user: dict = None):
    """Çift/takımı sil"""
    global db
    
    pair = await db.event_pairs.find_one({"id": pair_id, "group_id": group_id})
    if not pair:
        raise HTTPException(status_code=404, detail="Çift bulunamadı")
    
    await db.event_pairs.delete_one({"id": pair_id})
    
    return {"success": True, "message": "Çift silindi"}

@event_management_router.post("/{event_id}/groups/{group_id}/auto-pair")
async def auto_pair_players(event_id: str, group_id: str):
    """Oyuncuları otomatik eşleştir - Puana göre en yakın oyuncuları eşleştirir"""
    global db
    
    group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Mevcut çiftleri sil
    await db.event_pairs.delete_many({"event_id": event_id, "group_id": group_id})
    
    participant_ids = group.get("participant_ids", [])
    is_mixed = group.get("is_mixed", False)
    
    # Oyuncu bilgilerini ve puanlarını al
    players = []
    for pid in participant_ids:
        user = await db.users.find_one({"id": pid})
        if user:
            # Kullanıcının puanını al (yoksa varsayılan 1000)
            rating = user.get("rating", user.get("score", 1000))
            if not rating:
                rating = 1000
            
            players.append({
                "id": pid,
                "name": user.get("full_name"),
                "gender": user.get("gender", "Erkek"),
                "avatar": user.get("profile_image"),
                "rating": rating
            })
    
    created_pairs = []
    
    if is_mixed:
        # Karışık çift: Erkek + Kadın eşleştir (puana göre)
        erkekler = [p for p in players if p["gender"] in ["Erkek", "erkek", "male", "Male"]]
        kadinlar = [p for p in players if p["gender"] in ["Kadın", "kadın", "female", "Female"]]
        
        # Puana göre sırala
        erkekler.sort(key=lambda x: x["rating"], reverse=True)
        kadinlar.sort(key=lambda x: x["rating"], reverse=True)
        
        min_count = min(len(erkekler), len(kadinlar))
        for i in range(min_count):
            pair_id = str(uuid.uuid4())
            p1_first = erkekler[i]["name"].split()[0] if erkekler[i]["name"] else "?"
            p2_first = kadinlar[i]["name"].split()[0] if kadinlar[i]["name"] else "?"
            combined_rating = (erkekler[i]["rating"] + kadinlar[i]["rating"]) // 2
            
            pair = {
                "id": pair_id,
                "event_id": event_id,
                "group_id": group_id,
                "player1_id": erkekler[i]["id"],
                "player2_id": kadinlar[i]["id"],
                "team_name": f"{p1_first} & {p2_first}",
                "team_rating": combined_rating,
                "status": "active",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            await db.event_pairs.insert_one(pair)
            pair.pop("_id", None)
            pair["player1"] = erkekler[i]
            pair["player2"] = kadinlar[i]
            created_pairs.append(pair)
    else:
        # Normal çift: Puana göre en yakın oyuncuları eşleştir
        # Puana göre sırala
        players.sort(key=lambda x: x["rating"], reverse=True)
        
        # En yakın puanlı oyuncuları eşleştir (1-2, 3-4, 5-6 şeklinde)
        for i in range(0, len(players) - 1, 2):
            pair_id = str(uuid.uuid4())
            p1_first = players[i]["name"].split()[0] if players[i]["name"] else "?"
            p2_first = players[i+1]["name"].split()[0] if players[i+1]["name"] else "?"
            combined_rating = (players[i]["rating"] + players[i+1]["rating"]) // 2
            
            pair = {
                "id": pair_id,
                "event_id": event_id,
                "group_id": group_id,
                "player1_id": players[i]["id"],
                "player2_id": players[i+1]["id"],
                "team_name": f"{p1_first} & {p2_first}",
                "team_rating": combined_rating,
                "status": "active",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            await db.event_pairs.insert_one(pair)
            pair.pop("_id", None)
            pair["player1"] = players[i]
            pair["player2"] = players[i+1]
            created_pairs.append(pair)
    
    # Eşleşmemiş oyuncuları bul
    paired_ids = set()
    for p in created_pairs:
        paired_ids.add(p["player1_id"])
        paired_ids.add(p["player2_id"])
    
    unpaired = [p for p in players if p["id"] not in paired_ids]
    
    return {
        "success": True,
        "pairs": created_pairs,
        "unpaired_players": unpaired,
        "message": f"{len(created_pairs)} çift oluşturuldu (puana göre eşleştirildi)"
    }


# ================== GRUP OYUNCU YÖNETİMİ ==================

class MoveParticipantRequest(BaseModel):
    """Oyuncu taşıma modeli"""
    participant_id: str
    target_group_id: str


class AddParticipantRequest(BaseModel):
    """Gruba oyuncu ekleme modeli"""
    user_id: str
    skip_payment: bool = True  # Ödeme kontrolünü atla


class RemoveParticipantRequest(BaseModel):
    """Gruptan oyuncu çıkarma modeli"""
    participant_id: str
    remove_from_event: bool = False  # Etkinlikten de çıkarsın mı?


@event_management_router.post("/{event_id}/groups/{group_id}/move-participant")
async def move_participant_to_group(
    event_id: str,
    group_id: str,
    request_body: MoveParticipantRequest
):
    """Oyuncuyu veya çifti bir gruptan diğerine taşı"""
    global db
    
    participant_id = request_body.participant_id
    target_group_id = request_body.target_group_id
    
    logger.info(f"🔄 Move participant request: event={event_id}, source_group={group_id}")
    logger.info(f"🔄 Request data: participant_id={participant_id}, target_group_id={target_group_id}")
    
    # Önce kaynak grubu ID ile bul
    source_group = await db.event_groups.find_one({
        "id": group_id,
        "event_id": event_id
    })
    
    if not source_group:
        raise HTTPException(status_code=404, detail="Kaynak grup bulunamadı")
    
    # Hedef grubu bul
    target_group = await db.event_groups.find_one({
        "id": target_group_id,
        "event_id": event_id
    })
    
    if not target_group:
        raise HTTPException(status_code=404, detail="Hedef grup bulunamadı")
    
    # Aynı gruba taşıma kontrolü
    if source_group["id"] == target_group_id:
        raise HTTPException(status_code=400, detail="Oyuncu zaten bu grupta")
    
    # Çift grubu mu kontrol et
    is_doubles = source_group.get("is_doubles", False)
    player_name = "Bilinmeyen"
    
    if is_doubles or source_group.get("pairs"):
        # Çift grubu - pairs listesinde ara
        source_pairs = source_group.get("pairs", [])
        pair_to_move = None
        pair_index = -1
        
        for i, pair in enumerate(source_pairs):
            # pair_id veya birleşik ID ile eşleştir
            if pair.get("pair_id") == participant_id or pair.get("id") == participant_id:
                pair_to_move = pair
                pair_index = i
                break
            # player1_id_player2_id formatını kontrol et
            combined_id = f"{pair.get('player1_id')}_{pair.get('player2_id')}"
            if combined_id == participant_id:
                pair_to_move = pair
                pair_index = i
                break
        
        if pair_to_move is None:
            raise HTTPException(status_code=404, detail="Çift bu grupta bulunamadı")
        
        player_name = pair_to_move.get("pair_name", f"{pair_to_move.get('player1_name', '')} - {pair_to_move.get('player2_name', '')}")
        
        # Kaynak gruptan çıkar
        source_pairs.pop(pair_index)
        await db.event_groups.update_one(
            {"id": source_group["id"]},
            {"$set": {"pairs": source_pairs, "updated_at": datetime.utcnow()}}
        )
        
        # Hedef gruba ekle
        target_pairs = target_group.get("pairs", [])
        target_pairs.append(pair_to_move)
        await db.event_groups.update_one(
            {"id": target_group_id},
            {"$set": {"pairs": target_pairs, "updated_at": datetime.utcnow()}}
        )
        
        logger.info(f"✅ Çift taşındı: {player_name} ({source_group.get('name')} → {target_group.get('name')})")
    else:
        # Tek oyuncu grubu - participant_ids listesinde ara
        source_group_with_participant = await db.event_groups.find_one({
            "id": group_id,
            "event_id": event_id,
            "participant_ids": participant_id
        })
        
        if not source_group_with_participant:
            # Eğer bulamazsa, oyuncunun olduğu herhangi bir gruptan almayı dene
            source_group_with_participant = await db.event_groups.find_one({
                "event_id": event_id,
                "participant_ids": participant_id
            })
            if not source_group_with_participant:
                raise HTTPException(status_code=404, detail="Oyuncu herhangi bir grupta bulunamadı")
            source_group = source_group_with_participant
        
        # Kaynak gruptan çıkar
        source_participants = source_group.get("participant_ids", [])
        if participant_id in source_participants:
            source_participants.remove(participant_id)
        await db.event_groups.update_one(
            {"id": source_group["id"]},
            {"$set": {"participant_ids": source_participants, "updated_at": datetime.utcnow()}}
        )
        
        # Hedef gruba ekle
        target_participants = target_group.get("participant_ids", [])
        if participant_id not in target_participants:
            target_participants.append(participant_id)
        await db.event_groups.update_one(
            {"id": target_group_id},
            {"$set": {"participant_ids": target_participants, "updated_at": datetime.utcnow()}}
        )
        
        # Kullanıcı bilgisi
        user = await db.users.find_one({"id": participant_id})
        player_name = user.get("full_name") if user else "Bilinmeyen"
    
    return {
        "status": "success",
        "message": f"{player_name} taşındı: {source_group.get('name')} → {target_group.get('name')}",
        "participant_id": participant_id,
        "from_group": source_group.get("name"),
        "to_group": target_group.get("name")
    }


@event_management_router.post("/{event_id}/groups/{group_id}/add-participant")
async def add_participant_to_group(
    event_id: str,
    group_id: str,
    user_id: str = Query(..., description="Eklenecek kullanıcının ID'si"),
    current_user: dict = None
):
    """Gruba manuel olarak oyuncu ekle (ödeme durumundan bağımsız)"""
    global db
    
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id gerekli")
    
    # Etkinlik kontrolü
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Grup kontrolü
    group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Kullanıcı kontrolü
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Zaten grupta mı?
    if user_id in group.get("participant_ids", []):
        raise HTTPException(status_code=400, detail="Kullanıcı zaten bu grupta")
    
    # Gruba ekle
    group_participants = group.get("participant_ids", [])
    group_participants.append(user_id)
    await db.event_groups.update_one(
        {"id": group_id},
        {"$set": {"participant_ids": group_participants, "updated_at": datetime.utcnow()}}
    )
    
    # Etkinliğe de ekle (yoksa)
    event_participants = event.get("participants", [])
    if user_id not in event_participants:
        event_participants.append(user_id)
        await db.events.update_one(
            {"id": event_id},
            {"$set": {
                "participants": event_participants,
                "participant_count": len(event_participants),
                "updated_at": datetime.utcnow().isoformat()
            }}
        )
    
    # ===== BİLDİRİMLER =====
    event_title = event.get('title', event.get('name', 'Etkinlik'))
    
    # 1. KATILIMCIYA BİLDİRİM
    participant_notification = {
        "id": f"notif_participant_{event_id}_{user_id}_{datetime.utcnow().timestamp()}",
        "user_id": user_id,
        "type": "event_participation",
        "title": "🎉 Etkinliğe Eklendi!",
        "message": f"'{event_title}' etkinliğine katılımcı olarak eklendiniz.",
        "data": {
            "event_id": event_id,
            "group_id": group_id
        },
        "is_read": False,
        "created_at": datetime.utcnow()
    }
    await db.notifications.insert_one(participant_notification)
    
    # 2. ORGANİZATÖRE BİLDİRİM
    organizer_id = event.get("organizer_id") or event.get("creator_id")
    if organizer_id and organizer_id != user_id:
        organizer_notification = {
            "id": f"notif_organizer_{event_id}_{user_id}_{datetime.utcnow().timestamp()}",
            "user_id": organizer_id,
            "type": "event_new_participant",
            "title": "👤 Yeni Katılımcı",
            "message": f"{user.get('full_name', 'Bir kullanıcı')} '{event_title}' etkinliğinize eklendi.",
            "data": {
                "event_id": event_id,
                "participant_id": user_id
            },
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(organizer_notification)
    
    # 3. ADMIN'E BİLDİRİM
    admin = await db.users.find_one({"phone": "+905324900472"})
    if not admin:
        admin = await db.users.find_one({"phone": "905324900472"})
    if not admin:
        admin = await db.users.find_one({"user_type": "super_admin"})
    if not admin:
        admin = await db.users.find_one({"user_type": "admin"})
    
    if admin and admin["id"] != user_id and admin["id"] != organizer_id:
        admin_notification = {
            "id": f"notif_admin_{event_id}_{user_id}_{datetime.utcnow().timestamp()}",
            "user_id": admin["id"],
            "type": "admin_event_participant",
            "title": "👤 Yeni Etkinlik Katılımcısı",
            "message": f"{user.get('full_name', 'Kullanıcı')} - {event_title}",
            "data": {
                "event_id": event_id,
                "participant_id": user_id
            },
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(admin_notification)
    
    return {
        "status": "success",
        "message": f"{user.get('full_name')} gruba eklendi",
        "user_id": user_id,
        "user_name": user.get("full_name"),
        "group_name": group.get("name")
    }


@event_management_router.delete("/{event_id}/groups/{group_id}/remove-participant/{participant_id}")
async def remove_participant_from_group(
    event_id: str,
    group_id: str,
    participant_id: str,
    remove_from_event: bool = False,
    current_user: dict = None
):
    """Gruptan oyuncu çıkar"""
    global db
    
    # Grup kontrolü
    group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    
    # Oyuncu grupta mı?
    if participant_id not in group.get("participant_ids", []):
        raise HTTPException(status_code=400, detail="Oyuncu bu grupta değil")
    
    # Kullanıcı bilgisi
    user = await db.users.find_one({"id": participant_id})
    player_name = user.get("full_name") if user else "Bilinmeyen"
    
    # Gruptan çıkar
    group_participants = group.get("participant_ids", [])
    group_participants.remove(participant_id)
    
    # Bay listesinden de çıkar
    bye_ids = group.get("bye_participant_ids", [])
    if participant_id in bye_ids:
        bye_ids.remove(participant_id)
    
    await db.event_groups.update_one(
        {"id": group_id},
        {"$set": {
            "participant_ids": group_participants,
            "bye_participant_ids": bye_ids,
            "bye_participant_id": bye_ids[0] if bye_ids else None,
            "updated_at": datetime.utcnow()
        }}
    )
    
    # Etkinlikten de çıkar (isteğe bağlı)
    if remove_from_event:
        event = await find_event_by_id(db, event_id)
        if event:
            event_participants = event.get("participants", [])
            if participant_id in event_participants:
                event_participants.remove(participant_id)
                await db.events.update_one(
                    {"id": event_id},
                    {"$set": {
                        "participants": event_participants,
                        "participant_count": len(event_participants),
                        "updated_at": datetime.utcnow().isoformat()
                    }}
                )
    
    return {
        "status": "success",
        "message": f"{player_name} gruptan çıkarıldı" + (" ve etkinlikten silindi" if remove_from_event else ""),
        "participant_id": participant_id,
        "group_name": group.get("name"),
        "removed_from_event": remove_from_event
    }


@event_management_router.get("/{event_id}/available-users")
async def get_available_users_for_event(
    event_id: str,
    search: str = "",
    group_id: str = None,
    current_user: dict = None
):
    """Etkinliğe/gruba eklenebilecek kullanıcıları getir
    
    Artık event participants yerine grup participant_ids kontrol edilir.
    Böylece gruptan çıkarılan oyuncular tekrar eklenebilir.
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Tüm gruplardaki mevcut oyuncuları topla
    all_group_participants = set()
    groups = await db.event_groups.find({"event_id": event_id}).to_list(None)
    for group in groups:
        for pid in group.get("participant_ids", []):
            all_group_participants.add(pid)
    
    # Eğer belirli bir grup için sorgu yapılıyorsa, sadece o gruptakileri filtrele
    if group_id:
        group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
        if group:
            exclude_ids = list(group.get("participant_ids", []))
        else:
            exclude_ids = list(all_group_participants)
    else:
        exclude_ids = list(all_group_participants)
    
    # Kullanıcıları ara - sadece mevcut gruplarda olmayanlar
    query = {}
    if exclude_ids:
        query["id"] = {"$nin": exclude_ids}
    
    if search:
        search_query = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}}
        ]
        if query:
            query = {"$and": [query, {"$or": search_query}]}
        else:
            query = {"$or": search_query}
    
    # Alfabetik sıralama (full_name'e göre A-Z) - Tüm kullanıcıları getir
    users = await db.users.find(query).sort("full_name", 1).to_list(None)
    
    result = []
    for u in users:
        result.append({
            "id": u.get("id"),
            "name": u.get("full_name", "Bilinmeyen"),
            "phone": u.get("phone"),
            "email": u.get("email"),
            "avatar": u.get("profile_image"),
            "gender": u.get("gender"),
            "city": u.get("city")
        })
    
    return {
        "users": result,
        "total": len(result)
    }


# ================== DUYURU YÖNETİMİ ==================

class AnnouncementCreate(BaseModel):
    title: str
    content: str
    priority: str = "normal"  # normal, important, urgent
    send_notification: bool = True


@event_management_router.post("/{event_id}/announcements")
async def create_announcement(
    event_id: str, 
    announcement: AnnouncementCreate,
    current_user: dict = Depends(get_current_user)
):
    """Etkinlik için duyuru oluştur"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yetki kontrolü - etkinlik sahibi, yöneticiler veya katılımcılar
    organizer_id = event.get("organizer_id")
    creator_id = event.get("created_by") or event.get("creator_id")
    admin_ids = event.get("admin_ids", [])
    organizers = event.get("organizers", [])
    participants = event.get("participants", [])
    
    current_user_id = current_user.get("id")
    
    # Eğer creator_id yoksa (eski etkinlik), katılımcılar da duyuru yapabilir
    if not creator_id:
        is_authorized = current_user_id in participants or current_user_id in admin_ids or current_user_id in organizers
    else:
        is_authorized = (
            current_user_id == creator_id or
            current_user_id in admin_ids or
            current_user_id in organizers
        )
    
    if not is_authorized:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok. Sadece etkinlik yöneticileri duyuru yapabilir.")
    
    # Duyuruyu oluştur
    announcement_id = str(uuid.uuid4())
    announcement_data = {
        "id": announcement_id,
        "event_id": event_id,
        "title": announcement.title,
        "content": announcement.content,
        "priority": announcement.priority,
        "created_by": current_user_id,
        "created_by_name": current_user.get("full_name", "Yönetici"),
        "created_at": datetime.utcnow(),
        "is_read_by": []
    }
    
    await db.event_announcements.insert_one(announcement_data)
    
    # Bildirim gönder
    if announcement.send_notification:
        participants = event.get("participants", [])
        priority_icons = {
            "urgent": "🚨",
            "important": "⚠️",
            "normal": "📢"
        }
        icon = priority_icons.get(announcement.priority, "📢")
        
        for participant_id in participants:
            if participant_id != current_user_id:
                notification = {
                    "id": str(uuid.uuid4()),
                    "user_id": participant_id,
                    "type": "event_announcement",
                    "title": f"{icon} {event.get('title', 'Etkinlik')} - Duyuru",
                    "message": announcement.title,
                    "data": {
                        "event_id": event_id,
                        "announcement_id": announcement_id,
                        "priority": announcement.priority
                    },
                    "is_read": False,
                    "created_at": datetime.utcnow()
                }
                await db.notifications.insert_one(notification)
    
    logger.info(f"📢 Announcement created for event {event_id}: {announcement.title}")
    
    return {
        "status": "success",
        "message": "Duyuru oluşturuldu",
        "announcement_id": announcement_id
    }


@event_management_router.get("/{event_id}/announcements")
async def get_event_announcements(event_id: str):
    """Etkinlik duyurularını getir"""
    global db
    
    announcements = await db.event_announcements.find({
        "event_id": event_id
    }).sort("created_at", -1).to_list(50)
    
    result = []
    for ann in announcements:
        ann.pop("_id", None)
        result.append(ann)
    
    return {"announcements": result}


@event_management_router.delete("/{event_id}/announcements/{announcement_id}")
async def delete_announcement(
    event_id: str,
    announcement_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Duyuruyu sil"""
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yetki kontrolü
    organizer_id = event.get("organizer_id")
    creator_id = event.get("created_by") or event.get("creator_id")
    admin_ids = event.get("admin_ids", [])
    current_user_id = current_user.get("id")
    
    # Organizatör, creator veya admin olmalı
    if current_user_id != organizer_id and current_user_id != creator_id and current_user_id not in admin_ids:
        logging.error(f"Yetki hatası: user={current_user_id}, organizer={organizer_id}, creator={creator_id}, admins={admin_ids}")
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Duyuruyu bul - önce "id" sonra "_id" ile dene
    announcement = await db.event_announcements.find_one({
        "event_id": event_id,
        "$or": [{"id": announcement_id}, {"_id": announcement_id}]
    })
    
    if not announcement:
        logging.error(f"Duyuru bulunamadı: announcement_id={announcement_id}, event_id={event_id}")
        raise HTTPException(status_code=404, detail="Duyuru bulunamadı")
    
    # Sil
    result = await db.event_announcements.delete_one({"_id": announcement["_id"]})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Duyuru silinemedi")
    
    logging.info(f"✅ Duyuru silindi: {announcement_id}")
    return {"status": "success", "message": "Duyuru silindi"}


@event_management_router.put("/{event_id}/announcements/{announcement_id}/mark-read")
async def mark_announcement_read(
    event_id: str,
    announcement_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Duyuruyu okundu olarak işaretle"""
    global db
    
    current_user_id = current_user.get("id")
    
    await db.event_announcements.update_one(
        {"id": announcement_id, "event_id": event_id},
        {"$addToSet": {"is_read_by": current_user_id}}
    )
    
    return {"status": "success"}


# ================== SKOR ONAY SİSTEMİ ==================

class ScoreConfirmation(BaseModel):
    confirmed: bool
    user_role: str = "player"  # player, referee, organizer, admin

@event_management_router.post("/{event_id}/matches/{match_id}/confirm-score")
async def confirm_match_score(
    event_id: str,
    match_id: str,
    confirmation: ScoreConfirmation,
    current_user: dict = Depends(get_current_user)
):
    """
    Maç skorunu onayla veya itiraz et.
    Oyuncular, hakemler, etkinlik organizatörleri ve adminler onay verebilir.
    """
    global db
    
    current_user_id = current_user.get("id")
    current_user_name = current_user.get("name") or current_user.get("full_name") or "Kullanıcı"
    
    logger.info(f"🔍 confirm_match_score called: event_id={event_id}, match_id={match_id}, user={current_user_id}")
    
    # Etkinliği bul
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Maçı event_matches koleksiyonunda ara
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    
    if not match:
        logger.error(f"❌ Match not found in event_matches: {match_id}")
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    logger.info(f"✅ Match found: {match.get('participant1', {}).get('name')} vs {match.get('participant2', {}).get('name')}")
    
    # Kullanıcının onay yetkisi var mı kontrol et
    participant1_id = match.get("participant1_id") or (match.get("participant1", {}).get("id") if match.get("participant1") else None)
    participant2_id = match.get("participant2_id") or (match.get("participant2", {}).get("id") if match.get("participant2") else None)
    
    is_player1 = participant1_id == current_user_id
    is_player2 = participant2_id == current_user_id
    is_player = is_player1 or is_player2
    is_referee = match.get("referee_id") == current_user_id
    is_organizer = event.get("organizer_id") == current_user_id or event.get("created_by") == current_user_id
    is_admin = current_user.get("user_type") in ["admin", "super_admin"]
    
    logger.info(f"🔐 Permissions: player1={is_player1}, player2={is_player2}, referee={is_referee}, organizer={is_organizer}, admin={is_admin}")
    
    # Sadece maçın oyuncuları, hakemi, organizatör veya admin onay verebilir
    if not any([is_player, is_referee, is_organizer, is_admin]):
        raise HTTPException(status_code=403, detail="Bu maç için onay verme yetkiniz yok. Sadece maçın oyuncuları, hakemi veya organizatör onay verebilir.")
    
    # Onay kaydını ekle
    score_confirmations = match.get("score_confirmations") or []
    
    # Daha önce onay vermiş mi kontrol et
    existing = next((c for c in score_confirmations if c.get("user_id") == current_user_id), None)
    if existing:
        raise HTTPException(status_code=400, detail="Bu maç için zaten onay verdiniz")
    
    # Kullanıcının gerçek rolünü belirle
    if is_referee:
        actual_role = "referee"
    elif is_organizer:
        actual_role = "organizer"
    elif is_admin:
        actual_role = "admin"
    elif is_player:
        actual_role = "player"
    else:
        actual_role = "player"
    
    # Yeni onay ekle
    new_confirmation = {
        "user_id": current_user_id,
        "user_name": current_user_name,
        "user_role": actual_role,
        "confirmed": confirmation.confirmed,
        "confirmed_at": datetime.utcnow().isoformat()
    }
    score_confirmations.append(new_confirmation)
    
    # Onay kuralları:
    # 1. Hakem, Organizatör veya Admin tek başına onaylayabilir
    # 2. Oyuncular için: Her iki oyuncu da onaylamalı
    
    authority_confirmed = any(
        c.get("confirmed") and c.get("user_role") in ["referee", "organizer", "admin"]
        for c in score_confirmations
    )
    
    # Her iki oyuncu da onayladı mı?
    player1_confirmed = any(
        c.get("confirmed") and c.get("user_id") == participant1_id
        for c in score_confirmations
    )
    player2_confirmed = any(
        c.get("confirmed") and c.get("user_id") == participant2_id
        for c in score_confirmations
    )
    both_players_confirmed = player1_confirmed and player2_confirmed
    
    # Skor onaylandı mı?
    score_confirmed = authority_confirmed or both_players_confirmed
    
    logger.info(f"📊 Confirmation status: authority={authority_confirmed}, player1={player1_confirmed}, player2={player2_confirmed}, final={score_confirmed}")
    
    # Maçı güncelle
    update_data = {
        "score_confirmations": score_confirmations,
        "score_confirmed": score_confirmed
    }
    
    # Eğer yeterli onay alındıysa status'u completed yap
    if score_confirmed:
        update_data["status"] = "completed"
    
    # Veritabanını güncelle
    await db.event_matches.update_one(
        {"id": match_id, "event_id": event_id},
        {"$set": update_data}
    )
    
    logger.info(f"✅ Match updated: score_confirmed={score_confirmed}, status={update_data.get('status', 'unchanged')}")
    
    # Eğer maç tamamlandıysa ve kazanan varsa standings güncelle
    if score_confirmed and match.get("winner_id"):
        logger.info(f"📊 Updating standings for completed match...")
        try:
            await update_standings(event_id, match)
            logger.info(f"✅ Standings updated successfully")
        except Exception as e:
            logger.error(f"❌ Failed to update standings: {e}")
    
    # Güncel maç bilgisini döndür
    updated_match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if updated_match and "_id" in updated_match:
        del updated_match["_id"]
    
    return {
        "status": "success",
        "message": "Skor onaylandı" if confirmation.confirmed else "Skor itiraz edildi",
        "score_confirmed": score_confirmed,
        "match_status": update_data.get("status", match.get("status")),
        "match": updated_match
    }


# ================== ELEME GRUPLARI OLUŞTURMA ==================

@event_management_router.post("/{event_id}/create-elimination-groups")
async def create_elimination_groups(
    event_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Grup aşaması tamamlandıktan sonra eleme grupları oluştur.
    Her kategori için:
    - "[Yaş] [Cinsiyet] Eleme Grubu" -> Gruplardan 1. ve 2. sıradaki oyuncular
    - "[Yaş] [Cinsiyet] Teselli Eleme Grubu" -> Gruplardan 3. ve sonraki sıradaki oyuncular
    
    Bu gruplar düzenlenebilir olacak (oyuncu ekle/çıkar).
    """
    global db
    
    try:
        logger.info(f"🏆 Creating elimination groups for event: {event_id}")
        
        # 1. Etkinliği kontrol et
        event = await find_event_by_id(db, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
        
        # Yetki kontrolü
        is_organizer = event.get("organizer_id") == current_user.get("id") or event.get("created_by") == current_user.get("id")
        is_admin = current_user.get("user_type") in ["admin", "super_admin"]
        if not (is_organizer or is_admin):
            raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
        
        # 2. Turnuva ayarlarını al
        tournament_settings = event.get("tournament_settings", {})
        advance_count = tournament_settings.get("advance_from_group", 2)
        create_consolation = tournament_settings.get("consolation_bracket", False)
        
        logger.info(f"📊 Advance count: {advance_count}, Consolation enabled: {create_consolation}")
        
        # 3. Mevcut grupları al (sadece grup aşaması grupları)
        all_groups = await db.event_groups.find({
            "event_id": event_id,
            "group_type": {"$ne": "elimination"}  # Eleme gruplarını hariç tut
        }).to_list(length=200)
        
        if not all_groups:
            raise HTTPException(status_code=400, detail="Henüz grup oluşturulmamış")
        
        # 4. Kategorilere göre grupla
        categories = {}
        for g in all_groups:
            # Kategori bilgisini al (ya da grup isminden çıkar)
            cat = g.get("category")
            if not cat:
                # Grup isminden kategori çıkar: "Erkekler 50+ Tekler - Grup A" -> "Erkekler 50+ Tekler"
                name = g.get("name", "")
                if " - Grup " in name:
                    cat = name.split(" - Grup ")[0]
                else:
                    cat = name
            
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(g)
        
        logger.info(f"📊 Found {len(categories)} categories: {list(categories.keys())}")
        
        # 5. Her kategori için eleme grupları oluştur
        created_groups = []
        
        for category, groups in categories.items():
            logger.info(f"🏆 Processing category: {category} with {len(groups)} groups")
            
            # Ana eleme grubu için oyuncular (1. ve 2. sıra)
            main_elimination_players = []
            # Teselli eleme grubu için oyuncular (3. ve sonrası)
            consolation_players = []
            
            for group in groups:
                group_id = group["id"]
                group_name = group["name"]
                is_doubles = group.get("is_doubles", False)
                
                # Grup sıralamasını al
                standings = await db.event_standings.find({"group_id": group_id}).to_list(length=50)
                
                if standings:
                    # Sıralamaya göre oyuncuları al
                    sorted_standings = sorted(
                        standings,
                        key=lambda x: (
                            -x.get("points", 0),
                            -(x.get("goals_for", 0) - x.get("goals_against", 0)),
                            -x.get("wins", 0)
                        )
                    )
                    
                    # Çift grubu ise pairs listesini de al (isim bilgileri için)
                    pairs_dict = {}
                    if is_doubles or group.get("pairs"):
                        for pair in group.get("pairs", []):
                            # Olası ID formatlarını eşle
                            pair_id = pair.get("pair_id")
                            combined_id = f"{pair.get('player1_id')}_{pair.get('player2_id')}"
                            if pair_id:
                                pairs_dict[pair_id] = pair
                            pairs_dict[combined_id] = pair
                        logger.info(f"📊 Pairs dict keys: {list(pairs_dict.keys())[:5]}")
                    
                    for i, standing in enumerate(sorted_standings):
                        participant_id = standing["participant_id"]
                        logger.info(f"📊 Processing standing participant_id: {participant_id}, is_doubles: {is_doubles}")
                        
                        player_info = {
                            "participant_id": participant_id,
                            "group_name": group_name,
                            "group_position": i + 1,
                            "points": standing.get("points", 0),
                            "wins": standing.get("wins", 0),
                            "goal_diff": standing.get("goals_for", 0) - standing.get("goals_against", 0),
                            "is_pair": is_doubles
                        }
                        
                        # Çift grubu ise çift detaylarını ekle
                        if is_doubles:
                            # Önce direkt ID ile dene
                            pair = pairs_dict.get(participant_id)
                            
                            # Bulunamadıysa ters format dene (player2_player1)
                            if not pair and "_" in participant_id:
                                parts = participant_id.split("_")
                                if len(parts) == 2:
                                    reverse_id = f"{parts[1]}_{parts[0]}"
                                    pair = pairs_dict.get(reverse_id)
                            
                            if pair:
                                player_info["pair_name"] = pair.get("pair_name") or f"{pair.get('player1_name', '')} - {pair.get('player2_name', '')}"
                                player_info["player1_id"] = pair.get("player1_id")
                                player_info["player2_id"] = pair.get("player2_id")
                                player_info["player1_name"] = pair.get("player1_name")
                                player_info["player2_name"] = pair.get("player2_name")
                                logger.info(f"✅ Found pair info: {player_info['pair_name']}")
                            else:
                                logger.warning(f"⚠️ Could not find pair for participant_id: {participant_id}")
                        
                        if i < advance_count:
                            # 1. ve 2. sıra -> Ana eleme
                            main_elimination_players.append(player_info)
                        else:
                            # 3. ve sonrası -> Teselli
                            consolation_players.append(player_info)
                else:
                    # Sıralama yoksa katılımcıları direkt al
                    # Çift grubu mu kontrol et
                    if is_doubles or group.get("pairs"):
                        # Çift grubu - pairs listesinden al
                        pairs = group.get("pairs", [])
                        for i, pair in enumerate(pairs):
                            # Çift ID'si: pair_id veya player1_id_player2_id
                            pair_id = pair.get("pair_id") or f"{pair.get('player1_id')}_{pair.get('player2_id')}"
                            pair_name = pair.get("pair_name") or f"{pair.get('player1_name', '')} - {pair.get('player2_name', '')}"
                            
                            player_info = {
                                "participant_id": pair_id,
                                "group_name": group_name,
                                "group_position": i + 1,
                                "points": 0,
                                "wins": 0,
                                "goal_diff": 0,
                                "is_pair": True,
                                "pair_name": pair_name,
                                "player1_id": pair.get("player1_id"),
                                "player2_id": pair.get("player2_id"),
                                "player1_name": pair.get("player1_name"),
                                "player2_name": pair.get("player2_name")
                            }
                            
                            if i < advance_count:
                                main_elimination_players.append(player_info)
                            else:
                                consolation_players.append(player_info)
                    else:
                        # Tekli grup - participant_ids listesinden al
                        participant_ids = group.get("participant_ids", [])
                        for i, pid in enumerate(participant_ids):
                            if isinstance(pid, dict):
                                pid = pid.get("id")
                            
                            player_info = {
                                "participant_id": pid,
                                "group_name": group_name,
                                "group_position": i + 1,
                                "points": 0,
                                "wins": 0,
                                "goal_diff": 0,
                                "is_pair": False
                            }
                            
                            if i < advance_count:
                                main_elimination_players.append(player_info)
                            else:
                                consolation_players.append(player_info)
            
            # Oyuncu/Çift isimlerini çek
            async def get_player_name(player_info):
                participant_id = player_info["participant_id"]
                
                # Eğer çift ise ve pair_name varsa direkt kullan
                if player_info.get("is_pair") and player_info.get("pair_name"):
                    return player_info["pair_name"]
                
                # Çift ise ve player1_name, player2_name varsa birleştir
                if player_info.get("is_pair"):
                    p1_name = player_info.get("player1_name")
                    p2_name = player_info.get("player2_name")
                    if p1_name and p2_name:
                        return f"{p1_name} - {p2_name}"
                
                # Birleşik ID ise (çift) - users tablosundan bireysel isimleri al
                if "_" in participant_id:
                    parts = participant_id.split("_")
                    if len(parts) == 2:
                        user1 = await db.users.find_one({"id": parts[0]})
                        user2 = await db.users.find_one({"id": parts[1]})
                        name1 = (user1.get("full_name") or user1.get("name")) if user1 else "?"
                        name2 = (user2.get("full_name") or user2.get("name")) if user2 else "?"
                        if name1 != "?" or name2 != "?":
                            return f"{name1} - {name2}"
                
                # Önce event_participants'tan dene
                participant = await db.event_participants.find_one({"id": participant_id})
                if participant:
                    name = participant.get("name")
                    if name:
                        return name
                    user_id = participant.get("user_id")
                    if user_id:
                        user = await db.users.find_one({"id": user_id})
                        if user:
                            return user.get("full_name") or user.get("name") or f"Oyuncu {participant_id[:8]}"
                
                # Direkt users'tan dene
                user = await db.users.find_one({"id": participant_id})
                if user:
                    return user.get("full_name") or user.get("name") or f"Oyuncu {participant_id[:8]}"
                
                return f"Oyuncu {participant_id[:8]}"
            
            # Kategorinin çift kategorisi olup olmadığını belirle
            is_doubles_category = any(g.get("is_doubles") or g.get("pairs") for g in groups)
            
            # Ana eleme grubunu oluştur
            if main_elimination_players:
                # Oyuncuları puana göre sırala (seeding için)
                main_elimination_players.sort(
                    key=lambda x: (x["group_position"], -x["points"], -x["goal_diff"]),
                )
                
                main_group_id = str(uuid.uuid4())
                main_group_name = f"{category} Eleme Grubu"
                
                # Oyuncu detaylarını hazırla
                main_participant_details = []
                for i, p in enumerate(main_elimination_players):
                    name = await get_player_name(p)
                    detail = {
                        "id": p["participant_id"],
                        "name": name,
                        "seed": i + 1,
                        "from_group": p["group_name"],
                        "group_position": p["group_position"],
                        "points": p["points"],
                        "goal_diff": p["goal_diff"]
                    }
                    # Çift bilgilerini ekle
                    if p.get("is_pair"):
                        detail["is_pair"] = True
                        detail["player1_id"] = p.get("player1_id")
                        detail["player2_id"] = p.get("player2_id")
                        detail["player1_name"] = p.get("player1_name")
                        detail["player2_name"] = p.get("player2_name")
                    main_participant_details.append(detail)
                
                main_group = {
                    "id": main_group_id,
                    "event_id": event_id,
                    "name": main_group_name,
                    "category": category,
                    "group_type": "elimination",  # Eleme grubu olarak işaretle
                    "elimination_type": "main",  # Ana eleme
                    "is_doubles": is_doubles_category,  # Çift kategorisi mi?
                    "participant_ids": [p["participant_id"] for p in main_elimination_players],
                    "participant_details": main_participant_details,
                    "status": "pending",  # Düzenlenebilir
                    "editable": True,
                    "created_at": datetime.utcnow()
                }
                
                # Çift kategorisi ise pairs alanını da ekle
                if is_doubles_category:
                    pairs_list = []
                    for idx, p in enumerate(main_elimination_players):
                        if p.get("is_pair"):
                            # pair_name'i belirle - birden fazla kaynaktan kontrol et
                            pair_name = p.get("pair_name", "")
                            if not pair_name or pair_name.strip() == "" or pair_name == " - ":
                                # player1_name ve player2_name'den oluştur
                                p1n = p.get("player1_name", "")
                                p2n = p.get("player2_name", "")
                                if p1n and p2n:
                                    pair_name = f"{p1n} - {p2n}"
                                else:
                                    # participant_details'taki name'i kullan
                                    for detail in main_participant_details:
                                        if detail.get("id") == p["participant_id"]:
                                            pair_name = detail.get("name", "")
                                            break
                            
                            # Hala boşsa fallback
                            if not pair_name or pair_name.strip() == "" or pair_name == " - ":
                                pair_name = f"Çift {idx + 1}"
                            
                            pairs_list.append({
                                "pair_id": p["participant_id"],
                                "pair_name": pair_name,
                                "player1_id": p.get("player1_id"),
                                "player2_id": p.get("player2_id"),
                                "player1_name": p.get("player1_name"),
                                "player2_name": p.get("player2_name")
                            })
                            logger.info(f"✅ Main pairs_list: {p['participant_id'][:16]}... -> '{pair_name}'")
                    main_group["pairs"] = pairs_list
                
                await db.event_groups.insert_one(main_group)
                created_groups.append({
                    "id": main_group_id,
                    "name": main_group_name,
                    "type": "main",
                    "player_count": len(main_elimination_players),
                    "is_doubles": is_doubles_category
                })
                logger.info(f"✅ Created main elimination group: {main_group_name} with {len(main_elimination_players)} players/pairs")
            
            # Teselli eleme grubunu oluştur (yeterli oyuncu varsa)
            # consolation_bracket ayarından bağımsız olarak, 3+ oyuncu varsa teselli grubu oluştur
            if len(consolation_players) >= 2:
                # Oyuncuları puana göre sırala
                consolation_players.sort(
                    key=lambda x: (-x["points"], -x["goal_diff"], x["group_position"]),
                )
                
                consolation_group_id = str(uuid.uuid4())
                consolation_group_name = f"{category} Teselli Eleme Grubu"
                
                # Oyuncu detaylarını hazırla
                consolation_participant_details = []
                for i, p in enumerate(consolation_players):
                    name = await get_player_name(p)
                    detail = {
                        "id": p["participant_id"],
                        "name": name,
                        "seed": i + 1,
                        "from_group": p["group_name"],
                        "group_position": p["group_position"],
                        "points": p["points"],
                        "goal_diff": p["goal_diff"]
                    }
                    # Çift bilgilerini ekle
                    if p.get("is_pair"):
                        detail["is_pair"] = True
                        detail["player1_id"] = p.get("player1_id")
                        detail["player2_id"] = p.get("player2_id")
                        detail["player1_name"] = p.get("player1_name")
                        detail["player2_name"] = p.get("player2_name")
                    consolation_participant_details.append(detail)
                
                consolation_group = {
                    "id": consolation_group_id,
                    "event_id": event_id,
                    "name": consolation_group_name,
                    "category": category,
                    "group_type": "elimination",
                    "elimination_type": "consolation",  # Teselli eleme
                    "is_doubles": is_doubles_category,  # Çift kategorisi mi?
                    "participant_ids": [p["participant_id"] for p in consolation_players],
                    "participant_details": consolation_participant_details,
                    "status": "pending",
                    "editable": True,
                    "created_at": datetime.utcnow()
                }
                
                # Çift kategorisi ise pairs alanını da ekle
                if is_doubles_category:
                    pairs_list = []
                    for idx, p in enumerate(consolation_players):
                        if p.get("is_pair"):
                            # pair_name'i belirle - birden fazla kaynaktan kontrol et
                            pair_name = p.get("pair_name", "")
                            if not pair_name or pair_name.strip() == "" or pair_name == " - ":
                                # player1_name ve player2_name'den oluştur
                                p1n = p.get("player1_name", "")
                                p2n = p.get("player2_name", "")
                                if p1n and p2n:
                                    pair_name = f"{p1n} - {p2n}"
                                else:
                                    # participant_details'taki name'i kullan
                                    for detail in consolation_participant_details:
                                        if detail.get("id") == p["participant_id"]:
                                            pair_name = detail.get("name", "")
                                            break
                            
                            # Hala boşsa fallback
                            if not pair_name or pair_name.strip() == "" or pair_name == " - ":
                                pair_name = f"Çift {idx + 1}"
                            
                            pairs_list.append({
                                "pair_id": p["participant_id"],
                                "pair_name": pair_name,
                                "player1_id": p.get("player1_id"),
                                "player2_id": p.get("player2_id"),
                                "player1_name": p.get("player1_name"),
                                "player2_name": p.get("player2_name")
                            })
                            logger.info(f"✅ Consolation pairs_list: {p['participant_id'][:16]}... -> '{pair_name}'")
                    consolation_group["pairs"] = pairs_list
                
                await db.event_groups.insert_one(consolation_group)
                created_groups.append({
                    "id": consolation_group_id,
                    "name": consolation_group_name,
                    "type": "consolation",
                    "player_count": len(consolation_players),
                    "is_doubles": is_doubles_category
                })
                logger.info(f"✅ Created consolation group: {consolation_group_name} with {len(consolation_players)} players/pairs")
        
        return {
            "status": "success",
            "message": f"{len(created_groups)} eleme grubu oluşturuldu",
            "created_groups": created_groups,
            "categories_processed": len(categories)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating elimination groups: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Eleme grupları oluşturulamadı: {str(e)}")


@event_management_router.get("/{event_id}/elimination-groups")
async def get_elimination_groups(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eleme gruplarını getir"""
    global db
    
    try:
        # Eleme gruplarını al
        groups = await db.event_groups.find({
            "event_id": event_id,
            "group_type": "elimination"
        }).to_list(length=100)
        
        # _id'leri temizle
        for g in groups:
            if "_id" in g:
                del g["_id"]
        
        # Ana eleme ve teselli olarak ayır
        main_groups = [g for g in groups if g.get("elimination_type") == "main"]
        consolation_groups = [g for g in groups if g.get("elimination_type") == "consolation"]
        
        return {
            "status": "success",
            "main_groups": main_groups,
            "consolation_groups": consolation_groups,
            "total": len(groups)
        }
        
    except Exception as e:
        logger.error(f"❌ Error fetching elimination groups: {e}")
        raise HTTPException(status_code=500, detail=f"Eleme grupları alınamadı: {str(e)}")


@event_management_router.put("/{event_id}/elimination-groups/{group_id}")
async def update_elimination_group(
    event_id: str,
    group_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Eleme grubunu güncelle (oyuncu ekle/çıkar, sıralama değiştir)
    """
    global db
    
    try:
        body = await request.json()
        
        # Grubu kontrol et
        group = await db.event_groups.find_one({
            "id": group_id,
            "event_id": event_id,
            "group_type": "elimination"
        })
        
        if not group:
            raise HTTPException(status_code=404, detail="Eleme grubu bulunamadı")
        
        if not group.get("editable", True):
            raise HTTPException(status_code=400, detail="Bu grup artık düzenlenemez")
        
        # Yetki kontrolü
        event = await find_event_by_id(db, event_id)
        is_organizer = event.get("organizer_id") == current_user.get("id") or event.get("created_by") == current_user.get("id")
        is_admin = current_user.get("user_type") in ["admin", "super_admin"]
        if not (is_organizer or is_admin):
            raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
        
        update_data = {}
        
        # Oyuncu listesi güncelleme
        if "participant_ids" in body:
            update_data["participant_ids"] = body["participant_ids"]
        
        # Oyuncu detayları güncelleme
        if "participant_details" in body:
            update_data["participant_details"] = body["participant_details"]
        
        # Grubu güncelle
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            await db.event_groups.update_one(
                {"id": group_id, "event_id": event_id},
                {"$set": update_data}
            )
        
        # Güncel grubu döndür
        updated_group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
        if updated_group and "_id" in updated_group:
            del updated_group["_id"]
        
        return {
            "status": "success",
            "message": "Eleme grubu güncellendi",
            "group": updated_group
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error updating elimination group: {e}")
        raise HTTPException(status_code=500, detail=f"Eleme grubu güncellenemedi: {str(e)}")


@event_management_router.post("/{event_id}/elimination-groups/{group_id}/add-player")
async def add_player_to_elimination_group(
    event_id: str,
    group_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Eleme grubuna oyuncu ekle"""
    global db
    
    try:
        body = await request.json()
        participant_id = body.get("participant_id")
        
        if not participant_id:
            raise HTTPException(status_code=400, detail="participant_id gerekli")
        
        # Grubu kontrol et
        group = await db.event_groups.find_one({
            "id": group_id,
            "event_id": event_id,
            "group_type": "elimination"
        })
        
        if not group:
            raise HTTPException(status_code=404, detail="Eleme grubu bulunamadı")
        
        if not group.get("editable", True):
            raise HTTPException(status_code=400, detail="Bu grup artık düzenlenemez")
        
        # Oyuncu zaten grupta mı?
        if participant_id in group.get("participant_ids", []):
            raise HTTPException(status_code=400, detail="Oyuncu zaten bu grupta")
        
        # Oyuncu bilgisini al
        participant = await db.event_participants.find_one({"id": participant_id})
        if not participant:
            user = await db.users.find_one({"id": participant_id})
            if user:
                name = user.get("full_name") or user.get("name") or f"Oyuncu {participant_id[:8]}"
            else:
                name = f"Oyuncu {participant_id[:8]}"
        else:
            name = participant.get("name")
            if not name:
                user_id = participant.get("user_id")
                if user_id:
                    user = await db.users.find_one({"id": user_id})
                    name = user.get("full_name") or user.get("name") if user else f"Oyuncu {participant_id[:8]}"
                else:
                    name = f"Oyuncu {participant_id[:8]}"
        
        # Yeni oyuncu detayı
        current_details = group.get("participant_details", [])
        new_seed = len(current_details) + 1
        
        new_player_detail = {
            "id": participant_id,
            "name": name,
            "seed": new_seed,
            "from_group": "Manuel eklendi",
            "group_position": 0,
            "points": 0,
            "goal_diff": 0
        }
        
        # Grubu güncelle
        await db.event_groups.update_one(
            {"id": group_id, "event_id": event_id},
            {
                "$push": {
                    "participant_ids": participant_id,
                    "participant_details": new_player_detail
                },
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        return {
            "status": "success",
            "message": f"{name} eleme grubuna eklendi",
            "player": new_player_detail
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error adding player to elimination group: {e}")
        raise HTTPException(status_code=500, detail=f"Oyuncu eklenemedi: {str(e)}")


@event_management_router.delete("/{event_id}/elimination-groups/{group_id}/remove-player/{participant_id}")
async def remove_player_from_elimination_group(
    event_id: str,
    group_id: str,
    participant_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eleme grubundan oyuncu çıkar"""
    global db
    
    try:
        # Grubu kontrol et
        group = await db.event_groups.find_one({
            "id": group_id,
            "event_id": event_id,
            "group_type": "elimination"
        })
        
        if not group:
            raise HTTPException(status_code=404, detail="Eleme grubu bulunamadı")
        
        if not group.get("editable", True):
            raise HTTPException(status_code=400, detail="Bu grup artık düzenlenemez")
        
        # Oyuncu grupta mı?
        if participant_id not in group.get("participant_ids", []):
            raise HTTPException(status_code=400, detail="Oyuncu bu grupta değil")
        
        # Grubu güncelle
        await db.event_groups.update_one(
            {"id": group_id, "event_id": event_id},
            {
                "$pull": {
                    "participant_ids": participant_id,
                    "participant_details": {"id": participant_id}
                },
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        # Seed numaralarını yeniden düzenle
        updated_group = await db.event_groups.find_one({"id": group_id, "event_id": event_id})
        if updated_group:
            details = updated_group.get("participant_details", [])
            for i, d in enumerate(details):
                d["seed"] = i + 1
            
            await db.event_groups.update_one(
                {"id": group_id, "event_id": event_id},
                {"$set": {"participant_details": details}}
            )
        
        return {
            "status": "success",
            "message": "Oyuncu eleme grubundan çıkarıldı"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error removing player from elimination group: {e}")
        raise HTTPException(status_code=500, detail=f"Oyuncu çıkarılamadı: {str(e)}")


@event_management_router.delete("/{event_id}/elimination-matches")
async def delete_elimination_matches(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eleme maçlarını ve bracket'larını sil"""
    global db
    
    try:
        logger.info(f"🗑️ Deleting elimination matches for event: {event_id}")
        
        # Yetki kontrolü
        event = await find_event_by_id(db, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
        
        is_organizer = event.get("organizer_id") == current_user.get("id") or event.get("created_by") == current_user.get("id")
        is_admin = current_user.get("user_type") in ["admin", "super_admin"]
        if not (is_organizer or is_admin):
            raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
        
        # Eleme maçlarını sil - çok kapsamlı filtre
        elimination_result = await db.event_matches.delete_many({
            "event_id": event_id,
            "$or": [
                {"bracket_position": "elimination"},
                {"bracket_position": "consolation"},
                {"stage": "elimination"},
                {"stage": "knockout"},
                {"stage": "bracket"},
                {"group_name": {"$regex": "Eleme|Teselli", "$options": "i"}},
                {"round_name": {"$regex": "Final|Çeyrek|Yarı", "$options": "i"}}
            ]
        })
        
        # Bracket kayıtlarını sil
        brackets_result = await db.event_brackets.delete_many({"event_id": event_id})
        
        # Bracket slot'larını sil
        slots_result = await db.bracket_slots.delete_many({"event_id": event_id})
        
        logger.info(f"✅ Deleted {elimination_result.deleted_count} elimination matches, {brackets_result.deleted_count} brackets, {slots_result.deleted_count} slots")
        
        return {
            "status": "success",
            "message": f"Eleme fikstürü silindi",
            "deleted": {
                "matches": elimination_result.deleted_count,
                "brackets": brackets_result.deleted_count,
                "slots": slots_result.deleted_count
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting elimination matches: {e}")
        raise HTTPException(status_code=500, detail=f"Eleme fikstürü silinemedi: {str(e)}")


# ================== ELEME MAÇLARI OLUŞTURMA ==================

@event_management_router.post("/{event_id}/create-elimination-bracket")
async def create_elimination_bracket(
    event_id: str,
    request: Request,
    category: str = None,  # Belirli bir kategori için bracket oluştur (opsiyonel)
    current_user: dict = Depends(get_current_user)
):
    """
    Grup aşaması tamamlandıktan sonra eleme maçlarını oluştur.
    Category verilmezse TÜM kategoriler için ayrı ayrı eleme bracket'i oluşturur.
    """
    global db
    
    try:
        logger.info(f"🏆 Creating elimination bracket for event: {event_id}, category: {category}")
        
        # 1. Etkinliği kontrol et
        event = await find_event_by_id(db, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
        
        # Yetki kontrolü
        is_organizer = event.get("organizer_id") == current_user.get("id") or event.get("created_by") == current_user.get("id")
        is_admin = current_user.get("user_type") in ["admin", "super_admin"]
        if not (is_organizer or is_admin):
            raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
        
        # Turnuva ayarlarını al - consolation_bracket aktif mi?
        tournament_settings = event.get("tournament_settings", {})
        create_consolation = tournament_settings.get("consolation_bracket", False)
        
        logger.info(f"🏆 Consolation bracket enabled: {create_consolation}")
        
        # Eğer kategori verilmemişse, tüm kategorileri bul ve her biri için bracket oluştur
        if not category:
            all_groups = await db.event_groups.find({"event_id": event_id}).to_list(length=100)
            if not all_groups:
                raise HTTPException(status_code=400, detail="Henüz grup oluşturulmamış")
            
            # Benzersiz kategorileri bul
            categories = set()
            for g in all_groups:
                cat = g.get("category", g.get("name", "Varsayılan"))
                categories.add(cat)
            
            logger.info(f"📊 Found {len(categories)} categories: {categories}")
            
            # Her kategori için bracket oluştur
            all_results = []
            consolation_results = []
            
            for cat in categories:
                try:
                    # Ana eleme bracket'ı oluştur
                    result = await _create_bracket_for_category(db, event_id, event, cat, is_consolation=False)
                    all_results.append(result)
                    logger.info(f"✅ Created bracket for category: {cat}")
                    
                    # Teselli eleme bracket'ı oluştur (her zaman dene, yeterli oyuncu varsa oluşur)
                    try:
                        consolation_result = await _create_consolation_bracket_for_category(db, event_id, event, cat)
                        if consolation_result.get("status") == "success":
                            consolation_results.append(consolation_result)
                            logger.info(f"✅ Created CONSOLATION bracket for category: {cat}")
                    except Exception as ce:
                        logger.warning(f"⚠️ Could not create consolation bracket for {cat}: {ce}")
                            
                except Exception as e:
                    logger.warning(f"⚠️ Could not create bracket for {cat}: {e}")
                    all_results.append({
                        "category": cat,
                        "status": "error",
                        "error": str(e)
                    })
            
            # Sonuçları birleştir
            successful = [r for r in all_results if r.get("status") == "success"]
            failed = [r for r in all_results if r.get("status") != "success"]
            
            message = f"{len(successful)} kategori için eleme bracket'i oluşturuldu"
            if consolation_results:
                message += f", {len(consolation_results)} teselli bracket'ı oluşturuldu"
            
            return {
                "status": "success" if successful else "partial",
                "message": message,
                "categories_processed": len(all_results),
                "successful": len(successful),
                "failed": len(failed),
                "results": all_results,
                "consolation_results": consolation_results
            }
        
        # Tek kategori için bracket oluştur
        result = await _create_bracket_for_category(db, event_id, event, category, is_consolation=False)
        
        # Teselli bracket da oluştur (her zaman dene)
        try:
            consolation_result = await _create_consolation_bracket_for_category(db, event_id, event, category)
            result["consolation"] = consolation_result
        except Exception as ce:
            logger.warning(f"⚠️ Could not create consolation bracket for {category}: {ce}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating elimination bracket: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Eleme bracket'i oluşturulamadı: {str(e)}")


async def _create_bracket_for_category(db, event_id: str, event: dict, category: str, is_consolation: bool = False):
    """
    Standart turnuva bracket'i oluşturur.
    
    Seeding Kuralları:
    1. Bracket boyutu: 2'nin en yakın üst kuvveti (4, 8, 16, 32, 64...)
    2. BYE'lar en yüksek seed'li oyunculara verilir
    3. Seed 1 ve Seed 2 ancak finalde karşılaşır
    4. Her oyuncu bracket'ta sadece BİR KEZ yer alır
    
    Args:
        db: Database connection
        event_id: Event ID
        event: Event data
        category: Category name
        is_consolation: True if consolation bracket
    """
    import math
    import uuid
    
    bracket_type = "CONSOLATION" if is_consolation else "MAIN"
    logger.info(f"🏆 Creating {bracket_type} bracket for category: {category}")
    
    # Çiftler kategorisi mi kontrol et
    category_lower = category.lower()
    is_doubles = "çift" in category_lower or "cift" in category_lower or "double" in category_lower or "karışık" in category_lower or "mixed" in category_lower
    
    # 1. KATILIMCILARI TOPLA
    participants = []
    
    # Önce eleme gruplarından al
    elimination_type = "consolation" if is_consolation else "main"
    elimination_groups = await db.event_groups.find({
        "event_id": event_id,
        "group_type": "elimination",
        "elimination_type": elimination_type
    }).to_list(length=50)
    
    # Kategoriye göre filtrele
    category_groups = [g for g in elimination_groups if 
                       category.lower() in g.get("name", "").lower() or 
                       category.lower() in g.get("category", "").lower()]
    
    if category_groups:
        logger.info(f"✅ Found {len(category_groups)} elimination groups for {bracket_type}")
        
        # Önce tüm pairs'leri bir dict'e topla (hızlı erişim için)
        all_pairs = {}
        for eg in category_groups:
            for pair in eg.get("pairs", []):
                pair_id = pair.get("pair_id")
                combined_id = f"{pair.get('player1_id')}_{pair.get('player2_id')}"
                pair_name = pair.get("pair_name") or f"{pair.get('player1_name', '')} - {pair.get('player2_name', '')}"
                if pair_id:
                    all_pairs[pair_id] = pair_name
                all_pairs[combined_id] = pair_name
                # Ters sıralama da ekle
                reverse_id = f"{pair.get('player2_id')}_{pair.get('player1_id')}"
                all_pairs[reverse_id] = pair_name
        
        logger.info(f"📊 Collected {len(all_pairs)} pairs from elimination groups")
        
        # Tüm katılımcıları topla (TEKRARLI OLMAMALI)
        seen_ids = set()
        for eg in category_groups:
            is_doubles_group = eg.get("is_doubles", False)
            
            for pd in eg.get("participant_details", []):
                pid = pd.get("id")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    
                    # İsmi belirle - ÖNCELİK: all_pairs dict'inden al
                    participant_name = ""
                    
                    # 1. Önce all_pairs'ten bak (en güvenilir)
                    if pid in all_pairs:
                        participant_name = all_pairs[pid]
                    
                    # 2. participant_details'tan player1_name - player2_name
                    if not participant_name or participant_name == " - ":
                        if pd.get("is_pair") or is_doubles_group:
                            p1_name = pd.get("player1_name", "")
                            p2_name = pd.get("player2_name", "")
                            if p1_name and p2_name:
                                participant_name = f"{p1_name} - {p2_name}"
                    
                    # 3. participant_details'tan name
                    if not participant_name or participant_name == " - ":
                        participant_name = pd.get("name", "")
                    
                    # 4. Hala boşsa pairs listesinden ara
                    if not participant_name or participant_name.startswith("Oyuncu") or participant_name == " - ":
                        for pair in eg.get("pairs", []):
                            pair_pid = pair.get("pair_id") or f"{pair.get('player1_id')}_{pair.get('player2_id')}"
                            if pair_pid == pid:
                                participant_name = pair.get("pair_name") or f"{pair.get('player1_name', '')} - {pair.get('player2_name', '')}"
                                break
                    
                    logger.info(f"📊 Participant from elimination group: {pid[:16]}... -> '{participant_name}'")
                    
                    participants.append({
                        "participant_id": pid,
                        "name": participant_name,
                        "group_name": pd.get("from_group", ""),
                        "group_position": pd.get("group_position", 99),
                        "points": pd.get("points", 0),
                        "goal_diff": pd.get("goal_diff", 0),
                        "seed": pd.get("seed", 999)
                    })
    else:
        # Eleme grubu yoksa normal gruplardan al
        logger.info(f"⚠️ No elimination groups found for {bracket_type}, using regular groups")
        
        tournament_settings = event.get("tournament_settings", {})
        advance_count = tournament_settings.get("advance_from_group", 2)
        
        groups = await db.event_groups.find({
            "event_id": event_id,
            "group_type": {"$ne": "elimination"}
        }).to_list(length=100)
        
        # Kategoriye göre filtrele
        category_groups = [g for g in groups if 
                          category.lower() in g.get("name", "").lower() or 
                          category.lower() in g.get("category", "").lower()]
        
        seen_ids = set()
        for group in category_groups:
            group_id = group["id"]
            standings = await db.event_standings.find({"group_id": group_id}).to_list(length=50)
            
            if standings:
                sorted_standings = sorted(standings, key=lambda x: (-x.get("points", 0), -x.get("wins", 0)))
                for i, s in enumerate(sorted_standings[:advance_count]):
                    pid = s.get("participant_id")
                    if pid and pid not in seen_ids:
                        seen_ids.add(pid)
                        participants.append({
                            "participant_id": pid,
                            "name": "",
                            "group_name": group.get("name", ""),
                            "group_position": i + 1,
                            "points": s.get("points", 0),
                            "goal_diff": s.get("scored", 0) - s.get("conceded", 0),
                            "seed": 999
                        })
    
    # 2. KATILIMCI KONTROLÜ
    n = len(participants)
    logger.info(f"📊 Total unique participants: {n}")
    
    if n < 2:
        raise Exception(f"'{category}' kategorisinde {bracket_type} için en az 2 katılımcı gerekli (bulunan: {n})")
    
    # 3. SEEDING - Grup birincileri önce, puana göre sırala
    # Grup birincileri (position=1) puana göre
    group_winners = sorted([p for p in participants if p["group_position"] == 1], 
                          key=lambda x: (-x["points"], -x["goal_diff"]))
    # Grup ikincileri (position=2) puana göre
    group_runners = sorted([p for p in participants if p["group_position"] == 2],
                          key=lambda x: (-x["points"], -x["goal_diff"]))
    # Diğerleri puana göre
    others = sorted([p for p in participants if p["group_position"] > 2],
                   key=lambda x: (-x["points"], -x["goal_diff"]))
    
    # Birleştir ve seed numarası ata
    seeded_participants = group_winners + group_runners + others
    for i, p in enumerate(seeded_participants):
        p["seed"] = i + 1
    
    logger.info(f"📊 Seeding complete: {len(group_winners)} winners, {len(group_runners)} runners-up, {len(others)} others")
    
    # 4. BRACKET BOYUTU HESAPLA
    bracket_size = 2 ** math.ceil(math.log2(n))
    byes_needed = bracket_size - n
    
    logger.info(f"📐 Bracket size: {bracket_size}, Players: {n}, BYEs: {byes_needed}")
    
    # 5. STANDART BRACKET POZİSYONLARI OLUŞTUR
    def get_standard_bracket_positions(size):
        """
        Standart turnuva bracket pozisyonları.
        Seed 1 ve Seed 2 bracket'ın zıt uçlarına yerleşir (finalde karşılaşır).
        """
        if size == 2:
            return [1, 2]
        elif size == 4:
            return [1, 4, 2, 3]
        elif size == 8:
            return [1, 8, 4, 5, 2, 7, 3, 6]
        elif size == 16:
            return [1, 16, 8, 9, 4, 13, 5, 12, 2, 15, 7, 10, 3, 14, 6, 11]
        elif size == 32:
            return [1, 32, 16, 17, 8, 25, 9, 24, 4, 29, 13, 20, 5, 28, 12, 21,
                    2, 31, 15, 18, 7, 26, 10, 23, 3, 30, 14, 19, 6, 27, 11, 22]
        elif size == 64:
            # 64'lük bracket için
            return [1, 64, 32, 33, 16, 49, 17, 48, 8, 57, 25, 40, 9, 56, 24, 41,
                    4, 61, 29, 36, 13, 52, 20, 45, 5, 60, 28, 37, 12, 53, 21, 44,
                    2, 63, 31, 34, 15, 50, 18, 47, 7, 58, 26, 39, 10, 55, 23, 42,
                    3, 62, 30, 35, 14, 51, 19, 46, 6, 59, 27, 38, 11, 54, 22, 43]
        else:
            # Daha büyük bracket'lar için genel algoritma
            positions = []
            def fill_bracket(low, high, positions):
                if low == high:
                    positions.append(low)
                else:
                    mid = (low + high) // 2
                    fill_bracket(low, mid, positions)
                    fill_bracket(mid + 1, high, positions)
            fill_bracket(1, size, positions)
            return positions
    
    bracket_positions = get_standard_bracket_positions(bracket_size)
    logger.info(f"📋 Bracket positions: {bracket_positions[:16]}...")
    
    # 6. KATILIMCILARI POZİSYONLARA YERLEŞTİR
    # BYE'lar en yüksek seed'lere verilir (pozisyonlarda n+1'den bracket_size'a kadar olan seedler BYE alır)
    positioned = []
    for seed_pos in bracket_positions:
        if seed_pos <= n:
            # Gerçek katılımcı
            positioned.append(seeded_participants[seed_pos - 1])
        else:
            # BYE
            positioned.append(None)
    
    # 7. KATILIMCI İSİMLERİNİ ÇEK - DOĞRUDAN ELİME GRUPLARINDAKI PAIRS'TEN
    participant_names = {}
    
    # Önce tüm pairs'leri bir dict'e topla
    all_pairs_names = {}
    for eg in category_groups:
        # pairs listesinden al
        for pair in eg.get("pairs", []):
            pair_id = pair.get("pair_id")
            p1_id = pair.get("player1_id")
            p2_id = pair.get("player2_id")
            combined_id = f"{p1_id}_{p2_id}" if p1_id and p2_id else None
            reverse_id = f"{p2_id}_{p1_id}" if p1_id and p2_id else None
            
            # pair_name'i belirle - birden fazla kaynaktan kontrol et
            pair_name = pair.get("pair_name", "")
            if not pair_name or pair_name.strip() == "" or pair_name == " - ":
                p1n = pair.get('player1_name', '')
                p2n = pair.get('player2_name', '')
                if p1n and p2n:
                    pair_name = f"{p1n} - {p2n}"
            
            # Geçerli isim varsa kaydet
            if pair_name and pair_name.strip() and pair_name != " - ":
                if pair_id:
                    all_pairs_names[pair_id] = pair_name
                if combined_id:
                    all_pairs_names[combined_id] = pair_name
                if reverse_id:
                    all_pairs_names[reverse_id] = pair_name
        
        # participant_details'tan da al
        for pd in eg.get("participant_details", []):
            pid = pd.get("id")
            if pid:
                # Öncelik: player1_name - player2_name
                p1n = pd.get("player1_name", "")
                p2n = pd.get("player2_name", "")
                if p1n and p2n:
                    all_pairs_names[pid] = f"{p1n} - {p2n}"
                elif pd.get("name") and not pd.get("name", "").startswith("Oyuncu"):
                    all_pairs_names[pid] = pd.get("name")
    
    logger.info(f"📊 ALL_PAIRS_NAMES dict: {len(all_pairs_names)} entries")
    for k, v in list(all_pairs_names.items())[:5]:
        logger.info(f"  - {k[:20]}... -> {v}")
    
    # Şimdi seeded_participants'tan participant_names'i doldur
    for p in seeded_participants:
        pid = p["participant_id"]
        
        # 1. ÖNCE all_pairs_names'ten bak (EN GÜVENİLİR)
        if pid in all_pairs_names:
            participant_names[pid] = all_pairs_names[pid]
            logger.info(f"✅ Name from all_pairs_names: {pid[:16]}... -> {all_pairs_names[pid]}")
            continue
        
        # 2. seeded_participants'taki name'e bak
        name_from_group = p.get("name", "")
        if name_from_group and name_from_group.strip() and not name_from_group.startswith("Oyuncu") and name_from_group != "?" and name_from_group != " - ":
            participant_names[pid] = name_from_group
            logger.info(f"✅ Name from seeded: {pid[:16]}... -> {name_from_group}")
            continue
        
        # 3. Birleşik ID ise users tablosundan çek
        if "_" in pid:
            parts = pid.split("_")
            if len(parts) == 2:
                user1 = await db.users.find_one({"id": parts[0]})
                user2 = await db.users.find_one({"id": parts[1]})
                name1 = (user1.get("full_name") or user1.get("name")) if user1 else "?"
                name2 = (user2.get("full_name") or user2.get("name")) if user2 else "?"
                participant_names[pid] = f"{name1} - {name2}"
                logger.info(f"✅ Name from users DB: {pid[:16]}... -> {participant_names[pid]}")
            else:
                participant_names[pid] = f"Çift {pid[:8]}"
        else:
            # Tekli oyuncu
            user = await db.users.find_one({"id": pid})
            if user:
                participant_names[pid] = user.get("full_name") or user.get("name") or f"Oyuncu {pid[:8]}"
            else:
                participant_names[pid] = f"Oyuncu {pid[:8]}"
    
    logger.info(f"📊 FINAL participant_names: {len(participant_names)} entries")
    for k, v in list(participant_names.items())[:5]:
        logger.info(f"  - {k[:20]}... -> {v}")
    
    # 8. TUR İSİMLERİ
    def get_round_name(bracket_size, round_num):
        total_rounds = int(math.log2(bracket_size))
        remaining = total_rounds - round_num + 1
        
        if remaining == 1:
            return "Final"
        elif remaining == 2:
            return "Yarı Final"
        elif remaining == 3:
            return "Çeyrek Final"
        elif remaining == 4:
            return "Son 16"
        elif remaining == 5:
            return "Son 32"
        else:
            return f"{round_num}. Tur"
    
    # 9. İLK TUR MAÇLARINI OLUŞTUR
    matches = []
    bye_winners = []
    match_number = 1
    bracket_position_type = "consolation" if is_consolation else "elimination"
    
    # ========== 1. TUR HAKEM ATAMASI İÇİN HAZIRLIK ==========
    tournament_settings = event.get("tournament_settings", {})
    in_group_refereeing = tournament_settings.get("in_group_refereeing", False)
    
    # Hakem havuzu: Grup sıralamasında en sonda olanlar (seed değeri yüksek olanlar)
    # Maç yapmayacak oyuncular hakem olabilir (BYE alanlar hariç)
    referee_pool = []
    if in_group_refereeing:
        # Seed'e göre ters sıralama - en düşük seed'li (en iyi) oyuncular en sonda hakem olacak
        # En yüksek seed'li oyuncular (en kötü sıralamadakiler) önce hakem olacak
        sorted_by_seed_desc = sorted(seeded_participants, key=lambda x: x.get("seed", 999), reverse=True)
        
        # BYE almayan oyuncuları hakem havuzuna ekle
        bye_participant_ids = set()
        for i in range(0, bracket_size, 2):
            p1 = positioned[i]
            p2 = positioned[i + 1]
            if p1 is None and p2 is not None:
                bye_participant_ids.add(p2["participant_id"])
            elif p2 is None and p1 is not None:
                bye_participant_ids.add(p1["participant_id"])
        
        for p in sorted_by_seed_desc:
            if p["participant_id"] not in bye_participant_ids:
                referee_pool.append({
                    "id": p["participant_id"],
                    "name": participant_names.get(p["participant_id"], "?"),
                    "seed": p.get("seed", 999)
                })
        
        logger.info(f"⚖️ Hakem havuzu oluşturuldu: {len(referee_pool)} oyuncu (en yüksek seed'liler önce)")
    
    referee_index = 0  # Hangi hakemi atayacağımızı takip et
    
    for i in range(0, bracket_size, 2):
        p1 = positioned[i]
        p2 = positioned[i + 1]
        
        # 1. turdaki maç indeksi
        first_round_match_idx = i // 2
        
        if p1 is None and p2 is None:
            # İkisi de BYE - bu olmamalı ama güvenlik için
            continue
        elif p1 is None:
            # P1 BYE - P2 direkt 2. tura geçer (1. turda maç YOK)
            bye_winners.append({
                "participant": p2,
                "first_round_match_idx": first_round_match_idx,
                "seed": p2["seed"],
                "name": participant_names.get(p2["participant_id"], "?")
            })
            logger.info(f"🎯 BYE: Seed {p2['seed']} ({participant_names.get(p2['participant_id'])}) direkt 2. tura (1. tur maç {first_round_match_idx} yok)")
        elif p2 is None:
            # P2 BYE - P1 direkt 2. tura geçer (1. turda maç YOK)
            bye_winners.append({
                "participant": p1,
                "first_round_match_idx": first_round_match_idx,
                "seed": p1["seed"],
                "name": participant_names.get(p1["participant_id"], "?")
            })
            logger.info(f"🎯 BYE: Seed {p1['seed']} ({participant_names.get(p1['participant_id'])}) direkt 2. tura (1. tur maç {first_round_match_idx} yok)")
        else:
            # Normal maç
            match_id = str(uuid.uuid4())
            match = {
                "id": match_id,
                "event_id": event_id,
                "group_id": None,
                "group_name": f"{'Teselli ' if is_consolation else ''}Eleme",
                "category": category,
                "round_number": 1,
                "round_name": get_round_name(bracket_size, 1),
                "match_number": match_number,
                "bracket_match_number": i // 2 + 1,
                "participant1_id": p1["participant_id"],
                "participant1_name": participant_names.get(p1["participant_id"], "?"),
                "participant1_seed": p1["seed"],
                "participant2_id": p2["participant_id"],
                "participant2_name": participant_names.get(p2["participant_id"], "?"),
                "participant2_seed": p2["seed"],
                "status": "scheduled",
                "score": None,
                "winner_id": None,
                "bracket_position": bracket_position_type,
                "bracket_round": 1,
                "bracket_index": i // 2,
                "stage": "elimination",
                "is_bye": False,
                "is_doubles": is_doubles,
                "created_at": datetime.utcnow()
            }
            
            # ========== 1. TUR HAKEM ATAMASI ==========
            # Maça katılmayan oyunculardan hakem ata
            if in_group_refereeing and referee_pool:
                # Bu maçın oyuncuları dışında bir hakem bul
                match_participant_ids = {p1["participant_id"], p2["participant_id"]}
                
                for ref_candidate in referee_pool:
                    if ref_candidate["id"] not in match_participant_ids:
                        match["referee_id"] = ref_candidate["id"]
                        match["referee_name"] = ref_candidate["name"]
                        match["referee_is_player"] = True
                        logger.info(f"⚖️ 1. tur hakem atandı: {ref_candidate['name']} (seed {ref_candidate['seed']}) -> Maç {match_number}")
                        # Bu hakemi listeden çıkar (her hakem sadece 1 maça)
                        referee_pool.remove(ref_candidate)
                        break
            
            matches.append(match)
            logger.info(f"🏓 Match {match_number}: Seed {p1['seed']} ({participant_names.get(p1['participant_id'])}) vs Seed {p2['seed']} ({participant_names.get(p2['participant_id'])})")
            match_number += 1
    
    # 10. SONRAKI TURLARIN BOŞ MAÇLARINI OLUŞTUR
    total_rounds = int(math.log2(bracket_size))
    
    for round_num in range(2, total_rounds + 1):
        matches_in_round = bracket_size // (2 ** round_num)
        round_name = get_round_name(bracket_size, round_num)
        
        logger.info(f"📋 Creating {matches_in_round} empty matches for Round {round_num} ({round_name})")
        
        for match_idx in range(matches_in_round):
            match_id = str(uuid.uuid4())
            
            # BYE kazananlarını bu tura yerleştir
            # 2. turda, 1. turdaki BYE kazananlarını yerleştir
            p1_id = None
            p1_name = "TBD"
            p1_seed = None
            p2_id = None
            p2_name = "TBD"
            p2_seed = None
            
            if round_num == 2:
                # BYE kazananlarını 2. tura yerleştir
                # Her 2. tur maçı, 1. turdan 2 maçın kazananını alır
                # match_idx 0 -> 1. tur maç 0 ve 1'in kazananları
                # match_idx 1 -> 1. tur maç 2 ve 3'ün kazananları, vs.
                source_match_1_idx = match_idx * 2
                source_match_2_idx = match_idx * 2 + 1
                
                # 1. kaynak maç BYE mi?
                for bw in bye_winners:
                    if bw["first_round_match_idx"] == source_match_1_idx:
                        p1_id = bw["participant"]["participant_id"]
                        p1_name = participant_names.get(p1_id, "BYE Winner")
                        p1_seed = bw["participant"]["seed"]
                        logger.info(f"📥 2. tur maç {match_idx} P1 <- BYE kazananı: {p1_name}")
                    if bw["first_round_match_idx"] == source_match_2_idx:
                        p2_id = bw["participant"]["participant_id"]
                        p2_name = participant_names.get(p2_id, "BYE Winner")
                        p2_seed = bw["participant"]["seed"]
                        logger.info(f"📥 2. tur maç {match_idx} P2 <- BYE kazananı: {p2_name}")
            
            match = {
                "id": match_id,
                "event_id": event_id,
                "group_id": None,
                "group_name": f"{'Teselli ' if is_consolation else ''}Eleme",
                "category": category,
                "round_number": round_num,
                "round_name": round_name,
                "match_number": match_number,
                "bracket_match_number": match_idx + 1,
                "participant1_id": p1_id,
                "participant1_name": p1_name,
                "participant1_seed": p1_seed,
                "participant2_id": p2_id,
                "participant2_name": p2_name,
                "participant2_seed": p2_seed,
                "status": "pending",  # Önceki tur tamamlanana kadar beklemede
                "score": None,
                "winner_id": None,
                "bracket_position": bracket_position_type,
                "bracket_round": round_num,
                "bracket_index": match_idx,
                "stage": "elimination",
                "is_bye": False,
                "source_match_1": source_match_1_idx if round_num == 2 else (match_idx * 2),
                "source_match_2": source_match_2_idx if round_num == 2 else (match_idx * 2 + 1),
                "created_at": datetime.utcnow()
            }
            matches.append(match)
            match_number += 1
    
    # 11. MAÇLARI KAYDET
    if matches:
        await db.event_matches.insert_many(matches)
        logger.info(f"✅ Created {len(matches)} {bracket_type} elimination matches (all rounds)")
    
    # 12. BRACKET KAYDINI OLUŞTUR
    bracket_id = str(uuid.uuid4())
    bracket_record = {
        "id": bracket_id,
        "event_id": event_id,
        "category_key": category,
        "bracket_type": bracket_position_type,
        "bracket_size": bracket_size,
        "total_participants": n,
        "byes_count": byes_needed,
        "total_rounds": int(math.log2(bracket_size)),
        "bye_winners": [{"participant_id": bw["participant"]["participant_id"], 
                        "seed": bw["participant"]["seed"],
                        "first_round_match_idx": bw["first_round_match_idx"]} for bw in bye_winners],
        "seeding": [{"participant_id": p["participant_id"], 
                    "seed": p["seed"], 
                    "name": participant_names.get(p["participant_id"])} for p in seeded_participants],
        "created_at": datetime.utcnow()
    }
    await db.event_brackets.insert_one(bracket_record)
    
    return {
        "status": "success",
        "message": f"{bracket_type} bracket oluşturuldu",
        "category": category,
        "bracket_id": bracket_id,
        "bracket_size": bracket_size,
        "participants": n,
        "byes": byes_needed,
        "matches_created": len(matches),
        "bye_advances": len(bye_winners)
    }


async def _create_consolation_bracket_for_category(db, event_id: str, event: dict, category: str):
    """
    Tek bir kategori için TESELLİ eleme bracket'i oluşturur.
    ÖNCELİKLE teselli eleme gruplarından okur, yoksa normal gruplardan 3+ sıradakileri alır.
    """
    
    logger.info(f"🎗️ Creating CONSOLATION bracket for category: {category}")
    
    # ÖNCELİKLE: Teselli eleme gruplarından veri al
    consolation_groups = await db.event_groups.find({
        "event_id": event_id,
        "group_type": "elimination",
        "elimination_type": "consolation",
        "$or": [
            {"category": category},
            {"category": {"$regex": f"^{category}$", "$options": "i"}},
            {"name": {"$regex": f"{category}", "$options": "i"}}
        ]
    }).to_list(length=20)
    
    if consolation_groups:
        logger.info(f"✅ Found {len(consolation_groups)} consolation elimination groups")
        
        # Teselli eleme grubundan katılımcıları al
        consolation_participants = []
        for cg in consolation_groups:
            participant_details = cg.get("participant_details", [])
            for i, pd in enumerate(participant_details):
                consolation_participants.append({
                    "participant_id": pd.get("id"),
                    "group_name": pd.get("from_group", "Teselli Grubu"),
                    "group_category": category,
                    "group_position": pd.get("group_position", i + 1),
                    "points": pd.get("points", 0),
                    "wins": 0,
                    "goal_diff": pd.get("goal_diff", 0),
                    "seed": pd.get("seed", i + 1)
                })
        
        logger.info(f"✅ Got {len(consolation_participants)} participants from consolation groups")
        
        if len(consolation_participants) < 2:
            return {
                "status": "skipped",
                "message": "Teselli için yeterli oyuncu yok (en az 2 gerekli)",
                "category": category
            }
        
        # Kategori adından yaş grubunu çıkar
        import re
        age_match = re.search(r'(\d+[-\s]?\d*\s*(üstü|üzeri|altı|ve üstü)?)', category, re.IGNORECASE)
        age_group = age_match.group(0).strip() if age_match else ""
        consolation_category = f"{age_group} Teselli" if age_group else f"{category} Teselli"
        
        # is_consolation=True ile _create_bracket_for_category çağır
        return await _create_bracket_for_category(db, event_id, event, category, is_consolation=True)
    
    # FALLBACK: Teselli eleme grubu yoksa normal gruplardan 3+ sıradakileri al
    logger.info(f"⚠️ No consolation elimination groups found, falling back to regular groups")
    
    # Kategori adından yaş grubunu çıkar
    # Örn: "Erkekler 70 üstü Tekler" -> "70 üstü"
    import re
    age_match = re.search(r'(\d+[-\s]?\d*\s*(üstü|üzeri|altı|ve üstü)?)', category, re.IGNORECASE)
    age_group = age_match.group(0).strip() if age_match else ""
    
    # Teselli kategori adı oluştur
    consolation_category = f"{age_group} Teselli" if age_group else f"{category} Teselli"
    
    logger.info(f"🎗️ Consolation category name: {consolation_category}")
    
    # Grupları al (bu kategoriden)
    group_query = {
        "event_id": event_id,
        "$or": [
            {"category": category},
            {"category": {"$regex": f"^{category}$", "$options": "i"}},
            {"name": {"$regex": f"^{category}", "$options": "i"}}
        ]
    }
    
    groups = await db.event_groups.find(group_query).to_list(length=100)
    if not groups:
        raise Exception(f"'{category}' kategorisinde grup bulunamadı")
    
    # Turnuva ayarlarını al
    tournament_settings = await db.event_tournament_settings.find_one({"event_id": event_id})
    if tournament_settings is None:
        # Eğer ayrı collection'da yoksa, event içindeki tournament_settings'i kullan
        tournament_settings = event.get("tournament_settings", {})
    advance_count = tournament_settings.get("advance_from_group", 2) if tournament_settings else 2
    
    # Her gruptan 3. ve sonraki sıradaki katılımcıları al
    consolation_participants = []
    
    for group in groups:
        group_id = group["id"]
        group_name = group["name"]
        group_category = group.get("category", group_name)
        
        # Grup sıralamasını al
        standings = await db.event_standings.find({"group_id": group_id}).to_list(length=50)
        
        if not standings:
            # Sıralama yoksa katılımcıları direkt al
            participant_ids = group.get("participant_ids", [])
            for i, pid in enumerate(participant_ids[advance_count:], start=advance_count+1):
                if isinstance(pid, dict):
                    pid = pid.get("id")
                consolation_participants.append({
                    "participant_id": pid,
                    "group_name": group_name,
                    "group_category": group_category,
                    "group_position": i,
                    "points": 0,
                    "wins": 0,
                    "goal_diff": 0
                })
        else:
            # Sıralamaya göre 3. ve sonraki sıradakileri al
            sorted_standings = sorted(
                standings,
                key=lambda x: (
                    x.get("points", 0),
                    x.get("goals_for", 0) - x.get("goals_against", 0),
                    x.get("wins", 0)
                ),
                reverse=True
            )
            
            # 3. sıradan itibaren al (advance_count sonrası)
            for i, standing in enumerate(sorted_standings[advance_count:], start=advance_count+1):
                consolation_participants.append({
                    "participant_id": standing["participant_id"],
                    "group_name": group_name,
                    "group_category": group_category,
                    "group_position": i,
                    "points": standing.get("points", 0),
                    "wins": standing.get("wins", 0),
                    "goal_diff": standing.get("goals_for", 0) - standing.get("goals_against", 0)
                })
    
    logger.info(f"🎗️ Consolation participants count: {len(consolation_participants)}")
    
    if len(consolation_participants) < 2:
        raise Exception(f"'{category}' kategorisinde teselli eleme için en az 2 katılımcı gerekli (bulunan: {len(consolation_participants)})")
    
    # Katılımcıları sırala - puana ve averaja göre
    seeded_participants = sorted(
        consolation_participants,
        key=lambda x: (
            -x["points"],
            -x["goal_diff"],
            -x["wins"],
            x["group_position"]  # Grup sırası düşük olanlar önce
        )
    )
    
    # Seed numarası ata
    for i, p in enumerate(seeded_participants):
        p["seed"] = i + 1
    
    # Bracket boyutunu hesapla (2'nin kuvveti)
    n = len(seeded_participants)
    bracket_size = 2 ** math.ceil(math.log2(n))
    byes_needed = bracket_size - n
    
    logger.info(f"🎗️ Consolation bracket size: {bracket_size}, BYEs: {byes_needed}")
    
    # Standart bracket yerleşimi
    def generate_bracket_order(size):
        if size == 2:
            return [1, 2]
        half_size = size // 2
        upper_half = generate_bracket_order(half_size)
        lower_half = [size + 1 - x for x in upper_half]
        result = []
        for i in range(half_size):
            result.append(upper_half[i])
            result.append(lower_half[i])
        return result
    
    bracket_order = generate_bracket_order(bracket_size)
    
    # Participant'ları yerleştir
    positioned_participants = []
    for seed_position in bracket_order:
        if seed_position <= n:
            positioned_participants.append(seeded_participants[seed_position - 1])
        else:
            positioned_participants.append(None)
    
    # Participant isimlerini çek
    participant_names = {}
    for p in seeded_participants:
        pid = p["participant_id"]
        participant = await db.event_participants.find_one({"id": pid})
        if participant:
            pname = participant.get("name")
            if pname:
                participant_names[pid] = pname
            else:
                user_id = participant.get("user_id")
                if user_id:
                    user = await db.users.find_one({"id": user_id})
                    if user:
                        uname = user.get("full_name") or user.get("name")
                        participant_names[pid] = uname if uname else f"Katılımcı {pid[:8]}"
                    else:
                        participant_names[pid] = f"Katılımcı {pid[:8]}"
                else:
                    participant_names[pid] = f"Katılımcı {pid[:8]}"
        else:
            user = await db.users.find_one({"id": pid})
            if user:
                uname = user.get("full_name") or user.get("name")
                participant_names[pid] = uname if uname else f"Kullanıcı {pid[:8]}"
            else:
                participant_names[pid] = f"Katılımcı {pid[:8]}"
    
    # İlk tur maçlarını oluştur
    round_1_matches = []
    bye_winners = []
    match_number = 1
    
    for i in range(0, bracket_size, 2):
        p1 = positioned_participants[i]
        p2 = positioned_participants[i + 1]
        
        if p1 is None and p2 is None:
            continue
        elif p1 is None:
            bye_winners.append({"participant": p2, "match_number": match_number})
        elif p2 is None:
            bye_winners.append({"participant": p1, "match_number": match_number})
        else:
            match_id = str(uuid.uuid4())
            match = {
                "id": match_id,
                "event_id": event_id,
                "group_id": None,
                "group_name": "Teselli Eleme",
                "category": consolation_category,
                "round_number": 1,
                "round_name": get_consolation_round_name(bracket_size, 1),
                "match_number": match_number,
                "participant1_id": p1["participant_id"],
                "participant1_name": participant_names.get(p1["participant_id"], "Unknown"),
                "participant1_seed": p1["seed"],
                "participant2_id": p2["participant_id"],
                "participant2_name": participant_names.get(p2["participant_id"], "Unknown"),
                "participant2_seed": p2["seed"],
                "status": "scheduled",
                "score": None,
                "sets": [],
                "winner_id": None,
                "court_number": None,
                "referee_id": None,
                "scheduled_time": None,
                "bracket_position": "elimination",
                "bracket_round": 1,
                "is_consolation": True,
                "next_match_id": None,
                "created_at": datetime.utcnow()
            }
            round_1_matches.append(match)
        
        match_number += 1
    
    # Maçları veritabanına ekle
    if round_1_matches:
        await db.event_matches.insert_many(round_1_matches)
        logger.info(f"✅ Created {len(round_1_matches)} consolation matches for {consolation_category}")
    
    return {
        "status": "success",
        "message": f"Teselli bracket'ı oluşturuldu: {consolation_category}",
        "category": consolation_category,
        "original_category": category,
        "data": {
            "total_participants": n,
            "bracket_size": bracket_size,
            "byes_count": byes_needed,
            "matches_created": len(round_1_matches)
        }
    }


def get_consolation_round_name(bracket_size: int, round_number: int) -> str:
    """Teselli bracket turu için isim belirle"""
    total_rounds = int(math.log2(bracket_size))
    remaining_rounds = total_rounds - round_number + 1
    
    if remaining_rounds == 1:
        return "Teselli Finali"
    elif remaining_rounds == 2:
        return "Teselli Yarı Final"
    elif remaining_rounds == 3:
        return "Teselli Çeyrek Final"
    else:
        return f"Teselli {round_number}. Tur"


def get_round_name(bracket_size: int, round_number: int) -> str:
    """Tur için isim belirle"""
    total_rounds = int(math.log2(bracket_size))
    remaining_rounds = total_rounds - round_number + 1
    
    if remaining_rounds == 1:
        return "Final"
    elif remaining_rounds == 2:
        return "Yarı Final"
    elif remaining_rounds == 3:
        return "Çeyrek Final"
    elif remaining_rounds == 4:
        return "Son 16"
    elif remaining_rounds == 5:
        return "Son 32"
    else:
        return f"{round_number}. Tur"



# ================== BRACKET DÜZENLEME ENDPOINTLERİ ==================

@event_management_router.get("/{event_id}/bracket/slots")
async def get_bracket_slots(event_id: str, category: str = Query(...)):
    """
    Belirli bir kategori için bracket slot'larını getir.
    Yöneticiler düzenleme için kullanır.
    """
    global db
    
    # Etkinliği kontrol et
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Bu kategorideki eleme maçlarını al
    elimination_matches = await db.event_matches.find({
        "event_id": event_id,
        "category": category,
        "bracket_position": "elimination"
    }).to_list(100)
    
    # Katılımcıları al
    participants = await db.event_participants.find({
        "event_id": event_id
    }).to_list(500)
    
    # Kullanıcı isimlerini al
    user_ids = [p.get("user_id") for p in participants if p.get("user_id")]
    users = await db.users.find({"id": {"$in": user_ids}}).to_list(500)
    user_map = {u["id"]: u.get("full_name", "Bilinmeyen") for u in users}
    
    # Slot'ları oluştur
    slots = []
    for match in sorted(elimination_matches, key=lambda x: (x.get("round_number", 1), x.get("match_order", 1))):
        slots.append({
            "match_id": match.get("id"),
            "round_number": match.get("round_number", 1),
            "match_order": match.get("match_order", 1),
            "participant1_id": match.get("participant1_id"),
            "participant1_name": match.get("participant1_name") or user_map.get(match.get("participant1_id"), ""),
            "participant2_id": match.get("participant2_id"),
            "participant2_name": match.get("participant2_name") or user_map.get(match.get("participant2_id"), ""),
            "status": match.get("status"),
            "winner_id": match.get("winner_id"),
            "score": match.get("score")
        })
    
    # Katılımcı listesini de döndür (oyuncu ekleme için)
    available_participants = []
    for p in participants:
        user_id = p.get("user_id")
        available_participants.append({
            "id": user_id,
            "name": user_map.get(user_id, "Bilinmeyen"),
            "category": p.get("category", ""),
            "game_types": p.get("game_types", [])
        })
    
    return {
        "category": category,
        "slots": slots,
        "participants": available_participants,
        "total_rounds": max([s["round_number"] for s in slots]) if slots else 0
    }


@event_management_router.put("/{event_id}/bracket/update-slot")
async def update_bracket_slot(
    event_id: str,
    match_id: str = Body(...),
    participant1_id: Optional[str] = Body(None),
    participant2_id: Optional[str] = Body(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Bracket slot'ını güncelle (oyuncu ekle/değiştir).
    Sadece yöneticiler kullanabilir.
    """
    global db
    
    # Etkinliği kontrol et
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yönetici kontrolü
    user_id = current_user.get("id")
    organizer_id = event.get("organizer_id")
    creator_id = event.get("created_by") or event.get("creator_id")
    admin_ids = event.get("admin_ids", [])
    organizer_ids = event.get("organizers", [])
    
    is_admin = user_id == organizer_id or user_id == creator_id or user_id in admin_ids or user_id in organizer_ids or current_user.get("user_type") == "admin"
    if not is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Maçı bul
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    # Oyuncu isimlerini al
    p1_name = None
    p2_name = None
    
    if participant1_id:
        user1 = await db.users.find_one({"id": participant1_id})
        p1_name = user1.get("full_name", "Bilinmeyen") if user1 else "Bilinmeyen"
    
    if participant2_id:
        user2 = await db.users.find_one({"id": participant2_id})
        p2_name = user2.get("full_name", "Bilinmeyen") if user2 else "Bilinmeyen"
    
    # Güncelle
    update_data = {
        "participant1_id": participant1_id,
        "participant1_name": p1_name,
        "participant2_id": participant2_id,
        "participant2_name": p2_name,
        "updated_at": datetime.utcnow()
    }
    
    await db.event_matches.update_one(
        {"id": match_id},
        {"$set": update_data}
    )
    
    logger.info(f"✅ Bracket slot güncellendi: {match_id} -> P1={p1_name}, P2={p2_name}")
    
    return {
        "status": "success",
        "message": "Slot güncellendi",
        "match_id": match_id,
        "participant1_name": p1_name,
        "participant2_name": p2_name
    }


@event_management_router.post("/{event_id}/bracket/create-matches")
async def create_bracket_matches(
    event_id: str,
    category: str = Body(...),
    slots: List[dict] = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Bracket'tan maçları oluştur/güncelle.
    Sadece yöneticiler kullanabilir.
    """
    global db
    
    # Etkinliği kontrol et
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yönetici kontrolü
    user_id = current_user.get("id")
    organizer_id = event.get("organizer_id")
    creator_id = event.get("created_by") or event.get("creator_id")
    admin_ids = event.get("admin_ids", [])
    organizer_ids = event.get("organizers", [])
    
    is_admin = user_id == organizer_id or user_id == creator_id or user_id in admin_ids or user_id in organizer_ids or current_user.get("user_type") == "admin"
    if not is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    created_count = 0
    updated_count = 0
    scheduled_count = 0
    
    for slot in slots:
        round_number = slot.get("round_number", 1)
        match_order = slot.get("match_order", 1)
        participant1_id = slot.get("participant1_id")
        participant2_id = slot.get("participant2_id")
        match_id = slot.get("match_id")
        
        # Oyuncu isimlerini al
        p1_name = None
        p2_name = None
        
        if participant1_id:
            user1 = await db.users.find_one({"id": participant1_id})
            p1_name = user1.get("full_name", "Bilinmeyen") if user1 else "Bilinmeyen"
        
        if participant2_id:
            user2 = await db.users.find_one({"id": participant2_id})
            p2_name = user2.get("full_name", "Bilinmeyen") if user2 else "Bilinmeyen"
        
        # Maç var mı kontrol et
        if match_id:
            existing_match = await db.event_matches.find_one({"id": match_id})
        else:
            existing_match = await db.event_matches.find_one({
                "event_id": event_id,
                "category": category,
                "bracket_position": "elimination",
                "round_number": round_number,
                "match_order": match_order
            })
        
        # Her iki oyuncu da varsa status = scheduled
        status = "scheduled" if participant1_id and participant2_id else "pending"
        
        if existing_match:
            # Güncelle
            await db.event_matches.update_one(
                {"id": existing_match["id"]},
                {"$set": {
                    "participant1_id": participant1_id,
                    "participant1_name": p1_name,
                    "participant2_id": participant2_id,
                    "participant2_name": p2_name,
                    "status": status,
                    "updated_at": datetime.utcnow()
                }}
            )
            updated_count += 1
        else:
            # Yeni maç oluştur
            # Tur ismi belirle
            total_rounds = max([s.get("round_number", 1) for s in slots])
            remaining = total_rounds - round_number + 1
            if remaining == 1:
                round_name = "Final"
            elif remaining == 2:
                round_name = "Yarı Final"
            elif remaining == 3:
                round_name = "Çeyrek Final"
            else:
                round_name = f"{round_number}. Tur"
            
            new_match = {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "category": category,
                "bracket_position": "elimination",
                "round_number": round_number,
                "round_name": round_name,
                "match_order": match_order,
                "participant1_id": participant1_id,
                "participant1_name": p1_name,
                "participant2_id": participant2_id,
                "participant2_name": p2_name,
                "status": status,
                "group_name": "Eleme",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            await db.event_matches.insert_one(new_match)
            created_count += 1
        
        if status == "scheduled":
            scheduled_count += 1
    
    logger.info(f"✅ Bracket maçları oluşturuldu: {category} - Created={created_count}, Updated={updated_count}, Scheduled={scheduled_count}")
    
    return {
        "status": "success",
        "message": f"{created_count} maç oluşturuldu, {updated_count} maç güncellendi, {scheduled_count} maç planlandı",
        "created_count": created_count,
        "updated_count": updated_count,
        "scheduled_count": scheduled_count
    }


@event_management_router.post("/{event_id}/bracket/add-slot")
async def add_bracket_slot(
    event_id: str,
    category: str = Body(...),
    round_number: int = Body(...),
    match_order: int = Body(...),
    participant1_id: Optional[str] = Body(None),
    participant2_id: Optional[str] = Body(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Yeni bir bracket slot'u (maç) ekle.
    Sadece yöneticiler kullanabilir.
    """
    global db
    
    # Etkinliği kontrol et
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yönetici kontrolü
    user_id = current_user.get("id")
    organizer_id = event.get("organizer_id")
    creator_id = event.get("created_by") or event.get("creator_id")
    admin_ids = event.get("admin_ids", [])
    organizer_ids = event.get("organizers", [])
    
    is_admin = user_id == organizer_id or user_id == creator_id or user_id in admin_ids or user_id in organizer_ids or current_user.get("user_type") == "admin"
    if not is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Zaten var mı kontrol et
    existing = await db.event_matches.find_one({
        "event_id": event_id,
        "category": category,
        "bracket_position": "elimination",
        "round_number": round_number,
        "match_order": match_order
    })
    
    if existing:
        raise HTTPException(status_code=400, detail="Bu pozisyonda zaten bir maç var")
    
    # Oyuncu isimlerini al
    p1_name = None
    p2_name = None
    
    if participant1_id:
        user1 = await db.users.find_one({"id": participant1_id})
        p1_name = user1.get("full_name", "Bilinmeyen") if user1 else "Bilinmeyen"
    
    if participant2_id:
        user2 = await db.users.find_one({"id": participant2_id})
        p2_name = user2.get("full_name", "Bilinmeyen") if user2 else "Bilinmeyen"
    
    # Status belirle
    status = "scheduled" if participant1_id and participant2_id else "pending"
    
    # Tur ismi
    round_name = f"{round_number}. Tur"
    
    new_match = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "category": category,
        "bracket_position": "elimination",
        "round_number": round_number,
        "round_name": round_name,
        "match_order": match_order,
        "participant1_id": participant1_id,
        "participant1_name": p1_name,
        "participant2_id": participant2_id,
        "participant2_name": p2_name,
        "status": status,
        "group_name": "Eleme",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.event_matches.insert_one(new_match)
    
    return {
        "status": "success",
        "message": "Slot eklendi",
        "match_id": new_match["id"]
    }


@event_management_router.delete("/{event_id}/bracket/delete-slot/{match_id}")
async def delete_bracket_slot(
    event_id: str,
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Bracket slot'unu (maçı) sil.
    Sadece yöneticiler kullanabilir.
    """
    global db
    
    # Etkinliği kontrol et
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yönetici kontrolü
    user_id = current_user.get("id")
    organizer_id = event.get("organizer_id")
    creator_id = event.get("created_by") or event.get("creator_id")
    admin_ids = event.get("admin_ids", [])
    organizer_ids = event.get("organizers", [])
    
    is_admin = user_id == organizer_id or user_id == creator_id or user_id in admin_ids or user_id in organizer_ids or current_user.get("user_type") == "admin"
    if not is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Maçı bul
    match = await db.event_matches.find_one({"id": match_id, "event_id": event_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    # Tamamlanmış maç silinemez
    if match.get("status") in ["completed", "finished"]:
        raise HTTPException(status_code=400, detail="Tamamlanmış maç silinemez")
    
    await db.event_matches.delete_one({"id": match_id})
    
    return {"status": "success", "message": "Slot silindi"}


@event_management_router.get("/{event_id}/bracket/categories")
async def get_bracket_categories(event_id: str):
    """
    Etkinlikteki bracket kategorilerini getir.
    """
    global db
    
    # Etkinliği kontrol et
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Eleme maçlarından kategorileri çek
    elimination_matches = await db.event_matches.find({
        "event_id": event_id,
        "bracket_position": "elimination"
    }).to_list(500)
    
    categories = set()
    for match in elimination_matches:
        if match.get("category"):
            categories.add(match.get("category"))
    
    return {"categories": sorted(list(categories))}


@event_management_router.post("/{event_id}/bracket/generate-next-round")
async def generate_next_round_matches(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Tamamlanan maçların kazananlarını bir sonraki tura yerleştir ve maçları oluştur.
    Sadece yöneticiler kullanabilir.
    """
    global db
    
    # Etkinliği kontrol et
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yönetici kontrolü
    user_id = current_user.get("id")
    organizer_id = event.get("organizer_id")
    creator_id = event.get("created_by") or event.get("creator_id")
    admin_ids = event.get("admin_ids") or []
    organizer_ids = event.get("organizers") or []
    
    is_admin = (
        user_id == organizer_id or 
        user_id == creator_id or 
        user_id in admin_ids or 
        user_id in organizer_ids or
        current_user.get("user_type") == "admin"
    )
    
    if not is_admin:
        logger.warning(f"❌ Yetki hatası: user_id={user_id}, organizer_id={organizer_id}, creator_id={creator_id}")
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Tüm eleme maçlarını al
    elimination_matches = await db.event_matches.find({
        "event_id": event_id,
        "bracket_position": "elimination"
    }).to_list(500)
    
    if not elimination_matches:
        return {"status": "error", "message": "Eleme maçı bulunamadı"}
    
    # Kategorilere göre grupla
    categories = {}
    for match in elimination_matches:
        cat = match.get("category", "Genel")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(match)
    
    total_advanced = 0
    total_created = 0
    total_scheduled = 0
    
    for category, cat_matches in categories.items():
        # Tamamlanan maçları bul (kazananı olan)
        completed_matches = [m for m in cat_matches if m.get("winner_id") and m.get("status") in ["completed", "finished", "pending_confirmation"]]
        
        for match in completed_matches:
            winner_id = match.get("winner_id")
            current_round = match.get("round_number", 1)
            match_order = match.get("match_order", 1)
            
            # Kazananın ismini al
            winner_user = await db.users.find_one({"id": winner_id})
            winner_name = winner_user.get("full_name", "Bilinmeyen") if winner_user else "Bilinmeyen"
            
            # Bir sonraki tur bilgilerini hesapla
            next_round = current_round + 1
            next_match_order = ((match_order - 1) // 2) + 1
            is_participant1 = (match_order % 2) == 1
            
            # Bir sonraki tur maçını bul veya oluştur
            next_match = await db.event_matches.find_one({
                "event_id": event_id,
                "category": category,
                "bracket_position": "elimination",
                "round_number": next_round,
                "match_order": next_match_order
            })
            
            if next_match:
                # Mevcut maçı güncelle
                update_field = "participant1_id" if is_participant1 else "participant2_id"
                update_name_field = "participant1_name" if is_participant1 else "participant2_name"
                
                # Zaten yerleştirilmiş mi kontrol et
                current_value = next_match.get(update_field)
                if current_value == winner_id:
                    continue  # Zaten yerleştirilmiş
                
                await db.event_matches.update_one(
                    {"id": next_match["id"]},
                    {"$set": {
                        update_field: winner_id,
                        update_name_field: winner_name,
                        "updated_at": datetime.utcnow()
                    }}
                )
                total_advanced += 1
                
                # Her iki taraf da doluysa maçı "scheduled" yap
                updated_next = await db.event_matches.find_one({"id": next_match["id"]})
                if updated_next and updated_next.get("participant1_id") and updated_next.get("participant2_id"):
                    if updated_next.get("status") != "scheduled":
                        await db.event_matches.update_one(
                            {"id": updated_next["id"]},
                            {"$set": {"status": "scheduled"}}
                        )
                        total_scheduled += 1
            else:
                # Yeni maç oluştur
                # Tur ismi belirle
                max_round = max([m.get("round_number", 1) for m in cat_matches])
                if next_round > max_round:
                    # Yeni tur oluşturulması gerekiyor
                    remaining = max_round - next_round + 2
                    if remaining == 1:
                        round_name = "Final"
                    elif remaining == 2:
                        round_name = "Yarı Final"
                    elif remaining == 3:
                        round_name = "Çeyrek Final"
                    else:
                        round_name = f"{next_round}. Tur"
                else:
                    round_name = f"{next_round}. Tur"
                
                new_match = {
                    "id": str(uuid.uuid4()),
                    "event_id": event_id,
                    "category": category,
                    "bracket_position": "elimination",
                    "round_number": next_round,
                    "round_name": round_name,
                    "match_order": next_match_order,
                    "participant1_id": winner_id if is_participant1 else None,
                    "participant1_name": winner_name if is_participant1 else None,
                    "participant2_id": winner_id if not is_participant1 else None,
                    "participant2_name": winner_name if not is_participant1 else None,
                    "status": "pending",
                    "group_name": "Eleme",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                await db.event_matches.insert_one(new_match)
                total_created += 1
                total_advanced += 1
    
    logger.info(f"✅ Sonraki tur maçları oluşturuldu: Advanced={total_advanced}, Created={total_created}, Scheduled={total_scheduled}")
    
    return {
        "status": "success",
        "message": f"{total_advanced} kazanan ilerletildi, {total_created} yeni maç oluşturuldu, {total_scheduled} maç planlandı",
        "advanced_count": total_advanced,
        "created_count": total_created,
        "scheduled_count": total_scheduled
    }


@event_management_router.post("/{event_id}/bracket/swap-players")
async def swap_bracket_players(
    event_id: str,
    match1_id: str = Body(...),
    match1_position: str = Body(...),  # "p1" veya "p2"
    match2_id: str = Body(...),
    match2_position: str = Body(...),  # "p1" veya "p2"
    current_user: dict = Depends(get_current_user)
):
    """
    İki bracket pozisyonundaki oyuncuları değiştir (swap).
    Sürükle-bırak için kullanılır.
    """
    global db
    
    # Etkinliği kontrol et
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yönetici kontrolü
    user_id = current_user.get("id")
    organizer_id = event.get("organizer_id")
    creator_id = event.get("created_by") or event.get("creator_id")
    admin_ids = event.get("admin_ids", [])
    organizer_ids = event.get("organizers", [])
    
    is_admin = user_id == organizer_id or user_id == creator_id or user_id in admin_ids or user_id in organizer_ids or current_user.get("user_type") == "admin"
    if not is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Maçları bul
    match1 = await db.event_matches.find_one({"id": match1_id, "event_id": event_id})
    match2 = await db.event_matches.find_one({"id": match2_id, "event_id": event_id})
    
    if not match1 or not match2:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    # Tamamlanmış maçlarda değişiklik yapılamaz
    if match1.get("status") in ["completed", "finished"] or match2.get("status") in ["completed", "finished"]:
        raise HTTPException(status_code=400, detail="Tamamlanmış maçlarda değişiklik yapılamaz")
    
    # Pozisyon alanlarını belirle
    field1_id = "participant1_id" if match1_position == "p1" else "participant2_id"
    field1_name = "participant1_name" if match1_position == "p1" else "participant2_name"
    field2_id = "participant1_id" if match2_position == "p1" else "participant2_id"
    field2_name = "participant1_name" if match2_position == "p1" else "participant2_name"
    
    # Değerleri al
    player1_id = match1.get(field1_id)
    player1_name = match1.get(field1_name)
    player2_id = match2.get(field2_id)
    player2_name = match2.get(field2_name)
    
    # Swap yap
    await db.event_matches.update_one(
        {"id": match1_id},
        {"$set": {
            field1_id: player2_id,
            field1_name: player2_name,
            "updated_at": datetime.utcnow()
        }}
    )
    
    await db.event_matches.update_one(
        {"id": match2_id},
        {"$set": {
            field2_id: player1_id,
            field2_name: player1_name,
            "updated_at": datetime.utcnow()
        }}
    )
    
    return {
        "status": "success",
        "message": "Oyuncular değiştirildi"
    }


# ================== SPORCU YÖNETİMİ ENDPOINTLERİ ==================

@event_management_router.get("/{event_id}/athletes")
async def get_event_athletes(
    event_id: str,
    sort_by: str = Query("name", description="Sıralama: name, points, created"),
    sort_order: str = Query("asc", description="Sıralama yönü: asc, desc"),
    search: str = Query(None, description="İsme göre arama"),
    current_user: dict = None
):
    """
    Etkinlik sporcularını listele - puanlarıyla birlikte
    Puanlar user_rankings koleksiyonundan etkinlik spor dalına göre alınır
    """
    global db
    
    # Etkinlik kontrolü
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Etkinliğin spor dalını al ve sport_code'a çevir
    sport_raw = event.get("sport_type") or event.get("sport") or "TABLE_TENNIS"
    
    # Türkçe spor adını sport_code'a çevir
    sport_name_to_code = {
        "Masa Tenisi": "TABLE_TENNIS",
        "masa tenisi": "TABLE_TENNIS",
        "TABLE_TENNIS": "TABLE_TENNIS",
        "Tenis": "TENNIS",
        "tenis": "TENNIS",
        "TENNIS": "TENNIS",
        "Badminton": "BADMINTON",
        "badminton": "BADMINTON",
        "BADMINTON": "BADMINTON",
        "Squash": "SQUASH",
        "squash": "SQUASH",
        "SQUASH": "SQUASH",
        "Padel": "PADEL",
        "padel": "PADEL",
        "PADEL": "PADEL"
    }
    sport_code = sport_name_to_code.get(sport_raw, "TABLE_TENNIS")
    
    participant_ids = event.get("participants", [])
    if not participant_ids:
        return {
            "athletes": [],
            "total_count": 0,
            "event_title": event.get("title", ""),
            "sport_type": sport_code
        }
    
    # Tüm katılımcıların bilgilerini al
    users = await db.users.find({"id": {"$in": participant_ids}}).to_list(length=1000)
    users_map = {u["id"]: u for u in users}
    
    # Sıralama Yönetimi'nden puanları al (user_rankings koleksiyonundan)
    rankings_cursor = db.user_rankings.find({
        "user_id": {"$in": participant_ids},
        "sport_code": sport_code
    })
    rankings_list = await rankings_cursor.to_list(length=1000)
    rankings_map = {r["user_id"]: r.get("points", 0) for r in rankings_list}
    
    # Eski event_athlete_points'tan da puanları al (fallback olarak)
    points_cursor = db.event_athlete_points.find({"event_id": event_id})
    points_list = await points_cursor.to_list(length=1000)
    event_points_map = {p["participant_id"]: p.get("points", 0) for p in points_list}
    
    # Katılımcıların oyun türlerini al (event_participants koleksiyonundan)
    participants_cursor = db.event_participants.find({"event_id": event_id})
    participants_list = await participants_cursor.to_list(length=1000)
    game_types_map = {p["user_id"]: p.get("game_types", []) for p in participants_list}
    
    # Partner ID bilgilerini al
    doubles_partner_id_map = {p["user_id"]: p.get("doubles_partner_id", "") for p in participants_list}
    mixed_partner_id_map = {p["user_id"]: p.get("mixed_partner_id", "") for p in participants_list}
    
    # Partner ID'lerinden isimleri çöz
    all_partner_ids = list(set([pid for pid in doubles_partner_id_map.values() if pid] + 
                               [pid for pid in mixed_partner_id_map.values() if pid]))
    
    partner_names_map = {}
    if all_partner_ids:
        partner_users = await db.users.find({"id": {"$in": all_partner_ids}}).to_list(length=1000)
        for pu in partner_users:
            partner_names_map[pu["id"]] = pu.get("full_name") or pu.get("name") or "Bilinmeyen"
    
    # Sporcu listesini oluştur
    athletes = []
    for pid in participant_ids:
        user = users_map.get(pid, {})
        full_name = user.get("full_name") or user.get("name") or "Bilinmeyen"
        
        # Arama filtresi
        if search and search.lower() not in full_name.lower():
            continue
        
        # Partner adlarını çöz
        doubles_partner_id = doubles_partner_id_map.get(pid, "")
        mixed_partner_id = mixed_partner_id_map.get(pid, "")
        
        doubles_partner_name = partner_names_map.get(doubles_partner_id, "") if doubles_partner_id else ""
        mixed_partner_name = partner_names_map.get(mixed_partner_id, "") if mixed_partner_id else ""
        
        # Doğum yılını hesapla
        birth_year = user.get("birth_year") or user.get("birthYear")
        if not birth_year and user.get("date_of_birth"):
            # date_of_birth varsa yılı çıkar
            dob = user.get("date_of_birth")
            if isinstance(dob, str):
                try:
                    birth_year = int(dob[:4])  # "1974-02-21T00:00:00.000Z" -> 1974
                except:
                    pass
        
        # Puanı önce user_rankings'ten al, yoksa event_athlete_points'tan
        ranking_points = rankings_map.get(pid, 0)
        event_points = event_points_map.get(pid, 0)
        final_points = ranking_points if ranking_points > 0 else event_points
        
        athletes.append({
            "id": pid,
            "name": full_name,
            "avatar": user.get("profile_image") or user.get("profile_photo"),
            "city": user.get("city", ""),
            "gender": user.get("gender", ""),
            "phone": user.get("phone", ""),
            "points": final_points,
            "ranking_points": ranking_points,  # Sıralama yönetiminden gelen puan
            "created_at": user.get("created_at", ""),
            "game_types": game_types_map.get(pid, []),
            "doubles_partner": doubles_partner_name,
            "mixed_doubles_partner": mixed_partner_name,
            "birth_year": birth_year
        })
    
    # Sıralama - Türkçe karakter desteği için özel sıralama
    reverse = sort_order == "desc"
    
    # Türkçe alfabe sırası: a, b, c, ç, d, e, f, g, ğ, h, ı, i, j, k, l, m, n, o, ö, p, r, s, ş, t, u, ü, v, y, z
    def turkish_sort_key(name: str) -> str:
        """Türkçe alfabetik sıralama için key fonksiyonu"""
        # Türkçe karakterleri sıralama için dönüştür
        replacements = [
            ('İ', 'I0'),  # İ -> I'dan sonra ama J'den önce
            ('I', 'I'),   # I normal
            ('ı', 'i0'),  # ı -> i'den önce (h ile i arası)
            ('i', 'i1'),  # i -> ı'dan sonra
            ('Ç', 'C1'),  # Ç -> C'den sonra
            ('ç', 'c1'),
            ('Ğ', 'G1'),  # Ğ -> G'den sonra
            ('ğ', 'g1'),
            ('Ö', 'O1'),  # Ö -> O'dan sonra
            ('ö', 'o1'),
            ('Ş', 'S1'),  # Ş -> S'den sonra
            ('ş', 's1'),
            ('Ü', 'U1'),  # Ü -> U'dan sonra
            ('ü', 'u1'),
        ]
        
        result = name
        for tr_char, replacement in replacements:
            result = result.replace(tr_char, replacement)
        
        return result.lower()
    
    if sort_by == "name":
        athletes.sort(key=lambda x: turkish_sort_key(x["name"]), reverse=reverse)
    elif sort_by == "points":
        athletes.sort(key=lambda x: x["points"], reverse=reverse)
    elif sort_by == "created":
        athletes.sort(key=lambda x: str(x.get("created_at", "")), reverse=reverse)
    
    return {
        "athletes": athletes,
        "total_count": len(athletes),
        "event_title": event.get("title", ""),
        "sport_type": sport_code
    }


@event_management_router.post("/{event_id}/athletes/points/bulk")
async def bulk_update_athlete_points(
    event_id: str,
    data: BulkAthletePointsUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Toplu sporcu puan güncelleme - Excel benzeri hızlı giriş için
    Organizatör/admin tüm sporcuların puanlarını tek seferde güncelleyebilir
    Özel puanlar için custom_score_updates listesi kullanılır
    """
    global db
    
    # Yetki kontrolü
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    user_type = current_user.get("user_type", "")
    user_id = current_user.get("id", "")
    
    # Etkinlik kontrolü
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yetki kontrolü - sadece organizatör veya admin
    organizer_id = event.get("organizer_id") or event.get("creator_id")
    is_organizer = user_id == organizer_id
    is_admin = user_type in ["admin", "super_admin"]
    
    if not is_organizer and not is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Normal puan güncellemelerini uygula
    updated_count = 0
    for update in data.updates:
        # Upsert - varsa güncelle, yoksa oluştur
        result = await db.event_athlete_points.update_one(
            {"event_id": event_id, "participant_id": update.participant_id},
            {
                "$set": {
                    "points": update.points,
                    "updated_at": datetime.utcnow(),
                    "updated_by": user_id
                },
                "$setOnInsert": {
                    "id": f"eap_{event_id}_{update.participant_id}",
                    "event_id": event_id,
                    "participant_id": update.participant_id,
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        if result.modified_count > 0 or result.upserted_id:
            updated_count += 1
    
    # Özel puan güncellemelerini uygula (eğer varsa)
    custom_score_updates = data.custom_score_updates if hasattr(data, 'custom_score_updates') and data.custom_score_updates else []
    use_custom_scoring = data.use_custom_scoring if hasattr(data, 'use_custom_scoring') else False
    custom_scoring_name = data.custom_scoring_name if hasattr(data, 'custom_scoring_name') else 'Özel Puan'
    
    custom_updated_count = 0
    if use_custom_scoring and custom_score_updates:
        # Etkinliğe özel puanlama ayarını kaydet
        await db.events.update_one(
            {"id": event_id},
            {
                "$set": {
                    "use_custom_scoring": True,
                    "custom_scoring_name": custom_scoring_name,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        for cs_update in custom_score_updates:
            participant_id = cs_update.get("participant_id") if isinstance(cs_update, dict) else cs_update.participant_id
            custom_score = cs_update.get("custom_score") if isinstance(cs_update, dict) else cs_update.custom_score
            
            result = await db.event_athlete_points.update_one(
                {"event_id": event_id, "participant_id": participant_id},
                {
                    "$set": {
                        "custom_score": custom_score,
                        "custom_score_name": custom_scoring_name,
                        "updated_at": datetime.utcnow(),
                        "updated_by": user_id
                    },
                    "$setOnInsert": {
                        "id": f"eap_{event_id}_{participant_id}",
                        "event_id": event_id,
                        "participant_id": participant_id,
                        "points": 0,
                        "created_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            if result.modified_count > 0 or result.upserted_id:
                custom_updated_count += 1
    
    return {
        "status": "success",
        "message": f"{updated_count} sporcu puanı, {custom_updated_count} özel puan güncellendi",
        "updated_count": updated_count,
        "custom_updated_count": custom_updated_count
    }


@event_management_router.post("/{event_id}/athletes")
async def add_athlete_to_event(
    event_id: str,
    data: AthleteAdd,
    current_user: dict = Depends(get_current_user)
):
    """
    Etkinliğe yeni sporcu ekle
    """
    global db
    
    # Yetki kontrolü
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    user_type = current_user.get("user_type", "")
    user_id = current_user.get("id", "")
    
    # Etkinlik kontrolü
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yetki kontrolü
    organizer_id = event.get("organizer_id") or event.get("creator_id")
    is_organizer = user_id == organizer_id
    is_admin = user_type in ["admin", "super_admin"]
    
    if not is_organizer and not is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Kullanıcı kontrolü
    user = await db.users.find_one({"id": data.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Zaten katılımcı mı?
    participants = event.get("participants", [])
    if data.user_id in participants:
        raise HTTPException(status_code=400, detail="Kullanıcı zaten bu etkinliğe kayıtlı")
    
    # Etkinliğe ekle
    participants.append(data.user_id)
    await db.events.update_one(
        {"id": event_id},
        {
            "$set": {
                "participants": participants,
                "participant_count": len(participants),
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    )
    
    # Başlangıç puanı varsa kaydet
    if data.initial_points != 0:
        await db.event_athlete_points.update_one(
            {"event_id": event_id, "participant_id": data.user_id},
            {
                "$set": {
                    "points": data.initial_points,
                    "updated_at": datetime.utcnow(),
                    "updated_by": user_id
                },
                "$setOnInsert": {
                    "id": f"eap_{event_id}_{data.user_id}",
                    "event_id": event_id,
                    "participant_id": data.user_id,
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )
    
    return {
        "status": "success",
        "message": f"{user.get('full_name', 'Kullanıcı')} etkinliğe eklendi",
        "athlete": {
            "id": data.user_id,
            "name": user.get("full_name") or user.get("name"),
            "points": data.initial_points
        }
    }


@event_management_router.delete("/{event_id}/athletes/{athlete_id}")
async def remove_athlete_from_event(
    event_id: str,
    athlete_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Etkinlikten sporcu çıkar
    """
    global db
    
    # Yetki kontrolü
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    user_type = current_user.get("user_type", "")
    user_id = current_user.get("id", "")
    
    # Etkinlik kontrolü
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Yetki kontrolü
    organizer_id = event.get("organizer_id") or event.get("creator_id")
    is_organizer = user_id == organizer_id
    is_admin = user_type in ["admin", "super_admin"]
    
    if not is_organizer and not is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    # Katılımcı listesinden çıkar
    participants = event.get("participants", [])
    if athlete_id not in participants:
        raise HTTPException(status_code=400, detail="Kullanıcı bu etkinlikte değil")
    
    participants.remove(athlete_id)
    await db.events.update_one(
        {"id": event_id},
        {
            "$set": {
                "participants": participants,
                "participant_count": len(participants),
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    )
    
    # Gruplardan da çıkar
    await db.event_groups.update_many(
        {"event_id": event_id, "participant_ids": athlete_id},
        {"$pull": {"participant_ids": athlete_id}}
    )
    
    # Puan kaydını sil (opsiyonel - yorumda bırakılabilir)
    # await db.event_athlete_points.delete_one({"event_id": event_id, "participant_id": athlete_id})
    
    return {
        "status": "success",
        "message": "Sporcu etkinlikten çıkarıldı"
    }


@event_management_router.get("/{event_id}/athletes/search")
async def search_users_for_event(
    event_id: str,
    query: str = Query(..., min_length=2, description="Arama sorgusu (en az 2 karakter)"),
    limit: int = Query(20, description="Sonuç limiti"),
    current_user: dict = None
):
    """
    Etkinliğe eklenebilecek kullanıcıları ara
    Sadece henüz etkinliğe eklenmemiş kullanıcıları döner
    """
    global db
    
    # Etkinlik kontrolü
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    existing_participants = event.get("participants", [])
    
    # Kullanıcı ara - isim veya telefon
    search_filter = {
        "$and": [
            {"id": {"$nin": existing_participants}},  # Zaten katılımcı olmayanlar
            {
                "$or": [
                    {"full_name": {"$regex": query, "$options": "i"}},
                    {"name": {"$regex": query, "$options": "i"}},
                    {"phone": {"$regex": query, "$options": "i"}}
                ]
            }
        ]
    }
    
    users = await db.users.find(search_filter).limit(limit).to_list(length=limit)
    
    return {
        "users": [
            {
                "id": u["id"],
                "name": u.get("full_name") or u.get("name") or "Bilinmeyen",
                "phone": u.get("phone", ""),
                "avatar": u.get("profile_image") or u.get("profile_photo"),
                "city": u.get("city", ""),
                "gender": u.get("gender", "")
            }
            for u in users
        ],
        "total": len(users)
    }


# ================== HAKEM YÖNETİMİ ENDPOINTLERİ ==================

class RefereeAdd(BaseModel):
    """Etkinliğe hakem ekleme"""
    user_id: str
    initial_points: float = 0  # Başlangıç puanı (opsiyonel)

class RefereePointUpdate(BaseModel):
    """Tek hakem puan güncelleme"""
    referee_id: str
    points: float

class BulkRefereePointsUpdate(BaseModel):
    """Toplu hakem puan güncelleme"""
    updates: List[RefereePointUpdate]


@event_management_router.get("/{event_id}/referees")
async def get_event_referees(
    event_id: str,
    sort_by: str = Query("name", description="Sıralama: name, points, created"),
    sort_order: str = Query("asc", description="Sıralama yönü: asc, desc"),
    search: str = Query(None, description="İsme göre arama"),
    current_user: dict = None
):
    """
    Etkinlik hakemlerini listele - puanlarıyla birlikte
    """
    global db
    
    # Etkinlik kontrolü
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    referee_ids = event.get("referees", [])
    if not referee_ids:
        return {
            "referees": [],
            "total_count": 0,
            "event_title": event.get("title", "")
        }
    
    # Tüm hakemlerin bilgilerini al
    users = await db.users.find({"id": {"$in": referee_ids}}).to_list(length=1000)
    users_map = {u["id"]: u for u in users}
    
    # Etkinlik puanlarını al (event_referee_points koleksiyonundan)
    points_cursor = db.event_referee_points.find({"event_id": event_id})
    points_list = await points_cursor.to_list(length=1000)
    points_map = {p["referee_id"]: p.get("points", 0) for p in points_list}
    
    # Hakem listesini oluştur
    referees = []
    for rid in referee_ids:
        user = users_map.get(rid, {})
        full_name = user.get("full_name") or user.get("name") or "Bilinmeyen"
        
        # Arama filtresi
        if search and search.lower() not in full_name.lower():
            continue
        
        referees.append({
            "id": rid,
            "name": full_name,
            "avatar": user.get("profile_image") or user.get("profile_photo"),
            "city": user.get("city", ""),
            "gender": user.get("gender", ""),
            "phone": user.get("phone", ""),
            "points": points_map.get(rid, 0),
            "created_at": user.get("created_at", "")
        })
    
    # Türkçe sıralama
    reverse = sort_order == "desc"
    
    def turkish_sort_key(name: str) -> str:
        replacements = [
            ('İ', 'I0'), ('I', 'I'), ('ı', 'i0'), ('i', 'i1'),
            ('Ç', 'C1'), ('ç', 'c1'), ('Ğ', 'G1'), ('ğ', 'g1'),
            ('Ö', 'O1'), ('ö', 'o1'), ('Ş', 'S1'), ('ş', 's1'),
            ('Ü', 'U1'), ('ü', 'u1'),
        ]
        result = name
        for tr_char, replacement in replacements:
            result = result.replace(tr_char, replacement)
        return result.lower()
    
    if sort_by == "name":
        referees.sort(key=lambda x: turkish_sort_key(x["name"]), reverse=reverse)
    elif sort_by == "points":
        referees.sort(key=lambda x: x["points"], reverse=reverse)
    elif sort_by == "created":
        referees.sort(key=lambda x: str(x.get("created_at", "")), reverse=reverse)
    
    return {
        "referees": referees,
        "total_count": len(referees),
        "event_title": event.get("title", "")
    }


@event_management_router.post("/{event_id}/referees/points/bulk")
async def bulk_update_referee_points(
    event_id: str,
    data: BulkRefereePointsUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Toplu hakem puan güncelleme
    """
    global db
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    user_type = current_user.get("user_type", "")
    user_id = current_user.get("id", "")
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    organizer_id = event.get("organizer_id") or event.get("creator_id")
    is_organizer = user_id == organizer_id
    is_admin = user_type in ["admin", "super_admin"]
    
    if not is_organizer and not is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    updated_count = 0
    for update in data.updates:
        result = await db.event_referee_points.update_one(
            {"event_id": event_id, "referee_id": update.referee_id},
            {
                "$set": {
                    "points": update.points,
                    "updated_at": datetime.utcnow(),
                    "updated_by": user_id
                },
                "$setOnInsert": {
                    "id": f"erp_{event_id}_{update.referee_id}",
                    "event_id": event_id,
                    "referee_id": update.referee_id,
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        if result.modified_count > 0 or result.upserted_id:
            updated_count += 1
    
    return {
        "status": "success",
        "message": f"{updated_count} hakem puanı güncellendi",
        "updated_count": updated_count
    }


@event_management_router.post("/{event_id}/referees")
async def add_referee_to_event(
    event_id: str,
    data: RefereeAdd,
    current_user: dict = Depends(get_current_user)
):
    """
    Etkinliğe yeni hakem ekle
    """
    global db
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    user_type = current_user.get("user_type", "")
    user_id = current_user.get("id", "")
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    organizer_id = event.get("organizer_id") or event.get("creator_id")
    is_organizer = user_id == organizer_id
    is_admin = user_type in ["admin", "super_admin"]
    
    if not is_organizer and not is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    user = await db.users.find_one({"id": data.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    referees = event.get("referees", [])
    if data.user_id in referees:
        raise HTTPException(status_code=400, detail="Kullanıcı zaten bu etkinliğe hakem olarak kayıtlı")
    
    referees.append(data.user_id)
    await db.events.update_one(
        {"id": event_id},
        {
            "$set": {
                "referees": referees,
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    )
    
    if data.initial_points != 0:
        await db.event_referee_points.update_one(
            {"event_id": event_id, "referee_id": data.user_id},
            {
                "$set": {
                    "points": data.initial_points,
                    "updated_at": datetime.utcnow(),
                    "updated_by": user_id
                },
                "$setOnInsert": {
                    "id": f"erp_{event_id}_{data.user_id}",
                    "event_id": event_id,
                    "referee_id": data.user_id,
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )
    
    return {
        "status": "success",
        "message": f"{user.get('full_name', 'Kullanıcı')} hakem olarak eklendi",
        "referee": {
            "id": data.user_id,
            "name": user.get("full_name") or user.get("name"),
            "points": data.initial_points
        }
    }


@event_management_router.delete("/{event_id}/referees/{referee_id}")
async def remove_referee_from_event(
    event_id: str,
    referee_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Etkinlikten hakem çıkar
    """
    global db
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    user_type = current_user.get("user_type", "")
    user_id = current_user.get("id", "")
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    organizer_id = event.get("organizer_id") or event.get("creator_id")
    is_organizer = user_id == organizer_id
    is_admin = user_type in ["admin", "super_admin"]
    
    if not is_organizer and not is_admin:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")
    
    referees = event.get("referees", [])
    if referee_id not in referees:
        raise HTTPException(status_code=400, detail="Kullanıcı bu etkinlikte hakem değil")
    
    referees.remove(referee_id)
    await db.events.update_one(
        {"id": event_id},
        {
            "$set": {
                "referees": referees,
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    )
    
    return {
        "status": "success",
        "message": "Hakem etkinlikten çıkarıldı"
    }


@event_management_router.get("/{event_id}/referees/search")
async def search_users_for_referee(
    event_id: str,
    query: str = Query(..., min_length=2, description="Arama sorgusu (en az 2 karakter)"),
    limit: int = Query(20, description="Sonuç limiti"),
    current_user: dict = None
):
    """
    Etkinliğe eklenebilecek hakemleri ara
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    existing_referees = event.get("referees", [])
    
    search_filter = {
        "$and": [
            {"id": {"$nin": existing_referees}},
            {
                "$or": [
                    {"full_name": {"$regex": query, "$options": "i"}},
                    {"name": {"$regex": query, "$options": "i"}},
                    {"phone": {"$regex": query, "$options": "i"}}
                ]
            }
        ]
    }
    
    users = await db.users.find(search_filter).limit(limit).to_list(length=limit)
    
    return {
        "users": [
            {
                "id": u["id"],
                "name": u.get("full_name") or u.get("name") or "Bilinmeyen",
                "phone": u.get("phone", ""),
                "avatar": u.get("profile_image") or u.get("profile_photo"),
                "city": u.get("city", ""),
                "gender": u.get("gender", "")
            }
            for u in users
        ],
        "total": len(users)
    }


# ================== PARTNER YÖNETİMİ ==================

@event_management_router.get("/{event_id}/participants/{user_id}/partner-info")
async def get_partner_info(
    event_id: str,
    user_id: str,
    current_user: dict = None
):
    """
    Bir oyuncunun çift ve karışık çift partner bilgilerini getir
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    event_uuid = event.get("id", event_id)
    
    # Katılımcı kaydını bul
    ep = await db.event_participants.find_one({
        "event_id": event_uuid,
        "user_id": user_id
    })
    
    if not ep:
        raise HTTPException(status_code=404, detail="Katılımcı bulunamadı")
    
    # Kullanıcı bilgilerini al
    user = await db.users.find_one({"id": user_id})
    
    # Partner bilgilerini al
    doubles_partner_id = ep.get("doubles_partner_id")
    mixed_partner_id = ep.get("mixed_partner_id")
    
    doubles_partner = None
    mixed_partner = None
    
    if doubles_partner_id:
        partner_user = await db.users.find_one({"id": doubles_partner_id})
        if partner_user:
            doubles_partner = {
                "id": partner_user["id"],
                "name": partner_user.get("full_name") or partner_user.get("name"),
                "gender": partner_user.get("gender"),
                "avatar": partner_user.get("profile_image")
            }
    
    if mixed_partner_id:
        partner_user = await db.users.find_one({"id": mixed_partner_id})
        if partner_user:
            mixed_partner = {
                "id": partner_user["id"],
                "name": partner_user.get("full_name") or partner_user.get("name"),
                "gender": partner_user.get("gender"),
                "avatar": partner_user.get("profile_image")
            }
    
    return {
        "user_id": user_id,
        "user_name": user.get("full_name") if user else "Bilinmeyen",
        "user_gender": user.get("gender") if user else None,
        "game_types": ep.get("game_types", []),
        "doubles_partner": doubles_partner,
        "mixed_partner": mixed_partner
    }


@event_management_router.get("/{event_id}/participants/{user_id}/available-partners")
async def get_available_partners(
    event_id: str,
    user_id: str,
    partner_type: str = Query(..., description="'doubles' veya 'mixed'"),
    current_user: dict = None
):
    """
    Bir oyuncu için uygun partnerleri listele
    - Çift için: Aynı cinsiyette olanlar
    - Karışık için: Farklı cinsiyette olanlar
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    event_uuid = event.get("id", event_id)
    
    # Kullanıcının cinsiyetini al
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    user_gender = user.get("gender", "").lower()
    
    # Cinsiyet filtresini belirle
    if partner_type == "doubles":
        # Çift için aynı cinsiyet
        if user_gender in ["male", "erkek", "m"]:
            gender_filter = ["male", "erkek", "m"]
        else:
            gender_filter = ["female", "kadın", "kadin", "f"]
        game_type_filter = "cift"
    else:
        # Karışık çift için farklı cinsiyet
        if user_gender in ["male", "erkek", "m"]:
            gender_filter = ["female", "kadın", "kadin", "f"]
        else:
            gender_filter = ["male", "erkek", "m"]
        game_type_filter = "karisik_cift"
    
    # Bu etkinlikteki tüm katılımcıları al (ilgili oyun türüne kayıtlı)
    eps = await db.event_participants.find({
        "event_id": event_uuid,
        "game_types": game_type_filter,
        "user_id": {"$ne": user_id}  # Kendisi hariç
    }).to_list(1000)
    
    # Kullanıcı bilgilerini al
    user_ids = [ep["user_id"] for ep in eps]
    users = await db.users.find({"id": {"$in": user_ids}}).to_list(1000)
    users_map = {u["id"]: u for u in users}
    
    available_partners = []
    for ep in eps:
        partner_user = users_map.get(ep["user_id"])
        if not partner_user:
            continue
        
        partner_gender = partner_user.get("gender", "").lower()
        
        # Cinsiyet kontrolü
        if partner_gender not in gender_filter:
            continue
        
        # Mevcut partner durumunu kontrol et
        partner_field = "doubles_partner_id" if partner_type == "doubles" else "mixed_partner_id"
        current_partner = ep.get(partner_field)
        
        available_partners.append({
            "id": partner_user["id"],
            "name": partner_user.get("full_name") or partner_user.get("name"),
            "gender": partner_gender,
            "avatar": partner_user.get("profile_image"),
            "city": partner_user.get("city"),
            "has_partner": current_partner is not None,
            "current_partner_id": current_partner
        })
    
    # İsme göre sırala
    available_partners.sort(key=lambda x: x["name"] or "")
    
    return {
        "user_id": user_id,
        "partner_type": partner_type,
        "available_partners": available_partners,
        "total": len(available_partners)
    }


@event_management_router.put("/{event_id}/participants/{user_id}/partner")
async def update_partner(
    event_id: str,
    user_id: str,
    request: PartnerUpdateRequest,
    current_user: dict = None
):
    """
    Bir oyuncunun çift veya karışık çift partnerini güncelle
    
    Kurallar:
    - Çift: Aynı cinsiyet olmalı
    - Karışık: Farklı cinsiyet olmalı
    - Yeni partner başka birinin partneri ise uyarı ver
    - force_transfer=True ise eski partnerlikten al
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    event_uuid = event.get("id", event_id)
    partner_type = request.partner_type
    new_partner_id = request.new_partner_id
    force_transfer = request.force_transfer
    
    partner_field = "doubles_partner_id" if partner_type == "doubles" else "mixed_partner_id"
    
    # Kullanıcının katılımcı kaydını bul
    user_ep = await db.event_participants.find_one({
        "event_id": event_uuid,
        "user_id": user_id
    })
    if not user_ep:
        raise HTTPException(status_code=404, detail="Katılımcı bulunamadı")
    
    # Kullanıcı bilgilerini al
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    user_gender = user.get("gender", "").lower()
    user_name = user.get("full_name") or user.get("name") or "Bilinmeyen"
    
    # Partner kaldırma işlemi
    if not new_partner_id:
        # Eski partnerin de bağlantısını kaldır
        old_partner_id = user_ep.get(partner_field)
        if old_partner_id:
            await db.event_participants.update_one(
                {"event_id": event_uuid, "user_id": old_partner_id},
                {"$set": {partner_field: None}}
            )
        
        # Kullanıcının partnerini kaldır
        await db.event_participants.update_one(
            {"event_id": event_uuid, "user_id": user_id},
            {"$set": {partner_field: None}}
        )
        
        return {
            "success": True,
            "message": f"{user_name} için {'çift' if partner_type == 'doubles' else 'karışık çift'} partneri kaldırıldı"
        }
    
    # Yeni partner bilgilerini al
    new_partner = await db.users.find_one({"id": new_partner_id})
    if not new_partner:
        raise HTTPException(status_code=404, detail="Partner bulunamadı")
    
    new_partner_gender = new_partner.get("gender", "").lower()
    new_partner_name = new_partner.get("full_name") or new_partner.get("name") or "Bilinmeyen"
    
    # Cinsiyet kontrolü
    user_is_male = user_gender in ["male", "erkek", "m"]
    partner_is_male = new_partner_gender in ["male", "erkek", "m"]
    
    if partner_type == "doubles":
        # Çift için aynı cinsiyet olmalı
        if user_is_male != partner_is_male:
            raise HTTPException(
                status_code=400,
                detail=f"Çift eşlerin cinsiyeti aynı olmalı! {user_name} ({user_gender}) ile {new_partner_name} ({new_partner_gender}) eşleştirilemez."
            )
    else:
        # Karışık çift için farklı cinsiyet olmalı
        if user_is_male == partner_is_male:
            raise HTTPException(
                status_code=400,
                detail=f"Karışık çift eşlerin cinsiyeti farklı olmalı! {user_name} ({user_gender}) ile {new_partner_name} ({new_partner_gender}) eşleştirilemez."
            )
    
    # Yeni partnerin katılımcı kaydını bul
    new_partner_ep = await db.event_participants.find_one({
        "event_id": event_uuid,
        "user_id": new_partner_id
    })
    if not new_partner_ep:
        raise HTTPException(status_code=404, detail="Yeni partner bu etkinliğe kayıtlı değil")
    
    # Yeni partnerin mevcut partner durumunu kontrol et
    existing_partner_of_new = new_partner_ep.get(partner_field)
    
    if existing_partner_of_new and existing_partner_of_new != user_id:
        # Yeni partnerin başka bir partneri var
        existing_partner_user = await db.users.find_one({"id": existing_partner_of_new})
        existing_partner_name = (existing_partner_user.get("full_name") or existing_partner_user.get("name")) if existing_partner_user else "Bilinmeyen"
        
        if not force_transfer:
            # Uyarı ver, transfer onayı iste
            return {
                "success": False,
                "conflict": True,
                "message": f"{new_partner_name} şu anda {existing_partner_name} ile {'çift' if partner_type == 'doubles' else 'karışık çift'} partneri. Transfer etmek için onay gerekli.",
                "conflict_details": {
                    "new_partner_id": new_partner_id,
                    "new_partner_name": new_partner_name,
                    "existing_partner_id": existing_partner_of_new,
                    "existing_partner_name": existing_partner_name,
                    "partner_type": partner_type
                }
            }
        else:
            # Transfer onaylandı - eski partnerin bağlantısını kaldır
            await db.event_participants.update_one(
                {"event_id": event_uuid, "user_id": existing_partner_of_new},
                {"$set": {partner_field: None}}
            )
    
    # Kullanıcının eski partnerinin bağlantısını kaldır
    old_partner_id = user_ep.get(partner_field)
    if old_partner_id and old_partner_id != new_partner_id:
        await db.event_participants.update_one(
            {"event_id": event_uuid, "user_id": old_partner_id},
            {"$set": {partner_field: None}}
        )
    
    # Yeni partnerin eski partnerinin bağlantısını kaldır (eğer varsa ve kullanıcı değilse)
    if existing_partner_of_new and existing_partner_of_new != user_id:
        await db.event_participants.update_one(
            {"event_id": event_uuid, "user_id": existing_partner_of_new},
            {"$set": {partner_field: None}}
        )
    
    # İki yönlü eşleştirme yap
    await db.event_participants.update_one(
        {"event_id": event_uuid, "user_id": user_id},
        {"$set": {partner_field: new_partner_id}}
    )
    await db.event_participants.update_one(
        {"event_id": event_uuid, "user_id": new_partner_id},
        {"$set": {partner_field: user_id}}
    )
    
    transfer_note = ""
    if existing_partner_of_new and existing_partner_of_new != user_id:
        existing_partner_user = await db.users.find_one({"id": existing_partner_of_new})
        existing_partner_name = (existing_partner_user.get("full_name") or existing_partner_user.get("name")) if existing_partner_user else "Bilinmeyen"
        transfer_note = f" ({new_partner_name}, {existing_partner_name} ile olan partnerliğinden transfer edildi)"
    
    return {
        "success": True,
        "message": f"{user_name} ile {new_partner_name} {'çift' if partner_type == 'doubles' else 'karışık çift'} olarak eşleştirildi{transfer_note}",
        "partnership": {
            "user_id": user_id,
            "user_name": user_name,
            "partner_id": new_partner_id,
            "partner_name": new_partner_name,
            "partner_type": partner_type
        }
    }


@event_management_router.get("/{event_id}/participants/search-for-partner")
async def search_participants_for_partner(
    event_id: str,
    query: str = Query(..., min_length=1, description="Arama sorgusu"),
    partner_type: str = Query(..., description="'doubles' veya 'mixed'"),
    user_id: str = Query(..., description="Partner arayan kullanıcının ID'si"),
    current_user: dict = None
):
    """
    Partner aramak için katılımcılarda isim araması yap
    """
    global db
    
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    event_uuid = event.get("id", event_id)
    
    # Kullanıcının cinsiyetini al
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    user_gender = user.get("gender", "").lower()
    user_is_male = user_gender in ["male", "erkek", "m"]
    
    # Uygun cinsiyet filtresini belirle
    if partner_type == "doubles":
        if user_is_male:
            gender_values = ["male", "erkek", "m"]
        else:
            gender_values = ["female", "kadın", "kadin", "f"]
    else:
        if user_is_male:
            gender_values = ["female", "kadın", "kadin", "f"]
        else:
            gender_values = ["male", "erkek", "m"]
    
    # İsim araması yap
    users = await db.users.find({
        "$or": [
            {"full_name": {"$regex": query, "$options": "i"}},
            {"name": {"$regex": query, "$options": "i"}}
        ],
        "gender": {"$in": gender_values},
        "id": {"$ne": user_id}
    }).limit(20).to_list(20)
    
    user_ids = [u["id"] for u in users]
    
    # Bu etkinliğe kayıtlı olanları filtrele
    eps = await db.event_participants.find({
        "event_id": event_uuid,
        "user_id": {"$in": user_ids}
    }).to_list(1000)
    
    registered_ids = {ep["user_id"] for ep in eps}
    ep_map = {ep["user_id"]: ep for ep in eps}
    
    partner_field = "doubles_partner_id" if partner_type == "doubles" else "mixed_partner_id"
    
    results = []
    for u in users:
        if u["id"] not in registered_ids:
            continue
        
        ep = ep_map.get(u["id"], {})
        current_partner_id = ep.get(partner_field)
        
        current_partner_name = None
        if current_partner_id:
            partner_user = await db.users.find_one({"id": current_partner_id})
            current_partner_name = (partner_user.get("full_name") or partner_user.get("name")) if partner_user else None
        
        results.append({
            "id": u["id"],
            "name": u.get("full_name") or u.get("name"),
            "gender": u.get("gender"),
            "avatar": u.get("profile_image"),
            "city": u.get("city"),
            "has_partner": current_partner_id is not None,
            "current_partner_id": current_partner_id,
            "current_partner_name": current_partner_name
        })
    
    return {
        "results": results,
        "total": len(results)
    }


# ================== İSVİÇRE SİSTEMİ (SWISS SYSTEM - DUTCH FIDE) ==================

def dutch_fide_pairing(participants: List[Dict], round_num: int, previous_opponents: Dict[str, set]) -> List[Dict]:
    """
    Dutch FIDE İsviçre Sistemi Eşleştirmesi
    
    Kurallar:
    1. Oyuncular puana göre gruplandırılır (score groups)
    2. Her grup içinde üst yarı alt yarı ile eşleştirilir
    3. Daha önce karşılaşmış oyuncular eşleştirilmez
    4. Tek oyuncu kalırsa BYE alır (en düşük sıralı)
    
    Args:
        participants: Liste - her biri {id, name, points, rating, opponents} içerir
        round_num: Mevcut tur numarası
        previous_opponents: Dict - {player_id: set(opponent_ids)}
    
    Returns:
        List[Dict] - Eşleştirmeler [{p1_id, p1_name, p2_id, p2_name, is_bye}]
    """
    if not participants:
        return []
    
    # Oyuncuları puan > rating > isim sırasına göre sırala
    sorted_players = sorted(
        participants, 
        key=lambda x: (-x.get("points", 0), -x.get("rating", 0), x.get("name", ""))
    )
    
    # Puana göre grupla
    score_groups = {}
    for p in sorted_players:
        score = p.get("points", 0)
        if score not in score_groups:
            score_groups[score] = []
        score_groups[score].append(p)
    
    pairings = []
    paired_ids = set()
    
    # Her puan grubunu işle (yüksekten düşüğe)
    remaining_players = []
    for score in sorted(score_groups.keys(), reverse=True):
        group = score_groups[score] + remaining_players
        remaining_players = []
        
        # Tek sayıda oyuncu varsa, sondan birini sonraki gruba aktar
        if len(group) % 2 == 1:
            # En düşük sıralı ve BYE almamış oyuncuyu bul
            for i in range(len(group) - 1, -1, -1):
                player = group[i]
                player_opponents = previous_opponents.get(player["id"], set())
                if "BYE" not in player_opponents:
                    remaining_players.append(group.pop(i))
                    break
            else:
                # Herkes BYE almışsa, yine de sonuncuyu aktar
                if group:
                    remaining_players.append(group.pop())
        
        if not group:
            continue
        
        # Üst yarı ve alt yarı
        mid = len(group) // 2
        upper_half = group[:mid]
        lower_half = group[mid:]
        
        # Eşleştir: 1 vs n, 2 vs n-1, ...
        for i, p1 in enumerate(upper_half):
            if p1["id"] in paired_ids:
                continue
            
            # Alt yarıdan uygun rakip bul
            best_opponent = None
            best_opponent_idx = -1
            
            for j, p2 in enumerate(lower_half):
                if p2["id"] in paired_ids:
                    continue
                
                p1_opponents = previous_opponents.get(p1["id"], set())
                
                # Daha önce karşılaşmadılarsa
                if p2["id"] not in p1_opponents:
                    best_opponent = p2
                    best_opponent_idx = j
                    break
            
            # Eğer uygun rakip bulunamadıysa, herhangi birini al
            if best_opponent is None:
                for j, p2 in enumerate(lower_half):
                    if p2["id"] not in paired_ids:
                        best_opponent = p2
                        best_opponent_idx = j
                        break
            
            if best_opponent:
                pairings.append({
                    "participant1_id": p1["id"],
                    "participant1_name": p1.get("name", "Oyuncu"),
                    "participant2_id": best_opponent["id"],
                    "participant2_name": best_opponent.get("name", "Oyuncu"),
                    "is_bye": False,
                    "score_diff": abs(p1.get("points", 0) - best_opponent.get("points", 0))
                })
                paired_ids.add(p1["id"])
                paired_ids.add(best_opponent["id"])
    
    # Kalan oyuncular (tek sayı durumunda BYE)
    for player in remaining_players:
        if player["id"] not in paired_ids:
            pairings.append({
                "participant1_id": player["id"],
                "participant1_name": player.get("name", "Oyuncu"),
                "participant2_id": "BYE",
                "participant2_name": "BYE",
                "is_bye": True,
                "score_diff": 0
            })
            paired_ids.add(player["id"])
    
    return pairings


@event_management_router.post("/{event_id}/swiss/create-group")
async def create_swiss_group(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    İsviçre sistemi için tek grup oluştur
    Tüm katılımcıları tek bir gruba ekler
    """
    global db
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    user_id = current_user.get("id", "")
    
    # Etkinliği bul
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # Katılımcıları al
    participant_ids = event.get("participants", [])
    if not participant_ids:
        raise HTTPException(status_code=400, detail="Etkinlikte katılımcı bulunmuyor")
    
    # Mevcut İsviçre grubunu kontrol et
    existing_group = await db.event_groups.find_one({
        "event_id": event_id,
        "tournament_type": "swiss"
    })
    
    if existing_group:
        raise HTTPException(status_code=400, detail="İsviçre grubu zaten mevcut")
    
    # Katılımcı detaylarını al
    participant_details = []
    for pid in participant_ids:
        user = await db.users.find_one({"id": pid})
        if user:
            participant_details.append({
                "id": pid,
                "name": user.get("full_name") or user.get("name", "Bilinmeyen"),
                "rating": user.get("rating", 1500),
                "points": 0,
                "opponents": [],
                "matches_played": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "buchholz": 0,  # Tie-break puanı
                "sonneborn_berger": 0  # Tie-break puanı
            })
    
    # Grup oluştur
    group_id = str(uuid.uuid4())
    swiss_group = {
        "id": group_id,
        "event_id": event_id,
        "name": "İsviçre Sistemi",
        "tournament_type": "swiss",
        "group_type": "swiss",
        "participant_ids": participant_ids,
        "participant_details": participant_details,
        "current_round": 0,
        "total_rounds": math.ceil(math.log2(len(participant_ids))) + 1,  # Önerilen tur sayısı
        "status": "active",
        "created_at": datetime.utcnow(),
        "created_by": user_id
    }
    
    await db.event_groups.insert_one(swiss_group)
    
    # Standings kayıtlarını oluştur
    for pd in participant_details:
        standing = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "group_id": group_id,
            "participant_id": pd["id"],
            "participant_name": pd["name"],
            "points": 0,
            "matches_played": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "sets_won": 0,
            "sets_lost": 0,
            "games_won": 0,
            "games_lost": 0,
            "buchholz": 0,
            "sonneborn_berger": 0,
            "rating": pd.get("rating", 1500),
            "created_at": datetime.utcnow()
        }
        await db.event_standings.insert_one(standing)
    
    logger.info(f"🇨🇭 İsviçre grubu oluşturuldu: {len(participant_ids)} katılımcı")
    
    return {
        "status": "success",
        "message": f"İsviçre sistemi grubu oluşturuldu ({len(participant_ids)} katılımcı)",
        "group_id": group_id,
        "participant_count": len(participant_ids),
        "recommended_rounds": swiss_group["total_rounds"]
    }


@event_management_router.post("/{event_id}/swiss/generate-round")
async def generate_swiss_round(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    İsviçre sistemi için yeni tur maçları oluştur
    Dutch FIDE eşleştirme kurallarını kullanır
    """
    global db
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    user_id = current_user.get("id", "")
    
    # Etkinliği bul
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    # İsviçre grubunu bul
    swiss_group = await db.event_groups.find_one({
        "event_id": event_id,
        "tournament_type": "swiss"
    })
    
    if not swiss_group:
        raise HTTPException(status_code=404, detail="İsviçre grubu bulunamadı. Önce grup oluşturun.")
    
    current_round = swiss_group.get("current_round", 0)
    new_round = current_round + 1
    
    # Önceki tur maçlarının tamamlanıp tamamlanmadığını kontrol et
    if current_round > 0:
        incomplete_matches = await db.event_matches.count_documents({
            "event_id": event_id,
            "group_id": swiss_group["id"],
            "round_number": current_round,
            "status": {"$ne": "completed"}
        })
        
        if incomplete_matches > 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Tur {current_round}'deki {incomplete_matches} maç henüz tamamlanmadı"
            )
    
    # Standings'ten güncel puanları al
    standings = await db.event_standings.find({
        "event_id": event_id,
        "group_id": swiss_group["id"]
    }).to_list(1000)
    
    # Önceki rakipleri bul
    previous_opponents = {}
    previous_matches = await db.event_matches.find({
        "event_id": event_id,
        "group_id": swiss_group["id"],
        "is_bye": {"$ne": True}
    }).to_list(1000)
    
    for match in previous_matches:
        p1_id = match.get("participant1_id")
        p2_id = match.get("participant2_id")
        
        if p1_id and p2_id:
            if p1_id not in previous_opponents:
                previous_opponents[p1_id] = set()
            if p2_id not in previous_opponents:
                previous_opponents[p2_id] = set()
            
            previous_opponents[p1_id].add(p2_id)
            previous_opponents[p2_id].add(p1_id)
    
    # BYE almış oyuncuları işaretle
    bye_matches = await db.event_matches.find({
        "event_id": event_id,
        "group_id": swiss_group["id"],
        "is_bye": True
    }).to_list(1000)
    
    for match in bye_matches:
        p1_id = match.get("participant1_id")
        if p1_id:
            if p1_id not in previous_opponents:
                previous_opponents[p1_id] = set()
            previous_opponents[p1_id].add("BYE")
    
    # Katılımcı listesini hazırla
    participants = []
    for s in standings:
        participants.append({
            "id": s.get("participant_id"),
            "name": s.get("participant_name", "Bilinmeyen"),
            "points": s.get("points", 0),
            "rating": s.get("rating", 1500),
            "buchholz": s.get("buchholz", 0)
        })
    
    # Dutch FIDE eşleştirmesi yap
    pairings = dutch_fide_pairing(participants, new_round, previous_opponents)
    
    if not pairings:
        raise HTTPException(status_code=400, detail="Eşleştirme yapılamadı")
    
    # Turnuva ayarlarını al - hakem ataması için
    tournament_settings = event.get("tournament_settings", {})
    in_group_refereeing = tournament_settings.get("in_group_refereeing", False)
    
    # Hakem havuzu oluştur (puanı en düşük olanlar)
    referee_pool = []
    if in_group_refereeing:
        sorted_by_points = sorted(participants, key=lambda x: (x.get("points", 0), x.get("rating", 0)))
        referee_pool = [p for p in sorted_by_points]
    
    # Maçları oluştur
    matches_created = []
    match_number = 1
    referee_index = 0
    
    for pairing in pairings:
        match_id = str(uuid.uuid4())
        
        is_bye = pairing.get("is_bye", False)
        
        match = {
            "id": match_id,
            "event_id": event_id,
            "group_id": swiss_group["id"],
            "group_name": "İsviçre Sistemi",
            "round_number": new_round,
            "round_name": f"Tur {new_round}",
            "match_number": match_number,
            "participant1_id": pairing["participant1_id"],
            "participant1_name": pairing["participant1_name"],
            "participant2_id": pairing["participant2_id"] if not is_bye else None,
            "participant2_name": pairing["participant2_name"] if not is_bye else "BYE",
            "status": "completed" if is_bye else "scheduled",
            "is_bye": is_bye,
            "stage": "swiss",
            "tournament_type": "swiss",
            "score_diff": pairing.get("score_diff", 0),
            "created_at": datetime.utcnow()
        }
        
        # BYE maçı için otomatik sonuç
        if is_bye:
            match["winner_id"] = pairing["participant1_id"]
            match["score"] = "1-0"
            match["result_entered_at"] = datetime.utcnow()
        
        # Hakem ataması (BYE olmayan maçlar için)
        if in_group_refereeing and not is_bye and referee_pool:
            # Maça katılmayan, en düşük puanlı oyuncuyu hakem yap
            match_participant_ids = {pairing["participant1_id"], pairing["participant2_id"]}
            
            for ref in referee_pool:
                if ref["id"] not in match_participant_ids:
                    match["referee_id"] = ref["id"]
                    match["referee_name"] = ref["name"]
                    match["referee_is_player"] = True
                    referee_pool.remove(ref)
                    logger.info(f"⚖️ Hakem atandı: {ref['name']} -> Maç {match_number}")
                    break
        
        await db.event_matches.insert_one(match)
        matches_created.append(match)
        match_number += 1
        
        # BYE için standings güncelle
        if is_bye:
            await db.event_standings.update_one(
                {"event_id": event_id, "group_id": swiss_group["id"], "participant_id": pairing["participant1_id"]},
                {
                    "$inc": {
                        "points": 1,  # BYE = 1 puan (galibiyete eşdeğer)
                        "matches_played": 1,
                        "wins": 1
                    }
                }
            )
    
    # Grup tur numarasını güncelle
    await db.event_groups.update_one(
        {"id": swiss_group["id"]},
        {"$set": {"current_round": new_round, "updated_at": datetime.utcnow()}}
    )
    
    logger.info(f"🇨🇭 İsviçre Tur {new_round}: {len(matches_created)} maç oluşturuldu")
    
    return {
        "status": "success",
        "message": f"Tur {new_round} maçları oluşturuldu",
        "round_number": new_round,
        "matches_count": len(matches_created),
        "matches": [{
            "id": m["id"],
            "participant1_name": m["participant1_name"],
            "participant2_name": m["participant2_name"],
            "is_bye": m.get("is_bye", False),
            "referee_name": m.get("referee_name")
        } for m in matches_created]
    }


@event_management_router.post("/{event_id}/swiss/update-standings")
async def update_swiss_standings(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    İsviçre sistemi puanlarını ve tie-break hesaplamalarını güncelle
    Buchholz ve Sonneborn-Berger hesaplamaları yapar
    """
    global db
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    # İsviçre grubunu bul
    swiss_group = await db.event_groups.find_one({
        "event_id": event_id,
        "tournament_type": "swiss"
    })
    
    if not swiss_group:
        raise HTTPException(status_code=404, detail="İsviçre grubu bulunamadı")
    
    # Tüm standings kayıtlarını al
    standings = await db.event_standings.find({
        "event_id": event_id,
        "group_id": swiss_group["id"]
    }).to_list(1000)
    
    # Puanları dict olarak tut
    points_dict = {s["participant_id"]: s.get("points", 0) for s in standings}
    
    # Tüm maçları al
    matches = await db.event_matches.find({
        "event_id": event_id,
        "group_id": swiss_group["id"],
        "status": "completed"
    }).to_list(1000)
    
    # Her oyuncu için rakip listesini ve sonuçları hesapla
    opponent_results = {}  # {player_id: [(opponent_id, result)]} result: 1=win, 0.5=draw, 0=loss
    
    for match in matches:
        if match.get("is_bye"):
            continue
        
        p1_id = match.get("participant1_id")
        p2_id = match.get("participant2_id")
        winner_id = match.get("winner_id")
        
        if not p1_id or not p2_id:
            continue
        
        if p1_id not in opponent_results:
            opponent_results[p1_id] = []
        if p2_id not in opponent_results:
            opponent_results[p2_id] = []
        
        if winner_id == p1_id:
            opponent_results[p1_id].append((p2_id, 1))
            opponent_results[p2_id].append((p1_id, 0))
        elif winner_id == p2_id:
            opponent_results[p1_id].append((p2_id, 0))
            opponent_results[p2_id].append((p1_id, 1))
        else:
            # Beraberlik
            opponent_results[p1_id].append((p2_id, 0.5))
            opponent_results[p2_id].append((p1_id, 0.5))
    
    # Buchholz ve Sonneborn-Berger hesapla
    for standing in standings:
        pid = standing["participant_id"]
        
        # Buchholz: Rakiplerin toplam puanı
        buchholz = 0
        results = opponent_results.get(pid, [])
        for opp_id, result in results:
            buchholz += points_dict.get(opp_id, 0)
        
        # Sonneborn-Berger: Yenilen rakiplerin puanı + (berabere kalınan rakiplerin puanı / 2)
        sonneborn_berger = 0
        for opp_id, result in results:
            opp_points = points_dict.get(opp_id, 0)
            if result == 1:
                sonneborn_berger += opp_points
            elif result == 0.5:
                sonneborn_berger += opp_points / 2
        
        # Güncelle
        await db.event_standings.update_one(
            {"id": standing["id"]},
            {
                "$set": {
                    "buchholz": round(buchholz, 2),
                    "sonneborn_berger": round(sonneborn_berger, 2),
                    "updated_at": datetime.utcnow()
                }
            }
        )
    
    logger.info(f"🇨🇭 İsviçre standings güncellendi: {len(standings)} oyuncu")
    
    return {
        "status": "success",
        "message": f"{len(standings)} oyuncunun puanları güncellendi"
    }


# ================== ÇİFT ELİMİNASYON (DOUBLE ELIMINATION) ==================

def create_double_elimination_bracket(participants: List[Dict], participant_names: Dict[str, str]) -> Dict:
    """
    Çift Eleme Bracket Yapısı Oluştur
    
    Kurallar:
    1. Winners Bracket (Kazananlar): Yenilmemiş oyuncular
    2. Losers Bracket (Kaybedenler): 1 kez yenilmiş oyuncular
    3. 2 kez yenilen elenir
    4. Grand Final: Winners şampiyonu vs Losers şampiyonu
       - Losers şampiyonu 2 maç kazanmalı (çünkü Winners şampiyonu henüz yenilmemiş)
    
    Args:
        participants: Liste - [{id, name, seed}]
        participant_names: Dict - {id: name}
    
    Returns:
        Dict - {winners_bracket: [], losers_bracket: [], grand_final: {}}
    """
    import math
    
    n = len(participants)
    if n < 2:
        return {"winners_bracket": [], "losers_bracket": [], "grand_final": None}
    
    # Bracket boyutunu 2'nin kuvveti olarak belirle
    bracket_size = 2 ** math.ceil(math.log2(n))
    bye_count = bracket_size - n
    
    # Seed'e göre sırala
    sorted_participants = sorted(participants, key=lambda x: x.get("seed", 999))
    
    # Positioned array - BYE'lar için None
    positioned = [None] * bracket_size
    
    # Standard seeding: 1 vs n, 2 vs n-1, etc.
    seed_positions = []
    def generate_seed_positions(size, offset=0):
        if size == 1:
            return [offset]
        half = size // 2
        top = generate_seed_positions(half, offset)
        bottom = generate_seed_positions(half, offset + half)
        result = []
        for i in range(half):
            result.append(top[i])
            result.append(bottom[half - 1 - i])
        return result
    
    seed_positions = generate_seed_positions(bracket_size)
    
    # Oyuncuları yerleştir
    for i, p in enumerate(sorted_participants):
        if i < len(seed_positions):
            positioned[seed_positions[i]] = p
    
    # Winners Bracket turlarını oluştur
    winners_rounds = []
    current_round_players = positioned.copy()
    round_num = 1
    total_rounds = int(math.log2(bracket_size))
    
    while len(current_round_players) > 1:
        round_matches = []
        next_round_players = []
        
        for i in range(0, len(current_round_players), 2):
            p1 = current_round_players[i]
            p2 = current_round_players[i + 1] if i + 1 < len(current_round_players) else None
            
            if p1 is None and p2 is None:
                next_round_players.append(None)
            elif p1 is None:
                # P1 BYE - P2 direkt geçer
                next_round_players.append(p2)
            elif p2 is None:
                # P2 BYE - P1 direkt geçer
                next_round_players.append(p1)
            else:
                # Normal maç
                match = {
                    "round": round_num,
                    "match_index": len(round_matches),
                    "participant1_id": p1["id"],
                    "participant1_name": participant_names.get(p1["id"], "?"),
                    "participant1_seed": p1.get("seed"),
                    "participant2_id": p2["id"],
                    "participant2_name": participant_names.get(p2["id"], "?"),
                    "participant2_seed": p2.get("seed"),
                    "bracket_type": "winners",
                    "is_bye": False
                }
                round_matches.append(match)
                next_round_players.append(None)  # TBD - kazanan gelecek
        
        if round_matches:
            winners_rounds.append({
                "round_number": round_num,
                "round_name": get_round_name(bracket_size, round_num),
                "matches": round_matches
            })
        
        current_round_players = next_round_players
        round_num += 1
    
    # Losers Bracket yapısı - Winners'tan düşenler için
    # Losers bracket'ta 2x-1 tur var (x = winners tur sayısı)
    losers_rounds = []
    losers_round_count = (total_rounds - 1) * 2
    
    for lr in range(1, losers_round_count + 1):
        losers_rounds.append({
            "round_number": lr,
            "round_name": f"Kaybedenler Tur {lr}",
            "matches": []  # Dinamik olarak doldurulacak
        })
    
    # Grand Final
    grand_final = {
        "match_1": {
            "description": "Winners Şampiyonu vs Losers Şampiyonu",
            "participant1_name": "Winners Şampiyonu",
            "participant2_name": "Losers Şampiyonu"
        },
        "match_2": {
            "description": "Reset Maçı (Losers şampiyonu kazanırsa)",
            "participant1_name": "TBD",
            "participant2_name": "TBD",
            "conditional": True
        }
    }
    
    return {
        "winners_bracket": winners_rounds,
        "losers_bracket": losers_rounds,
        "grand_final": grand_final,
        "bracket_size": bracket_size,
        "bye_count": bye_count,
        "total_participants": n
    }


@event_management_router.post("/{event_id}/double-elimination/create")
async def create_double_elimination_tournament(
    event_id: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Çift Eleme turnuvası oluştur
    
    data:
        - source: "groups" (grup sonrası) veya "direct" (direkt katılımcılardan)
        - final_stage_size: 4, 8, 16, 32 (son kaç oyuncu)
        - category: kategori adı (opsiyonel)
    """
    global db
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    user_id = current_user.get("id", "")
    
    # Etkinliği bul
    event = await find_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
    
    source = data.get("source", "groups")
    final_stage_size = data.get("final_stage_size", 8)  # 4, 8, 16, 32, 64 veya "all"
    category = data.get("category")
    
    # "all" ise tüm katılımcıları al
    use_all_participants = final_stage_size == "all" or final_stage_size == 0
    if use_all_participants:
        final_stage_size = 9999  # Çok büyük bir sayı - tüm katılımcılar alınacak
    
    participants = []
    participant_names = {}
    
    if source == "groups":
        # Grup aşamasından en iyi oyuncuları al
        query = {"event_id": event_id, "group_type": {"$ne": "elimination"}}
        if category:
            query["category"] = {"$regex": category, "$options": "i"}
        
        groups = await db.event_groups.find(query).to_list(100)
        
        all_standings = []
        
        if groups:
            # Gruplar varsa, her gruptan standings'e göre sırala
            for group in groups:
                standings = await db.event_standings.find({
                    "event_id": event_id,
                    "group_id": group["id"]
                }).sort([("points", -1), ("sets_won", -1)]).to_list(100)
                
                for i, s in enumerate(standings):
                    all_standings.append({
                        "id": s["participant_id"],
                        "name": s.get("participant_name", "Bilinmeyen"),
                        "points": s.get("points", 0),
                        "group_position": i + 1,
                        "group_id": group["id"],
                        "group_name": group.get("name", "")
                    })
        else:
            # Gruplar yoksa, direkt event_standings koleksiyonundan al
            logger.info(f"⚠️ Çift eleme: Grup bulunamadı, event_standings'den direkt çekiliyor")
            standings = await db.event_standings.find({
                "event_id": event_id
            }).sort([("points", -1), ("sets_won", -1), ("sets_average", -1)]).to_list(200)
            
            if standings:
                for i, s in enumerate(standings):
                    all_standings.append({
                        "id": s.get("participant_id"),
                        "name": s.get("participant_name", "Bilinmeyen"),
                        "points": s.get("points", 0),
                        "group_position": i + 1,
                        "group_id": s.get("group_id", ""),
                        "group_name": s.get("group_name", "")
                    })
            else:
                # Standings da yoksa, event'in participants listesinden al
                logger.info(f"⚠️ Çift eleme: Standings da bulunamadı, participants listesinden çekiliyor")
                participant_ids = event.get("participants", [])
                for i, pid in enumerate(participant_ids):
                    # pid dict olabilir
                    if isinstance(pid, dict):
                        pid = pid.get("id", str(pid))
                    
                    user = await db.users.find_one({"id": pid})
                    if user:
                        all_standings.append({
                            "id": pid,
                            "name": user.get("full_name", "Bilinmeyen"),
                            "points": 0,
                            "group_position": i + 1,
                            "group_id": "",
                            "group_name": ""
                        })
        
        # Puana göre sırala ve en iyi X oyuncuyu al
        all_standings.sort(key=lambda x: (-x["points"], x["group_position"]))
        participants = all_standings[:final_stage_size]
        
        logger.info(f"✅ Çift eleme: {len(participants)} katılımcı bulundu (kaynak: {'gruplar' if groups else 'standings/participants'})")
        
    else:
        # Direkt katılımcılardan
        participant_ids = event.get("participants", [])[:final_stage_size]
        
        for i, pid in enumerate(participant_ids):
            # pid dict olabilir
            if isinstance(pid, dict):
                pid = pid.get("id", str(pid))
            
            user = await db.users.find_one({"id": pid})
            if user:
                participants.append({
                    "id": pid,
                    "name": user.get("full_name", "Bilinmeyen"),
                    "seed": i + 1
                })
    
    if len(participants) < 2:
        raise HTTPException(status_code=400, detail="En az 2 katılımcı gerekli")
    
    # participant_names sözlüğünü ÖNCE doldur
    for p in participants:
        participant_names[p["id"]] = p.get("name", "Bilinmeyen")
    
    # Seed'leri ata
    for i, p in enumerate(participants):
        p["seed"] = i + 1
    
    # Mevcut çift eleme bracket'ı kontrol et
    existing = await db.event_groups.find_one({
        "event_id": event_id,
        "tournament_type": "double_elimination"
    })
    
    if existing:
        raise HTTPException(status_code=400, detail="Çift eleme bracket'ı zaten mevcut. Önce silin.")
    
    # Bracket yapısını oluştur
    bracket_structure = create_double_elimination_bracket(participants, participant_names)
    
    # Grup oluştur
    group_id = str(uuid.uuid4())
    de_group = {
        "id": group_id,
        "event_id": event_id,
        "name": f"Çift Eleme{' - ' + category if category else ''}",
        "tournament_type": "double_elimination",
        "group_type": "elimination",
        "category": category,
        "source": source,
        "final_stage_size": final_stage_size,
        "participant_ids": [p["id"] for p in participants],
        "participant_details": participants,
        "bracket_structure": bracket_structure,
        "status": "active",
        "created_at": datetime.utcnow(),
        "created_by": user_id
    }
    
    await db.event_groups.insert_one(de_group)
    
    # Winners Bracket maçlarını oluştur (ilk tur)
    matches_created = []
    match_number = 1
    
    for round_data in bracket_structure["winners_bracket"]:
        if round_data["round_number"] == 1:  # Sadece ilk tur maçlarını oluştur
            for match_data in round_data["matches"]:
                match_id = str(uuid.uuid4())
                match = {
                    "id": match_id,
                    "event_id": event_id,
                    "group_id": group_id,
                    "group_name": "Çift Eleme - Kazananlar",
                    "category": category,
                    "round_number": 1,
                    "round_name": round_data["round_name"],
                    "match_number": match_number,
                    "bracket_match_index": match_data["match_index"],
                    "participant1_id": match_data["participant1_id"],
                    "participant1_name": match_data["participant1_name"],
                    "participant1_seed": match_data["participant1_seed"],
                    "participant2_id": match_data["participant2_id"],
                    "participant2_name": match_data["participant2_name"],
                    "participant2_seed": match_data["participant2_seed"],
                    "status": "scheduled",
                    "bracket_type": "winners",
                    "bracket_position": "winners",
                    "stage": "double_elimination",
                    "tournament_type": "double_elimination",
                    "is_bye": False,
                    "losses_p1": 0,
                    "losses_p2": 0,
                    "created_at": datetime.utcnow()
                }
                
                await db.event_matches.insert_one(match)
                matches_created.append(match)
                match_number += 1
    
    logger.info(f"🏆🏆 Çift Eleme turnuvası oluşturuldu: {len(participants)} katılımcı, {len(matches_created)} maç")
    
    return {
        "status": "success",
        "message": f"Çift eleme turnuvası oluşturuldu ({len(participants)} katılımcı)",
        "group_id": group_id,
        "participant_count": len(participants),
        "matches_count": len(matches_created),
        "bracket_size": bracket_structure["bracket_size"],
        "bye_count": bracket_structure["bye_count"]
    }


@event_management_router.post("/{event_id}/double-elimination/advance-winner")
async def advance_double_elimination_winner(
    event_id: str,
    match_id: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """
    Çift eleme maç sonucu sonrası kazananı ilerlet, kaybedeni losers bracket'a düşür
    """
    global db
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    # Maçı bul
    match = await db.event_matches.find_one({"id": match_id})
    if not match:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    
    if match.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Maç henüz tamamlanmadı")
    
    winner_id = match.get("winner_id")
    if not winner_id:
        raise HTTPException(status_code=400, detail="Kazanan belirlenmemiş")
    
    # Kaybedeni bul
    loser_id = match.get("participant1_id") if winner_id == match.get("participant2_id") else match.get("participant2_id")
    loser_name = match.get("participant1_name") if winner_id == match.get("participant2_id") else match.get("participant2_name")
    winner_name = match.get("participant1_name") if winner_id == match.get("participant1_id") else match.get("participant2_name")
    
    bracket_type = match.get("bracket_type", "winners")
    round_number = match.get("round_number", 1)
    match_index = match.get("bracket_match_index", 0)
    group_id = match.get("group_id")
    category = match.get("category")
    
    # Çift eleme grubunu bul
    de_group = await db.event_groups.find_one({
        "id": group_id,
        "tournament_type": "double_elimination"
    })
    
    if not de_group:
        raise HTTPException(status_code=404, detail="Çift eleme grubu bulunamadı")
    
    created_matches = []
    
    if bracket_type == "winners":
        # Winners bracket'tan kaybeden -> Losers bracket'a düşer
        # Losers bracket maçı oluştur veya mevcut maça ekle
        losers_round = round_number  # Winners R1 kaybedenleri -> Losers R1
        
        # Mevcut losers maçını kontrol et veya yeni oluştur
        existing_losers_match = await db.event_matches.find_one({
            "event_id": event_id,
            "group_id": group_id,
            "bracket_type": "losers",
            "round_number": losers_round,
            "bracket_match_index": match_index // 2,
            "status": "scheduled"
        })
        
        if existing_losers_match:
            # Mevcut maça ekle
            if not existing_losers_match.get("participant1_id"):
                await db.event_matches.update_one(
                    {"id": existing_losers_match["id"]},
                    {"$set": {
                        "participant1_id": loser_id,
                        "participant1_name": loser_name,
                        "losses_p1": 1
                    }}
                )
            else:
                await db.event_matches.update_one(
                    {"id": existing_losers_match["id"]},
                    {"$set": {
                        "participant2_id": loser_id,
                        "participant2_name": loser_name,
                        "losses_p2": 1
                    }}
                )
        else:
            # Yeni losers maçı oluştur
            losers_match_id = str(uuid.uuid4())
            losers_match = {
                "id": losers_match_id,
                "event_id": event_id,
                "group_id": group_id,
                "group_name": "Çift Eleme - Kaybedenler",
                "category": category,
                "round_number": losers_round,
                "round_name": f"Kaybedenler Tur {losers_round}",
                "bracket_match_index": match_index // 2,
                "participant1_id": loser_id,
                "participant1_name": loser_name,
                "losses_p1": 1,
                "status": "pending",
                "bracket_type": "losers",
                "bracket_position": "losers",
                "stage": "double_elimination",
                "tournament_type": "double_elimination",
                "created_at": datetime.utcnow()
            }
            await db.event_matches.insert_one(losers_match)
            created_matches.append(losers_match)
        
        # Winners bracket'ta kazananı bir sonraki tura ilerlet
        next_winners_round = round_number + 1
        next_match_index = match_index // 2
        
        existing_next_match = await db.event_matches.find_one({
            "event_id": event_id,
            "group_id": group_id,
            "bracket_type": "winners",
            "round_number": next_winners_round,
            "bracket_match_index": next_match_index
        })
        
        if existing_next_match:
            # Mevcut maça ekle
            position = "participant1" if match_index % 2 == 0 else "participant2"
            await db.event_matches.update_one(
                {"id": existing_next_match["id"]},
                {"$set": {
                    f"{position}_id": winner_id,
                    f"{position}_name": winner_name,
                    f"losses_{position[-2:]}": 0
                }}
            )
        else:
            # Yeni winners maçı oluştur
            next_match_id = str(uuid.uuid4())
            next_match = {
                "id": next_match_id,
                "event_id": event_id,
                "group_id": group_id,
                "group_name": "Çift Eleme - Kazananlar",
                "category": category,
                "round_number": next_winners_round,
                "round_name": f"Kazananlar Tur {next_winners_round}",
                "bracket_match_index": next_match_index,
                "participant1_id": winner_id if match_index % 2 == 0 else None,
                "participant1_name": winner_name if match_index % 2 == 0 else "TBD",
                "participant2_id": winner_id if match_index % 2 == 1 else None,
                "participant2_name": winner_name if match_index % 2 == 1 else "TBD",
                "status": "pending",
                "bracket_type": "winners",
                "bracket_position": "winners",
                "stage": "double_elimination",
                "tournament_type": "double_elimination",
                "created_at": datetime.utcnow()
            }
            await db.event_matches.insert_one(next_match)
            created_matches.append(next_match)
            
    else:  # Losers bracket
        # Losers bracket'tan kaybeden -> Elenir (2. yenilgi)
        # Kazanan bir sonraki losers turuna ilerler
        
        next_losers_round = round_number + 1
        next_match_index = match_index // 2
        
        existing_next_match = await db.event_matches.find_one({
            "event_id": event_id,
            "group_id": group_id,
            "bracket_type": "losers",
            "round_number": next_losers_round,
            "bracket_match_index": next_match_index
        })
        
        if existing_next_match:
            position = "participant1" if match_index % 2 == 0 else "participant2"
            await db.event_matches.update_one(
                {"id": existing_next_match["id"]},
                {"$set": {
                    f"{position}_id": winner_id,
                    f"{position}_name": winner_name,
                    f"losses_{position[-2:]}": 1
                }}
            )
        else:
            next_match_id = str(uuid.uuid4())
            next_match = {
                "id": next_match_id,
                "event_id": event_id,
                "group_id": group_id,
                "group_name": "Çift Eleme - Kaybedenler",
                "category": category,
                "round_number": next_losers_round,
                "round_name": f"Kaybedenler Tur {next_losers_round}",
                "bracket_match_index": next_match_index,
                "participant1_id": winner_id if match_index % 2 == 0 else None,
                "participant1_name": winner_name if match_index % 2 == 0 else "TBD",
                "status": "pending",
                "bracket_type": "losers",
                "bracket_position": "losers",
                "stage": "double_elimination",
                "tournament_type": "double_elimination",
                "created_at": datetime.utcnow()
            }
            await db.event_matches.insert_one(next_match)
            created_matches.append(next_match)
    
    logger.info(f"🏆🏆 Çift eleme ilerleme: {winner_name} kazandı, {loser_name} {'elendi' if bracket_type == 'losers' else 'losers bracketa düştü'}")
    
    return {
        "status": "success",
        "message": f"{winner_name} ilerledi" + (f", {loser_name} kaybedenler bracket'ına düştü" if bracket_type == "winners" else f", {loser_name} elendi"),
        "winner_id": winner_id,
        "loser_id": loser_id,
        "loser_eliminated": bracket_type == "losers",
        "created_matches": len(created_matches)
    }


@event_management_router.get("/{event_id}/double-elimination/bracket")
async def get_double_elimination_bracket(
    event_id: str,
    current_user: dict = None
):
    """
    Çift eleme bracket'ını getir
    """
    global db
    
    # Çift eleme grubunu bul
    de_group = await db.event_groups.find_one({
        "event_id": event_id,
        "tournament_type": "double_elimination"
    })
    
    if not de_group:
        return {"winners_bracket": [], "losers_bracket": [], "grand_final": None}
    
    # Winners bracket maçları
    winners_matches = await db.event_matches.find({
        "event_id": event_id,
        "group_id": de_group["id"],
        "bracket_type": "winners"
    }).sort([("round_number", 1), ("bracket_match_index", 1)]).to_list(500)
    
    # Losers bracket maçları
    losers_matches = await db.event_matches.find({
        "event_id": event_id,
        "group_id": de_group["id"],
        "bracket_type": "losers"
    }).sort([("round_number", 1), ("bracket_match_index", 1)]).to_list(500)
    
    # Grand final maçları
    grand_final_matches = await db.event_matches.find({
        "event_id": event_id,
        "group_id": de_group["id"],
        "bracket_type": "grand_final"
    }).sort("match_number", 1).to_list(10)
    
    # Maçları turlara göre grupla
    winners_rounds = {}
    for m in winners_matches:
        if "_id" in m:
            del m["_id"]
        rn = m.get("round_number", 1)
        if rn not in winners_rounds:
            winners_rounds[rn] = []
        winners_rounds[rn].append(m)
    
    losers_rounds = {}
    for m in losers_matches:
        if "_id" in m:
            del m["_id"]
        rn = m.get("round_number", 1)
        if rn not in losers_rounds:
            losers_rounds[rn] = []
        losers_rounds[rn].append(m)
    
    for m in grand_final_matches:
        if "_id" in m:
            del m["_id"]
    
    return {
        "winners_bracket": winners_rounds,
        "losers_bracket": losers_rounds,
        "grand_final": grand_final_matches,
        "group_id": de_group["id"],
        "participant_count": len(de_group.get("participant_ids", [])),
        "bracket_structure": de_group.get("bracket_structure", {})
    }


@event_management_router.delete("/{event_id}/double-elimination/delete")
async def delete_double_elimination_tournament(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Çift eleme turnuvasını sil
    """
    global db
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    # Çift eleme grubunu bul
    de_group = await db.event_groups.find_one({
        "event_id": event_id,
        "tournament_type": "double_elimination"
    })
    
    if not de_group:
        raise HTTPException(status_code=404, detail="Çift eleme turnuvası bulunamadı")
    
    # Maçları sil
    matches_deleted = await db.event_matches.delete_many({
        "event_id": event_id,
        "group_id": de_group["id"]
    })
    
    # Grubu sil
    await db.event_groups.delete_one({"id": de_group["id"]})
    
    logger.info(f"🏆🏆 Çift eleme turnuvası silindi: {matches_deleted.deleted_count} maç")
    
    return {
        "status": "success",
        "message": "Çift eleme turnuvası silindi",
        "matches_deleted": matches_deleted.deleted_count
    }


@event_management_router.get("/{event_id}/swiss/standings")
async def get_swiss_standings(
    event_id: str,
    current_user: dict = None
):
    """
    İsviçre sistemi sıralamasını getir
    Puan > Buchholz > Sonneborn-Berger sıralaması
    """
    global db
    
    # İsviçre grubunu bul
    swiss_group = await db.event_groups.find_one({
        "event_id": event_id,
        "tournament_type": "swiss"
    })
    
    if not swiss_group:
        return {"standings": [], "current_round": 0, "total_rounds": 0}
    
    # Standings'i al ve sırala
    standings = await db.event_standings.find({
        "event_id": event_id,
        "group_id": swiss_group["id"]
    }).to_list(1000)
    
    # Puan > Buchholz > Sonneborn-Berger > Rating sıralaması
    sorted_standings = sorted(
        standings,
        key=lambda x: (
            -x.get("points", 0),
            -x.get("buchholz", 0),
            -x.get("sonneborn_berger", 0),
            -x.get("rating", 0)
        )
    )
    
    # Sıra numarası ekle
    for i, s in enumerate(sorted_standings):
        s["rank"] = i + 1
        if "_id" in s:
            del s["_id"]
    
    return {
        "standings": sorted_standings,
        "current_round": swiss_group.get("current_round", 0),
        "total_rounds": swiss_group.get("total_rounds", 0),
        "group_id": swiss_group["id"]
    }


@event_management_router.get("/{event_id}/swiss/matches")
async def get_swiss_matches(
    event_id: str,
    round_number: Optional[int] = None,
    current_user: dict = None
):
    """
    İsviçre sistemi maçlarını getir
    """
    global db
    
    # İsviçre grubunu bul
    swiss_group = await db.event_groups.find_one({
        "event_id": event_id,
        "tournament_type": "swiss"
    })
    
    if not swiss_group:
        return {"matches": [], "rounds": []}
    
    query = {
        "event_id": event_id,
        "group_id": swiss_group["id"]
    }
    
    if round_number:
        query["round_number"] = round_number
    
    matches = await db.event_matches.find(query).sort([
        ("round_number", 1),
        ("match_number", 1)
    ]).to_list(1000)
    
    # Turları grupla
    rounds = {}
    for m in matches:
        if "_id" in m:
            del m["_id"]
        
        rn = m.get("round_number", 1)
        if rn not in rounds:
            rounds[rn] = []
        rounds[rn].append(m)
    
    return {
        "matches": matches,
        "rounds": rounds,
        "current_round": swiss_group.get("current_round", 0)
    }


@event_management_router.delete("/{event_id}/swiss/delete")
async def delete_swiss_tournament(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    İsviçre sistemi turnuvasını sil (grup, maçlar, standings)
    """
    global db
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız")
    
    # İsviçre grubunu bul
    swiss_group = await db.event_groups.find_one({
        "event_id": event_id,
        "tournament_type": "swiss"
    })
    
    if not swiss_group:
        raise HTTPException(status_code=404, detail="İsviçre grubu bulunamadı")
    
    # Maçları sil
    matches_deleted = await db.event_matches.delete_many({
        "event_id": event_id,
        "group_id": swiss_group["id"]
    })
    
    # Standings'i sil
    standings_deleted = await db.event_standings.delete_many({
        "event_id": event_id,
        "group_id": swiss_group["id"]
    })
    
    # Grubu sil
    await db.event_groups.delete_one({"id": swiss_group["id"]})
    
    logger.info(f"🇨🇭 İsviçre turnuvası silindi: {matches_deleted.deleted_count} maç, {standings_deleted.deleted_count} standings")
    
    return {
        "status": "success",
        "message": "İsviçre turnuvası silindi",
        "matches_deleted": matches_deleted.deleted_count,
        "standings_deleted": standings_deleted.deleted_count
    }



# ==================== ÇİFT ELEME İLERLEME FONKSİYONU ====================
async def advance_double_elimination(db, event_id: str, completed_match: dict):
    """
    Çift eleme maçı tamamlandığında:
    1. Kazanan → Winners bracket'ta bir sonraki tura
    2. Kaybeden → Losers bracket'a düşer (eğer winners'daysa)
    3. Losers'da kaybeden → Elenir
    4. Tüm ilk tur maçları bitince ikinci tur maçlarını oluştur
    """
    try:
        winner_id = completed_match.get("winner_id")
        if not winner_id:
            logger.warning("⚠️ advance_double_elimination: winner_id yok")
            return
        
        bracket_type = completed_match.get("bracket_type", "winners")  # winners, losers, grand_final
        current_round = completed_match.get("round_number", 1)
        group_id = completed_match.get("group_id")
        
        # Kazanan ve kaybeden bilgileri
        p1_id = completed_match.get("participant1_id")
        p2_id = completed_match.get("participant2_id")
        loser_id = p2_id if winner_id == p1_id else p1_id
        
        winner_name = completed_match.get("participant1_name") if winner_id == p1_id else completed_match.get("participant2_name")
        loser_name = completed_match.get("participant2_name") if winner_id == p1_id else completed_match.get("participant1_name")
        
        logger.info(f"🏆🏆 Çift Eleme İlerleme: {bracket_type} R{current_round}")
        logger.info(f"   Kazanan: {winner_name} ({winner_id[:8]}...)")
        logger.info(f"   Kaybeden: {loser_name} ({loser_id[:8]}...)")
        
        # Aynı bracket_type ve round'daki tüm maçları kontrol et
        same_round_matches = await db.event_matches.find({
            "event_id": event_id,
            "tournament_type": "double_elimination",
            "bracket_type": bracket_type,
            "round_number": current_round
        }).to_list(100)
        
        # Tamamlanan maç sayısını kontrol et
        completed_count = sum(1 for m in same_round_matches if m.get("winner_id"))
        total_count = len(same_round_matches)
        
        logger.info(f"   Tur durumu: {completed_count}/{total_count} maç tamamlandı")
        
        # Tüm maçlar tamamlandıysa bir sonraki turu oluştur
        if completed_count == total_count:
            logger.info(f"✅ {bracket_type} R{current_round} tamamlandı! Sonraki tur oluşturuluyor...")
            
            next_round = current_round + 1
            
            # Kazananları al (sıralı)
            winners = []
            for m in sorted(same_round_matches, key=lambda x: x.get("bracket_index", 0)):
                w_id = m.get("winner_id")
                w_name = m.get("participant1_name") if w_id == m.get("participant1_id") else m.get("participant2_name")
                winners.append({"id": w_id, "name": w_name or "Bilinmeyen"})
            
            # Winners bracket için sonraki tur maçlarını oluştur
            if bracket_type == "winners":
                # Kaybedenleri losers bracket'a ekle
                losers = []
                for m in sorted(same_round_matches, key=lambda x: x.get("bracket_index", 0)):
                    w_id = m.get("winner_id")
                    l_id = m.get("participant2_id") if w_id == m.get("participant1_id") else m.get("participant1_id")
                    l_name = m.get("participant2_name") if w_id == m.get("participant1_id") else m.get("participant1_name")
                    losers.append({"id": l_id, "name": l_name or "Bilinmeyen"})
                
                # Winners bracket sonraki tur
                if len(winners) >= 2:
                    next_winners_matches = []
                    for i in range(0, len(winners), 2):
                        if i + 1 < len(winners):
                            match = {
                                "id": str(uuid.uuid4()),
                                "event_id": event_id,
                                "group_id": group_id,
                                "tournament_type": "double_elimination",
                                "bracket_type": "winners",
                                "round_number": next_round,
                                "bracket_index": i // 2,
                                "participant1_id": winners[i]["id"],
                                "participant1_name": winners[i]["name"],
                                "participant2_id": winners[i + 1]["id"],
                                "participant2_name": winners[i + 1]["name"],
                                "status": "scheduled",
                                "created_at": datetime.utcnow()
                            }
                            next_winners_matches.append(match)
                    
                    if next_winners_matches:
                        await db.event_matches.insert_many(next_winners_matches)
                        logger.info(f"✅ Winners R{next_round}: {len(next_winners_matches)} maç oluşturuldu")
                elif len(winners) == 1:
                    # Winners bracket şampiyonu belli - Grand Final'e git
                    logger.info(f"🏆 Winners bracket şampiyonu: {winners[0]['name']}")
                
                # Losers bracket'a düşenleri ekle
                if losers:
                    # İlk tur ise direkt losers R1 oluştur
                    losers_round = 1 if current_round == 1 else current_round
                    
                    # Mevcut losers maçlarını kontrol et
                    existing_losers = await db.event_matches.find({
                        "event_id": event_id,
                        "tournament_type": "double_elimination",
                        "bracket_type": "losers",
                        "round_number": losers_round
                    }).to_list(100)
                    
                    if not existing_losers and len(losers) >= 2:
                        losers_matches = []
                        for i in range(0, len(losers), 2):
                            if i + 1 < len(losers):
                                match = {
                                    "id": str(uuid.uuid4()),
                                    "event_id": event_id,
                                    "group_id": group_id,
                                    "tournament_type": "double_elimination",
                                    "bracket_type": "losers",
                                    "round_number": losers_round,
                                    "bracket_index": i // 2,
                                    "participant1_id": losers[i]["id"],
                                    "participant1_name": losers[i]["name"],
                                    "participant2_id": losers[i + 1]["id"],
                                    "participant2_name": losers[i + 1]["name"],
                                    "status": "scheduled",
                                    "created_at": datetime.utcnow()
                                }
                                losers_matches.append(match)
                        
                        if losers_matches:
                            await db.event_matches.insert_many(losers_matches)
                            logger.info(f"✅ Losers R{losers_round}: {len(losers_matches)} maç oluşturuldu")
            
            # Losers bracket için sonraki tur
            elif bracket_type == "losers":
                if len(winners) >= 2:
                    next_losers_matches = []
                    for i in range(0, len(winners), 2):
                        if i + 1 < len(winners):
                            match = {
                                "id": str(uuid.uuid4()),
                                "event_id": event_id,
                                "group_id": group_id,
                                "tournament_type": "double_elimination",
                                "bracket_type": "losers",
                                "round_number": next_round,
                                "bracket_index": i // 2,
                                "participant1_id": winners[i]["id"],
                                "participant1_name": winners[i]["name"],
                                "participant2_id": winners[i + 1]["id"],
                                "participant2_name": winners[i + 1]["name"],
                                "status": "scheduled",
                                "created_at": datetime.utcnow()
                            }
                            next_losers_matches.append(match)
                    
                    if next_losers_matches:
                        await db.event_matches.insert_many(next_losers_matches)
                        logger.info(f"✅ Losers R{next_round}: {len(next_losers_matches)} maç oluşturuldu")
                elif len(winners) == 1:
                    # Losers bracket şampiyonu belli - Grand Final'e git
                    logger.info(f"🥈 Losers bracket şampiyonu: {winners[0]['name']}")
                    
                    # Grand Final oluştur (eğer yoksa)
                    existing_gf = await db.event_matches.find_one({
                        "event_id": event_id,
                        "tournament_type": "double_elimination",
                        "bracket_type": "grand_final"
                    })
                    
                    if not existing_gf:
                        # Winners şampiyonunu bul
                        winners_champ = await db.event_matches.find_one({
                            "event_id": event_id,
                            "tournament_type": "double_elimination",
                            "bracket_type": "winners",
                            "winner_id": {"$exists": True}
                        }, sort=[("round_number", -1)])
                        
                        if winners_champ:
                            wc_id = winners_champ.get("winner_id")
                            wc_name = winners_champ.get("participant1_name") if wc_id == winners_champ.get("participant1_id") else winners_champ.get("participant2_name")
                            
                            grand_final = {
                                "id": str(uuid.uuid4()),
                                "event_id": event_id,
                                "group_id": group_id,
                                "tournament_type": "double_elimination",
                                "bracket_type": "grand_final",
                                "round_number": 1,
                                "bracket_index": 0,
                                "participant1_id": wc_id,
                                "participant1_name": wc_name,
                                "participant2_id": winners[0]["id"],
                                "participant2_name": winners[0]["name"],
                                "status": "scheduled",
                                "created_at": datetime.utcnow()
                            }
                            await db.event_matches.insert_one(grand_final)
                            logger.info(f"🏆🏆 GRAND FINAL oluşturuldu: {wc_name} vs {winners[0]['name']}")
        
        logger.info(f"✅ Çift eleme ilerleme tamamlandı")
        
    except Exception as e:
        logger.error(f"❌ advance_double_elimination hatası: {str(e)}")
        import traceback
        traceback.print_exc()

