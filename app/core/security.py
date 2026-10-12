from typing import Optional
from fastapi import Header, HTTPException, status, Depends
import bcrypt  
from cryptography.fernet import Fernet 
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_db
from app.models.mobile_user_model import MobileUser

# =====================================================================
# SYMMETRIC ENCRYPTION ENGINE (For Camera Stream Passwords)
# =====================================================================
try:
    fernet_cipher = Fernet(settings.SECRET_KEY.encode('utf-8')[:32].ljust(32, b'='))
except Exception:
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
# SIMPLE USER_ID AUTHENTICATION DEPENDENCY
# =====================================================================
async def get_current_user(
    x_user_id: Optional[int] = Header(None, description="Pass the user ID directly for identification"),
    db: AsyncSession = Depends(get_db)
) -> MobileUser:
    """
    Identifies the user directly via the X-User-ID header instead of JWT tokens.
    """
    if x_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-ID header missing from request context."
        )

    # Asynchronously search PostgreSQL for the user by ID
    result = await db.execute(
        select(MobileUser).where(MobileUser.id == x_user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User profile corresponding to the provided ID does not exist."
        )
        
    return user