from abc import abstractmethod
from typing import Dict


class CoordinatorInterface:
    @abstractmethod
    async def _get_data(self) -> Dict[str, any]:
        raise NotImplementedError

    @abstractmethod
    async def get_initial_value(self) -> Dict[str, any]:
        raise NotImplementedError

    @abstractmethod
    def set_polling_interval(self, polling: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_log_response_data(self, log_response_data: bool) -> None:
        raise NotImplementedError