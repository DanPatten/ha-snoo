"""The Snoo integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import pysnoo2

from .const import DOMAIN

PLATFORMS = ["sensor"]

_LOGGER = logging.getLogger(__name__)


class SnooHub:
    """Hub containing of the Snoo API objects."""

    def __init__(self, auth, snoo, device, baby, pubnub):
        """Initialize the hub."""
        self.auth = auth
        self.snoo = snoo
        self.device = device
        self.baby = baby
        self.pubnub = pubnub
        self.is_unloading = False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Snoo from a config entry."""
    auth = pysnoo2.SnooAuthSession(entry.data["username"], entry.data["password"])
    await auth.fetch_token()

    snoo = pysnoo2.Snoo(auth)

    devices = await snoo.get_devices()

    # Snoo's app only allows one device per account...
    if len(devices) != 1:
        return True

    device = devices[0]

    # ... because who would have multiple devices and only one baby.
    baby = await snoo.get_baby()

    pubnubToken = await snoo.pubnub_auth()
    pubnub = pysnoo2.SnooPubNub(
        pubnubToken,
        snoo.pubnub_auth,
        device.serial_number,
        f"pn-homeassistant-{device.serial_number}",
    )

    await pubnub.subscribe_and_await_connect()

    hub = SnooHub(auth, snoo, device, baby, pubnub)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hub = hass.data[DOMAIN].pop(entry.entry_id)
        if hub:
            hub.is_unloading = True
            await hub.pubnub.unsubscribe_and_await_disconnect()

    return unload_ok
