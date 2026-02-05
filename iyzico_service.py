import iyzipay
import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IyzicoService:
    def __init__(self):
        # Get credentials from environment
        self.api_key = os.getenv('IYZICO_API_KEY', '')
        self.secret_key = os.getenv('IYZICO_SECRET_KEY', '')
        base_url_env = os.getenv('IYZICO_BASE_URL', 'https://sandbox-api.iyzipay.com')
        # Fix URL format for iyzipay library
        if base_url_env.startswith('https://'):
            self.base_url = base_url_env.replace('https://', '')
        else:
            self.base_url = base_url_env
        
        # Create iyzipay options
        self.options = {
            'api_key': self.api_key,
            'secret_key': self.secret_key,
            'base_url': self.base_url
        }
        
        logger.info(f"IyzicoService initialized with base_url: {self.base_url}")
    
    def _validate_credentials(self):
        """Check if API credentials are configured"""
        if not self.api_key or not self.secret_key:
            raise ValueError("Iyzico API credentials not configured. Please set IYZICO_API_KEY and IYZICO_SECRET_KEY in .env file")
    
    def initialize_checkout_form(
        self,
        user: Dict[str, Any],
        amount: float,
        related_type: str,
        related_id: str,
        related_name: str,
        callback_url: str
    ) -> Dict[str, Any]:
        """
        Initialize iyzico checkout form for 3D Secure payment
        
        Args:
            user: User dictionary with id, email, full_name, phone_number, etc.
            amount: Payment amount in TRY
            related_type: 'event' or 'reservation'
            related_id: ID of event or reservation
            related_name: Name/title of event or service
            callback_url: URL for payment callback
        
        Returns:
            Dictionary with token and payment page URL
        """
        self._validate_credentials()
        
        conversation_id = str(uuid.uuid4())
        
        # Prepare buyer information
        name_parts = (user.get('full_name') or 'Customer User').split(' ', 1)
        buyer_name = name_parts[0]
        buyer_surname = name_parts[1] if len(name_parts) > 1 else 'User'
        
        request = {
            'locale': 'tr',
            'conversationId': conversation_id,
            'price': str(amount),
            'paidPrice': str(amount),
            'currency': 'TRY',
            'basketId': f"{related_type}_{related_id}",
            'paymentGroup': 'PRODUCT',
            'callbackUrl': callback_url,
            'enabledInstallments': ['1', '2', '3', '6', '9', '12'],
            'buyer': {
                'id': str(user.get('id')),
                'name': buyer_name,
                'surname': buyer_surname,
                'gsmNumber': str(user.get('phone_number') or '+905000000000'),
                'email': str(user.get('email') or 'user@example.com'),
                'identityNumber': str(user.get('tc_kimlik') or '11111111111'),
                'lastLoginDate': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                'registrationDate': user.get('created_at', datetime.utcnow()).strftime('%Y-%m-%d %H:%M:%S') if isinstance(user.get('created_at'), datetime) else '2024-01-01 00:00:00',
                'registrationAddress': 'Address',
                'ip': '85.34.78.112',
                'city': 'Istanbul',
                'country': 'Turkey',
                'zipCode': '34732'
            },
            'shippingAddress': {
                'contactName': f"{buyer_name} {buyer_surname}",
                'city': 'Istanbul',
                'country': 'Turkey',
                'address': 'Shipping Address',
                'zipCode': '34732'
            },
            'billingAddress': {
                'contactName': f"{buyer_name} {buyer_surname}",
                'city': 'Istanbul',
                'country': 'Turkey',
                'address': 'Billing Address',
                'zipCode': '34732'
            },
            'basketItems': [
                {
                    'id': f"item_{related_id}",
                    'name': related_name[:128],  # iyzico has 128 char limit
                    'category1': related_type.capitalize(),
                    'category2': 'Sports',
                    'itemType': 'VIRTUAL',
                    'price': str(amount)
                }
            ]
        }
        
        logger.info(f"💳 İyzico ödeme başlatılıyor:")
        logger.info(f"  - Tutar: {amount} TRY")
        logger.info(f"  - Price field: {request['price']}")
        logger.info(f"  - BasketItems[0] price: {request['basketItems'][0]['price']}")
        
        checkout_form_initialize = iyzipay.CheckoutFormInitialize().create(request, self.options)
        
        result = checkout_form_initialize.read().decode('utf-8')
        
        # Parse response
        import json
        response_data = json.loads(result)
        
        logger.info(f"🔍 İyzico Response Keys: {list(response_data.keys())}")
        logger.info(f"🔍 paymentPageUrl: {response_data.get('paymentPageUrl')}")
        
        if response_data.get('status') == 'success':
            logger.info(f"Checkout form initialized successfully. Token: {response_data.get('token')}")
            
            # İyzico'dan gelen tüm URL key'lerini kontrol et
            payment_url = (response_data.get('paymentPageUrl') or 
                          response_data.get('payment_page_url') or
                          response_data.get('paymentUrl'))
            
            logger.info(f"✅ Payment URL: {payment_url}")
            
            return {
                'status': 'success',
                'token': response_data.get('token'),
                'checkout_form_content': response_data.get('checkoutFormContent'),
                'payment_page_url': payment_url,  # Snake case - backend/frontend uyumu için
                'paymentPageUrl': payment_url,    # CamelCase - eski uyumluluk için
                'conversationId': conversation_id
            }
        else:
            error_msg = response_data.get('errorMessage', 'Unknown error')
            logger.error(f"Checkout form initialization failed: {error_msg}")
            raise Exception(f"Payment initialization failed: {error_msg}")
    
    def retrieve_checkout_form_result(self, token: str) -> Dict[str, Any]:
        """
        Retrieve payment result after 3D Secure completion
        
        Args:
            token: Payment token from callback
        
        Returns:
            Payment result dictionary
        """
        self._validate_credentials()
        
        request = {
            'locale': 'tr',
            'conversationId': str(uuid.uuid4()),
            'token': token
        }
        
        logger.info(f"Retrieving checkout form result for token: {token}")
        
        checkout_form_result = iyzipay.CheckoutForm().retrieve(request, self.options)
        
        result = checkout_form_result.read().decode('utf-8')
        
        import json
        response_data = json.loads(result)
        
        if response_data.get('status') == 'success':
            logger.info(f"Payment successful. Payment ID: {response_data.get('paymentId')}")
        else:
            error_msg = response_data.get('errorMessage', 'Bilinmeyen hata')
            logger.error(f"Payment failed: {error_msg}")
            
            # Kullanıcı dostu hata mesajları
            user_friendly_errors = {
                'Üye işyeri kategori kodu hatalı': 'Ödeme sistemi yapılandırması devam ediyor. Lütfen daha sonra tekrar deneyin veya yönetici ile iletişime geçin.',
                'Kart numarası geçersiz': 'Girdiğiniz kart numarası geçersiz. Lütfen kontrol edin.',
                'Geçersiz CVC': 'Güvenlik kodu (CVC) hatalı.',
                'Yetersiz bakiye': 'Kartınızda yeterli bakiye bulunmuyor.',
                'Kart limiti yetersiz': 'Kart limitiniz yetersiz.',
                'İşlem reddedildi': 'Bankanız bu işlemi reddetti. Lütfen bankanızla iletişime geçin.',
                '3D Secure doğrulama başarısız': '3D Secure doğrulaması başarısız. Lütfen tekrar deneyin.',
            }
            
            # Hata mesajını kullanıcı dostu hale getir
            for key, friendly_msg in user_friendly_errors.items():
                if key.lower() in error_msg.lower():
                    response_data['userFriendlyError'] = friendly_msg
                    break
            else:
                response_data['userFriendlyError'] = f'Ödeme işlemi başarısız: {error_msg}'
        
        return response_data
    
    def retrieve_payment(self, token: str) -> Dict[str, Any]:
        """
        Alias for retrieve_checkout_form_result
        """
        return self.retrieve_checkout_form_result(token)
    
    def refund_payment(self, payment_id: str, amount: float, ip: str = '85.34.78.112') -> Dict[str, Any]:
        """
        Refund a payment
        
        Args:
            payment_id: iyzico payment ID
            amount: Amount to refund
            ip: User IP address
        
        Returns:
            Refund result dictionary
        """
        self._validate_credentials()
        
        request = {
            'locale': 'tr',
            'conversationId': str(uuid.uuid4()),
            'paymentId': payment_id,
            'price': str(amount),
            'ip': ip,
            'currency': iyzipay.CURRENCY_TRY
        }
        
        logger.info(f"Refunding payment {payment_id}, amount: {amount} TRY")
        
        refund = iyzipay.Refund().create(request, self.options)
        
        result = refund.read().decode('utf-8')
        
        import json
        response_data = json.loads(result)
        
        if response_data.get('status') == 'success':
            logger.info(f"Refund successful for payment {payment_id}")
        else:
            logger.error(f"Refund failed: {response_data.get('errorMessage')}")
        
        return response_data
    
    def cancel_payment(self, payment_id: str, ip: str = '85.34.78.112') -> Dict[str, Any]:
        """
        Cancel a payment (same day cancellation)
        
        Args:
            payment_id: iyzico payment ID
            ip: User IP address
        
        Returns:
            Cancellation result dictionary
        """
        self._validate_credentials()
        
        request = {
            'locale': 'tr',
            'conversationId': str(uuid.uuid4()),
            'paymentId': payment_id,
            'ip': ip
        }
        
        logger.info(f"Cancelling payment {payment_id}")
        
        cancel = iyzipay.Cancel().create(request, self.options)
        
        result = cancel.read().decode('utf-8')
        
        import json
        response_data = json.loads(result)
        
        if response_data.get('status') == 'success':
            logger.info(f"Payment cancelled successfully: {payment_id}")
        else:
            logger.error(f"Payment cancellation failed: {response_data.get('errorMessage')}")
        
        return response_data

# Global instance
iyzico_service = IyzicoService()
