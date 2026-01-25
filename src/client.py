from socketio import AsyncClient

from typing import Callable, Dict, Any, List, Self, Literal
from src.utils import generate_webagent

import aiohttp
from aiohttp.resolver import ThreadedResolver
import structlog
import time
import logging

SEX_ANNOTATION = Literal["F", "M"]

class Client(AsyncClient):
    """
    NektoMe SocketIO Async Client
    """

    addr: str = "wss://im.nekto.me"

    def __init__(
        self, 
        token: str, 
        ua: str,
        locale: str = "ru",
        tz: str = "Europe/Kiew",
        age: List[int] = None,
        wish_age: List[List[int]] = None,
        sex: SEX_ANNOTATION = None,
        wish_sex: SEX_ANNOTATION = None,
        role: bool = None,
        wish_role: Literal["suggest", "search"] = None,
        adult: bool = None,
        *args, 
        **kwargs
    ):
        self.token = token
        self.ua = ua
        self.locale = locale
        self.tz = tz

        self.events = dict()

        self._logger = structlog.get_logger()
        
        # Подавляем ошибки JSON парсинга из socketio
        logging.getLogger('socketio').setLevel(logging.CRITICAL)
        logging.getLogger('engineio').setLevel(logging.CRITICAL)

        super().__init__(*args, **kwargs)

        if role and adult:
            self.get_logger().warning("Adult and Role cannot be True. Choose one!")
        if role and (age or wish_age):
            self.get_logger().warning("Age is not required when you use Role!")

        if not role and wish_role:
            self.get_logger().warning("Wish role is not required when you use not Role!")
            
        self.search_parameters = {
            "wishAge":wish_age,
            "myAge":age,
            "mySex":sex,
            "wishSex":wish_sex,
            "adult":adult,
            "role":role
        }

        if role:
            if wish_role == "suggest":
                self.search_parameters["myAge"] = [30, 40]
            elif wish_role == "search":
                self.search_parameters["myAge"] = [10, 20]
            else:
                self.get_logger().warning("Wish role is unexcepted.", wish_role=wish_role)

        self.on("connect", self.on_connect)
        self.on("disconnect", self.on_disconnect)
        self.on("notice", self.on_notice)
        self.add_event_handler("auth.successToken", self.on_auth)
        self.add_event_handler("dialog.opened", self.on_dialog_opened)
        self.add_event_handler("dialog.closed", self.on_dialog_closed)
        self.add_event_handler("error.code", self.error_handler)

    def get_logger(self):
        return self._logger.bind(token=self.token[:10])

    async def error_handler(self, data: Dict[str, Any], _: Self) -> None:
        # Игнорируем ошибки типа "Wrong data" и другие несущественные ошибки
        pass

    async def on_auth(self, data: Dict[str, Any], _: Self) -> None:
        self.get_logger().debug("The client has logged in.")
        setattr(self, "id", data.get("id"))
        dialog_id = data.get("statusInfo").get("anonDialogId")
        if dialog_id: setattr(self, "dialog_id", dialog_id)
        payload = {
            "type":"web-agent",
            "data":generate_webagent(self.token, self.id, round(time.time() * 1000))
        }
        self.get_logger().debug("Sending web-agent", payload=payload)
        await self.emit("action", data=payload)

    async def on_connect(self) -> None:
        self.get_logger().info(f"Connected to server!")
        self.is_reconnecting = False  # Сбрасываем флаг переподключения
        
        payload = {
            "token":self.token,
            "locale":self.locale,
            "t":round(time.time() * 1000),
            "timeZone":self.tz,
            "version":12,
            "action":"auth.sendToken"
        }
        await self.emit("action", data=payload)
        self.get_logger().debug("Sent user credentials!", payload=payload)

    async def on_dialog_opened(self, data: Dict[str, Any], _: Self) -> None:
        setattr(self, "dialog_id", data.get("id"))
    
    async def on_dialog_closed(self, data: Dict[str, Any], _: Self) -> None:
        if hasattr(self, "dialog_id"):
            delattr(self, "dialog_id")

    def get_handlers(self, name: str) -> List[Callable]:
        self.get_logger().debug(f"Getting {name} handlers!")
        handlers = self.events.get(name) or []
        self.get_logger().debug(f"Found {len(handlers)} handler(s)!")
        return handlers
    
    def is_connected(self) -> bool:
        """Проверяет, подключен ли клиент к Socket.IO серверу"""
        return self.connected and hasattr(self, 'id')
    
    async def safe_emit(self, event: str, data: dict = None) -> bool:
        """Безопасная отправка события с проверкой подключения и автоматическим переподключением"""
        import asyncio
        
        if not self.connected:
            self.get_logger().warning("Client disconnected, attempting to reconnect...")
            try:
                await self.connect(max_retries=3, retry_delay=2)
            except Exception as e:
                self.get_logger().error(f"Reconnection failed: {e}")
                return False
        
        try:
            await self.emit(event, data=data)
            return True
        except Exception as e:
            # Если соединение потеряно, пробуем переподключиться
            self.get_logger().warning(f"Error emitting event: {e}. Attempting reconnect...")
            try:
                await asyncio.sleep(1)
                await self.connect(max_retries=3, retry_delay=2)
                await self.emit(event, data=data)
                return True
            except Exception as reconnect_error:
                self.get_logger().error(f"Reconnection and emit failed: {reconnect_error}")
                return False

    async def search(self) -> bool:
        """Запуск поиска. Возвращает True если успешно."""
        payload = {
            "action":"search.run"
        }
        payload.update(self.search_parameters)
        self.get_logger().debug("Searching with search parameters", payload=payload)
        return await self.safe_emit("action", data=payload)

    async def on_disconnect(self) -> None:
        """Обработка отключения с авто-реконнектом"""
        self.get_logger().warning(f"Disconnected from server!")
        
        # Вызываем обработчики (например обновление статуса комнаты)
        handlers = self.get_handlers("disconnect")
        if handlers:
            for handler in handlers:
                await handler()
                
        if hasattr(self, "id"):
            delattr(self, "id")
            
        # Автоматическое переподключение
        # Если это не ручное отключение (которое мы пока не отслеживаем, но обычно disconnect вызывается нами)
        # В данном случае WinError 10054 это разрыв со стороны сервера/сети
        
        import asyncio
        self.get_logger().info("Starting auto-reconnection in 3 seconds...")
        await asyncio.sleep(3)
        try:
            await self.connect(max_retries=100, retry_delay=5)
        except Exception as e:
            self.get_logger().error(f"Auto-reconnection failed: {e}")

    async def on_notice(self, data: Dict[str, Any]) -> None:
        self.get_logger().debug("Received notice!", notice=data)
        notice = data.get("notice")
        if not notice: return
        handlers = self.get_handlers(notice)
        if not handlers: return
        for handler in handlers:
            await handler(data.get("data"), self)

    async def connect(self, max_retries: int = 5, retry_delay: int = 3) -> None:
        """Подключение с автоматическими повторными попытками"""
        import asyncio
        
        # Use ThreadedResolver for proper DNS resolution on Windows
        resolver = ThreadedResolver()
        connector = aiohttp.TCPConnector(resolver=resolver)
        http_session = aiohttp.ClientSession(connector=connector)
        self.http = http_session
        self.eio.http = http_session
        
        for attempt in range(1, max_retries + 1):
            try:
                self.get_logger().info(f"Попытка подключения {attempt}/{max_retries}...")
                await super().connect(
                    url=self.addr, 
                    headers={
                        "User-Agent": self.ua,
                        "Origin": "https://nekto.me",
                    }, 
                    transports=["websocket"],
                )
                self.get_logger().info("Успешно подключено!")
                return
            except Exception as e:
                error_msg = str(e)
                if attempt < max_retries:
                    self.get_logger().warning(
                        f"Ошибка подключения (попытка {attempt}/{max_retries}): {error_msg}. "
                        f"Повтор через {retry_delay} сек..."
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    self.get_logger().error(
                        f"Не удалось подключиться после {max_retries} попыток: {error_msg}"
                    )
                    raise

    async def _handle_eio_message(self, data):
        """Переопределяем метод для подавления ошибок JSON парсинга"""
        try:
            await super()._handle_eio_message(data)
        except Exception as e:
            # Игнорируем все ошибки парсинга, они не критичны
            pass

    def add_event_handler(self, event: str, callback: Callable) -> None:
        if not isinstance(self.events.get(event), list):
            self.events[event] = list()
        self.events[event].append(callback)