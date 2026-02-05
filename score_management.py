"""Score management service for match score proposals and confirmations"""
from typing import List, Dict, Optional
from datetime import datetime
import uuid

class ScoreManagementService:
    @staticmethod
    def can_submit_score(user_id: str, match: Dict, event: Dict, tournament: Dict) -> tuple[bool, str]:
        """
        Check if user can submit/edit score
        Returns: (can_submit: bool, reason: str)
        """
        # Event organizer
        if event.get("organizer_id") == user_id:
            return True, "organizer"
        
        # Event managers (yöneticiler)
        if user_id in event.get("managers", []):
            return True, "manager"
        
        # Event assistants (asistanlar)
        if user_id in event.get("assistants", []):
            return True, "assistant"
        
        # Event organizers list
        if user_id in event.get("organizers", []):
            return True, "organizer"
        
        # Admin users can always submit scores
        # (This is checked by user_type in the endpoint, but we can add it here too)
        
        # Tournament organizer
        if tournament.get("organizer_id") == user_id:
            return True, "organizer"
        
        # Match referee
        if match.get("referee_id") == user_id:
            return True, "referee"
        
        # Participants - check both player_id and participant_id fields
        # Also need to check user_id of participants since match stores participant IDs
        participant1_id = match.get("player1_id") or match.get("participant1_id")
        participant2_id = match.get("player2_id") or match.get("participant2_id")
        
        # Direct ID match
        if user_id in [participant1_id, participant2_id]:
            return True, "participant"
        
        # Check if user_id matches any participant's user_id
        participants = tournament.get("participants", [])
        for participant in participants:
            if participant.get("user_id") == user_id:
                # Check if this participant is in the match
                if participant.get("id") in [participant1_id, participant2_id]:
                    return True, "participant"
        
        return False, "not_authorized"
    
    @staticmethod
    def needs_confirmation(submitted_by: str, match: Dict) -> bool:
        """
        Check if score needs confirmation from others
        Referee can confirm alone, participants need confirmation
        """
        # If submitted by referee, no confirmation needed
        if match.get("referee_id") == submitted_by:
            return False
        
        # If submitted by participant, needs confirmation
        return True
    
    @staticmethod
    def who_needs_to_confirm(proposed_by: str, match: Dict, tournament: Dict = None) -> List[str]:
        """
        Get list of user IDs who need to confirm the score
        """
        user_ids = []
        
        # Add referee if exists
        if match.get("referee_id"):
            user_ids.append(match.get("referee_id"))
        
        # Add other participant - check both player_id and participant_id fields
        participant1_id = match.get("player1_id") or match.get("participant1_id")
        participant2_id = match.get("player2_id") or match.get("participant2_id")
        
        # Need to get user_ids from participant records if tournament is provided
        if tournament:
            participants = tournament.get("participants", [])
            for participant in participants:
                p_id = participant.get("id")
                u_id = participant.get("user_id")
                
                # If this participant is in the match and didn't propose
                if p_id in [participant1_id, participant2_id] and u_id != proposed_by:
                    user_ids.append(u_id)
        else:
            # Fallback to direct IDs
            if participant1_id and participant1_id != proposed_by:
                user_ids.append(participant1_id)
            if participant2_id and participant2_id != proposed_by:
                user_ids.append(participant2_id)
        
        return user_ids
    
    @staticmethod
    def can_confirm_score(user_id: str, proposed_by: str, match: Dict, tournament: Dict = None) -> bool:
        """
        Check if user can confirm a score proposal
        """
        # Can't confirm own proposal
        if user_id == proposed_by:
            return False
        
        # Referee can confirm
        if match.get("referee_id") == user_id:
            return True
        
        # Other participant can confirm - check both player_id and participant_id fields
        participant1_id = match.get("player1_id") or match.get("participant1_id")
        participant2_id = match.get("player2_id") or match.get("participant2_id")
        
        # Direct ID match
        if user_id in [participant1_id, participant2_id]:
            return True
        
        # Check via participant records if tournament is provided
        if tournament:
            participants = tournament.get("participants", [])
            for participant in participants:
                if participant.get("user_id") == user_id:
                    # Check if this participant is in the match
                    if participant.get("id") in [participant1_id, participant2_id]:
                        return True
        
        return False
