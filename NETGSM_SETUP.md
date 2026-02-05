# Netgsm SMS Entegrasyonu - Kurulum Rehberi

## 📱 Netgsm Nedir?

Netgsm, Türkiye'nin önde gelen SMS API sağlayıcılarından biridir. Sport Connect uygulamasında OTP (One-Time Password) kodlarını Türk kullanıcılara göndermek için kullanılır.

## 🚀 Kurulum Adımları

### 1. Netgsm Hesabı Oluşturun

1. https://www.netgsm.com.tr adresine gidin
2. "Üyelik" veya "Kayıt Ol" butonuna tıklayın
3. Hesap bilgilerinizi girin ve onaylayın
4. Email adresinizi doğrulayın

### 2. API Erişimi Aktif Edin

1. Netgsm hesabınıza giriş yapın
2. "API" veya "Entegrasyonlar" bölümüne gidin
3. API erişimini aktif edin
4. API kullanıcı adı ve şifresini kaydedin

### 3. Gönderici Adı (Message Header) Kaydedin

1. Netgsm panelinde "Başlık Yönetimi" bölümüne gidin
2. Yeni başlık ekleyin: **"SPORTCON"** (veya istediğiniz başlık)
3. Başlığın onaylanması 5 iş günü sürer
4. Operatörler (Turkcell, Vodafone, Türk Telekom) başlığı onaylamalıdır

### 4. .env Dosyanızı Güncelleyin

`/app/backend/.env` dosyasını açın ve şu satırları doldurun:

```env
NETGSM_USERNAME="your_netgsm_username"
NETGSM_PASSWORD="your_netgsm_password"
NETGSM_MSGHEADER="SPORTCON"
```

**ÖNEMLİ:** Gerçek credential'larınızı girin, yoksa mock modda çalışır.

### 5. Backend'i Yeniden Başlatın

```bash
sudo supervisorctl restart backend
```

## 📋 Kullanım

### Mevcut Entegrasyon

Netgsm entegrasyonu zaten `verification_service.py` dosyasına eklenmiştir. Hiçbir ek kod değişikliği yapmanıza gerek yok!

### SMS Gönderme (Otomatik)

Mevcut telefon doğrulama sisteminiz otomatik olarak Netgsm kullanacaktır:

```python
# Mevcut kodunuz böyle çalışır:
from verification_service import VerificationService

code = VerificationService.generate_code()
success = VerificationService.send_sms_verification("+905551234567", code)
```

### Manuel SMS Gönderme (İsteğe Bağlı)

Direkt Netgsm servisini kullanmak isterseniz:

```python
from netgsm_service import netgsm_service

# OTP gönder
result = netgsm_service.send_otp_sms("+905551234567")
print(f"OTP Code: {result['otp_code']}")
print(f"Job ID: {result['job_id']}")

# Özel mesaj gönder
result = netgsm_service.send_sms(
    "+905551234567",
    "Hoş geldiniz! Spor Connect uygulamasını kullanmaya başlayabilirsiniz."
)

# Rezervasyon onayı gönder
result = netgsm_service.send_booking_confirmation_sms(
    phone="+905551234567",
    event_name="Futbol Sahası A",
    date="15 Kasım 2025",
    time="14:00"
)
```

## 🇹🇷 Türkiye Özel Notlar

### Telefon Numarası Formatları

Netgsm servisi aşağıdaki formatları otomatik olarak tanır:

- `+90 555 123 4567` (uluslararası format)
- `0555 123 4567` (ulusal format)
- `90 555 123 4567` (ülke kodu ile)
- `555 123 4567` (sadece numara)

### Türkçe Karakter Desteği

SMS'lerde Türkçe karakterler (ç, ğ, ı, ö, ş, ü) otomatik olarak desteklenir. `dil=TR` parametresi kullanılır.

### Yasal Gereklilikler

1. **Opt-out Zorunluluğu**: Her SMS'de "İptal: IPTAL" metni bulunmalıdır (OTP mesajlarında otomatik eklenir)
2. **Gönderici Adı**: Mutlaka kayıtlı olmalı (5 iş günü sürer)
3. **Sessiz Saatler**: 21:00-08:00 arası reklam SMS'i yasak (OTP muaf)

## 💰 Maliyet

- **Kayıt**: Ücretsiz
- **OTP SMS**: ~₺0.10-0.15/mesaj
- **Toplu SMS**: ~₺0.08/mesaj  
- **Minimum yükleme**: ₺100 (yaklaşık 700-1000 SMS)

## 🧪 Test Etme

### Mock Mod (Credential'lar yoksa)

Eğer credential'lar boşsa, sistem mock modda çalışır:

```
2025-11-04 10:29:27,331 - netgsm_service - WARNING - ⚠️  Netgsm credentials not configured. SMS sending will be mocked.
```

Bu durumda:
- SMS gönderilmez
- Kodlar log'a yazılır
- Sistem normal çalışmaya devam eder

### Gerçek SMS Testi

1. .env dosyasına gerçek credential'ları ekleyin
2. Backend'i restart edin
3. Login sayfasında kendi telefon numaranızla test edin
4. SMS'i almalısınız!

## 🔍 Hata Ayıklama

### Hata Kodları

| Kod | Açıklama | Çözüm |
|-----|----------|-------|
| 20  | Mesaj metni hatası | Mesaj çok uzun veya geçersiz karakter |
| 30  | Geçersiz credential | Username/password'u kontrol edin |
| 40  | Gönderici adı kayıtlı değil | MSGHEADER operatörlerde onaylanmalı |
| 50  | Geçersiz telefon numarası | Numara formatını kontrol edin |
| 80  | Günlük limit aşıldı | Netgsm'den limit artırımı isteyin |
| 85  | Duplicate limit aşıldı | 1 dakika içinde aynı numaraya 20'den fazla SMS |

### Log Kontrolleri

Backend loglarını kontrol edin:

```bash
tail -f /var/log/supervisor/backend.err.log | grep netgsm
```

Başarılı SMS:
```
2025-11-04 10:29:27 - netgsm_service - INFO - ✅ SMS sent successfully to 905551234567. Job ID: 123456789
```

Hata:
```
2025-11-04 10:29:27 - netgsm_service - ERROR - ❌ Netgsm error 30: Invalid credentials or insufficient API access
```

## 📞 Destek

### Netgsm Destek

- **Web**: https://www.netgsm.com.tr
- **Email**: destek@netgsm.com.tr
- **Telefon**: +90 (850) 850 10 50

### Sık Sorulan Sorular

**S: Başlık onayı ne kadar sürer?**
C: Genelde 5 iş günü, bazen 3 güne kadar.

**S: Test kredisi var mı?**
C: Hayır, ama minimum ₺100 yükleme yapabilirsiniz.

**S: Uluslararası numara destekliyor mu?**
C: Evet ama bu entegrasyon sadece Türk numaraları için optimize edilmiş.

**S: Mock mod production'da sorun çıkarır mı?**
C: Hayır, credential yoksa mock mod devreye girer ve sistem çalışmaya devam eder.

## ✅ Tamamlandı!

Netgsm entegrasyonu tamamlanmıştır. Credential'larınızı girdikten sonra sistem otomatik olarak gerçek SMS gönderecektir.

---

**Not**: Bu dokümantasyon Sport Connect projesi için hazırlanmıştır. Sorularınız için support ekibine başvurun.
