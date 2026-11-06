import asyncio
from app.core.config import settings
from app.services.google_map_service import GoogleMapsService

async def test_maps_connection():
    print(f"Testing Google Maps API Key...")
    print(f"API Key Prefix: {settings.GOOGLE_MAPS_API_KEY[:6]}...\n")

    # Sample coordinates (e.g., Ikeja, Lagos)
    test_lat = 6.6018
    test_lng = 3.3515

    address = await GoogleMapsService.reverse_geocode(test_lat, test_lng)
    
    print(f"Coordinates: ({test_lat}, {test_lng})")
    print(f"Resolved Address: {address}")

if __name__ == "__main__":
    asyncio.run(test_maps_connection())