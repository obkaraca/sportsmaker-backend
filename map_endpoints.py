"""
Map Endpoints Module
Harita için konum tabanlı endpoint'ler
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Header
from typing import Optional, List
from datetime import datetime
import logging
import math

from auth import get_current_user_optional, get_current_user
from api_response import success_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/map", tags=["Map"])

# Database reference
db = None

def set_database(database):
    """Set database reference from main server"""
    global db
    db = database


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine formula ile iki nokta arasındaki mesafeyi hesapla (km)"""
    R = 6371  # Dünya yarıçapı (km)
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c


@router.get("/events")
async def get_events_on_map(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius: float = 50,  # km
    sport: Optional[str] = None,
    status: str = "active",
    limit: int = 100,
    authorization: Optional[str] = Header(None)  # Optional auth
):
    """Harita üzerinde gösterilecek etkinlikleri getir"""
    try:
        query = {"status": status}
        
        if sport:
            query["sport"] = sport
        
        # Konumu olan etkinlikleri getir
        query["$or"] = [
            {"location": {"$exists": True, "$ne": None}},
            {"latitude": {"$exists": True, "$ne": None}},
        ]
        
        events = await db.events.find(query).limit(limit * 2).to_list(limit * 2)
        
        result = []
        for event in events:
            # Konum bilgisini al
            event_lat = None
            event_lng = None
            
            if event.get("location") and isinstance(event["location"], dict):
                event_lat = event["location"].get("lat")
                event_lng = event["location"].get("lng")
            elif event.get("latitude") and event.get("longitude"):
                event_lat = event["latitude"]
                event_lng = event["longitude"]
            
            if event_lat is None or event_lng is None:
                continue
            
            # Mesafe kontrolü
            distance = None
            if lat is not None and lng is not None:
                distance = calculate_distance(lat, lng, event_lat, event_lng)
                if distance > radius:
                    continue
            
            result.append({
                "id": event.get("id"),
                "title": event.get("title"),
                "sport": event.get("sport"),
                "city": event.get("city"),
                "district": event.get("district"),
                "address": event.get("address"),
                "start_date": event.get("start_date").isoformat() if event.get("start_date") else None,
                "end_date": event.get("end_date").isoformat() if event.get("end_date") else None,
                "current_participants": event.get("current_participants", 0),
                "max_participants": event.get("max_participants"),
                "status": event.get("status"),
                "latitude": event_lat,
                "longitude": event_lng,
                "distance_km": round(distance, 2) if distance else None,
                "organizer_id": event.get("organizer_id"),
            })
        
        # Mesafeye göre sırala
        if lat is not None and lng is not None:
            result.sort(key=lambda x: x.get("distance_km") or float('inf'))
        
        return success_response(data={
            "events": result[:limit],
            "total": len(result),
            "center": {"lat": lat, "lng": lng} if lat and lng else None,
            "radius_km": radius
        })
    except Exception as e:
        logger.error(f"Map events error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/venues")
async def get_venues_on_map(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius: float = 50,  # km
    sport: Optional[str] = None,
    limit: int = 100,
    authorization: Optional[str] = Header(None)  # Optional auth
):
    """Harita üzerinde gösterilecek tesisleri getir"""
    try:
        query = {"is_active": True}
        
        if sport:
            query["sports"] = sport
        
        venues = await db.venues.find(query).limit(limit * 2).to_list(limit * 2)
        
        result = []
        for venue in venues:
            # Konum bilgisini al
            venue_lat = venue.get("latitude")
            venue_lng = venue.get("longitude")
            
            if venue_lat is None or venue_lng is None:
                # Location dict'den dene
                if venue.get("location") and isinstance(venue["location"], dict):
                    venue_lat = venue["location"].get("lat")
                    venue_lng = venue["location"].get("lng")
            
            if venue_lat is None or venue_lng is None:
                continue
            
            # Mesafe kontrolü
            distance = None
            if lat is not None and lng is not None:
                distance = calculate_distance(lat, lng, venue_lat, venue_lng)
                if distance > radius:
                    continue
            
            result.append({
                "id": venue.get("id"),
                "name": venue.get("name"),
                "city": venue.get("city"),
                "district": venue.get("district"),
                "address": venue.get("address"),
                "sports": venue.get("sports", []),
                "rating": venue.get("rating"),
                "review_count": venue.get("review_count", 0),
                "hourly_rate": venue.get("hourly_rate"),
                "latitude": venue_lat,
                "longitude": venue_lng,
                "distance_km": round(distance, 2) if distance else None,
                "image": venue.get("image") or venue.get("images", [None])[0] if venue.get("images") else None,
            })
        
        # Mesafeye göre sırala
        if lat is not None and lng is not None:
            result.sort(key=lambda x: x.get("distance_km") or float('inf'))
        
        return success_response(data={
            "venues": result[:limit],
            "total": len(result),
            "center": {"lat": lat, "lng": lng} if lat and lng else None,
            "radius_km": radius
        })
    except Exception as e:
        logger.error(f"Map venues error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nearby")
async def get_nearby_all(
    lat: float,
    lng: float,
    radius: float = 10,  # km
    current_user: dict = Depends(get_current_user)
):
    """Yakındaki tüm etkinlik ve tesisleri getir"""
    try:
        events_result = await get_events_on_map(lat, lng, radius, None, "active", 50, current_user)
        venues_result = await get_venues_on_map(lat, lng, radius, None, 50, current_user)
        
        return success_response(data={
            "events": events_result["data"]["events"] if events_result.get("data") else [],
            "venues": venues_result["data"]["venues"] if venues_result.get("data") else [],
            "center": {"lat": lat, "lng": lng},
            "radius_km": radius
        })
    except Exception as e:
        logger.error(f"Nearby all error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-location/{item_type}/{item_id}")
async def update_item_location(
    item_type: str,
    item_id: str,
    location_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Etkinlik veya tesis konumunu güncelle"""
    try:
        current_user_id = current_user.get("id")
        lat = location_data.get("latitude") or location_data.get("lat")
        lng = location_data.get("longitude") or location_data.get("lng")
        
        if lat is None or lng is None:
            raise HTTPException(status_code=400, detail="Latitude ve longitude gerekli")
        
        if item_type == "event":
            event = await db.events.find_one({"id": item_id})
            if not event:
                raise HTTPException(status_code=404, detail="Etkinlik bulunamadı")
            
            if event.get("organizer_id") != current_user_id:
                user = await db.users.find_one({"id": current_user_id})
                if user.get("user_type") not in ["admin", "super_admin"]:
                    raise HTTPException(status_code=403, detail="Bu etkinliği düzenleme yetkiniz yok")
            
            await db.events.update_one(
                {"id": item_id},
                {"$set": {
                    "latitude": lat,
                    "longitude": lng,
                    "location": {"lat": lat, "lng": lng}
                }}
            )
            
        elif item_type == "venue":
            venue = await db.venues.find_one({"id": item_id})
            if not venue:
                raise HTTPException(status_code=404, detail="Tesis bulunamadı")
            
            if venue.get("owner_id") != current_user_id:
                user = await db.users.find_one({"id": current_user_id})
                if user.get("user_type") not in ["admin", "super_admin"]:
                    raise HTTPException(status_code=403, detail="Bu tesisi düzenleme yetkiniz yok")
            
            await db.venues.update_one(
                {"id": item_id},
                {"$set": {
                    "latitude": lat,
                    "longitude": lng,
                    "location": {"lat": lat, "lng": lng}
                }}
            )
        else:
            raise HTTPException(status_code=400, detail="Geçersiz item_type. 'event' veya 'venue' olmalı")
        
        return success_response(message="Konum başarıyla güncellendi")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update location error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Türkiye şehir merkezleri
TURKEY_CITY_CENTERS = {
    "İstanbul": {"lat": 41.0082, "lng": 28.9784},
    "Ankara": {"lat": 39.9334, "lng": 32.8597},
    "İzmir": {"lat": 38.4192, "lng": 27.1287},
    "Bursa": {"lat": 40.1885, "lng": 29.0610},
    "Antalya": {"lat": 36.8969, "lng": 30.7133},
    "Adana": {"lat": 37.0000, "lng": 35.3213},
    "Konya": {"lat": 37.8746, "lng": 32.4932},
    "Gaziantep": {"lat": 37.0662, "lng": 37.3833},
    "Mersin": {"lat": 36.8121, "lng": 34.6415},
    "Kayseri": {"lat": 38.7312, "lng": 35.4787},
    "Eskişehir": {"lat": 39.7767, "lng": 30.5206},
    "Samsun": {"lat": 41.2867, "lng": 36.3300},
    "Trabzon": {"lat": 41.0027, "lng": 39.7168},
    "Denizli": {"lat": 37.7765, "lng": 29.0864},
    "Diyarbakır": {"lat": 37.9144, "lng": 40.2306},
}


@router.get("/city-center/{city}")
async def get_city_center(city: str):
    """Şehir merkezinin koordinatlarını getir"""
    try:
        # Tam eşleşme
        if city in TURKEY_CITY_CENTERS:
            return success_response(data=TURKEY_CITY_CENTERS[city])
        
        # Küçük/büyük harf farkı
        for city_name, coords in TURKEY_CITY_CENTERS.items():
            if city_name.lower() == city.lower():
                return success_response(data=coords)
        
        # Varsayılan: İstanbul
        return success_response(
            data=TURKEY_CITY_CENTERS["İstanbul"],
            message=f"'{city}' şehri bulunamadı, İstanbul merkezi döndürüldü"
        )
    except Exception as e:
        logger.error(f"City center error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
