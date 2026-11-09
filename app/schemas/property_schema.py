import enum
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class PropertyTypeEnum(str, enum.Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    RETAIL = "retail"
    INDUSTRIAL = "industrial"


class CreatePropertySchema(BaseModel):
    property_name: str = Field(..., json_schema_extra={"example": "My Home"})
    full_address: str = Field(..., json_schema_extra={"example": "12 Adeola Way, Lekki Phase 1"})
    property_type: PropertyTypeEnum = Field(PropertyTypeEnum.RESIDENTIAL, json_schema_extra={"example": "residential"})
    
    latitude: Optional[float] = Field(None, json_schema_extra={"example": 6.4474})
    longitude: Optional[float] = Field(None, json_schema_extra={"example": 3.4723})

    model_config = ConfigDict(from_attributes=True)


class PropertyResponseSchema(BaseModel):
    id: int
    user_id: int
    property_name: str
    full_address: str
    property_type: PropertyTypeEnum
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PropertyListResponseSchema(BaseModel):
    properties: List[PropertyResponseSchema]
    total: int

    model_config = ConfigDict(from_attributes=True)


class UpdatePropertySchema(BaseModel):
    property_name: Optional[str] = Field(None, json_schema_extra={"example": "Main Residence"})
    full_address: Optional[str] = Field(None, json_schema_extra={"example": "15 Admiralty Way, Lekki Phase 1"})
    property_type: Optional[PropertyTypeEnum] = Field(None, json_schema_extra={"example": "residential"})
    latitude: Optional[float] = Field(None, json_schema_extra={"example": 6.5244})
    longitude: Optional[float] = Field(None, json_schema_extra={"example": 3.3792})

    model_config = ConfigDict(from_attributes=True)