"""
Reports Endpoints Module
Kapsamlı raporlama sistemi: Etkinlikler, Kullanıcılar, Finansal, Sistem
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime, timedelta
from collections import defaultdict
import logging

from auth import get_current_user
from api_response import success_response, paginated_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Reports"])

# Database reference
db = None

def set_database(database):
    """Set database reference from main server"""
    global db
    db = database


# ==================== DASHBOARD OVERVIEW ====================

@router.get("/dashboard")
async def get_dashboard_report(current_user: dict = Depends(get_current_user)):
    """Ana dashboard özet raporu - tüm önemli metrikler"""
    try:
        current_user_id = current_user.get("id")
        user = await db.users.find_one({"id": current_user_id})
        is_admin = user.get("user_type") in ["admin", "super_admin"]
        
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Temel sayılar
        total_users = await db.users.count_documents({})
        total_events = await db.events.count_documents({})
        active_events = await db.events.count_documents({"status": "active"})
        total_venues = await db.venues.count_documents({})
        
        # Bu ay kayıtlar
        new_users_this_month = await db.users.count_documents({
            "created_at": {"$gte": month_start}
        })
        new_events_this_month = await db.events.count_documents({
            "created_at": {"$gte": month_start}
        })
        
        # Bugünkü aktivite
        today_participations = await db.participations.count_documents({
            "created_at": {"$gte": today_start}
        })
        today_reservations = await db.reservations.count_documents({
            "created_at": {"$gte": today_start}
        })
        
        # Kullanıcı dağılımı
        user_distribution = await db.users.aggregate([
            {"$group": {"_id": "$user_type", "count": {"$sum": 1}}}
        ]).to_list(None)
        
        # Spor dağılımı
        sport_distribution = await db.events.aggregate([
            {"$group": {"_id": "$sport", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]).to_list(None)
        
        # Şehir dağılımı
        city_distribution = await db.events.aggregate([
            {"$group": {"_id": "$city", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]).to_list(None)
        
        return success_response(data={
            "overview": {
                "total_users": total_users,
                "total_events": total_events,
                "active_events": active_events,
                "total_venues": total_venues,
                "new_users_this_month": new_users_this_month,
                "new_events_this_month": new_events_this_month,
            },
            "today": {
                "participations": today_participations,
                "reservations": today_reservations,
            },
            "distributions": {
                "users": {item["_id"] or "unknown": item["count"] for item in user_distribution},
                "sports": {item["_id"] or "unknown": item["count"] for item in sport_distribution},
                "cities": {item["_id"] or "unknown": item["count"] for item in city_distribution},
            },
            "generated_at": now.isoformat()
        })
    except Exception as e:
        logger.error(f"Dashboard report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== EVENT REPORTS ====================

@router.get("/events")
async def get_events_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sport: Optional[str] = None,
    city: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Etkinlik raporları - filtrelenebilir"""
    try:
        query = {}
        
        if start_date:
            query["start_date"] = {"$gte": datetime.fromisoformat(start_date)}
        if end_date:
            if "start_date" in query:
                query["start_date"]["$lte"] = datetime.fromisoformat(end_date)
            else:
                query["start_date"] = {"$lte": datetime.fromisoformat(end_date)}
        if sport:
            query["sport"] = sport
        if city:
            query["city"] = city
        if status:
            query["status"] = status
        
        # Toplam sayılar
        total_events = await db.events.count_documents(query)
        
        # Durum dağılımı
        status_pipeline = [
            {"$match": query},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        status_dist = await db.events.aggregate(status_pipeline).to_list(None)
        
        # Katılımcı istatistikleri
        events = await db.events.find(query).to_list(1000)
        total_participants = 0
        total_max_participants = 0
        
        for event in events:
            total_participants += event.get("current_participants", 0)
            total_max_participants += event.get("max_participants", 0)
        
        fill_rate = (total_participants / total_max_participants * 100) if total_max_participants > 0 else 0
        
        # Haftalık trend
        now = datetime.utcnow()
        weekly_trend = []
        for i in range(7):
            day = now - timedelta(days=6-i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            count = await db.events.count_documents({
                **query,
                "created_at": {"$gte": day_start, "$lt": day_end}
            })
            weekly_trend.append({
                "date": day_start.strftime("%d/%m"),
                "count": count
            })
        
        # Format dağılımı
        format_pipeline = [
            {"$match": query},
            {"$group": {"_id": "$format", "count": {"$sum": 1}}}
        ]
        format_dist = await db.events.aggregate(format_pipeline).to_list(None)
        
        return success_response(data={
            "summary": {
                "total_events": total_events,
                "total_participants": total_participants,
                "average_participants": total_participants / total_events if total_events > 0 else 0,
                "fill_rate": round(fill_rate, 1),
            },
            "status_distribution": {item["_id"] or "unknown": item["count"] for item in status_dist},
            "format_distribution": {item["_id"] or "unknown": item["count"] for item in format_dist},
            "weekly_trend": weekly_trend,
            "filters_applied": {
                "start_date": start_date,
                "end_date": end_date,
                "sport": sport,
                "city": city,
                "status": status
            }
        })
    except Exception as e:
        logger.error(f"Events report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== USER REPORTS ====================

@router.get("/users")
async def get_users_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_type: Optional[str] = None,
    city: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Kullanıcı raporları"""
    try:
        query = {}
        
        if start_date:
            query["created_at"] = {"$gte": datetime.fromisoformat(start_date)}
        if end_date:
            if "created_at" in query:
                query["created_at"]["$lte"] = datetime.fromisoformat(end_date)
            else:
                query["created_at"] = {"$lte": datetime.fromisoformat(end_date)}
        if user_type:
            query["user_type"] = user_type
        if city:
            query["city"] = city
        
        # Toplam sayılar
        total_users = await db.users.count_documents(query)
        verified_users = await db.users.count_documents({**query, "is_verified": True})
        
        # Tip dağılımı
        type_pipeline = [
            {"$match": query},
            {"$group": {"_id": "$user_type", "count": {"$sum": 1}}}
        ]
        type_dist = await db.users.aggregate(type_pipeline).to_list(None)
        
        # Şehir dağılımı
        city_pipeline = [
            {"$match": query},
            {"$group": {"_id": "$city", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        city_dist = await db.users.aggregate(city_pipeline).to_list(None)
        
        # Cinsiyet dağılımı
        gender_pipeline = [
            {"$match": query},
            {"$group": {"_id": "$gender", "count": {"$sum": 1}}}
        ]
        gender_dist = await db.users.aggregate(gender_pipeline).to_list(None)
        
        # Haftalık kayıt trendi
        now = datetime.utcnow()
        weekly_trend = []
        for i in range(7):
            day = now - timedelta(days=6-i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            count = await db.users.count_documents({
                **query,
                "created_at": {"$gte": day_start, "$lt": day_end}
            })
            weekly_trend.append({
                "date": day_start.strftime("%d/%m"),
                "count": count
            })
        
        # Aktif kullanıcılar (son 7 günde giriş yapan)
        week_ago = now - timedelta(days=7)
        active_users = await db.users.count_documents({
            **query,
            "last_login": {"$gte": week_ago}
        })
        
        return success_response(data={
            "summary": {
                "total_users": total_users,
                "verified_users": verified_users,
                "verification_rate": round(verified_users / total_users * 100, 1) if total_users > 0 else 0,
                "active_users_7d": active_users,
            },
            "type_distribution": {item["_id"] or "unknown": item["count"] for item in type_dist},
            "city_distribution": {item["_id"] or "unknown": item["count"] for item in city_dist},
            "gender_distribution": {item["_id"] or "unknown": item["count"] for item in gender_dist},
            "weekly_trend": weekly_trend,
        })
    except Exception as e:
        logger.error(f"Users report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== MATCH REPORTS ====================

@router.get("/matches")
async def get_matches_report(
    event_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Maç raporları"""
    try:
        query = {}
        
        if event_id:
            query["event_id"] = event_id
        if start_date:
            query["created_at"] = {"$gte": datetime.fromisoformat(start_date)}
        if end_date:
            if "created_at" in query:
                query["created_at"]["$lte"] = datetime.fromisoformat(end_date)
            else:
                query["created_at"] = {"$lte": datetime.fromisoformat(end_date)}
        
        # Toplam sayılar
        total_matches = await db.matches.count_documents(query)
        completed_matches = await db.matches.count_documents({**query, "status": "completed"})
        pending_matches = await db.matches.count_documents({**query, "status": {"$in": ["pending", "scheduled"]}})
        
        # Durum dağılımı
        status_pipeline = [
            {"$match": query},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        status_dist = await db.matches.aggregate(status_pipeline).to_list(None)
        
        # En çok kazanan oyuncular
        winner_pipeline = [
            {"$match": {**query, "winner_id": {"$ne": None}}},
            {"$group": {"_id": "$winner_id", "wins": {"$sum": 1}}},
            {"$sort": {"wins": -1}},
            {"$limit": 10}
        ]
        top_winners = await db.matches.aggregate(winner_pipeline).to_list(None)
        
        # Kazanan isimleri al
        for winner in top_winners:
            user = await db.users.find_one({"id": winner["_id"]})
            winner["name"] = user.get("full_name", "Bilinmeyen") if user else "Bilinmeyen"
        
        # Günlük maç trendi (son 7 gün)
        now = datetime.utcnow()
        daily_trend = []
        for i in range(7):
            day = now - timedelta(days=6-i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            count = await db.matches.count_documents({
                **query,
                "created_at": {"$gte": day_start, "$lt": day_end}
            })
            daily_trend.append({
                "date": day_start.strftime("%d/%m"),
                "count": count
            })
        
        return success_response(data={
            "summary": {
                "total_matches": total_matches,
                "completed_matches": completed_matches,
                "pending_matches": pending_matches,
                "completion_rate": round(completed_matches / total_matches * 100, 1) if total_matches > 0 else 0,
            },
            "status_distribution": {item["_id"] or "unknown": item["count"] for item in status_dist},
            "top_winners": [{"id": w["_id"], "name": w["name"], "wins": w["wins"]} for w in top_winners],
            "daily_trend": daily_trend,
        })
    except Exception as e:
        logger.error(f"Matches report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== FINANCIAL REPORTS ====================

@router.get("/financial")
async def get_financial_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    facility_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Finansal raporlar"""
    try:
        current_user_id = current_user.get("id")
        
        query = {}
        if facility_id:
            query["facility_id"] = facility_id
        
        # Tarih filtreleri
        date_filter = {}
        if start_date:
            date_filter["$gte"] = datetime.fromisoformat(start_date)
        if end_date:
            date_filter["$lte"] = datetime.fromisoformat(end_date)
        if date_filter:
            query["created_at"] = date_filter
        
        # Gelirler (rezervasyonlar + etkinlik ödemeleri)
        reservation_income = 0
        reservations = await db.reservations.find({
            **query,
            "status": "confirmed",
            "payment_status": "paid"
        }).to_list(1000)
        for r in reservations:
            reservation_income += r.get("total_price", 0)
        
        event_income = 0
        event_payments = await db.event_payments.find({
            **query,
            "status": "completed"
        }).to_list(1000)
        for p in event_payments:
            event_income += p.get("amount", 0)
        
        total_income = reservation_income + event_income
        
        # Giderler
        total_expenses = 0
        expenses = await db.expenses.find(query).to_list(1000)
        for e in expenses:
            total_expenses += e.get("amount", 0)
        
        # Gider kategorileri
        expense_pipeline = [
            {"$match": query},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
        ]
        expense_categories = await db.expenses.aggregate(expense_pipeline).to_list(None)
        
        # Net kar
        net_profit = total_income - total_expenses
        
        # Aylık trend
        now = datetime.utcnow()
        monthly_trend = []
        for i in range(6):
            month_date = now - timedelta(days=30*i)
            month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1)
            
            month_reservations = await db.reservations.find({
                "created_at": {"$gte": month_start, "$lt": month_end},
                "status": "confirmed",
                "payment_status": "paid"
            }).to_list(1000)
            month_income = sum(r.get("total_price", 0) for r in month_reservations)
            
            month_expenses_list = await db.expenses.find({
                "created_at": {"$gte": month_start, "$lt": month_end}
            }).to_list(1000)
            month_expense = sum(e.get("amount", 0) for e in month_expenses_list)
            
            monthly_trend.insert(0, {
                "month": month_start.strftime("%b %Y"),
                "income": month_income,
                "expense": month_expense,
                "profit": month_income - month_expense
            })
        
        return success_response(data={
            "summary": {
                "total_income": total_income,
                "reservation_income": reservation_income,
                "event_income": event_income,
                "total_expenses": total_expenses,
                "net_profit": net_profit,
                "profit_margin": round(net_profit / total_income * 100, 1) if total_income > 0 else 0,
            },
            "expense_breakdown": {item["_id"] or "other": item["total"] for item in expense_categories},
            "monthly_trend": monthly_trend,
        })
    except Exception as e:
        logger.error(f"Financial report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SYSTEM REPORTS ====================

@router.get("/system")
async def get_system_report(current_user: dict = Depends(get_current_user)):
    """Sistem sağlık raporu"""
    try:
        # Koleksiyon sayıları
        collections = {
            "users": await db.users.count_documents({}),
            "events": await db.events.count_documents({}),
            "matches": await db.matches.count_documents({}),
            "messages": await db.messages.count_documents({}),
            "group_messages": await db.group_messages.count_documents({}),
            "reservations": await db.reservations.count_documents({}),
            "venues": await db.venues.count_documents({}),
            "facilities": await db.facilities.count_documents({}),
            "notifications": await db.notifications.count_documents({}),
        }
        
        # Son 24 saat aktivite
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        
        activity_24h = {
            "new_users": await db.users.count_documents({"created_at": {"$gte": day_ago}}),
            "new_events": await db.events.count_documents({"created_at": {"$gte": day_ago}}),
            "new_messages": await db.messages.count_documents({"sent_at": {"$gte": day_ago}}),
            "new_reservations": await db.reservations.count_documents({"created_at": {"$gte": day_ago}}),
            "completed_matches": await db.matches.count_documents({
                "updated_at": {"$gte": day_ago},
                "status": "completed"
            }),
        }
        
        # Veritabanı boyutu (tahmini)
        total_documents = sum(collections.values())
        
        return success_response(data={
            "collections": collections,
            "total_documents": total_documents,
            "activity_24h": activity_24h,
            "server_time": now.isoformat(),
        })
    except Exception as e:
        logger.error(f"System report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== EXPORT REPORTS ====================

@router.get("/export/{report_type}")
async def export_report(
    report_type: str,
    format: str = "json",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Rapor dışa aktarma"""
    try:
        if report_type == "events":
            data = await get_events_report(start_date, end_date, None, None, None, current_user)
        elif report_type == "users":
            data = await get_users_report(start_date, end_date, None, None, current_user)
        elif report_type == "matches":
            data = await get_matches_report(None, start_date, end_date, current_user)
        elif report_type == "financial":
            data = await get_financial_report(start_date, end_date, None, current_user)
        else:
            raise HTTPException(status_code=400, detail="Geçersiz rapor tipi")
        
        return {
            "report_type": report_type,
            "format": format,
            "generated_at": datetime.utcnow().isoformat(),
            "data": data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
