from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.property_model import Property
from app.models.mobile_user_model import MobileUser
from app.schemas.property_schema import (
    CreatePropertySchema,
    PropertyResponseSchema,
    PropertyListResponseSchema,
)

router = APIRouter(prefix="/api/v1/mobile/properties", tags=["User Properties"])


@router.post("", response_model=PropertyResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_user_property(
    payload: CreatePropertySchema,
    db: AsyncSession = Depends(get_db)
):
    """
    Registers a new home, commercial, retail, or industrial location 
    along with optional pinned GPS coordinates for emergency dispatch.
    """
    # Verify mobile user exists
    user_query = select(MobileUser).where(MobileUser.id == payload.user_id)
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    new_property = Property(
        user_id=payload.user_id,
        property_name=payload.property_name,
        full_address=payload.full_address,
        property_type=payload.property_type,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )

    db.add(new_property)
    await db.commit()
    await db.refresh(new_property)

    return new_property


@router.get("/user/{user_id}", response_model=PropertyListResponseSchema)
async def get_user_properties(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieves all registered properties for a specific user.
    """
    query = select(Property).where(Property.user_id == user_id)
    result = await db.execute(query)
    properties = result.scalars().all()

    return PropertyListResponseSchema(
        properties=properties,
        total=len(properties)
    )