import requests
import uuid
import random

# API URL
API_URL = "http://localhost:8001/api"

# Oyuncu listesi
players_str = """Abdülkadir TAŞÇI, Alp KAYMAN, Burak KARATATAR, Alperen KUZU, Ersoy ÖNEMLİ, Özgür Barış KARACA, Mustafa CANDAN, Cihan ADLI, Coşkun KOCAGÖZ, Salih GEÇGİL, Duran BEYAZIT, Barış UĞUR, Bilal SAN, Muhammet Ali ŞAHİN, Berke Arda DÜNDAR, Soner KARTOP, Erol DENİZ, Ahmet YILDIZGÖZ, Zafer AŞIK, Kağan YURDAL, Serhat ÖZKILIÇ, Emre BALLI, Haydar ÇINAR, Hakan GÖKÇAYIR, Muhammet KARTAL, Soner CANTÜRK, Nihat KAYALI, Mesut ALPARSLAN, Uğur ÖZGÜRGİL, Cavit YILMAZ, Koray YAVAŞ, Ömer YETİLMİŞ, Haydar KAHRAMAN, İlhan GÜLTEKİN, Yusuf TUNA, Şeref COŞKUNYÜREK, Bülent YAŞAR, Murat ER, İsmail Hakkı YİĞİT, Hasan KARCİ, Adil Samet YALÇINKAYA, Hami KALKAN, Abdurrahman YAVUZ, Çağlar Mehmet ÇAĞLAYAN, Cuma YAVUZ, Cüneyt GÜRBÜZ, Erol ALGÜN, Ümit İPEK, Sungur DURAN, Muammer ÖZKORUL, Yiğit Mehmet UZEL, Kubilay AKAYDIN, Tuncay GÖK, Murathan SAYINALP, İsmail DOLU, Erkan KAYA, Fatih YILDIRIM, Ender ALPAGÜL, Halit JABBAR, Emin TUĞRUL, Oktay UNCU, Onur ATAOĞLU, İsmail CANLI, Suna GENÇOĞLU, Mesut BAYRAM, Serdal YÜKSEL, Engin Burak KOÇAK, Eray KILIÇ, İrem TOMAK, Metin Alp YURTSEVEN, Tayfun KAYABAŞI, Abdülbasit YAVUZ, Ömer AYVAZ, Tevfik Furkan PEKŞEN, Ersin ATLAS"""

# Kadın oyuncular (case insensitive)
female_players = ["İREM TOMAK", "SUNA GENÇOĞLU"]

# Planet Lig event ID
EVENT_ID = "1dbb0527-bbfa-4338-991b-7f9e5278377b"

def normalize_email(name):
    """İsmi email formatına çevir"""
    tr_map = {
        'ı': 'i', 'İ': 'i', 'ğ': 'g', 'Ğ': 'g',
        'ü': 'u', 'Ü': 'u', 'ş': 's', 'Ş': 's',
        'ö': 'o', 'Ö': 'o', 'ç': 'c', 'Ç': 'c'
    }
    result = name.lower()
    for tr_char, en_char in tr_map.items():
        result = result.replace(tr_char, en_char)
    return result.replace(' ', '')

def main():
    # Oyuncuları parse et
    players = [p.strip() for p in players_str.split(',') if p.strip()]
    print(f"Toplam {len(players)} oyuncu bulundu")
    
    created_users = []
    
    for i, player_name in enumerate(players):
        # İsim ve soyisim ayır
        parts = player_name.split()
        if len(parts) >= 2:
            first_name = ' '.join(parts[:-1])
            last_name = parts[-1]
        else:
            first_name = player_name
            last_name = ""
        
        full_name = player_name
        
        # Cinsiyet belirle
        is_female = any(f in player_name.upper() for f in female_players)
        gender = "female" if is_female else "male"
        
        # Seviye belirle (ilk 25 iyi, sonraki 25 orta-iyi, son 25 orta)
        if i < 25:
            skill_level = "iyi"
        elif i < 50:
            skill_level = "orta-iyi"
        else:
            skill_level = "orta"
        
        # Email oluştur
        email = f"{normalize_email(first_name)}.{normalize_email(last_name)}@planetlig.com"
        
        # Kullanıcı oluştur (register API)
        user_data = {
            "email": email,
            "password": "Planet2025!",
            "full_name": full_name,
            "user_type": "player",
            "gender": gender,
            "city": "Ankara",
            "phone": f"05{random.randint(300000000, 599999999)}",
            "date_of_birth": f"{random.randint(1970, 2000)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "player_profile": {
                "skill_levels": {
                    "Masa Tenisi": skill_level
                },
                "preferred_sports": ["Masa Tenisi"]
            }
        }
        
        # Kayıt ol
        resp = requests.post(f"{API_URL}/auth/register", json=user_data)
        
        if resp.status_code == 200:
            result = resp.json()
            user_id = result.get("user", {}).get("id")
            token = result.get("access_token")
            print(f"✅ Oluşturuldu: {full_name} ({gender}, {skill_level})")
            created_users.append({"id": user_id, "token": token, "name": full_name})
        else:
            # Kullanıcı zaten var, giriş yap
            login_resp = requests.post(f"{API_URL}/auth/login", json={"email": email, "password": "Planet2025!"})
            if login_resp.status_code == 200:
                result = login_resp.json()
                user_id = result.get("user", {}).get("id")
                token = result.get("access_token")
                print(f"⚠️ Zaten var: {full_name}")
                created_users.append({"id": user_id, "token": token, "name": full_name})
            else:
                print(f"❌ Giriş başarısız: {full_name} - {login_resp.text[:100]}")
    
    print(f"\n✅ Toplam {len(created_users)} oyuncu hazır")
    
    # Etkinliğe kaydet
    print(f"\n📝 Etkinliğe kayıt başlıyor: Planet Lig ({EVENT_ID})")
    
    for user in created_users:
        headers = {"Authorization": f"Bearer {user['token']}"}
        
        # Etkinliğe katıl
        join_data = {
            "category": "Open"
        }
        resp = requests.post(f"{API_URL}/events/{EVENT_ID}/join", json=join_data, headers=headers)
        
        if resp.status_code == 200:
            print(f"✅ Etkinliğe kaydedildi: {user['name']}")
        elif "already" in resp.text.lower() or "zaten" in resp.text.lower():
            print(f"⚠️ Zaten kayıtlı: {user['name']}")
        else:
            print(f"❌ Kayıt başarısız: {user['name']} - {resp.text[:100]}")
    
    print(f"\n✅ İşlem tamamlandı!")

if __name__ == "__main__":
    main()
