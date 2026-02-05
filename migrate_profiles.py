"""
Profile Data Migration Script
Migrates CoachProfile and RefereeProfile to new comprehensive structure
"""
import os
from pymongo import MongoClient
from datetime import datetime

# MongoDB connection
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017/')
DB_NAME = os.environ.get('DB_NAME', 'sportconnect')
client = MongoClient(MONGO_URL)
db = client[DB_NAME]
print(f"🔗 Connected to database: {DB_NAME}\n")

def migrate_coach_profiles():
    """Migrate CoachProfile to add missing fields"""
    print("🔄 Migrating Coach Profiles...")
    
    coaches = db.users.find({'user_type': 'coach'})
    updated_count = 0
    
    for coach in coaches:
        profile = coach.get('coach_profile')
        
        # Skip if no coach_profile at all
        if not profile:
            print(f"  ⏭️  Skipped (no coach_profile): {coach['full_name']}")
            continue
        
        # Add missing fields with default values
        updates = {}
        
        # specializations - derive from bio or set defaults
        if 'specializations' not in profile:
            # Default specializations based on sports
            default_specs = ['Teknik', 'Kondisyon']
            updates['coach_profile.specializations'] = default_specs
            
        # license_number - check certifications or set default
        if 'license_number' not in profile:
            certs = profile.get('certifications', [])
            if certs and len(certs) > 0:
                # Use first certification as license
                updates['coach_profile.license_number'] = certs[0]
            else:
                updates['coach_profile.license_number'] = 'LIC-' + coach['_id'][:8].upper()
        
        # years_of_experience - derive from bio or set default
        if 'years_of_experience' not in profile:
            bio = profile.get('bio', '')
            # Try to extract years from bio
            import re
            year_match = re.search(r'(\d+)\s*yıl', bio)
            if year_match:
                updates['coach_profile.years_of_experience'] = int(year_match.group(1))
            else:
                updates['coach_profile.years_of_experience'] = 5  # default
        
        # age_groups - set reasonable defaults
        if 'age_groups' not in profile:
            updates['coach_profile.age_groups'] = ['Çocuklar', 'Gençler', 'Yetişkinler']
        
        # service_types - set reasonable defaults
        if 'service_types' not in profile:
            updates['coach_profile.service_types'] = ['Bireysel', 'Grup']
        
        if updates:
            db.users.update_one(
                {'_id': coach['_id']},
                {'$set': updates}
            )
            updated_count += 1
            print(f"  ✅ Updated coach: {coach['full_name']}")
    
    print(f"✅ Migrated {updated_count} coach profiles\n")
    return updated_count

def migrate_referee_profiles():
    """Migrate RefereeProfile to multi-sport structure"""
    print("🔄 Migrating Referee Profiles...")
    
    referees = db.users.find({'user_type': 'referee'})
    updated_count = 0
    
    for referee in referees:
        profile = referee.get('referee_profile', {})
        
        # Check if already migrated (has 'sports' array)
        if 'sports' in profile and isinstance(profile['sports'], list):
            print(f"  ⏭️  Skipped (already migrated): {referee['full_name']}")
            continue
        
        # Extract single sport data
        sport = profile.get('sport', 'Futbol')
        level = profile.get('level', 'il')
        license_number = profile.get('license_number', '')
        years_of_experience = profile.get('years_of_experience')
        match_count = profile.get('match_count')
        
        # Create RefereeSportProfile structure
        sport_profile = {
            'sport': sport,
            'level': level,
            'license_number': license_number,
            'years_of_experience': years_of_experience,
            'match_count': match_count
        }
        
        # Remove None values
        sport_profile = {k: v for k, v in sport_profile.items() if v is not None}
        
        # Create new structure
        new_profile = {
            'sports': [sport_profile],
            'bio': profile.get('bio'),
            'rating': profile.get('rating', 0.0),
            'review_count': profile.get('review_count', 0)
        }
        
        # Replace entire referee_profile with new structure
        db.users.update_one(
            {'_id': referee['_id']},
            {'$set': {'referee_profile': new_profile}}
        )
        updated_count += 1
        print(f"  ✅ Updated referee: {referee['full_name']} - {sport}")
    
    print(f"✅ Migrated {updated_count} referee profiles\n")
    return updated_count

def verify_migration():
    """Verify migration was successful"""
    print("🔍 Verifying Migration...")
    
    # Check coaches
    coaches = list(db.users.find({'user_type': 'coach'}).limit(1))
    if coaches:
        coach = coaches[0]
        profile = coach.get('coach_profile', {})
        required_fields = ['specializations', 'license_number', 'years_of_experience', 'age_groups', 'service_types']
        missing = [f for f in required_fields if f not in profile]
        
        if missing:
            print(f"  ❌ Coach profile missing fields: {missing}")
            return False
        else:
            print(f"  ✅ Coach profile has all required fields")
    
    # Check referees
    referees = list(db.users.find({'user_type': 'referee'}).limit(1))
    if referees:
        referee = referees[0]
        profile = referee.get('referee_profile', {})
        
        if 'sports' not in profile or not isinstance(profile['sports'], list):
            print(f"  ❌ Referee profile missing 'sports' array")
            return False
        
        if len(profile['sports']) > 0:
            sport_profile = profile['sports'][0]
            required_fields = ['sport', 'level', 'license_number']
            missing = [f for f in required_fields if f not in sport_profile]
            
            if missing:
                print(f"  ❌ Referee sport profile missing fields: {missing}")
                return False
            else:
                print(f"  ✅ Referee profile has correct structure")
    
    print("✅ Migration verification passed!\n")
    return True

if __name__ == '__main__':
    print("=" * 60)
    print("PROFILE DATA MIGRATION")
    print("=" * 60)
    print()
    
    # Run migrations
    coach_count = migrate_coach_profiles()
    referee_count = migrate_referee_profiles()
    
    # Verify
    success = verify_migration()
    
    # Summary
    print("=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"✅ Coaches migrated: {coach_count}")
    print(f"✅ Referees migrated: {referee_count}")
    print(f"{'✅ Verification: PASSED' if success else '❌ Verification: FAILED'}")
    print()
    
    client.close()
