from abc import abstractmethod


class CoordinatorValveInterface:
    @abstractmethod
    async def set_valve(self, data_to_set: dict[str, any]) -> dict[str, any]:
        raise NotImplementedError

    @abstractmethod
    async def get_valve_value(self) -> dict[str, any]:
        raise NotImplementedError
