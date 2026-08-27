from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.incident_model import Incident


async def find_existing_incident(
    db: AsyncSession,
    camera_id: str,
    incident_type: str,
    time_window_seconds: int = 60
) -> Incident | None:
    """
    Prevents duplicate incident creation across sequential AI frames.
    Groups events on the same camera & incident type within a sliding time window.
    """
    cutoff_time = datetime.utcnow() - timedelta(seconds=time_window_seconds)
    
    query = (
        select(Incident)
        .where(
            Incident.camera_id == camera_id,
            Incident.incident_type == incident_type,
            Incident.timestamp >= cutoff_time
        )
        .order_by(Incident.timestamp.desc())
    )
    
    result = await db.execute(query)
    return result.scalars().first()