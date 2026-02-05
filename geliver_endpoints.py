"""
Geliver Kargo API Entegrasyonu
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import httpx
import os
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()

# Geliver API Configuration
GELIVER_API_URL = "https://api.geliver.io/api/v1"
GELIVER_API_TOKEN = os.getenv("GELIVER_API_TOKEN", "")  # Test token'ı .env'den alınacak

# MongoDB connection
db = None

def set_db(database):
    global db
    db = database

# Models
class AddressInfo(BaseModel):
    full_name: str
    phone: str
    email: Optional[str] = ""
    address_line1: str
    address_line2: Optional[str] = ""
    city_code: str  # Plaka kodu (örn: "34" Istanbul)
    city_name: str
    district_name: str
    notes: Optional[str] = ""

class ShippingRateRequest(BaseModel):
    sender_city_code: str
    sender_district_name: str
    recipient_city_code: str
    recipient_district_name: str
    weight: float = 1.0  # kg
    length: float = 10.0  # cm
    width: float = 10.0  # cm
    height: float = 10.0  # cm

class CreateShipmentRequest(BaseModel):
    listing_id: str
    transaction_id: str
    sender_address: AddressInfo
    recipient_address: AddressInfo
    selected_offer_id: str
    provider_code: str
    provider_service_code: str
    shipping_amount: float
    weight: float = 1.0
    length: float = 10.0
    width: float = 10.0
    height: float = 10.0
    item_title: str
    item_quantity: int = 1
    order_amount: float

class ShippingOffer(BaseModel):
    id: str
    provider_code: str
    provider_service_code: str
    amount: float
    amount_vat: float
    total_amount: float
    currency: str
    estimated_time: Optional[str] = None

# Helper functions
def get_geliver_headers():
    return {
        "Authorization": f"Bearer {GELIVER_API_TOKEN}",
        "Content-Type": "application/json"
    }

def get_provider_logo(provider_code: str) -> str:
    """Kargo firması logosu döndür"""
    logos = {
        "SENDEO": "https://www.sendeo.com.tr/images/sendeo-logo.png",
        "SURAT": "https://www.suratkargo.com.tr/assets/images/logo.png",
        "PTT": "https://www.ptt.gov.tr/assets/images/logo/ptt-logo.png",
        "YURTICI": "https://www.yurticikargo.com/Content/images/logo.png",
        "MNG": "https://www.mngkargo.com.tr/assets/images/logo.svg",
        "ARAS": "https://www.araskargo.com.tr/images/logo.png",
        "UPS": "https://www.ups.com/assets/resources/images/UPS_logo.svg",
        "GELIVER": "https://geliver.io/logo.png",
        "KOLAYGELSIN": "https://www.kolaygelsin.com/images/logo.png",
        "HEPSIJET": "https://www.hepsijet.com/images/logo.png",
        "TRENDYOLEXPRESS": "https://www.trendyolexpress.com/images/logo.png",
        "PAKETTAXI": "https://pakettaxi.com/images/logo.png",
    }
    return logos.get(provider_code, "")

def get_provider_name(provider_code: str) -> str:
    """Kargo firması adını döndür"""
    names = {
        "SENDEO": "Sendeo Kargo",
        "SURAT": "Sürat Kargo",
        "PTT": "PTT Kargo",
        "YURTICI": "Yurtiçi Kargo",
        "MNG": "MNG Kargo",
        "ARAS": "Aras Kargo",
        "UPS": "UPS",
        "GELIVER": "Geliver",
        "KOLAYGELSIN": "Kolay Gelsin",
        "HEPSIJET": "HepsiJet",
        "TRENDYOLEXPRESS": "Trendyol Express",
        "PAKETTAXI": "Paket Taxi",
    }
    return names.get(provider_code, provider_code)


# City code mapping (plaka kodları)
CITY_CODES = {
    "Adana": "01", "Adıyaman": "02", "Afyonkarahisar": "03", "Ağrı": "04", "Amasya": "05",
    "Ankara": "06", "Antalya": "07", "Artvin": "08", "Aydın": "09", "Balıkesir": "10",
    "Bilecik": "11", "Bingöl": "12", "Bitlis": "13", "Bolu": "14", "Burdur": "15",
    "Bursa": "16", "Çanakkale": "17", "Çankırı": "18", "Çorum": "19", "Denizli": "20",
    "Diyarbakır": "21", "Edirne": "22", "Elazığ": "23", "Erzincan": "24", "Erzurum": "25",
    "Eskişehir": "26", "Gaziantep": "27", "Giresun": "28", "Gümüşhane": "29", "Hakkari": "30",
    "Hatay": "31", "Isparta": "32", "Mersin": "33", "İstanbul": "34", "İzmir": "35",
    "Kars": "36", "Kastamonu": "37", "Kayseri": "38", "Kırklareli": "39", "Kırşehir": "40",
    "Kocaeli": "41", "Konya": "42", "Kütahya": "43", "Malatya": "44", "Manisa": "45",
    "Kahramanmaraş": "46", "Mardin": "47", "Muğla": "48", "Muş": "49", "Nevşehir": "50",
    "Niğde": "51", "Ordu": "52", "Rize": "53", "Sakarya": "54", "Samsun": "55",
    "Siirt": "56", "Sinop": "57", "Sivas": "58", "Tekirdağ": "59", "Tokat": "60",
    "Trabzon": "61", "Tunceli": "62", "Şanlıurfa": "63", "Uşak": "64", "Van": "65",
    "Yozgat": "66", "Zonguldak": "67", "Aksaray": "68", "Bayburt": "69", "Karaman": "70",
    "Kırıkkale": "71", "Batman": "72", "Şırnak": "73", "Bartın": "74", "Ardahan": "75",
    "Iğdır": "76", "Yalova": "77", "Karabük": "78", "Kilis": "79", "Osmaniye": "80", "Düzce": "81"
}

def get_city_code(city_name: str) -> str:
    """Şehir adından plaka kodunu döndür"""
    return CITY_CODES.get(city_name, "34")  # Varsayılan İstanbul


async def create_geliver_shipment_after_payment(
    transaction: dict,
    listing: dict,
    buyer: dict,
    seller: dict,
    database
) -> dict:
    """
    Ödeme tamamlandıktan sonra Geliver'da gönderi oluşturur.
    Bu fonksiyon marketplace_endpoints.py'den çağrılır.
    
    Returns:
        dict: {
            "success": bool,
            "shipment_id": str,
            "barcode": str,
            "tracking_code": str,
            "label_url": str,
            "provider_name": str,
            "error": str (if failed)
        }
    """
    try:
        provider_code = transaction.get("shipping_provider", "")
        provider_service_code = transaction.get("shipping_service", "")
        
        if not provider_code or not provider_service_code:
            logger.warning("Kargo bilgisi eksik, gönderi oluşturulamadı")
            return {
                "success": False,
                "error": "Kargo bilgisi eksik"
            }
        
        # Alıcı adres bilgilerini al
        shipping_address = transaction.get("shipping_address", {})
        if not shipping_address:
            logger.warning("Alıcı adresi eksik")
            return {
                "success": False,
                "error": "Alıcı adresi eksik"
            }
        
        # Gönderici adres bilgilerini listing'den al
        sender_city = listing.get("seller_shipping_city", seller.get("city", "İstanbul"))
        sender_district = listing.get("seller_shipping_district", seller.get("district", ""))
        sender_name = listing.get("seller_shipping_name", seller.get("full_name", ""))
        sender_neighborhood = listing.get("seller_shipping_neighborhood", "")
        sender_street = listing.get("seller_shipping_street", "")
        sender_building_no = listing.get("seller_shipping_building_no", "")
        sender_apartment_no = listing.get("seller_shipping_apartment_no", "")
        
        # Mahalle bilgisi yoksa ilçeyi mahalle olarak kullan (Geliver mahalle zorunlu tutuyor)
        if not sender_neighborhood:
            sender_neighborhood = sender_district
        
        # Tam gönderici adresi oluştur - Mahalle bilgisi EN BAŞTA olmalı (Geliver gereksinimi)
        sender_address_parts = [sender_neighborhood]
        if sender_street:
            sender_address_parts.append(sender_street)
        if sender_building_no:
            sender_address_parts.append(f"No: {sender_building_no}")
        if sender_apartment_no:
            sender_address_parts.append(f"Daire: {sender_apartment_no}")
        sender_full_address = " ".join(filter(None, sender_address_parts)) or f"{sender_neighborhood} Mahallesi, {sender_district}"
        
        # Alıcı bilgileri
        recipient_name = shipping_address.get("full_name", buyer.get("full_name", ""))
        recipient_phone = shipping_address.get("phone", buyer.get("phone", ""))
        recipient_city = shipping_address.get("city_name", "")
        recipient_city_code = shipping_address.get("city_code", get_city_code(recipient_city))
        recipient_district = shipping_address.get("district_name", "")
        recipient_address = shipping_address.get("address_line1", "")
        
        logger.info(f"📦 Geliver gönderi oluşturuluyor: {listing.get('title')} -> {recipient_name}")
        logger.info(f"   Provider: {provider_service_code}")
        logger.info(f"   Gönderen: {sender_name}, {sender_city}/{sender_district}")
        logger.info(f"   Alıcı: {recipient_name}, {recipient_city}/{recipient_district}")
        
        if not GELIVER_API_TOKEN:
            # Test modu
            test_barcode = f"TEST{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            logger.warning("Geliver API token yok, test barcode oluşturuldu: " + test_barcode)
            return {
                "success": True,
                "test_mode": True,
                "shipment_id": f"test-{transaction['id']}",
                "barcode": test_barcode,
                "tracking_code": test_barcode,
                "label_url": "",
                "provider_name": get_provider_name(provider_code)
            }
        
        # Geliver API'ye tek aşamalı gönderi oluşturma isteği
        shipment_data = {
            "providerServiceCode": provider_service_code,
            "shipment": {
                "test": False,  # Canlı ortam
                "senderAddress": {
                    "name": sender_name,
                    "phone": seller.get("phone", "+905000000000"),
                    "email": seller.get("email", ""),
                    "address1": sender_full_address,
                    "countryCode": "TR",
                    "cityCode": get_city_code(sender_city),
                    "districtName": sender_district
                },
                "recipientAddress": {
                    "name": recipient_name,
                    "phone": recipient_phone or "+905000000000",
                    "email": buyer.get("email", ""),
                    "address1": recipient_address,
                    "countryCode": "TR",
                    "cityCode": recipient_city_code,
                    "districtName": recipient_district
                },
                "length": str(listing.get("package_depth", 20)),
                "height": str(listing.get("package_height", 15)),
                "width": str(listing.get("package_width", 15)),
                "distanceUnit": "cm",
                "weight": str(listing.get("package_weight", 1)),
                "massUnit": "kg",
                "items": [
                    {
                        "title": listing.get("title", "Ürün"),
                        "quantity": 1
                    }
                ],
                "productPaymentOnDelivery": False,
                "hidePackageContentOnTag": False,
                "order": {
                    "sourceCode": "API",
                    "sourceIdentifier": "SportsMaker",
                    "orderNumber": transaction["id"],
                    "totalAmount": int(transaction.get("total_paid_by_buyer", 0)),
                    "totalAmountCurrency": "TL"
                }
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GELIVER_API_URL}/transactions",
                json=shipment_data,
                headers=get_geliver_headers(),
                timeout=30.0
            )
            
            logger.info(f"Geliver API response status: {response.status_code}")
            
            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Geliver API hatası: {response.status_code} - {error_text}")
                return {
                    "success": False,
                    "error": f"Geliver API hatası: {error_text[:200]}"
                }
            
            data = response.json()
            logger.info(f"Geliver API response: {data}")
            
            if not data.get("result"):
                error_msg = data.get("message", "Gönderi oluşturulamadı")
                logger.error(f"Geliver API başarısız: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
            
            shipment_data_response = data.get("data", {})
            shipment = shipment_data_response.get("shipment", {})
            
            shipment_id = shipment.get("id", "")
            barcode = shipment.get("barcode", "")
            label_url = shipment.get("labelURL", "")
            
            logger.info(f"✅ Geliver gönderi oluşturuldu: ID={shipment_id}, Barcode={barcode}")
            
            # Transaction'ı güncelle
            if database is not None:
                await database.marketplace_transactions.update_one(
                    {"id": transaction["id"]},
                    {"$set": {
                        "geliver_shipment_id": shipment_id,
                        "tracking_code": barcode,
                        "barcode": barcode,
                        "label_url": label_url,
                        "shipping_status": "label_created",
                        "updated_at": datetime.utcnow()
                    }}
                )
            
            return {
                "success": True,
                "test_mode": False,
                "shipment_id": shipment_id,
                "barcode": barcode,
                "tracking_code": barcode,
                "label_url": label_url,
                "provider_name": get_provider_name(provider_code)
            }
            
    except Exception as e:
        logger.error(f"Geliver gönderi oluşturma hatası: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


async def create_geliver_return_shipment(
    return_request: dict,
    transaction: dict,
    listing: dict,
    buyer: dict,
    seller: dict
) -> dict:
    """
    İade için Geliver gönderi oluşturur.
    Bu sefer gönderici ALICI, alıcı SATICI olacak.
    Kargo ücreti alıcıya yansıtılacak.
    """
    try:
        if not GELIVER_API_TOKEN:
            logger.warning("Geliver API token yok - test modu (İade)")
            return {
                "success": True,
                "test_mode": True,
                "barcode": f"IADE-TEST{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "tracking_code": f"IADE-TEST{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "shipping_cost": 50.0,  # Test kargo ücreti
                "provider_name": "Test Kargo (İade)"
            }
        
        # Alıcının (gönderici) adres bilgileri - shipping_address'ten al
        shipping_address = transaction.get("shipping_address", {})
        sender_name = shipping_address.get("full_name", buyer.get("full_name", ""))
        sender_phone = shipping_address.get("phone", buyer.get("phone", ""))
        sender_city = shipping_address.get("city", buyer.get("city", "İstanbul"))
        sender_district = shipping_address.get("district", buyer.get("district", ""))
        sender_address = shipping_address.get("address_line1", "")
        sender_neighborhood = shipping_address.get("neighborhood", sender_district)
        
        # Sender city code
        sender_city_code = CITY_CODES.get(sender_city.lower(), 34)
        
        # Satıcının (alıcı) adres bilgileri - listing'den al
        recipient_city = listing.get("seller_shipping_city", seller.get("city", "İstanbul"))
        recipient_district = listing.get("seller_shipping_district", seller.get("district", ""))
        recipient_name = listing.get("seller_shipping_name", seller.get("full_name", ""))
        recipient_phone = seller.get("phone", "")
        recipient_neighborhood = listing.get("seller_shipping_neighborhood", recipient_district)
        recipient_street = listing.get("seller_shipping_street", "")
        recipient_building_no = listing.get("seller_shipping_building_no", "")
        recipient_apartment_no = listing.get("seller_shipping_apartment_no", "")
        
        # Recipient city code
        recipient_city_code = CITY_CODES.get(recipient_city.lower(), 34)
        
        # Alıcı tam adres
        recipient_address_parts = [recipient_neighborhood]
        if recipient_street:
            recipient_address_parts.append(recipient_street)
        if recipient_building_no:
            recipient_address_parts.append(f"No: {recipient_building_no}")
        if recipient_apartment_no:
            recipient_address_parts.append(f"Daire: {recipient_apartment_no}")
        recipient_full_address = " ".join(filter(None, recipient_address_parts)) or f"{recipient_neighborhood}, {recipient_district}"
        
        # Mahalle bilgisi kontrolü
        if not sender_neighborhood:
            sender_neighborhood = sender_district
        
        logger.info("🔄 İade Geliver gönderi oluşturuluyor...")
        logger.info(f"   Gönderici (Alıcı): {sender_name}, {sender_city}/{sender_district}")
        logger.info(f"   Alıcı (Satıcı): {recipient_name}, {recipient_city}/{recipient_district}")
        
        # İade için tercih edilen kargo şirketini belirle
        # Orijinal gönderimde kullanılan şirketi kullanmayı dene
        original_provider = transaction.get("shipping_provider_code", "ups")
        
        shipment_data = {
            "shipment": {
                "test": False,
                "currency": "try",
                "providerCode": original_provider,
                "senderAddress": {
                    "name": sender_name,
                    "phone": sender_phone or "+905000000000",
                    "email": buyer.get("email", ""),
                    "address1": f"{sender_neighborhood} {sender_address}".strip() or f"{sender_neighborhood} Mahallesi",
                    "countryCode": "TR",
                    "cityCode": sender_city_code,
                    "districtName": sender_district
                },
                "recipientAddress": {
                    "name": recipient_name,
                    "phone": recipient_phone or "+905000000000",
                    "email": seller.get("email", ""),
                    "address1": recipient_full_address,
                    "countryCode": "TR",
                    "cityCode": recipient_city_code,
                    "districtName": recipient_district
                },
                "length": str(listing.get("package_depth", 20)),
                "height": str(listing.get("package_height", 15)),
                "width": str(listing.get("package_width", 15)),
                "distanceUnit": "cm",
                "weight": str(listing.get("package_weight", 1)),
                "massUnit": "kg",
                "items": [
                    {
                        "title": f"İade: {listing.get('title', 'Ürün')}",
                        "quantity": 1
                    }
                ],
                "productPaymentOnDelivery": False,
                "hidePackageContentOnTag": False,
                "order": {
                    "sourceCode": "API",
                    "sourceIdentifier": "SportsMaker-IADE",
                    "orderNumber": f"IADE-{return_request.get('id', '')}",
                    "totalAmount": 0,
                    "totalAmountCurrency": "TL"
                }
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GELIVER_API_URL}/transactions",
                headers={
                    "Authorization": f"Bearer {GELIVER_API_TOKEN}",
                    "Content-Type": "application/json"
                },
                json=shipment_data,
                timeout=30.0
            )
            
            logger.info(f"İade Geliver API yanıtı: {response.status_code}")
            
            if response.status_code not in [200, 201]:
                error_text = response.text
                logger.error(f"İade Geliver API hatası: {error_text}")
                return {
                    "success": False,
                    "error": f"Geliver API error: {error_text}"
                }
            
            result = response.json()
            logger.info(f"İade Geliver yanıt: {json.dumps(result, indent=2, default=str)}")
            
            # Barcode ve label URL'i al
            shipment_result = result.get("data", result)
            barcode = shipment_result.get("barcode", "")
            label_url = shipment_result.get("labelUrl", "")
            shipping_cost = shipment_result.get("price", 0)
            provider_code = shipment_result.get("providerCode", original_provider)
            
            if not barcode:
                barcode = shipment_result.get("trackingNumber", f"IADE-{datetime.now().strftime('%Y%m%d%H%M%S')}")
            
            logger.info(f"✅ İade Geliver gönderi oluşturuldu: {barcode}")
            
            return {
                "success": True,
                "test_mode": False,
                "barcode": barcode,
                "tracking_code": barcode,
                "label_url": label_url,
                "shipping_cost": float(shipping_cost) if shipping_cost else 0,
                "provider_name": get_provider_name(provider_code)
            }
            
    except Exception as e:
        logger.error(f"İade Geliver gönderi oluşturma hatası: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/shipping/rates")
async def get_shipping_rates(
    weight: float = 1.0,
    length: float = 10.0,
    width: float = 10.0,
    height: float = 10.0
):
    """Kargo fiyatlarını listele"""
    try:
        if not GELIVER_API_TOKEN:
            # Test modu - mock data döndür
            logger.warning("Geliver API token bulunamadı, test verileri döndürülüyor")
            return {
                "success": True,
                "test_mode": True,
                "offers": [
                    {
                        "id": "test-sendeo-1",
                        "provider_code": "SENDEO",
                        "provider_service_code": "SENDEO_STANDART",
                        "provider_name": "Sendeo Kargo",
                        "provider_logo": get_provider_logo("SENDEO"),
                        "amount": 45.00,
                        "amount_vat": 9.00,
                        "total_amount": 54.00,
                        "currency": "TL",
                        "estimated_time": "1-2 iş günü"
                    },
                    {
                        "id": "test-ptt-1",
                        "provider_code": "PTT",
                        "provider_service_code": "PTT_STANDART",
                        "provider_name": "PTT Kargo",
                        "provider_logo": get_provider_logo("PTT"),
                        "amount": 38.00,
                        "amount_vat": 7.60,
                        "total_amount": 45.60,
                        "currency": "TL",
                        "estimated_time": "2-3 iş günü"
                    },
                    {
                        "id": "test-yurtici-1",
                        "provider_code": "YURTICI",
                        "provider_service_code": "YURTICI_STANDART",
                        "provider_name": "Yurtiçi Kargo",
                        "provider_logo": get_provider_logo("YURTICI"),
                        "amount": 52.00,
                        "amount_vat": 10.40,
                        "total_amount": 62.40,
                        "currency": "TL",
                        "estimated_time": "1 iş günü"
                    },
                    {
                        "id": "test-surat-1",
                        "provider_code": "SURAT",
                        "provider_service_code": "SURAT_STANDART",
                        "provider_name": "Sürat Kargo",
                        "provider_logo": get_provider_logo("SURAT"),
                        "amount": 42.00,
                        "amount_vat": 8.40,
                        "total_amount": 50.40,
                        "currency": "TL",
                        "estimated_time": "1-2 iş günü"
                    }
                ]
            }
        
        # Gerçek Geliver API çağrısı
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GELIVER_API_URL}/priceList",
                params={
                    "paramType": "parcel",
                    "length": length,
                    "width": width,
                    "height": height,
                    "weight": weight
                },
                headers=get_geliver_headers(),
                timeout=30.0
            )
            
            if response.status_code != 200:
                logger.error(f"Geliver API hatası: {response.status_code} - {response.text}")
                # API hatası durumunda test verilerini döndür
                logger.warning("Geliver API hatası, test verileri döndürülüyor")
                return {
                    "success": True,
                    "test_mode": True,
                    "api_error": True,
                    "offers": [
                        {
                            "id": "test-sendeo-1",
                            "provider_code": "SENDEO",
                            "provider_service_code": "SENDEO_STANDART",
                            "provider_name": "Sendeo Kargo",
                            "provider_logo": get_provider_logo("SENDEO"),
                            "amount": 45.00,
                            "amount_vat": 9.00,
                            "total_amount": 54.00,
                            "currency": "TL",
                            "estimated_time": "1-2 iş günü"
                        },
                        {
                            "id": "test-ptt-1",
                            "provider_code": "PTT",
                            "provider_service_code": "PTT_STANDART",
                            "provider_name": "PTT Kargo",
                            "provider_logo": get_provider_logo("PTT"),
                            "amount": 38.00,
                            "amount_vat": 7.60,
                            "total_amount": 45.60,
                            "currency": "TL",
                            "estimated_time": "2-3 iş günü"
                        },
                        {
                            "id": "test-yurtici-1",
                            "provider_code": "YURTICI",
                            "provider_service_code": "YURTICI_STANDART",
                            "provider_name": "Yurtiçi Kargo",
                            "provider_logo": get_provider_logo("YURTICI"),
                            "amount": 52.00,
                            "amount_vat": 10.40,
                            "total_amount": 62.40,
                            "currency": "TL",
                            "estimated_time": "1 iş günü"
                        },
                        {
                            "id": "test-surat-1",
                            "provider_code": "SURAT",
                            "provider_service_code": "SURAT_STANDART",
                            "provider_name": "Sürat Kargo",
                            "provider_logo": get_provider_logo("SURAT"),
                            "amount": 42.00,
                            "amount_vat": 8.40,
                            "total_amount": 50.40,
                            "currency": "TL",
                            "estimated_time": "1-2 iş günü"
                        }
                    ]
                }
            
            data = response.json()
            
            if not data.get("result"):
                # API başarısız olursa test verilerini döndür
                logger.warning(f"Geliver API başarısız: {data.get('message')}, test verileri döndürülüyor")
                return {
                    "success": True,
                    "test_mode": True,
                    "api_error": True,
                    "offers": [
                        {
                            "id": "test-sendeo-1",
                            "provider_code": "SENDEO",
                            "provider_service_code": "SENDEO_STANDART",
                            "provider_name": "Sendeo Kargo",
                            "provider_logo": get_provider_logo("SENDEO"),
                            "amount": 45.00,
                            "amount_vat": 9.00,
                            "total_amount": 54.00,
                            "currency": "TL",
                            "estimated_time": "1-2 iş günü"
                        },
                        {
                            "id": "test-ptt-1",
                            "provider_code": "PTT",
                            "provider_service_code": "PTT_STANDART",
                            "provider_name": "PTT Kargo",
                            "provider_logo": get_provider_logo("PTT"),
                            "amount": 38.00,
                            "amount_vat": 7.60,
                            "total_amount": 45.60,
                            "currency": "TL",
                            "estimated_time": "2-3 iş günü"
                        },
                        {
                            "id": "test-yurtici-1",
                            "provider_code": "YURTICI",
                            "provider_service_code": "YURTICI_STANDART",
                            "provider_name": "Yurtiçi Kargo",
                            "provider_logo": get_provider_logo("YURTICI"),
                            "amount": 52.00,
                            "amount_vat": 10.40,
                            "total_amount": 62.40,
                            "currency": "TL",
                            "estimated_time": "1 iş günü"
                        },
                        {
                            "id": "test-surat-1",
                            "provider_code": "SURAT",
                            "provider_service_code": "SURAT_STANDART",
                            "provider_name": "Sürat Kargo",
                            "provider_logo": get_provider_logo("SURAT"),
                            "amount": 42.00,
                            "amount_vat": 8.40,
                            "total_amount": 50.40,
                            "currency": "TL",
                            "estimated_time": "1-2 iş günü"
                        }
                    ]
                }
            
            # Teklifleri formatla
            offers = []
            seen_ids = set()  # Tekrarlı teklifleri önlemek için
            price_list = data.get("priceList", [])
            
            for price_item in price_list:
                for offer in price_item.get("offers", []):
                    offer_id = f"{offer.get('providerCode')}-{offer.get('providerServiceCode')}"
                    
                    # Tekrarlı teklifleri atla
                    if offer_id in seen_ids:
                        continue
                    seen_ids.add(offer_id)
                    
                    offers.append({
                        "id": offer_id,
                        "provider_code": offer.get("providerCode"),
                        "provider_service_code": offer.get("providerServiceCode"),
                        "provider_name": get_provider_name(offer.get("providerCode")),
                        "provider_logo": get_provider_logo(offer.get("providerCode")),
                        "amount": float(offer.get("amount", 0)),
                        "amount_vat": float(offer.get("amountVat", 0)),
                        "total_amount": float(offer.get("totalAmount", 0)),
                        "currency": offer.get("currency", "TL"),
                        "estimated_time": None
                    })
            
            # Fiyata göre sırala
            offers.sort(key=lambda x: x["total_amount"])
            
            return {
                "success": True,
                "test_mode": False,
                "offers": offers
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Kargo fiyatları alınırken hata: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shipping/create-shipment")
async def create_shipment(request: CreateShipmentRequest):
    """Geliver üzerinden gönderi oluştur"""
    try:
        if not GELIVER_API_TOKEN:
            # Test modu
            shipment_id = f"test-shipment-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            
            # Transaction'a kargo bilgilerini kaydet
            if db is not None:
                await db.marketplace_transactions.update_one(
                    {"id": request.transaction_id},
                    {"$set": {
                        "shipping_provider": request.provider_code,
                        "shipping_service": request.provider_service_code,
                        "shipping_amount": request.shipping_amount,
                        "geliver_shipment_id": shipment_id,
                        "shipping_status": "pending_pickup",
                        "updated_at": datetime.utcnow()
                    }}
                )
            
            return {
                "success": True,
                "test_mode": True,
                "shipment_id": shipment_id,
                "tracking_code": f"TEST{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                "status": "pending_pickup",
                "message": "Test gönderisi oluşturuldu"
            }
        
        # Gerçek Geliver API çağrısı
        shipment_data = {
            "test": False,  # Canlı ortam için false
            "length": str(request.length),
            "height": str(request.height),
            "width": str(request.width),
            "distanceUnit": "cm",
            "weight": str(request.weight),
            "massUnit": "kg",
            "items": [
                {
                    "title": request.item_title,
                    "quantity": request.item_quantity
                }
            ],
            "recipientAddress": {
                "name": request.recipient_address.full_name,
                "email": request.recipient_address.email or "noemail@example.com",
                "phone": request.recipient_address.phone,
                "address1": request.recipient_address.address_line1,
                "countryCode": "TR",
                "cityCode": request.recipient_address.city_code,
                "districtName": request.recipient_address.district_name
            },
            "productPaymentOnDelivery": False,
            "order": {
                "sourceCode": "API",
                "sourceIdentifier": "SportsMaker",
                "orderNumber": request.transaction_id,
                "totalAmount": int(request.order_amount),
                "totalAmountCurrency": "TL"
            }
        }
        
        async with httpx.AsyncClient() as client:
            # 1. Gönderi oluştur ve teklifleri al
            response = await client.post(
                f"{GELIVER_API_URL}/shipments",
                json=shipment_data,
                headers=get_geliver_headers(),
                timeout=30.0
            )
            
            if response.status_code != 200:
                logger.error(f"Geliver gönderi oluşturma hatası: {response.status_code} - {response.text}")
                raise HTTPException(status_code=500, detail="Gönderi oluşturulamadı")
            
            data = response.json()
            
            if not data.get("result"):
                raise HTTPException(status_code=500, detail=data.get("message", "Gönderi oluşturulamadı"))
            
            shipment = data.get("data", {})
            shipment_id = shipment.get("id")
            
            # 2. Seçilen teklifi kabul et
            offers = shipment.get("offers", {}).get("list", [])
            selected_offer = None
            
            for offer in offers:
                if offer.get("providerServiceCode") == request.provider_service_code:
                    selected_offer = offer
                    break
            
            if not selected_offer:
                # En ucuz teklifi seç
                selected_offer = shipment.get("offers", {}).get("cheapest")
            
            if selected_offer:
                offer_id = selected_offer.get("id")
                
                # Teklifi kabul et
                accept_response = await client.post(
                    f"{GELIVER_API_URL}/shipments/{shipment_id}/acceptOffer",
                    json={"offerID": offer_id},
                    headers=get_geliver_headers(),
                    timeout=30.0
                )
                
                if accept_response.status_code == 200:
                    accept_data = accept_response.json()
                    tracking_code = accept_data.get("data", {}).get("trackingCode", "")
                else:
                    tracking_code = ""
            else:
                tracking_code = ""
            
            # Transaction'a kargo bilgilerini kaydet
            if db is not None:
                await db.marketplace_transactions.update_one(
                    {"id": request.transaction_id},
                    {"$set": {
                        "shipping_provider": request.provider_code,
                        "shipping_service": request.provider_service_code,
                        "shipping_amount": request.shipping_amount,
                        "geliver_shipment_id": shipment_id,
                        "tracking_code": tracking_code,
                        "shipping_status": "pending_pickup",
                        "updated_at": datetime.utcnow()
                    }}
                )
            
            return {
                "success": True,
                "test_mode": False,
                "shipment_id": shipment_id,
                "tracking_code": tracking_code,
                "status": "pending_pickup",
                "message": "Gönderi başarıyla oluşturuldu"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gönderi oluşturulurken hata: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Kargo durumu eşleştirme sabitleri
GELIVER_STATUS_MAP = {
    "PRE_TRANSIT": "pending_pickup",
    "IN_TRANSIT": "in_transit",
    "OUT_FOR_DELIVERY": "out_for_delivery",
    "DELIVERED": "delivered",
    "RETURNED": "returned",
    "FAILURE": "failed"
}

SHIPPING_STATUS_TEXT = {
    "pending_pickup": "Kargo Bekleniyor",
    "in_transit": "Yolda",
    "out_for_delivery": "Dağıtımda",
    "delivered": "Teslim Edildi",
    "returned": "İade Edildi",
    "failed": "Teslim Edilemedi"
}


async def track_shipment_by_code(tracking_code: str, provider_code: str = None) -> dict:
    """
    Kargo takip kodu ile gönderi durumunu sorgula.
    Bu fonksiyon background_scheduler.py tarafından çağrılabilir.
    
    Returns:
        dict: {
            "success": bool,
            "status": str,
            "status_text": str,
            "tracking_history": list,
            "raw_status": str
        }
    """
    try:
        if not GELIVER_API_TOKEN:
            # Test modu - rastgele durum döndür
            import random
            test_statuses = ["in_transit", "out_for_delivery", "delivered"]
            status = random.choice(test_statuses)
            return {
                "success": True,
                "test_mode": True,
                "status": status,
                "status_text": SHIPPING_STATUS_TEXT.get(status, "Bilinmeyen"),
                "tracking_history": [],
                "raw_status": status
            }
        
        # Geliver API'ye barkod/takip kodu ile sorgulama
        # Geliver transactions endpoint'i kendi barcode'uyla sorgulanabilir
        async with httpx.AsyncClient() as client:
            # Shipment bilgisini tracking code ile al
            response = await client.get(
                f"{GELIVER_API_URL}/transactions",
                params={"barcode": tracking_code},
                headers=get_geliver_headers(),
                timeout=30.0
            )
            
            if response.status_code != 200:
                logger.warning(f"Geliver tracking sorgusu başarısız: {tracking_code} - {response.status_code}")
                return {
                    "success": False,
                    "error": f"API hatası: {response.status_code}"
                }
            
            data = response.json()
            
            if not data.get("result"):
                return {
                    "success": False,
                    "error": data.get("message", "Gönderi bulunamadı")
                }
            
            transactions = data.get("data", {}).get("transactions", [])
            
            if not transactions:
                return {
                    "success": False,
                    "error": "Gönderi bulunamadı"
                }
            
            shipment = transactions[0]
            tracking_status = shipment.get("trackingStatus", {})
            raw_status = tracking_status.get("trackingStatusCode", "UNKNOWN")
            status = GELIVER_STATUS_MAP.get(raw_status, "unknown")
            
            # Tracking history'yi parse et
            tracking_history = []
            events = shipment.get("trackingEvents", [])
            for event in events:
                tracking_history.append({
                    "date": event.get("createdAt", ""),
                    "status": event.get("statusDescription", ""),
                    "location": event.get("location", "")
                })
            
            return {
                "success": True,
                "test_mode": False,
                "status": status,
                "status_text": tracking_status.get("statusDetails", SHIPPING_STATUS_TEXT.get(status, "")),
                "tracking_history": tracking_history,
                "raw_status": raw_status
            }
            
    except Exception as e:
        logger.error(f"Kargo takip hatası ({tracking_code}): {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/shipping/track/{shipment_id}")
async def track_shipment(shipment_id: str):
    """Gönderi takibi"""
    try:
        if not GELIVER_API_TOKEN or shipment_id.startswith("test-"):
            # Test modu
            return {
                "success": True,
                "test_mode": True,
                "shipment_id": shipment_id,
                "status": "in_transit",
                "status_text": "Yolda",
                "tracking_history": [
                    {
                        "date": datetime.utcnow().isoformat(),
                        "status": "Kargo teslim alındı",
                        "location": "İstanbul"
                    }
                ]
            }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GELIVER_API_URL}/shipments/{shipment_id}",
                headers=get_geliver_headers(),
                timeout=30.0
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=404, detail="Gönderi bulunamadı")
            
            data = response.json()
            shipment = data.get("data", {})
            
            tracking_status = shipment.get("trackingStatus", {})
            status_code = tracking_status.get("trackingStatusCode", "UNKNOWN")
            
            return {
                "success": True,
                "test_mode": False,
                "shipment_id": shipment_id,
                "status": GELIVER_STATUS_MAP.get(status_code, "unknown"),
                "status_text": tracking_status.get("statusDetails", ""),
                "tracking_code": shipment.get("trackingCode", ""),
                "tracking_history": []
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gönderi takibi hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# User address endpoints
@router.get("/users/{user_id}/shipping-address")
async def get_user_shipping_address(user_id: str):
    """Kullanıcının kayıtlı teslimat adresini getir"""
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection error")
        
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        
        shipping_address = user.get("shipping_address")
        
        if not shipping_address:
            return {
                "success": True,
                "has_address": False,
                "address": None
            }
        
        return {
            "success": True,
            "has_address": True,
            "address": shipping_address
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Adres getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{user_id}/shipping-address")
async def update_user_shipping_address(user_id: str, address: AddressInfo):
    """Kullanıcının teslimat adresini güncelle"""
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection error")
        
        result = await db.users.update_one(
            {"id": user_id},
            {"$set": {
                "shipping_address": address.dict(),
                "updated_at": datetime.utcnow()
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        
        return {
            "success": True,
            "message": "Adres güncellendi"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Adres güncelleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
