from abc import abstractmethod


class CoordinatorConfigInterface:
    @abstractmethod
    async def set_config(self, data_to_set: dict[str, any]) -> dict[str, any]:
        raise NotImplementedError

    @abstractmethod
    async def get_config_value(self) -> dict[str, any]:
        raise NotImplementedError
