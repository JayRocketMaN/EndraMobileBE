from fastapi import APIRouter, Response, Request, status, HTTPException
from pydantic import BaseModel

router = APIRouter(
    prefix="/mock/hikvision",
    tags=["Mock Hikvision Hardware (Dev Only)"]
)

class DeviceActivationPayload(BaseModel):
    password: str

# 1. Mock Device Info Endpoint (ISAPI)
@router.get("/ISAPI/System/deviceInfo")
async def mock_device_info():
    """
    Simulates Hikvision ISAPI Device Information response.
    Returns XML metadata expected by the backend parser.
    """
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <DeviceInfo version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
        <deviceName>MOCK-HIK-CAMERA</deviceName>
        <deviceID>DEV-9988776655</deviceID>
        <model>DS-2CD2143G0-I</model>
        <serialNumber>DS-2CD2143G0-I20261105AAWR9988776655W</serialNumber>
        <macAddress>AA:BB:CC:DD:EE:FF</macAddress>
        <firmwareVersion>V5.5.800</firmwareVersion>
    </DeviceInfo>"""
    return Response(content=xml_content, media_type="application/xml")


# 2. Mock Activation Endpoint (ISAPI)
@router.put("/ISAPI/System/activate")
async def mock_activate_device(payload: DeviceActivationPayload):
    """
    Simulates Hikvision uninitialized device password setup.
    """
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password length does not meet Hikvision security requirements."
        )
    
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <ResponseStatus version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
        <requestURL>/ISAPI/System/activate</requestURL>
        <statusCode>1</statusCode>
        <statusString>OK</statusString>
        <subStatusCode>ok</subStatusCode>
    </ResponseStatus>"""
    return Response(content=xml_content, media_type="application/xml")


# 3. Mock Channel Status / Stream Info
@router.get("/ISAPI/Streaming/channels")
async def mock_streaming_channels():
    """
    Returns active RTSP stream channel metadata.
    """
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <StreamingChannelList version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
        <StreamingChannel>
            <id>101</id>
            <channelName>MainStream</channelName>
            <enabled>true</enabled>
        </StreamingChannel>
    </StreamingChannelList>"""
    return Response(content=xml_content, media_type="application/xml")