from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends, Header, Request
from fastapi.security import OAuth2PasswordBearer
import os

# Placeholder for OAuth - will be implemented with actual keys
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kimlik doğrulanamadı",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(token: str = Depends(oauth2_scheme), request: Request = None):
    payload = decode_token(token)
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kimlik doğrulanamadı"
        )
    
    # Token'da user_type varsa kullan, yoksa veritabanından al
    user_type = payload.get("user_type")
    
    if not user_type and request and hasattr(request.app.state, 'db'):
        db = request.app.state.db
        user = await db.users.find_one({"id": user_id})
        if user:
            user_type = user.get("user_type", "player")
    
    return {"id": user_id, "user_type": user_type or "player"}

# Alias for compatibility
get_current_active_user = get_current_user

async def get_current_user_optional(authorization: Optional[str] = Header(None)):
    """Get current user if authenticated, otherwise return None"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    try:
        token = authorization.replace("Bearer ", "")
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        return user_id
    except:
        return None

# Placeholder functions for OAuth integration
# These will be implemented when user provides OAuth credentials

def init_google_oauth():
    """Initialize Google OAuth - requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET"""
    # Will be implemented with actual credentials
    pass

def init_facebook_oauth():
    """Initialize Facebook OAuth - requires FACEBOOK_APP_ID and FACEBOOK_APP_SECRET"""
    # Will be implemented with actual credentials
    pass
