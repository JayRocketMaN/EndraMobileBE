import json
import re
from typing import Any, Dict


def parse_third_party_qr(qr_payload: str) -> Dict[str, Any]:
    """
    Parses QR string formats: JSON objects, Key-Value pairs, or raw MAC/Serial strings.
    Returns a normalized dictionary containing extracted identifiers and network credentials.
    """
    cleaned = qr_payload.strip()
    result: Dict[str, Any] = {
        "identifier": None,
        "type": "unknown",
        "ip_address": None,
        "port": None,
        "username": None,
        "password": None,
        "channel": None,
        "custom_stream_path": None,
        "protocol": None,
    }

    # 1. Attempt JSON parsing (Full payload QR code)
    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            data = json.loads(cleaned)
            result["ip_address"] = data.get("ip_address") or data.get("ip")
            result["port"] = int(data["port"]) if data.get("port") else None
            result["username"] = data.get("username") or data.get("user")
            result["password"] = data.get("password") or data.get("pass")
            result["channel"] = int(data["channel"]) if data.get("channel") else None
            result["custom_stream_path"] = data.get("custom_stream_path") or data.get("path")
            result["protocol"] = data.get("protocol")

            identifier = data.get("mac_address") or data.get("mac") or data.get("serial_number") or data.get("sn")
            if identifier:
                result["identifier"] = str(identifier).upper()
                result["type"] = "mac" if ":" in str(identifier) or "-" in str(identifier) else "serial"
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # 2. Key-Value string parsing (e.g. "IP=192.168.1.50;USER=admin;PASS=1234;MAC=001A2B3C4D5E")
    if "=" in cleaned:
        kv = dict(item.split("=", 1) for item in cleaned.split(";") if "=" in item)
        
        result["ip_address"] = kv.get("IP") or kv.get("ip")
        result["port"] = int(kv["PORT"]) if "PORT" in kv or "port" in kv else None
        result["username"] = kv.get("USER") or kv.get("username")
        result["password"] = kv.get("PASS") or kv.get("password")
        
        sn = kv.get("SN") or kv.get("SERIAL") or kv.get("s/n")
        mac = kv.get("MAC") or kv.get("mac")

        if mac:
            result["identifier"] = mac.upper()
            result["type"] = "mac"
            return result
        if sn:
            result["identifier"] = sn
            result["type"] = "serial"
            return result

    # 3. Standard Regex MAC Match (e.g. "00:1A:2B:3C:4D:5E" or "00-1A-2B-3C-4D-5E")
    mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', cleaned)
    if mac_match:
        result["identifier"] = mac_match.group(0).upper()
        result["type"] = "mac"
        return result

    # 4. Fallback: Treat raw non-empty string as Serial Number
    if len(cleaned) >= 4:
        result["identifier"] = cleaned
        result["type"] = "serial"

    return result