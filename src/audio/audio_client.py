from typing import Callable, Awaitable, Optional, Union

from socketio import AsyncClient
import aiohttp
from aiohttp.resolver import ThreadedResolver
import structlog

from src.audio.dispatcher import Dispatcher
from src.audio.types import SearchCriteria


class AudioClient(AsyncClient):
	endpoint: str = "wss://audio.nekto.me/"

	def __init__(
		self,
		name: str,
		user_id: str,
		ua: str,
		search_criteria: SearchCriteria,
		locale: str = "ru",
		time_zone: str = "Europe/Berlin",
		wait_for: Optional[str] = None,
		proxy: Optional[str] = None,
		*args,
		**kwargs,
	) -> None:
		self.name = name
		self.wait_for = wait_for
		self.user_id = user_id
		self.ua = ua
		self.locale = locale
		self.time_zone = time_zone
		self.search_criteria = search_criteria
		self.proxy = proxy
		self.is_firefox = "Gecko" in self.ua
		self.connection_id: Optional[str] = None
		
		# НЕ создаём http_session здесь - это вызовет ошибку вне event loop
		# Сессия будет создана в init() внутри async контекста
		super().__init__(
			logger=False,
			*args,
			**kwargs,
		)
		self.log = structlog.get_logger().bind(audio_user=user_id[:7])
		if proxy:
			self.log.info(f"Using proxy: {proxy[:30]}...")
		self.dispatcher = Dispatcher(default={"client": self})
	
	def _create_http_session(self, proxy: Optional[str]) -> aiohttp.ClientSession:
		"""Создаёт HTTP сессию с опциональной поддержкой прокси (вызывать только в async контексте!)"""
		# Use ThreadedResolver for proper DNS resolution on Windows
		resolver = ThreadedResolver()
		
		if proxy:
			try:
				from aiohttp_socks import ProxyConnector
				connector = ProxyConnector.from_url(proxy, resolver=resolver)
				return aiohttp.ClientSession(connector=connector)
			except ImportError:
				self.log.warning("aiohttp_socks not installed, proxy ignored. Run: pip install aiohttp_socks")
			except Exception as e:
				self.log.warning(f"Failed to create proxy connector: {e}")
		
		connector = aiohttp.TCPConnector(resolver=resolver)
		return aiohttp.ClientSession(connector=connector)

	def set_connection_id(self, value: Union[str, None]) -> None:
		self.connection_id = value

	def get_connection_id(self) -> Optional[str]:
		if self.connection_id:
			return self.connection_id
		raise AttributeError("Client not connected.")

	def add_action(self, name: str, callback: Union[Callable, Awaitable]) -> None:
		self.dispatcher.add_action(name, callback)

	def remove_action(self, name: str) -> None:
		self.dispatcher.remove_action(name)

	async def search(self) -> None:
		self.log.info("Audio client searching for a voice partner.")
		payload = {
			"type": "scan-for-peer",
			"peerToPeer": True,
			"token": None,
			"searchCriteria": self.search_criteria,
		}
		await self.emit("event", data=payload)

	async def peer_disconnect(self) -> None:
		try:
			connection_id = self.get_connection_id()
			self.log.info("Audio client disconnects peer", connection_id=connection_id)
			await self.emit(
				"event",
				data={"type": "peer-disconnect", "connectionId": connection_id},
			)
		except AttributeError:
			self.log.info("Audio client stops scanning")
			await self.emit("event", data={"type": "stop-scan"})

	async def init(self, wait: bool = True) -> None:
		# Создаём http_session здесь - внутри async контекста
		self.http = self._create_http_session(self.proxy)
		self.eio.http = self.http
		
		self.on("connect", self.dispatcher.dispatch_connect)
		self.on("event", self.dispatcher.dispatch_socketio)
		await super().connect(
			self.endpoint,
			transports=["websocket"],
			socketio_path="websocket",
			headers={
				"User-Agent": self.ua,
				"Origin": "https://nekto.me",
			},
		)
		if wait:
			await super().wait()

	async def _handle_eio_message(self, data):
		try:
			await super()._handle_eio_message(data)
		except Exception:
			# Игнорируем ошибки парсинга Engine.IO
			pass

