import argparse
import asyncio
import hashlib
import logging
import random
import uuid
import aiohttp
from copy import deepcopy

logger = logging.getLogger(__name__)

terminalId = str(uuid.uuid1()).replace('-', '')[-33:]
trace_uuid = str(uuid.uuid4()).replace('-', '')
traceId = "PET" + trace_uuid[-16:] + "-" + f"{random.randint(0, 99999):05}"

context = {
    "acceptLanguage": "en",
    "appID": "psybfyca",
    "clientInfo": "API",
    "clientType": "pawsync",
    "clientVersion": "Pawsync 1.0.85",
    "debugMode": 'false',
    "method": "",
    "osInfo": "Android 15",
    "terminalId": terminalId,
    "timeZone": "America/Los_Angeles",  # TODO
    "traceId": traceId,
    "userCountryCode": "US",
}


class PawsyncAuthError(Exception):
    pass


def request_json(data: dict):
    return {"context": context, "data": data}


async def request_post(session: aiohttp.ClientSession, type: str, method: str, data: dict):
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
            'password': hashlib.sha256(password.encode('utf-8')).hexdigest()
        })
    login_json = await r.json()
    if login_json["code"] != 0 or login_json["result"] is None:
        raise PawsyncAuthError(login_json.get("msg", "unknown error"))
    context["accountID"] = login_json["result"]["accountId"]
    context["token"] = login_json["result"]["token"]


class Device:
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
        self.deviceProp = d["deviceProp"]

    async def requestFeed(self, session: aiohttp.ClientSession, amount: int = 12):
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
                "data": {
                    "serving1": amount,
                    "cid": self.deviceId,
                    "configModule": self.configModel
                },
                "method": "manualFeeding",
                "source": "APP"
            }
        }
        logger.debug("Requesting feed for device %s, amount=%s", self.deviceId, amount)
        return await session.post(
            'https://smartapi.pawsync.com/pet/api/deviceManaged/v1/bypassV2',
            json=payload)


async def getDeviceList(session: aiohttp.ClientSession, logger: logging.Logger):
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
