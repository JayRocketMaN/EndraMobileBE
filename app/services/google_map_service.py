import logging
import httpx
from app.core.config import settings

logger = logging.getLogger("endra_maps_service")


class GoogleMapsService:
    GEOCODE_BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

    @staticmethod
    async def reverse_geocode(latitude: float, longitude: float) -> str:
        """
        Converts latitude and longitude coordinates into a human-readable address string
        via the Google Maps Geocoding REST API.
        """
        if not settings.GOOGLE_MAPS_API_KEY:
            logger.warning("GOOGLE_MAPS_API_KEY is not set in environment settings.")
            return f"Lat: {latitude}, Lng: {longitude}"

        params = {
            "latlng": f"{latitude},{longitude}",
            "key": settings.GOOGLE_MAPS_API_KEY,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    GoogleMapsService.GEOCODE_BASE_URL,
                    params=params,
                    timeout=5.0,
                )

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "OK" and data.get("results"):
                    # Get the formatted street address string
                    formatted_address = data["results"][0]["formatted_address"]
                    return formatted_address
                else:
                    logger.warning(
                        f"Google Maps API status: {data.get('status')}"
                    )

            logger.error(
                f"Google Maps API HTTP Error {response.status_code}: {response.text}"
            )
            return f"Lat: {latitude}, Lng: {longitude}"

        except Exception as e:
            logger.error(f"Failed to reverse geocode coordinates: {str(e)}")
            return f"Lat: {latitude}, Lng: {longitude}"