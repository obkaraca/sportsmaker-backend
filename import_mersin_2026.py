import asyncio
import motor.motor_asyncio
import uuid
from datetime import datetime
import random
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")

# Mersin 2026 Oyuncu verileri
# Format: Ad Soyad | Doğum Yılı | Cinsiyet (K/E) | Yaş Kategorisi | Şehir | Çift Eş | Karışık Çift Eş
RAW_DATA = """Mediha Öztürk	1994	K	30	Mersin	Aliye Işıklı	Serdar Süha Taş
Özlem Doğan	1991	K	30	Gaziantep		
Seçil Öngel	1990	K	30	Antalya	Buğra Kurumak	Çağrı Öcal
Seda Altuntaş	1993	K	30	Kocaeli	Sibel Çullu Tekin	Mustafa Demir
Derya Güzelbey	1979	K	40	Gaziantep		
Dilek Özay	1982	K	40	Antalya	Nadigül Güdül	
Burcu D. Karadayı	1977	K	40	Ankara		Hakan Gökçayır
Burcu Koçyiğit	1980	K	40	Adana	Haslet Gemici	Noyan Yalçınöz
Haslet Gemici	1983	K	40	Antalya	Burcu Koçyiğit	Kaan Aras
Hülya Sarsıcı	1978	K	40	Bursa	Funda Songelen	Erdoğan Sarsıcı
Nadigül Güdül	1978	K	40	Bursa	Dilek Özay	
Sibel Çullu Tekin	1978	K	40	Osmaniye	Seda Altuntaş	Efkan Evkuran
Aliye Işıklı	1974	K	50	Mersin	Mediha Öztürk	Enis Kara
Ayfer Boğa	1967	K	50	Mersin	Ayşe Can Tuna	Mehmet S.Kırmızıtaş
Ayşe Selda Orhon	1967	K	50	KKTC	Derya Gürel Kaya	Zeki Selin
Betül Tan	1976	K	50	Mersin	Yeşim Akdeniz	Nevzat Bozkurt
Buğra Kurumak	1974	K	50	Mersin	Seçil Öngel	
Değer Baysal	1968	K	50	KKTC	Fulya Diker	Fadıl Olguner
Derya Gürel Kaya	1975	K	50	Kırıkkale	Ayşe Selda Orhon	Koray Er
Filiz Alkiraz	1972	K	50	Antalya	İsmet Yağar	Gültekin Alkiraz
Fulya Diker	1966	K	50	İstanbul	Değer Baysal	
Funda Songelen	1975	K	50	İzmir	Hülya Sarsıcı	Öner Özer
Neslihan Öner	1971	K	50	Mersin		Mustafa Asparuk
Nurcan Ay	1970	K	50	Antalya	Olga Shynkarova	
Olga Shynkarova	1974	K	50	Giresun	Nurcan Ay	Fatih Üstünçelik
Aydan Demir	1966	K	60	İstanbul	Elife Sağ	Serdar Yıldırım
Ayşe Can Tuna	1962	K	60	Ankara	Ayfer Boğa	Yusuf Tuna
Elife Sağ	1956	K	60	Adana	Aydan Demir	Hasan Basri Saygı
İsmet Yağar	1961	K	60	Adana	Filiz Alkiraz	Seçkin Öngel
Yeşim Akdeniz	1964	K	60	İstanbul	Betül Tan	Rubil Gündüz
Çağrı Öcal	1994	E	30	Mersin	Mehmet S.Kırmızıtaş	Seçil Öngel
Dursun Erduran	1992	E	30	Kırıkkale	Mustafa Türkyılmaz	
Efkan Evkuran	1992	E	30	İstanbul	Salih Geçgil	Sibel Çullu Tekin
Emre Şahap	1994	E	30	Şanlıurfa	İsmail Gökhan	
Enes Tetik	1990	E	30	Mersin	Feti Tetik	
Farkhad Bikmuratov	1993	E	30	Antalya	Maksim Samorai	
Hakan Gökçayır	1987	E	30	Ankara		Burcu D. Karadayı
Hamza Çalışkan	1994	E	30	Konya		
Hasan Erdoğan	1995	E	30	Mersin	Bünyamin Kutluca	
Hasan Timurtürkan	1992	E	30	Şanlıurfa		
İhsan Egemen Reis	1986	E	30	Adana	Cemil Özmaden	
Kerim Dovan	1987	E	30	Mersin	Enis Kara	
Mahmut Kuzgun	1992	E	30	Sivas	Mehmet Zahit Yuvacı	
Maksim Samorai	1982	E	30	Ukrayna	Farkhad Bikmuratov	
Mehmet S.Kırmızıtaş	1991	E	30	Mersin	Çağrı Öcal	Ayfer Boğa
Murat Yıldırım	1989	E	30	Gaziantep	Suat Gür	
Mustafa Demir	1995	E	30	Kahramanmaraş	Nebi Kürtül	Seda Altuntaş
Mustafa Türkyılmaz	1988	E	30	Kırıkkale	Dursun Erduran	
Nevzat Bozkurt	1987	E	30	Bursa	Fatih Yüzer	Betül Tan
Salih Geçgil	1989	E	30	Ankara	Efkan Evkuran	
Suat Gür	1995	E	30	Mersin	Murat Yıldırım	
Talha Kırca	1995	E	30	Karaman	Volkan Acembekiroğlu	
Adnan Tetik	1978	E	40	Mersin	Gürsel Tataş	
Ahmet Nadıç	1981	E	40	Mersin	Erkan Demirtaş	
Ali Hakan Kılıç	1985	E	40	Mersin	Kemal Şener	
Atilla Uğur Perşembe	1986	E	40	Mersin	Gökhan Kınaş	
Ayhan Karpuzcu	1978	E	40	Şanlıurfa	Mustafa Çopur	
Barış Özek	1980	E	40	İzmir	Özgür Barış Karaca	
Barış Uğur	1983	E	40	Ankara	Serdar Yıldırım	
Bayram Akçay	1981	E	40	Diyarbakır		
Cemil Özmaden	1977	E	40	Adana	İhsan Egemen Reis	
Doğan Karakaş	1980	E	40	Mersin	Selçuk Yeşil	
Emrah Tümkaya	1980	E	40	Hatay		
Engin Yazıtaş	1981	E	40	Muğla	Gökmen Kasımoğulları	
Enis Kara	1981	E	40	Mersin	Kerim Dovan	Aliye Işıklı
Erdal Ördek	1981	E	40	Hatay		
Erdoğan Sarsıcı	1975	E	40	Bursa		Hülya Sarsıcı
Erkan Demirtaş	1980	E	40	Mersin	Ahmet Nadıç	
Ersoy Önemli	1980	E	40	Ankara	Nihat Kayalı	
Fatih Bakırcı	1976	E	40	İzmir	Adil Karasoy	
Fatih Yüzer	1981	E	40	Gaziantep	Nevzat Bozkurt	
Gökmen Kasımoğulları	1977	E	40	Muğla	Engin Yazıtaş	
Gökhan Kınaş	1983	E	40	Mersin	Atilla Perşembe	
Hakan Koç	1984	E	40	Mersin	Kaan Aras	
Haydar Kahraman	1979	E	40	Ankara	Zafer Aşık	
Hulusi Alkaç	1983	E	40	Diyarbakır	Nurullah Ay	
İsa Eren	1974	E	40	Isparta	Özgür Koşkan	
İsmail Gökhan	1982	E	40	Şanlıurfa	Emre Şahap	
Mahmut Ateş	1979	E	40	Ankara	Rubil Gündüz	
Mahmut Özdemir	1981	E	40	Şanlıurfa	Mehmet Altun	
Mehmet Altun	1981	E	40	Şanlıurfa	Mahmut Özdemir	
Mehmet Erkul	1979	E	40	Mersin	Sergei Koval	
Mehmet Zahit Yuvacı	1983	E	40	Sivas	Mahmut Kuzgun	
Mukadder Altıntaş	1980	E	40	Aksaray	Serdar Ölçek	
Mustafa Okur	1986	E	40	Diyarbakır	Cuma Akıncı	
Mustafa Çopur	1978	E	40	Mersin	Ayhan Karpuzcu	
Nurullah Ay	1979	E	40	Diyarbakır	Hulusi Alkaç	
Osman Aytekin	1978	E	40	Aksaray	Mustafa Ateş	
Özkan Çarpazlı	1976	E	40	Mersin	Şakir Yetişen	
Ramazan Kaptanlıoğlu	1984	E	40	Kahramanmaraş	Selçuk Kurt	
Rubil Gündüz	1980	E	40	İstanbul	Mahmut Ateş	Yeşim Akdeniz
Saip Bülent Yaşar	1979	E	40	Ankara		
Samir Cazba	1982	E	40	Gaziantep	Reşit Gökoğlu	
Sedat Göksu	1983	E	40	Hatay		
Selçuk Kurt	1985	E	40	Kahramanmaraş	Ramazan Kaptanlıoğlu	
Selçuk Yeşil	1977	E	40	Mersin	Doğan Karakaş	
Serdar Ölçek	1977	E	40	Aksaray	Mukadder Altıntaş	
Sergeii Koval	1976	E	40	Ukrayna	Mehmet Erkul	
Serhat Mut	1981	E	40	Mersin	Şevki Tom	
Volkan Acembekiroğlu	1980	E	40	Adana	Talha Kırca	
Adil Karasoy	1969	E	50	Antalya	Fatih Bakırcı	
Adnan Göçer	1967	E	50	Adana		
Ahmet Çulha	1975	E	50	Sivas		
Ali İhsan Yener	1971	E	50	Konya		
Ali Kıcalı	1968	E	50	Konya		
Ali Tayfun Sarıkaya	1969	E	50	Samsun		
Ali Yücel	1969	E	50	Adana	Satılmış Agatay	
Atilla Kurucan	1970	E	50	Ankara		
Ata Durmuş	1969	E	50	Mersin	Öner Özer	
Atilla Saltık	1973	E	50	Mersin	Suat Güven	
Aziz Elhasoğlu	1969	E	50	Adana	Levent Ali Gürdil	
Bayram Akça	1974	E	50	Kayseri	Metin Sarıalp	
Cuma Akıncı	1970	E	50	Diyarbakır	Mustafa Okur	
Durmuş Ali Eryavuz	1975	E	50	Aksaray	Yakup Gültekin	
Fatih Üstünçelik	1973	E	50	Adana	Hasan Basri Saygı	Olga Shynkarova
Ferdai Alan	1970	E	50	Antalya		
Gültekin Alkiraz	1968	E	50	Antalya		Filiz Alkiraz
Gürsel Tataş	1973	E	50	Mersin	Adnan Tetik	
Halil Sağdıçoğlu	1973	E	50	Şanlıurfa		
Halit Akbaş	1972	E	50	Şanlıurfa	Halil Doğangül	
İhab Hariri	1966	E	50	IRAK	İmadettin Mardini	
Kaan Aras	1969	E	50	Antalya	Hakan Koç	Haslet Gemici
Kemal Ekinci	1968	E	50	Konya		
Kemal Şener	1976	E	50	Mersin	Ali Hakan Kılıç	
Kemal Turan	1974	E	50	Adana		
Koray Er	1974	E	50	Ankara	Serdar Süha Taş	Derya Gürel Kaya
Levent Ali Gürdil	1970	E	50	Adana		
Halil Dogangul	1968	E	50	Gaziantep	Halit Akbaş	
Hüseyin Şirin	1971	E	50	Adana		
Mehmet Ali Kabul	1974	E	50	Mersin	Süleyman Tellioğlu	
Mehmet Ali Özer	1975	E	50	Adana	Tekin Doğan	
Mehmet Kirişci	1970	E	50	Kahramanmaraş	Selçuk Paksoy	
Mustafa Ateş	1969	E	50	Aksaray	Osman Aytekin	
Nebi Kürtül	1967	E	50	Kahramanmaraş	Mustafa Demir	
Nihat Kayalı	1977	E	50	Ankara	Ersoy Önemli	
Önder Albayrak	1974	E	50	Mersin	Seçkin Öngel	
Öner Özer	1971	E	50	Mersin	Ata Durmuş	Funda Songelen
Özgür Barış Karaca	1974	E	50	Ankara	Barış Özek	
Özgür Koşkan	1974	E	50	Isparta	İsa Eren	
Reşit Gökoğlu	1976	E	50	Gaziantep	Samir Cazba	
Selçuk Paksoy	1970	E	50	Kahramanmaraş	Mehmet Kirişçi	
Suat Güven	1969	E	50	Mersin	Atilla Saltık	
Süleyman Tellioğlu	1976	E	50	Mersin	Mehmet Ali Kabul	
Serdar Süha Taş	1968	E	50	Mersin	Koray Er	Mediha Öztürk
Serdar Yıldırım	1972	E	50	İstanbul	Barış Uğur	Aydan Demir
Şakir Yetişen	1968	E	50	Antalya	Özkan Çarpazlı	
Şevki Tom	1969	E	50	Mersin	Serhat Mut	
Tekin Doğan	1971	E	50	Adana	Mehmet Ali Özer	
Yakup Gültekin	1983	E	50	Aksaray	Durmuş Ali Eryavuz	
Zafer Aşık	1975	E	50	Ankara	Haydar Kahraman	
Ahmet Kurt	1966	E	60	Adana	Yaşar Yücel	
Ahmet Şahan	1962	E	60	Muğla	Turgay Albayrak	
Bülent Süha Özmen	1963	E	60	Antalya	Fatih Yenisolak	
Cavit Yılmaz	1962	E	60	Ankara	Kubilay Akaydın	
Fatih Yenisolak	1965	E	60	Kahramanmaraş	Bülent Süha Özmen	
Feti Tetik	1965	E	60	Mersin	Enes Tetik	
Hasan Basri Saygı	1963	E	60	Adana	Fatih Üstünçelik	Elife Sağ
İmadettin Mardini	1966	E	60	İstanbul	İhab Hariri	
Metin Sarıalp	1962	E	60	Kayseri	Bayram Akça	
Mustafa Oymacı	1966	E	60	KKTC	Zeki Selin	
Rüstem Gökçe	1962	E	60	Adana	Muhsin Seçer	
Satılmış Agatay	1965	E	60	Mersin	Ali Yücel	
Seçkin Öngel	1964	E	60	Mersin	Önder Albayrak	İsmet Yağar
Selçukhan Şengüler	1964	E	60	Adana	Tamer Ağar	
Soner Doğan	1966	E	60	Osmaniye	Hasan Keskin	
Kubilay Akaydın	1962	E	60	Ankara	Cavit Yılmaz	
Yaşar Yücel	1966	E	60	Adana	Ahmet Kurt	
Yusuf Tuna	1962	E	60	Ankara	İsmail Hakkı Yiğit	Ayşe Can Tuna
Zeki Selin	1966	E	60	KKTC	Mustafa Oymacı	Ayşe Selda Orhon
Bilal Arslan	1961	E	65	Ankara		
Bilal San	1960	E	65	Ankara	İrfan Temiz	
Hasan Gündal	1959	E	65	Gaziantep	Oktai Ozturki	
İrfan Temiz	1960	E	65	Kırıkkale	Bilal San	
Noyan Yalçınöz	1960	E	65	Adana	Tümer Eren	Burcu Koçyiğit
Oktai Ozturki	1959	E	65	Gürcistan	Hasan Gündal	
Ramazan Orhan	1958	E	65	Mersin	Ural Erdal	
Tamer Ağar	1961	E	65	Adana	Selçukhan Şengüler	
Tümer Eren	1961	E	65	Adana	Noyan Yalçınöz	
İsmail Hakkı Yiğit	1960	E	65	Ankara	Yusuf Tuna	
Turgay Albayrak	1958	E	65	Antalya	Ahmet Şahan	
Ural Erdal	1958	E	65	Mersin	Ramazan Orhan	
Bektaş Aydoğan	1955	E	70	Muğla	Murat Sivrikaş	
Fadıl Olguner	1953	E	70	KKTC	Mustafa Asparuk	Değer Baysal
Ferit Atabey	1955	E	70	İstanbul	Filiz Özçelik	
Filiz Özçelik	1950	E	70	Ankara	Ferit Atabey	
Hasan Keskin	1956	E	70	Adana	Soner Doğan	
Murat Sivrikaş	1955	E	70	Antalya	Bektaş Aydoğan	
Müfit Üstüner	1956	E	70	Mersin	Şükrü Erkurt	
Muhsin Seçer	1949	E	70	Mersin	Rüstem Gökçe	
Kemal Sağ	1955	E	70	Adana	Süleyman Şimşek	
Rasim Eşme	1953	E	70	Mersin	Sacid Aker	
Sacid Aker	1956	E	70	Mersin	Rasim Eşme	
Süleyman Şimşek	1954	E	70	Mersin	Kemal Sağ	
Şükrü Erkurt	1955	E	70	Mersin	Müfit Üstüner	
Ahmet Özer	1938	E	75	Mersin	Can Bingöl	
Can Bingöl	1947	E	75	İstanbul	Ahmet Özer	
Mustafa Asparuk	1950	E	75	Mersin	Fadıl Olguner	Neslihan Öner"""

def parse_players():
    """Oyuncu verilerini parse et"""
    players = []
    for line in RAW_DATA.strip().split('\n'):
        parts = line.split('\t')
        if len(parts) >= 5:
            player = {
                'full_name': parts[0].strip(),
                'birth_year': int(parts[1].strip()),
                'gender': 'female' if parts[2].strip() == 'K' else 'male',
                'age_category': int(parts[3].strip()),
                'city': parts[4].strip(),
                'doubles_partner': parts[5].strip() if len(parts) > 5 and parts[5].strip() else None,
                'mixed_partner': parts[6].strip() if len(parts) > 6 and parts[6].strip() else None
            }
            players.append(player)
    return players

def turkish_to_ascii(text):
    """Türkçe karakterleri ASCII'ye dönüştür"""
    tr_chars = {'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
                'İ': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c'}
    for tr, en in tr_chars.items():
        text = text.replace(tr, en)
    return text

def generate_phone():
    """Rastgele telefon numarası üret"""
    return f"05{random.randint(30, 59)}{random.randint(1000000, 9999999)}"

def generate_email(name):
    """İsimden email oluştur"""
    name_parts = name.lower().split()
    ascii_name = turkish_to_ascii(''.join(name_parts))
    ascii_name = ''.join(c for c in ascii_name if c.isalnum())
    return f"{ascii_name}@mersin2026.com"

async def main():
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    # Backend sports_management kullanıyor
    db = client.sports_management
    
    print("=" * 60)
    print("🏓 MERSİN 2026 VETERAN MASA TENİSİ TURNUVASI - VERİ AKTARIMI")
    print("=" * 60)
    
    # 1. Önce etkinliği oluştur veya bul
    EVENT_TITLE = "Mersin 2026 Veteran Masa Tenisi Turnuvası"
    
    event = await db.events.find_one({"title": EVENT_TITLE})
    
    if not event:
        event_id = str(uuid.uuid4())
        event = {
            "id": event_id,
            "title": EVENT_TITLE,
            "description": "Mersin 2026 Veteran Masa Tenisi Turnuvası - Tüm yaş kategorilerinde tek, çift ve karışık çift müsabakaları",
            "sport": "Masa Tenisi",
            "event_type": "tournament",
            "city": "Mersin",
            "district": "Yenişehir",
            "address": "Mersin Spor Salonu",
            "start_date": "2026-06-01T09:00:00",
            "end_date": "2026-06-05T18:00:00",
            "registration_deadline": "2026-05-25T23:59:59",
            "max_participants": 300,
            "participant_count": 0,
            "participants": [],
            "game_types": ["tek", "cift", "karisik_cift"],
            "categories": [
                {"name": "Kadınlar 30", "gender": "female", "age_min": 30, "age_max": 39},
                {"name": "Kadınlar 40", "gender": "female", "age_min": 40, "age_max": 49},
                {"name": "Kadınlar 50", "gender": "female", "age_min": 50, "age_max": 59},
                {"name": "Kadınlar 60", "gender": "female", "age_min": 60, "age_max": 69},
                {"name": "Erkekler 30", "gender": "male", "age_min": 30, "age_max": 39},
                {"name": "Erkekler 40", "gender": "male", "age_min": 40, "age_max": 49},
                {"name": "Erkekler 50", "gender": "male", "age_min": 50, "age_max": 59},
                {"name": "Erkekler 60", "gender": "male", "age_min": 60, "age_max": 69},
                {"name": "Erkekler 65", "gender": "male", "age_min": 65, "age_max": 69},
                {"name": "Erkekler 70", "gender": "male", "age_min": 70, "age_max": 74},
                {"name": "Erkekler 75", "gender": "male", "age_min": 75, "age_max": 100}
            ],
            "status": "upcoming",
            "is_paid": False,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        await db.events.insert_one(event)
        print(f"✅ Etkinlik oluşturuldu: {EVENT_TITLE}")
        print(f"   ID: {event_id}")
    else:
        event_id = event["id"]
        print(f"✅ Mevcut etkinlik bulundu: {EVENT_TITLE}")
        print(f"   ID: {event_id}")
    
    # 2. Oyuncuları parse et
    players = parse_players()
    print(f"\n📋 Toplam {len(players)} oyuncu bulundu")
    
    # İstatistikler
    stats = {
        'users_created': 0,
        'users_existing': 0,
        'participations_created': 0,
        'participations_existing': 0,
        'tek_count': 0,
        'cift_count': 0,
        'karisik_count': 0
    }
    
    # 3. Her oyuncu için kullanıcı oluştur ve etkinliğe kaydet
    for i, player in enumerate(players, 1):
        full_name = player['full_name']
        email = generate_email(full_name)
        phone = generate_phone()
        
        # Doğum tarihini oluştur (yıl sabit, gün/ay rastgele)
        birth_month = random.randint(1, 12)
        birth_day = random.randint(1, 28)
        date_of_birth = f"{player['birth_year']}-{birth_month:02d}-{birth_day:02d}"
        
        # Kullanıcı var mı kontrol et
        existing_user = await db.users.find_one({"email": email})
        
        if existing_user:
            user_id = existing_user["id"]
            stats['users_existing'] += 1
        else:
            # Yeni kullanıcı oluştur
            user_id = str(uuid.uuid4())
            user = {
                "id": user_id,
                "email": email,
                "full_name": full_name,
                "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4DpT2gVJgH1mPwHm",  # Default: password123
                "user_type": "player",
                "gender": player['gender'],
                "city": player['city'],
                "phone": phone,
                "date_of_birth": date_of_birth,
                "player_profile": {
                    "skill_levels": {
                        "Masa Tenisi": "orta"
                    },
                    "preferred_sports": ["Masa Tenisi"],
                    "achievements": [],
                    "bio": f"Masa tenisi oyuncusu - Veteran {player['age_category']} kategorisi"
                },
                "is_verified": True,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            await db.users.insert_one(user)
            stats['users_created'] += 1
        
        # Oyun türlerini belirle
        game_types = ["tek"]  # Herkes tek'e katılıyor
        stats['tek_count'] += 1
        
        if player['doubles_partner']:
            game_types.append("cift")
            stats['cift_count'] += 1
            
        if player['mixed_partner']:
            game_types.append("karisik_cift")
            stats['karisik_count'] += 1
        
        # Kategori belirle
        gender_prefix = "Kadınlar" if player['gender'] == 'female' else "Erkekler"
        category = f"{gender_prefix} {player['age_category']}"
        
        # Etkinlik katılımı var mı kontrol et
        existing_participation = await db.event_participants.find_one({
            "event_id": event_id,
            "user_id": user_id
        })
        
        if existing_participation:
            stats['participations_existing'] += 1
        else:
            # Etkinliğe katılım kaydı oluştur
            participation = {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "user_id": user_id,
                "status": "confirmed",
                "registration_date": datetime.utcnow().isoformat(),
                "payment_status": "completed",
                "category": category,
                "game_types": game_types,
                "doubles_partner": player['doubles_partner'],
                "mixed_doubles_partner": player['mixed_partner'],
                "created_at": datetime.utcnow().isoformat()
            }
            await db.event_participants.insert_one(participation)
            stats['participations_created'] += 1
            
            # Event participants array'ine de ekle
            await db.events.update_one(
                {"id": event_id},
                {
                    "$addToSet": {"participants": user_id},
                    "$inc": {"participant_count": 1}
                }
            )
        
        # İlerleme göster
        if i % 20 == 0 or i == len(players):
            print(f"   İşlenen: {i}/{len(players)}")
    
    # 4. Sonuçları göster
    print("\n" + "=" * 60)
    print("📊 SONUÇ İSTATİSTİKLERİ")
    print("=" * 60)
    print(f"✅ Oluşturulan kullanıcı: {stats['users_created']}")
    print(f"⚠️  Mevcut kullanıcı: {stats['users_existing']}")
    print(f"✅ Oluşturulan katılım: {stats['participations_created']}")
    print(f"⚠️  Mevcut katılım: {stats['participations_existing']}")
    print(f"\n🏓 Oyun Türü Dağılımı:")
    print(f"   Tek: {stats['tek_count']}")
    print(f"   Çift: {stats['cift_count']}")
    print(f"   Karışık Çift: {stats['karisik_count']}")
    
    # 5. Final kontrol
    final_count = await db.event_participants.count_documents({"event_id": event_id})
    print(f"\n📈 Etkinlik toplam katılımcı: {final_count}")
    
    client.close()
    print("\n✅ İşlem tamamlandı!")

if __name__ == "__main__":
    asyncio.run(main())
