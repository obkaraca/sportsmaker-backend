"""
Event and Reservation Reminder Scheduler
Sends notifications 24 hours and 1 hour before events/reservations start
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, timezone
import logging
from typing import List, Dict
import asyncio
from push_notification_service import PushNotificationService

logger = logging.getLogger(__name__)

# Global push notification service
push_service = None

# Global scheduler instance
scheduler = None

async def check_and_send_reminders(db):
    """
    Check for upcoming events and reservations and send notifications
    Runs every 5 minutes
    """
    try:
        logger.info("🔔 Running reminder check...")
        now = datetime.now(timezone.utc)
        
        # Get all active users
        users = await db.users.find({}).to_list(length=None)
        
        for user in users:
            user_id = user.get("id")
            if not user_id:
                continue
                
            await send_user_reminders(db, user_id, now)
            
        logger.info("✅ Reminder check completed")
    except Exception as e:
        logger.error(f"❌ Error in reminder check: {str(e)}")

async def send_user_reminders(db, user_id: str, now: datetime):
    """Send reminders for a specific user"""
    try:
        # Get user's event participations
        participations = await db.participations.find({
            "user_id": user_id,
            "status": "approved"
        }).to_list(1000)
        
        for participation in participations:
            event = await db.events.find_one({"id": participation["event_id"]})
            if event and event.get("start_date"):
                await check_event_reminder(db, user_id, event, now)
        
        # Get user's reservations
        reservations = await db.reservations.find({
            "user_id": user_id,
            "status": "confirmed"
        }).to_list(1000)
        
        # Get reservations TO user
        user = await db.users.find_one({"id": user_id})
        if user:
            user_type = user.get("user_type")
            if user_type in ["player", "coach", "referee", "venue_owner"]:
                reservations_to_me = await db.reservations.find({
                    "$or": [
                        {"player_id": user_id},
                        {"coach_id": user_id},
                        {"referee_id": user_id},
                        {"venue_id": user_id}
                    ],
                    "status": "confirmed"
                }).to_list(1000)
                reservations.extend(reservations_to_me)
        
        for reservation in reservations:
            await check_reservation_reminder(db, user_id, reservation, now)
            
    except Exception as e:
        logger.error(f"Error sending reminders for user {user_id}: {str(e)}")

async def check_event_reminder(db, user_id: str, event: Dict, now: datetime):
    """Check if event needs reminder and send notification"""
    try:
        event_time = datetime.fromisoformat(event["start_date"].replace('Z', '+00:00'))
        
        # Skip past events
        if event_time <= now:
            return
        
        hours_until = (event_time - now).total_seconds() / 3600
        
        # Check if we should send reminder
        reminder_type = None
        if 23.5 <= hours_until <= 24.5:  # 24 hour window (30 min tolerance)
            reminder_type = "24h"
        elif 0.5 <= hours_until <= 1.5:  # 1 hour window (30 min tolerance)
            reminder_type = "1h"
        else:
            return  # Not in reminder window
        
        # Check if notification already sent
        notification_exists = await db.notifications.find_one({
            "user_id": user_id,
            "type": f"event_reminder_{reminder_type}",
            "data.event_id": event["id"]
        })
        
        if notification_exists:
            return  # Already sent
        
        # Create notification
        notification_id = str(datetime.now().timestamp())
        
        title = f"🔔 Etkinlik Hatırlatması"
        if reminder_type == "24h":
            message = f"'{event['title']}' etkinliğinin başlamasına 24 saat kaldı!"
        else:  # 1h
            message = f"'{event['title']}' etkinliğinin başlamasına 1 saat kaldı! Hazırlıklı olun."
        
        notification = {
            "id": notification_id,
            "user_id": user_id,
            "type": f"event_reminder_{reminder_type}",
            "title": title,
            "message": message,
            "read": False,
            "created_at": now,
            "data": {
                "event_id": event["id"],
                "event_title": event["title"],
                "start_date": event["start_date"],
                "hours_until": round(hours_until, 1),
                "reminder_type": reminder_type
            }
        }
        
        await db.notifications.insert_one(notification)
        logger.info(f"📅 Sent {reminder_type} reminder for event '{event['title']}' to user {user_id[:20]}")
        
        # Send push notification
        if push_service:
            user = await db.users.find_one({"id": user_id})
            if user and user.get("push_tokens"):
                try:
                    await PushNotificationService.send_push_notification(
                        push_tokens=user["push_tokens"],
                        title=title,
                        body=message,
                        data={
                            "type": "event_reminder",
                            "event_id": event["id"],
                            "reminder_type": reminder_type
                        }
                    )
                    logger.info(f"📲 Push sent to user {user_id[:20]}")
                except Exception as push_error:
                    logger.error(f"Push notification error: {str(push_error)}")
        
    except Exception as e:
        logger.error(f"Error checking event reminder: {str(e)}")

async def check_reservation_reminder(db, user_id: str, reservation: Dict, now: datetime):
    """Check if reservation needs reminder and send notification"""
    try:
        if not reservation.get("date") or not reservation.get("start_time"):
            return
        
        # Combine date and start_time
        reservation_date = datetime.fromisoformat(reservation["date"].replace('Z', '+00:00'))
        start_time = datetime.fromisoformat(reservation["start_time"].replace('Z', '+00:00'))
        
        reservation_datetime = datetime.combine(
            reservation_date.date(),
            start_time.time(),
            tzinfo=timezone.utc
        )
        
        # Skip past reservations
        if reservation_datetime <= now:
            return
        
        hours_until = (reservation_datetime - now).total_seconds() / 3600
        
        # Check if we should send reminder
        reminder_type = None
        if 23.5 <= hours_until <= 24.5:  # 24 hour window
            reminder_type = "24h"
        elif 0.5 <= hours_until <= 1.5:  # 1 hour window
            reminder_type = "1h"
        else:
            return
        
        # Check if notification already sent
        notification_exists = await db.notifications.find_one({
            "user_id": user_id,
            "type": f"reservation_reminder_{reminder_type}",
            "data.reservation_id": reservation["id"]
        })
        
        if notification_exists:
            return
        
        # Get venue name
        venue_name = "Yer"
        if reservation.get("venue_id"):
            venue = await db.venues.find_one({"id": reservation["venue_id"]})
            if venue:
                venue_name = venue.get("name", venue_name)
        
        # Create notification
        notification_id = str(datetime.now().timestamp())
        
        title = f"🔔 Rezervasyon Hatırlatması"
        if reminder_type == "24h":
            message = f"'{venue_name}' rezervasyonunuzun başlamasına 24 saat kaldı!"
        else:  # 1h
            message = f"'{venue_name}' rezervasyonunuzun başlamasına 1 saat kaldı! Hazırlıklı olun."
        
        notification = {
            "id": notification_id,
            "user_id": user_id,
            "type": f"reservation_reminder_{reminder_type}",
            "title": title,
            "message": message,
            "read": False,
            "created_at": now,
            "data": {
                "reservation_id": reservation["id"],
                "venue_name": venue_name,
                "start_date": reservation["date"],
                "start_time": reservation["start_time"],
                "hours_until": round(hours_until, 1),
                "reminder_type": reminder_type
            }
        }
        
        await db.notifications.insert_one(notification)
        logger.info(f"📅 Sent {reminder_type} reminder for reservation at '{venue_name}' to user {user_id[:20]}")
        
    except Exception as e:
        logger.error(f"Error checking reservation reminder: {str(e)}")

def start_reminder_scheduler(db):
    """Start the reminder scheduler"""
    global scheduler
    
    if scheduler is not None:
        logger.warning("Scheduler already running")
        return
    
    scheduler = AsyncIOScheduler()
    
    # Run reminder check every 5 minutes
    scheduler.add_job(
        check_and_send_reminders,
        'interval',
        minutes=5,
        args=[db],
        id='reminder_check',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("✅ Reminder scheduler started (checking every 5 minutes)")

def stop_reminder_scheduler():
    """Stop the reminder scheduler"""
    global scheduler
    
    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        logger.info("❌ Reminder scheduler stopped")
