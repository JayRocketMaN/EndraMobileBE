import asyncio
import logging
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, Base
from app.models.mobile_user_model import EmergencyDirectory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALL_NIGERIA_DIRECTORY_DATA = [
    # Federal / National
    {"title": "National Emergency Toll-Free Helpline", "primary_number": "112", "scope": "federal", "state_name": "All", "category": "General Emergency"},
    {"title": "Federal Road Safety Corps (FRSC)", "primary_number": "122", "scope": "federal", "state_name": "All", "category": "Road Safety"},
    {"title": "National Emergency Management Agency (NEMA)", "primary_number": "080022556362", "scope": "federal", "state_name": "All", "category": "Disaster Management"},

    # State Data
    {"title": "Abia State Police Command", "primary_number": "08035415408", "scope": "state", "state_name": "Abia State", "category": "Security & Police"},
    {"title": "Adamawa State Police Command", "primary_number": "08089671313", "scope": "state", "state_name": "Adamawa State", "category": "Security & Police"},
    {"title": "Akwa Ibom State Police Command", "primary_number": "08039213071", "scope": "state", "state_name": "Akwa Ibom State", "category": "Security & Police"},
    {"title": "Anambra State Police Command", "primary_number": "07039194332", "scope": "state", "state_name": "Anambra State", "category": "Security & Police"},
    {"title": "Bauchi State Police Command", "primary_number": "08151849417", "scope": "state", "state_name": "Bauchi State", "category": "Security & Police"},
    {"title": "Bayelsa State Police Command", "primary_number": "07034578208", "scope": "state", "state_name": "Bayelsa State", "category": "Security & Police"},
    {"title": "Benue State Police Command", "primary_number": "08066006475", "scope": "state", "state_name": "Benue State", "category": "Security & Police"},
    {"title": "Borno State Police Command", "primary_number": "08068075581", "scope": "state", "state_name": "Borno State", "category": "Security & Police"},
    {"title": "Cross River State Police Command", "primary_number": "08133568456", "scope": "state", "state_name": "Cross River State", "category": "Security & Police"},
    {"title": "Delta State Police Command", "primary_number": "08036684974", "scope": "state", "state_name": "Delta State", "category": "Security & Police"},
    {"title": "Ebonyi State Police Command", "primary_number": "07064515001", "scope": "state", "state_name": "Ebonyi State", "category": "Security & Police"},
    {"title": "Edo State Police Command", "primary_number": "08037646272", "scope": "state", "state_name": "Edo State", "category": "Security & Police"},
    {"title": "Ekiti State Police Command", "primary_number": "08062335577", "scope": "state", "state_name": "Ekiti State", "category": "Security & Police"},
    {"title": "Enugu State Police Command", "primary_number": "08032003702", "scope": "state", "state_name": "Enugu State", "category": "Security & Police"},
    {"title": "FCT Abuja Police Command", "primary_number": "07057337653", "scope": "state", "state_name": "FCT Abuja", "category": "Security & Police"},
    {"title": "Gombe State Police Command", "primary_number": "08150567771", "scope": "state", "state_name": "Gombe State", "category": "Security & Police"},
    {"title": "Imo State Police Command", "primary_number": "08034773600", "scope": "state", "state_name": "Imo State", "category": "Security & Police"},
    {"title": "Jigawa State Police Command", "primary_number": "08075391069", "scope": "state", "state_name": "Jigawa State", "category": "Security & Police"},
    {"title": "Kaduna State Police Command", "primary_number": "08123822284", "scope": "state", "state_name": "Kaduna State", "category": "Security & Police"},
    {"title": "Kano State Police Command", "primary_number": "08032419754", "scope": "state", "state_name": "Kano State", "category": "Security & Police"},
    {"title": "Katsina State Police Command", "primary_number": "08075391255", "scope": "state", "state_name": "Katsina State", "category": "Security & Police"},
    {"title": "Kebbi State Police Command", "primary_number": "08038797644", "scope": "state", "state_name": "Kebbi State", "category": "Security & Police"},
    {"title": "Kogi State Police Command", "primary_number": "08075391335", "scope": "state", "state_name": "Kogi State", "category": "Security & Police"},
    {"title": "Kwara State Police Command", "primary_number": "07032069501", "scope": "state", "state_name": "Kwara State", "category": "Security & Police"},
    {"title": "Lagos State LASEMA", "primary_number": "767", "secondary_number": "112", "scope": "state", "state_name": "Lagos State", "category": "Disaster & Rescue"},
    {"title": "Lagos State Police Command", "primary_number": "08035963919", "scope": "state", "state_name": "Lagos State", "category": "Security & Police"},
    {"title": "Nasarawa State Police Command", "primary_number": "08123821571", "scope": "state", "state_name": "Nasarawa State", "category": "Security & Police"},
    {"title": "Niger State Police Command", "primary_number": "08081777498", "scope": "state", "state_name": "Niger State", "category": "Security & Police"},
    {"title": "Ogun State Police Command", "primary_number": "08032136765", "scope": "state", "state_name": "Ogun State", "category": "Security & Police"},
    {"title": "Ondo State Police Command", "primary_number": "07034313903", "scope": "state", "state_name": "Ondo State", "category": "Security & Police"},
    {"title": "Osun State Police Command", "primary_number": "08075872433", "scope": "state", "state_name": "Osun State", "category": "Security & Police"},
    {"title": "Oyo State Police Command", "primary_number": "08081768614", "scope": "state", "state_name": "Oyo State", "category": "Security & Police"},
    {"title": "Plateau State Police Command", "primary_number": "08126375938", "scope": "state", "state_name": "Plateau State", "category": "Security & Police"},
    {"title": "Rivers State Police Command", "primary_number": "08032003514", "scope": "state", "state_name": "Rivers State", "category": "Security & Police"},
    {"title": "Sokoto State Police Command", "primary_number": "07068848035", "scope": "state", "state_name": "Sokoto State", "category": "Security & Police"},
    {"title": "Taraba State Police Command", "primary_number": "08140089863", "scope": "state", "state_name": "Taraba State", "category": "Security & Police"},
    {"title": "Yobe State Police Command", "primary_number": "07039301585", "scope": "state", "state_name": "Yobe State", "category": "Security & Police"},
    {"title": "Zamfara State Police Command", "primary_number": "08106580123", "scope": "state", "state_name": "Zamfara State", "category": "Security & Police"}
]

async def seed_emergency_directory():
    async with AsyncSessionLocal() as session:
        # Force creation of tables if they are missing
        async with session.bind.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Seeding nationwide emergency directory for all states...")
        for data in ALL_NIGERIA_DIRECTORY_DATA:
            stmt = select(EmergencyDirectory).where(
                EmergencyDirectory.primary_number == data["primary_number"],
                EmergencyDirectory.state_name == data["state_name"]
            )
            result = await session.execute(stmt)
            if not result.scalars().first():
                session.add(EmergencyDirectory(**data))
        await session.commit()
        logger.info("All 36 states and FCT successfully seeded permanently.")

if __name__ == "__main__":
    asyncio.run(seed_emergency_directory())