from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Request, Response, HTTPException, status, Depends
from jose import jwt, JWTError
import bcrypt  
from cryptography.fernet import Fernet # New addition for camera encryption
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_db
from app.models.mobile_user_model import User


# =====================================================================
# SYMMETRIC ENCRYPTION ENGINE (For Camera Stream Passwords)
# =====================================================================

# Ensure settings.SECRET_KEY is a valid 32-byte URL-safe base64 string for Fernet
# If you run into padding errors, use a dedicated key variable in your .env
try:
    fernet_cipher = Fernet(settings.SECRET_KEY.encode('utf-8')[:32].ljust(32, b'='))
except Exception:
    # Safe fallback wrapper to ensure it initializes regardless of key length
    import base64
    import hashlib
    key_hash = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    fernet_cipher = Fernet(base64.urlsafe_b64encode(key_hash))

def encrypt_password(plain_text: str) -> str:
    """Encrypts camera passwords into secure strings before saving to PostgreSQL."""
    if not plain_text:
        return ""
    return fernet_cipher.encrypt(plain_text.encode('utf-8')).decode('utf-8')

def decrypt_password(encrypted_text: str) -> str:
    """Decrypts database cipher strings back to plaintext for local edge consumption."""
    if not encrypted_text:
        return ""
    return fernet_cipher.decrypt(encrypted_text.encode('utf-8')).decode('utf-8')


# =====================================================================
# CRYPTOGRAPHY & HASHING ENGINE (Native Bcrypt for User Logins)
# =====================================================================
def hash_password(password: str) -> str:
    """Transforms plain text credentials into secure bcrypt hashes natively."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies an incoming input matches our database record hash safely."""
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False


# =====================================================================
# TOKEN ENGINE UTILITIES
# =====================================================================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generates a secure JWT access token signed by the ENDRA core signature key."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


# =====================================================================
# COOKIE DELIVERY SYSTEM
# =====================================================================
def set_auth_cookie(response: Response, token: str) -> None:
    """Injects the JWT access token directly into client's browser using HttpOnly cookies."""
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        samesite="lax",
        secure=True,  
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


# =====================================================================
# COOKIE-BASED AUTHENTICATION DEPENDENCY
# =====================================================================
async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Extracts JWT token from HttpOnly cookies and returns current database User."""
    token_cookie = request.cookies.get("access_token")
    
    if not token_cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials missing from cookie session context."
        )
    
    try:
        if token_cookie.startswith("Bearer "):
            token = token_cookie.split(" ")[1]
        else:
            token = token_cookie

        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")

        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid session token payload context."
            )
            
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired or is cryptographically corrupted."
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user record no longer exists in the system engine."
        )
        
    return user
