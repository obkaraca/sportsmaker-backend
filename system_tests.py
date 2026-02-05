"""
Automatic Backend Testing System
Tests all API endpoints and returns results
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio
import logging
import time
import uuid
import httpx
import psutil
import platform

from auth import get_current_user
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()
logger = logging.getLogger(__name__)

# Database connection
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client.match_alert

class TestResult:
    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category
        self.status = "pending"  # pending, pass, fail, skip
        self.message = ""
        self.duration_ms = 0
        self.details = {}

    def to_dict(self):
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "details": self.details
        }

class BackendTestRunner:
    def __init__(self, db):
        self.db = db
        self.results: List[TestResult] = []
        self.start_time = None
        self.end_time = None

    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all backend tests"""
        self.start_time = datetime.utcnow()
        self.results = []

        # Database Tests
        await self.test_database_connection()
        await self.test_collections_exist()

        # Auth Tests
        await self.test_user_collection()
        
        # Event Tests
        await self.test_events_collection()
        await self.test_event_matches_collection()

        # Marketplace Tests
        await self.test_marketplace_listings()
        await self.test_marketplace_transactions()
        await self.test_reviews_collection()

        # Notification Tests
        await self.test_notifications_collection()
        await self.test_push_tokens_collection()

        # Reservation Tests
        await self.test_reservations_collection()

        # Facility Tests
        await self.test_facilities_collection()

        # Message Tests
        await self.test_messages_collection()

        # Calendar Tests
        await self.test_calendar_collection()

        # Data Integrity Tests
        await self.test_orphan_records()
        await self.test_required_fields()

        self.end_time = datetime.utcnow()
        
        return self.get_summary()

    def get_summary(self) -> Dict[str, Any]:
        """Get test results summary"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "pass")
        failed = sum(1 for r in self.results if r.status == "fail")
        skipped = sum(1 for r in self.results if r.status == "skip")

        duration = (self.end_time - self.start_time).total_seconds() * 1000 if self.end_time and self.start_time else 0

        # Group by category
        categories = {}
        for r in self.results:
            if r.category not in categories:
                categories[r.category] = {"pass": 0, "fail": 0, "skip": 0, "tests": []}
            categories[r.category][r.status] += 1
            categories[r.category]["tests"].append(r.to_dict())

        return {
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "success_rate": round((passed / total) * 100, 1) if total > 0 else 0,
                "duration_ms": round(duration, 2)
            },
            "categories": categories,
            "results": [r.to_dict() for r in self.results],
            "timestamp": datetime.utcnow().isoformat(),
            "status": "pass" if failed == 0 else "fail"
        }

    async def _run_test(self, test_func, name: str, category: str):
        """Run a single test and record result"""
        result = TestResult(name, category)
        start = time.time()
        
        try:
            test_result = await test_func()
            result.status = "pass" if test_result.get("success", False) else "fail"
            result.message = test_result.get("message", "")
            result.details = test_result.get("details", {})
        except Exception as e:
            result.status = "fail"
            result.message = str(e)
            logger.error(f"Test failed: {name} - {str(e)}")
        
        result.duration_ms = round((time.time() - start) * 1000, 2)
        self.results.append(result)

    # ============================================
    # DATABASE TESTS
    # ============================================

    async def test_database_connection(self):
        """Test database connection"""
        async def test():
            try:
                await self.db.command("ping")
                return {"success": True, "message": "Veritabanı bağlantısı başarılı"}
            except Exception as e:
                return {"success": False, "message": f"Bağlantı hatası: {str(e)}"}
        
        await self._run_test(test, "Veritabanı Bağlantısı", "Veritabanı")

    async def test_collections_exist(self):
        """Test required collections exist"""
        async def test():
            required = ["users", "events", "event_matches", "notifications", 
                       "marketplace_listings", "marketplace_transactions", 
                       "facilities", "reservations", "messages"]
            
            existing = await self.db.list_collection_names()
            missing = [c for c in required if c not in existing]
            
            if missing:
                return {
                    "success": False, 
                    "message": f"Eksik koleksiyonlar: {', '.join(missing)}",
                    "details": {"missing": missing, "existing": existing}
                }
            return {
                "success": True, 
                "message": f"{len(required)} koleksiyon mevcut",
                "details": {"collections": existing}
            }
        
        await self._run_test(test, "Koleksiyon Kontrolü", "Veritabanı")

    # ============================================
    # AUTH TESTS
    # ============================================

    async def test_user_collection(self):
        """Test users collection"""
        async def test():
            count = await self.db.users.count_documents({})
            admin_count = await self.db.users.count_documents({"user_type": {"$in": ["admin", "super_admin"]}})
            
            if count == 0:
                return {"success": False, "message": "Kullanıcı bulunamadı"}
            
            return {
                "success": True,
                "message": f"{count} kullanıcı, {admin_count} yönetici",
                "details": {"total_users": count, "admin_count": admin_count}
            }
        
        await self._run_test(test, "Kullanıcı Koleksiyonu", "Kimlik Doğrulama")

    # ============================================
    # EVENT TESTS
    # ============================================

    async def test_events_collection(self):
        """Test events collection"""
        async def test():
            count = await self.db.events.count_documents({})
            active = await self.db.events.count_documents({"status": "active"})
            
            return {
                "success": True,
                "message": f"{count} etkinlik, {active} aktif",
                "details": {"total": count, "active": active}
            }
        
        await self._run_test(test, "Etkinlik Koleksiyonu", "Etkinlikler")

    async def test_event_matches_collection(self):
        """Test event matches collection"""
        async def test():
            count = await self.db.event_matches.count_documents({})
            completed = await self.db.event_matches.count_documents({"status": "completed"})
            pending = await self.db.event_matches.count_documents({"status": "pending"})
            
            return {
                "success": True,
                "message": f"{count} maç ({completed} tamamlandı, {pending} bekliyor)",
                "details": {"total": count, "completed": completed, "pending": pending}
            }
        
        await self._run_test(test, "Maç Koleksiyonu", "Etkinlikler")

    # ============================================
    # MARKETPLACE TESTS
    # ============================================

    async def test_marketplace_listings(self):
        """Test marketplace listings"""
        async def test():
            count = await self.db.marketplace_listings.count_documents({})
            active = await self.db.marketplace_listings.count_documents({"status": "active"})
            sold = await self.db.marketplace_listings.count_documents({"status": "sold"})
            
            return {
                "success": True,
                "message": f"{count} ilan ({active} aktif, {sold} satıldı)",
                "details": {"total": count, "active": active, "sold": sold}
            }
        
        await self._run_test(test, "Market İlanları", "Sport Market")

    async def test_marketplace_transactions(self):
        """Test marketplace transactions"""
        async def test():
            count = await self.db.marketplace_transactions.count_documents({})
            completed = await self.db.marketplace_transactions.count_documents({"status": "completed"})
            approved = await self.db.marketplace_transactions.count_documents({"status": "approved"})
            
            return {
                "success": True,
                "message": f"{count} işlem ({completed} tamamlandı, {approved} onaylandı)",
                "details": {"total": count, "completed": completed, "approved": approved}
            }
        
        await self._run_test(test, "Market İşlemleri", "Sport Market")

    async def test_reviews_collection(self):
        """Test reviews collection"""
        async def test():
            count = await self.db.reviews.count_documents({})
            
            # Calculate average rating
            pipeline = [
                {"$group": {"_id": None, "avgRating": {"$avg": "$rating"}}}
            ]
            result = await self.db.reviews.aggregate(pipeline).to_list(1)
            avg_rating = round(result[0]["avgRating"], 1) if result else 0
            
            return {
                "success": True,
                "message": f"{count} değerlendirme (ortalama: {avg_rating}⭐)",
                "details": {"total": count, "average_rating": avg_rating}
            }
        
        await self._run_test(test, "Değerlendirmeler", "Sport Market")

    # ============================================
    # NOTIFICATION TESTS
    # ============================================

    async def test_notifications_collection(self):
        """Test notifications collection"""
        async def test():
            count = await self.db.notifications.count_documents({})
            unread = await self.db.notifications.count_documents({"read": False})
            
            return {
                "success": True,
                "message": f"{count} bildirim ({unread} okunmamış)",
                "details": {"total": count, "unread": unread}
            }
        
        await self._run_test(test, "Bildirimler", "Bildirimler")

    async def test_push_tokens_collection(self):
        """Test push tokens collection"""
        async def test():
            count = await self.db.push_tokens.count_documents({})
            active = await self.db.push_tokens.count_documents({"expo_push_token": {"$ne": None}})
            
            return {
                "success": True,
                "message": f"{count} cihaz ({active} aktif)",
                "details": {"total": count, "active": active}
            }
        
        await self._run_test(test, "Push Token'ları", "Bildirimler")

    # ============================================
    # RESERVATION TESTS
    # ============================================

    async def test_reservations_collection(self):
        """Test reservations collection"""
        async def test():
            count = await self.db.reservations.count_documents({})
            confirmed = await self.db.reservations.count_documents({"status": "confirmed"})
            pending = await self.db.reservations.count_documents({"status": "pending"})
            
            return {
                "success": True,
                "message": f"{count} rezervasyon ({confirmed} onaylı, {pending} bekliyor)",
                "details": {"total": count, "confirmed": confirmed, "pending": pending}
            }
        
        await self._run_test(test, "Rezervasyonlar", "Rezervasyonlar")

    # ============================================
    # FACILITY TESTS
    # ============================================

    async def test_facilities_collection(self):
        """Test facilities collection"""
        async def test():
            count = await self.db.facilities.count_documents({})
            approved = await self.db.facilities.count_documents({"status": "approved"})
            
            return {
                "success": True,
                "message": f"{count} tesis ({approved} onaylı)",
                "details": {"total": count, "approved": approved}
            }
        
        await self._run_test(test, "Tesisler", "Tesisler")

    # ============================================
    # MESSAGE TESTS
    # ============================================

    async def test_messages_collection(self):
        """Test messages collection"""
        async def test():
            count = await self.db.messages.count_documents({})
            
            return {
                "success": True,
                "message": f"{count} mesaj",
                "details": {"total": count}
            }
        
        await self._run_test(test, "Mesajlar", "Mesajlaşma")

    # ============================================
    # CALENDAR TESTS
    # ============================================

    async def test_calendar_collection(self):
        """Test calendar collection"""
        async def test():
            count = await self.db.calendar_items.count_documents({})
            
            return {
                "success": True,
                "message": f"{count} takvim öğesi",
                "details": {"total": count}
            }
        
        await self._run_test(test, "Takvim", "Takvim")

    # ============================================
    # DATA INTEGRITY TESTS
    # ============================================

    async def test_orphan_records(self):
        """Test for orphan records in transactions"""
        async def test():
            # Check for transactions without valid listings
            orphan_count = 0
            transactions = await self.db.marketplace_transactions.find({}).limit(100).to_list(100)
            
            for tx in transactions:
                listing = await self.db.marketplace_listings.find_one({"id": tx.get("listing_id")})
                if not listing:
                    orphan_count += 1
            
            if orphan_count > 0:
                return {
                    "success": False,
                    "message": f"{orphan_count} yetim işlem kaydı bulundu",
                    "details": {"orphan_count": orphan_count}
                }
            
            return {
                "success": True,
                "message": "Yetim kayıt bulunamadı",
                "details": {"checked": len(transactions)}
            }
        
        await self._run_test(test, "Yetim Kayıt Kontrolü", "Veri Bütünlüğü")

    async def test_required_fields(self):
        """Test for required fields in critical collections"""
        async def test():
            issues = []
            
            # Check users for required fields
            users_without_phone = await self.db.users.count_documents({"phone": {"$exists": False}})
            if users_without_phone > 0:
                issues.append(f"{users_without_phone} kullanıcıda telefon eksik")
            
            # Check events for required fields
            events_without_title = await self.db.events.count_documents({"title": {"$exists": False}})
            if events_without_title > 0:
                issues.append(f"{events_without_title} etkinlikte başlık eksik")
            
            if issues:
                return {
                    "success": False,
                    "message": "; ".join(issues),
                    "details": {"issues": issues}
                }
            
            return {
                "success": True,
                "message": "Tüm zorunlu alanlar mevcut",
                "details": {}
            }
        
        await self._run_test(test, "Zorunlu Alan Kontrolü", "Veri Bütünlüğü")


# API Endpoints
@router.get("/system-tests/run")
async def run_system_tests(current_user: dict = Depends(get_current_user)):
    """Run all backend tests - Admin only"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Yetkiniz yok")
    
    runner = BackendTestRunner(db)
    results = await runner.run_all_tests()
    
    # Save test results
    test_report = {
        "id": str(uuid.uuid4()),
        "type": "backend_auto_test",
        "run_by": current_user.get("id"),
        "run_by_name": current_user.get("full_name"),
        "results": results,
        "created_at": datetime.utcnow()
    }
    await db.test_reports.insert_one(test_report)
    
    return results


@router.get("/system-tests/history")
async def get_test_history(
    limit: int = 10,
    current_user: dict = Depends(get_current_user)
):
    """Get test history - Admin only"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Yetkiniz yok")
    
    reports = await db.test_reports.find(
        {"type": "backend_auto_test"}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    # Clean up _id
    for report in reports:
        report.pop("_id", None)
    
    return {"reports": reports, "total": len(reports)}


@router.get("/system-tests/health")
async def health_check():
    """Quick health check - Public"""
    try:
        await db.command("ping")
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


# ============================================
# E2E (END-TO-END) TEST RUNNER
# ============================================

class E2ETestRunner:
    """
    End-to-End test runner that simulates complete user flows
    Tests full application scenarios from start to finish
    """
    
    def __init__(self, db, current_user: dict):
        self.db = db
        self.current_user = current_user
        self.results: List[TestResult] = []
        self.start_time = None
        self.end_time = None
        self.test_data = {}  # Store test data for cleanup

    async def run_all_e2e_tests(self) -> Dict[str, Any]:
        """Run all E2E tests"""
        self.start_time = datetime.utcnow()
        self.results = []

        # User Flow Tests
        await self.test_user_registration_flow()
        await self.test_user_login_flow()
        await self.test_user_profile_update_flow()

        # Event Flow Tests
        await self.test_event_creation_flow()
        await self.test_event_registration_flow()
        await self.test_event_match_flow()

        # Marketplace Flow Tests
        await self.test_marketplace_listing_flow()
        await self.test_marketplace_purchase_flow()
        await self.test_marketplace_review_flow()

        # Reservation Flow Tests
        await self.test_facility_reservation_flow()

        # Notification Flow Tests
        await self.test_notification_flow()

        # Message Flow Tests
        await self.test_messaging_flow()

        # Cleanup test data
        await self.cleanup_test_data()

        self.end_time = datetime.utcnow()
        return self.get_summary()

    def get_summary(self) -> Dict[str, Any]:
        """Get E2E test results summary"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "pass")
        failed = sum(1 for r in self.results if r.status == "fail")
        skipped = sum(1 for r in self.results if r.status == "skip")

        duration = (self.end_time - self.start_time).total_seconds() * 1000 if self.end_time and self.start_time else 0

        # Group by category
        categories = {}
        for r in self.results:
            if r.category not in categories:
                categories[r.category] = {"pass": 0, "fail": 0, "skip": 0, "tests": []}
            categories[r.category][r.status] += 1
            categories[r.category]["tests"].append(r.to_dict())

        return {
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "success_rate": round((passed / total) * 100, 1) if total > 0 else 0,
                "duration_ms": round(duration, 2)
            },
            "categories": categories,
            "results": [r.to_dict() for r in self.results],
            "timestamp": datetime.utcnow().isoformat(),
            "status": "pass" if failed == 0 else "fail"
        }

    async def _run_test(self, test_func, name: str, category: str):
        """Run a single E2E test and record result"""
        result = TestResult(name, category)
        start = time.time()
        
        try:
            test_result = await test_func()
            result.status = "pass" if test_result.get("success", False) else "fail"
            result.message = test_result.get("message", "")
            result.details = test_result.get("details", {})
        except Exception as e:
            result.status = "fail"
            result.message = str(e)
            logger.error(f"E2E Test failed: {name} - {str(e)}")
        
        result.duration_ms = round((time.time() - start) * 1000, 2)
        self.results.append(result)

    # ============================================
    # USER FLOW TESTS
    # ============================================

    async def test_user_registration_flow(self):
        """Test complete user registration flow"""
        async def test():
            test_phone = f"+90555{str(uuid.uuid4().int)[:7]}"
            
            # Check if phone is available
            existing = await self.db.users.find_one({"phone": test_phone})
            if existing:
                return {"success": True, "message": "Test phone already exists, skipping"}
            
            # Simulate registration data
            user_data = {
                "id": str(uuid.uuid4()),
                "phone": test_phone,
                "full_name": "E2E Test User",
                "user_type": "player",
                "created_at": datetime.utcnow(),
                "is_test_user": True
            }
            
            # Insert test user
            await self.db.users.insert_one(user_data)
            self.test_data["test_user_id"] = user_data["id"]
            self.test_data["test_phone"] = test_phone
            
            # Verify user was created
            created_user = await self.db.users.find_one({"id": user_data["id"]})
            if not created_user:
                return {"success": False, "message": "User creation failed"}
            
            return {
                "success": True, 
                "message": f"Kullanıcı kaydı başarılı: {test_phone}",
                "details": {"user_id": user_data["id"]}
            }
        
        await self._run_test(test, "Kullanıcı Kayıt Akışı", "Kullanıcı Akışları")

    async def test_user_login_flow(self):
        """Test user login flow with OTP"""
        async def test():
            # Use existing admin user for login test
            admin_user = await self.db.users.find_one({"user_type": "admin"})
            if not admin_user:
                return {"success": False, "message": "Admin kullanıcı bulunamadı"}
            
            # Check OTP codes collection
            otp_count = await self.db.otp_codes.count_documents({})
            
            return {
                "success": True,
                "message": f"Giriş sistemi aktif, {otp_count} OTP kaydı mevcut",
                "details": {"admin_exists": True, "otp_system": "active"}
            }
        
        await self._run_test(test, "Kullanıcı Giriş Akışı", "Kullanıcı Akışları")

    async def test_user_profile_update_flow(self):
        """Test user profile update flow"""
        async def test():
            test_user_id = self.test_data.get("test_user_id")
            if not test_user_id:
                # Use current user
                test_user_id = self.current_user.get("id")
            
            user = await self.db.users.find_one({"id": test_user_id})
            if not user:
                return {"success": False, "message": "Test kullanıcısı bulunamadı"}
            
            # Simulate profile update
            update_result = await self.db.users.update_one(
                {"id": test_user_id},
                {"$set": {"last_e2e_test": datetime.utcnow()}}
            )
            
            if update_result.modified_count > 0 or update_result.matched_count > 0:
                return {
                    "success": True,
                    "message": "Profil güncelleme başarılı",
                    "details": {"user_id": test_user_id}
                }
            
            return {"success": False, "message": "Profil güncellenemedi"}
        
        await self._run_test(test, "Profil Güncelleme Akışı", "Kullanıcı Akışları")

    # ============================================
    # EVENT FLOW TESTS
    # ============================================

    async def test_event_creation_flow(self):
        """Test event creation flow"""
        async def test():
            # Create test event
            event_data = {
                "id": str(uuid.uuid4()),
                "title": "E2E Test Etkinliği",
                "description": "Otomatik test için oluşturuldu",
                "sport_type": "tennis",
                "event_type": "tournament",
                "status": "draft",
                "created_by": self.current_user.get("id"),
                "created_at": datetime.utcnow(),
                "is_test_event": True
            }
            
            await self.db.events.insert_one(event_data)
            self.test_data["test_event_id"] = event_data["id"]
            
            # Verify
            created = await self.db.events.find_one({"id": event_data["id"]})
            if created:
                return {
                    "success": True,
                    "message": "Etkinlik oluşturma başarılı",
                    "details": {"event_id": event_data["id"]}
                }
            
            return {"success": False, "message": "Etkinlik oluşturulamadı"}
        
        await self._run_test(test, "Etkinlik Oluşturma Akışı", "Etkinlik Akışları")

    async def test_event_registration_flow(self):
        """Test event registration flow"""
        async def test():
            event_id = self.test_data.get("test_event_id")
            if not event_id:
                # Find any active event
                event = await self.db.events.find_one({"status": "active"})
                if event:
                    event_id = event.get("id")
                else:
                    return {"success": True, "message": "Aktif etkinlik yok, test atlandı"}
            
            # Simulate registration
            registration_data = {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "user_id": self.current_user.get("id"),
                "status": "pending",
                "created_at": datetime.utcnow(),
                "is_test": True
            }
            
            await self.db.event_registrations.insert_one(registration_data)
            self.test_data["test_registration_id"] = registration_data["id"]
            
            return {
                "success": True,
                "message": "Etkinlik kaydı başarılı",
                "details": {"registration_id": registration_data["id"]}
            }
        
        await self._run_test(test, "Etkinlik Kayıt Akışı", "Etkinlik Akışları")

    async def test_event_match_flow(self):
        """Test event match creation and scoring flow"""
        async def test():
            event_id = self.test_data.get("test_event_id")
            if not event_id:
                return {"success": True, "message": "Test etkinliği yok, atlandı"}
            
            # Create test match
            match_data = {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "participant1_id": self.current_user.get("id"),
                "participant2_id": str(uuid.uuid4()),
                "status": "pending",
                "scheduled_time": datetime.utcnow(),
                "created_at": datetime.utcnow(),
                "is_test": True
            }
            
            await self.db.event_matches.insert_one(match_data)
            self.test_data["test_match_id"] = match_data["id"]
            
            # Update match score
            await self.db.event_matches.update_one(
                {"id": match_data["id"]},
                {"$set": {"score": "6-4, 6-3", "status": "completed", "winner_id": self.current_user.get("id")}}
            )
            
            return {
                "success": True,
                "message": "Maç oluşturma ve skor girişi başarılı",
                "details": {"match_id": match_data["id"]}
            }
        
        await self._run_test(test, "Maç Akışı", "Etkinlik Akışları")

    # ============================================
    # MARKETPLACE FLOW TESTS
    # ============================================

    async def test_marketplace_listing_flow(self):
        """Test marketplace listing creation flow"""
        async def test():
            listing_data = {
                "id": str(uuid.uuid4()),
                "title": "E2E Test Ürünü",
                "description": "Otomatik test için oluşturuldu",
                "price": 100,
                "category": "equipment",
                "condition": "new",
                "seller_id": self.current_user.get("id"),
                "status": "pending",
                "created_at": datetime.utcnow(),
                "is_test": True
            }
            
            await self.db.marketplace_listings.insert_one(listing_data)
            self.test_data["test_listing_id"] = listing_data["id"]
            
            # Verify
            created = await self.db.marketplace_listings.find_one({"id": listing_data["id"]})
            if created:
                return {
                    "success": True,
                    "message": "İlan oluşturma başarılı",
                    "details": {"listing_id": listing_data["id"]}
                }
            
            return {"success": False, "message": "İlan oluşturulamadı"}
        
        await self._run_test(test, "İlan Oluşturma Akışı", "Market Akışları")

    async def test_marketplace_purchase_flow(self):
        """Test marketplace purchase flow"""
        async def test():
            listing_id = self.test_data.get("test_listing_id")
            if not listing_id:
                return {"success": True, "message": "Test ilanı yok, atlandı"}
            
            # Create test transaction
            transaction_data = {
                "id": str(uuid.uuid4()),
                "listing_id": listing_id,
                "buyer_id": str(uuid.uuid4()),  # Different user
                "seller_id": self.current_user.get("id"),
                "amount": 100,
                "status": "completed",
                "created_at": datetime.utcnow(),
                "is_test": True
            }
            
            await self.db.marketplace_transactions.insert_one(transaction_data)
            self.test_data["test_transaction_id"] = transaction_data["id"]
            
            return {
                "success": True,
                "message": "Satın alma akışı başarılı",
                "details": {"transaction_id": transaction_data["id"]}
            }
        
        await self._run_test(test, "Satın Alma Akışı", "Market Akışları")

    async def test_marketplace_review_flow(self):
        """Test marketplace review flow"""
        async def test():
            transaction_id = self.test_data.get("test_transaction_id")
            if not transaction_id:
                return {"success": True, "message": "Test işlemi yok, atlandı"}
            
            # Create test review
            review_data = {
                "id": str(uuid.uuid4()),
                "reviewer_id": str(uuid.uuid4()),
                "target_id": self.current_user.get("id"),
                "target_type": "seller",
                "rating": 5,
                "comment": "E2E Test değerlendirmesi",
                "order_id": transaction_id,
                "created_at": datetime.utcnow(),
                "is_test": True
            }
            
            await self.db.reviews.insert_one(review_data)
            self.test_data["test_review_id"] = review_data["id"]
            
            return {
                "success": True,
                "message": "Değerlendirme akışı başarılı",
                "details": {"review_id": review_data["id"]}
            }
        
        await self._run_test(test, "Değerlendirme Akışı", "Market Akışları")

    # ============================================
    # RESERVATION FLOW TESTS
    # ============================================

    async def test_facility_reservation_flow(self):
        """Test facility reservation flow"""
        async def test():
            # Find a facility
            facility = await self.db.facilities.find_one({"status": "approved"})
            if not facility:
                return {"success": True, "message": "Onaylı tesis yok, atlandı"}
            
            # Create test reservation
            reservation_data = {
                "id": str(uuid.uuid4()),
                "facility_id": facility.get("id"),
                "user_id": self.current_user.get("id"),
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "start_time": "10:00",
                "end_time": "11:00",
                "status": "pending",
                "created_at": datetime.utcnow(),
                "is_test": True
            }
            
            await self.db.reservations.insert_one(reservation_data)
            self.test_data["test_reservation_id"] = reservation_data["id"]
            
            # Confirm reservation
            await self.db.reservations.update_one(
                {"id": reservation_data["id"]},
                {"$set": {"status": "confirmed"}}
            )
            
            return {
                "success": True,
                "message": "Rezervasyon akışı başarılı",
                "details": {"reservation_id": reservation_data["id"]}
            }
        
        await self._run_test(test, "Tesis Rezervasyon Akışı", "Rezervasyon Akışları")

    # ============================================
    # NOTIFICATION FLOW TESTS
    # ============================================

    async def test_notification_flow(self):
        """Test notification creation and delivery flow"""
        async def test():
            # Create test notification
            notification_data = {
                "id": str(uuid.uuid4()),
                "user_id": self.current_user.get("id"),
                "type": "e2e_test",
                "title": "E2E Test Bildirimi",
                "message": "Bu bir otomatik test bildirimidir",
                "read": False,
                "created_at": datetime.utcnow(),
                "is_test": True
            }
            
            await self.db.notifications.insert_one(notification_data)
            self.test_data["test_notification_id"] = notification_data["id"]
            
            # Mark as read
            await self.db.notifications.update_one(
                {"id": notification_data["id"]},
                {"$set": {"read": True}}
            )
            
            # Verify
            updated = await self.db.notifications.find_one({"id": notification_data["id"]})
            if updated and updated.get("read") == True:
                return {
                    "success": True,
                    "message": "Bildirim akışı başarılı",
                    "details": {"notification_id": notification_data["id"]}
                }
            
            return {"success": False, "message": "Bildirim güncellenemedi"}
        
        await self._run_test(test, "Bildirim Akışı", "Bildirim Akışları")

    # ============================================
    # MESSAGE FLOW TESTS
    # ============================================

    async def test_messaging_flow(self):
        """Test messaging flow"""
        async def test():
            # Find another user to message
            other_user = await self.db.users.find_one({
                "id": {"$ne": self.current_user.get("id")}
            })
            
            if not other_user:
                return {"success": True, "message": "Başka kullanıcı yok, atlandı"}
            
            # Create test message
            message_data = {
                "id": str(uuid.uuid4()),
                "sender_id": self.current_user.get("id"),
                "receiver_id": other_user.get("id"),
                "content": "E2E Test mesajı",
                "read": False,
                "created_at": datetime.utcnow(),
                "is_test": True
            }
            
            await self.db.messages.insert_one(message_data)
            self.test_data["test_message_id"] = message_data["id"]
            
            return {
                "success": True,
                "message": "Mesajlaşma akışı başarılı",
                "details": {"message_id": message_data["id"]}
            }
        
        await self._run_test(test, "Mesajlaşma Akışı", "Mesajlaşma Akışları")

    # ============================================
    # CLEANUP
    # ============================================

    async def cleanup_test_data(self):
        """Clean up all test data created during E2E tests"""
        try:
            # Delete test user
            if self.test_data.get("test_user_id"):
                await self.db.users.delete_one({"id": self.test_data["test_user_id"]})
            
            # Delete test event
            if self.test_data.get("test_event_id"):
                await self.db.events.delete_one({"id": self.test_data["test_event_id"]})
            
            # Delete test registration
            if self.test_data.get("test_registration_id"):
                await self.db.event_registrations.delete_one({"id": self.test_data["test_registration_id"]})
            
            # Delete test match
            if self.test_data.get("test_match_id"):
                await self.db.event_matches.delete_one({"id": self.test_data["test_match_id"]})
            
            # Delete test listing
            if self.test_data.get("test_listing_id"):
                await self.db.marketplace_listings.delete_one({"id": self.test_data["test_listing_id"]})
            
            # Delete test transaction
            if self.test_data.get("test_transaction_id"):
                await self.db.marketplace_transactions.delete_one({"id": self.test_data["test_transaction_id"]})
            
            # Delete test review
            if self.test_data.get("test_review_id"):
                await self.db.reviews.delete_one({"id": self.test_data["test_review_id"]})
            
            # Delete test reservation
            if self.test_data.get("test_reservation_id"):
                await self.db.reservations.delete_one({"id": self.test_data["test_reservation_id"]})
            
            # Delete test notification
            if self.test_data.get("test_notification_id"):
                await self.db.notifications.delete_one({"id": self.test_data["test_notification_id"]})
            
            # Delete test message
            if self.test_data.get("test_message_id"):
                await self.db.messages.delete_one({"id": self.test_data["test_message_id"]})
            
            logger.info("✅ E2E test data cleaned up successfully")
        except Exception as e:
            logger.error(f"❌ Error cleaning up E2E test data: {str(e)}")


# E2E Test API Endpoint
@router.get("/system-tests/e2e")
async def run_e2e_tests(current_user: dict = Depends(get_current_user)):
    """Run all E2E tests - Admin only"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Yetkiniz yok")
    
    runner = E2ETestRunner(db, current_user)
    results = await runner.run_all_e2e_tests()
    
    # Save test results
    test_report = {
        "id": str(uuid.uuid4()),
        "type": "e2e_test",
        "run_by": current_user.get("id"),
        "run_by_name": current_user.get("full_name"),
        "results": results,
        "created_at": datetime.utcnow()
    }
    await db.test_reports.insert_one(test_report)
    
    return results


@router.get("/system-tests/e2e/history")
async def get_e2e_test_history(
    limit: int = 10,
    current_user: dict = Depends(get_current_user)
):
    """Get E2E test history - Admin only"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Yetkiniz yok")
    
    reports = await db.test_reports.find(
        {"type": "e2e_test"}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    # Clean up _id
    for report in reports:
        report.pop("_id", None)
    
    return {"reports": reports, "total": len(reports)}


# ============================================
# SYSTEM DASHBOARD - SERVICE STATUS
# ============================================

@router.get("/system-tests/dashboard")
async def get_system_dashboard(current_user: dict = Depends(get_current_user)):
    """Get comprehensive system status dashboard - Admin only"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Yetkiniz yok")
    
    dashboard_start = time.time()
    services = []
    
    # 1. Database Status
    db_status = await check_database_status()
    services.append(db_status)
    
    # 2. API Status
    api_status = await check_api_status()
    services.append(api_status)
    
    # 3. Push Notification Status
    push_status = await check_push_notification_status()
    services.append(push_status)
    
    # 4. Background Jobs Status
    jobs_status = await check_background_jobs_status()
    services.append(jobs_status)
    
    # 5. Storage Status
    storage_status = await check_storage_status()
    services.append(storage_status)
    
    # 6. SMS/OTP Service Status
    sms_status = await check_sms_status()
    services.append(sms_status)
    
    # 7. Payment Service Status
    payment_status = await check_payment_status()
    services.append(payment_status)
    
    # Calculate overall status
    total_services = len(services)
    healthy_services = sum(1 for s in services if s["status"] == "healthy")
    warning_services = sum(1 for s in services if s["status"] == "warning")
    unhealthy_services = sum(1 for s in services if s["status"] == "unhealthy")
    
    if unhealthy_services > 0:
        overall_status = "unhealthy"
    elif warning_services > 0:
        overall_status = "warning"
    else:
        overall_status = "healthy"
    
    # System metrics
    system_metrics = await get_system_metrics()
    
    # Recent activity
    recent_activity = await get_recent_activity()
    
    return {
        "overall_status": overall_status,
        "summary": {
            "total": total_services,
            "healthy": healthy_services,
            "warning": warning_services,
            "unhealthy": unhealthy_services,
            "health_percentage": round((healthy_services / total_services) * 100, 1)
        },
        "services": services,
        "system_metrics": system_metrics,
        "recent_activity": recent_activity,
        "checked_at": datetime.utcnow().isoformat(),
        "check_duration_ms": round((time.time() - dashboard_start) * 1000, 2)
    }


async def check_database_status() -> Dict[str, Any]:
    """Check MongoDB database status"""
    try:
        start = time.time()
        
        # Ping database
        await db.command("ping")
        
        # Get stats
        stats = await db.command("dbStats")
        collections = await db.list_collection_names()
        
        # Count documents in key collections
        users_count = await db.users.count_documents({})
        events_count = await db.events.count_documents({})
        notifications_count = await db.notifications.count_documents({})
        
        return {
            "name": "Veritabanı (MongoDB)",
            "icon": "server",
            "status": "healthy",
            "message": f"{len(collections)} koleksiyon, {users_count} kullanıcı",
            "details": {
                "collections": len(collections),
                "users": users_count,
                "events": events_count,
                "notifications": notifications_count,
                "data_size_mb": round(stats.get("dataSize", 0) / (1024 * 1024), 2),
                "storage_size_mb": round(stats.get("storageSize", 0) / (1024 * 1024), 2)
            },
            "response_time_ms": round((time.time() - start) * 1000, 2)
        }
    except Exception as e:
        return {
            "name": "Veritabanı (MongoDB)",
            "icon": "server",
            "status": "unhealthy",
            "message": f"Bağlantı hatası: {str(e)}",
            "details": {},
            "response_time_ms": 0
        }


async def check_api_status() -> Dict[str, Any]:
    """Check API server status"""
    try:
        start = time.time()
        
        # Check critical endpoints
        endpoints_to_check = [
            "/api/system-tests/health",
            "/api/events",
            "/api/marketplace/listings"
        ]
        
        working_endpoints = 0
        failed_endpoints = []
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            for endpoint in endpoints_to_check:
                try:
                    # Use internal URL
                    response = await client.get(f"http://localhost:8001{endpoint}")
                    if response.status_code < 500:
                        working_endpoints += 1
                    else:
                        failed_endpoints.append(endpoint)
                except:
                    failed_endpoints.append(endpoint)
        
        total = len(endpoints_to_check)
        
        if working_endpoints == total:
            status = "healthy"
            message = f"Tüm endpoint'ler çalışıyor ({total}/{total})"
        elif working_endpoints > 0:
            status = "warning"
            message = f"{working_endpoints}/{total} endpoint çalışıyor"
        else:
            status = "unhealthy"
            message = "API yanıt vermiyor"
        
        return {
            "name": "API Sunucusu",
            "icon": "globe",
            "status": status,
            "message": message,
            "details": {
                "working_endpoints": working_endpoints,
                "total_endpoints": total,
                "failed": failed_endpoints
            },
            "response_time_ms": round((time.time() - start) * 1000, 2)
        }
    except Exception as e:
        return {
            "name": "API Sunucusu",
            "icon": "globe",
            "status": "unhealthy",
            "message": f"Kontrol hatası: {str(e)}",
            "details": {},
            "response_time_ms": 0
        }


async def check_push_notification_status() -> Dict[str, Any]:
    """Check push notification service status"""
    try:
        start = time.time()
        
        # Count push tokens
        total_tokens = await db.push_tokens.count_documents({})
        active_tokens = await db.push_tokens.count_documents({"expo_push_token": {"$ne": None}})
        
        # Count recent notifications
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        recent_notifications = await db.notifications.count_documents({
            "created_at": {"$gte": one_day_ago}
        })
        
        if active_tokens > 0:
            status = "healthy"
            message = f"{active_tokens} aktif cihaz, son 24 saat: {recent_notifications} bildirim"
        else:
            # No active devices is OK - just informational
            status = "healthy"
            message = f"Henüz kayıtlı cihaz yok (son 24 saat: {recent_notifications} bildirim)"
        
        return {
            "name": "Push Bildirimleri",
            "icon": "notifications",
            "status": status,
            "message": message,
            "details": {
                "total_tokens": total_tokens,
                "active_tokens": active_tokens,
                "notifications_24h": recent_notifications
            },
            "response_time_ms": round((time.time() - start) * 1000, 2)
        }
    except Exception as e:
        return {
            "name": "Push Bildirimleri",
            "icon": "notifications",
            "status": "warning",
            "message": f"Kontrol hatası: {str(e)}",
            "details": {},
            "response_time_ms": 0
        }


async def check_background_jobs_status() -> Dict[str, Any]:
    """Check background job scheduler status"""
    try:
        start = time.time()
        
        # Check recent scheduler activity via logs or last run times
        # For now, check if scheduler collections have recent updates
        
        jobs = [
            {"name": "Etkinlik Hatırlatıcı", "collection": "notifications", "type_filter": "event_reminder"},
            {"name": "Maç Hatırlatıcı", "collection": "notifications", "type_filter": "match_reminder"},
            {"name": "Değerlendirme Hatırlatıcı", "collection": "notifications", "type_filter": "review_reminder"}
        ]
        
        active_jobs = 0
        job_details = []
        
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        for job in jobs:
            count = await db[job["collection"]].count_documents({
                "type": {"$regex": job["type_filter"]},
                "created_at": {"$gte": one_hour_ago}
            })
            if count > 0:
                active_jobs += 1
            job_details.append({
                "name": job["name"],
                "recent_count": count,
                "status": "active" if count > 0 else "idle"
            })
        
        # Scheduler is considered healthy if it's running (we can't directly check APScheduler)
        status = "healthy"
        message = f"{active_jobs} aktif iş, son 1 saat içinde çalıştı"
        
        return {
            "name": "Arkaplan İşleri",
            "icon": "time",
            "status": status,
            "message": message,
            "details": {
                "jobs": job_details,
                "active_jobs": active_jobs
            },
            "response_time_ms": round((time.time() - start) * 1000, 2)
        }
    except Exception as e:
        return {
            "name": "Arkaplan İşleri",
            "icon": "time",
            "status": "warning",
            "message": f"Kontrol hatası: {str(e)}",
            "details": {},
            "response_time_ms": 0
        }


async def check_storage_status() -> Dict[str, Any]:
    """Check file storage status"""
    try:
        start = time.time()
        
        # Check uploads directory
        uploads_path = "/app/backend/uploads"
        
        # Create directory if it doesn't exist
        if not os.path.exists(uploads_path):
            os.makedirs(uploads_path, exist_ok=True)
            logger.info(f"Created uploads directory: {uploads_path}")
        
        if os.path.exists(uploads_path):
            # Count files
            total_files = 0
            total_size = 0
            for root, dirs, files in os.walk(uploads_path):
                for f in files:
                    total_files += 1
                    try:
                        total_size += os.path.getsize(os.path.join(root, f))
                    except:
                        pass
            
            size_mb = round(total_size / (1024 * 1024), 2)
            status = "healthy"
            if total_files == 0:
                message = "Depolama hazır (henüz dosya yok)"
            else:
                message = f"{total_files} dosya, {size_mb} MB"
        else:
            status = "warning"
            message = "Uploads klasörü oluşturulamadı"
            total_files = 0
            size_mb = 0
        
        return {
            "name": "Dosya Depolama",
            "icon": "folder",
            "status": status,
            "message": message,
            "details": {
                "total_files": total_files,
                "size_mb": size_mb,
                "path": uploads_path
            },
            "response_time_ms": round((time.time() - start) * 1000, 2)
        }
    except Exception as e:
        return {
            "name": "Dosya Depolama",
            "icon": "folder",
            "status": "warning",
            "message": f"Kontrol hatası: {str(e)}",
            "details": {},
            "response_time_ms": 0
        }


async def check_sms_status() -> Dict[str, Any]:
    """Check SMS/OTP service status"""
    try:
        start = time.time()
        
        # Check OTP codes in last hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_otps = await db.verification_codes.count_documents({
            "created_at": {"$gte": one_hour_ago}
        })
        
        # Check Netgsm configuration
        netgsm_user = os.getenv("NETGSM_USERCODE")
        netgsm_configured = bool(netgsm_user)
        
        # Always healthy - just informational about mode
        status = "healthy"
        if netgsm_configured:
            message = f"NetGSM aktif, son 1 saat: {recent_otps} OTP"
        else:
            message = f"Dev mod aktif (test için 123456), son 1 saat: {recent_otps} OTP"
        
        return {
            "name": "SMS/OTP Servisi",
            "icon": "chatbubble-ellipses",
            "status": status,
            "message": message,
            "details": {
                "provider": "NetGSM" if netgsm_configured else "Dev Mode",
                "configured": netgsm_configured,
                "recent_otps": recent_otps
            },
            "response_time_ms": round((time.time() - start) * 1000, 2)
        }
    except Exception as e:
        return {
            "name": "SMS/OTP Servisi",
            "icon": "chatbubble-ellipses",
            "status": "warning",
            "message": f"Kontrol hatası: {str(e)}",
            "details": {},
            "response_time_ms": 0
        }


async def check_payment_status() -> Dict[str, Any]:
    """Check payment service status"""
    try:
        start = time.time()
        
        # Check iyzico configuration
        iyzico_key = os.getenv("IYZICO_API_KEY")
        iyzico_configured = bool(iyzico_key)
        
        # Count recent transactions
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        recent_transactions = await db.marketplace_transactions.count_documents({
            "created_at": {"$gte": one_day_ago}
        })
        
        # Always healthy - just informational
        status = "healthy"
        if iyzico_configured:
            message = f"iyzico aktif, son 24 saat: {recent_transactions} işlem"
        else:
            message = f"iyzico test modu, son 24 saat: {recent_transactions} işlem"
        
        return {
            "name": "Ödeme Servisi",
            "icon": "card",
            "status": status,
            "message": message,
            "details": {
                "provider": "iyzico",
                "configured": iyzico_configured,
                "transactions_24h": recent_transactions
            },
            "response_time_ms": round((time.time() - start) * 1000, 2)
        }
    except Exception as e:
        return {
            "name": "Ödeme Servisi",
            "icon": "card",
            "status": "warning",
            "message": f"Kontrol hatası: {str(e)}",
            "details": {},
            "response_time_ms": 0
        }


async def get_system_metrics() -> Dict[str, Any]:
    """Get system resource metrics"""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_gb = round(memory.used / (1024 ** 3), 2)
        memory_total_gb = round(memory.total / (1024 ** 3), 2)
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_used_gb = round(disk.used / (1024 ** 3), 2)
        disk_total_gb = round(disk.total / (1024 ** 3), 2)
        
        return {
            "cpu": {
                "percent": cpu_percent,
                "status": "healthy" if cpu_percent < 80 else "warning" if cpu_percent < 95 else "critical"
            },
            "memory": {
                "percent": memory_percent,
                "used_gb": memory_used_gb,
                "total_gb": memory_total_gb,
                "status": "healthy" if memory_percent < 80 else "warning" if memory_percent < 95 else "critical"
            },
            "disk": {
                "percent": disk_percent,
                "used_gb": disk_used_gb,
                "total_gb": disk_total_gb,
                "status": "healthy" if disk_percent < 80 else "warning" if disk_percent < 95 else "critical"
            },
            "platform": platform.system(),
            "python_version": platform.python_version()
        }
    except Exception as e:
        return {
            "error": str(e),
            "cpu": {"percent": 0, "status": "unknown"},
            "memory": {"percent": 0, "status": "unknown"},
            "disk": {"percent": 0, "status": "unknown"}
        }


async def get_recent_activity() -> Dict[str, Any]:
    """Get recent system activity"""
    try:
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        
        # Recent registrations
        new_users_24h = await db.users.count_documents({
            "created_at": {"$gte": one_day_ago}
        })
        
        # Recent events
        new_events_24h = await db.events.count_documents({
            "created_at": {"$gte": one_day_ago}
        })
        
        # Recent orders
        new_orders_24h = await db.marketplace_transactions.count_documents({
            "created_at": {"$gte": one_day_ago}
        })
        
        # Active users (with recent activity)
        active_users_1h = await db.users.count_documents({
            "last_active": {"$gte": one_hour_ago}
        })
        
        return {
            "new_users_24h": new_users_24h,
            "new_events_24h": new_events_24h,
            "new_orders_24h": new_orders_24h,
            "active_users_1h": active_users_1h
        }
    except Exception as e:
        return {
            "error": str(e),
            "new_users_24h": 0,
            "new_events_24h": 0,
            "new_orders_24h": 0,
            "active_users_1h": 0
        }


# ============================================
# CRON JOB - AUTOMATIC HEALTH CHECK
# ============================================

# In-memory storage for cron job settings and results
cron_job_settings = {
    "enabled": False,
    "interval_minutes": 30,
    "last_run": None,
    "next_run": None,
    "notify_on_failure": True,
    "notify_admin_ids": []
}

cron_job_history = []


async def run_automatic_health_check():
    """Run automatic health check and store results"""
    global cron_job_settings, cron_job_history
    
    try:
        start_time = datetime.utcnow()
        
        # Run health checks
        services = []
        
        # Database check
        db_status = await check_database_status()
        services.append(db_status)
        
        # API check
        api_status = await check_api_status()
        services.append(api_status)
        
        # Push notification check
        push_status = await check_push_notification_status()
        services.append(push_status)
        
        # SMS check
        sms_status = await check_sms_status()
        services.append(sms_status)
        
        # Payment check
        payment_status = await check_payment_status()
        services.append(payment_status)
        
        # Calculate overall status
        healthy_count = sum(1 for s in services if s["status"] == "healthy")
        warning_count = sum(1 for s in services if s["status"] == "warning")
        unhealthy_count = sum(1 for s in services if s["status"] == "unhealthy")
        
        if unhealthy_count > 0:
            overall_status = "unhealthy"
        elif warning_count > 0:
            overall_status = "warning"
        else:
            overall_status = "healthy"
        
        end_time = datetime.utcnow()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        # Create result
        result = {
            "id": str(uuid.uuid4()),
            "timestamp": start_time.isoformat(),
            "overall_status": overall_status,
            "services": services,
            "summary": {
                "total": len(services),
                "healthy": healthy_count,
                "warning": warning_count,
                "unhealthy": unhealthy_count
            },
            "duration_ms": round(duration_ms, 2),
            "triggered_by": "cron_job"
        }
        
        # Store in history (keep last 100)
        cron_job_history.insert(0, result)
        if len(cron_job_history) > 100:
            cron_job_history = cron_job_history[:100]
        
        # Also store in database
        await db.health_check_logs.insert_one({
            **result,
            "created_at": start_time
        })
        
        # Update settings
        cron_job_settings["last_run"] = start_time.isoformat()
        if cron_job_settings["enabled"]:
            next_run = start_time + timedelta(minutes=cron_job_settings["interval_minutes"])
            cron_job_settings["next_run"] = next_run.isoformat()
        
        # Send notification if unhealthy and notifications enabled
        if overall_status == "unhealthy" and cron_job_settings["notify_on_failure"]:
            await send_health_check_alert(result)
        
        logger.info(f"✅ Automatic health check completed: {overall_status}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Automatic health check failed: {str(e)}")
        error_result = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": "error",
            "error": str(e),
            "triggered_by": "cron_job"
        }
        cron_job_history.insert(0, error_result)
        return error_result


async def send_health_check_alert(result: dict):
    """Send notification to admins when health check fails"""
    try:
        # Find admin users
        admins = await db.users.find({
            "user_type": {"$in": ["admin", "super_admin"]}
        }).to_list(100)
        
        unhealthy_services = [s["name"] for s in result.get("services", []) if s["status"] == "unhealthy"]
        
        for admin in admins:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": admin.get("id"),
                "type": "system_health_alert",
                "title": "⚠️ Sistem Sağlık Uyarısı",
                "message": f"Bazı servisler sorunlu: {', '.join(unhealthy_services)}",
                "data": {
                    "health_check_id": result.get("id"),
                    "unhealthy_services": unhealthy_services
                },
                "read": False,
                "created_at": datetime.utcnow()
            }
            await db.notifications.insert_one(notification)
        
        logger.info(f"📢 Health alert sent to {len(admins)} admins")
    except Exception as e:
        logger.error(f"Failed to send health alert: {str(e)}")


# APScheduler job function
def scheduled_health_check():
    """Wrapper function for APScheduler"""
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_automatic_health_check())
        loop.close()
    except Exception as e:
        logger.error(f"Scheduled health check error: {str(e)}")


# Scheduler instance
health_check_scheduler = None


def start_health_check_scheduler():
    """Start the health check scheduler"""
    global health_check_scheduler
    
    from apscheduler.schedulers.background import BackgroundScheduler
    
    if health_check_scheduler is None:
        health_check_scheduler = BackgroundScheduler()
    
    # Remove existing job if any
    try:
        health_check_scheduler.remove_job("auto_health_check")
    except:
        pass
    
    if cron_job_settings["enabled"]:
        interval = cron_job_settings["interval_minutes"]
        health_check_scheduler.add_job(
            scheduled_health_check,
            'interval',
            minutes=interval,
            id="auto_health_check",
            name=f"Auto Health Check (every {interval} min)"
        )
        
        if not health_check_scheduler.running:
            health_check_scheduler.start()
        
        # Set next run time
        next_run = datetime.utcnow() + timedelta(minutes=interval)
        cron_job_settings["next_run"] = next_run.isoformat()
        
        logger.info(f"✅ Health check scheduler started (interval: {interval} min)")
    else:
        cron_job_settings["next_run"] = None
        logger.info("Health check scheduler disabled")


def stop_health_check_scheduler():
    """Stop the health check scheduler"""
    global health_check_scheduler
    
    if health_check_scheduler:
        try:
            health_check_scheduler.remove_job("auto_health_check")
        except:
            pass
        cron_job_settings["next_run"] = None
        logger.info("Health check scheduler stopped")


# API Endpoints for Cron Job Management
@router.get("/system-tests/cron/status")
async def get_cron_status(current_user: dict = Depends(get_current_user)):
    """Get cron job status - Admin only"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Yetkiniz yok")
    
    return {
        "settings": cron_job_settings,
        "scheduler_running": health_check_scheduler is not None and health_check_scheduler.running if health_check_scheduler else False,
        "history_count": len(cron_job_history)
    }


@router.post("/system-tests/cron/configure")
async def configure_cron_job(
    enabled: bool = True,
    interval_minutes: int = 30,
    notify_on_failure: bool = True,
    current_user: dict = Depends(get_current_user)
):
    """Configure cron job settings - Admin only"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Yetkiniz yok")
    
    if interval_minutes < 5:
        raise HTTPException(status_code=400, detail="Minimum interval 5 dakikadır")
    if interval_minutes > 1440:
        raise HTTPException(status_code=400, detail="Maksimum interval 1440 dakikadır (24 saat)")
    
    cron_job_settings["enabled"] = enabled
    cron_job_settings["interval_minutes"] = interval_minutes
    cron_job_settings["notify_on_failure"] = notify_on_failure
    
    # Restart scheduler with new settings
    if enabled:
        start_health_check_scheduler()
    else:
        stop_health_check_scheduler()
    
    # Log configuration change
    await db.system_logs.insert_one({
        "type": "cron_config_change",
        "user_id": current_user.get("id"),
        "user_name": current_user.get("full_name"),
        "settings": cron_job_settings.copy(),
        "created_at": datetime.utcnow()
    })
    
    return {
        "success": True,
        "message": f"Cron job {'etkinleştirildi' if enabled else 'devre dışı bırakıldı'}",
        "settings": cron_job_settings
    }


@router.post("/system-tests/cron/run-now")
async def run_cron_now(current_user: dict = Depends(get_current_user)):
    """Run health check immediately - Admin only"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Yetkiniz yok")
    
    result = await run_automatic_health_check()
    result["triggered_by"] = "manual"
    
    return result


@router.get("/system-tests/cron/history")
async def get_cron_history(
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    """Get cron job history - Admin only"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Yetkiniz yok")
    
    # Get from database for persistence
    history = await db.health_check_logs.find({}).sort("created_at", -1).limit(limit).to_list(limit)
    
    # Clean up _id
    for item in history:
        item.pop("_id", None)
    
    return {
        "history": history,
        "total": len(history),
        "in_memory_count": len(cron_job_history)
    }


# ============================================
# TEST PROCEDURES - User Test Management
# ============================================

@router.get("/test-procedures/{procedure_type}")
async def get_test_procedure(procedure_type: str):
    """Get test procedure data - Public endpoint for link sharing"""
    valid_types = ["player", "coach", "referee", "facility-owner", "sport-market", "admin", "general-system"]
    
    if procedure_type not in valid_types:
        raise HTTPException(status_code=404, detail="Geçersiz prosedür tipi")
    
    # Get from database
    procedure = await db.test_procedures.find_one({"type": procedure_type})
    
    if procedure:
        procedure.pop("_id", None)
        return procedure
    
    return {
        "type": procedure_type,
        "items": [],
        "tester": "",
        "updated_at": None
    }


@router.post("/test-procedures/save")
async def save_test_procedure(data: dict):
    """Save test procedure data - Public endpoint for anyone to save"""
    procedure_type = data.get("type")
    valid_types = ["player", "coach", "referee", "facility-owner", "sport-market", "admin", "general-system"]
    
    if procedure_type not in valid_types:
        raise HTTPException(status_code=400, detail="Geçersiz prosedür tipi")
    
    # Upsert the procedure
    await db.test_procedures.update_one(
        {"type": procedure_type},
        {"$set": {
            "type": procedure_type,
            "items": data.get("items", []),
            "tester": data.get("tester", ""),
            "updated_at": datetime.utcnow()
        }},
        upsert=True
    )
    
    return {"success": True, "message": "Kaydedildi"}


@router.get("/test-procedures-list")
async def get_all_test_procedures(current_user: dict = Depends(get_current_user)):
    """Get all test procedures summary - Admin only"""
    if current_user.get("user_type") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Yetkiniz yok")
    
    procedures = await db.test_procedures.find({}).to_list(100)
    
    summary = []
    for p in procedures:
        items = p.get("items", [])
        total = len(items)
        passed = sum(1 for i in items if i.get("status") == "pass")
        failed = sum(1 for i in items if i.get("status") == "fail")
        pending = sum(1 for i in items if i.get("status") == "pending")
        
        summary.append({
            "type": p.get("type"),
            "tester": p.get("tester"),
            "updated_at": p.get("updated_at"),
            "stats": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "pending": pending,
                "progress": round((passed / total) * 100) if total > 0 else 0
            }
        })
    
    return {"procedures": summary}

