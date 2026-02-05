"""
Background Scheduler for Event Reminders
Checks every minute for matches that need reminders
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from typing import Dict, List
import logging
import asyncio
import os
import uuid
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class EventReminderScheduler:
    def __init__(self, db, push_service):
        self.db = db
        self.push_service = push_service
        self.scheduler = BackgroundScheduler()
        self._mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        self._db_name = os.environ.get('DB_NAME', 'match_alert')
        
    def _get_fresh_db_connection(self):
        """Create a fresh MongoDB connection for background tasks"""
        client = AsyncIOMotorClient(self._mongo_url)
        return client[self._db_name]
    
    def _run_async_task(self, coro_func):
        """Run async function with fresh event loop and db connection"""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Create fresh db connection
            fresh_db = self._get_fresh_db_connection()
            
            try:
                # Run the coroutine
                loop.run_until_complete(coro_func(fresh_db))
            finally:
                # Close the loop
                loop.close()
        except Exception as e:
            logger.error(f"Error in async task: {str(e)}")
        
    def start(self):
        """Start the background scheduler"""
        # Run every hour for event reminders
        self.scheduler.add_job(
            func=self._check_event_reminders_sync,
            trigger=IntervalTrigger(hours=1),
            id='event_reminder_job',
            name='Check event reminders every hour',
            replace_existing=True
        )
        
        # Run every minute for match reminders (30 min and 5 min before)
        self.scheduler.add_job(
            func=self._check_match_reminders_sync,
            trigger=IntervalTrigger(minutes=1),
            id='match_reminder_job',
            name='Check match reminders every minute',
            replace_existing=True
        )
        
        # Run every 5 minutes for completed reservations/events review reminders
        self.scheduler.add_job(
            func=self._check_review_reminders_sync,
            trigger=IntervalTrigger(minutes=5),
            id='review_reminder_job',
            name='Check for completed reservations/events to send review reminders',
            replace_existing=True
        )
        
        # Run every 10 minutes for marketplace auto-approval
        self.scheduler.add_job(
            func=self._check_marketplace_auto_approval_sync,
            trigger=IntervalTrigger(minutes=10),
            id='marketplace_auto_approval_job',
            name='Auto-approve delivered orders after 1 day',
            replace_existing=True
        )
        
        # Run every 6 hours for cargo tracking
        self.scheduler.add_job(
            func=self._check_cargo_tracking_sync,
            trigger=IntervalTrigger(hours=6),
            id='cargo_tracking_job',
            name='Track cargo shipments every 6 hours',
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("Event and match reminder scheduler started")
        logger.info("📦 Cargo tracking job scheduled to run every 6 hours")
    
    def stop(self):
        """Stop the background scheduler"""
        self.scheduler.shutdown()
        logger.info("Event reminder scheduler stopped")
    
    # Sync wrappers for scheduler - use fresh db connection
    def _check_event_reminders_sync(self):
        """Sync wrapper for check_event_reminders"""
        self._run_async_task(self._check_event_reminders_with_db)
    
    def _check_match_reminders_sync(self):
        """Sync wrapper for check_match_reminders"""
        self._run_async_task(self._check_match_reminders_with_db)
    
    def _check_review_reminders_sync(self):
        """Sync wrapper for check_review_reminders"""
        self._run_async_task(self._check_review_reminders_with_db)
    
    def _check_marketplace_auto_approval_sync(self):
        """Sync wrapper for marketplace auto-approval"""
        self._run_async_task(self._check_marketplace_auto_approval_with_db)
    
    def _check_cargo_tracking_sync(self):
        """Sync wrapper for cargo tracking"""
        self._run_async_task(self._check_cargo_tracking_with_db)
    
    async def _check_event_reminders_with_db(self, fresh_db):
        """Check event reminders with fresh db connection"""
        try:
            logger.info("Checking for event and reservation reminders...")
            now = datetime.utcnow()
            
            # Check for events 24 hours away
            await self._check_24hour_reminders(fresh_db, now)
            
            # Check for events 1 hour away
            await self._check_1hour_reminders(fresh_db, now)
            
            logger.info("Event and reservation reminder check completed")
        except Exception as e:
            logger.error(f"Error in check_event_reminders: {str(e)}")
    
    async def _check_match_reminders_with_db(self, fresh_db):
        """Check match reminders with fresh db connection"""
        try:
            logger.info("🏟️ Checking for match reminders...")
            now = datetime.utcnow()
            
            # Check for 30-minute reminders (players only)
            await self._check_30min_match_reminders(fresh_db, now)
            
            # Check for 5-minute reminders (players and referees)
            await self._check_5min_match_reminders(fresh_db, now)
            
            logger.info("🏟️ Match reminder check completed")
        except Exception as e:
            logger.error(f"Error in check_match_reminders: {str(e)}")
    
    async def _check_review_reminders_with_db(self, fresh_db):
        """Check review reminders with fresh db connection"""
        try:
            logger.info("📝 Checking for review reminders...")
            now = datetime.utcnow()
            
            # Check for completed reservations that need review reminders
            await self._check_reservation_review_reminders(fresh_db, now)
            
            # Check for completed events that need review reminders
            await self._check_event_review_reminders(fresh_db, now)
            
            logger.info("📝 Review reminder check completed")
        except Exception as e:
            logger.error(f"Error in check_review_reminders: {str(e)}")
    
    async def _check_24hour_reminders(self, db, now):
        """Check for events 24 hours away"""
        try:
            start_time = now + timedelta(hours=23, minutes=55)
            end_time = now + timedelta(hours=24, minutes=5)
            
            events = await db.events.find({
                "status": "active",
                "start_date": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            }).to_list(length=100)
            
            for event in events:
                # Check if reminder already sent
                existing = await db.notifications.find_one({
                    "related_id": event.get("id"),
                    "type": "event_reminder_24h"
                })
                
                if not existing:
                    # Get participants
                    participants = event.get("participants", [])
                    for user_id in participants:
                        notification = {
                            "id": str(__import__('uuid').uuid4()),
                            "user_id": user_id,
                            "type": "event_reminder_24h",
                            "title": "📅 Etkinlik Hatırlatması",
                            "message": f"'{event.get('title', 'Etkinlik')}' yarın başlıyor!",
                            "related_id": event.get("id"),
                            "read": False,
                            "created_at": now
                        }
                        await db.notifications.insert_one(notification)
                    
                    logger.info(f"24h reminder sent for event: {event.get('title')}")
        except Exception as e:
            logger.error(f"Error in _check_24hour_reminders: {str(e)}")
    
    async def _check_1hour_reminders(self, db, now):
        """Check for events 1 hour away"""
        try:
            start_time = now + timedelta(minutes=55)
            end_time = now + timedelta(hours=1, minutes=5)
            
            events = await db.events.find({
                "status": "active",
                "start_date": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            }).to_list(length=100)
            
            for event in events:
                existing = await db.notifications.find_one({
                    "related_id": event.get("id"),
                    "type": "event_reminder_1h"
                })
                
                if not existing:
                    participants = event.get("participants", [])
                    for user_id in participants:
                        notification = {
                            "id": str(__import__('uuid').uuid4()),
                            "user_id": user_id,
                            "type": "event_reminder_1h",
                            "title": "⏰ Etkinlik 1 Saat Sonra",
                            "message": f"'{event.get('title', 'Etkinlik')}' 1 saat sonra başlıyor!",
                            "related_id": event.get("id"),
                            "read": False,
                            "created_at": now
                        }
                        await db.notifications.insert_one(notification)
                    
                    logger.info(f"1h reminder sent for event: {event.get('title')}")
        except Exception as e:
            logger.error(f"Error in _check_1hour_reminders: {str(e)}")
    
    async def _check_30min_match_reminders(self, db, now):
        """Send reminders to players 30 minutes before match"""
        try:
            start_time = now + timedelta(minutes=28)
            end_time = now + timedelta(minutes=32)
            
            matches = await db.event_matches.find({
                "status": {"$in": ["scheduled", "in_progress"]},
                "scheduled_time": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            }).to_list(length=500)
            
            for match in matches:
                existing = await db.notifications.find_one({
                    "related_id": match.get("id"),
                    "type": "match_reminder_30min"
                })
                
                if not existing:
                    # Send to participants
                    for participant_key in ["participant1_id", "participant2_id"]:
                        user_id = match.get(participant_key)
                        if user_id:
                            notification = {
                                "id": str(__import__('uuid').uuid4()),
                                "user_id": user_id,
                                "type": "match_reminder_30min",
                                "title": "🏟️ Maç 30 Dakika Sonra",
                                "message": "Maçınız 30 dakika sonra başlıyor!",
                                "related_id": match.get("id"),
                                "read": False,
                                "created_at": now
                            }
                            await db.notifications.insert_one(notification)
                    
                    logger.info(f"30min reminder sent for match: {match.get('id')}")
        except Exception as e:
            logger.error(f"Error in _check_30min_match_reminders: {str(e)}")
    
    async def _check_5min_match_reminders(self, db, now):
        """Send reminders to players and referees 5 minutes before match"""
        try:
            start_time = now + timedelta(minutes=4)
            end_time = now + timedelta(minutes=6)
            
            matches = await db.event_matches.find({
                "status": {"$in": ["scheduled", "in_progress"]},
                "scheduled_time": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            }).to_list(length=500)
            
            for match in matches:
                existing = await db.notifications.find_one({
                    "related_id": match.get("id"),
                    "type": "match_reminder_5min"
                })
                
                if not existing:
                    # Send to participants
                    for participant_key in ["participant1_id", "participant2_id"]:
                        user_id = match.get(participant_key)
                        if user_id:
                            notification = {
                                "id": str(__import__('uuid').uuid4()),
                                "user_id": user_id,
                                "type": "match_reminder_5min",
                                "title": "🏟️ Maç 5 Dakika Sonra",
                                "message": "Maçınız 5 dakika sonra başlıyor!",
                                "related_id": match.get("id"),
                                "read": False,
                                "created_at": now
                            }
                            await db.notifications.insert_one(notification)
                    
                    # Send to referee if assigned
                    referee_id = match.get("referee_id")
                    if referee_id:
                        notification = {
                            "id": str(__import__('uuid').uuid4()),
                            "user_id": referee_id,
                            "type": "match_reminder_5min_referee",
                            "title": "🏟️ Hakemlik Göreviniz 5 Dakika Sonra",
                            "message": "Hakemlik yapacağınız maç 5 dakika sonra başlıyor!",
                            "related_id": match.get("id"),
                            "read": False,
                            "created_at": now
                        }
                        await db.notifications.insert_one(notification)
                    
                    logger.info(f"5min reminder sent for match: {match.get('id')}")
        except Exception as e:
            logger.error(f"Error in _check_5min_match_reminders: {str(e)}")
    
    async def _check_reservation_review_reminders(self, db, now):
        """Check for completed reservations that need review reminders"""
        try:
            # Find reservations completed in the last 24 hours
            one_day_ago = now - timedelta(hours=24)
            
            reservations = await db.reservations.find({
                "status": "completed",
                "end_time": {
                    "$gte": one_day_ago,
                    "$lte": now
                }
            }).to_list(length=100)
            
            for reservation in reservations:
                existing = await db.notifications.find_one({
                    "related_id": reservation.get("id"),
                    "type": "review_reminder"
                })
                
                if not existing:
                    user_id = reservation.get("user_id")
                    if user_id:
                        notification = {
                            "id": str(__import__('uuid').uuid4()),
                            "user_id": user_id,
                            "type": "review_reminder",
                            "title": "⭐ Değerlendirme Hatırlatması",
                            "message": "Son rezervasyonunuz nasıldı? Değerlendirmenizi bekliyoruz!",
                            "related_id": reservation.get("id"),
                            "read": False,
                            "created_at": now
                        }
                        await db.notifications.insert_one(notification)
                    
                    logger.info(f"Review reminder sent for reservation: {reservation.get('id')}")
        except Exception as e:
            logger.error(f"Error in _check_reservation_review_reminders: {str(e)}")
    
    async def _check_event_review_reminders(self, db, now):
        """Check for completed events that need review reminders"""
        try:
            # Find events that ended in the last 2 hours (just after event ends)
            two_hours_ago = now - timedelta(hours=2)
            
            # Check both completed status and end_date passed
            events = await db.events.find({
                "$or": [
                    # Events with completed status
                    {
                        "status": "completed",
                        "end_date": {
                            "$gte": two_hours_ago,
                            "$lte": now
                        }
                    },
                    # Events with end_date passed but status still active
                    {
                        "status": "active",
                        "end_date": {
                            "$lte": now,
                            "$gte": two_hours_ago
                        }
                    }
                ]
            }).to_list(length=100)
            
            for event in events:
                event_id = event.get("id")
                
                # Check if reminder already sent for this event
                existing = await db.notifications.find_one({
                    "related_id": event_id,
                    "type": "event_review_reminder"
                })
                
                if not existing:
                    participants = event.get("participants", [])
                    event_title = event.get('title', 'Etkinlik')
                    
                    # Extract participant IDs
                    participant_ids = []
                    for p in participants:
                        if isinstance(p, str):
                            participant_ids.append(p)
                        elif isinstance(p, dict):
                            pid = p.get("id") or p.get("user_id")
                            if pid:
                                participant_ids.append(pid)
                    
                    # Only send if there are at least 2 participants
                    if len(participant_ids) >= 2:
                        # Collect push tokens for push notifications
                        push_tokens = []
                        
                        for user_id in participant_ids:
                            notification = {
                                "id": str(__import__('uuid').uuid4()),
                                "user_id": user_id,
                                "type": "event_review_reminder",
                                "title": "⭐ Katılımcıları Değerlendirin",
                                "message": f"'{event_title}' etkinliği sona erdi! Diğer katılımcıları değerlendirmek ister misiniz?",
                                "related_id": event_id,
                                "related_type": "event",
                                "action_url": f"/event/rate-participants?eventId={event_id}",
                                "read": False,
                                "created_at": now
                            }
                            await db.notifications.insert_one(notification)
                            
                            # Get user push token
                            user = await db.users.find_one({"id": user_id})
                            if user and user.get("push_token"):
                                push_tokens.append(user.get("push_token"))
                        
                        # Send push notifications
                        if push_tokens and self.push_service:
                            try:
                                await self.push_service.send_push_notification(
                                    push_tokens=push_tokens,
                                    title="⭐ Katılımcıları Değerlendirin",
                                    body=f"'{event_title}' etkinliği sona erdi! Değerlendirme yapın.",
                                    data={
                                        "type": "event_review_reminder",
                                        "event_id": event_id,
                                        "action_url": f"/event/rate-participants?eventId={event_id}"
                                    }
                                )
                                logger.info(f"📱 Push notification sent to {len(push_tokens)} users for event review")
                            except Exception as push_err:
                                logger.error(f"Push notification error: {str(push_err)}")
                        
                        logger.info(f"📝 Review reminder sent for event: {event_title} to {len(participant_ids)} participants")
                    
                    # Update event status to completed if it was active
                    if event.get("status") == "active":
                        await db.events.update_one(
                            {"id": event_id},
                            {"$set": {"status": "completed"}}
                        )
                        logger.info(f"📝 Event status updated to completed: {event_title}")
                        
        except Exception as e:
            logger.error(f"Error in _check_event_review_reminders: {str(e)}")
    
    async def _check_reservation_review_reminders_v2(self, db, now):
        """Check for completed reservations that need review reminders - Enhanced version"""
        try:
            # Find reservations that ended in the last 2 hours
            two_hours_ago = now - timedelta(hours=2)
            
            reservations = await db.reservations.find({
                "$or": [
                    {"status": "completed", "end_time": {"$gte": two_hours_ago, "$lte": now}},
                    {"status": "confirmed", "end_time": {"$lte": now, "$gte": two_hours_ago}}
                ]
            }).to_list(length=100)
            
            for reservation in reservations:
                reservation_id = reservation.get("id")
                
                existing = await db.notifications.find_one({
                    "related_id": reservation_id,
                    "type": "reservation_review_reminder"
                })
                
                if not existing:
                    user_id = reservation.get("user_id")
                    facility_id = reservation.get("facility_id")
                    
                    # Get facility info
                    facility = await db.facilities.find_one({"id": facility_id})
                    facility_name = facility.get("name", "Tesis") if facility else "Tesis"
                    facility_owner_id = facility.get("owner_id") if facility else None
                    
                    if user_id:
                        notification = {
                            "id": str(__import__('uuid').uuid4()),
                            "user_id": user_id,
                            "type": "reservation_review_reminder",
                            "title": "⭐ Rezervasyon Değerlendirmesi",
                            "message": f"'{facility_name}' tesisindeki rezervasyonunuz nasıldı? Değerlendirmenizi bekliyoruz!",
                            "related_id": reservation_id,
                            "related_type": "reservation",
                            "action_url": f"/profile/user-reviews?userId={facility_owner_id}" if facility_owner_id else None,
                            "read": False,
                            "created_at": now
                        }
                        await db.notifications.insert_one(notification)
                        
                        # Send push notification
                        user = await db.users.find_one({"id": user_id})
                        if user and user.get("push_token") and self.push_service:
                            try:
                                await self.push_service.send_push_notification(
                                    push_tokens=[user.get("push_token")],
                                    title="⭐ Rezervasyon Değerlendirmesi",
                                    body=f"'{facility_name}' tesisindeki rezervasyonunuz nasıldı?",
                                    data={
                                        "type": "reservation_review_reminder",
                                        "reservation_id": reservation_id,
                                        "facility_owner_id": facility_owner_id
                                    }
                                )
                                logger.info(f"📱 Push notification sent for reservation review: {reservation_id}")
                            except Exception as push_err:
                                logger.error(f"Push notification error: {str(push_err)}")
                        
                        logger.info(f"📝 Reservation review reminder sent for: {reservation_id}")
                    
                    # Update reservation status to completed if it was confirmed
                    if reservation.get("status") == "confirmed":
                        await db.reservations.update_one(
                            {"id": reservation_id},
                            {"$set": {"status": "completed"}}
                        )
                        
        except Exception as e:
            logger.error(f"Error in _check_reservation_review_reminders_v2: {str(e)}") 
    
    # Keep old methods for backwards compatibility (they won't be used by scheduler anymore)
    async def check_event_reminders(self):
        """
        Check for events and reservations that need reminders and create notifications
        """
        try:
            logger.info("Checking for event and reservation reminders...")
            now = datetime.utcnow()
            
            # Check for events 24 hours away
            await self.check_24hour_reminders(now)
            
            # Check for events 1 hour away
            await self.check_1hour_reminders(now)
            
            # Check for reservations 24 hours away
            await self.check_24hour_reservation_reminders(now)
            
            # Check for reservations 1 hour away
            await self.check_1hour_reservation_reminders(now)
            
            # Check for overdue payment requests
            await self.check_overdue_payments(now)
            
            # Check for expiring marketplace offers (1 hour before expiry)
            await self.check_expiring_offers(now)
            
            logger.info("Event and reservation reminder check completed")
        except Exception as e:
            logger.error(f"Error in check_event_reminders: {str(e)}")
    
    async def check_24hour_reminders(self, now: datetime):
        """Send reminders for events starting in 24 hours"""
        try:
            # Find events starting between 23-25 hours from now
            start_time = now + timedelta(hours=23)
            end_time = now + timedelta(hours=25)
            
            events = await self.db.events.find({
                "start_date": {
                    "$gte": start_time.isoformat(),
                    "$lte": end_time.isoformat()
                }
            }).to_list(length=100)
            
            for event in events:
                # Check if reminder already sent
                reminder_check = await self.db.notifications.find_one({
                    "related_id": event["_id"],
                    "type": "event_reminder_1day"
                })
                
                if reminder_check:
                    continue  # Already sent
                
                # Get all participants
                participations = await self.db.participations.find({
                    "event_id": str(event["_id"])
                }).to_list(length=1000)
                
                for participation in participations:
                    await self.create_reminder_notification(
                        user_id=participation["user_id"],
                        event=event,
                        reminder_type="event_reminder_1day",
                        message=f"{event['title']} yarın başlıyor!"
                    )
            
            logger.info(f"Processed {len(events)} events for 24-hour reminders")
        except Exception as e:
            logger.error(f"Error in check_24hour_reminders: {str(e)}")
    
    async def check_1hour_reminders(self, now: datetime):
        """Send reminders for events starting in 1 hour"""
        try:
            # Find events starting between 0.5-1.5 hours from now
            start_time = now + timedelta(minutes=30)
            end_time = now + timedelta(minutes=90)
            
            events = await self.db.events.find({
                "start_date": {
                    "$gte": start_time.isoformat(),
                    "$lte": end_time.isoformat()
                }
            }).to_list(length=100)
            
            for event in events:
                # Check if reminder already sent
                reminder_check = await self.db.notifications.find_one({
                    "related_id": event["_id"],
                    "type": "event_reminder_1hour"
                })
                
                if reminder_check:
                    continue  # Already sent
                
                # Get all participants
                participations = await self.db.participations.find({
                    "event_id": str(event["_id"])
                }).to_list(length=1000)
                
                for participation in participations:
                    await self.create_reminder_notification(
                        user_id=participation["user_id"],
                        event=event,
                        reminder_type="event_reminder_1hour",
                        message=f"{event['title']} 1 saat içinde başlıyor!"
                    )
            
            logger.info(f"Processed {len(events)} events for 1-hour reminders")
        except Exception as e:
            logger.error(f"Error in check_1hour_reminders: {str(e)}")
    
    async def check_24hour_reservation_reminders(self, now: datetime):
        """Send reminders for reservations starting in 24 hours"""
        try:
            # Find confirmed reservations starting between 23-25 hours from now
            start_time = now + timedelta(hours=23)
            end_time = now + timedelta(hours=25)
            
            reservations = await self.db.reservations.find({
                "status": "confirmed",
                "date": {
                    "$gte": start_time.isoformat(),
                    "$lte": end_time.isoformat()
                }
            }).to_list(length=100)
            
            for reservation in reservations:
                # Check if reminder already sent
                reminder_check = await self.db.notifications.find_one({
                    "related_id": str(reservation.get("id", reservation.get("_id"))),
                    "type": "reservation_reminder_1day"
                })
                
                if reminder_check:
                    continue  # Already sent
                
                # Get venue name
                venue_name = "Rezervasyon"
                if reservation.get("venue_id"):
                    venue = await self.db.venues.find_one({"id": reservation["venue_id"]})
                    if venue:
                        venue_name = venue.get("name", "Rezervasyon")
                
                # Send to requester (user who made the reservation)
                await self.create_reservation_reminder_notification(
                    user_id=reservation["user_id"],
                    reservation=reservation,
                    reminder_type="reservation_reminder_1day",
                    message=f"{venue_name} rezervasyonunuz yarın başlıyor!",
                    title="Rezervasyon Hatırlatma"
                )
                
                # Send to provider (venue owner, coach, etc.)
                provider_id = None
                if reservation.get("venue_id"):
                    # Get venue owner
                    venue = await self.db.venues.find_one({"id": reservation["venue_id"]})
                    if venue:
                        provider_id = venue.get("owner_id")
                elif reservation.get("coach_id"):
                    provider_id = reservation["coach_id"]
                elif reservation.get("referee_id"):
                    provider_id = reservation["referee_id"]
                elif reservation.get("player_id"):
                    provider_id = reservation["player_id"]
                
                if provider_id and provider_id != reservation["user_id"]:
                    await self.create_reservation_reminder_notification(
                        user_id=provider_id,
                        reservation=reservation,
                        reminder_type="reservation_reminder_1day",
                        message=f"{venue_name} rezervasyonunuz yarın başlıyor!",
                        title="Rezervasyon Hatırlatma"
                    )
            
            logger.info(f"Processed {len(reservations)} reservations for 24-hour reminders")
        except Exception as e:
            logger.error(f"Error in check_24hour_reservation_reminders: {str(e)}")
    
    async def check_1hour_reservation_reminders(self, now: datetime):
        """Send reminders for reservations starting in 1 hour"""
        try:
            # Find confirmed reservations starting between 0.5-1.5 hours from now
            start_time = now + timedelta(minutes=30)
            end_time = now + timedelta(minutes=90)
            
            reservations = await self.db.reservations.find({
                "status": "confirmed",
                "date": {
                    "$gte": start_time.isoformat(),
                    "$lte": end_time.isoformat()
                }
            }).to_list(length=100)
            
            for reservation in reservations:
                # Check if reminder already sent
                reminder_check = await self.db.notifications.find_one({
                    "related_id": str(reservation.get("id", reservation.get("_id"))),
                    "type": "reservation_reminder_1hour"
                })
                
                if reminder_check:
                    continue  # Already sent
                
                # Get venue name
                venue_name = "Rezervasyon"
                if reservation.get("venue_id"):
                    venue = await self.db.venues.find_one({"id": reservation["venue_id"]})
                    if venue:
                        venue_name = venue.get("name", "Rezervasyon")
                
                # Send to requester
                await self.create_reservation_reminder_notification(
                    user_id=reservation["user_id"],
                    reservation=reservation,
                    reminder_type="reservation_reminder_1hour",
                    message=f"{venue_name} rezervasyonunuz 1 saat içinde başlıyor!",
                    title="Rezervasyon Hatırlatma"
                )
                
                # Send to provider
                provider_id = None
                if reservation.get("venue_id"):
                    venue = await self.db.venues.find_one({"id": reservation["venue_id"]})
                    if venue:
                        provider_id = venue.get("owner_id")
                elif reservation.get("coach_id"):
                    provider_id = reservation["coach_id"]
                elif reservation.get("referee_id"):
                    provider_id = reservation["referee_id"]
                elif reservation.get("player_id"):
                    provider_id = reservation["player_id"]
                
                if provider_id and provider_id != reservation["user_id"]:
                    await self.create_reservation_reminder_notification(
                        user_id=provider_id,
                        reservation=reservation,
                        reminder_type="reservation_reminder_1hour",
                        message=f"{venue_name} rezervasyonunuz 1 saat içinde başlıyor!",
                        title="Rezervasyon Hatırlatma"
                    )
            
            logger.info(f"Processed {len(reservations)} reservations for 1-hour reminders")
        except Exception as e:
            logger.error(f"Error in check_1hour_reservation_reminders: {str(e)}")
    
    async def create_reminder_notification(
        self, 
        user_id: str, 
        event: Dict, 
        reminder_type: str,
        message: str
    ):
        """Create a reminder notification and send push notification"""
        try:
            from bson import ObjectId
            
            # Create notification in database
            notification = {
                "user_id": user_id,
                "type": reminder_type,
                "title": "Etkinlik Hatırlatma",
                "message": message,
                "related_id": str(event["_id"]),
                "related_type": "event",
                "read": False,
                "created_at": datetime.utcnow()
            }
            
            result = await self.db.notifications.insert_one(notification)
            logger.info(f"Created notification {result.inserted_id} for user {user_id}")
            
            # Get user's push token
            push_token_doc = await self.db.push_tokens.find_one({"user_id": user_id})
            
            if push_token_doc and push_token_doc.get("expo_push_token"):
                # Send push notification
                await self.push_service.send_push_notification(
                    push_tokens=[push_token_doc["expo_push_token"]],
                    title="Etkinlik Hatırlatma",
                    body=message,
                    data={
                        "type": "event",
                        "event_id": str(event["_id"]),
                        "notification_id": str(result.inserted_id)
                    }
                )
                logger.info(f"Sent push notification to user {user_id}")
        except Exception as e:
            logger.error(f"Error creating reminder notification: {str(e)}")
    
    async def create_reservation_reminder_notification(
        self, 
        user_id: str, 
        reservation: Dict, 
        reminder_type: str,
        message: str,
        title: str
    ):
        """Create a reservation reminder notification and send push notification"""
        try:
            from bson import ObjectId
            
            reservation_id = str(reservation.get("id", reservation.get("_id")))
            
            # Create notification in database
            notification = {
                "user_id": user_id,
                "type": reminder_type,
                "title": title,
                "message": message,
                "related_id": reservation_id,
                "related_type": "reservation",
                "read": False,
                "created_at": datetime.utcnow()
            }
            
            result = await self.db.notifications.insert_one(notification)
            logger.info(f"Created reservation notification {result.inserted_id} for user {user_id}")
            
            # Get user's push token
            push_token_doc = await self.db.push_tokens.find_one({"user_id": user_id})
            
            if push_token_doc and push_token_doc.get("expo_push_token"):
                # Send push notification
                await self.push_service.send_push_notification(
                    push_tokens=[push_token_doc["expo_push_token"]],
                    title=title,
                    body=message,
                    data={
                        "type": "reservation",
                        "reservation_id": reservation_id,
                        "notification_id": str(result.inserted_id)
                    }
                )
                logger.info(f"Sent reservation push notification to user {user_id}")
        except Exception as e:
            logger.error(f"Error creating reservation reminder notification: {str(e)}")
    
    async def check_overdue_payments(self, now: datetime):
        """Check for overdue payment requests (3 days past due date)"""
        try:
            # Find payment requests that are overdue (3+ days past due date)
            payment_requests = await self.db.payment_requests.find({
                "status": "pending",
                "due_date": {"$lte": now}
            }).to_list(1000)
            
            for payment_request in payment_requests:
                # Check if already notified about overdue
                overdue_notification = await self.db.notifications.find_one({
                    "related_id": payment_request["id"],
                    "type": "payment_overdue"
                })
                
                if overdue_notification:
                    continue  # Already notified
                
                # Update status to overdue
                await self.db.payment_requests.update_one(
                    {"id": payment_request["id"]},
                    {"$set": {"status": "overdue"}}
                )
                
                # Notify organization (payment requester)
                notification = {
                    "user_id": payment_request["organization_id"],
                    "type": "payment_overdue",
                    "title": "Ödeme Gecikti",
                    "message": f"{payment_request['member_name']} için {payment_request['amount']}₺ ödeme 3 gündür bekleniyor.",
                    "related_id": payment_request["id"],
                    "related_type": "payment_request",
                    "is_read": False,
                    "created_at": datetime.utcnow()
                }
                await self.db.notifications.insert_one(notification)
                logger.info(f"Overdue payment notification sent for request {payment_request['id']}")
            
            logger.info(f"Checked {len(payment_requests)} overdue payment requests")
        except Exception as e:
            logger.error(f"Error checking overdue payments: {str(e)}")

    async def check_expiring_offers(self, now: datetime):
        """
        Check for marketplace offers with price locks expiring in 1 hour
        Send reminder notifications to buyers
        """
        try:
            # Find accepted offers with price locked until 1-2 hours from now
            # that haven't had reminders sent yet
            start_time = now + timedelta(minutes=30)
            end_time = now + timedelta(minutes=90)
            
            offers = await self.db.marketplace_offers.find({
                "status": "accepted",
                "reminder_sent": False,
                "price_locked_until": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            }).to_list(length=100)
            
            for offer in offers:
                # Get listing details
                listing = await self.db.marketplace_listings.find_one({
                    "id": offer["listing_id"]
                })
                
                if not listing:
                    continue
                
                # Send reminder notification to buyer
                notification = {
                    "id": str(__import__('uuid').uuid4()),
                    "user_id": offer["buyer_id"],
                    "type": "offer_expiring_soon",
                    "title": "Teklif Süresi Dolmak Üzere! ⏰",
                    "message": f"'{listing['title']}' ilanı için kabul edilen teklifinizin fiyat kilidi 1 saat içinde dolacak. Ödeme yapmayı unutmayın!",
                    "related_id": offer["id"],
                    "related_type": "marketplace_offer",
                    "is_read": False,
                    "created_at": datetime.utcnow()
                }
                await self.db.notifications.insert_one(notification)
                
                # Mark reminder as sent
                await self.db.marketplace_offers.update_one(
                    {"id": offer["id"]},
                    {"$set": {"reminder_sent": True}}
                )
                
                logger.info(f"✅ Sent expiring offer reminder for offer {offer['id']}")
            
            logger.info(f"Processed {len(offers)} expiring marketplace offers")
        except Exception as e:
            logger.error(f"Error in check_expiring_offers: {str(e)}")

    # ═══════════════════════════════════════════════════════════════
    # MAÇ HATIRLATMA SİSTEMİ
    # ═══════════════════════════════════════════════════════════════
    
    async def check_match_reminders(self):
        """
        Check for upcoming matches and send reminders:
        - 30 minutes before: Players
        - 5 minutes before: Players and Referees
        """
        try:
            logger.info("🏟️ Checking for match reminders...")
            now = datetime.utcnow()
            
            # Check for 30-minute reminders (players only)
            await self.check_30min_match_reminders(now)
            
            # Check for 5-minute reminders (players and referees)
            await self.check_5min_match_reminders(now)
            
            logger.info("🏟️ Match reminder check completed")
        except Exception as e:
            logger.error(f"Error in check_match_reminders: {str(e)}")
    
    async def check_30min_match_reminders(self, now: datetime):
        """Send reminders to players 30 minutes before match"""
        try:
            # Find matches starting between 28-32 minutes from now
            start_time = now + timedelta(minutes=28)
            end_time = now + timedelta(minutes=32)
            
            matches = await self.db.event_matches.find({
                "status": {"$in": ["scheduled", "in_progress"]},
                "scheduled_time": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            }).to_list(length=500)
            
            for match in matches:
                # Check if 30-min reminder already sent
                reminder_check = await self.db.notifications.find_one({
                    "related_id": match["id"],
                    "type": "match_reminder_30min"
                })
                
                if reminder_check:
                    continue  # Already sent
                
                # Get match details
                match_info = await self.get_match_info(match)
                
                # Send to participant 1
                if match.get("participant1_id"):
                    await self.send_match_reminder_to_player(
                        user_id=match["participant1_id"],
                        match=match,
                        match_info=match_info,
                        reminder_type="match_reminder_30min",
                        time_text="30 dakika"
                    )
                
                # Send to participant 2
                if match.get("participant2_id"):
                    await self.send_match_reminder_to_player(
                        user_id=match["participant2_id"],
                        match=match,
                        match_info=match_info,
                        reminder_type="match_reminder_30min",
                        time_text="30 dakika"
                    )
            
            logger.info(f"🏟️ Processed {len(matches)} matches for 30-minute reminders")
        except Exception as e:
            logger.error(f"Error in check_30min_match_reminders: {str(e)}")
    
    async def check_5min_match_reminders(self, now: datetime):
        """Send reminders to players and referees 5 minutes before match"""
        try:
            # Find matches starting between 4-6 minutes from now
            start_time = now + timedelta(minutes=4)
            end_time = now + timedelta(minutes=6)
            
            matches = await self.db.event_matches.find({
                "status": {"$in": ["scheduled", "in_progress"]},
                "scheduled_time": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            }).to_list(length=500)
            
            for match in matches:
                # Check if 5-min reminder already sent
                reminder_check = await self.db.notifications.find_one({
                    "related_id": match["id"],
                    "type": "match_reminder_5min"
                })
                
                if reminder_check:
                    continue  # Already sent
                
                # Get match details
                match_info = await self.get_match_info(match)
                
                # Send to participant 1
                if match.get("participant1_id"):
                    await self.send_match_reminder_to_player(
                        user_id=match["participant1_id"],
                        match=match,
                        match_info=match_info,
                        reminder_type="match_reminder_5min",
                        time_text="5 dakika"
                    )
                
                # Send to participant 2
                if match.get("participant2_id"):
                    await self.send_match_reminder_to_player(
                        user_id=match["participant2_id"],
                        match=match,
                        match_info=match_info,
                        reminder_type="match_reminder_5min",
                        time_text="5 dakika"
                    )
                
                # Send to referee (if assigned)
                if match.get("referee_id"):
                    await self.send_match_reminder_to_referee(
                        user_id=match["referee_id"],
                        match=match,
                        match_info=match_info
                    )
            
            logger.info(f"🏟️ Processed {len(matches)} matches for 5-minute reminders")
        except Exception as e:
            logger.error(f"Error in check_5min_match_reminders: {str(e)}")
    
    async def get_match_info(self, match: Dict) -> Dict:
        """Get detailed match information including participant names and referee"""
        info = {
            "participant1_name": "Oyuncu 1",
            "participant2_name": "Oyuncu 2",
            "referee_name": None,
            "event_title": None,
            "court_number": match.get("court_number"),
            "scheduled_time": match.get("scheduled_time"),
            "group_name": match.get("group_name")
        }
        
        try:
            # Get participant 1 name
            if match.get("participant1_id"):
                participant1 = await self.db.event_participants.find_one({"id": match["participant1_id"]})
                if participant1:
                    info["participant1_name"] = participant1.get("name", "Oyuncu 1")
                else:
                    # Try users collection
                    user1 = await self.db.users.find_one({"id": match["participant1_id"]})
                    if user1:
                        info["participant1_name"] = user1.get("name", "Oyuncu 1")
            
            # Get participant 2 name
            if match.get("participant2_id"):
                participant2 = await self.db.event_participants.find_one({"id": match["participant2_id"]})
                if participant2:
                    info["participant2_name"] = participant2.get("name", "Oyuncu 2")
                else:
                    # Try users collection
                    user2 = await self.db.users.find_one({"id": match["participant2_id"]})
                    if user2:
                        info["participant2_name"] = user2.get("name", "Oyuncu 2")
            
            # Get referee name
            if match.get("referee_id"):
                referee = await self.db.users.find_one({"id": match["referee_id"]})
                if referee:
                    info["referee_name"] = referee.get("name", "Hakem")
            
            # Get event title
            if match.get("event_id"):
                event = await self.db.events.find_one({"id": match["event_id"]})
                if event:
                    info["event_title"] = event.get("title", "Etkinlik")
        except Exception as e:
            logger.error(f"Error getting match info: {str(e)}")
        
        return info
    
    async def send_match_reminder_to_player(
        self,
        user_id: str,
        match: Dict,
        match_info: Dict,
        reminder_type: str,
        time_text: str
    ):
        """Send match reminder notification to a player"""
        try:
            # Format scheduled time
            match_time = match_info.get("scheduled_time")
            if isinstance(match_time, datetime):
                time_str = match_time.strftime("%H:%M")
            else:
                time_str = str(match_time)[:5] if match_time else "?"
            
            # Determine opponent name
            if user_id == match.get("participant1_id"):
                opponent_name = match_info.get("participant2_name", "Rakip")
            else:
                opponent_name = match_info.get("participant1_name", "Rakip")
            
            court_num = match_info.get("court_number", "?")
            referee_name = match_info.get("referee_name")
            
            # Build message
            message = f"⏰ Maçınız {time_text} sonra başlıyor!\n"
            message += f"🏟️ Saha: {court_num}\n"
            message += f"⚔️ Rakip: {opponent_name}\n"
            message += f"🕐 Saat: {time_str}"
            if referee_name:
                message += f"\n🎖️ Hakem: {referee_name}"
            
            title = f"🏆 Maç Hatırlatması - {time_text}"
            
            # Create notification in database
            notification = {
                "id": str(__import__('uuid').uuid4()),
                "user_id": user_id,
                "type": reminder_type,
                "title": title,
                "message": message,
                "related_id": match["id"],
                "related_type": "match",
                "is_read": False,
                "read": False,
                "created_at": datetime.utcnow()
            }
            
            await self.db.notifications.insert_one(notification)
            logger.info(f"🏟️ Created match reminder notification for player {user_id}")
            
            # Send push notification
            push_token_doc = await self.db.push_tokens.find_one({"user_id": user_id})
            
            if push_token_doc and push_token_doc.get("expo_push_token"):
                await self.push_service.send_push_notification(
                    push_tokens=[push_token_doc["expo_push_token"]],
                    title=title,
                    body=message,
                    data={
                        "type": "match_reminder",
                        "match_id": match["id"],
                        "event_id": match.get("event_id"),
                        "notification_id": notification["id"]
                    }
                )
                logger.info(f"🏟️ Sent push notification to player {user_id}")
        except Exception as e:
            logger.error(f"Error sending match reminder to player: {str(e)}")
    
    async def send_match_reminder_to_referee(
        self,
        user_id: str,
        match: Dict,
        match_info: Dict
    ):
        """Send match reminder notification to the referee 5 minutes before"""
        try:
            # Format scheduled time
            match_time = match_info.get("scheduled_time")
            if isinstance(match_time, datetime):
                time_str = match_time.strftime("%H:%M")
            else:
                time_str = str(match_time)[:5] if match_time else "?"
            
            court_num = match_info.get("court_number", "?")
            player1 = match_info.get("participant1_name", "Oyuncu 1")
            player2 = match_info.get("participant2_name", "Oyuncu 2")
            
            # Build message
            message = "⏰ Hakemlik yapacağınız maç 5 dakika sonra başlıyor!\n"
            message += f"🏟️ Saha: {court_num}\n"
            message += f"👤 {player1} vs {player2}\n"
            message += f"🕐 Saat: {time_str}"
            
            title = "🎖️ Hakem Görevi - 5 dakika"
            
            # Create notification in database
            notification = {
                "id": str(__import__('uuid').uuid4()),
                "user_id": user_id,
                "type": "match_reminder_referee_5min",
                "title": title,
                "message": message,
                "related_id": match["id"],
                "related_type": "match",
                "is_read": False,
                "read": False,
                "created_at": datetime.utcnow()
            }
            
            await self.db.notifications.insert_one(notification)
            logger.info(f"🎖️ Created match reminder notification for referee {user_id}")
            
            # Send push notification
            push_token_doc = await self.db.push_tokens.find_one({"user_id": user_id})
            
            if push_token_doc and push_token_doc.get("expo_push_token"):
                await self.push_service.send_push_notification(
                    push_tokens=[push_token_doc["expo_push_token"]],
                    title=title,
                    body=message,
                    data={
                        "type": "match_reminder_referee",
                        "match_id": match["id"],
                        "event_id": match.get("event_id"),
                        "notification_id": notification["id"]
                    }
                )
                logger.info(f"🎖️ Sent push notification to referee {user_id}")
        except Exception as e:
            logger.error(f"Error sending match reminder to referee: {str(e)}")

    # ============================================
    # REVIEW REMINDERS (Rezervasyon/Etkinlik Bitişi Sonrası)
    # ============================================
    
    async def check_review_reminders(self):
        """
        Check for completed reservations/events and send review reminder notifications.
        Runs every 5 minutes.
        """
        try:
            logger.info("⭐ Checking for completed reservations/events for review reminders...")
            now = datetime.utcnow()
            
            # 1. Bitmiş maçlar için oyuncu değerlendirme hatırlatması (maç bitiminden 30 dakika sonra)
            await self.check_match_review_reminders(now)
            
            # 2. Bitmiş rezervasyonlar için değerlendirme hatırlatması
            await self.check_reservation_review_reminders(now)
            
            # 3. Onaylanan siparişler için satıcı değerlendirme hatırlatması
            await self.check_order_review_reminders(now)
            
            logger.info("⭐ Review reminder check completed")
        except Exception as e:
            logger.error(f"Error in check_review_reminders: {str(e)}")
    
    async def check_match_review_reminders(self, now: datetime):
        """Send review reminders for completed matches"""
        try:
            # Maç bitiminden 30 dakika - 1 saat sonrası için kontrol
            check_start = now - timedelta(hours=1)
            check_end = now - timedelta(minutes=30)
            
            # Bitmiş maçları bul
            completed_matches = await self.db.event_matches.find({
                "status": "completed",
                "end_time": {
                    "$gte": check_start.isoformat(),
                    "$lte": check_end.isoformat()
                }
            }).to_list(100)
            
            for match in completed_matches:
                # Her iki oyuncuya da hakem için değerlendirme hatırlatması gönder
                referee_id = match.get("referee_id")
                if not referee_id:
                    continue
                
                for participant_key in ["participant1_id", "participant2_id"]:
                    player_id = match.get(participant_key)
                    if not player_id:
                        continue
                    
                    # Daha önce bildirim gönderilmiş mi kontrol et
                    existing = await self.db.notifications.find_one({
                        "user_id": player_id,
                        "type": "review_reminder_referee",
                        "related_id": match.get("id")
                    })
                    
                    if existing:
                        continue
                    
                    # Hakem bilgisini al
                    referee = await self.db.users.find_one({"id": referee_id})
                    referee_name = referee.get("full_name", "Hakem") if referee else "Hakem"
                    
                    # Bildirim oluştur
                    notification = {
                        "id": str(__import__('uuid').uuid4()),
                        "user_id": player_id,
                        "type": "review_reminder_referee",
                        "title": "⭐ Hakemi Değerlendir",
                        "message": f"Maçınızdaki hakem {referee_name}'i değerlendirmek ister misiniz?",
                        "related_id": match.get("id"),
                        "related_type": "match",
                        "data": {
                            "target_type": "referee",
                            "target_id": referee_id,
                            "target_name": referee_name,
                            "match_id": match.get("id")
                        },
                        "action_url": f"/reviews/referee/{referee_id}",
                        "is_read": False,
                        "read": False,
                        "created_at": datetime.utcnow()
                    }
                    
                    await self.db.notifications.insert_one(notification)
                    logger.info(f"⭐ Created referee review reminder for player {player_id}")
                    
                    # Push notification gönder
                    push_token_doc = await self.db.push_tokens.find_one({"user_id": player_id})
                    if push_token_doc and push_token_doc.get("expo_push_token"):
                        await self.push_service.send_push_notification(
                            push_tokens=[push_token_doc["expo_push_token"]],
                            title="⭐ Hakemi Değerlendir",
                            body=f"Maçınızdaki hakem {referee_name}'i değerlendirmek ister misiniz?",
                            data={
                                "type": "review_reminder",
                                "target_type": "referee",
                                "target_id": referee_id,
                                "notification_id": notification["id"]
                            }
                        )
        except Exception as e:
            logger.error(f"Error in check_match_review_reminders: {str(e)}")
    
    async def check_reservation_review_reminders(self, now: datetime):
        """Send review reminders for completed reservations (coach, player, facility)"""
        try:
            # Rezervasyon bitiminden 30 dakika - 2 saat sonrası için kontrol
            check_start = now - timedelta(hours=2)
            check_end = now - timedelta(minutes=30)
            
            # Bitmiş rezervasyonları bul
            completed_reservations = await self.db.reservations.find({
                "status": {"$in": ["completed", "confirmed"]},
                "end_time": {
                    "$gte": check_start.isoformat(),
                    "$lte": check_end.isoformat()
                }
            }).to_list(100)
            
            for reservation in completed_reservations:
                user_id = reservation.get("user_id")
                target_id = reservation.get("provider_id") or reservation.get("facility_id") or reservation.get("coach_id")
                target_type = reservation.get("type", "facility")  # coach, player, facility
                
                if not user_id or not target_id:
                    continue
                
                # Daha önce bildirim gönderilmiş mi kontrol et
                existing = await self.db.notifications.find_one({
                    "user_id": user_id,
                    "type": f"review_reminder_{target_type}",
                    "related_id": reservation.get("id")
                })
                
                if existing:
                    continue
                
                # Hedef bilgisini al
                if target_type == "facility":
                    target = await self.db.facilities.find_one({"id": target_id})
                    target_name = target.get("name", "Tesis") if target else "Tesis"
                else:
                    target = await self.db.users.find_one({"id": target_id})
                    target_name = target.get("full_name", "Kullanıcı") if target else "Kullanıcı"
                
                type_labels = {
                    "coach": "Antrenörü",
                    "player": "Oyuncuyu",
                    "facility": "Tesisi"
                }
                type_label = type_labels.get(target_type, "Hizmeti")
                
                # Bildirim oluştur
                notification = {
                    "id": str(__import__('uuid').uuid4()),
                    "user_id": user_id,
                    "type": f"review_reminder_{target_type}",
                    "title": f"⭐ {type_label} Değerlendir",
                    "message": f"'{target_name}' ile deneyiminizi değerlendirmek ister misiniz?",
                    "related_id": reservation.get("id"),
                    "related_type": "reservation",
                    "data": {
                        "target_type": target_type,
                        "target_id": target_id,
                        "target_name": target_name,
                        "reservation_id": reservation.get("id")
                    },
                    "action_url": f"/reviews/{target_type}/{target_id}",
                    "is_read": False,
                    "read": False,
                    "created_at": datetime.utcnow()
                }
                
                await self.db.notifications.insert_one(notification)
                logger.info(f"⭐ Created {target_type} review reminder for user {user_id}")
                
                # Push notification gönder
                push_token_doc = await self.db.push_tokens.find_one({"user_id": user_id})
                if push_token_doc and push_token_doc.get("expo_push_token"):
                    await self.push_service.send_push_notification(
                        push_tokens=[push_token_doc["expo_push_token"]],
                        title=f"⭐ {type_label} Değerlendir",
                        body=f"'{target_name}' ile deneyiminizi değerlendirmek ister misiniz?",
                        data={
                            "type": "review_reminder",
                            "target_type": target_type,
                            "target_id": target_id,
                            "notification_id": notification["id"]
                        }
                    )
        except Exception as e:
            logger.error(f"Error in check_reservation_review_reminders: {str(e)}")
    
    async def check_order_review_reminders(self, now: datetime):
        """Send review reminders for approved orders (seller review)"""
        try:
            # Sipariş onayından 1-24 saat sonrası için kontrol
            check_start = now - timedelta(hours=24)
            check_end = now - timedelta(hours=1)
            
            # Onaylanmış ama değerlendirilmemiş siparişleri bul
            approved_orders = await self.db.marketplace_transactions.find({
                "status": "approved",
                "reviewed": {"$ne": True},
                "approved_at": {
                    "$gte": check_start,
                    "$lte": check_end
                }
            }).to_list(100)
            
            for order in approved_orders:
                buyer_id = order.get("buyer_id")
                seller_id = order.get("seller_id")
                
                if not buyer_id or not seller_id:
                    continue
                
                # Daha önce bildirim gönderilmiş mi kontrol et
                existing = await self.db.notifications.find_one({
                    "user_id": buyer_id,
                    "type": "review_reminder_seller",
                    "related_id": order.get("id")
                })
                
                if existing:
                    continue
                
                # Satıcı ve ürün bilgisini al
                seller = await self.db.users.find_one({"id": seller_id})
                seller_name = seller.get("full_name", "Satıcı") if seller else "Satıcı"
                
                listing = await self.db.marketplace_listings.find_one({"id": order.get("listing_id")})
                listing_title = listing.get("title", "Ürün") if listing else "Ürün"
                
                # Bildirim oluştur
                notification = {
                    "id": str(__import__('uuid').uuid4()),
                    "user_id": buyer_id,
                    "type": "review_reminder_seller",
                    "title": "⭐ Satıcıyı Değerlendir",
                    "message": f"'{listing_title}' için satıcı {seller_name}'i değerlendirmek ister misiniz?",
                    "related_id": order.get("id"),
                    "related_type": "order",
                    "data": {
                        "target_type": "seller",
                        "target_id": seller_id,
                        "target_name": seller_name,
                        "order_id": order.get("id"),
                        "listing_title": listing_title
                    },
                    "action_url": "/marketplace/my-orders",
                    "is_read": False,
                    "read": False,
                    "created_at": datetime.utcnow()
                }
                
                await self.db.notifications.insert_one(notification)
                logger.info(f"⭐ Created seller review reminder for buyer {buyer_id}")
                
                # Push notification gönder
                push_token_doc = await self.db.push_tokens.find_one({"user_id": buyer_id})
                if push_token_doc and push_token_doc.get("expo_push_token"):
                    await self.push_service.send_push_notification(
                        push_tokens=[push_token_doc["expo_push_token"]],
                        title="⭐ Satıcıyı Değerlendir",
                        body=f"'{listing_title}' için satıcı {seller_name}'i değerlendirmek ister misiniz?",
                        data={
                            "type": "review_reminder",
                            "target_type": "seller",
                            "target_id": seller_id,
                            "order_id": order.get("id"),
                            "notification_id": notification["id"]
                        }
                    )
        except Exception as e:
            logger.error(f"Error in check_order_review_reminders: {str(e)}")


    async def _check_marketplace_auto_approval_with_db(self, fresh_db):
        """Auto-approve delivered orders after 1 day"""
        try:
            logger.info("🛒 Checking for orders to auto-approve...")
            now = datetime.utcnow()
            
            # Find orders that:
            # 1. Status is "delivered"
            # 2. auto_approve_deadline has passed
            # 3. Not yet auto-approved
            orders_to_approve = await fresh_db.marketplace_transactions.find({
                "status": "delivered",
                "auto_approve_deadline": {"$lt": now},
                "auto_approved": {"$ne": True}
            }).to_list(100)
            
            if not orders_to_approve:
                logger.info("🛒 No orders to auto-approve")
                return
            
            logger.info(f"🛒 Found {len(orders_to_approve)} orders to auto-approve")
            
            for order in orders_to_approve:
                try:
                    order_id = order.get("id")
                    buyer_id = order.get("buyer_id")
                    seller_id = order.get("seller_id")
                    listing_id = order.get("listing_id")
                    
                    # Get listing info
                    listing = await fresh_db.marketplace_listings.find_one({"id": listing_id})
                    listing_title = listing.get("title", "Ürün") if listing else "Ürün"
                    
                    # Update order status
                    await fresh_db.marketplace_transactions.update_one(
                        {"id": order_id},
                        {"$set": {
                            "status": "approved",
                            "auto_approved": True,
                            "approved_at": now
                        }}
                    )
                    
                    # Update listing status
                    await fresh_db.marketplace_listings.update_one(
                        {"id": listing_id},
                        {"$set": {"status": "completed"}}
                    )
                    
                    # Create notification for buyer
                    buyer_notification = {
                        "id": str(uuid.uuid4()),
                        "user_id": buyer_id,
                        "type": "order_auto_approved",
                        "title": "✅ Sipariş Otomatik Onaylandı",
                        "message": f"'{listing_title}' siparişiniz 1 gün içinde onaylanmadığı için otomatik olarak onaylandı.",
                        "related_id": order_id,
                        "related_type": "marketplace_order",
                        "data": {
                            "order_id": order_id,
                            "listing_id": listing_id,
                            "seller_id": seller_id,
                            "can_review": True
                        },
                        "read": False,
                        "created_at": now
                    }
                    await fresh_db.notifications.insert_one(buyer_notification)
                    
                    # Create notification for seller
                    seller_notification = {
                        "id": str(uuid.uuid4()),
                        "user_id": seller_id,
                        "type": "order_auto_approved_seller",
                        "title": "✅ Sipariş Otomatik Onaylandı",
                        "message": f"'{listing_title}' siparişi alıcı tarafından 1 gün içinde onaylanmadığı için otomatik olarak onaylandı.",
                        "related_id": order_id,
                        "related_type": "marketplace_order",
                        "data": {
                            "order_id": order_id,
                            "listing_id": listing_id,
                            "buyer_id": buyer_id
                        },
                        "read": False,
                        "created_at": now
                    }
                    await fresh_db.notifications.insert_one(seller_notification)
                    
                    # Create notification for admins
                    admins = await fresh_db.users.find({"user_type": "admin"}).to_list(100)
                    for admin in admins:
                        admin_notification = {
                            "id": str(uuid.uuid4()),
                            "user_id": admin["id"],
                            "type": "order_auto_approved_admin",
                            "title": "🔔 Sipariş Otomatik Onaylandı",
                            "message": f"'{listing_title}' siparişi otomatik olarak onaylandı (1 gün aşıldı).",
                            "related_id": order_id,
                            "related_type": "marketplace_order",
                            "data": {
                                "order_id": order_id,
                                "listing_id": listing_id,
                                "buyer_id": buyer_id,
                                "seller_id": seller_id
                            },
                            "read": False,
                            "created_at": now
                        }
                        await fresh_db.notifications.insert_one(admin_notification)
                    
                    logger.info(f"✅ Order {order_id} auto-approved, notifications sent")
                    
                except Exception as e:
                    logger.error(f"Error auto-approving order {order.get('id')}: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error in check_marketplace_auto_approval: {str(e)}")


    # ============================================
    # CARGO TRACKING (6 saatte bir)
    # ============================================
    
    async def _check_cargo_tracking_with_db(self, fresh_db):
        """
        6 saatte bir çalışan kargo takip sistemi.
        - Tüm 'shipped' durumundaki işlemleri kontrol et
        - Geliver API ile kargo durumunu sorgula
        - Durum değişikliklerinde alıcı ve satıcıya bildirim gönder
        """
        try:
            logger.info("📦 Starting cargo tracking check...")
            now = datetime.utcnow()
            
            # 'shipped' veya 'label_created' veya 'in_transit' durumundaki işlemleri bul
            transactions_to_track = await fresh_db.marketplace_transactions.find({
                "status": {"$in": ["shipped", "label_created", "in_transit", "out_for_delivery", "completed"]},
                "tracking_code": {"$exists": True, "$ne": ""},
                "shipping_status": {"$nin": ["delivered", "returned", "failed"]}  # Henüz teslim edilmemişler
            }).to_list(500)
            
            if not transactions_to_track:
                logger.info("📦 No shipments to track")
                return
            
            logger.info(f"📦 Found {len(transactions_to_track)} shipments to track")
            
            # Geliver tracking fonksiyonunu import et
            from geliver_endpoints import track_shipment_by_code, SHIPPING_STATUS_TEXT
            
            status_updates = 0
            notifications_sent = 0
            
            for transaction in transactions_to_track:
                try:
                    transaction_id = transaction.get("id")
                    tracking_code = transaction.get("tracking_code") or transaction.get("barcode")
                    provider_code = transaction.get("shipping_provider")
                    buyer_id = transaction.get("buyer_id")
                    seller_id = transaction.get("seller_id")
                    listing_id = transaction.get("listing_id")
                    old_shipping_status = transaction.get("shipping_status", "unknown")
                    
                    if not tracking_code:
                        continue
                    
                    # Geliver API'ye sorgula
                    tracking_result = await track_shipment_by_code(tracking_code, provider_code)
                    
                    if not tracking_result.get("success"):
                        logger.warning(f"📦 Tracking failed for {tracking_code}: {tracking_result.get('error')}")
                        continue
                    
                    new_status = tracking_result.get("status", "unknown")
                    status_text = tracking_result.get("status_text", "")
                    
                    # Durum değişikliği var mı kontrol et
                    if new_status != old_shipping_status and new_status != "unknown":
                        logger.info(f"📦 Status change for {tracking_code}: {old_shipping_status} -> {new_status}")
                        
                        # Transaction'ı güncelle
                        update_data = {
                            "shipping_status": new_status,
                            "shipping_status_text": status_text,
                            "last_tracking_check": now,
                            "updated_at": now
                        }
                        
                        # Eğer teslim edildiyse, status'u da güncelle
                        if new_status == "delivered":
                            update_data["status"] = "delivered"
                            update_data["delivered_at"] = now
                            # 1 gün sonra otomatik onay için deadline koy
                            update_data["auto_approve_deadline"] = now + timedelta(days=1)
                        
                        await fresh_db.marketplace_transactions.update_one(
                            {"id": transaction_id},
                            {"$set": update_data}
                        )
                        status_updates += 1
                        
                        # Listing bilgisini al
                        listing = await fresh_db.marketplace_listings.find_one({"id": listing_id})
                        listing_title = listing.get("title", "Ürün") if listing else "Ürün"
                        
                        # Bildirim mesajlarını belirle
                        notification_title, notification_message = self._get_shipping_notification_message(
                            new_status, tracking_code, listing_title, provider_code
                        )
                        
                        # Alıcıya bildirim gönder
                        buyer_notification = {
                            "id": str(uuid.uuid4()),
                            "user_id": buyer_id,
                            "type": f"shipping_status_{new_status}",
                            "title": notification_title,
                            "message": notification_message,
                            "related_id": transaction_id,
                            "related_type": "marketplace_order",
                            "data": {
                                "transaction_id": transaction_id,
                                "listing_id": listing_id,
                                "tracking_code": tracking_code,
                                "shipping_status": new_status,
                                "shipping_status_text": status_text
                            },
                            "read": False,
                            "created_at": now
                        }
                        await fresh_db.notifications.insert_one(buyer_notification)
                        notifications_sent += 1
                        
                        # Satıcıya bildirim gönder
                        seller_notification = {
                            "id": str(uuid.uuid4()),
                            "user_id": seller_id,
                            "type": f"shipping_status_{new_status}_seller",
                            "title": notification_title,
                            "message": notification_message,
                            "related_id": transaction_id,
                            "related_type": "marketplace_order",
                            "data": {
                                "transaction_id": transaction_id,
                                "listing_id": listing_id,
                                "tracking_code": tracking_code,
                                "shipping_status": new_status,
                                "shipping_status_text": status_text
                            },
                            "read": False,
                            "created_at": now
                        }
                        await fresh_db.notifications.insert_one(seller_notification)
                        notifications_sent += 1
                        
                        # Push notification gönder (eğer push service varsa)
                        if self.push_service:
                            try:
                                # Alıcı push
                                buyer_push_token = await fresh_db.push_tokens.find_one({"user_id": buyer_id})
                                if buyer_push_token and buyer_push_token.get("expo_push_token"):
                                    await self.push_service.send_push_notification(
                                        push_tokens=[buyer_push_token["expo_push_token"]],
                                        title=notification_title,
                                        body=notification_message,
                                        data={
                                            "type": f"shipping_{new_status}",
                                            "transaction_id": transaction_id,
                                            "tracking_code": tracking_code
                                        }
                                    )
                                
                                # Satıcı push
                                seller_push_token = await fresh_db.push_tokens.find_one({"user_id": seller_id})
                                if seller_push_token and seller_push_token.get("expo_push_token"):
                                    await self.push_service.send_push_notification(
                                        push_tokens=[seller_push_token["expo_push_token"]],
                                        title=notification_title,
                                        body=notification_message,
                                        data={
                                            "type": f"shipping_{new_status}",
                                            "transaction_id": transaction_id,
                                            "tracking_code": tracking_code
                                        }
                                    )
                            except Exception as push_err:
                                logger.error(f"Push notification error: {str(push_err)}")
                    else:
                        # Durum değişikliği yok, sadece last_tracking_check güncelle
                        await fresh_db.marketplace_transactions.update_one(
                            {"id": transaction_id},
                            {"$set": {"last_tracking_check": now}}
                        )
                    
                except Exception as e:
                    logger.error(f"Error tracking shipment {transaction.get('id')}: {str(e)}")
                    continue
            
            logger.info(f"📦 Cargo tracking completed: {status_updates} updates, {notifications_sent} notifications sent")
            
        except Exception as e:
            logger.error(f"Error in cargo tracking check: {str(e)}")
    
    def _get_shipping_notification_message(self, status: str, tracking_code: str, listing_title: str, provider_code: str = None) -> tuple:
        """Kargo durumuna göre bildirim başlığı ve mesajı oluştur"""
        provider_name = provider_code or "Kargo"
        
        messages = {
            "pending_pickup": (
                "📦 Kargo Hazırlanıyor",
                f"'{listing_title}' kargonuz hazırlanıyor. Kargo Kodu: {tracking_code}"
            ),
            "in_transit": (
                "🚚 Kargo Yola Çıktı",
                f"'{listing_title}' kargonuz yola çıktı! Kargo Kodu: {tracking_code}. {provider_name} ile takip edebilirsiniz."
            ),
            "out_for_delivery": (
                "🏃 Kargo Dağıtımda",
                f"'{listing_title}' kargonuz dağıtıma çıktı! Bugün teslim edilecek. Kargo Kodu: {tracking_code}"
            ),
            "delivered": (
                "✅ Kargo Teslim Edildi",
                f"'{listing_title}' kargonuz teslim edildi! Kargo Kodu: {tracking_code}. Ürünü kontrol edip onaylayabilirsiniz."
            ),
            "returned": (
                "↩️ Kargo İade Edildi",
                f"'{listing_title}' kargonuz iade edildi. Kargo Kodu: {tracking_code}. Detaylar için işlem geçmişinizi kontrol edin."
            ),
            "failed": (
                "⚠️ Kargo Teslim Edilemedi",
                f"'{listing_title}' kargonuz teslim edilemedi. Kargo Kodu: {tracking_code}. Lütfen kargo firmasıyla iletişime geçin."
            )
        }
        
        return messages.get(status, (
            "📦 Kargo Durumu Güncellendi",
            f"'{listing_title}' kargonuzun durumu güncellendi. Kargo Kodu: {tracking_code}"
        ))
