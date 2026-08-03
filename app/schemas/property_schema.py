import enum
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class PropertyTypeEnum(str, enum.Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    RETAIL = "retail"
    INDUSTRIAL = "industrial"


class CreatePropertySchema(BaseModel):
    user_id: int = Field(..., json_schema_extra={"example": 1})
    property_name: str = Field(..., json_schema_extra={"example": "My Home"})
    full_address: str = Field(..., json_schema_extra={"example": "12 Adeola Way, Lekki Phase 1"})
    property_type: PropertyTypeEnum = Field(PropertyTypeEnum.RESIDENTIAL, json_schema_extra={"example": "residential"})
    
    latitude: Optional[float] = Field(None, json_schema_extra={"example": 6.4474})
    longitude: Optional[float] = Field(None, json_schema_extra={"example": 3.4723})


class PropertyResponseSchema(BaseModel):
    id: int
    user_id: int
    property_name: str
    full_address: str
    property_type: PropertyTypeEnum
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PropertyListResponseSchema(BaseModel):
    properties: List[PropertyResponseSchema]
    total: int