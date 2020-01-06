"""MagicHome @skyzhishui"""
import socket
import csv
import struct
import datetime
import subprocess
import time
import hashlib
import logging
import voluptuous as vol
import threading
import homeassistant.helpers.config_validation as cv
import homeassistant.util.color as color_util
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    ATTR_EFFECT,
    ATTR_WHITE_VALUE,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_EFFECT,
    SUPPORT_WHITE_VALUE,
    Light,
    PLATFORM_SCHEMA,
	ENTITY_ID_FORMAT,
)
from homeassistant.const import (
    CONF_FRIENDLY_NAME
)
_LOGGER = logging.getLogger(__name__)

CONF_LIGHT_IP = "ip"
CONF_LIGHT_TYPE = "dev_type"

ENTITYID = 'entity_id'
DOMAIN = 'light'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_LIGHT_IP): cv.string,
        vol.Optional(CONF_LIGHT_TYPE, default=0): vol.All(int, vol.Range(min=0, max=9)),
    }
)

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Find and return MagicHomeLight."""
    ip = config.get(CONF_LIGHT_IP)
    dev_type = config.get(CONF_LIGHT_TYPE)
    lights = []
    lights.append(MagicHomeLight(ip,dev_type))
    if not lights:
        return False
    add_entities(lights)
    return True

class MagicHomeLight(Light):
    """Representation of a MagicHomeLight."""

    def __init__(self, ip, dev_type):
        """Initialize the MagicHomeLight."""
        self.ctrl = MagicHomeApi(ip, dev_type)
        self._tick = 0
        self.entity_id = ENTITY_ID_FORMAT.format(("magichome_" + ip.replace(".","_")).lower())
        self._transition = 1
        stat = self.ctrl.get_status()
        if stat[1] == 161:
            self._state = stat
            rgb = (self._state[6],self._state[7],self._state[8])
            _LOGGER.info("magic_home_rgb: %s",str(rgb))
            max_color = max(rgb)
            self._brightness = max_color
            hs_rgb = (rgb[0] * 255 / max_color,rgb[2] * 255 / max_color,rgb[1] * 255 / max_color)
            self._hs = color_util.color_RGB_to_hs(*hs_rgb)
            _LOGGER.info("init_magic_home_hs_rgb: %s",str(self._hs))
            _LOGGER.info("init_magic_home_brightness: %s",str(self._brightness))
            _LOGGER.info("init_magic_home_stat[2]: %s",str(stat[2]))
            self._available = True
            self._white_value = stat[5]
            if stat[2] == 0x23:
                self._ison = True
            else:
                self._ison = False
            if stat[3] == 0 and stat[4] == 0x61:
                self._effect = "0"
            else:
                self._effect = str(stat[3] * 256 + stat[4] - 99)
                _LOGGER.info("init_magic_home_stat[3]: %s",str(stat[3]))
                _LOGGER.info("init_magic_home_stat[4]: %s",str(stat[4]))
                _LOGGER.info("init_magic_home_effect: %s",str(self._effect))
        else:
            self._hs = None
            self._ison = False
            self._effect = None
            self._brightness = None
        eff_list = []
        for i in range(300):
            eff_list.append(str(i))
        self._effect_list = eff_list

    @property
    def is_on(self):
        """Return true if it is on."""
        return self._ison

    @property
    def hs_color(self):
        """Return the hs color value."""
        return self._hs

    @property
    def brightness(self):
        """Return the hs color value."""
        return self._brightness

    @property
    def white_value(self):
        """Return the hs color value."""
        return self._white_value


    @property
    def effect(self):
        """Return the hs color value."""
        return self._effect

    @property
    def effect_list(self):
        """Return the hs color value."""
        return self._effect_list

    @property
    def supported_features(self):
        """Return the supported features."""
        return SUPPORT_COLOR | SUPPORT_BRIGHTNESS | SUPPORT_EFFECT | SUPPORT_WHITE_VALUE

    @property
    def available(self):
        """Return true when state is known."""
        return self._available

    def turn_on(self, **kwargs):
        """Turn the light on."""
        if ATTR_HS_COLOR in kwargs:
            self._hs = kwargs[ATTR_HS_COLOR]
        if ATTR_EFFECT in kwargs:
            self._effect = kwargs[ATTR_EFFECT]
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]
        if ATTR_WHITE_VALUE in kwargs:
            self._white_value = kwargs[ATTR_WHITE_VALUE]
        _LOGGER.info("set_magic_home:ATTR_HS_COLOR=%s, ATTR_EFFECT=%s, ATTR_BRIGHTNESS=%s, ATTR_WHITE_VALUE=%s " % (self._hs,self._effect,self._brightness,self._white_value))
        if self._effect == "0":
            #_LOGGER.info("set_magic_home_brightness: %s",str(self._brightness))
            rgb = color_util.color_hs_to_RGB(*self._hs)
            #_LOGGER.info("set_magic_home_rgb: %s",str(rgb))
            mh_rgb = (rgb[0] * self._brightness / 255,rgb[2] * self._brightness / 255,rgb[1] * self._brightness / 255)
            #_LOGGER.info("set_magic_home_rgb: %s",str(mh_rgb))
            if self.ctrl.update_device(int(mh_rgb[0]),int(mh_rgb[1]),int(mh_rgb[2])) == -1:
                return
        else:
            if self._ison:
                if self._white_value > 100:
                    self._white_value = 100
                if self.ctrl.send_preset_function(int(self._effect),self._white_value) == -1:
                    return
        if self.ctrl.turn_on() == -1:
            return
        self._ison = True
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        if self.ctrl.turn_off() == -1:
            return
        self._ison = False
        self.schedule_update_ha_state()

    def update(self):
        """Fetch state from the device."""
        stat = self.ctrl.get_status()
        if stat == -1:
            self._available = False
            return
        if len(stat) != 14:
            return
        if stat[1] == 161:
            self._state = stat
            self._available = True
            self._white_value = stat[5]
            if stat[2] == 0x23:
                self._ison = True
            else:
                self._ison = False
            if stat[3] == 0 and stat[4] == 0x61:
                self._effect = "0"
                rgb = (self._state[6],self._state[7],self._state[8])
                max_color = max(rgb)
                self._brightness = max_color
                hs_rgb = (rgb[0] * 255 / max_color,rgb[2] * 255 / max_color,rgb[1] * 255 / max_color)
                self._hs = color_util.color_RGB_to_hs(*hs_rgb)
            else:
                self._effect = str(stat[3] * 256 + stat[4] - 99)

"""
reference from https://github.com/adamkempenich/magichome-python

"""
"""MagicHome Python API.
Copyright 2016, Adam Kempenich. Licensed under MIT.
It currently supports:
- Bulbs (Firmware v.4 and greater)
- Legacy Bulbs (Firmware v.3 and lower)
- RGB Controllers
- RGB+WW Controllers
- RGB+WW+CW Controllers
"""

class MagicHomeApi:
    """Representation of a MagicHome device."""

    def __init__(self, device_ip, device_type):
        """"Initialize a device."""
        self.device_ip = device_ip
        self.device_type = device_type
        self.API_PORT = 5577
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.settimeout(5)

    def turn_on(self):
        """Turn a device on."""
        if not self.socket_connect():
            return -1
        self.send_bytes(0x71, 0x23, 0x0F, 0xA3) if self.device_type != 4 else self.send_bytes(0xCC, 0x23, 0x33)
        self.s.shutdown(2)
        self.s.close()
        return 0

    def turn_off(self):
        """Turn a device off."""
        if not self.socket_connect():
            return -1
        self.send_bytes(0x71, 0x24, 0x0F, 0xA4) if self.device_type != 4 else self.send_bytes(0xCC, 0x24, 0x33)
        self.s.shutdown(2)
        self.s.close()
        return 0

    def get_status(self):
        """Get the current status of a device."""
        if not self.socket_connect():
            return -1
        resv = []
        if self.device_type == 2:
            self.send_bytes(0x81, 0x8A, 0x8B, 0x96)
            resv = self.s.recv(15)
        else:
            self.send_bytes(0x81, 0x8A, 0x8B, 0x96)
            resv = self.s.recv(14)
        self.s.shutdown(2)
        self.s.close()
        return resv

    def update_device(self, r=0, g=0, b=0, white1=None, white2=None):
        """Updates a device based upon what we're sending to it.

        Values are excepted as integers between 0-255.
        Whites can have a value of None.
        """
        if not self.socket_connect():
            return -1
        if self.device_type <= 1:
            # Update an RGB or an RGB + WW device
            white1 = self.check_number_range(white1)
            message = [0x31, r, g, b, white1, 0x00, 0x0f]
            self.send_bytes(*(message+[self.calculate_checksum(message)]))

        elif self.device_type == 2:
            # Update an RGB + WW + CW device
            message = [0x31,
                       self.check_number_range(r),
                       self.check_number_range(g),
                       self.check_number_range(b),
                       self.check_number_range(white1),
                       self.check_number_range(white2),
                       0x0f, 0x0f]
            self.send_bytes(*(message+[self.calculate_checksum(message)]))

        elif self.device_type == 3:
            # Update the white, or color, of a bulb
            if white1 is not None:
                message = [0x31, 0x00, 0x00, 0x00,
                           self.check_number_range(white1),
                           0x0f, 0x0f]
                self.send_bytes(*(message+[self.calculate_checksum(message)]))
            else:
                message = [0x31,
                           self.check_number_range(r),
                           self.check_number_range(g),
                           self.check_number_range(b),
                           0x00, 0xf0, 0x0f]
                self.send_bytes(*(message+[self.calculate_checksum(message)]))

        elif self.device_type == 4:
            # Update the white, or color, of a legacy bulb
            if white1 != None:
                message = [0x56, 0x00, 0x00, 0x00,
                           self.check_number_range(white1),
                           0x0f, 0xaa, 0x56, 0x00, 0x00, 0x00,
                           self.check_number_range(white1),
                           0x0f, 0xaa]
                self.send_bytes(*(message+[self.calculate_checksum(message)]))
            else:
                message = [0x56,
                           self.check_number_range(r),
                           self.check_number_range(g),
                           self.check_number_range(b),
                           0x00, 0xf0, 0xaa]
                self.send_bytes(*(message+[self.calculate_checksum(message)]))

        elif self.device_type == 5:
            # Update the white, or color, of a bulb
            if white1 is not None:
                message = [0x31, 0x00, 0x00, 0x00,
                           self.check_number_range(white1),
                           0x00, 0x0f]
                self.send_bytes(*(message+[self.calculate_checksum(message)]))
            else:
                message = [0x31,
                           self.check_number_range(r),
                           self.check_number_range(g),
                           self.check_number_range(b),
                           0x00, 0x00, 0x0f]
                self.send_bytes(*(message+[self.calculate_checksum(message)]))
        else:
            # Incompatible device received
            _LOGGER.info("Incompatible device type received...")
        self.s.shutdown(2)
        self.s.close()
        return 0

    def check_number_range(self, number):
        """Check if the given number is in the allowed range."""
        if number < 0:
            return 0
        elif number > 255:
            return 255
        else:
            return number

    def socket_connect(self):
        try:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.settimeout(5)
            self.s.connect((self.device_ip, self.API_PORT))
            return True
        except socket.error as exc:
            _LOGGER.info("Caught exception socket.error : %s" % exc)
            return False
    def send_preset_function(self, preset_number, speed):
        """Send a preset command to a device."""
        if not self.socket_connect():
            return
        preset_number = preset_number + 99
        p1 = preset_number & 0xff
        p2 = preset_number >> 8 & 0xff
        if speed < 0:
            speed = 0
        if speed > 100:
            speed = 100
        if type == 4:
            self.send_bytes(0xBB, preset_number, speed, 0x44)
        else:
            if self.device_type == 5:
                message = [0x61, p2, p1, speed, 0x0F]
                self.send_bytes(*(message+[self.calculate_checksum(message)]))
            else:
                message = [0x61, preset_number, speed, 0x0F]
                self.send_bytes(*(message+[self.calculate_checksum(message)]))
        self.s.shutdown(2)
        self.s.close()

    def calculate_checksum(self, bytes):
        """Calculate the checksum from an array of bytes."""
        return sum(bytes) & 0xFF

    def send_bytes(self, *bytes):
        """Send commands to the device."""
        try:
            message_length = len(bytes)
            self.s.send(struct.pack("B"*message_length, *bytes))
            # Close the connection unless requested not to
        except socket.error as exc:
            _LOGGER.info("Caught exception socket.error : %s" % exc)
