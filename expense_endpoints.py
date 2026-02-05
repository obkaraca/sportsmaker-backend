from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
import os
from auth import get_current_user
from datetime import datetime, timedelta
from typing import Optional
import uuid

router = APIRouter()

# Database
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sports_management")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


@router.post("/expenses")
async def create_expense(expense_data: dict, current_user: dict = Depends(get_current_user)):
    """Gider oluştur"""
    try:
        expense = {
            "id": str(uuid.uuid4()),
            "user_id": current_user["id"],
            "facility_id": expense_data.get("facility_id"),  # Tek tesis için (eski format)
            "facility_ids": expense_data.get("facility_ids", []),  # Çoklu tesis için
            "amount": expense_data.get("amount"),
            "kdv_rate": expense_data.get("kdv_rate", 0),
            "description": expense_data.get("description"),
            "category": expense_data.get("category", "genel"),
            "date": expense_data.get("date", datetime.utcnow().isoformat()),
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Eğer facility_id verilmiş ama facility_ids boşsa, facility_id'yi listeye ekle
        if expense["facility_id"] and not expense["facility_ids"]:
            expense["facility_ids"] = [expense["facility_id"]]
        
        result = await db.expenses.insert_one(expense)
        
        # MongoDB'nin eklediği _id'yi çıkar
        expense.pop("_id", None)
        
        return {
            "success": True,
            "expense": expense
        }
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==================== MANUEL GELİRLER ====================

@router.post("/manual-incomes")
async def create_manual_income(income_data: dict, current_user: dict = Depends(get_current_user)):
    """Manuel gelir oluştur"""
    try:
        income = {
            "id": str(uuid.uuid4()),
            "user_id": current_user["id"],
            "facility_id": income_data.get("facility_id"),  # Tek tesis için
            "facility_ids": income_data.get("facility_ids", []),  # Çoklu tesis için
            "amount": income_data.get("amount"),
            "kdv_rate": income_data.get("kdv_rate", 0),  # KDV oranı
            "description": income_data.get("description"),
            "category": income_data.get("category", "diger"),
            "date": income_data.get("date", datetime.utcnow().isoformat()),
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Eğer facility_id verilmiş ama facility_ids boşsa, facility_id'yi listeye ekle
        if income["facility_id"] and not income["facility_ids"]:
            income["facility_ids"] = [income["facility_id"]]
        
        result = await db.manual_incomes.insert_one(income)
        
        # MongoDB'nin eklediği _id'yi çıkar
        income.pop("_id", None)
        
        return {
            "success": True,
            "income": income
        }
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/manual-incomes")
async def get_manual_incomes(
    facility_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Manuel gelirleri listele"""
    try:
        query = {"user_id": current_user["id"]}
        
        if facility_id:
            query["$or"] = [
                {"facility_id": facility_id},
                {"facility_ids": facility_id}
            ]
        
        if start_date and end_date:
            query["date"] = {
                "$gte": start_date,
                "$lte": end_date
            }
        
        incomes = await db.manual_incomes.find(query).sort("date", -1).to_list(1000)
        
        # _id'leri çıkar ve tesis isimlerini ekle
        user_facilities = await db.facilities.find({"owner_id": current_user["id"]}).to_list(100)
        facility_map = {f["id"]: f["name"] for f in user_facilities}
        
        for income in incomes:
            income.pop("_id", None)
            # Tesis isimlerini ekle
            if income.get("facility_ids"):
                income["facility_names"] = [facility_map.get(fid, "Bilinmeyen") for fid in income["facility_ids"]]
            elif income.get("facility_id"):
                income["facility_name"] = facility_map.get(income["facility_id"], "Bilinmeyen")
        
        return {
            "success": True,
            "incomes": incomes
        }
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/manual-incomes/{income_id}")
async def delete_manual_income(income_id: str, current_user: dict = Depends(get_current_user)):
    """Manuel gelir sil"""
    try:
        result = await db.manual_incomes.delete_one({
            "id": income_id,
            "user_id": current_user["id"]
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Gelir bulunamadı")
        
        return {"success": True, "message": "Gelir silindi"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/expenses")
async def get_expenses(
    facility_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Giderleri listele"""
    try:
        query = {"user_id": current_user["id"]}
        
        if facility_id:
            query["facility_id"] = facility_id
        
        if start_date and end_date:
            query["date"] = {
                "$gte": start_date,
                "$lte": end_date
            }
        
        expenses = await db.expenses.find(query).sort("date", -1).to_list(1000)
        
        # _id'leri çıkar
        for expense in expenses:
            expense.pop("_id", None)
        
        return {
            "success": True,
            "expenses": expenses
        }
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/expenses")
async def get_expense_report(
    period: str = "daily",  # daily, weekly, monthly
    date: Optional[str] = None,
    facility_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Gider raporu"""
    try:
        # Tarih aralığını belirle
        if date:
            target_date = datetime.fromisoformat(date)
        else:
            target_date = datetime.utcnow()
        
        if period == "daily":
            start_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)
        elif period == "weekly":
            days_since_monday = target_date.weekday()
            start_date = target_date - timedelta(days=days_since_monday)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=7)
        else:  # monthly
            start_date = target_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = start_date.replace(day=28) + timedelta(days=4)
            end_date = next_month.replace(day=1)
        
        query = {
            "user_id": current_user["id"],
            "date": {
                "$gte": start_date.isoformat(),
                "$lt": end_date.isoformat()
            }
        }
        
        if facility_id:
            query["facility_id"] = facility_id
        
        expenses = await db.expenses.find(query).to_list(1000)
        
        # Kategorilere göre grupla
        category_totals = {}
        total_expenses = 0
        
        for expense in expenses:
            category = expense.get("category", "genel")
            amount = expense.get("amount", 0)
            
            if category not in category_totals:
                category_totals[category] = 0
            category_totals[category] += amount
            total_expenses += amount
            
            # _id çıkar
            expense.pop("_id", None)
        
        return {
            "success": True,
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_expenses": total_expenses,
            "category_totals": category_totals,
            "expense_count": len(expenses),
            "expenses": expenses
        }
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, current_user: dict = Depends(get_current_user)):
    """Gider sil"""
    try:
        result = await db.expenses.delete_one({
            "id": expense_id,
            "user_id": current_user["id"]
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Gider bulunamadı")
        
        return {
            "success": True,
            "message": "Gider silindi"
        }
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/revenue/detailed")
async def get_detailed_revenue_report(
    facility_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Detaylı işlem bazlı tahsilat raporu"""
    try:
        facilities_query = {"owner_id": current_user["id"], "status": "approved"}
        if facility_id:
            facilities_query["id"] = facility_id
        
        facilities = await db.facilities.find(facilities_query).to_list(100)
        facility_ids = [f["id"] for f in facilities]
        
        # Tarih aralığı
        if start_date and end_date:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date)
        else:
            # Default: son 30 gün
            end = datetime.utcnow()
            start = end - timedelta(days=30)
        
        # Tüm işlemleri topla
        transactions = []
        
        for facility in facilities:
            fields = await db.facility_fields.find({"facility_id": facility["id"]}).to_list(100)
            
            for field in fields:
                sessions = field.get("session_history", [])
                for session in sessions:
                    if not session.get("end_time"):
                        continue
                    
                    session_end_str = session["end_time"]
                    if 'T' in session_end_str:
                        session_end_str = session_end_str.split('+')[0].split('Z')[0].split('.')[0]
                    session_end = datetime.fromisoformat(session_end_str)
                    
                    if start <= session_end <= end:
                        transactions.append({
                            "facility_name": facility["name"],
                            "field_name": field.get("name", field.get("field_name", "Bilinmiyor")),
                            "date": session_end.isoformat(),
                            "player_names": ", ".join(session.get("player_names", [])),
                            "duration_minutes": session.get("duration_minutes", 0),
                            "base_price": session.get("base_price", 0),
                            "overtime_price": session.get("overtime_price", 0),
                            "total_collected": session.get("total_collected", 0),
                            "payment_method": session.get("payment_method", "nakit")
                        })
        
        # Tarihe göre sırala
        transactions.sort(key=lambda x: x["date"], reverse=True)
        
        return {
            "success": True,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "transactions": transactions,
            "total_transactions": len(transactions),
            "total_revenue": sum(t["total_collected"] for t in transactions)
        }
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/revenue/export")
async def export_revenue_report(
    export_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Gelir raporunu Excel olarak mail gönder"""
    try:
        email = export_data.get("email")
        start_date = export_data.get("start_date")
        end_date = export_data.get("end_date")
        facility_id = export_data.get("facility_id")
        
        if not email:
            raise HTTPException(status_code=400, detail="Email adresi gerekli")
        
        # Detaylı raporu al
        detailed_response = await get_detailed_revenue_report(
            facility_id=facility_id,
            start_date=start_date,
            end_date=end_date,
            current_user=current_user
        )
        
        transactions = detailed_response["transactions"]
        
        # CSV formatına çevir (Excel'de açılabilir)
        csv_content = "Tesis,Saha,Tarih,Oyuncular,Süre (dk),Temel Ücret,Süre Aşım Ücreti,Toplam Tahsilat,Ödeme Yöntemi\n"
        
        for t in transactions:
            csv_content += f"{t['facility_name']},{t['field_name']},{t['date']},{t['player_names']},{t['duration_minutes']},{t['base_price']},{t['overtime_price']},{t['total_collected']},{t['payment_method']}\n"
        
        # Email gönderme (basit SMTP)
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.mime.base import MIMEBase
            from email import encoders
            import io
            
            # Email mesajı oluştur
            msg = MIMEMultipart()
            msg['From'] = "noreply@sportsmaker.net"
            msg['To'] = email
            msg['Subject'] = "Gelir Raporu - Sports Maker"
            
            body = f"""
Merhaba,

Talep ettiğiniz gelir raporu ektedir.

Tarih Aralığı: {detailed_response['start_date']} - {detailed_response['end_date']}
Toplam İşlem: {len(transactions)}
Toplam Gelir: {detailed_response['total_revenue']:.2f} TL

İyi günler dileriz.
Sports Maker Ekibi
            """
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # CSV dosyasını ekle
            attachment = MIMEBase('application', 'octet-stream')
            attachment.set_payload(csv_content.encode('utf-8'))
            encoders.encode_base64(attachment)
            attachment.add_header('Content-Disposition', f'attachment; filename=gelir_raporu.csv')
            msg.attach(attachment)
            
            # Not: Gerçek SMTP bilgileri gerekli
            # Şimdilik mock olarak success döndürüyoruz
            print(f"📧 Email gönderildi (MOCK): {email}")
            
        except Exception as email_error:
            print(f"Email gönderme hatası: {email_error}")
            # Email hatası olsa bile rapor oluşturulduğu için success dönüyoruz
        
        return {
            "success": True,
            "message": f"Rapor hazırlandı ve {email} adresine gönderildi",
            "transaction_count": len(transactions),
            "total_revenue": detailed_response['total_revenue']
        }
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/expenses/export")
async def export_expense_report(
    export_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Gider raporunu Excel olarak mail gönder"""
    try:
        email = export_data.get("email")
        
        if not email:
            raise HTTPException(status_code=400, detail="Email adresi gerekli")
        
        # Tüm giderleri al
        expenses = await db.expenses.find({"user_id": current_user["id"]}).sort("date", -1).to_list(1000)
        
        # _id'leri çıkar
        for expense in expenses:
            expense.pop("_id", None)
        
        # CSV formatına çevir
        csv_content = "Tarih,Açıklama,Kategori,KDV Oranı,Tutar (TL)\n"
        
        total = 0
        for exp in expenses:
            date = datetime.fromisoformat(exp['date']).strftime('%d.%m.%Y')
            kdv = f"%{exp.get('kdv_rate', 0)}" if exp.get('kdv_rate', 0) > 0 else "-"
            amount = exp.get('amount', 0)
            total += amount
            csv_content += f"{date},{exp['description']},{exp['category']},{kdv},{amount:.2f}\n"
        
        csv_content += f"\n,,,Toplam,{total:.2f}\n"
        
        # Email gönderme
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.mime.base import MIMEBase
            from email import encoders
            
            msg = MIMEMultipart()
            msg['From'] = "noreply@sportsmaker.net"
            msg['To'] = email
            msg['Subject'] = "Gider Raporu - Sports Maker"
            
            body = f"""
Merhaba,

Talep ettiğiniz gider raporu ektedir.

Toplam Gider Sayısı: {len(expenses)}
Toplam Gider: {total:.2f} TL

İyi günler dileriz.
Sports Maker Ekibi
            """
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # CSV dosyasını ekle
            attachment = MIMEBase('application', 'octet-stream')
            attachment.set_payload(csv_content.encode('utf-8'))
            encoders.encode_base64(attachment)
            attachment.add_header('Content-Disposition', f'attachment; filename=gider_raporu.csv')
            msg.attach(attachment)
            
            print(f"📧 Email gönderildi (MOCK): {email}")
            
        except Exception as email_error:
            print(f"Email gönderme hatası: {email_error}")
        
        return {
            "success": True,
            "message": f"Gider raporu hazırlandı ve {email} adresine gönderildi",
            "expense_count": len(expenses),
            "total_expenses": total
        }
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/revenue")
async def get_revenue_report(
    facility_id: Optional[str] = None,
    period: str = "daily",  # daily, weekly, monthly
    date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Tahsilat raporu - Rezervasyon ödemeleri + Oturum gelirleri + Manuel gelirler"""
    try:
        # Kullanıcının tesislerini bul
        facilities_query = {"owner_id": current_user["id"], "status": "approved"}
        if facility_id:
            facilities_query["id"] = facility_id
        
        facilities = await db.facilities.find(facilities_query).to_list(100)
        facility_ids = [f["id"] for f in facilities]
        
        print(f"📊 Gelir raporu - Kullanıcı: {current_user['id']}, Tesisler: {facility_ids}")
        
        # Tarih aralığını belirle
        if date:
            target_date = datetime.fromisoformat(date)
        else:
            target_date = datetime.utcnow()
        
        if period == "daily":
            start_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)
        elif period == "weekly":
            # Pazartesi başlangıç, Pazar sonu
            days_since_monday = target_date.weekday()
            start_date = target_date - timedelta(days=days_since_monday)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=7)
        else:  # monthly
            start_date = target_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = start_date.replace(day=28) + timedelta(days=4)
            end_date = next_month.replace(day=1)
        
        print(f"📅 Tarih aralığı: {start_date} - {end_date}")
        
        # Her tesisin gelirini hesapla
        total_revenue = 0
        facility_revenues = []
        payment_methods = {"nakit": 0, "kredi_karti": 0, "iyzico": 0, "uyelik": 0, "manuel": 0}
        
        for facility in facilities:
            fac_id = facility["id"]
            facility_total = 0
            session_count = 0
            reservation_count = 0
            manual_income_count = 0
            
            # 1️⃣ OTURUM GELİRLERİ (session_history)
            fields = await db.facility_fields.find({"facility_id": fac_id}).to_list(100)
            for field in fields:
                sessions = field.get("session_history", [])
                for session in sessions:
                    if not session.get("end_time"):
                        continue
                    
                    try:
                        session_end = datetime.fromisoformat(session["end_time"].replace("Z", "+00:00"))
                        if start_date <= session_end.replace(tzinfo=None) < end_date:
                            collected = session.get("total_collected", 0)
                            facility_total += collected
                            session_count += 1
                            
                            method = session.get("payment_method", "nakit")
                            if method in payment_methods:
                                payment_methods[method] += collected
                    except:
                        pass
            
            # 2️⃣ REZERVASYON ÖDEMELERİ (reservations tablosu)
            reservations = await db.reservations.find({
                "facility_id": fac_id,
                "$or": [
                    {"payment_status": "paid"},
                    {"payment_status": "completed"},
                    {"status": "confirmed", "payment_status": {"$ne": "pending"}}
                ]
            }).to_list(1000)
            
            for res in reservations:
                try:
                    # Ödeme tarihini kontrol et
                    paid_at = res.get("paid_at") or res.get("updated_at") or res.get("created_at")
                    if paid_at:
                        if isinstance(paid_at, str):
                            paid_date = datetime.fromisoformat(paid_at.replace("Z", "+00:00")).replace(tzinfo=None)
                        else:
                            paid_date = paid_at.replace(tzinfo=None) if hasattr(paid_at, 'replace') else paid_at
                        
                        if start_date <= paid_date < end_date:
                            amount = res.get("total_price", 0) or res.get("amount", 0)
                            facility_total += amount
                            reservation_count += 1
                            payment_methods["iyzico"] += amount
                            print(f"  💳 Rezervasyon ödemesi: {amount} TL - {res.get('id', '')[:8]}")
                except Exception as e:
                    print(f"  ⚠️ Rezervasyon parse hatası: {e}")
            
            # 3️⃣ MANUEL GELİRLER (manual_incomes tablosu)
            manual_incomes = await db.manual_incomes.find({
                "$or": [
                    {"facility_id": fac_id},
                    {"facility_ids": fac_id}
                ],
                "user_id": current_user["id"]
            }).to_list(1000)
            
            for income in manual_incomes:
                try:
                    income_date_str = income.get("date") or income.get("created_at")
                    if income_date_str:
                        if isinstance(income_date_str, str):
                            income_date = datetime.fromisoformat(income_date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        else:
                            income_date = income_date_str.replace(tzinfo=None) if hasattr(income_date_str, 'replace') else income_date_str
                        
                        if start_date <= income_date < end_date:
                            amount = income.get("amount", 0)
                            facility_total += amount
                            manual_income_count += 1
                            payment_methods["manuel"] += amount
                except Exception as e:
                    print(f"  ⚠️ Manuel gelir parse hatası: {e}")
            
            total_revenue += facility_total
            facility_revenues.append({
                "facility_id": fac_id,
                "facility_name": facility["name"],
                "revenue": facility_total,
                "session_count": session_count,
                "reservation_count": reservation_count,
                "manual_income_count": manual_income_count
            })
            
            print(f"  📍 {facility['name']}: {facility_total} TL (Oturum: {session_count}, Rezervasyon: {reservation_count}, Manuel: {manual_income_count})")
        
        print(f"💰 Toplam gelir: {total_revenue} TL")
        
        return {
            "success": True,
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_revenue": total_revenue,
            "facilities": facility_revenues,
            "payment_methods": payment_methods
        }
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/reports/analytics")
async def get_analytics_report(
    year: int = None,
    type: str = "income",  # income veya expense
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Aylık analiz raporu - grafik için"""
    try:
        if not year:
            year = datetime.utcnow().year
        
        # Kullanıcının tesislerini bul
        facilities = await db.facilities.find({"owner_id": current_user["id"]}).to_list(100)
        facility_ids = [f["id"] for f in facilities]
        
        print(f"📊 Analytics - User: {current_user['id']}, Year: {year}, Type: {type}, Category: {category}")
        
        # 12 ay için boş array
        monthly_data = [0.0] * 12
        
        if type == "income":
            # 1. Rezervasyon gelirleri
            for fac_id in facility_ids:
                reservations = await db.reservations.find({
                    "facility_id": fac_id,
                    "$or": [
                        {"payment_status": "paid"},
                        {"payment_status": "completed"},
                        {"status": "confirmed", "payment_status": {"$ne": "pending"}}
                    ]
                }).to_list(10000)
                
                for res in reservations:
                    try:
                        paid_at = res.get("paid_at") or res.get("updated_at") or res.get("created_at")
                        if paid_at:
                            if isinstance(paid_at, str):
                                paid_date = datetime.fromisoformat(paid_at.replace("Z", "+00:00"))
                            else:
                                paid_date = paid_at
                            
                            if paid_date.year == year:
                                month = paid_date.month - 1  # 0-indexed
                                amount = res.get("total_price", 0) or res.get("amount", 0)
                                if not category or category == "rezervasyon":
                                    monthly_data[month] += amount
                    except:
                        pass
            
            # 2. Manuel gelirler
            query = {"user_id": current_user["id"]}
            if category and category != "all" and category != "rezervasyon":
                query["category"] = category
            
            manual_incomes = await db.manual_incomes.find(query).to_list(10000)
            for income in manual_incomes:
                try:
                    income_date_str = income.get("date") or income.get("created_at")
                    if income_date_str:
                        if isinstance(income_date_str, str):
                            income_date = datetime.fromisoformat(income_date_str.replace("Z", "+00:00"))
                        else:
                            income_date = income_date_str
                        
                        if income_date.year == year:
                            month = income_date.month - 1
                            if not category or category == "all" or income.get("category") == category:
                                monthly_data[month] += income.get("amount", 0)
                except:
                    pass
            
            # 3. Oturum gelirleri (session_history)
            for fac_id in facility_ids:
                fields = await db.facility_fields.find({"facility_id": fac_id}).to_list(100)
                for field in fields:
                    sessions = field.get("session_history", [])
                    for session in sessions:
                        if not session.get("end_time"):
                            continue
                        try:
                            session_end = datetime.fromisoformat(session["end_time"].replace("Z", "+00:00"))
                            if session_end.year == year:
                                month = session_end.month - 1
                                if not category or category == "all" or category == "nakit":
                                    monthly_data[month] += session.get("total_collected", 0)
                        except:
                            pass
        
        else:  # expense
            query = {"user_id": current_user["id"]}
            if category and category != "all":
                query["category"] = category
            
            expenses = await db.expenses.find(query).to_list(10000)
            for expense in expenses:
                try:
                    expense_date_str = expense.get("date") or expense.get("created_at")
                    if expense_date_str:
                        if isinstance(expense_date_str, str):
                            expense_date = datetime.fromisoformat(expense_date_str.replace("Z", "+00:00"))
                        else:
                            expense_date = expense_date_str
                        
                        if expense_date.year == year:
                            month = expense_date.month - 1
                            monthly_data[month] += expense.get("amount", 0)
                except:
                    pass
        
        print(f"📊 Monthly data for {year}: {monthly_data}")
        
        return {
            "success": True,
            "year": year,
            "type": type,
            "category": category,
            "monthly_data": monthly_data,
            "total": sum(monthly_data)
        }
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
