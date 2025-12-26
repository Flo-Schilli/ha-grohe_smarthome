import logging
from typing import List

from benedict import benedict
from grohe import GroheClient

from grohe import GroheTypes

_LOGGER = logging.getLogger(__name__)


class GroheDevice:
    def __init__(self, location_id: int, room_id: int, room_name: str, appliance: benedict):
        self._location_id = location_id
        self._room_id = room_id
        self._room_name = room_name
        self._appliance = appliance

    @property
    def location_id(self):
        return self._location_id

    @property
    def room_id(self):
        return self._room_id

    @property
    def room_name(self) -> str:
        return self._room_name

    @property
    def appliance_id(self) -> str:
        return self._appliance.get('appliance_id')

    @property
    def sw_version(self) -> str:
        return self._appliance.get('version')

    @property
    def stripped_sw_version(self) -> tuple[int, ...]:
        try:
            version = tuple(map(int, self.sw_version.split('.')[:2]))
        except ValueError:
            _LOGGER.warning(f'SW-Version for {self.name} cannot be split into two numbers. Value is: "{self.sw_version}"')
            version = (0, 0)
        return version

    @property
    def name(self) -> str:
        return self._appliance.get('name')

    @property
    def device_serial(self) -> str:
        return self._appliance.get('serial_number')

    @property
    def type(self) -> GroheTypes:
        return GroheTypes(self._appliance.get('type'))

    @property
    def device_name(self) -> str:
        dev_name = self.type
        if dev_name == GroheTypes.GROHE_SENSE:
            return 'Sense'
        elif dev_name == GroheTypes.GROHE_SENSE_GUARD:
            return 'Sense Guard'
        elif dev_name == GroheTypes.GROHE_SENSE_PLUS:
            return 'Sense Plus'
        elif dev_name == GroheTypes.GROHE_BLUE_HOME:
            return 'Blue Home'
        elif dev_name == GroheTypes.GROHE_BLUE_PROFESSIONAL:
            return 'Blue Professional'
        else:
            return 'Unknown'

    @staticmethod
    async def get_devices(api: GroheClient) -> List['GroheDevice']:
        """
        Fetches all devices associated with the provided GroheClient instance.

        :param api: An instance of the GroheClient class.
        :type api: GroheClient
        :return: A list of GroheDevice objects representing the discovered devices.
        :rtype: List[GroheDevice]
        """
        _LOGGER.debug(f'Getting all available Grohe devices')
        devices: List[GroheDevice] = []

        data = await api.get_dashboard()

        if data is not None:
            dashboard = benedict(data)

            locations = dashboard.get('locations')

            if locations is not None:
                for location in locations:
                    rooms = location.get('rooms')
                    if rooms is not None:
                        for room in rooms:
                            appliances = room.get('appliances')

                            if appliances is not None:
                                for appliance in appliances:
                                    location_id = location.get('id')
                                    room_id = room.get('id')
                                    appliance_id = appliance.get('appliance_id')
                                    registration_complete = appliance.get('registration_complete')

                                    _LOGGER.debug(
                                        f'Found in location {location_id} and room {room_id} the following appliance: {appliance_id} '
                                        f'from type {appliance.get('type')} with name {appliance.get('name')}'
                                    )

                                    if registration_complete is True or registration_complete is None:
                                        try:
                                            device: GroheDevice = GroheDevice(location_id, room_id, room.get('name'), appliance)
                                            if not device.is_valid_device_type():
                                                _LOGGER.warning(f'Could not parse the following appliance as a GroheDevice. Please file '
                                                                f'a new issue with your Grohe Devices and this information.'
                                                                f'Appliance: {appliance.get('name')}, Appliance details: {appliance}')
                                            else:
                                                devices.append(device)
                                        except ValueError as e:
                                            _LOGGER.warning(f'Could not parse the following appliance as a GroheDevice: {appliance}. Error: {e}')
                                    else:
                                        _LOGGER.warning(f'Appliance {appliance_id} with name {appliance.get('name')} is not yet fully registered at Grohe. Skipping.')
                            else:
                                _LOGGER.error(f'Could not find any appliances assigned to this room')
                    else:
                        _LOGGER.error(f'Could not find any rooms assigned to this location')
            else:
                _LOGGER.error(f'Could not find any locations assigned to this account')

        return devices

    def is_valid_device_type(self) -> bool:
        is_valid = any(self._appliance.get('type') == item.value for item in GroheTypes)
        return is_valid