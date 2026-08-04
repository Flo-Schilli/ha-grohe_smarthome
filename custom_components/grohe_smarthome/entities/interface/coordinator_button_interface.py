from abc import abstractmethod


class CoordinatorButtonInterface:
    @abstractmethod
    async def send_command(self, data_to_send: dict[str, any]) -> dict[str, any]:
        raise NotImplementedError
