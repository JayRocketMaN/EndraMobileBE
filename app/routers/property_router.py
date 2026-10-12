from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.property_model import Property
from app.models.mobile_user_model import MobileUser
from app.schemas.property_schema import (
    CreatePropertySchema,
    UpdatePropertySchema,
    PropertyResponseSchema,
    PropertyListResponseSchema,
)

router = APIRouter(prefix="/api/v1/mobile/properties", tags=["User Properties"])


@router.post("", response_model=PropertyResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_user_property(
    payload: CreatePropertySchema,
    current_user: MobileUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Registers a new home, commercial, retail, or industrial location 
    for the authenticated user via the X-User-ID header.
    """
    new_property = Property(
        user_id=current_user.id,  # Automatically assigned from header authentication
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


@router.get("", response_model=PropertyListResponseSchema)
async def get_user_properties(
    current_user: MobileUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieves all registered properties belonging to the authenticated user.
    """
    query = select(Property).where(Property.user_id == current_user.id)
    result = await db.execute(query)
    properties = result.scalars().all()

    return PropertyListResponseSchema(
        properties=properties,
        total=len(properties)
    )


@router.put("/{property_id}", response_model=PropertyResponseSchema)
async def update_user_property(
    property_id: int,
    payload: UpdatePropertySchema,
    current_user: MobileUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing property by its ID for the authenticated user.
    Only updates fields that are provided in the payload.
    """
    # 1. Fetch the property ensuring it belongs to the current user
    result = await db.execute(
        select(Property).where(
            Property.id == property_id,
            Property.user_id == current_user.id
        )
    )
    property_item = result.scalar_one_or_none()

    if not property_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found or unauthorized."
        )

    # 2. Apply updates selectively (partial update support)
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(property_item, key, value)

    await db.commit()
    await db.refresh(property_item)

    return property_item


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_property(
    property_id: int,
    current_user: MobileUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete an existing property by its ID for the authenticated user.
    """
    
    result = await db.execute(
        select(Property).where(
            Property.id == property_id,
            Property.user_id == current_user.id
        )
    )
    property_item = result.scalar_one_or_none()

    if not property_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found or unauthorized."
        )

  
    await db.delete(property_item)
    await db.commit()

    return None