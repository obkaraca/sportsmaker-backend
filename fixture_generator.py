"""
Fikstür oluşturma algoritmaları
Farklı turnuva sistemleri için maç programı oluşturur
"""
import random
from typing import List, Dict
from datetime import datetime, timedelta
import math

class FixtureGenerator:
    
    @staticmethod
    def generate_single_elimination(participants: List[str]) -> List[Dict]:
        """
        Eleme Sistemi: Kaybeden elenir
        """
        matches = []
        num_participants = len(participants)
        
        # Katılımcı sayısını 2'nin kuvvetine tamamla
        next_power = 2 ** math.ceil(math.log2(num_participants))
        byes_needed = next_power - num_participants
        
        # Shuffle participants for randomization
        shuffled = participants.copy()
        random.shuffle(shuffled)
        
        # İlk tur
        round_num = 1
        match_num = 1
        
        # Bye'ları ayarla
        participants_in_round = shuffled.copy()
        
        # İlk turdaki maçlar
        for i in range(0, len(participants_in_round) - 1, 2):
            if i + 1 < len(participants_in_round):
                matches.append({
                    "round": round_num,
                    "match_number": match_num,
                    "participant1_id": participants_in_round[i],
                    "participant2_id": participants_in_round[i+1],
                    "bracket_position": "main"
                })
                match_num += 1
        
        # Sonraki turlar için placeholder maçlar oluştur
        total_rounds = math.ceil(math.log2(next_power))
        matches_per_round = next_power // 2
        
        for round_num in range(2, total_rounds + 1):
            matches_per_round = matches_per_round // 2
            for i in range(matches_per_round):
                matches.append({
                    "round": round_num,
                    "match_number": match_num,
                    "participant1_id": None,  # Önceki turun galibi
                    "participant2_id": None,  # Önceki turun galibi
                    "bracket_position": "main"
                })
                match_num += 1
        
        return matches
    
    @staticmethod
    def generate_double_elimination(participants: List[str]) -> List[Dict]:
        """
        Çift Eleme Sistemi: 2 kez kaybeden elenir
        """
        matches = []
        shuffled = participants.copy()
        random.shuffle(shuffled)
        
        # Üst bracket (winners bracket)
        upper_matches = FixtureGenerator.generate_single_elimination(shuffled)
        for match in upper_matches:
            match["bracket_position"] = "upper"
        
        matches.extend(upper_matches)
        
        # Alt bracket (losers bracket) - Placeholder
        num_upper_rounds = max([m["round"] for m in upper_matches])
        match_num = len(upper_matches) + 1
        
        for round_num in range(1, num_upper_rounds * 2):
            matches.append({
                "round": round_num,
                "match_number": match_num,
                "participant1_id": None,
                "participant2_id": None,
                "bracket_position": "lower"
            })
            match_num += 1
        
        # Final
        matches.append({
            "round": num_upper_rounds + 1,
            "match_number": match_num,
            "participant1_id": None,
            "participant2_id": None,
            "bracket_position": "final"
        })
        
        return matches
    
    @staticmethod
    def generate_round_robin(participants: List[str], double_round: bool = False) -> List[Dict]:
        """
        Lig Sistemi: Herkes herkesle oynar
        double_round=True: Çift maç (ev-deplasman)
        """
        matches = []
        n = len(participants)
        match_num = 1
        
        # Round-robin algoritması
        if n % 2 == 1:
            participants.append(None)  # Bye için
            n += 1
        
        for round_num in range(n - 1):
            for i in range(n // 2):
                p1 = participants[i]
                p2 = participants[n - 1 - i]
                
                if p1 is not None and p2 is not None:
                    matches.append({
                        "round": round_num + 1,
                        "match_number": match_num,
                        "participant1_id": p1,
                        "participant2_id": p2,
                        "bracket_position": "single" if not double_round else "first_leg"
                    })
                    match_num += 1
            
            # Rotate participants (pivot around first)
            participants = [participants[0]] + [participants[-1]] + participants[1:-1]
        
        # Çift maç için ters maçları ekle
        if double_round:
            first_leg_matches = matches.copy()
            for match in first_leg_matches:
                matches.append({
                    "round": match["round"] + (n - 1),
                    "match_number": match_num,
                    "participant1_id": match["participant2_id"],
                    "participant2_id": match["participant1_id"],
                    "bracket_position": "second_leg"
                })
                match_num += 1
        
        return matches
    
    @staticmethod
    def generate_swiss_system(participants: List[str], num_rounds: int = 5) -> List[Dict]:
        """
        İsviçre Sistemi: Benzer puanlı oyuncular eşleşir
        İlk tur için rastgele eşleşme, sonraki turlar puana göre
        """
        matches = []
        shuffled = participants.copy()
        random.shuffle(shuffled)
        
        match_num = 1
        
        # İlk tur - rastgele eşleştir
        for i in range(0, len(shuffled) - 1, 2):
            if i + 1 < len(shuffled):
                matches.append({
                    "round": 1,
                    "match_number": match_num,
                    "participant1_id": shuffled[i],
                    "participant2_id": shuffled[i+1],
                    "bracket_position": "swiss"
                })
                match_num += 1
        
        # Sonraki turlar için placeholder
        for round_num in range(2, num_rounds + 1):
            for i in range(len(participants) // 2):
                matches.append({
                    "round": round_num,
                    "match_number": match_num,
                    "participant1_id": None,  # Puana göre belirlenecek
                    "participant2_id": None,
                    "bracket_position": "swiss"
                })
                match_num += 1
        
        return matches
    
    @staticmethod
    def generate_group_stage(participants: List[str], group_size: int = 4) -> List[Dict]:
        """
        Grup + Eleme Sistemi: Önce gruplar, sonra eleme
        """
        matches = []
        num_groups = math.ceil(len(participants) / group_size)
        
        # Katılımcıları gruplara ayır
        shuffled = participants.copy()
        random.shuffle(shuffled)
        
        groups = []
        for i in range(num_groups):
            group = shuffled[i*group_size:(i+1)*group_size]
            groups.append(group)
        
        match_num = 1
        
        # Her grup için round-robin
        group_names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for idx, group in enumerate(groups):
            group_name = f"Grup {group_names[idx]}" if idx < len(group_names) else f"Grup {idx+1}"
            
            # Grup içi maçlar
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    matches.append({
                        "round": 1,  # Grup aşaması
                        "match_number": match_num,
                        "participant1_id": group[i],
                        "participant2_id": group[j],
                        "group_name": group_name,
                        "bracket_position": "group_stage"
                    })
                    match_num += 1
        
        # Eleme turu placeholder'ları
        # Grup birincileri için
        num_knockout_matches = num_groups // 2
        for i in range(num_knockout_matches):
            matches.append({
                "round": 2,  # Eleme turu
                "match_number": match_num,
                "participant1_id": None,
                "participant2_id": None,
                "bracket_position": "knockout"
            })
            match_num += 1
        
        return matches
