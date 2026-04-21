"""
Pawsync API client.

The Pawsync app is built on VeSync's platform. All device control goes through
a single 'bypassV2' endpoint that wraps device-specific commands in a common
envelope. Read/list calls use standard REST-style endpoints.

API method names were discovered by patching the APK to bypass certificate
pinning (MyTrustManager in f6/g.smali) and intercepting traffic with mitmproxy.
"""

import argparse
import asyncio
import hashlib
import logging
import random
import time
import uuid
import aiohttp
from copy import deepcopy

logger = logging.getLogger(__name__)

# These are generated once per process. The traceId just needs to be unique
# per request — the server uses it to correlate logs.
terminalId = str(uuid.uuid1()).replace('-', '')[-33:]
trace_uuid = str(uuid.uuid4()).replace('-', '')
traceId = "PET" + trace_uuid[-16:] + "-" + f"{random.randint(0, 99999):05}"

# Every API request includes this context envelope. accountID and token are
# populated after login(). terminalId is overwritten in login() with a stable
# value derived from the email address.
context = {
    "acceptLanguage": "en",
    "appID": "psybfyca",
    "clientInfo": "API",
    "clientType": "pawsync",
    "clientVersion": "Pawsync 1.1.32",
    "debugMode": 'false',
    "method": "",
    "osInfo": "Android 15",
    "terminalId": terminalId,
    "timeZone": "America/Los_Angeles",  # TODO: read from HA config
    "traceId": traceId,
    "userCountryCode": "US",
}


class PawsyncAuthError(Exception):
    pass


def request_json(data: dict):
    """Wrap data in the standard context envelope."""
    return {"context": context, "data": data}


async def request_post(session: aiohttp.ClientSession, type: str, method: str, data: dict):
    """POST to a standard (non-bypass) API endpoint.

    deepcopy is required because the context dict is shared and we mutate
    the 'method' field per request.
    """
    json = deepcopy(request_json(data))
    json['context']['method'] = method
    return await session.post(
        f'https://smartapi.pawsync.com/pet/api/{type}/v1/{method}',
        json=json)


async def login(session: aiohttp.ClientSession, email: str, password: str):
    # Use a stable terminal ID derived from the email so the server reuses the same session
    # across HA restarts. A random ID causes session accumulation that logs out the phone app.
    context["terminalId"] = hashlib.sha256(email.encode('utf-8')).hexdigest()[:32]
    r = await request_post(session, 'userManaged', 'login',
        {
            'email': email,
            # The app SHA256-hashes the password before sending — plain text is never transmitted.
            'password': hashlib.sha256(password.encode('utf-8')).hexdigest()
        })
    login_json = await r.json()
    if login_json["code"] != 0 or login_json["result"] is None:
        raise PawsyncAuthError(login_json.get("msg", "unknown error"))
    # Store credentials in the shared context so all subsequent requests are authenticated.
    context["accountID"] = login_json["result"]["accountId"]
    context["token"] = login_json["result"]["token"]


class Device:
    """Represents a single Pawsync feeder device."""

    def __init__(self, d: dict):
        self.deviceName = d["deviceName"]
        self.deviceImg = d["deviceImg"]
        self.deviceDefaultImg = d["deviceDefaultImg"]
        self.deviceId = d["deviceId"]
        self.connectionType = d["connectionType"]
        self.secondaryCategory = d["secondaryCategory"]
        self.deviceModel = d["deviceModel"]
        self.configModel = d["configModel"]
        self.bizId = d["bizId"]
        self.petId = d["petId"]
        # deviceProp holds all live device state (food levels, switch states, etc.)
        # It gets merged with getPetDeviceStatus data each coordinator poll.
        self.deviceProp = d["deviceProp"]

    async def _send_bypass(self, session: aiohttp.ClientSession, method: str, data: dict | None = None) -> aiohttp.ClientResponse:
        """Send a device command via the bypassV2 envelope.

        bypassV2 is the VeSync platform's generic device control endpoint.
        The actual command goes in payload.method; cid and configModule identify
        which device to target.
        """
        payload = {
            "acceptLanguage": "en",
            "accountID": context["accountID"],
            "appID": context["appID"],
            "appVersion": context["clientVersion"],
            "debugMode": context["debugMode"],
            "method": "bypassV2",
            "phoneBrand": "",
            "phoneOS": context["osInfo"],
            "timeZone": context["timeZone"],
            "token": context["token"],
            "traceId": context["traceId"],
            "userCountryCode": "US",
            "cid": self.deviceId,
            "configModule": self.configModel,
            "payload": {
                "data": {**(data or {}), "cid": self.deviceId, "configModule": self.configModel},
                "method": method,
                "source": "APP"
            }
        }
        return await session.post(
            'https://smartapi.pawsync.com/pet/api/deviceManaged/v1/bypassV2',
            json=payload)

    async def requestFeed(self, session: aiohttp.ClientSession, amount: int = 12):
        """Dispense food. amount is in grams; 11g ≈ 1 portion ≈ 0.4 oz."""
        logger.debug("Requesting feed for device %s, amount=%s", self.deviceId, amount)
        return await self._send_bypass(session, "manualFeeding", {"serving1": amount})

    async def setSwitch(self, session: aiohttp.ClientSession, method: str, data: dict):
        """Generic switch/setting command. Used by switches, time entities, and number entities."""
        return await self._send_bypass(session, method, data)

    async def zeroScale(self, session: aiohttp.ClientSession):
        """Tare the bowl scale to zero at the current weight."""
        return await self._send_bypass(session, "setFeedingBowlToZero")

    async def playMealCall(self, session: aiohttp.ClientSession):
        """Play the meal call audio on the device speaker."""
        return await self._send_bypass(session, "playPetVoice")

    async def resetDesiccant(self, session: aiohttp.ClientSession):
        """Reset the desiccant countdown. maxResetTime is 30 days per getPetFunction."""
        return await self._send_bypass(session, "updatePetDesiccantInfo", {"remainTime": 30})

    async def getStatus(self, session: aiohttp.ClientSession, logger: logging.Logger) -> dict:
        """Fetch real-time device state via getPetDeviceStatus.

        deviceList4Pet returns cached/stale values for bowl weight and desiccant.
        getPetDeviceStatus gives live readings directly from the device, including
        bowlWeight (live scale), desiccantRemainTime, bowlConnected, and switch states.
        The result is merged into deviceProp each coordinator poll.
        """
        response = await self._send_bypass(session, "getPetDeviceStatus")
        result = await response.json()
        if result.get("code") != 0:
            logger.error("getPetDeviceStatus failed for %s: %s", self.deviceId, result)
            return {}
        inner = (result.get("result") or {})
        if inner.get("code") != 0:
            logger.error("getPetDeviceStatus inner error for %s: %s", self.deviceId, inner)
            return {}
        return inner.get("result") or {}


async def getPetLogList(session: aiohttp.ClientSession, device_id: str, logger: logging.Logger, page_size: int = 50) -> list:
    """Fetch feeding activity logs for the last 24 hours.

    Log types seen in the wild: planFeeding (scheduled), manualFeeding (extra meal),
    takeFood (pet eating from bowl). Each entry has a timestamp and value in grams.
    """
    end_ts = int(time.time())
    start_ts = end_ts - 86400  # last 24 hours
    r = await request_post(session, 'petDeviceManaged', 'getPetLogList', {
        "deviceId": device_id,
        "endTimestamp": end_ts,
        "objectType": 0,
        "pageSize": page_size,
        "startTimestamp": start_ts,
    })
    result = await r.json()
    if result["code"] != 0 or result["result"] is None:
        logger.error("getPetLogList failed for %s: %s", device_id, result)
        return []
    return result["result"].get("petLogList", [])


async def getPetList(session: aiohttp.ClientSession, logger: logging.Logger) -> list:
    """Fetch pet profiles linked to this account.

    Note: uses 'petManaged' service path, NOT 'petDeviceManaged' — easy to confuse.
    Returns weight, daily intake, food target, avatar URL, etc.
    """
    r = await request_post(session, 'petManaged', 'getPetList', {})
    result = await r.json()
    if result["code"] != 0 or result["result"] is None:
        logger.error("getPetList failed: %s", result)
        return []
    return result["result"].get("petList", [])


async def getFirmwareUpdateInfo(session: aiohttp.ClientSession, device_ids: list[str], logger: logging.Logger) -> dict:
    """Check for available firmware updates across all devices.

    Returns a dict keyed by deviceId. Each value is a list of firmware components
    (mainFw, mcuFw) with upgradeLevel > 0 indicating an update is available.
    """
    r = await request_post(session, 'deviceManaged', 'getFirmwareUpdateInfoList', {
        "deviceIdList": device_ids,
    })
    result = await r.json()
    if result["code"] != 0 or result["result"] is None:
        logger.error("getFirmwareUpdateInfoList failed: %s", result)
        return {}
    out = {}
    for item in result["result"].get("wifiInfoList", []):
        out[item["deviceId"]] = item.get("firmUpdateInfos", [])
    return out


async def getDeviceList(session: aiohttp.ClientSession, logger: logging.Logger):
    """Fetch all feeders linked to this account."""
    r = await request_post(session, 'deviceManaged', 'deviceList4Pet', {})
    devices_json = await r.json()
    if devices_json["code"] != 0 or devices_json["result"] is None:
        logger.error("getDeviceList failed: %s", devices_json)
        return None
    return [Device(d) for d in devices_json["result"]["list"]]


if __name__ == '__main__':
    parser = argparse.ArgumentParser("pawsync")
    parser.add_argument("email", type=str)
    parser.add_argument("password", type=str)
    parser.add_argument("--feed", action='store_true')
    args = parser.parse_args()

    async def impl():
        session = aiohttp.ClientSession()
        try:
            await login(session, args.email, args.password)
        except PawsyncAuthError as e:
            print(f"Authentication failed: {e}")
            await session.close()
            return

        devices = await getDeviceList(session, logger)
        if devices is None:
            await session.close()
            return

        for d in devices:
            print(vars(d))

        if args.feed:
            f = await devices[0].requestFeed(session)
            print(await f.json())

        await session.close()

    asyncio.run(impl())
