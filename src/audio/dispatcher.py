from typing import Dict, Any, Union, Callable, Awaitable
from inspect import iscoroutinefunction
from contextlib import suppress


class Dispatcher:
    def __init__(self, default: Dict[str, Any] | None = None) -> None:
        self.actions: Dict[str, list] = {}
        self.default = default or {}

    def default_update(self, default: Dict[str, Any]) -> None:
        self.default.update(default)

    def default_remove(self, name: str) -> None:
        with suppress(KeyError):
            return self.default.pop(name)

    def clear_default(self) -> None:
        self.default.clear()

    def add_action(self, name: str, callback: Union[Callable, Awaitable]) -> None:
        if not self.actions.get(name):
            self.actions[name] = []
        if not callable(callback):
            raise ValueError("callback is not callable")
        self.actions[name].append(callback)

    def remove_action(self, name: str) -> None:
        if self.actions.get(name):
            self.actions[name].clear()

    def clear_action(self) -> None:
        self.actions.clear()

    async def dispatch_connect(self) -> None:
        await self.dispatch("connect", {})

    async def dispatch_socketio(self, payload: Dict[str, Any]) -> None:
        from src.audio import DEBUG_MODE
        event_type = payload.get("type")
        # Получаем client из default для красивого вывода
        client = self.default.get("client")
        client_name = client.name if client else "unknown"
        if DEBUG_MODE:
            print(f"  📨 [{client_name}] Event: {event_type}")
            if event_type in ["offer", "answer", "ice-candidate"]:
                # Скрываем большие payload для этих событий
                print(f"      → Data: <WebRTC data>")
            elif event_type not in ["users-count"]:  # Скрываем спам
                print(f"      → {payload}")
        await self.dispatch(event_type, payload)

    async def dispatch(self, name: str, payload: Dict[str, Any]) -> None:
        actions = self.actions.get(name)
        if not actions:
            return
        for action in actions:
            if iscoroutinefunction(action):
                await action(**self.default, payload=payload)
            else:
                action(**self.default, payload=payload)
