"""
API Response Helpers
Standard response formats for API endpoints
"""
from typing import Any, Optional, Dict, List
from pydantic import BaseModel
from datetime import datetime


class APIResponse(BaseModel):
    """Standart API yanıt formatı"""
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None
    error: Optional[str] = None
    timestamp: datetime = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
    
    def __init__(self, **data):
        if 'timestamp' not in data or data['timestamp'] is None:
            data['timestamp'] = datetime.utcnow()
        super().__init__(**data)


class PaginatedResponse(BaseModel):
    """Pagination ile birlikte standart yanıt"""
    success: bool = True
    data: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
    message: Optional[str] = None
    timestamp: datetime = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
    
    def __init__(self, **data):
        if 'timestamp' not in data or data['timestamp'] is None:
            data['timestamp'] = datetime.utcnow()
        super().__init__(**data)


def success_response(
    data: Any = None,
    message: str = "İşlem başarılı"
) -> Dict:
    """Başarılı yanıt döndür"""
    return {
        "success": True,
        "data": data,
        "message": message,
        "timestamp": datetime.utcnow().isoformat()
    }


def error_response(
    error: str,
    message: str = "İşlem başarısız",
    data: Any = None
) -> Dict:
    """Hata yanıtı döndür"""
    return {
        "success": False,
        "error": error,
        "message": message,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }


def paginated_response(
    data: List[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
    message: str = None
) -> Dict:
    """Sayfalanmış yanıt döndür"""
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    
    return {
        "success": True,
        "data": data,
        "pagination": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        },
        "message": message,
        "timestamp": datetime.utcnow().isoformat()
    }


# HTTP Status Code Constants
class HTTPStatus:
    OK = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    INTERNAL_SERVER_ERROR = 500
    SERVICE_UNAVAILABLE = 503


# Error Messages (Turkish)
class ErrorMessages:
    USER_NOT_FOUND = "Kullanıcı bulunamadı"
    EVENT_NOT_FOUND = "Etkinlik bulunamadı"
    MATCH_NOT_FOUND = "Maç bulunamadı"
    TEAM_NOT_FOUND = "Takım bulunamadı"
    VENUE_NOT_FOUND = "Tesis bulunamadı"
    UNAUTHORIZED = "Bu işlem için yetkiniz yok"
    INVALID_CREDENTIALS = "Geçersiz kimlik bilgileri"
    INVALID_CODE = "Geçersiz doğrulama kodu"
    CODE_EXPIRED = "Doğrulama kodunun süresi dolmuş"
    ALREADY_EXISTS = "Bu kayıt zaten mevcut"
    INVALID_DATA = "Geçersiz veri formatı"
    SERVER_ERROR = "Sunucu hatası oluştu"
    PAYMENT_FAILED = "Ödeme işlemi başarısız"
    QUOTA_EXCEEDED = "Kota aşıldı"


# Success Messages (Turkish)
class SuccessMessages:
    CREATED = "Başarıyla oluşturuldu"
    UPDATED = "Başarıyla güncellendi"
    DELETED = "Başarıyla silindi"
    LOGIN_SUCCESS = "Giriş başarılı"
    LOGOUT_SUCCESS = "Çıkış başarılı"
    CODE_SENT = "Doğrulama kodu gönderildi"
    VERIFIED = "Doğrulama başarılı"
    PAYMENT_SUCCESS = "Ödeme başarılı"
    JOINED = "Başarıyla katıldınız"
    LEFT = "Başarıyla ayrıldınız"
