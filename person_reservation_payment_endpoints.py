from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
import uuid
import logging
from pydantic import BaseModel

from auth import get_current_user
from iyzico_service import IyzicoService
from notification_endpoints import create_notification_helper

# Setup
router = APIRouter()
logger = logging.getLogger(__name__)

# Database
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8001")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# İyzico service
iyzico_service = IyzicoService()


@router.post("/person-reservations/{reservation_id}/reject")
async def reject_person_reservation(
    reservation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Oyuncu/Antrenör/Hakem rezervasyonunu reddet
    """
    try:
        logger.info(f"❌ Reservation rejection - User: {current_user['id']}, Reservation: {reservation_id}")
        
        # Rezervasyonu bul
        reservation = await db.reservations.find_one({"id": reservation_id})
        if not reservation:
            raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
        
        # Rezervasyon tipi (hem "type" hem "reservation_type" field'larını kontrol et)
        reservation_type = reservation.get("reservation_type") or reservation.get("type")
        
        if not reservation_type:
            logger.error(f"❌ Reservation has no type field: {reservation}")
            raise HTTPException(status_code=400, detail="Rezervasyon tipi bulunamadı")
        
        person_id_field = f"{reservation_type}_id"
        person_id = reservation.get(person_id_field)
        
        if not person_id:
            logger.error(f"❌ Person ID not found. Type: {reservation_type}, Field: {person_id_field}")
            raise HTTPException(status_code=400, detail=f"{reservation_type}_id bulunamadı")
        
        # Sadece ilgili kişi (oyuncu/antrenör/hakem) reddedebilir
        if person_id != current_user["id"]:
            raise HTTPException(status_code=403, detail="Bu rezervasyonu reddetme yetkiniz yok")
        
        # Rezervasyonu reddet
        await db.reservations.update_one(
            {"id": reservation_id},
            {
                "$set": {
                    "status": "rejected",
                    "rejected_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )
        
        # Rezervasyon yapan kişiye bildirim gönder
        requester_id = reservation.get("user_id")
        
        # CRITICAL: user_id bazen dictionary olabiliyor
        if isinstance(requester_id, dict):
            logger.warning(f"⚠️ requester_id is dict, extracting id: {requester_id}")
            requester_id = requester_id.get("id")
        
        if not requester_id:
            logger.error(f"❌ Requester ID not found in reservation: {reservation}")
            raise HTTPException(status_code=400, detail="Rezervasyonu yapan kişi bulunamadı")
        
        person = await db.users.find_one({"id": person_id})
        if not person:
            logger.error(f"❌ Person user not found: {person_id}")
            raise HTTPException(status_code=404, detail="Hizmet sağlayıcı bulunamadı")
        
        person_type_tr = {
            "player": "Oyuncu",
            "coach": "Antrenör",
            "referee": "Hakem"
        }
        type_name = person_type_tr.get(reservation_type, "Kişi")
        
        await create_notification_helper(
            db=db,
            notification_data={
                "user_id": requester_id,
                "notification_type": "reservation_rejected",
                "title": f"{type_name} Rezervasyonunuz Reddedildi",
                "message": f"{person.get('full_name')} rezervasyonunuzu reddetti.",
                "related_type": "reservation",
                "related_id": reservation_id,
                "is_read": False,
                "data": {
                    "reservation_id": reservation_id,
                    "type": reservation_type,
                    "person_name": person.get("full_name"),
                }
            }
        )
        
        logger.info(f"❌ Reservation rejected - Reservation: {reservation_id}")
        
        return {
            "success": True,
            "message": "Rezervasyon reddedildi",
            "reservation_id": reservation_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Rejection error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/person-reservations/{reservation_id}/approve")
async def approve_person_reservation(
    reservation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Oyuncu/Antrenör/Hakem rezervasyonunu onayla
    """
    try:
        logger.info(f"✅ Reservation approval - User: {current_user['id']}, Reservation: {reservation_id}")
        
        # Rezervasyonu bul
        reservation = await db.reservations.find_one({"id": reservation_id})
        if not reservation:
            raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
        
        # Rezervasyon tipi (hem "type" hem "reservation_type" field'larını kontrol et)
        reservation_type = reservation.get("reservation_type") or reservation.get("type")
        
        if not reservation_type:
            logger.error(f"❌ Reservation has no type field: {reservation}")
            raise HTTPException(status_code=400, detail="Rezervasyon tipi bulunamadı")
        
        person_id_field = f"{reservation_type}_id"
        person_id = reservation.get(person_id_field)
        
        if not person_id:
            logger.error(f"❌ Person ID not found. Type: {reservation_type}, Field: {person_id_field}, Reservation: {reservation}")
            raise HTTPException(status_code=400, detail=f"{reservation_type}_id bulunamadı")
        
        # Sadece ilgili kişi (oyuncu/antrenör/hakem) onaylayabilir
        if person_id != current_user["id"]:
            raise HTTPException(status_code=403, detail="Bu rezervasyonu onaylama yetkiniz yok")
        
        # Zaten onaylanmış mı?
        if reservation.get("status") == "approved":
            raise HTTPException(status_code=400, detail="Bu rezervasyon zaten onaylandı")
        
        # Rezervasyonu onayla
        await db.reservations.update_one(
            {"id": reservation_id},
            {
                "$set": {
                    "status": "approved",
                    "approved_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )
        
        # Rezervasyon yapan kişiye bildirim gönder (ödeme linki ile)
        requester_id = reservation.get("user_id")
        if not requester_id:
            logger.error(f"❌ Requester ID not found in reservation: {reservation}")
            raise HTTPException(status_code=400, detail="Rezervasyonu yapan kişi bulunamadı")
        
        # CRITICAL: user_id bazen dictionary olabiliyor (Pydantic validation hatası)
        # Örnek: {"id": "...", "user_type": "..."}
        if isinstance(requester_id, dict):
            logger.warning(f"⚠️ requester_id is dict, extracting id: {requester_id}")
            requester_id = requester_id.get("id")
            if not requester_id:
                logger.error(f"❌ Could not extract id from dict: {reservation.get('user_id')}")
                raise HTTPException(status_code=400, detail="Rezervasyonu yapan kişi ID'si bulunamadı")
        
        requester = await db.users.find_one({"id": requester_id})
        if not requester:
            logger.error(f"❌ Requester user not found: {requester_id}")
            raise HTTPException(status_code=404, detail="Rezervasyonu yapan kullanıcı bulunamadı")
        
        person = await db.users.find_one({"id": person_id})
        if not person:
            logger.error(f"❌ Person (provider) user not found: {person_id}")
            raise HTTPException(status_code=404, detail="Hizmet sağlayıcı kullanıcı bulunamadı")
        
        person_type_tr = {
            "player": "Oyuncu",
            "coach": "Antrenör",
            "referee": "Hakem"
        }
        type_name = person_type_tr.get(reservation_type, "Kişi")
        
        # 1. Talep edene bildirim (ödeme linki ile)
        await create_notification_helper(
            db=db,
            notification_data={
                "user_id": requester_id,
                "notification_type": "reservation_approved",
                "title": f"{type_name} Rezervasyonunuz Onaylandı!",
                "message": f"{person.get('full_name')} rezervasyonunuzu onayladı. Ödeme yapmak için bildirime tıklayın. Tutar: ₺{reservation.get('total_price', 0):.2f}",
                "related_type": "reservation",
                "related_id": reservation_id,
                "is_read": False,
                "data": {
                    "reservation_id": reservation_id,
                    "type": reservation_type,
                    "action": "payment_required",
                    "person_name": person.get("full_name"),
                    "total_price": reservation.get("total_price"),
                    "date": reservation.get("date") or reservation.get("selected_date"),
                    "hour": reservation.get("hour") or reservation.get("selected_hour")
                }
            }
        )
        
        # 2. Yöneticiye bildirim
        admin_users = await db.users.find({"user_type": {"$in": ["admin", "super_admin"]}}).to_list(length=100)
        for admin in admin_users:
            await create_notification_helper(
                db=db,
                notification_data={
                    "user_id": admin["id"],
                    "notification_type": "reservation_approved_admin",
                    "title": f"Rezervasyon Onaylandı - {type_name}",
                    "message": f"{person.get('full_name')} rezervasyonu onayladı. Talep eden: {requester.get('full_name')}. Tutar: ₺{reservation.get('total_price', 0):.2f}",
                    "related_type": "reservation",
                    "related_id": reservation_id,
                    "is_read": False,
                    "data": {
                        "reservation_id": reservation_id,
                        "type": reservation_type,
                        "provider_name": person.get("full_name"),
                        "requester_name": requester.get("full_name"),
                        "total_price": reservation.get("total_price"),
                        "date": reservation.get("date") or reservation.get("selected_date"),
                        "hour": reservation.get("hour") or reservation.get("selected_hour")
                    }
                }
            )
        
        logger.info(f"✅ Reservation approved - Notifications sent to requester and {len(admin_users)} admins - Reservation: {reservation_id}")
        
        return {
            "success": True,
            "message": "Rezervasyon onaylandı",
            "reservation_id": reservation_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Approval error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/person-reservations/initiate-payment")
async def initiate_person_reservation_payment(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Oyuncu/Antrenör/Hakem rezervasyonu için ödeme başlat
    """
    try:
        # Request body'den reservation_id al
        body = await request.json()
        reservation_id = body.get("reservation_id")
        
        if not reservation_id:
            raise HTTPException(status_code=400, detail="reservation_id gerekli")
        
        logger.info(f"💳 Person Reservation Payment - User: {current_user['id']}, Reservation: {reservation_id}")
        
        # Rezervasyonu bul
        reservation = await db.reservations.find_one({"id": reservation_id})
        if not reservation:
            raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
        
        # Rezervasyon sahibi kontrolü
        requester_id = reservation.get("user_id")
        
        # CRITICAL: user_id bazen dictionary olabiliyor
        if isinstance(requester_id, dict):
            requester_id = requester_id.get("id")
        
        if requester_id != current_user["id"]:
            raise HTTPException(status_code=403, detail="Bu rezervasyon size ait değil")
        
        # Zaten ödenmiş mi?
        if reservation.get("payment_status") == "paid":
            raise HTTPException(status_code=400, detail="Bu rezervasyon zaten ödendi")
        
        # Rezervasyon tipi (hem "type" hem "reservation_type" field'larını kontrol et)
        reservation_type = reservation.get("type") or reservation.get("reservation_type")
        
        if not reservation_type:
            logger.error(f"❌ Reservation has no type field: {reservation}")
            raise HTTPException(status_code=400, detail="Rezervasyon tipi bulunamadı")
        
        person_id = reservation.get(f"{reservation_type}_id")
        
        if not person_id:
            logger.error(f"❌ Person ID not found. Type: {reservation_type}, Reservation: {reservation}")
            raise HTTPException(status_code=400, detail=f"{reservation_type}_id bulunamadı")
        
        # Kişiyi bul (oyuncu/antrenör/hakem)
        person = await db.users.find_one({"id": person_id})
        if not person:
            logger.error(f"❌ Person not found: {person_id}")
            raise HTTPException(status_code=404, detail=f"{reservation_type.title()} bulunamadı")
        
        # Fiyat bilgisi
        total_price = reservation.get("total_price", 0)
        if total_price <= 0:
            raise HTTPException(status_code=400, detail="Geçersiz fiyat")
        
        # Transaction oluştur
        transaction_id = str(uuid.uuid4())
        transaction = {
            "id": transaction_id,
            "reservation_id": reservation_id,
            "reservation_type": reservation_type,
            "buyer_id": current_user["id"],
            "seller_id": person_id,
            "total_amount": total_price,
            "commission_rate": 0.10,  # %10 komisyon
            "commission_amount": total_price * 0.10,
            "seller_receives": total_price * 0.90,
            "payment_status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        await db.person_reservation_transactions.insert_one(transaction)
        
        # Buyer bilgileri
        buyer_name = current_user.get("full_name", "Kullanıcı")
        buyer_email = current_user.get("email", "noreply@sportpazar.com")
        buyer_phone = current_user.get("phone", "+905555555555")
        
        # Seller bilgileri
        seller_name = person.get("full_name", "Satıcı")
        
        # Item bilgisi
        person_type_tr = {
            "player": "Oyuncu",
            "coach": "Antrenör",
            "referee": "Hakem"
        }
        item_name = f"{person_type_tr.get(reservation_type, 'Kişi')} Rezervasyonu - {seller_name}"
        
        # Callback URL
        callback_url = f"{BACKEND_BASE_URL}/api/person-reservations/payment-callback"
        
        # Iyzico ödeme başlat
        # Kullanıcı bilgilerini hazırla
        user_dict = {
            "id": current_user["id"],
            "full_name": buyer_name,
            "email": buyer_email,
            "phone_number": buyer_phone,
            "tc_kimlik": current_user.get("tckn", "11111111111"),
            "created_at": current_user.get("created_at")
        }
        
        payment_result = iyzico_service.initialize_checkout_form(
            user=user_dict,
            amount=total_price,
            related_type="person_reservation",
            related_id=transaction_id,  # ✅ transaction_id gönder (reservation_id değil!)
            related_name=item_name,
            callback_url=callback_url
        )
        
        if payment_result.get("status") != "success":
            raise HTTPException(
                status_code=400,
                detail=payment_result.get("error_message", "Ödeme başlatılamadı")
            )
        
        # Transaction güncelle
        await db.person_reservation_transactions.update_one(
            {"id": transaction_id},
            {
                "$set": {
                    "iyzico_token": payment_result.get("token"),
                    "payment_page_url": payment_result.get("payment_page_url"),
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )
        
        logger.info(f"✅ Payment initialized - Transaction: {transaction_id}")
        
        return {
            "success": True,
            "transaction_id": transaction_id,
            "payment_page_url": payment_result.get("payment_page_url"),
            "checkout_form_content": payment_result.get("checkout_form_content"),
            "price_breakdown": {
                "total": total_price,
                "commission": transaction["commission_amount"],
                "seller_receives": transaction["seller_receives"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Payment initialization error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/person-reservations/payment-callback")
async def person_reservation_payment_callback(request: Request):
    """
    Iyzico ödeme callback endpoint'i
    """
    try:
        # Form data al
        form_data = await request.form()
        token = form_data.get("token")
        
        if not token:
            raise HTTPException(status_code=400, detail="Token bulunamadı")
        
        logger.info(f"💳 Payment Callback - Token: {token}")
        
        # Iyzico'dan ödeme sonucunu al
        payment_result = iyzico_service.retrieve_checkout_form_result(token)
        
        if payment_result.get("status") != "success":
            logger.error(f"❌ Payment failed: {payment_result.get('error_message')}")
            raise HTTPException(status_code=400, detail="Ödeme başarısız")
        
        payment_status = payment_result.get("paymentStatus")
        # İyzico conversation_id'yi basketId olarak döndürüyor
        basket_id = payment_result.get("basketId") or payment_result.get("conversationId")
        
        logger.info(f"💳 Callback - PaymentStatus: {payment_status}, BasketId: {basket_id}")
        
        if not basket_id:
            logger.error(f"❌ BasketId not found in payment_result: {payment_result}")
            raise HTTPException(status_code=400, detail="BasketId bulunamadı")
        
        # basketId formatı: "person_reservation_{transaction_id}"
        # transaction_id'yi extract et
        if "_" in basket_id:
            transaction_id = basket_id.split("_", 2)[-1]  # Son kısmı al
        else:
            transaction_id = basket_id
        
        logger.info(f"💳 Extracted transaction_id: {transaction_id}")
        
        # Transaction'ı bul
        transaction = await db.person_reservation_transactions.find_one({"id": transaction_id})
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction bulunamadı")
        
        # Payment durumu kontrolü
        if payment_status == "SUCCESS":
            # Transaction güncelle
            await db.person_reservation_transactions.update_one(
                {"id": transaction_id},
                {
                    "$set": {
                        "payment_status": "completed",  # ✅ Frontend 'completed' bekliyor
                        "iyzico_payment_id": payment_result.get("payment_id"),
                        "paid_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat()
                    }
                }
            )
            
            # Rezervasyonu güncelle
            reservation_id = transaction.get("reservation_id")
            await db.reservations.update_one(
                {"id": reservation_id},
                {
                    "$set": {
                        "payment_status": "completed",  # ✅ Frontend 'completed' bekliyor
                        "status": "confirmed",
                        "paid_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat()
                    }
                }
            )
            
            # Reservation detaylarını al
            reservation = await db.reservations.find_one({"id": reservation_id})
            
            # Bildirim gönder
            await send_person_reservation_notifications(
                db=db,
                reservation=reservation,
                transaction=transaction
            )
            
            # Her iki taraf için de calendar'a unread badge ekle
            await add_calendar_items_for_reservation(db, reservation)
            
            logger.info(f"✅ Payment SUCCESS - Transaction: {transaction_id}")
            
            # HTML redirect döndür (İyzico bunu bekliyor)
            from fastapi.responses import HTMLResponse
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Ödeme Başarılı</title>
                <script>
                    // Mobile app için postMessage
                    if (window.ReactNativeWebView) {{
                        window.ReactNativeWebView.postMessage(JSON.stringify({{
                            success: true,
                            reservationId: '{reservation_id}'
                        }}));
                    }}
                    // Web için redirect
                    setTimeout(function() {{
                        window.location.href = '/reservations/payment-success?reservationId={reservation_id}';
                    }}, 1000);
                </script>
            </head>
            <body>
                <h2>Ödeme Başarılı ✅</h2>
                <p>Rezervasyonunuz onaylandı. Ajandanıza yönlendiriliyorsunuz...</p>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content)
        else:
            logger.error(f"❌ Payment FAILED - Status: {payment_status}")
            
            # HTML error döndür
            from fastapi.responses import HTMLResponse
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Ödeme Başarısız</title>
                <script>
                    if (window.ReactNativeWebView) {
                        window.ReactNativeWebView.postMessage(JSON.stringify({
                            success: false,
                            error: 'Ödeme başarısız'
                        }));
                    }
                    setTimeout(function() {
                        window.history.back();
                    }, 2000);
                </script>
            </head>
            <body>
                <h2>Ödeme Başarısız ❌</h2>
                <p>Ödeme işlemi tamamlanamadı. Lütfen tekrar deneyin.</p>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Callback error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def send_person_reservation_notifications(db, reservation: dict, transaction: dict):
    """
    Rezervasyon bildirimlerini gönder
    """
    try:
        reservation_type = reservation.get("type") or reservation.get("reservation_type")
        buyer_id = reservation.get("user_id")
        
        # CRITICAL: IDs bazen dict olabiliyor
        if isinstance(buyer_id, dict):
            buyer_id = buyer_id.get("id")
        
        seller_id = reservation.get(f"{reservation_type}_id")
        if isinstance(seller_id, dict):
            seller_id = seller_id.get("id")
        
        # Kullanıcı bilgilerini al
        buyer = await db.users.find_one({"id": buyer_id}) if buyer_id else None
        seller = await db.users.find_one({"id": seller_id}) if seller_id else None
        
        if not buyer or not seller:
            logger.error(f"❌ Buyer or Seller not found. Buyer ID: {buyer_id}, Seller ID: {seller_id}")
            return
        
        person_type_tr = {
            "player": "Oyuncu",
            "coach": "Antrenör",
            "referee": "Hakem"
        }
        type_name = person_type_tr.get(reservation_type, "Kişi")
        
        # 1. Alıcıya bildirim
        await create_notification_helper(
            db=db,
            notification_data={
                "user_id": buyer_id,
                "notification_type": "reservation_confirmed",
                "title": "Rezervasyon Onaylandı!",
                "message": f"{type_name} rezervasyonunuz onaylandı. {seller.get('full_name')} - Tarih: {reservation.get('date')} {reservation.get('hour')}",
                "related_type": "reservation",
                "related_id": reservation.get("id"),
                "is_read": False,
                "data": {
                    "reservation_id": reservation.get("id"),
                    "type": reservation_type,
                    "seller_name": seller.get("full_name"),
                    "seller_phone": seller.get("phone"),
                    "date": reservation.get("date"),
                    "hour": reservation.get("hour"),
                    "total_paid": transaction.get("total_amount")
                }
            }
        )
        
        # 2. Satıcıya bildirim
        await create_notification_helper(
            db=db,
            notification_data={
                "user_id": seller_id,
                "notification_type": "reservation_received",
                "title": "Yeni Rezervasyon!",
                "message": f"Yeni rezervasyon aldınız! Müşteri: {buyer.get('full_name')}. Tarih: {reservation.get('date')} {reservation.get('hour')}. Kazanç: ₺{transaction.get('seller_receives'):.2f}",
                "related_type": "reservation",
                "related_id": reservation.get("id"),
                "is_read": False,
                "data": {
                    "reservation_id": reservation.get("id"),
                    "type": reservation_type,
                    "buyer_name": buyer.get("full_name"),
                    "buyer_phone": buyer.get("phone"),
                    "date": reservation.get("date"),
                    "hour": reservation.get("hour"),
                    "seller_receives": transaction.get("seller_receives"),
                    "commission": transaction.get("commission_amount")
                }
            }
        )
        
        # 3. Tüm adminlere bildirim
        admins = await db.users.find({"user_type": {"$in": ["admin", "super_admin"]}}).to_list(100)
        for admin in admins:
            await create_notification_helper(
                db=db,
                notification_data={
                    "user_id": admin["id"],
                    "notification_type": "reservation_admin",
                    "title": f"Yeni {type_name} Rezervasyonu",
                    "message": f"{type_name} rezervasyonu: {buyer.get('full_name')} → {seller.get('full_name')}. Komisyon: ₺{transaction.get('commission_amount'):.2f}",
                    "related_type": "reservation",
                    "related_id": reservation.get("id"),
                    "is_read": False,
                    "data": {
                        "reservation_id": reservation.get("id"),
                        "type": reservation_type,
                        "buyer_name": buyer.get("full_name"),
                        "seller_name": seller.get("full_name"),
                        "commission": transaction.get("commission_amount"),
                        "total_amount": transaction.get("total_amount")
                    }
                }
            )
        
        logger.info(f"📧 Notifications sent: Buyer, Seller, {len(admins)} Admins")
        
    except Exception as e:
        logger.error(f"❌ Notification error: {str(e)}")



async def add_calendar_items_for_reservation(db, reservation: dict):
    """
    Ödeme tamamlandığında her iki taraf için calendar'a unread badge ekle
    """
    try:
        reservation_type = reservation.get("type") or reservation.get("reservation_type")
        buyer_id = reservation.get("user_id")
        seller_id_field = f"{reservation_type}_id"
        seller_id = reservation.get(seller_id_field)
        
        # CRITICAL: user_id bazen dictionary olabiliyor, extract et
        if isinstance(buyer_id, dict):
            buyer_id = buyer_id.get("id")
        if isinstance(seller_id, dict):
            seller_id = seller_id.get("id")
        
        reservation_id = reservation.get("id")
        reservation_date = reservation.get("date") or reservation.get("selected_date")
        reservation_hour = reservation.get("hour") or reservation.get("selected_hour")
        
        # 1. Talep edene (alıcıya) calendar item ekle
        calendar_item_buyer = {
            "id": str(uuid.uuid4()),
            "user_id": buyer_id,  # ✅ Artık string
            "reservation_id": reservation_id,
            "type": "reservation_out",  # Giden rezervasyon
            "title": f"{reservation_type.capitalize()} Rezervasyonu",
            "date": reservation_date,
            "hour": reservation_hour,
            "is_read": False,  # Okunmadı badge için
            "created_at": datetime.utcnow().isoformat()
        }
        await db.calendar_items.insert_one(calendar_item_buyer)
        
        # 2. Hizmet sağlayıcıya calendar item ekle
        calendar_item_seller = {
            "id": str(uuid.uuid4()),
            "user_id": seller_id,
            "reservation_id": reservation_id,
            "type": "reservation_in",  # Gelen rezervasyon
            "title": f"{reservation_type.capitalize()} Rezervasyonu",
            "date": reservation_date,
            "hour": reservation_hour,
            "is_read": False,  # Okunmadı badge için
            "created_at": datetime.utcnow().isoformat()
        }
        await db.calendar_items.insert_one(calendar_item_seller)
        
        logger.info(f"📅 Calendar items created for reservation {reservation_id} - Buyer: {buyer_id}, Seller: {seller_id}")
        
    except Exception as e:
        logger.error(f"❌ Calendar item creation error: {str(e)}")
