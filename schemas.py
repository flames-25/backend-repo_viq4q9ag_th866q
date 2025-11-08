"""
Database Schemas for Smart Waste Finder

Each Pydantic model corresponds to a MongoDB collection (lowercased class name).
Use these for validation and to keep a consistent shape across the app.
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, HttpUrl, EmailStr

# User profiles (future use)
class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    city: Optional[str] = Field(None, description="Home city")
    is_active: bool = Field(True, description="Account status")

StationType = Literal["dump", "recycling", "ewaste", "compost", "hazmat"]

class Station(BaseModel):
    """
    Waste station locations with geocoordinates and metadata
    Collection: "station"
    """
    name: str = Field(..., description="Station name")
    type: StationType = Field(..., description="Station category")
    address: str = Field(..., description="Street address")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    rating: Optional[float] = Field(None, ge=0, le=5)
    review_count: Optional[int] = Field(0, ge=0)
    phone: Optional[str] = None
    website: Optional[HttpUrl] = None
    hours: Optional[str] = Field(None, description="Open hours summary")
    services: Optional[List[str]] = Field(default_factory=list)

class Recommendation(BaseModel):
    """
    Recommendation items shown in the drawer
    Collection: "recommendation"
    """
    title: str
    description: Optional[str] = None
    image: Optional[HttpUrl] = None
    station_id: Optional[str] = Field(None, description="Related station id")
    tags: List[str] = Field(default_factory=list)

class RecommendationFeedback(BaseModel):
    """
    Quick feedback on recommendations (thumbs up/down)
    Collection: "recommendationfeedback"
    """
    item_id: str
    action: Literal["up", "down"]
    reason: Optional[str] = None
    user_id: Optional[str] = None
