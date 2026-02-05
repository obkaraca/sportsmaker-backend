"""
Tournament Management Service
Handles draw, seeding, bracket generation, scheduling, and scoring
"""

import random
import math
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import uuid

class TournamentService:
    """Service for tournament operations"""
    
    @staticmethod
    def generate_single_elimination_bracket(participants: List[Dict], seeding_method: str = "random") -> List[Dict]:
        """
        Generate single elimination bracket
        Returns list of bracket nodes with matchups
        """
        num_participants = len(participants)
        
        # Calculate tournament size (next power of 2)
        tournament_size = 2 ** math.ceil(math.log2(num_participants))
        num_byes = tournament_size - num_participants
        
        # Seed participants
        if seeding_method == "seeded":
            seeded_participants = sorted(participants, key=lambda x: x.get('seed') or 999)
        elif seeding_method == "random":
            seeded_participants = participants.copy()
            random.shuffle(seeded_participants)
        else:
            seeded_participants = participants
        
        # Add bye players
        for i in range(num_byes):
            seeded_participants.insert(i * 2 + 1, {"is_bye": True, "id": f"bye_{i}"})
        
        bracket = []
        round_num = 1
        total_rounds = int(math.log2(tournament_size))
        
        # First round matchups
        match_num = 1
        for i in range(0, len(seeded_participants), 2):
            p1 = seeded_participants[i]
            p2 = seeded_participants[i + 1] if i + 1 < len(seeded_participants) else {"is_bye": True}
            
            bracket_node = {
                "id": str(uuid.uuid4()),
                "round": round_num,
                "match_number": match_num,
                "position": "upper",
                "participant1_id": p1.get("id") if not p1.get("is_bye") else None,
                "participant2_id": p2.get("id") if not p2.get("is_bye") else None,
                "winner_id": None,
                "next_match_id": None,
                "is_bye": p1.get("is_bye") or p2.get("is_bye")
            }
            
            # Auto-advance if bye
            if p1.get("is_bye") and not p2.get("is_bye"):
                bracket_node["winner_id"] = p2.get("id")
            elif p2.get("is_bye") and not p1.get("is_bye"):
                bracket_node["winner_id"] = p1.get("id")
            
            bracket.append(bracket_node)
            match_num += 1
        
        # Create subsequent rounds
        current_round_matches = bracket.copy()
        for round_num in range(2, total_rounds + 1):
            next_round_matches = []
            match_num = 1
            
            for i in range(0, len(current_round_matches), 2):
                match1 = current_round_matches[i]
                match2 = current_round_matches[i + 1] if i + 1 < len(current_round_matches) else None
                
                next_match = {
                    "id": str(uuid.uuid4()),
                    "round": round_num,
                    "match_number": match_num,
                    "position": "final" if round_num == total_rounds else "upper",
                    "participant1_id": None,
                    "participant2_id": None,
                    "winner_id": None,
                    "next_match_id": None,
                    "is_bye": False
                }
                
                # Link previous matches to this one
                match1["next_match_id"] = next_match["id"]
                if match2:
                    match2["next_match_id"] = next_match["id"]
                
                next_round_matches.append(next_match)
                match_num += 1
                bracket.append(next_match)
            
            current_round_matches = next_round_matches
        
        return bracket
    
    @staticmethod
    def generate_double_elimination_bracket(participants: List[Dict], seeding_method: str = "random") -> List[Dict]:
        """
        Generate double elimination bracket (upper and lower brackets)
        """
        # Similar to single elimination but with loser's bracket
        # This is complex, implementing basic version
        
        bracket = TournamentService.generate_single_elimination_bracket(participants, seeding_method)
        
        # Add lower bracket structure
        # Winners continue in upper, losers drop to lower
        # Implementation simplified for now
        
        return bracket
    
    @staticmethod
    def generate_round_robin_schedule(participants: List[Dict], rounds: int = 2) -> List[Dict]:
        """
        Generate round-robin schedule (everyone plays everyone)
        rounds: 1 for single round-robin, 2 for double (home & away)
        """
        num_participants = len(participants)
        matches = []
        
        # Round-robin algorithm (circle method)
        for round_num in range(rounds):
            for i in range(num_participants):
                for j in range(i + 1, num_participants):
                    match = {
                        "id": str(uuid.uuid4()),
                        "round": round_num + 1,
                        "match_number": len(matches) + 1,
                        "match_type": "group",
                        "participant1_id": participants[i]["id"] if round_num == 0 else participants[j]["id"],
                        "participant2_id": participants[j]["id"] if round_num == 0 else participants[i]["id"],
                        "status": "scheduled",
                        "group_name": None
                    }
                    matches.append(match)
        
        return matches
    
    @staticmethod
    def generate_group_stage_schedule(participants: List[Dict], num_groups: int) -> Tuple[Dict[str, List[Dict]], List[Dict]]:
        """
        Generate group stage with multiple groups
        Returns: (groups_dict, all_matches)
        """
        # Distribute participants into groups
        groups = {}
        group_names = [chr(65 + i) for i in range(num_groups)]  # A, B, C, D...
        
        participants_per_group = len(participants) // num_groups
        extra = len(participants) % num_groups
        
        start_idx = 0
        for i, group_name in enumerate(group_names):
            group_size = participants_per_group + (1 if i < extra else 0)
            groups[f"Group {group_name}"] = participants[start_idx:start_idx + group_size]
            start_idx += group_size
        
        # Generate round-robin within each group
        all_matches = []
        for group_name, group_participants in groups.items():
            group_matches = TournamentService.generate_round_robin_schedule(group_participants, rounds=1)
            for match in group_matches:
                match["group_name"] = group_name
                all_matches.append(match)
        
        return groups, all_matches
    
    @staticmethod
    def generate_swiss_system_round(participants: List[Dict], current_standings: List[Dict], round_num: int) -> List[Dict]:
        """
        Generate matchups for Swiss system tournament
        Pairs players with similar scores
        """
        # Sort by points/wins
        sorted_participants = sorted(participants, key=lambda x: current_standings.get(x["id"], {}).get("points", 0), reverse=True)
        
        matches = []
        used = set()
        
        match_num = 1
        for i, p1 in enumerate(sorted_participants):
            if p1["id"] in used:
                continue
            
            # Find best opponent with similar score
            for j in range(i + 1, len(sorted_participants)):
                p2 = sorted_participants[j]
                if p2["id"] not in used:
                    match = {
                        "id": str(uuid.uuid4()),
                        "round": round_num,
                        "match_number": match_num,
                        "match_type": "swiss",
                        "participant1_id": p1["id"],
                        "participant2_id": p2["id"],
                        "status": "scheduled"
                    }
                    matches.append(match)
                    used.add(p1["id"])
                    used.add(p2["id"])
                    match_num += 1
                    break
        
        return matches
    
    @staticmethod
    def assign_matches_to_schedule(matches: List[Dict], available_slots: List[Dict], fields: List[Dict]) -> List[Dict]:
        """
        Assign matches to time slots and fields
        Returns updated matches with schedule info
        """
        scheduled_matches = []
        slot_idx = 0
        field_idx = 0
        
        for match in matches:
            if slot_idx >= len(available_slots):
                # No more slots available
                match["scheduled_datetime"] = None
                match["field_id"] = None
                scheduled_matches.append(match)
                continue
            
            slot = available_slots[slot_idx]
            field = fields[field_idx] if fields else None
            
            match["scheduled_date"] = slot["date"]
            match["scheduled_time"] = slot["time"]
            match["field_id"] = field["id"] if field else None
            match["field_name"] = field["name"] if field else None
            
            scheduled_matches.append(match)
            
            # Move to next field, or next slot if all fields used
            field_idx += 1
            if field_idx >= len(fields):
                field_idx = 0
                slot_idx += 1
        
        return scheduled_matches
    
    @staticmethod
    def calculate_standings(matches: List[Dict], participants: List[Dict], scoring_system: Dict[str, int]) -> List[Dict]:
        """
        Calculate standings from match results
        scoring_system: {"win": 3, "draw": 1, "loss": 0}
        """
        standings = {}
        
        # Initialize standings
        for participant in participants:
            standings[participant["id"]] = {
                "participant_id": participant["id"],
                "participant_name": participant.get("full_name", "Unknown"),
                "matches_played": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "points": 0,
                "goals_for": 0,
                "goals_against": 0,
                "goal_difference": 0,
                "form": []
            }
        
        # Process completed matches
        for match in matches:
            if match["status"] != "completed" or not match.get("winner_id"):
                continue
            
            p1_id = match["participant1_id"]
            p2_id = match["participant2_id"]
            
            if not p1_id or not p2_id:
                continue
            
            p1_score = match.get("score_participant1", 0)
            p2_score = match.get("score_participant2", 0)
            
            # Update statistics
            standings[p1_id]["matches_played"] += 1
            standings[p2_id]["matches_played"] += 1
            
            standings[p1_id]["goals_for"] += p1_score
            standings[p1_id]["goals_against"] += p2_score
            standings[p2_id]["goals_for"] += p2_score
            standings[p2_id]["goals_against"] += p1_score
            
            # Determine result
            if p1_score > p2_score:
                standings[p1_id]["wins"] += 1
                standings[p1_id]["points"] += scoring_system.get("win", 3)
                standings[p1_id]["form"].append("W")
                
                standings[p2_id]["losses"] += 1
                standings[p2_id]["points"] += scoring_system.get("loss", 0)
                standings[p2_id]["form"].append("L")
            elif p1_score < p2_score:
                standings[p2_id]["wins"] += 1
                standings[p2_id]["points"] += scoring_system.get("win", 3)
                standings[p2_id]["form"].append("W")
                
                standings[p1_id]["losses"] += 1
                standings[p1_id]["points"] += scoring_system.get("loss", 0)
                standings[p1_id]["form"].append("L")
            else:
                standings[p1_id]["draws"] += 1
                standings[p1_id]["points"] += scoring_system.get("draw", 1)
                standings[p1_id]["form"].append("D")
                
                standings[p2_id]["draws"] += 1
                standings[p2_id]["points"] += scoring_system.get("draw", 1)
                standings[p2_id]["form"].append("D")
        
        # Calculate goal difference and keep last 5 form
        for standing in standings.values():
            standing["goal_difference"] = standing["goals_for"] - standing["goals_against"]
            standing["form"] = standing["form"][-5:]  # Last 5 matches
        
        # Sort by points, then goal difference, then goals for
        sorted_standings = sorted(
            standings.values(),
            key=lambda x: (x["points"], x["goal_difference"], x["goals_for"]),
            reverse=True
        )
        
        # Assign ranks
        for i, standing in enumerate(sorted_standings):
            standing["rank"] = i + 1
            standing["id"] = str(uuid.uuid4())
        
        return sorted_standings
    
    @staticmethod
    def update_bracket_after_match(bracket: List[Dict], completed_match_id: str, winner_id: str) -> List[Dict]:
        """
        Update bracket when a match is completed
        Advance winner to next round
        """
        # Find the completed match
        completed_match = None
        for node in bracket:
            if node["id"] == completed_match_id:
                completed_match = node
                node["winner_id"] = winner_id
                break
        
        if not completed_match or not completed_match.get("next_match_id"):
            return bracket
        
        # Find next match and update participant
        next_match_id = completed_match["next_match_id"]
        for node in bracket:
            if node["id"] == next_match_id:
                if node["participant1_id"] is None:
                    node["participant1_id"] = winner_id
                elif node["participant2_id"] is None:
                    node["participant2_id"] = winner_id
                break
        
        return bracket

    @staticmethod
    def auto_assign_seeding(participants: List[Dict], event_data: Dict) -> List[Dict]:
        """
        Automatically assign seeding based on participant skill levels
        - Only assigns seeds if not already set
        - Professional players → Seed 1 tier
        - Advanced players → Seed 2 tier
        - Others → Seed 3+ tier (by order)
        """
        # Categorize by skill level
        professionals = []
        advanced = []
        others = []
        
        for participant in participants:
            # Skip if seed already assigned
            if participant.get('seed') is not None:
                continue
                
            skill = (participant.get('skill_level') or '').lower()
            if skill == 'professional' or skill == 'profesyonel':
                professionals.append(participant)
            elif skill == 'advanced' or skill == 'ileri' or skill == 'i̇leri':
                advanced.append(participant)
            else:
                others.append(participant)
        
        # Assign seeds: Professionals get 1, Advanced get 2, Others get 3+
        current_seed = 1
        
        # Assign seed 1 to all professionals
        for participant in professionals:
            participant['seed'] = 1
        
        # Assign seed 2 to all advanced players
        for participant in advanced:
            participant['seed'] = 2
        
        # Assign seed 3+ to others
        seed_for_others = 3
        for participant in others:
            participant['seed'] = seed_for_others
            seed_for_others += 1
        
        return participants
    
    @staticmethod
    def auto_create_groups(participants: List[Dict], event_data: Dict, num_groups: Optional[int] = None) -> Dict[str, List[Dict]]:
        """
        Automatically create groups based on age, gender, and skill level
        Returns dict of group_name -> List[participants]
        """
        groups = {}
        
        # Get event criteria
        age_groups = event_data.get('age_groups') or []
        gender_restriction = event_data.get('gender_restriction')
        enable_age_groups = len(age_groups) > 0
        
        if enable_age_groups and age_groups:
            # Group by age categories
            for age_group in age_groups:
                groups[age_group] = []
            
            # Assign participants to age groups
            for participant in participants:
                age = participant.get('age')
                if not age:
                    # Default group if no age
                    if 'Açık' not in groups:
                        groups['Açık'] = []
                    groups['Açık'].append(participant)
                    participant['group_name'] = 'Açık'
                    continue
                
                # Match to age group
                assigned = False
                if age < 12:
                    if 'Minik' in groups:
                        groups['Minik'].append(participant)
                        participant['group_name'] = 'Minik'
                        assigned = True
                elif age < 14:
                    if 'Küçük' in groups:
                        groups['Küçük'].append(participant)
                        participant['group_name'] = 'Küçük'
                        assigned = True
                elif age < 18:
                    if 'Genç' in groups:
                        groups['Genç'].append(participant)
                        participant['group_name'] = 'Genç'
                        assigned = True
                elif age < 35:
                    if 'Büyük' in groups:
                        groups['Büyük'].append(participant)
                        participant['group_name'] = 'Büyük'
                        assigned = True
                else:
                    if 'Veteran' in groups:
                        groups['Veteran'].append(participant)
                        participant['group_name'] = 'Veteran'
                        assigned = True
                
                if not assigned:
                    # Default to Açık if specific group not found
                    if 'Açık' not in groups:
                        groups['Açık'] = []
                    groups['Açık'].append(participant)
                    participant['group_name'] = 'Açık'
        
        elif gender_restriction:
            # Group by gender
            groups = {
                'Erkek': [],
                'Kadın': []
            }
            
            for participant in participants:
                gender = participant.get('gender', 'male')
                if gender == 'female':
                    groups['Kadın'].append(participant)
                    participant['group_name'] = 'Kadın'
                else:
                    groups['Erkek'].append(participant)
                    participant['group_name'] = 'Erkek'
        
        elif num_groups and num_groups > 1:
            # Create balanced groups (A, B, C, etc.)
            group_names = [chr(65 + i) for i in range(num_groups)]  # A, B, C...
            for name in group_names:
                groups[f'Grup {name}'] = []
            
            # Distribute participants evenly
            for idx, participant in enumerate(participants):
                group_idx = idx % num_groups
                group_name = f'Grup {group_names[group_idx]}'
                groups[group_name].append(participant)
                participant['group_name'] = group_name
        
        else:
            # Single group - everyone together
            groups['Açık'] = participants
            for participant in participants:
                participant['group_name'] = 'Açık'
        
        # Remove empty groups
        groups = {k: v for k, v in groups.items() if len(v) > 0}
        
        return groups
    
    @staticmethod
    def identify_bye_participants(participants: List[Dict], tournament_size: Optional[int] = None) -> List[str]:
        """
        Identify which participants should get byes in the first round
        Returns list of participant IDs who get byes
        Typically lowest seeds get byes
        """
        num_participants = len(participants)
        
        if not tournament_size:
            # Calculate next power of 2
            tournament_size = 2 ** math.ceil(math.log2(num_participants))
        
        num_byes = tournament_size - num_participants
        
        if num_byes <= 0:
            return []
        
        # Sort by seed (best seeds get byes)
        sorted_participants = sorted(
            participants,
            key=lambda x: x.get('seed', 999)
        )
        
        # Top seeds get byes
        bye_participants = [p['user_id'] for p in sorted_participants[:num_byes]]
        
        # Mark participants as having byes
        for participant in participants:
            if participant['user_id'] in bye_participants:
                participant['is_bye'] = True
        
        return bye_participants
