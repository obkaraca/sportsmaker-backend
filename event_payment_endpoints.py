"""
Event Payment Endpoints with İyzico Integration
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import logging
import uuid
import os
from motor.motor_asyncio import AsyncIOMotorClient

from auth import get_current_user
from iyzico_service import IyzicoService

# Database
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

logger = logging.getLogger(__name__)

router = APIRouter()


class EventPaymentRequest(BaseModel):
    event_id: str
    participant_name: Optional[str] = None
    participant_email: Optional[str] = None
    participant_phone: Optional[str] = None
    selected_game_types: Optional[list] = None  # Seçilen oyun türleri
    total_price: Optional[float] = None  # Frontend'den gelen toplam fiyat


@router.get("/events/payment-status/{payment_id}")
async def get_event_payment_status(
    payment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Ödeme durumunu kontrol et (polling için)
    Önce DB durumunu kontrol eder, sonra gerekirse İyzico'dan sorgular
    """
    try:
        payment = await db.payments.find_one({"id": payment_id})
        
        if not payment:
            raise HTTPException(status_code=404, detail="Ödeme kaydı bulunamadı")
        
        # Sadece kendi ödemesini görebilir
        if payment.get("user_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Bu ödemeye erişim yetkiniz yok")
        
        current_status = payment.get("status", "pending")
        logger.info(f"📊 Payment {payment_id} DB status: {current_status}")
        
        # ✅ ÖNCELİK 1: Eğer DB'de zaten completed ise direkt döndür (callback gelmiş)
        if current_status in ["completed", "payment_completed", "success"]:
            logger.info(f"✅ Payment already completed in DB (callback processed)")
            return {
                "payment_id": payment_id,
                "status": "completed",
                "event_id": payment.get("event_id"),
                "amount": payment.get("amount"),
                "updated_at": payment.get("updated_at")
            }
        
        # ✅ ÖNCELİK 2: Eğer DB'de failed ise direkt döndür
        if current_status in ["failed", "payment_failed"]:
            logger.info(f"❌ Payment already failed in DB")
            return {
                "payment_id": payment_id,
                "status": "failed",
                "event_id": payment.get("event_id"),
                "error": payment.get("error_message", "Ödeme başarısız oldu")
            }
        
        # ✅ ÖNCELİK 3: Eğer beklemede ise ve İyzico token varsa, İyzico'dan kontrol et
        if current_status in ["pending", "init_3ds", "waiting_3ds", "init"] and payment.get("iyzico_token"):
            try:
                iyzico_service = IyzicoService()
                iyzico_result = iyzico_service.retrieve_payment(payment.get("iyzico_token"))
                
                if iyzico_result:
                    iyzico_status = iyzico_result.get('status')
                    payment_status = iyzico_result.get('paymentStatus')
                    error_message = iyzico_result.get('errorMessage', '')
                    
                    logger.info(f"📊 İyzico sorgu: status={iyzico_status}, paymentStatus={payment_status}, error={error_message}")
                    
                    # Token bulunamadı veya süresi doldu - ama DB'yi tekrar kontrol et
                    if error_message and ('token' in error_message.lower() or 'bulunamadı' in error_message.lower()):
                        # DB'yi tekrar kontrol et - belki callback gelmiştir
                        fresh_payment = await db.payments.find_one({"id": payment_id})
                        if fresh_payment and fresh_payment.get("status") in ["completed", "payment_completed", "success"]:
                            logger.info(f"✅ Payment completed via callback (detected after Iyzico error)")
                            return {
                                "payment_id": payment_id,
                                "status": "completed",
                                "event_id": fresh_payment.get("event_id"),
                                "amount": fresh_payment.get("amount"),
                                "updated_at": fresh_payment.get("updated_at")
                            }
                        
                        logger.info(f"⏳ 3DS henüz tamamlanmadı, bekleniyor...")
                        return {
                            "payment_id": payment_id,
                            "status": "waiting_3ds",
                            "event_id": payment.get("event_id"),
                            "amount": payment.get("amount"),
                            "message": "3DS doğrulaması bekleniyor..."
                        }
                    
                    # ✅ BAŞARILI: status=success VE paymentStatus=SUCCESS
                    if iyzico_status == 'success' and payment_status == 'SUCCESS':
                        # Ödeme başarılı - callback işlemlerini yap
                        logger.info(f"✅ İyzico ödeme başarılı (polling ile tespit)")
                        
                        # Payment'ı güncelle
                        await db.payments.update_one(
                            {"id": payment_id},
                            {"$set": {
                                "status": "completed",
                                "iyzico_result": iyzico_result,
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        
                        # Katılımı onayla
                        event_id = payment.get("event_id")
                        user_id = payment.get("user_id")
                        
                        # Event'e katılımcı ekle
                        event = await db.events.find_one({"id": event_id})
                        if event:
                            participants = event.get("participants", [])
                            if user_id not in participants:
                                participants.append(user_id)
                                await db.events.update_one(
                                    {"id": event_id},
                                    {"$set": {
                                        "participants": participants,
                                        "participant_count": len(participants)
                                    }}
                                )
                        
                        # Geçici katılımı onayla
                        await db.event_participations.update_one(
                            {"payment_id": payment_id},
                            {"$set": {"payment_status": "completed"}}
                        )
                        
                        # Bildirimleri gönder
                        await send_payment_notifications(payment, event, current_user)
                        
                        return {
                            "payment_id": payment_id,
                            "status": "completed",
                            "event_id": event_id,
                            "amount": payment.get("amount"),
                            "updated_at": datetime.utcnow().isoformat()
                        }
                    
                    # ⏳ 3DS BEKLENİYOR: status=success ama paymentStatus=FAILURE veya None
                    # Bu durum 3DS doğrulaması henüz tamamlanmamış demek - HATA DEĞİL!
                    elif iyzico_status == 'success' and (payment_status == 'FAILURE' or payment_status is None):
                        logger.info(f"⏳ 3DS doğrulaması devam ediyor (paymentStatus={payment_status})")
                        return {
                            "payment_id": payment_id,
                            "status": "waiting_3ds",
                            "event_id": payment.get("event_id"),
                            "amount": payment.get("amount"),
                            "message": "3DS doğrulaması bekleniyor..."
                        }
                    
                    # ❌ BAŞARISIZ: status=failure (gerçek hata)
                    elif iyzico_status == 'failure':
                        error_msg = iyzico_result.get('errorMessage', 'Ödeme başarısız')
                        logger.error(f"❌ İyzico ödeme başarısız: {error_msg}")
                        await db.payments.update_one(
                            {"id": payment_id},
                            {"$set": {
                                "status": "failed",
                                "error_message": error_msg,
                                "iyzico_result": iyzico_result,
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        return {
                            "payment_id": payment_id,
                            "status": "failed",
                            "event_id": payment.get("event_id"),
                            "error": error_msg
                        }
            except Exception as e:
                logger.error(f"İyzico sorgu hatası: {str(e)}")
        
        return {
            "payment_id": payment_id,
            "status": current_status,
            "event_id": payment.get("event_id"),
            "amount": payment.get("amount"),
            "updated_at": payment.get("updated_at")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking payment status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def send_payment_notifications(payment: dict, event: dict, user: dict):
    """Ödeme başarılı olduğunda bildirimleri gönder"""
    try:
        event_id = payment.get("event_id")
        user_id = payment.get("user_id")
        event_title = event.get('title', event.get('name', 'Etkinlik'))
        
        # 1. Katılımcıya bildirim
        await db.notifications.insert_one({
            "id": f"notif_pmt_{event_id}_{user_id}_{datetime.utcnow().timestamp()}",
            "user_id": user_id,
            "type": "payment_success",
            "title": "✅ Ödeme Başarılı!",
            "message": f"'{event_title}' etkinliğine katılımınız onaylandı. Ödeme: {payment.get('amount', 0)} TL",
            "data": {"event_id": event_id, "payment_id": payment.get("id")},
            "is_read": False,
            "created_at": datetime.utcnow()
        })
        
        # 2. Organizatöre bildirim
        organizer_id = event.get("organizer_id") or event.get("creator_id")
        if organizer_id and organizer_id != user_id:
            await db.notifications.insert_one({
                "id": f"notif_org_{event_id}_{user_id}_{datetime.utcnow().timestamp()}",
                "user_id": organizer_id,
                "type": "new_participant_payment",
                "title": "💰 Yeni Katılımcı",
                "message": f"{user.get('full_name', 'Bir kullanıcı')} '{event_title}' etkinliğine katıldı. Ödeme: {payment.get('amount', 0)} TL",
                "data": {"event_id": event_id, "participant_id": user_id},
                "is_read": False,
                "created_at": datetime.utcnow()
            })
        
        # 3. Admin'e bildirim
        admin = await db.users.find_one({"phone": "+905324900472"})
        if not admin:
            admin = await db.users.find_one({"phone": "905324900472"})
        if not admin:
            admin = await db.users.find_one({"user_type": "super_admin"})
        
        if admin and admin["id"] != user_id:
            await db.notifications.insert_one({
                "id": f"notif_adm_{event_id}_{user_id}_{datetime.utcnow().timestamp()}",
                "user_id": admin["id"],
                "type": "admin_payment",
                "title": "💰 Yeni Etkinlik Ödemesi",
                "message": f"{user.get('full_name', 'Kullanıcı')} - {event_title} - {payment.get('amount', 0)} TL",
                "data": {"event_id": event_id, "payment_id": payment.get("id")},
                "is_read": False,
                "created_at": datetime.utcnow()
            })
        
        logger.info(f"✅ Ödeme bildirimleri gönderildi: {event_id}")
    except Exception as e:
        logger.error(f"Bildirim gönderme hatası: {str(e)}")


@router.post("/events/initialize-payment")
async def initialize_event_payment(
    payment_request: EventPaymentRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Ücretli etkinlik için ödeme başlat
    """
    try:
        event_id = payment_request.event_id
        logger.info(f"💳 Event payment initialization for event: {event_id}, user: {current_user['id']}")
        
        # 1. Etkinliği kontrol et
        event = await db.events.find_one({"id": event_id})
        if not event:
            raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
        
        # Etkinlik ücretli mi?
        ticket_info = event.get("ticket_info")
        if not ticket_info or not ticket_info.get("price") or ticket_info.get("price") <= 0:
            raise HTTPException(status_code=400, detail="Bu etkinlik ücretsizdir")
        
        # Frontend'den gelen toplam fiyatı kullan (çoklu oyun türü seçimi için)
        # Eğer frontend'den total_price geliyorsa onu kullan, yoksa varsayılan event fiyatını kullan
        if payment_request.total_price and payment_request.total_price > 0:
            event_price = payment_request.total_price
            logger.info(f"💰 Using frontend total_price: {event_price} (selected_game_types: {payment_request.selected_game_types})")
        else:
            event_price = ticket_info.get("price", 0)
            logger.info(f"💰 Using default event price: {event_price}")
        
        event_currency = ticket_info.get("currency", "TRY")
        
        # 2. Zaten katılım var mı kontrol et
        existing_participation = await db.event_participants.find_one({
            "event_id": event_id,
            "user_id": current_user["id"]
        })
        
        if existing_participation and existing_participation.get("payment_status") == "completed":
            raise HTTPException(status_code=400, detail="Bu etkinliğe zaten katıldınız")
        
        # 3. Kontenjan kontrolü
        max_participants = event.get("max_participants")
        if max_participants:
            current_count = await db.event_participants.count_documents({
                "event_id": event_id,
                "status": {"$in": ["approved", "confirmed"]}
            })
            if current_count >= max_participants:
                raise HTTPException(status_code=400, detail="Etkinlik kontenjanı doldu")
        
        # 4. Geçici katılım kaydı oluştur (ödeme bekliyor)
        participation_id = str(uuid.uuid4())
        participation = {
            "id": participation_id,
            "event_id": event_id,
            "user_id": current_user["id"],
            "status": "payment_pending",
            "payment_status": "pending",
            "role": "participant",
            "price": event_price,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.event_participants.insert_one(participation)
        logger.info(f"✅ Temporary participation created: {participation_id}")
        
        # 5. Ödeme kaydı oluştur
        payment_id = str(uuid.uuid4())
        payment = {
            "id": payment_id,
            "user_id": current_user["id"],
            "event_id": event_id,
            "participation_id": participation_id,
            "amount": event_price,
            "currency": event_currency,
            "status": "init",
            "payment_method": "iyzico",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.payments.insert_one(payment)
        logger.info(f"💰 Payment record created: {payment_id}")
        
        # 6. İyzico checkout form başlat
        import os
        backend_base_url = os.getenv('BACKEND_BASE_URL', os.getenv('EXPO_PUBLIC_BACKEND_URL', 'https://tourneys-portal.preview.emergentagent.com'))
        callback_url = f"{backend_base_url}/api/events/payment-callback"
        
        logger.info(f"💳 İyzico callback URL: {callback_url}")
        
        # İyzico service kullan - basketId olarak payment_id kullan ki callback'de bulabilelim
        iyzico_service = IyzicoService()
        iyzico_result = iyzico_service.initialize_checkout_form(
            user=current_user,
            amount=event_price,
            related_type="payment",
            related_id=payment_id,
            related_name=event.get("title", "Etkinlik"),
            callback_url=callback_url
        )
        
        if iyzico_result.get('status') == 'success':
            # Payment'ı güncelle
            await db.payments.update_one(
                {"id": payment_id},
                {
                    "$set": {
                        "iyzico_token": iyzico_result.get("token"),
                        "status": "init_3ds",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            # Frontend'e dönülecek URL
            payment_url = iyzico_result.get("paymentPageUrl") or iyzico_result.get("payment_page_url")
            logger.info(f"✅ Returning payment URL to frontend: {payment_url}")
            
            return {
                "success": True,
                "participation_id": participation_id,
                "payment_id": payment_id,
                "payment_page_url": payment_url,
                "event_name": event.get("name"),
                "price": event.get("price", 0),
                "currency": "TRY"
            }
        else:
            error_msg = iyzico_result.get('errorMessage', 'Ödeme başlatılamadı')
            logger.error(f"❌ İyzico error: {error_msg}")
            
            # Geçici kayıtları sil
            await db.event_participants.delete_one({"id": participation_id})
            await db.payments.delete_one({"id": payment_id})
            
            raise HTTPException(status_code=500, detail=error_msg)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Event payment initialization error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/events/payment-callback", include_in_schema=True)
@router.post("/events/payment-callback/", include_in_schema=False)
@router.get("/events/payment-callback", include_in_schema=True)
@router.get("/events/payment-callback/", include_in_schema=False)
async def event_payment_callback(request: Request):
    """
    İyzico payment callback for events
    """
    try:
        # Form data al
        form_data = await request.form()
        token = form_data.get("token")
        
        logger.info(f"💳 Event payment callback received - Token: {token}")
        
        if not token:
            logger.error("❌ No token in callback")
            return {"status": "error", "message": "Token bulunamadı"}
        
        # İyzico'dan ödeme sonucunu al
        iyzico_service = IyzicoService()
        payment_result = iyzico_service.retrieve_checkout_form_result(token)
        
        logger.info(f"💳 İyzico result status: {payment_result.get('status')}")
        logger.info(f"💳 Payment status: {payment_result.get('paymentStatus')}")
        
        if payment_result.get('status') == 'success' and payment_result.get('paymentStatus') == 'SUCCESS':
            # Payment ID'yi bul - basketId'den prefix'i temizle
            basket_id = payment_result.get('basketId')
            logger.info(f"💳 Received basketId: {basket_id}")
            
            # "payment_" prefix'ini kaldır
            if basket_id.startswith("payment_"):
                payment_id = basket_id.replace("payment_", "", 1)
            else:
                payment_id = basket_id
            
            logger.info(f"💳 Searching for payment_id: {payment_id}")
            payment = await db.payments.find_one({"id": payment_id})
            
            if not payment:
                logger.error(f"❌ Payment not found with id: {payment_id} (original basketId: {basket_id})")
                return {"status": "error", "message": "Ödeme kaydı bulunamadı"}
            
            participation_id = payment.get("participation_id")
            event_id = payment.get("event_id")
            user_id = payment.get("user_id")
            
            logger.info(f"✅ Payment success - Participation: {participation_id}")
            
            # 1. PAYMENT'I UPDATE ET
            await db.payments.update_one(
                {"id": payment_id},  # ← payment_id kullan (parse edilmiş hali), basket_id değil!
                {
                    "$set": {
                        "status": "completed",
                        "payment_status": "completed",
                        "iyzico_payment_id": payment_result.get('paymentId'),
                        "paid_price": payment_result.get('paidPrice'),
                        "completed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            logger.info(f"✅ Payment updated to completed: {payment_id}")
            
            # 2. PARTICIPATION'I ONAYLA (event_participants tablosu)
            await db.event_participants.update_one(
                {"id": participation_id},
                {
                    "$set": {
                        "status": "confirmed",
                        "payment_status": "completed",
                        "confirmed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            logger.info("✅ Participation confirmed in event_participants")
            
            # 2b. PARTICIPATIONS TABLOSUNU DA GÜNCELLE (varsa)
            await db.participations.update_one(
                {"id": participation_id},
                {
                    "$set": {
                        "status": "confirmed",
                        "payment_status": "completed",
                        "confirmed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            logger.info("✅ Participation confirmed in participations")
            
            # 2c. ETKİNLİĞİN KATILIMCI SAYISINI ARTIR
            await db.events.update_one(
                {"id": event_id},
                {
                    "$inc": {"participant_count": 1},
                    "$push": {"participants": user_id}
                }
            )
            logger.info(f"✅ Event participant_count incremented for event: {event_id}")
            
            # Event bilgilerini al
            event = await db.events.find_one({"id": event_id})
            user = await db.users.find_one({"id": user_id})
            
            # 3. KULLANICININ AJANDASINA EKLE
            calendar_item_id = f"cal_{str(uuid.uuid4())}"
            calendar_item = {
                "id": calendar_item_id,
                "user_id": user_id,
                "type": "event",
                "event_id": event_id,
                "title": f"Etkinlik: {event.get('name', 'Bilinmiyor')}",
                "description": f"Katılım onaylandı. Tutar: {payment_result.get('paidPrice', 0)} TL",
                "date": event.get("start_date"),
                "start_time": event.get("start_time"),
                "end_time": event.get("end_time"),
                "location": event.get("location", "Belirtilmedi"),
                "is_read": False,
                "created_at": datetime.utcnow()
            }
            await db.calendar_items.insert_one(calendar_item)
            logger.info(f"📅 Calendar item added for user: {user_id}")
            
            # 4. KATILIMCIYA BİLDİRİM
            participant_notification = {
                "id": f"notif_{participation_id}_participant",
                "user_id": user_id,
                "type": "event_participation_confirmed",
                "title": "✅ Ödeme Başarılı!",
                "message": f"'{event.get('title', 'Etkinlik')}' etkinliğine başarıyla katıldınız. Ödeme tutarı: {payment_result.get('paidPrice', 0)} TL",
                "data": {
                    "event_id": event_id,
                    "participation_id": participation_id,
                    "amount": payment_result.get('paidPrice', 0)
                },
                "is_read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(participant_notification)
            logger.info(f"🔔 Participant notification sent: {user_id}")
            
            # 5. ORGANİZATÖRE BİLDİRİM
            organizer_id = event.get("organizer_id")
            if organizer_id and organizer_id != user_id:  # Kendisi organizatörse bildirim gönderme
                organizer_notification = {
                    "id": f"notif_{participation_id}_organizer",
                    "user_id": organizer_id,
                    "type": "event_payment",
                    "title": "💰 Yeni Katılımcı",
                    "message": f"{user.get('full_name', 'Bir kullanıcı')} '{event.get('title', 'Etkinlik')}' etkinliğinize ödeme yaparak katıldı. Tutar: {payment_result.get('paidPrice', 0)} TL",
                    "data": {
                        "event_id": event_id,
                        "participation_id": participation_id,
                        "user_id": user_id,
                        "amount": payment_result.get('paidPrice', 0)
                    },
                    "is_read": False,
                    "created_at": datetime.utcnow()
                }
                await db.notifications.insert_one(organizer_notification)
                logger.info(f"🔔 Organizer notification sent: {organizer_id}")
            
            # 6. ADMIN'E BİLDİRİM
            admin = await db.users.find_one({"phone": "+905324900472"})
            if not admin:
                admin = await db.users.find_one({"phone": "905324900472"})
            if not admin:
                admin = await db.users.find_one({"user_type": "super_admin"})
            if not admin:
                admin = await db.users.find_one({"user_type": "admin"})
            
            if admin:
                admin_notification = {
                    "id": f"notif_{participation_id}_admin",
                    "user_id": admin["id"],
                    "type": "admin_event_payment",
                    "title": "💰 Yeni Etkinlik Ödemesi",
                    "message": f"{event.get('name', 'Etkinlik')} - {user.get('full_name', 'Kullanıcı')} ödeme yaptı: {payment_result.get('paidPrice', 0)} TL",
                    "data": {
                        "event_id": event_id,
                        "participation_id": participation_id,
                        "user_id": user_id,
                        "amount": payment_result.get('paidPrice', 0)
                    },
                    "is_read": False,
                    "created_at": datetime.utcnow()
                }
                await db.notifications.insert_one(admin_notification)
                logger.info(f"👨‍💼 Admin notification sent: {admin['id']}")
            
            # Ödeme başarılı log'u
            try:
                from auth_endpoints import log_user_activity
                await log_user_activity(user_id, "payment_success", "success", {
                    "payment_id": payment_id,
                    "payment_type": "event_participation",
                    "event_id": event_id,
                    "event_title": event.get("title", "Etkinlik"),
                    "amount": payment_result.get('paidPrice', 0),
                    "currency": "TRY"
                })
            except Exception as log_err:
                logger.error(f"Log error: {log_err}")
            
            # Frontend'e HTML sayfası döndür (postMessage ile parent'a bildir)
            from fastapi.responses import HTMLResponse
            success_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Ödeme Başarılı</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background-color: #121212;
                        color: white;
                        text-align: center;
                    }}
                    .container {{
                        padding: 40px;
                    }}
                    .success-icon {{
                        font-size: 80px;
                        margin-bottom: 20px;
                    }}
                    h1 {{ color: #4CAF50; margin-bottom: 10px; }}
                    p {{ color: #888; font-size: 16px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="success-icon">✅</div>
                    <h1>Ödeme Başarılı!</h1>
                    <p>Etkinliğe katılımınız onaylandı.</p>
                    <p>Bu pencere birkaç saniye içinde kapanacak...</p>
                </div>
                <script>
                    // Parent window'a mesaj gönder
                    try {{
                        if (window.parent && window.parent !== window) {{
                            window.parent.postMessage({{
                                type: 'PAYMENT_SUCCESS',
                                eventId: '{event_id}',
                                status: 'success'
                            }}, '*');
                        }}
                        if (window.opener) {{
                            window.opener.postMessage({{
                                type: 'PAYMENT_SUCCESS',
                                eventId: '{event_id}',
                                status: 'success'
                            }}, '*');
                            setTimeout(function() {{ window.close(); }}, 2000);
                        }}
                    }} catch (e) {{
                        console.log('PostMessage error:', e);
                    }}
                    // 3 saniye sonra etkinlik sayfasına yönlendir
                    setTimeout(function() {{
                        window.location.href = '{frontend_url}/event/{event_id}?payment=success';
                    }}, 3000);
                </script>
            </body>
            </html>
            """
            logger.info(f"✅ Returning success HTML for event: {event_id}")
            return HTMLResponse(content=success_html)
            
        else:
            # Ödeme başarısız
            error_message = payment_result.get('errorMessage', 'Ödeme başarısız')
            logger.error(f"❌ Payment failed: {error_message}")
            
            # Frontend'e HTML sayfası döndür
            from fastapi.responses import HTMLResponse
            frontend_url = os.getenv('FRONTEND_URL', 'https://tourneys-portal.preview.emergentagent.com')
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Ödeme Başarısız</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background-color: #121212;
                        color: white;
                        text-align: center;
                    }}
                    .container {{
                        padding: 40px;
                    }}
                    .error-icon {{
                        font-size: 80px;
                        margin-bottom: 20px;
                    }}
                    h1 {{ color: #f44336; margin-bottom: 10px; }}
                    p {{ color: #888; font-size: 16px; }}
                    .error-detail {{ color: #ff9800; font-size: 14px; margin-top: 10px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="error-icon">❌</div>
                    <h1>Ödeme Başarısız</h1>
                    <p>Ödeme işlemi tamamlanamadı.</p>
                    <p class="error-detail">{error_message}</p>
                    <p>Bu pencere birkaç saniye içinde kapanacak...</p>
                </div>
                <script>
                    // Parent window'a mesaj gönder
                    try {{
                        if (window.parent && window.parent !== window) {{
                            window.parent.postMessage({{
                                type: 'PAYMENT_FAILED',
                                error: '{error_message}',
                                status: 'failed'
                            }}, '*');
                        }}
                        if (window.opener) {{
                            window.opener.postMessage({{
                                type: 'PAYMENT_FAILED',
                                error: '{error_message}',
                                status: 'failed'
                            }}, '*');
                            setTimeout(function() {{ window.close(); }}, 2000);
                        }}
                    }} catch (e) {{
                        console.log('PostMessage error:', e);
                    }}
                    // 3 saniye sonra ana sayfaya yönlendir
                    setTimeout(function() {{
                        window.location.href = '{frontend_url}/?payment=failed';
                    }}, 3000);
                </script>
            </body>
            </html>
            """
            logger.info(f"❌ Returning error HTML: {error_message}")
            return HTMLResponse(content=error_html)
            
    except Exception as e:
        logger.error(f"❌ Payment callback error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        from fastapi.responses import HTMLResponse
        frontend_url = os.getenv('FRONTEND_URL', 'https://tourneys-portal.preview.emergentagent.com')
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Ödeme Hatası</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background-color: #121212;
                    color: white;
                    text-align: center;
                }}
                .container {{
                    padding: 40px;
                }}
                .error-icon {{
                    font-size: 80px;
                    margin-bottom: 20px;
                }}
                h1 {{ color: #f44336; margin-bottom: 10px; }}
                p {{ color: #888; font-size: 16px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error-icon">⚠️</div>
                <h1>Ödeme Hatası</h1>
                <p>Bir hata oluştu. Lütfen tekrar deneyin.</p>
            </div>
            <script>
                try {{
                    if (window.parent && window.parent !== window) {{
                        window.parent.postMessage({{
                            type: 'PAYMENT_ERROR',
                            status: 'error'
                        }}, '*');
                    }}
                }} catch (e) {{
                    console.log('PostMessage error:', e);
                }}
                setTimeout(function() {{
                    window.location.href = '{frontend_url}/?payment=error';
                }}, 3000);
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html)
