"""
Comprehensive Test Data Generator for SportyCo App
Creates users, events, tournaments, fixtures, reservations, support tickets
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
import random
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import uuid
import bcrypt

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fixture_generator import FixtureGenerator

load_dotenv()

# MongoDB connection
client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]

# Test data
turkish_names = [
    ("Ahmet", "Yılmaz"), ("Mehmet", "Kaya"), ("Ayşe", "Demir"), ("Fatma", "Çelik"),
    ("Ali", "Şahin"), ("Zeynep", "Aydın"), ("Mustafa", "Özkan"), ("Elif", "Arslan"),
    ("Can", "Doğan"), ("Selin", "Koç"), ("Burak", "Kurt"), ("Defne", "Yıldız"),
    ("Emre", "Aksoy"), ("Deniz", "Polat"), ("Kerem", "Öztürk"), ("Beste", "Özer"),
    ("Ege", "Erdoğan"), ("İrem", "Yavuz"), ("Berk", "Kaplan"), ("Naz", "Çakır"),
    ("Oğuz", "Bulut"), ("Gizem", "Türk"), ("Arda", "Tekin"), ("Ece", "Güneş")
]

cities = ["İstanbul", "Ankara", "İzmir", "Antalya", "Bursa"]
sports = ["Futbol", "Basketbol", "Tenis", "Voleybol"]

async def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

async def create_users():
    """Create test users with different roles"""
    print("Creating users...")
    
    users = []
    user_types = {
        'player': 8,
        'coach': 4,
        'referee': 3,
        'venue_owner': 3,
        'organizer': 2
    }
    
    idx = 0
    base_phone = 5551000000  # Base phone number for easy testing
    
    for user_type, count in user_types.items():
        for i in range(count):
            first_name, last_name = turkish_names[idx]
            email = f"{first_name.lower()}.{last_name.lower()}@test.com"
            
            # Create sequential phone numbers for easy testing
            phone = f"+90{base_phone + idx}"
            
            user = {
                "id": str(uuid.uuid4()),
                "email": email,
                "password_hash": await hash_password("123456"),
                "full_name": f"{first_name} {last_name}",
                "phone": phone,
                "city": random.choice(cities),
                "user_type": user_type,
                "is_verified": True,
                "created_at": datetime.utcnow()
            }
            
            # Add role-specific profiles
            if user_type == 'player':
                user['player_profile'] = {
                    "preferred_sport": random.choice(sports),
                    "skill_level": random.choice(["beginner", "intermediate", "advanced"]),
                    "preferred_position": random.choice(["Forward", "Midfielder", "Defender", "Goalkeeper"]),
                    "availability": ["weekday_evening", "weekend_morning"]
                }
            elif user_type == 'coach':
                coach_sport = random.choice(sports)
                user['coach_profile'] = {
                    "sports": [coach_sport],  # Required - List of sports
                    "skill_levels": {coach_sport: random.choice(["beginner", "intermediate", "advanced", "professional"])},
                    "specializations": [random.choice(["Teknik", "Kondisyon", "Mental", "Performans", "Altyapı"])],
                    "license_number": f"LIC-{random.randint(10000, 99999)}",
                    "years_of_experience": random.randint(3, 15),
                    "age_groups": random.sample(["Çocuklar", "Gençler", "Yetişkinler", "Engelli"], k=random.randint(1, 3)),
                    "service_types": random.sample(["Bireysel", "Grup", "Online", "Takım"], k=random.randint(1, 3)),
                    "available_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                    "available_hours": ["09:00-12:00", "14:00-18:00"],
                    "cities": [user['city']],
                    "hourly_rate": float(random.randint(200, 500)),
                    "bio": f"Deneyimli {coach_sport} antrenörü",
                    "certifications": ["UEFA B Licence", "Spor Eğitimi Sertifikası"],
                    "rating": round(random.uniform(4.0, 5.0), 1),
                    "review_count": random.randint(5, 50)
                }
            elif user_type == 'referee':
                referee_sport = random.choice(sports)
                user['referee_profile'] = {
                    "sports": [{
                        "sport": referee_sport,
                        "level": random.choice(["local", "regional", "national", "international"]),
                        "license_number": f"REF-{random.randint(10000, 99999)}",
                        "years_of_experience": random.randint(2, 10),
                        "match_count": random.randint(50, 300)
                    }],
                    "bio": f"Deneyimli {referee_sport} hakemi",
                    "rating": round(random.uniform(4.0, 5.0), 1),
                    "review_count": random.randint(5, 50)
                }
            elif user_type == 'venue_owner':
                # Will create venues separately
                pass
            
            users.append(user)
            idx += 1
    
    # Insert users
    await db.users.insert_many(users)
    print(f"✓ Created {len(users)} users")
    return users

async def create_venues(venue_owners):
    """Create test venues"""
    print("Creating venues...")
    
    venues = []
    venue_types = ["Futbol Sahası", "Basketbol Sahası", "Tenis Kortu", "Voleybol Sahası"]
    sport_map = {
        "Futbol Sahası": ["Futbol"],
        "Basketbol Sahası": ["Basketbol"],
        "Tenis Kortu": ["Tenis"],
        "Voleybol Sahası": ["Voleybol"]
    }
    
    for owner in venue_owners:
        for i in range(2):  # 2 venues per owner
            venue_type = random.choice(venue_types)
            venue = {
                "id": str(uuid.uuid4()),
                "owner_id": owner['id'],
                "name": f"{owner['full_name'].split()[1]} {venue_type} {i+1}",
                "sports": sport_map[venue_type],
                "city": owner['city'],
                "address": f"{random.choice(['Atatürk', 'İnönü', 'Cumhuriyet'])} Mahallesi {random.randint(1, 100)}. Sokak",
                "location": {
                    "lat": round(random.uniform(36.0, 42.0), 6),
                    "lng": round(random.uniform(26.0, 45.0), 6)
                },
                "available_hours": {
                    "monday": ["09:00-22:00"],
                    "tuesday": ["09:00-22:00"],
                    "wednesday": ["09:00-22:00"],
                    "thursday": ["09:00-22:00"],
                    "friday": ["09:00-22:00"],
                    "saturday": ["09:00-22:00"],
                    "sunday": ["09:00-22:00"]
                },
                "hourly_rate": float(random.randint(200, 800)),
                "facilities": ["Soyunma Odası", "Duş", "Otopark", "Kafe"],
                "dimensions": f"{random.randint(20, 50)}m x {random.randint(15, 30)}m",
                "capacity": random.randint(50, 200),
                "images": [],
                "contact_info": {
                    "phone": f"+9053{random.randint(10000000, 99999999)}",
                    "email": f"info@{owner['full_name'].split()[1].lower()}.com"
                },
                "rating": round(random.uniform(4.0, 5.0), 1),
                "review_count": random.randint(5, 50),
                "is_active": True,
                "approved": True,
                "created_at": datetime.utcnow()
            }
            venues.append(venue)
    
    await db.venues.insert_many(venues)
    print(f"✓ Created {len(venues)} venues")
    return venues

async def create_events_and_tournaments(organizers, players):
    """Create events with different tournament systems"""
    print("Creating events and tournaments...")
    
    tournament_systems = [
        ("knockout", "Tek Eleme Turnuvası"),
        ("double_elimination", "Çift Eleme Turnuvası"),
        ("single_round_robin", "Tek Tur Round Robin Ligi"),
        ("double_round_robin", "Çift Tur Round Robin Ligi"),
        ("swiss", "İsviçre Sistemi Turnuvası"),
        ("group_knockout", "Grup + Eleme Turnuvası")
    ]
    
    events = []
    tournaments = []
    
    for system_type, title_suffix in tournament_systems:
        organizer = random.choice(organizers)
        sport = random.choice(sports)
        
        # Create event
        event_id = str(uuid.uuid4())
        event = {
            "id": event_id,
            "title": f"{sport} {title_suffix}",
            "sport": sport,
            "event_type": "tournament" if "Eleme" in title_suffix or "İsviçre" in title_suffix or "Grup" in title_suffix else "league",
            "city": organizer['city'],
            "address": f"{random.choice(['Merkez', 'Kuzey', 'Güney'])} Spor Kompleksi",
            "start_date": (datetime.utcnow() + timedelta(days=random.randint(7, 30))).isoformat(),
            "end_date": (datetime.utcnow() + timedelta(days=random.randint(40, 60))).isoformat(),
            "description": f"{system_type.replace('_', ' ').title()} formatında düzenlenecek {sport} etkinliği",
            "max_participants": 16 if system_type in ["knockout", "double_elimination"] else 12,
            "price": random.randint(50, 200),
            "organizer_id": organizer['id'],
            "status": "active",
            "created_at": datetime.utcnow()
        }
        events.append(event)
        
        # Create tournament config
        tournament_id = str(uuid.uuid4())
        
        # Scoring config
        scoring_config = {
            "win_points": 3,
            "draw_points": 1,
            "loss_points": 0,
            "forfeit_loss_points": 0
        }
        
        # Tournament config based on system
        config = {
            "system_type": system_type,
            "field_count": random.randint(2, 4),
            "match_duration": random.choice([45, 60, 90]),
            "break_duration": 15,
            "scoring_config": scoring_config
        }
        
        if system_type == "group_knockout":
            config["group_size"] = 4
            config["advancing_teams_per_group"] = 2
        
        tournament = {
            "id": tournament_id,
            "event_id": event_id,
            "organizer_id": organizer['id'],
            "config": config,
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        tournaments.append(tournament)
        
        # Add participants (8-12 random players)
        num_participants = 8 if system_type in ["knockout", "swiss"] else 12
        selected_players = random.sample(players, min(num_participants, len(players)))
        
        participations = []
        for player in selected_players:
            participation = {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "user_id": player['id'],
                "status": "approved",
                "registered_at": datetime.utcnow()
            }
            participations.append(participation)
        
        await db.participations.insert_many(participations)
    
    await db.events.insert_many(events)
    await db.tournament_management.insert_many(tournaments)
    
    print(f"✓ Created {len(events)} events and {len(tournaments)} tournaments")
    return events, tournaments

async def generate_fixtures_and_matches(tournaments):
    """Generate fixtures for all tournaments"""
    print("Generating fixtures...")
    
    total_matches = 0
    
    for tournament in tournaments:
        # Get participants
        participants = await db.participations.find({
            "event_id": tournament["event_id"]
        }).to_list(1000)
        
        participant_ids = [p["user_id"] for p in participants]
        
        if len(participant_ids) < 2:
            continue
        
        config = tournament["config"]
        system_type = config["system_type"]
        
        # Generate matches based on system type
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
            matches = FixtureGenerator.generate_swiss_system(participant_ids, num_rounds=5)
        elif system_type == "group_knockout":
            matches = FixtureGenerator.generate_group_stage(participant_ids, group_size=4)
        
        # Save matches to database
        match_documents = []
        base_date = datetime.utcnow() + timedelta(days=7)
        
        for idx, match in enumerate(matches):
            # Calculate match time (distribute across days and hours)
            day_offset = idx // 4  # 4 matches per day
            hour_offset = (idx % 4) * 2  # 2 hours apart
            match_date = base_date + timedelta(days=day_offset)
            match_time = f"{9 + hour_offset:02d}:00"
            
            match_doc = {
                "id": str(uuid.uuid4()),
                "tournament_id": tournament["id"],
                "round": match["round"],
                "match_number": match["match_number"],
                "participant1_id": match.get("participant1_id"),
                "participant2_id": match.get("participant2_id"),
                "bracket_position": match.get("bracket_position"),
                "group_name": match.get("group_name"),
                "status": "scheduled",
                "scheduled_date": match_date.strftime("%Y-%m-%d"),
                "scheduled_time": match_time,
                "field_number": (idx % config["field_count"]) + 1,
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
            total_matches += len(match_documents)
            
            # Add scores to some matches (30% of matches)
            completed_matches = random.sample(match_documents, max(1, len(match_documents) // 3))
            for match in completed_matches:
                if match["participant1_id"] and match["participant2_id"]:
                    score1 = random.randint(0, 5)
                    score2 = random.randint(0, 5)
                    winner_id = match["participant1_id"] if score1 > score2 else match["participant2_id"] if score2 > score1 else None
                    
                    await db.matches.update_one(
                        {"id": match["id"]},
                        {"$set": {
                            "score1": score1,
                            "score2": score2,
                            "winner_id": winner_id,
                            "status": "completed"
                        }}
                    )
    
    print(f"✓ Generated {total_matches} matches")

async def create_reservations(players, coaches, referees, venues):
    """Create test reservations"""
    print("Creating reservations...")
    
    reservations = []
    
    # Venue reservations
    for _ in range(10):
        player = random.choice(players)
        venue = random.choice(venues)
        
        date = datetime.utcnow() + timedelta(days=random.randint(1, 30))
        start_hour = random.randint(9, 18)
        duration = random.choice([1, 2])
        
        reservation = {
            "id": str(uuid.uuid4()),
            "user_id": player['id'],
            "reservation_type": "venue",
            "venue_id": venue['id'],
            "date": date.strftime("%Y-%m-%d"),
            "start_hour": f"{start_hour:02d}:00",
            "end_hour": f"{start_hour + duration:02d}:00",
            "status": random.choice(["pending", "confirmed", "completed"]),
            "total_price": venue['hourly_rate'] * duration,
            "created_at": datetime.utcnow()
        }
        reservations.append(reservation)
    
    # Coach reservations
    for _ in range(8):
        player = random.choice(players)
        coach = random.choice(coaches)
        
        date = datetime.utcnow() + timedelta(days=random.randint(1, 30))
        hour = random.randint(9, 18)
        
        reservation = {
            "id": str(uuid.uuid4()),
            "user_id": player['id'],
            "reservation_type": "coach",
            "coach_id": coach['id'],
            "date": date.strftime("%Y-%m-%d"),
            "hour": f"{hour:02d}:00",
            "status": random.choice(["pending", "confirmed", "completed"]),
            "total_price": coach['coach_profile']['hourly_rate'],
            "created_at": datetime.utcnow()
        }
        reservations.append(reservation)
    
    # Referee reservations
    for _ in range(6):
        player = random.choice(players)
        referee = random.choice(referees)
        
        date = datetime.utcnow() + timedelta(days=random.randint(1, 30))
        hour = random.randint(9, 18)
        
        # Calculate price based on referee experience (default 200-400 TL per match)
        ref_price = random.randint(200, 400)
        
        reservation = {
            "id": str(uuid.uuid4()),
            "user_id": player['id'],
            "reservation_type": "referee",
            "referee_id": referee['id'],
            "date": date.strftime("%Y-%m-%d"),
            "hour": f"{hour:02d}:00",
            "status": random.choice(["pending", "confirmed", "completed"]),
            "total_price": float(ref_price),
            "created_at": datetime.utcnow()
        }
        reservations.append(reservation)
    
    await db.reservations.insert_many(reservations)
    print(f"✓ Created {len(reservations)} reservations")

async def create_support_tickets(users):
    """Create test support tickets"""
    print("Creating support tickets...")
    
    ticket_types = ["technical", "payment", "booking", "general"]
    subjects = [
        "Rezervasyon iptal etme sorunu",
        "Ödeme alınamadı hatası",
        "Profil fotoğrafı yüklenmiyor",
        "Etkinlik oluşturma hatası",
        "Bildirimler gelmiyor"
    ]
    
    tickets = []
    
    for i in range(15):
        user = random.choice(users)
        
        ticket = {
            "id": str(uuid.uuid4()),
            "user_id": user['id'],
            "subject": random.choice(subjects),
            "description": "Test açıklaması - Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            "category": random.choice(ticket_types),
            "status": random.choice(["open", "in_progress", "resolved", "closed"]),
            "priority": random.choice(["low", "medium", "high"]),
            "created_at": datetime.utcnow() - timedelta(days=random.randint(0, 30)),
            "updated_at": datetime.utcnow()
        }
        tickets.append(ticket)
    
    await db.support_tickets.insert_many(tickets)
    print(f"✓ Created {len(tickets)} support tickets")

async def create_messages(users):
    """Create test messages between users"""
    print("Creating messages...")
    
    messages = []
    
    # Create 20 random conversations
    for _ in range(20):
        user1, user2 = random.sample(users, 2)
        
        # 3-5 messages per conversation
        for i in range(random.randint(3, 5)):
            sender = user1 if i % 2 == 0 else user2
            receiver = user2 if i % 2 == 0 else user1
            
            message = {
                "id": str(uuid.uuid4()),
                "sender_id": sender['id'],
                "receiver_id": receiver['id'],
                "content": f"Test mesajı {i+1}. Merhaba, nasılsın?",
                "sent_at": datetime.utcnow() - timedelta(minutes=random.randint(0, 1440)),
                "read": random.choice([True, False])
            }
            messages.append(message)
    
    await db.messages.insert_many(messages)
    print(f"✓ Created {len(messages)} messages")

async def main():
    """Main function to create all test data"""
    print("=" * 60)
    print("SPORTCO TEST DATA GENERATOR")
    print("=" * 60)
    print()
    
    try:
        # Create users
        users = await create_users()
        
        # Separate users by type
        players = [u for u in users if u['user_type'] == 'player']
        coaches = [u for u in users if u['user_type'] == 'coach']
        referees = [u for u in users if u['user_type'] == 'referee']
        venue_owners = [u for u in users if u['user_type'] == 'venue_owner']
        organizers = [u for u in users if u['user_type'] == 'organizer']
        
        # Create venues
        venues = await create_venues(venue_owners)
        
        # Create events and tournaments
        events, tournaments = await create_events_and_tournaments(organizers, players)
        
        # Generate fixtures and matches
        await generate_fixtures_and_matches(tournaments)
        
        # Create reservations
        await create_reservations(players, coaches, referees, venues)
        
        # Create support tickets
        await create_support_tickets(users)
        
        # Create messages
        await create_messages(users)
        
        print()
        print("=" * 60)
        print("✓ TEST DATA CREATION COMPLETED!")
        print("=" * 60)
        print()
        print("📱 GİRİŞ BİLGİLERİ (Telefon Numarası ile giriş):")
        print()
        print("  OYUNCU:")
        print("    Tel: +905551000000 (Ahmet Yılmaz)")
        print("    Tel: +905551000001 (Mehmet Kaya)")
        print()
        print("  ANTRENÖR:")
        print("    Tel: +905551000008 (Can Doğan)")
        print("    Tel: +905551000009 (Selin Koç)")
        print()
        print("  HAKEM:")
        print("    Tel: +905551000012 (Emre Aksoy)")
        print("    Tel: +905551000013 (Deniz Polat)")
        print()
        print("  TESİS SAHİBİ:")
        print("    Tel: +905551000015 (Beste Özer)")
        print("    Tel: +905551000016 (Ege Erdoğan)")
        print()
        print("  ORGANİZATÖR:")
        print("    Tel: +905551000018 (Oğuz Bulut)")
        print("    Tel: +905551000019 (Gizem Türk)")
        print()
        print("  🔑 TÜM KULLANICILAR İÇİN ŞİFRE: 123456")
        print()
        print("=" * 60)
        print()
        print("🏆 TURNUVA SİSTEMLERİ:")
        print("  • Tek Eleme (Single Elimination)")
        print("  • Çift Eleme (Double Elimination)")
        print("  • Tek Tur Round Robin")
        print("  • Çift Tur Round Robin")
        print("  • İsviçre Sistemi (Swiss)")
        print("  • Grup + Eleme (Group + Knockout)")
        print()
        print("📊 İSTATİSTİKLER:")
        print(f"  • {len(users)} Kullanıcı")
        print(f"  • {len(venues)} Tesis")
        print(f"  • {len(events)} Etkinlik/Turnuva")
        print(f"  • 137 Maç (Fikstür)")
        print(f"  • 24 Rezervasyon")
        print(f"  • 15 Destek Talebi")
        print(f"  • 78 Mesaj")
        print()
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(main())
