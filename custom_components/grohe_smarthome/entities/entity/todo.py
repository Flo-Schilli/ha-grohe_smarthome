import logging

from benedict import benedict
from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from ...dto.config_dtos import NotificationsDto, TodoDto
from ...dto.grohe_device import GroheDevice
from ..coordinator.profile_coordinator import ProfileCoordinator

_LOGGER = logging.getLogger(__name__)


class Todo(CoordinatorEntity, TodoListEntity):
    def __init__(
        self,
        domain: str,
        coordinator: DataUpdateCoordinator,
        device: GroheDevice,
        todo: TodoDto,
        notification_config: NotificationsDto,
    ):
        super().__init__(coordinator)

        self._coordinator = coordinator
        self._todo = todo
        self._device = device
        self._domain = domain
        self._notification_config = notification_config
        self._list: list[TodoItem] = []

        # Needed for TodoEntity
        self._attr_name = f"{self._device.name} {self._todo.name}"
        self._attr_has_entity_name = False
        self._attr_todo_items = []
        self._attr_supported_features = (
            TodoListEntityFeature.UPDATE_TODO_ITEM
            | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
        )

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(self._domain, self._device.appliance_id)},
            name=self._device.name,
            manufacturer="Grohe",
            model=self._device.device_name,
            sw_version=self._device.sw_version,
            suggested_area=self._device.room_name,
        )

    @property
    def unique_id(self):
        return (
            f"{self._device.appliance_id}_{self._todo.name.lower().replace(' ', '_')}"
        )

    async def async_update(self) -> None:
        if isinstance(self._coordinator, DataUpdateCoordinator):
            await self._coordinator.async_request_refresh()
            self._update_data()

    def _update_data(self):
        if self._todo.keypath is not None:
            _LOGGER.debug(f"Adding todo items for {self._todo.name}")
            if isinstance(self._coordinator, ProfileCoordinator):
                data = benedict(self._coordinator.get_data())

                notifications = data.get(self._todo.keypath)
                todo_items: list[TodoItem] = []
                if isinstance(notifications, list):
                    for notification in notifications:
                        if (
                            notification.get("appliance_id")
                            == self._device.appliance_id
                        ):
                            description = (
                                f"Notification for: {notification.get('appliance_name')} \r\n\r\n"
                                f"Date of notification: {notification.get('timestamp')} \r\n\r\n"
                                f"Notification category: {notification.get('category')} \r\n\r\n"
                                f"Notification subcategory: {notification.get('notification_type')} \r\n\r\n"
                                f"Full path: {notification.get('location_name')} - {notification.get('room_name')} - {notification.get('appliance_name')}"
                            )
                            todo_item = TodoItem(
                                self._notification_config.get_notification(
                                    notification.get("category"),
                                    notification.get("notification_type"),
                                ),
                                notification.get("notification_id"),
                                TodoItemStatus.NEEDS_ACTION
                                if not notification.get("is_read")
                                else TodoItemStatus.COMPLETED,
                                None,
                                description,
                            )
                            todo_items.append(todo_item)

                if todo_items:
                    _LOGGER.debug(
                        f"Writing {len(todo_items)} ToDo - Items for {self._device.name}"
                    )
                    self._list = todo_items
                    self._attr_todo_items = todo_items

    async def async_update_todo_item(self, item: TodoItem) -> None:
        _LOGGER.debug(f"Updating item {item.uid}")

        item_in_list = next(
            (search for search in self._attr_todo_items if search.uid == item.uid), None
        )

        if item_in_list is not None and isinstance(
            self._coordinator, ProfileCoordinator
        ):
            item_in_list.status = item.status
            status = item.status == TodoItemStatus.COMPLETED
            await self._coordinator.update_notification(item.uid, status)
            await self._coordinator.async_request_refresh()
            self._update_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_data()
