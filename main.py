import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Station, Recommendation, RecommendationFeedback, User

app = FastAPI(title="Smart Waste Finder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Helpers
class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        try:
            return str(ObjectId(str(v)))
        except Exception:
            return str(v)

def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    # Convert any nested ObjectIds
    for k, v in list(doc.items()):
        if isinstance(v, ObjectId):
            doc[k] = str(v)
    return doc


# Basic routes
@app.get("/")
def read_root():
    return {"message": "Smart Waste Finder backend is running"}

@app.get("/health")
def health():
    return {"status": "ok"}


# Database test and info
@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response


# Schema endpoint for viewers/tools
class SchemaResponse(BaseModel):
    name: str
    collection: str
    schema: dict

@app.get("/schema", response_model=List[SchemaResponse])
def get_schema():
    items: List[SchemaResponse] = []
    for model in [User, Station, Recommendation, RecommendationFeedback]:
        try:
            schema = model.model_json_schema()
        except Exception:
            schema = {}
        items.append(
            SchemaResponse(
                name=model.__name__,
                collection=model.__name__.lower(),
                schema=schema,
            )
        )
    return items


# Stations API
@app.get("/api/stations")
def list_stations(
    type: Optional[str] = Query(default=None, description="Filter by station type"),
    query: Optional[str] = Query(default=None, description="Search by name or address"),
    limit: int = Query(default=50, ge=1, le=200),
    lat: Optional[float] = Query(default=None),
    lng: Optional[float] = Query(default=None),
    radius_km: Optional[float] = Query(default=None, description="Radius filter in km (approx, simple bbox)")
):
    filter_dict: Dict[str, Any] = {}
    if type:
        filter_dict["type"] = type
    if query:
        # Simple regex search on name/address
        filter_dict["$or"] = [
            {"name": {"$regex": query, "$options": "i"}},
            {"address": {"$regex": query, "$options": "i"}},
        ]
    # If lat/lng & radius provided, do bbox filter (not geospatial index)
    if lat is not None and lng is not None and radius_km:
        # very rough degrees conversion
        dlat = radius_km / 111.0
        dlng = radius_km / 111.0
        filter_dict.update({
            "latitude": {"$gte": lat - dlat, "$lte": lat + dlat},
            "longitude": {"$gte": lng - dlng, "$lte": lng + dlng},
        })

    docs = get_documents("station", filter_dict, limit)
    return [serialize_doc(d) for d in docs]


@app.post("/api/stations", status_code=201)
def create_station(payload: Station):
    try:
        inserted_id = create_document("station", payload)
        doc = db["station"].find_one({"_id": ObjectId(inserted_id)})
        return serialize_doc(doc)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/stations/nearby")
def nearby_stations(
    lat: float = Query(...),
    lng: float = Query(...),
    limit: int = Query(default=10, ge=1, le=100)
):
    # Rough nearest by sorting on squared distance (no geo index)
    docs = get_documents("station", {}, None)
    def dist2(d):
        try:
            return (float(d.get("latitude", 0)) - lat) ** 2 + (float(d.get("longitude", 0)) - lng) ** 2
        except Exception:
            return 1e12
    sorted_docs = sorted(docs, key=dist2)[:limit]
    return [serialize_doc(d) for d in sorted_docs]


# Recommendations API
@app.get("/api/recommendations")
def list_recommendations(limit: int = Query(default=20, ge=1, le=100)):
    docs = get_documents("recommendation", {}, limit)
    return [serialize_doc(d) for d in docs]


@app.post("/api/recommendations/feedback", status_code=201)
def submit_feedback(payload: RecommendationFeedback):
    try:
        inserted_id = create_document("recommendationfeedback", payload)
        doc = db["recommendationfeedback"].find_one({"_id": ObjectId(inserted_id)})
        return serialize_doc(doc)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Simple seed endpoint (optional utility)
class SeedResult(BaseModel):
    inserted: int

@app.post("/api/seed", response_model=SeedResult)
def seed_sample_data():
    """Seed a few stations and recommendations if collections are empty"""
    inserted = 0
    if db["station"].count_documents({}) == 0:
        samples = [
            Station(name="GreenCycle Center", type="recycling", address="123 Elm St", latitude=37.7749, longitude=-122.4194, rating=4.7, review_count=128, services=["plastic", "paper", "metal"]),
            Station(name="City Dump Yard", type="dump", address="45 Industrial Rd", latitude=37.78, longitude=-122.41, rating=4.1, review_count=63, services=["bulk", "construction"]),
            Station(name="Tech E-Waste Depot", type="ewaste", address="9 Silicon Ave", latitude=37.76, longitude=-122.42, rating=4.8, review_count=204, services=["electronics", "batteries"]),
        ]
        for s in samples:
            create_document("station", s)
            inserted += 1
    if db["recommendation"].count_documents({}) == 0:
        recs = [
            Recommendation(title="Recycle plastics today", description="Drop-off at GreenCycle before 6pm", tags=["recycling", "plastic"]),
            Recommendation(title="Dispose e-waste safely", description="Tech Depot accepts laptops", tags=["ewaste"]),
        ]
        for r in recs:
            create_document("recommendation", r)
            inserted += 1
    return SeedResult(inserted=inserted)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
