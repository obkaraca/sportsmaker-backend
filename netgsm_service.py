"""
Netgsm SMS Service for Turkish Phone Numbers
Handles OTP sending with Turkish character support
"""

import requests
import secrets
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class NetgsmService:
    """Service for sending SMS via Netgsm API"""
    
    # Netgsm API endpoints
    SMS_API_URL = "https://api.netgsm.com.tr/sms/send/get"
    OTP_API_URL = "https://api.netgsm.com.tr/sms/send/otp"  # Dedicated OTP endpoint
    
    def __init__(self):
        """Initialize Netgsm service with credentials from environment"""
        self.username = os.getenv('NETGSM_USERNAME', '')
        self.password = os.getenv('NETGSM_PASSWORD', '')
        self.msgheader = os.getenv('NETGSM_MSGHEADER', 'SPORTCON')
        
        # Validate credentials
        if not self.username or not self.password:
            logger.warning("⚠️  Netgsm credentials not configured. SMS sending will be mocked.")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("✅ Netgsm service initialized successfully")
    
    @staticmethod
    def normalize_phone_number(phone: str, domestic_format: bool = True) -> str:
        """
        Normalize Turkish phone number to Netgsm format
        
        Args:
            phone: Phone number in various formats
            domestic_format: If True, returns format for domestic SMS (5XXXXXXXXX)
                           If False, returns international format (90XXXXXXXXX)
            
        Returns:
            Normalized phone number
        """
        # Remove spaces, dashes, parentheses
        cleaned = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        # Remove + if present
        if cleaned.startswith('+'):
            cleaned = cleaned[1:]
        
        # Get the 10-digit mobile number (5XXXXXXXXX)
        if cleaned.startswith('90') and len(cleaned) == 12:
            # 905XXXXXXXXX -> 5XXXXXXXXX
            mobile_number = cleaned[2:]
        elif cleaned.startswith('0') and len(cleaned) == 11:
            # 05XXXXXXXXX -> 5XXXXXXXXX
            mobile_number = cleaned[1:]
        elif cleaned.startswith('5') and len(cleaned) == 10:
            # Already 5XXXXXXXXX
            mobile_number = cleaned
        else:
            # Invalid format, return as is
            return cleaned
        
        # Return based on format preference
        if domestic_format:
            # For Turkey domestic SMS: 5XXXXXXXXX
            return mobile_number
        else:
            # For international format: 905XXXXXXXXX
            return '90' + mobile_number
    
    @staticmethod
    def validate_turkish_number(phone: str) -> bool:
        """
        Validate Turkish mobile phone number
        
        Valid formats:
        - +90 5XX XXX XXXX
        - 0 5XX XXX XXXX
        - 5XX XXX XXXX
        
        Returns:
            True if valid Turkish mobile number
        """
        # Get domestic format (5XXXXXXXXX)
        normalized = NetgsmService.normalize_phone_number(phone, domestic_format=True)
        
        # Must be 10 digits starting with 5
        if len(normalized) != 10 or not normalized.startswith('5'):
            return False
        
        # Second digit must be valid operator prefix
        valid_prefixes = ['0', '1', '2', '3', '4', '5', '6']  # Turkish mobile operators
        if normalized[1] not in valid_prefixes:
            return False
        
        # Must be all digits
        if not normalized.isdigit():
            return False
        
        return True
    
    @staticmethod
    def generate_otp(length: int = 6) -> str:
        """
        Generate cryptographically secure OTP
        
        Args:
            length: OTP length (default: 6)
            
        Returns:
            Numeric OTP string
        """
        return ''.join(secrets.choice('0123456789') for _ in range(length))
    
    def send_sms(self, phone: str, message: str) -> Dict:
        """
        Send SMS via Netgsm API
        
        Args:
            phone: Recipient phone number
            message: SMS message content
            
        Returns:
            Dict with success status and job_id or error
        """
        try:
            # Validate phone number
            if not self.validate_turkish_number(phone):
                logger.error(f"Invalid Turkish phone number: {phone}")
                return {
                    'success': False,
                    'error': 'Invalid Turkish phone number format'
                }
            
            # Normalize phone number (use domestic format for Turkey)
            normalized_phone = self.normalize_phone_number(phone, domestic_format=True)
            
            # Check if service is enabled
            if not self.enabled:
                logger.info(f"📱 MOCK SMS to {normalized_phone}: {message}")
                return {
                    'success': True,
                    'job_id': 'MOCK_' + secrets.token_hex(8),
                    'message': 'SMS sent (mock mode)',
                    'mock': True
                }
            
            # Prepare API request
            params = {
                'usercode': self.username,
                'password': self.password,
                'gsmno': normalized_phone,
                'message': message,
                'msgheader': self.msgheader,
                'dil': 'TR'  # Turkish character support
            }
            
            # Send request to Netgsm API
            response = requests.get(self.SMS_API_URL, params=params, timeout=10)
            response_text = response.text.strip()
            
            # Parse response
            # Success: "00 123456789" (00 followed by job ID)
            # Error: Error code (20, 30, 40, etc.)
            if response_text.startswith('00'):
                parts = response_text.split()
                job_id = parts[1] if len(parts) > 1 else 'unknown'
                
                logger.info(f"✅ SMS sent successfully to {normalized_phone}. Job ID: {job_id}")
                
                return {
                    'success': True,
                    'job_id': job_id,
                    'message': 'SMS sent successfully',
                    'phone': normalized_phone
                }
            else:
                # Error occurred
                error_messages = {
                    '20': 'Message text error or exceeds character limit',
                    '30': 'Invalid credentials or insufficient API access',
                    '40': 'Sender ID (message header) not registered',
                    '50': 'Invalid recipient numbers',
                    '51': 'Sender ID (message header) not approved or approval pending',
                    '60': 'Invalid job ID',
                    '70': 'Invalid parameters',
                    '80': 'Daily sending limit exceeded',
                    '85': 'Duplicate sending limit exceeded'
                }
                
                error_msg = error_messages.get(response_text, f'Unknown error: {response_text}')
                logger.error(f"❌ Netgsm error {response_text}: {error_msg}")
                
                return {
                    'success': False,
                    'error': error_msg,
                    'error_code': response_text
                }
                
        except requests.RequestException as e:
            logger.error(f"Network error sending SMS: {str(e)}")
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Unexpected error sending SMS: {str(e)}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }
    
    def send_otp_sms(self, phone: str, otp_code: Optional[str] = None) -> Dict:
        """
        Send OTP verification code via Netgsm dedicated OTP API
        
        Args:
            phone: Recipient phone number
            otp_code: OTP code (if None, generates new one)
            
        Returns:
            Dict with success status, job_id, and otp_code
        """
        # Generate OTP if not provided
        if not otp_code:
            otp_code = self.generate_otp()
        
        try:
            # Validate phone number
            if not self.validate_turkish_number(phone):
                logger.error(f"Invalid Turkish phone number: {phone}")
                return {
                    'success': False,
                    'error': 'Invalid Turkish phone number format'
                }
            
            # Normalize phone number - OTP API requires 5XXXXXXXXX format
            normalized_phone = self.normalize_phone_number(phone, domestic_format=True)
            
            # Check if service is enabled
            if not self.enabled:
                logger.info(f"📱 MOCK OTP SMS to {normalized_phone}: {otp_code}")
                return {
                    'success': True,
                    'job_id': 'MOCK_OTP_' + secrets.token_hex(8),
                    'otp_code': otp_code,
                    'message': 'OTP sent (mock mode)',
                    'mock': True,
                    'expires_at': datetime.utcnow() + timedelta(minutes=2)
                }
            
            # Create OTP message - short and clear
            message = f"SportsMaker dogrulama kodunuz: {otp_code}"
            
            # Prepare OTP API request (XML format as per Netgsm docs)
            xml_data = f'''<?xml version="1.0" encoding="UTF-8"?>
<mainbody>
    <header>
        <usercode>{self.username}</usercode>
        <password>{self.password}</password>
        <msgheader>{self.msgheader}</msgheader>
    </header>
    <body>
        <msg><![CDATA[{message}]]></msg>
        <no>{normalized_phone}</no>
    </body>
</mainbody>'''
            
            # Send request to Netgsm OTP API
            logger.info(f"📱 Sending OTP via dedicated OTP API to {normalized_phone}")
            
            headers = {'Content-Type': 'application/xml'}
            response = requests.post(
                self.OTP_API_URL, 
                data=xml_data.encode('utf-8'), 
                headers=headers, 
                timeout=15
            )
            response_text = response.text.strip()
            
            logger.info(f"📱 OTP API Response: {response_text}")
            
            # Parse response - OTP API returns XML format
            # Success: <?xml version="1.0"?><xml><main><code>0</code><jobID>xxx</jobID></main></xml>
            # Error: <?xml version="1.0"?><xml><main><code>30</code><error>xxx</error></main></xml>
            
            if '<code>0</code>' in response_text or '<code>00</code>' in response_text:
                # Success - extract job ID
                import re
                job_match = re.search(r'<jobID>([^<]+)</jobID>', response_text)
                job_id = job_match.group(1) if job_match else 'unknown'
                
                logger.info(f"✅ OTP SMS sent successfully to {normalized_phone}. Job ID: {job_id}")
                
                return {
                    'success': True,
                    'job_id': job_id,
                    'otp_code': otp_code,
                    'message': 'OTP SMS sent successfully via dedicated OTP API',
                    'phone': normalized_phone,
                    'expires_at': datetime.utcnow() + timedelta(minutes=2)
                }
            elif response_text.startswith('00') or (response_text.isdigit() and len(response_text) > 5):
                # Legacy response format
                parts = response_text.split()
                if parts[0] == '00' and len(parts) > 1:
                    job_id = parts[1]
                elif response_text.isdigit():
                    job_id = response_text
                else:
                    job_id = parts[0] if parts else 'unknown'
                
                logger.info(f"✅ OTP SMS sent successfully to {normalized_phone}. Job ID: {job_id}")
                
                return {
                    'success': True,
                    'job_id': job_id,
                    'otp_code': otp_code,
                    'message': 'OTP SMS sent successfully via dedicated OTP API',
                    'phone': normalized_phone,
                    'expires_at': datetime.utcnow() + timedelta(minutes=2)
                }
            else:
                # Error occurred - try to extract error code from XML
                import re
                code_match = re.search(r'<code>(\d+)</code>', response_text)
                error_code = code_match.group(1) if code_match else 'unknown'
                
                error_messages = {
                    '20': 'Message text error or exceeds character limit',
                    '30': 'Invalid credentials or insufficient API access',
                    '40': 'Sender ID (message header) not registered',
                    '50': 'Invalid recipient numbers',
                    '51': 'Sender ID not approved for OTP',
                    '60': 'Invalid job ID',
                    '70': 'Invalid parameters',
                    '80': 'Daily sending limit exceeded',
                    '85': 'Duplicate sending limit exceeded'
                }
                
                error_msg = error_messages.get(error_code, f'Error code: {error_code}')
                logger.error(f"❌ Netgsm OTP error {error_code}: {error_msg}")
                
                return {
                    'success': False,
                    'error': error_msg,
                    'error_code': error_code
                }
                
        except requests.RequestException as e:
            logger.error(f"Network error sending OTP SMS: {str(e)}")
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Unexpected error sending OTP SMS: {str(e)}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }
    
    def send_welcome_sms(self, phone: str, name: str) -> Dict:
        """
        Send welcome message to new user
        
        Args:
            phone: Recipient phone number
            name: User's name
            
        Returns:
            Dict with success status and job_id
        """
        message = (
            f"{name}, domin.ist'e hoş geldiniz! "
            f"Etkinliklere katılmaya ve rezervasyon yapmaya başlayabilirsiniz."
        )
        
        return self.send_sms(phone, message)
    
    def send_booking_confirmation_sms(
        self,
        phone: str,
        event_name: str,
        date: str,
        time: str
    ) -> Dict:
        """
        Send booking confirmation SMS
        
        Args:
            phone: Recipient phone number
            event_name: Name of booked event/venue
            date: Booking date
            time: Booking time
            
        Returns:
            Dict with success status and job_id
        """
        message = (
            f"Rezervasyonunuz onaylandı!\n"
            f"Etkinlik: {event_name}\n"
            f"Tarih: {date}\n"
            f"Saat: {time}\n"
            f"İyi eğlenceler!"
        )
        
        return self.send_sms(phone, message)


# Create global instance
netgsm_service = NetgsmService()
