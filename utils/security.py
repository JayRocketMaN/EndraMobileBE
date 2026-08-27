import secrets
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.hardware_model import DiscoveredDevice


def generate_activation_token(prefix: str = "sec_tok") -> str:
    """Generates an opaque, secure hex activation token."""
    return f"{prefix}_{secrets.token_hex(8)}"


async def verify_activation_token(
    db: AsyncSession, 
    activation_token: str
) -> Optional[DiscoveredDevice]:
    """
    Validates the activation token by verifying its existence in the database.
    
    Returns:
        DiscoveredDevice: The staged device matching the activation token.
        None: If the token is invalid or no matching device is found.
    """
    if not activation_token or not isinstance(activation_token, str):
        return None

    query = await db.execute(
        select(DiscoveredDevice).where(
            DiscoveredDevice.activation_token == activation_token
        )
    )
    device = query.scalar_one_or_none()
    return device