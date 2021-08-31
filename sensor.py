"""Platform for sensor integration."""
import logging

from homeassistant.components.sensor import STATE_CLASS_MEASUREMENT, SensorEntity
from homeassistant.const import DEVICE_CLASS_TIMESTAMP
from pysnoo import ActivityState, SessionLevel

from . import SnooHub
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

LEVEL_NAME = {
    SessionLevel.ONLINE: "Online",
    SessionLevel.BASELINE: "Baseline",
    SessionLevel.WEANING_BASELINE: "Weaning Baseline",
    SessionLevel.LEVEL1: "One",
    SessionLevel.LEVEL2: "Two",
    SessionLevel.LEVEL3: "Three",
    SessionLevel.LEVEL4: "Four",
    SessionLevel.NONE: None,
    SessionLevel.PRETIMEOUT: "Pre-Timeout",
    SessionLevel.TIMEOUT: "Timeout",
}

LEVEL_NUMBER = {
    SessionLevel.ONLINE: None,
    SessionLevel.BASELINE: 0.1,
    SessionLevel.WEANING_BASELINE: 0,
    SessionLevel.LEVEL1: 1,
    SessionLevel.LEVEL2: 2,
    SessionLevel.LEVEL3: 3,
    SessionLevel.LEVEL4: 4,
    SessionLevel.NONE: None,
    SessionLevel.PRETIMEOUT: 5,
    SessionLevel.TIMEOUT: None,
}

LEVEL_ICON = {
    SessionLevel.ONLINE: "mdi:bed-empty",
    SessionLevel.BASELINE: "mdi:bed",
    SessionLevel.WEANING_BASELINE: "mdi:bed",
    SessionLevel.LEVEL1: "mdi:numeric-1-circle",
    SessionLevel.LEVEL2: "mdi:numeric-2-circle",
    SessionLevel.LEVEL3: "mdi:numeric-3-circle",
    SessionLevel.LEVEL4: "mdi:numeric-4-circle",
    SessionLevel.NONE: "mdi:bed-empty",
    SessionLevel.PRETIMEOUT: "mdi:alert-decagram",
    SessionLevel.TIMEOUT: "mdi:alert-decagram",
}


async def async_setup_entry(
    hass, config_entry, async_add_entities, discovery_info=None
):
    """Set up the sensor platform."""

    hub = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        [SnooMainSensor(hub), SnooLevelSensor(hub), SnooSessionStartSensor(hub)]
    )


class SnooSensor(SensorEntity):
    """Representation of a Snoo sensor."""

    _as: ActivityState = None
    _hub: SnooHub

    def __init__(self, hub):
        """Initialize the sensor."""
        self._hub = hub

    @property
    def available(self):
        """Return if data is available."""
        return self._connected and self._as is not None

    @property
    def device_info(self):
        """Return device registry information for this entity."""
        return {
            "identifiers": {(DOMAIN, self._hub.device.serial_number)},
            "manufacturer": "Snoo",
            "name": f"{self._hub.baby.baby_name}'s Snoo",
            "sw_version": self._hub.device.firmware_version,
        }

    async def async_added_to_hass(self):
        """Run when this Entity has been added to HA."""

        def as_callback(activity_state):
            self._as = activity_state
            _LOGGER.info(
                "Activity state event '%s': %s",
                activity_state.event.value,
                activity_state,
                extra={"as": activity_state},
            )
            self.schedule_update_ha_state()

        self.async_on_remove(self._hub.pubnub.add_listener(as_callback))

        def conn_callback(is_connected):
            _LOGGER.info("Connected event: %s", is_connected)
            self._connected = is_connected
            self.schedule_update_ha_state()

        self.async_on_remove(self._hub.pubnub.add_listener(conn_callback))

        self._as = (await self._hub.pubnub.history(1))[0]
        self._connected = self._hub.pubnub.is_connected()
        self.async_schedule_update_ha_state()

    @property
    def icon(self):
        """Return the icon of the sensor."""
        if self._as is None:
            return LEVEL_ICON[SessionLevel.NONE]
        return LEVEL_ICON.get(
            self._as.state_machine.state, LEVEL_ICON[SessionLevel.NONE]
        )

    @property
    def should_poll(self):
        """No polling needed."""
        return False


class SnooMainSensor(SnooSensor):
    """Sensor for the Snoo's main state."""

    @property
    def unique_id(self):
        """Return the unique id of the sensor."""
        return self._hub.device.serial_number

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._hub.baby.baby_name}'s Snoo"

    @property
    def state(self):
        """Return the state of the sensor."""
        if self._as is None:
            return None
        return LEVEL_NAME.get(self._as.state_machine.state, None)

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        if self._as is None:
            return {}
        return {
            "raw_state": self._as.state_machine.state.value,
            "left_safety_clip": self._as.left_safety_clip,
            "right_safety_clip": self._as.right_safety_clip,
            "system_state": self._as.system_state,
            "last_event": self._as.event.value,
            "down_transition": self._as.state_machine.down_transition.value,
            "sticky_white_noise": self._as.state_machine.sticky_white_noise,
            "weaning": self._as.state_machine.weaning,
            "up_transition": self._as.state_machine.up_transition.value,
            "hold": self._as.state_machine.hold,
            "audio": self._as.state_machine.audio,
        }


class SnooSessionStartSensor(SnooSensor):
    """Sensor for the session's start time."""

    _attr_device_class = DEVICE_CLASS_TIMESTAMP

    @property
    def unique_id(self):
        """Return the unique id of the sensor."""
        return f"{self._hub.device.serial_number}_session_start"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._hub.baby.baby_name}'s Snoo Session Start"

    @property
    def state(self):
        """Return the state of the sensor."""
        if self._as is None or not self._as.state_machine.is_active_session:
            return None
        return (
            self._as.event_time - self._as.state_machine.since_session_start
        ).isoformat()

    @property
    def icon(self):
        """Return the icon of the sensor."""
        if self._as is None or not self._as.state_machine.state.is_active_level():
            return "mdi:sleep-off"
        return "mdi:sleep"

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        if self._as is None:
            return {}
        return {
            "event_time": self._as.event_time.isoformat(),
            "since_session_start": str(self._as.state_machine.since_session_start),
            "is_active_session": self._as.state_machine.is_active_session,
            "session_id": self._as.state_machine.session_id,
        }


class SnooLevelSensor(SnooSensor):
    """Sensor for the current level in numeric form."""

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_unit_of_measurement = "level"

    @property
    def unique_id(self):
        """Return the unique id of the sensor."""
        return f"{self._hub.device.serial_number}_level"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._hub.baby.baby_name}'s Snoo Level"

    @property
    def state(self):
        """Return the state of the sensor."""
        if self._as is None:
            return None
        return LEVEL_NUMBER.get(self._as.state_machine.state, None)
