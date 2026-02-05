"""
Legal Endpoints - Privacy Policy, Terms of Service, KVKK
Bu endpoint'ler App Store ve Google Play için gerekli yasal sayfaları sunar.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/legal", tags=["Legal"])

PRIVACY_POLICY = """
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gizlilik Politikası - SportCo</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }
        h1 { color: #F44336; }
        h2 { color: #1A2744; margin-top: 30px; }
        ul { padding-left: 20px; }
        .updated { color: #666; font-size: 14px; }
    </style>
</head>
<body>
    <h1>Gizlilik Politikası</h1>
    <p class="updated">Son güncelleme: Ocak 2025</p>
    
    <p>Bu Gizlilik Politikası, SportCo tarafından sunulan mobil uygulama, web sitesi ve diğer tüm dijital platformların ("Platform") kullanıcılarının kişisel verilerinin toplanması, işlenmesi, saklanması ve korunmasına ilişkin esasları içermektedir.</p>
    
    <h2>1. Toplanan Veriler</h2>
    <p>SportCo kullanıcılarından aşağıdaki verileri toplayabilir:</p>
    <ul>
        <li>Ad, soyad, telefon numarası, e-posta adresi</li>
        <li>Kullanıcı adı, profil fotoğrafı, yaş, cinsiyet</li>
        <li>Kullanım bilgileri, rezervasyon geçmişi, antrenör veya tesis tercihleri</li>
        <li>Lokasyon bilgisi (kullanıcı onayı ile)</li>
        <li>Ödeme ve faturalandırma verileri (bankacılık bilgileri kaydedilmez, yalnızca ödeme sağlayıcı aracılığıyla işlenir)</li>
    </ul>
    
    <h2>2. Verilerin Toplanma Amaçları</h2>
    <ul>
        <li>Hizmetlerin sunulması ve kullanıcı hesabının yönetilmesi</li>
        <li>Spor tesisi ve antrenör rezervasyonlarının gerçekleştirilmesi</li>
        <li>Duyuru, kampanya ve bilgilendirme mesajlarının iletilmesi</li>
        <li>Kullanıcı güvenliğinin sağlanması, hukuki yükümlülüklerin yerine getirilmesi</li>
        <li>Hizmet kalitesinin artırılması ve analiz yapılması</li>
    </ul>
    
    <h2>3. Verilerin Saklanması ve Güvenlik</h2>
    <p>Kişisel verileriniz, Türkiye'de bulunan güvenli sunucularda saklanmakta olup üçüncü taraflarla yalnızca yasal zorunluluklar veya kullanıcı onayı halinde paylaşılmaktadır. Verilere yetkisiz erişim, kayıp veya kötüye kullanımın engellenmesi için gerekli teknik ve idari tedbirler uygulanmaktadır.</p>
    
    <h2>4. Kullanıcı Hakları</h2>
    <p>Kullanıcılar:</p>
    <ul>
        <li>Verilerinin işlenip işlenmediğini öğrenme</li>
        <li>Düzeltme veya silme talep etme</li>
        <li>İşlemenin kısıtlanmasını talep etme</li>
        <li>Onayı geri çekme</li>
    </ul>
    <p>haklarına sahiptir.</p>
    
    <h2>5. İletişim</h2>
    <p>Bu haklar için: <a href="mailto:destek@sportco.app">destek@sportco.app</a> üzerinden bize ulaşabilirsiniz.</p>
</body>
</html>
"""

TERMS_OF_SERVICE = """
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kullanım Koşulları - SportCo</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }
        h1 { color: #F44336; }
        h2 { color: #1A2744; margin-top: 30px; }
        ul { padding-left: 20px; }
        .updated { color: #666; font-size: 14px; }
    </style>
</head>
<body>
    <h1>Kullanım Koşulları ve Kullanıcı Sözleşmesi</h1>
    <p class="updated">Son güncelleme: Ocak 2025</p>
    
    <h2>1. Taraflar</h2>
    <p>Bu sözleşme, SportCo ile uygulamayı kullanmaya başlayan kullanıcı arasında kurulmuştur.</p>
    
    <h2>2. Hizmet Tanımı</h2>
    <p>SportCo, spor tesisleri, antrenörler, kulüpler ve spor organizasyonları ile kullanıcıları bir araya getiren aracı bir hizmet platformudur. SportCo bir tesis sahibi veya antrenör değildir; yalnızca bağlantı kurulmasını sağlar.</p>
    
    <h2>3. Kullanıcı Yükümlülükleri</h2>
    <ul>
        <li>Hesap bilgilerinizin doğruluğunu sağlamakla yükümlüsünüz.</li>
        <li>Platformu hukuka aykırı veya hileli amaçlarla kullanamazsınız.</li>
        <li>Rezervasyon iptal, değişiklik ve ödeme koşullarını kabul etmiş olursunuz.</li>
        <li>Başka kullanıcıların hak ve gizliliğini ihlal edemezsiniz.</li>
    </ul>
    
    <h2>4. SportCo'nun Sorumlulukları</h2>
    <p>SportCo, platformda listelenen tesis ve antrenörlerin hizmet kalitesinden doğrudan sorumlu değildir. Hizmet ifası, ilgili tesis ve/veya antrenör tarafından sağlanır.</p>
    
    <h2>5. Ücretlendirme</h2>
    <p>Ödemeler, anlaşmalı ödeme kuruluşları üzerinden güvenli şekilde gerçekleştirilir. SportCo hizmet bedeli komisyon modeliyle tahsil edilebilir.</p>
    
    <h2>6. Sözleşme Feshi</h2>
    <p>Kullanıcı dilediği zaman hesabını silebilir. Platform, kurallara aykırılık durumunda kullanıcı hesabını askıya alma veya kapatma hakkına sahiptir.</p>
    
    <h2>7. İletişim</h2>
    <p>Sorularınız için: <a href="mailto:destek@sportco.app">destek@sportco.app</a></p>
</body>
</html>
"""

KVKK_TEXT = """
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KVKK Aydınlatma Metni - SportCo</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }
        h1 { color: #F44336; }
        h2 { color: #1A2744; margin-top: 30px; }
        ul { padding-left: 20px; }
        .updated { color: #666; font-size: 14px; }
    </style>
</head>
<body>
    <h1>KVKK Aydınlatma Metni</h1>
    <p class="updated">Son güncelleme: Ocak 2025</p>
    
    <h2>Kişisel Verilerin Korunması Kanunu (KVKK) Aydınlatma Metni</h2>
    
    <p>6698 sayılı Kişisel Verilerin Korunması Kanunu kapsamında veri sorumlusu sıfatıyla SportCo, kişisel verilerinizi aşağıdaki amaçlarla işlemektedir:</p>
    
    <ul>
        <li>Üyelik oluşturma, rezervasyon ve iletişim süreçlerinin yürütülmesi</li>
        <li>Müşteri destek hizmetlerinin sağlanması</li>
        <li>Yasal yükümlülüklerin yerine getirilmesi</li>
        <li>Hizmet geliştirme ve performans analizi</li>
    </ul>
    
    <h2>Veri İşleme ve Paylaşım</h2>
    <p>Kişisel verileriniz, açık rızanız veya Kanun'un 5. ve 6. maddelerinde yer alan işleme şartlarına dayanılarak işlenmektedir. Verileriniz; ilgili spor tesisleri, antrenörler ve zorunlu teknik hizmet sağlayıcıları ile sınırlı olmak üzere paylaşılabilir.</p>
    
    <h2>Haklarınız</h2>
    <p>KVKK kapsamında aşağıdaki haklara sahipsiniz:</p>
    <ul>
        <li>Kişisel verilerinizin işlenip işlenmediğini öğrenme</li>
        <li>İşlenmişse buna ilişkin bilgi talep etme</li>
        <li>İşlenme amacını ve bunların amacına uygun kullanılıp kullanılmadığını öğrenme</li>
        <li>Yurt içinde veya yurt dışında aktarıldığı üçüncü kişileri bilme</li>
        <li>Eksik veya yanlış işlenmiş verilerin düzeltilmesini isteme</li>
        <li>Kişisel verilerin silinmesini veya yok edilmesini isteme</li>
        <li>İşlenen verilerin münhasıran otomatik sistemler vasıtasıyla analiz edilmesi suretiyle aleyhinize bir sonucun ortaya çıkmasına itiraz etme</li>
    </ul>
    
    <h2>İletişim</h2>
    <p>Haklarınızı kullanmak için: <a href="mailto:kvkk@sportco.app">kvkk@sportco.app</a> adresi üzerinden bize ulaşabilirsiniz.</p>
</body>
</html>
"""


@router.get("/privacy-policy", response_class=HTMLResponse)
async def get_privacy_policy():
    """Gizlilik Politikası sayfası - App Store ve Google Play için gerekli"""
    return PRIVACY_POLICY


@router.get("/terms-of-service", response_class=HTMLResponse)
async def get_terms_of_service():
    """Kullanım Koşulları sayfası - App Store ve Google Play için gerekli"""
    return TERMS_OF_SERVICE


@router.get("/kvkk", response_class=HTMLResponse)
async def get_kvkk():
    """KVKK Aydınlatma Metni - Türkiye için zorunlu"""
    return KVKK_TEXT


@router.get("/all")
async def get_all_legal_links():
    """Tüm yasal sayfa linklerini döndürür"""
    return {
        "privacy_policy": "/api/legal/privacy-policy",
        "terms_of_service": "/api/legal/terms-of-service",
        "kvkk": "/api/legal/kvkk"
    }
