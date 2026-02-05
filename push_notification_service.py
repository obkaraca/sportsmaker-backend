"""
Push Notification Service
Handles sending push notifications via Expo Push Notification API
"""
import os
import requests
import logging
from typing import List, Dict, Optional
from models import NotificationType, NotificationRelatedType

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
logger = logging.getLogger(__name__)

class PushNotificationService:
    
    def __init__(self):
        self.db = None
    
    def set_db(self, database):
        """Database referansını ayarla"""
        self.db = database
    
    async def send_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        data: Optional[Dict] = None,
        badge: int = 1
    ) -> Dict:
        """
        Send push notification to a single user by user_id
        This method looks up the user's push token from the database
        """
        if not self.db:
            logger.warning("Database not set for PushNotificationService")
            return {"success": False, "error": "Database not configured"}
        
        try:
            # Get user's push token from database
            user = await self.db.users.find_one({"id": user_id})
            if not user:
                logger.warning(f"User not found for push notification: {user_id}")
                return {"success": False, "error": "User not found"}
            
            push_token = user.get("push_token") or user.get("expoPushToken")
            if not push_token:
                logger.debug(f"No push token for user: {user_id}")
                return {"success": False, "error": "No push token for user"}
            
            # Send the notification
            return await self.send_push_notification(
                push_tokens=[push_token],
                title=title,
                body=body,
                data=data,
                badge=badge
            )
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def send_push_notification(
        push_tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict] = None,
        badge: int = 1
    ) -> Dict:
        """
        Send push notification to multiple devices
        """
        if not push_tokens:
            return {"success": False, "error": "No push tokens provided"}
        
        messages = []
        for token in push_tokens:
            if not token:
                continue
            # Accept both ExponentPushToken and expo push token formats
            if not (token.startswith("ExponentPushToken") or token.startswith("Expo")):
                logger.warning(f"Invalid push token format: {token[:20]}...")
                continue
                
            message = {
                "to": token,
                "sound": "default",
                "title": title,
                "body": body,
                "data": data or {},
                "badge": badge,  # ✅ Badge eklendi
            }
            messages.append(message)
        
        if not messages:
            return {"success": False, "error": "No valid push tokens"}
        
        try:
            response = requests.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Push notification sent successfully to {len(messages)} devices")
                return {"success": True, "data": response.json()}
            else:
                logger.error(f"Push notification failed: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"Failed to send notification: {response.status_code}",
                    "details": response.text
                }
        except Exception as e:
            logger.error(f"Push notification exception: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_to_multiple_users(
        self,
        user_ids: List[str],
        title: str,
        body: str,
        data: Optional[Dict] = None,
        badge: int = 1
    ) -> Dict:
        """
        Send push notification to multiple users by their IDs
        """
        if not self.db:
            logger.warning("Database not set for PushNotificationService")
            return {"success": False, "error": "Database not configured"}
        
        try:
            # Get all users' push tokens
            users = await self.db.users.find({"id": {"$in": user_ids}}).to_list(length=None)
            push_tokens = []
            
            for user in users:
                token = user.get("push_token") or user.get("expoPushToken")
                if token:
                    push_tokens.append(token)
            
            if not push_tokens:
                return {"success": False, "error": "No push tokens found for users"}
            
            return await self.send_push_notification(
                push_tokens=push_tokens,
                title=title,
                body=body,
                data=data,
                badge=badge
            )
        except Exception as e:
            logger.error(f"Error sending notification to multiple users: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_notification_content(
        notification_type: NotificationType,
        related_data: Dict
    ) -> Dict[str, str]:
        """
        Get notification title and body based on type
        """
        if notification_type == NotificationType.MESSAGE_RECEIVED:
            return {
                "title": "Yeni Mesaj",
                "body": f"{related_data.get('sender_name', 'Bir kullanıcı')} size mesaj gönderdi"
            }
        elif notification_type == NotificationType.EVENT_REMINDER_1DAY:
            return {
                "title": "Etkinlik Hatırlatma",
                "body": f"{related_data.get('event_title', 'Etkinlik')} yarın başlıyor!"
            }
        elif notification_type == NotificationType.EVENT_REMINDER_1HOUR:
            return {
                "title": "Etkinlik Yakında",
                "body": f"{related_data.get('event_title', 'Etkinlik')} 1 saat içinde başlıyor!"
            }
        elif notification_type == NotificationType.PARTICIPANT_JOINED:
            return {
                "title": "Yeni Katılımcı",
                "body": f"{related_data.get('participant_name', 'Bir kullanıcı')} etkinliğinize katıldı"
            }
        elif notification_type == NotificationType.EVENT_JOINED:
            return {
                "title": "Etkinliğe Katıldınız",
                "body": f"'{related_data.get('event_title', 'Etkinlik')}' etkinliğine başarıyla katıldınız"
            }
        else:
            return {
                "title": "Bildirim",
                "body": "Yeni bir bildiriminiz var"
            }
