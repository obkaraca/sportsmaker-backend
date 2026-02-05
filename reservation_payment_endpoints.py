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
from workflow_endpoints import trigger_workflow

# Setup
router = APIRouter()
logger = logging.getLogger(__name__)

# Database
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# İyzico service
iyzico_service = IyzicoService()


class ReservationPaymentRequest(BaseModel):
    facility_id: str
    field_id: str
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM
    end_time: str  # HH:MM
    time_slots: list[str]  # ["14:00", "15:00", "16:00"]
    notes: Optional[str] = ""
    # Promo code fields
    promo_code: Optional[str] = None
    promo_discount: Optional[float] = 0
    discount_amount: Optional[float] = 0
    original_price: Optional[float] = None
    total_price: Optional[float] = None


@router.post("/reservations/initialize-payment")
async def initialize_reservation_payment(
    payment_request: ReservationPaymentRequest,
    current_user: dict = Depends(get_current_user),
    request: Request = None
):
    """Rezervasyon için ödeme başlat (iyzico checkout)"""
    try:
        logger.info(f"💳 Rezervasyon ödemesi başlatılıyor - User: {current_user['id']}, Field: {payment_request.field_id}")
        
        # 1. Tesisi ve sahayı kontrol et
        facility = await db.facilities.find_one({"id": payment_request.facility_id})
        if not facility:
            raise HTTPException(status_code=404, detail="Tesis bulunamadı")
        
        # CRITICAL: Saha bilgileri facilities koleksiyonundaki fields array'inde (sport_configs değil)
        fields_data = facility.get("fields", [])
        logger.info(f"🔍 DEBUG: Facility has {len(fields_data)} fields in 'fields' array")
        logger.info(f"🔍 DEBUG: Facility keys: {list(facility.keys())}")
        
        # Eğer fields array'i boşsa, facility_fields koleksiyonundan çekmeyi dene
        if not fields_data:
            logger.info("🔍 DEBUG: No fields in facility.fields, trying facility_fields collection")
            # CRITICAL FIX: Aynı sıralamayı kullan (available-fields ile tutarlı olması için)
            facility_fields = await db.facility_fields.find({
                "facility_id": payment_request.facility_id,
                "is_active": True
            }).sort("created_at", 1).to_list(100)
            logger.info(f"🔍 DEBUG: Found {len(facility_fields)} fields in facility_fields collection")
            fields_data = facility_fields
        
        field = None
        for field_item in fields_data:
            # Field ID'si olmayabilir, name ile de eşleşmeyi dene
            if (field_item.get("id") == payment_request.field_id or 
                field_item.get("_id") == payment_request.field_id or
                field_item.get("name") == payment_request.field_id or
                field_item.get("field_name") == payment_request.field_id):
                field = field_item
                logger.info(f"✅ DEBUG: Found matching field: {field.get('name') or field.get('field_name')}")
                break
        
        if not field:
            # Eğer field_id ile bulunamadıysa, ilk müsait sahayı kullan
            if fields_data:
                field = fields_data[0]  # İlk sahayı kullan
                logger.info(f"⚠️ Field ID {payment_request.field_id} not found, using first available field: {field.get('name') or field.get('field_name')}")
            else:
                logger.error(f"❌ No fields found anywhere. Field ID: {payment_request.field_id}")
                logger.error(f"❌ Facility structure: {facility}")
                raise HTTPException(status_code=404, detail="Saha bulunamadı")
        
        # 2. Müsaitlik kontrolü (son kez)
        reservations = await db.reservations.find({
            "field_id": payment_request.field_id,
            "date": payment_request.date,
            "status": {"$in": ["pending", "confirmed"]}
        }).to_list(100)
        
        reserved_hours = set()
        for reservation in reservations:
            time_slots = reservation.get("time_slots", [])
            for slot in time_slots:
                try:
                    hour = int(slot.split(":")[0])
                    reserved_hours.add(hour)
                except:
                    continue
        
        requested_hours = [int(slot.split(":")[0]) for slot in payment_request.time_slots]
        if any(hour in reserved_hours for hour in requested_hours):
            raise HTTPException(
                status_code=400,
                detail="Seçtiğiniz saatlerden bazıları artık müsait değil. Lütfen sayfayı yenileyin."
            )
        
        # 3. Fiyat hesapla - DİNAMİK FİYATLANDIRMA V2
        from datetime import datetime
        from facility_endpoints import calculate_field_price_v2
        
        total_hours = len(payment_request.time_slots)
        
        # Tarihi parse et
        booking_date = datetime.strptime(payment_request.date, "%Y-%m-%d")
        
        # CRITICAL FIX: Saha numarası bul (available-fields endpoint ile AYNI sıralamayı kullan)
        # Aynı sıralama: is_active=True + created_at artan sıralama
        all_fields = await db.facility_fields.find({
            "facility_id": payment_request.facility_id, 
            "is_active": True
        }).sort("created_at", 1).to_list(100)
        
        # CRITICAL FIX: MongoDB _id'leri string'e çevirerek karşılaştır
        field_id_str = str(field.get('_id')) if field.get('_id') else field.get('id')
        logger.info(f"🔍 DEBUG: Looking for field: {field.get('name') or field.get('field_name')} (id={field_id_str})")
        
        field_index = 1
        for idx, f in enumerate(all_fields, 1):
            f_id_str = str(f.get('_id')) if f.get('_id') else f.get('id')
            f_name = f.get('name') or f.get('field_name')
            logger.info(f"  #{idx}: {f_name} (id={f_id_str})")
            
            # String karşılaştırması yap
            if field_id_str == f_id_str:
                field_index = idx
                logger.info(f"✅ MATCH! Field found at index {idx}: {f_name}")
                break
        
        logger.info(f"🎯 Final field_index: {field_index}")
        
        # HER SAAT İÇİN AYRI FİYAT HESAPLA (Çünkü farklı zaman dilimlerine denk gelebilir)
        logger.info(f"🕐 time_slots alındı: {payment_request.time_slots} (count: {len(payment_request.time_slots)})")
        total_price = 0
        for time_slot in payment_request.time_slots:
            # Her slot için ayrı fiyat hesapla
            hourly_rate = await calculate_field_price_v2(
                facility=facility,
                field=field,
                field_index=field_index,
                booking_date=booking_date,
                start_time=time_slot,
                end_time=time_slot  # Tek saat
            )
            total_price += hourly_rate
            logger.info(f"  {time_slot}: {hourly_rate} TL")
        
        logger.info(f"💵 TOPLAM: {total_hours} saat = {total_price} TL")
        
        # 3.1. Promo kod varsa, frontend'den gelen fiyatı kullan
        final_price = total_price
        original_price = total_price
        promo_applied = False
        
        if payment_request.promo_code and payment_request.total_price is not None:
            # Frontend'den gelen indirimli fiyatı kullan
            final_price = payment_request.total_price
            original_price = payment_request.original_price or total_price
            promo_applied = True
            logger.info(f"🎫 Promo kod uygulandı: {payment_request.promo_code}")
            logger.info(f"   Orijinal fiyat: {original_price} TL")
            logger.info(f"   İndirim: %{payment_request.promo_discount} ({payment_request.discount_amount} TL)")
            logger.info(f"   Final fiyat: {final_price} TL")
        
        # 4. Geçici rezervasyon oluştur (ödeme bekliyor)
        reservation_id = str(uuid.uuid4())
        reservation = {
            "id": reservation_id,
            "type": "facility",  # CRITICAL: Tesis rezervasyonu
            "facility_id": payment_request.facility_id,
            "field_id": payment_request.field_id,
            "user_id": current_user["id"],
            "date": payment_request.date,
            "start_time": payment_request.start_time,
            "end_time": payment_request.end_time,
            "time_slots": payment_request.time_slots,
            "total_hours": total_hours,
            "hourly_rate": hourly_rate,
            "original_price": original_price,
            "total_price": final_price,  # İndirimli fiyat
            # Promo code info
            "promo_code": payment_request.promo_code if promo_applied else None,
            "promo_discount": payment_request.promo_discount if promo_applied else 0,
            "discount_amount": payment_request.discount_amount if promo_applied else 0,
            "status": "payment_pending",  # Ödeme bekleniyor
            "payment_status": "pending",
            "notes": payment_request.notes,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.reservations.insert_one(reservation)
        logger.info(f"✅ Geçici rezervasyon oluşturuldu: {reservation_id}")
        
        # 5. İyzico checkout başlat
        # Get backend base URL from environment (MUST be public URL for Iyzico callback)
        backend_base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:3000")
        callback_url = f"{backend_base_url}/api/reservations/payment-callback"
        
        logger.info(f"💳 İyzico callback URL: {callback_url}")
        logger.info(f"🌐 Backend base URL: {backend_base_url}")
        
        try:
            field_display_name = field.get("name") or field.get("field_name") or "Saha"
            
            # Promo kod açıklaması ekle
            payment_description = f"{facility['name']} - {field_display_name}"
            if promo_applied and payment_request.promo_code:
                payment_description += f" (İndirim: %{payment_request.promo_discount})"
            
            payment_result = iyzico_service.initialize_checkout_form(
                user=current_user,
                amount=final_price,  # İndirimli fiyat kullan
                related_type="reservation",
                related_id=reservation_id,
                related_name=payment_description,
                callback_url=callback_url
            )
            
            payment_token = payment_result.get("token")
            logger.info(f"✅ İyzico checkout başlatıldı: {payment_token}")
            
            # Payment token'ı rezervasyona kaydet (polling için gerekli)
            await db.reservations.update_one(
                {"id": reservation_id},
                {"$set": {"payment_token": payment_token}}
            )
            
            response_data = {
                "success": True,
                "reservation_id": reservation_id,
                "payment_token": payment_token,
                "payment_page_url": payment_result.get("paymentPageUrl") or payment_result.get("payment_page_url"),  # İyzico camelCase döndürüyor
                "checkout_form_content": payment_result.get("checkoutFormContent") or payment_result.get("checkout_form_content"),  # İyzico camelCase döndürüyor
                "total_price": final_price,  # İndirimli fiyat
                "original_price": original_price,
                "promo_code": payment_request.promo_code if promo_applied else None,
                "promo_discount": payment_request.promo_discount if promo_applied else 0,
                "discount_amount": payment_request.discount_amount if promo_applied else 0,
                "facility_name": facility["name"],
                "field_name": field.get("name") or field.get("field_name") or "Saha"
            }
            
            logger.info(f"✅ Payment initialized successfully - Response: {response_data}")
            logger.info(f"🔑 Payment URL: {response_data.get('payment_page_url')}")
            
            return response_data
        
        except Exception as e:
            # İyzico hatası, rezervasyonu sil
            await db.reservations.delete_one({"id": reservation_id})
            logger.error(f"❌ İyzico hatası: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Ödeme başlatılamadı: {str(e)}")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Rezervasyon ödeme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reservations/payment-callback")
@router.get("/reservations/payment-callback")
async def payment_callback(request: Request, token: str = None):
    """İyzico ödeme callback (3D Secure sonrası)"""
    try:
        logger.info(f"🔔 CALLBACK ALINDI! Method: {request.method}, URL: {request.url}")
        logger.info(f"📋 Headers: {dict(request.headers)}")
        
        # Token'ı GET veya POST'tan al
        if request.method == "POST":
            form_data = await request.form()
            logger.info(f"📦 Form data: {dict(form_data)}")
            token = form_data.get("token")
        elif request.method == "GET":
            # Query parameter'dan al
            logger.info(f"📦 Query params: {dict(request.query_params)}")
            token = request.query_params.get("token")
        
        logger.info(f"💳 Ödeme callback alındı - Token: {token}")
        
        # İyzico'dan sonucu al
        payment_result = iyzico_service.retrieve_checkout_form_result(token)
        
        if payment_result.get("status") == "success":
            # Ödeme başarılı
            basket_id = payment_result.get("basketId", "")
            reservation_id = basket_id.split("_")[-1] if "_" in basket_id else ""
            
            if not reservation_id:
                raise HTTPException(status_code=400, detail="Rezervasyon ID bulunamadı")
            
            # Rezervasyonu güncelle
            reservation = await db.reservations.find_one({"id": reservation_id})
            if not reservation:
                raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
            
            await db.reservations.update_one(
                {"id": reservation_id},
                {
                    "$set": {
                        "status": "confirmed",
                        "payment_status": "completed",
                        "payment_id": payment_result.get("paymentId"),
                        "paid_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"✅ Rezervasyon onaylandı: {reservation_id}")
            
            # 1. KULLANICI AJANDASINA EKLE
            facility = await db.facilities.find_one({"id": reservation.get("facility_id")})
            
            # Field'ı hem id hem _id ile ara
            field = None
            field_id = reservation.get("field_id")
            if field_id:
                field = await db.facility_fields.find_one({"id": field_id})
                if not field:
                    # ObjectId olarak dene
                    from bson import ObjectId
                    try:
                        field = await db.facility_fields.find_one({"_id": ObjectId(field_id)})
                    except:
                        pass
            
            logger.info(f"🏢 Facility: {facility.get('name') if facility else 'None'}")
            logger.info(f"⚽ Field: {field.get('name') if field else 'None'}")
            
            # user_id'yi düzgün al (dict veya string olabilir)
            user_id = reservation.get("user_id")
            if isinstance(user_id, dict):
                user_id = user_id.get("id")
            
            # Müşteri bilgilerini al
            customer = await db.users.find_one({"id": user_id})
            customer_name = customer.get("full_name", "Bilinmeyen Müşteri") if customer else "Bilinmeyen Müşteri"
            customer_phone = customer.get("phone", "") or customer.get("phone_number", "") if customer else ""
            
            user_calendar_item = {
                "id": f"cal_{reservation_id}_user",
                "user_id": user_id,
                "type": "reservation",
                "reservation_id": reservation_id,
                "title": f"{facility.get('name', 'Tesis')} - {field.get('name', 'Saha') if field else 'Saha'}",
                "description": f"Rezervasyon: {reservation.get('date')} {reservation.get('start_time')}-{reservation.get('end_time')}",
                "date": reservation.get("date"),
                "start_time": reservation.get("start_time"),
                "end_time": reservation.get("end_time"),
                "location": facility.get("address", "") if facility else "",
                "is_read": False,
                "created_at": datetime.utcnow()
            }
            await db.calendar_items.insert_one(user_calendar_item)
            logger.info(f"📅 Kullanıcı ajandasına eklendi: {user_id}")
            
            # 2. TESİS SAHİBİNİN AJANDASINA EKLE (Müşteri bilgileriyle)
            owner_calendar_item = {
                "id": f"cal_{reservation_id}_owner",
                "user_id": facility.get("owner_id") if facility else None,
                "type": "reservation",
                "reservation_id": reservation_id,
                "title": f"Rezervasyon: {field.get('name', 'Saha') if field else 'Saha'}",
                "description": f"Müşteri: {customer_name}\nTelefon: {customer_phone}\nTarih: {reservation.get('date')} {reservation.get('start_time')}-{reservation.get('end_time')}",
                "date": reservation.get("date"),
                "start_time": reservation.get("start_time"),
                "end_time": reservation.get("end_time"),
                "location": facility.get("name", "") if facility else "",
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "customer_id": user_id,
                "is_read": False,
                "created_at": datetime.utcnow()
            }
            await db.calendar_items.insert_one(owner_calendar_item)
            logger.info(f"📅 Tesis sahibi ajandasına eklendi: {facility.get('owner_id') if facility else 'N/A'} (Müşteri: {customer_name})")
            
            # 3. TESİS SAHİBİNE BİLDİRİM GÖNDER (Detaylı)
            owner_notification = {
                "id": f"notif_{reservation_id}_payment",
                "user_id": facility.get("owner_id"),
                "type": "payment",
                "title": "💰 Yeni Rezervasyon Ödemesi",
                "message": f"📍 {facility.get('name', 'Tesis')} - {field.get('name', 'Saha')}\n📅 {reservation.get('date')} | ⏰ {reservation.get('start_time')}-{reservation.get('end_time')}\n👤 {customer_name}\n📞 {customer_phone}\n💵 {payment_result.get('paidPrice', 0)} TL",
                "data": {
                    "reservation_id": reservation_id,
                    "facility_id": reservation["facility_id"],
                    "facility_name": facility.get("name", ""),
                    "field_name": field.get("name", "Saha"),
                    "customer_name": customer_name,
                    "customer_phone": customer_phone,
                    "customer_id": reservation.get("user_id"),
                    "amount": payment_result.get("paidPrice", 0),
                    "date": reservation.get("date"),
                    "time": f"{reservation.get('start_time')}-{reservation.get('end_time')}"
                },
                "is_read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(owner_notification)
            logger.info(f"🔔 Tesis sahibine bildirim gönderildi: {facility.get('owner_id')} - Müşteri: {customer_name}")
            
            # 4. ADMIN'E BİLDİRİM GÖNDER (Özgür Barış Karaca)
            # Önce telefon numarasıyla ara, bulamazsan isimle ara
            admin_user = await db.users.find_one({"phone_number": "+905324900472"})
            if not admin_user:
                admin_user = await db.users.find_one({"full_name": "Özgür Barış Karaca", "user_type": "admin"})
            
            if admin_user:
                admin_notification = {
                    "id": f"notif_{reservation_id}_admin",
                    "user_id": admin_user["id"],
                    "type": "admin_payment",
                    "title": "💰 Yeni Rezervasyon Ödemesi",
                    "message": f"📍 {facility.get('name', 'Tesis')} - {field.get('name', 'Saha')}\n📅 {reservation.get('date')} | ⏰ {reservation.get('start_time')}-{reservation.get('end_time')}\n👤 {customer_name}\n📞 {customer_phone}\n💵 {payment_result.get('paidPrice', 0)} TL",
                    "data": {
                        "reservation_id": reservation_id,
                        "facility_id": reservation["facility_id"],
                        "facility_name": facility.get("name", ""),
                        "field_name": field.get("name", "Saha"),
                        "customer_name": customer_name,
                        "customer_phone": customer_phone,
                        "customer_id": reservation.get("user_id"),
                        "amount": payment_result.get("paidPrice", 0),
                        "date": reservation.get("date"),
                        "time": f"{reservation.get('start_time')}-{reservation.get('end_time')}"
                    },
                    "is_read": False,
                    "created_at": datetime.utcnow()
                }
                await db.notifications.insert_one(admin_notification)
                logger.info(f"👨‍💼 Admin'e bildirim gönderildi: {admin_user['id']} - Müşteri: {customer_name}")
            else:
                logger.warning("⚠️ Admin kullanıcısı bulunamadı (telefon: +905324900472)")
            
            # 5. WORKFLOW TETİKLE - Rezervasyon oluşturulduğunda
            try:
                reservation_date = reservation.get("date")
                await trigger_workflow("on_reservation_create", {
                    "user_id": user_id,
                    "user_name": customer_name,
                    "user_phone": customer_phone,
                    "reservation_id": reservation_id,
                    "reservation_date": reservation_date,
                    "event_date": reservation_date,  # Alias for templates
                    "facility_id": reservation.get("facility_id"),
                    "facility_name": facility.get("name", "") if facility else "",
                    "field_name": field.get("name", "") if field else "",
                    "start_time": reservation.get("start_time"),
                    "end_time": reservation.get("end_time"),
                    "total_price": payment_result.get("paidPrice", 0),
                    "owner_id": facility.get("owner_id") if facility else None,
                    "reservation_link": f"/reservation-detail/{reservation_id}",
                })
                logger.info(f"⚙️ Workflow tetiklendi: on_reservation_create - {reservation_id}")
            except Exception as workflow_error:
                logger.error(f"⚠️ Workflow tetikleme hatası: {workflow_error}")
            
            # 6. ÖDEME BAŞARILI WORKFLOW TETİKLE
            try:
                await trigger_workflow("on_payment_success", {
                    "user_id": user_id,
                    "user_name": customer_name,
                    "reservation_id": reservation_id,
                    "amount": payment_result.get("paidPrice", 0),
                    "payment_type": "reservation",
                })
                logger.info(f"⚙️ Workflow tetiklendi: on_payment_success - {reservation_id}")
            except Exception as workflow_error:
                logger.error(f"⚠️ Workflow tetikleme hatası: {workflow_error}")
            
            # Frontend success sayfasına redirect
            from fastapi.responses import RedirectResponse
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            return RedirectResponse(
                url=f"{frontend_url}/reservations/payment-success?reservation_id={reservation_id}",
                status_code=303
            )
        else:
            # Ödeme başarısız
            error_message = payment_result.get("errorMessage", "Ödeme başarısız")
            logger.error(f"❌ Ödeme başarısız: {error_message}")
            
            # Frontend error sayfasına redirect
            from fastapi.responses import RedirectResponse
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            return RedirectResponse(
                url=f"{frontend_url}/reservations/payment-error?message={error_message}",
                status_code=303
            )
    
    except Exception as e:
        logger.error(f"❌ Payment callback hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reservations/{reservation_id}/check-payment")
async def check_payment_status(
    reservation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Frontend polling için: Rezervasyon durumunu kontrol et ve gerekirse İyzico'dan sonucu çek
    """
    try:
        # Rezervasyonu bul
        reservation = await db.reservations.find_one({"id": reservation_id})
        if not reservation:
            raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
        
        # Kullanıcı yetkisi kontrolü
        if reservation["user_id"] != current_user.get("id"):
            raise HTTPException(status_code=403, detail="Bu rezervasyona erişim yetkiniz yok")
        
        # Eğer zaten confirmed ise, direkt döndür
        if reservation["status"] == "confirmed" and reservation["payment_status"] == "completed":
            return {
                "success": True,
                "status": "confirmed",
                "payment_status": "completed",
                "message": "Rezervasyon zaten onaylanmış"
            }
        
        # Eğer payment_pending ise ve payment_token varsa, İyzico'dan sonucu kontrol et
        if reservation["payment_status"] == "pending" and reservation.get("payment_token"):
            logger.info(f"🔍 İyzico ödeme durumu kontrol ediliyor: {reservation_id}")
            
            try:
                payment_result = iyzico_service.retrieve_checkout_form_result(reservation["payment_token"])
                
                if payment_result.get("status") == "success":
                    # Ödeme başarılı, rezervasyonu onayla
                    await db.reservations.update_one(
                        {"id": reservation_id},
                        {
                            "$set": {
                                "status": "confirmed",
                                "payment_status": "completed",
                                "payment_id": payment_result.get("paymentId"),
                                "paid_at": datetime.utcnow(),
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )
                    
                    logger.info(f"✅ Rezervasyon onaylandı (polling check): {reservation_id}")
                    
                    # Güncellenmiş rezervasyonu al
                    reservation = await db.reservations.find_one({"id": reservation_id})
                    
                    # Bildirimleri gönder
                    await send_reservation_notifications(reservation)
                    
                    return {
                        "success": True,
                        "status": "confirmed",
                        "payment_status": "completed",
                        "payment_id": payment_result.get("paymentId"),
                        "message": "Ödeme başarılı, rezervasyon onaylandı"
                    }
                else:
                    # Ödeme başarısız
                    await db.reservations.update_one(
                        {"id": reservation_id},
                        {
                            "$set": {
                                "payment_status": "failed",
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )
                    
                    return {
                        "success": False,
                        "status": reservation["status"],
                        "payment_status": "failed",
                        "message": payment_result.get("errorMessage", "Ödeme başarısız")
                    }
            
            except Exception as iyzico_error:
                logger.error(f"❌ İyzico sorgulama hatası: {str(iyzico_error)}")
                # Hata olsa bile mevcut durumu döndür
        
        # Mevcut durumu döndür
        return {
            "success": reservation["payment_status"] == "completed",
            "status": reservation["status"],
            "payment_status": reservation["payment_status"],
            "message": "Ödeme bekleniyor"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Payment check hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def send_reservation_notifications(reservation: dict):
    """Rezervasyon bildirimleri gönder (3 taraf: kullanıcı, tesis sahibi, admin)"""
    try:
        # Tesis ve saha bilgilerini al
        facility = await db.facilities.find_one({"id": reservation["facility_id"]})
        field = await db.facility_fields.find_one({"id": reservation["field_id"]})
        user = await db.users.find_one({"id": reservation["user_id"]})
        
        if not facility or not field or not user:
            logger.warning("Tesis, saha veya kullanıcı bulunamadı")
            return
        
        # 1. Kullanıcıya bildirim
        user_notification = {
            "id": str(uuid.uuid4()),
            "user_id": reservation["user_id"],
            "type": "RESERVATION_CONFIRMED",
            "title": "Rezervasyonunuz Onaylandı",
            "message": f"{facility['name']} - {field['field_name']} için {reservation['date']} tarihli rezervasyonunuz onaylandı.",
            "related_id": reservation["id"],
            "related_type": "reservation",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(user_notification)
        logger.info(f"✅ Kullanıcıya bildirim gönderildi: {reservation['user_id']}")
        
        # 2. Tesis sahibine bildirim
        owner_notification = {
            "id": str(uuid.uuid4()),
            "user_id": facility["owner_id"],
            "type": "NEW_RESERVATION",
            "title": "Yeni Rezervasyon Alındı",
            "message": f"{user.get('full_name', 'Bir kullanıcı')} {reservation['date']} tarihinde {field['field_name']} için rezervasyon yaptı.",
            "related_id": reservation["id"],
            "related_type": "reservation",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await db.notifications.insert_one(owner_notification)
        logger.info(f"✅ Tesis sahibine bildirim gönderildi: {facility['owner_id']}")
        
        # 3. Admin'e bildirim (Özgür Barış Karaca - +905324900472)
        admin_user = await db.users.find_one({"phone_number": "+905324900472"})
        if admin_user:
            admin_notification = {
                "id": str(uuid.uuid4()),
                "user_id": admin_user["id"],
                "type": "ADMIN_ACTION",
                "title": "Yeni Rezervasyon Bildirimi",
                "message": f"{facility['name']} tesisinde yeni rezervasyon: {reservation['total_price']} TL",
                "related_id": reservation["id"],
                "related_type": "reservation",
                "read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(admin_notification)
            logger.info(f"✅ Admin'e bildirim gönderildi: {admin_user['id']}")
        else:
            logger.warning("⚠️ Admin kullanıcısı bulunamadı (telefon: +905324900472)")
    
    except Exception as e:
        logger.error(f"❌ Bildirim gönderme hatası: {str(e)}")
        # Hata olsa bile rezervasyonu iptal etme
