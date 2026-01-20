"""
Аудио менеджер для nekto.me audio chat
Управление комнатами и клиентами, API для UI
"""
from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from aiortc import RTCPeerConnection
from aiortc.contrib.signaling import object_to_string
import structlog
import asyncio
import json
import os
import random

from src.audio.audio_client import AudioClient
from src.audio.config import parse_audio_clients
from src.audio.rtc import MediaRedirect, MediaRecorder
from src.audio.utils import get_ice_candidates, parse_turn_params, alarm
from src.utils import generate_random_id

# Module-level logger
log = structlog.get_logger().bind(module="audio_manager")

AUDIO_LOGS_DIR = Path("audio_logs")

# Anti-detection delays (в секундах)
DELAY_BEFORE_SEARCH_MIN = 3.0
DELAY_BEFORE_SEARCH_MAX = 8.0
DELAY_RESTART_MIN = 5.0
DELAY_RESTART_MAX = 15.0
DELAY_BETWEEN_ACTIONS_MIN = 0.5
DELAY_BETWEEN_ACTIONS_MAX = 2.0


async def human_delay(min_sec: float, max_sec: float, name: str = "") -> None:
    """Случайная задержка для имитации человека"""
    from src.audio import DEBUG_MODE
    delay = random.uniform(min_sec, max_sec)
    if name and DEBUG_MODE:
        print(f"  ⏳ [{name}] Waiting {delay:.1f}s...")
    await asyncio.sleep(delay)

# Глобальные хранилища для API
AUDIO_CLIENTS: Dict[str, AudioClient] = {}
AUDIO_ROOMS: Dict[str, "AudioRoom"] = {}


@dataclass
class Member:
    """Участник аудио комнаты"""
    client: AudioClient
    redirect: Optional[MediaRedirect] = None
    pc: Optional[RTCPeerConnection] = None


class AudioRoom:
    """Аудио комната для двух участников"""
    
    def __init__(self, room_id: str, recorder: MediaRecorder, file_path: Path):
        self.room_id = room_id
        self.file_path = file_path
        self.recorder = recorder
        self.members: List[Member] = []
        self.log = structlog.get_logger().bind(audio_room=room_id)
        self.start_time = datetime.now()
        self.is_recording = False
        self.is_paused = False  # Состояние паузы
    
    def add_member(self, member: Member):
        """Добавление участника в комнату"""
        # Регистрируем обработчики WebRTC событий
        member.client.add_action("peer-connect", self._on_peer_connect)
        member.client.add_action("peer-disconnect", self._on_peer_disconnect)
        member.client.add_action("search.out", self._on_search_out)
        
        # Добавляем обработчики для полного flow авторизации
        async def on_connect(client, payload):
            """При подключении отправляем register с userId"""
            from src.audio import DEBUG_MODE
            if DEBUG_MODE:
                print(f"  📡 [{client.name}] Connected, sending register...")
            register_payload = {
                "type": "register",
                "android": False,
                "version": 22,
                "userId": client.user_id,
                "timeZone": client.time_zone,
                "locale": client.locale
            }
            if client.is_firefox:
                register_payload["firefox"] = True
            await client.emit("event", data=register_payload)
        
        async def on_registered(client, payload):
            """После регистрации отправляем web-agent с подписью"""
            from src.audio import DEBUG_MODE
            internal_id = payload.get("internal_id")
            if DEBUG_MODE:
                print(f"  ✅ [{client.name}] Registered, internal_id = {internal_id}")
            
            # Генерируем подпись и отправляем web-agent
            webagent_data = alarm(client.user_id, internal_id)
            webagent_payload = {
                "type": "web-agent",
                "data": webagent_data
            }
            await client.emit("event", data=webagent_payload)
            if DEBUG_MODE:
                print(f"  📤 [{client.name}] Sent web-agent")
            
            # Начинаем поиск если не ждём другого клиента
            if not client.wait_for:
                # Случайная задержка перед поиском (имитация человека)
                await human_delay(DELAY_BEFORE_SEARCH_MIN, DELAY_BEFORE_SEARCH_MAX, client.name)
                if DEBUG_MODE:
                    print(f"  🔎 [{client.name}] Starting search...")
                await client.search()
        
        async def on_search_success(client, payload):
            from src.audio import DEBUG_MODE
            if DEBUG_MODE:
                print(f"  🔎 [{client.name}] Search criteria: {client.search_criteria}")
        
        member.client.add_action("connect", on_connect)
        member.client.add_action("registered", on_registered)
        member.client.add_action("search.success", on_search_success)
        
        self.members.append(member)
        self.log.info(f"Added member: {member.client.name}")
    
    def get_member_by_client(self, client: AudioClient) -> Optional[Member]:
        """Получение участника по клиенту"""
        for member in self.members:
            if member.client == client:
                return member
        return None
    
    def add_members_track(self, track, client: AudioClient):
        """Добавление трека участника другим участникам"""
        for member in self.members:
            if member.client == client:
                continue
            if member.redirect:
                member.redirect.add_track(track)
    
    async def _on_peer_connect(self, client: AudioClient, payload: Dict[str, Any]):
        """Обработка подключения к собеседнику"""
        from src.audio import DEBUG_MODE
        if DEBUG_MODE:
            print(f"  🔗 [{client.name}] Peer found! Setting up WebRTC...")
        
        # ВАЖНО: Устанавливаем connection_id СРАЗУ, до настройки WebRTC
        connection_id = payload.get("connectionId")
        if connection_id:
            client.set_connection_id(connection_id)
            if DEBUG_MODE:
                print(f"  🔑 [{client.name}] Set connection_id: {connection_id}")
        
        member = self.get_member_by_client(client)
        if not member:
            return
        
        # Закрываем старый PeerConnection если есть (предотвращает накопление обработчиков)
        if member.pc and member.pc.connectionState not in ("failed", "closed"):
            self.log.info(f"Closing old PeerConnection for {client.name}")
            try:
                await member.pc.close()
            except Exception as e:
                self.log.warning(f"Error closing old PC: {e}")
            member.pc = None
        
        # Небольшая задержка между действиями (имитация человека)
        await human_delay(DELAY_BETWEEN_ACTIONS_MIN, DELAY_BETWEEN_ACTIONS_MAX)
        
        # Настраиваем WebRTC
        turn_params = json.loads(payload.get("turnParams", "{}"))
        configuration = parse_turn_params(turn_params)
        pc = RTCPeerConnection(configuration=configuration)
        member.pc = pc
        if DEBUG_MODE:
            print(f"  📞 [{client.name}] WebRTC peer connection created")
        
        # Запуск поиска для второго клиента если он ждал
        for other in self.members:
            if other.client.wait_for == client.name:
                if other.client.connected:
                    # Случайная задержка перед поиском второго клиента
                    await human_delay(DELAY_BEFORE_SEARCH_MIN, DELAY_BEFORE_SEARCH_MAX, other.client.name)
                    if DEBUG_MODE:
                        print(f"  🔎 [{other.client.name}] Starting search (was waiting for {client.name})")
                    await other.client.search()
                else:
                    other.client.wait_for = None
        
        # Регистрация WebRTC обработчиков через внешний модуль (новый PC = новые обработчики)
        from src.audio.handlers import setup_webrtc_handlers
        setup_webrtc_handlers(pc, client, member.redirect, self)
    
    async def _on_peer_disconnect(self, client: AudioClient, payload: Dict[str, Any]):
        """Обработка отключения от собеседника - отключаем обоих и перезапускаем поиск"""
        # Избегаем повторных вызовов restart
        if hasattr(self, '_restarting') and self._restarting:
            self.log.debug(f"Already restarting, skipping duplicate disconnect for {client.name}")
            return
        
        self._restarting = True
        self.log.info(f"Peer disconnect for {client.name}")
        
        try:
            # Отключаем другого участника тоже
            for member in self.members:
                if member.client != client and member.client.connection_id:
                    self.log.info(f"Disconnecting other member: {member.client.name}")
                    try:
                        await member.client.peer_disconnect()
                    except Exception as e:
                        self.log.warning(f"Error disconnecting other member: {e}")
            
            # Очищаем ресурсы
            await self._cleanup()
            
            # Перезапускаем поиск если не на паузе
            if not self.is_paused:
                await self._restart_search_for_all()
        finally:
            self._restarting = False
    
    async def _on_search_out(self, client: AudioClient, payload: Dict[str, Any]):
        """Обработка выхода из поиска"""
        self.log.info(f"Search out for {client.name}")
        await self._cleanup()
    
    async def _restart_search_for_all(self):
        """Перезапуск поиска для всех участников комнаты"""
        # Увеличенная случайная задержка перед перезапуском (имитация человека)
        await human_delay(DELAY_RESTART_MIN, DELAY_RESTART_MAX, "room")
        
        # Сначала сбрасываем wait_for для всех (кроме первого)
        first_member = None
        for member in self.members:
            if first_member is None:
                first_member = member
            else:
                # Второй клиент ждет первого
                member.client.wait_for = first_member.client.name
        
        # Запускаем поиск только для первого клиента (с задержкой)
        if first_member and first_member.client.connected:
            await human_delay(DELAY_BEFORE_SEARCH_MIN, DELAY_BEFORE_SEARCH_MAX, first_member.client.name)
            self.log.info(f"Restarting search for {first_member.client.name}")
            try:
                await first_member.client.search()
            except Exception as e:
                self.log.error(f"Error restarting search: {e}")
    
    async def _cleanup(self):
        """Очистка ресурсов"""
        for member in self.members:
            member.client.set_connection_id(None)
            if member.redirect:
                await member.redirect.stop()
            if member.pc and member.pc.connectionState not in ("failed", "closed", "new"):
                await member.pc.close()
            member.pc = None
        self.is_recording = False
    
    async def send_ice_candidates(self, pc: RTCPeerConnection, client: AudioClient):
        """Отправка ICE кандидатов"""
        self.log.info(f"Sending ICE candidates for {client.name}")
        async for candidate in get_ice_candidates(pc):
            candidate_string = json.loads(object_to_string(candidate)).get("candidate")
            payload = {
                "type": "ice-candidate",
                "candidate": json.dumps({
                    "candidate": {
                        "candidate": candidate_string,
                        "sdpMid": 0,
                        "sdpMLineIndex": 0,
                    },
                }),
                "connectionId": client.get_connection_id(),
            }
            await client.emit("event", data=payload)
    
    async def disconnect_all_members(self):
        """Отключение всех участников"""
        for member in self.members:
            with suppress(AttributeError):
                if member.client.connection_id:
                    await member.client.peer_disconnect()
    
    async def force_close(self):
        """Принудительное закрытие диалога и перезапуск поиска"""
        self.log.info("Force closing room")
        self.is_paused = False  # Снимаем паузу если была
        await self._cleanup()
        await self.disconnect_all_members()
        await self._restart_search_for_all()
    
    async def toggle_pause(self) -> bool:
        """Переключение паузы. Возвращает новое состояние."""
        self.is_paused = not self.is_paused
        self.log.info(f"Room paused: {self.is_paused}")
        
        if self.is_paused:
            # Останавливаем поиск и отключаем диалоги
            await self._cleanup()
            for member in self.members:
                if member.client.connected:
                    try:
                        await member.client.peer_disconnect()
                    except Exception as e:
                        self.log.warning(f"Error disconnecting: {e}")
        else:
            # Возобновляем поиск
            await self._restart_search_for_all()
        
        return self.is_paused
    
    async def stop(self):
        """Остановка комнаты"""
        self.log.info("Stopping room")
        await self._cleanup()
        await self.disconnect_all_members()
        self.members.clear()
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация для API"""
        return {
            "room_id": self.room_id,
            "file_path": str(self.file_path),
            "start_time": self.start_time.isoformat(),
            "is_recording": self.is_recording,
            "is_paused": self.is_paused,
            "members": [
                {
                    "name": m.client.name,
                    "user_id": m.client.user_id,
                    "connected": m.client.connected,
                    "connection_id": m.client.connection_id,
                    "status": "in_call" if m.client.connection_id and self.is_recording else 
                              "searching" if m.client.connected else "disconnected"
                }
                for m in self.members
            ],
        }


def get_all_audio_status() -> Dict[str, Any]:
    """Получение статуса всех аудио клиентов для UI"""
    clients_status = []
    for name, client in AUDIO_CLIENTS.items():
        clients_status.append({
            "name": client.name,
            "user_id": client.user_id,
            "connected": client.connected,
            "connection_id": client.connection_id,
            "wait_for": client.wait_for,
            "status": "in_call" if client.connection_id else "searching" if client.connected else "disconnected"
        })
    
    rooms_status = []
    for room_id, room in AUDIO_ROOMS.items():
        rooms_status.append(room.to_dict())
    
    return {
        "clients": clients_status,
        "rooms": rooms_status,
        "total_clients": len(AUDIO_CLIENTS),
        "active_rooms": len([r for r in AUDIO_ROOMS.values() if r.is_recording]),
    }


async def start_audio_async() -> None:
    """Запуск аудио MITM status"""
    from src.audio import DEBUG_MODE
    
    print("\n" + "=" * 50)
    print("🎧 AUDIO MITM: Starting...")
    print("=" * 50)
    
    # Создаём директорию для логов
    os.makedirs(AUDIO_LOGS_DIR, exist_ok=True)
    
    # Парсим клиентов из конфига
    clients = list(parse_audio_clients() or [])
    if DEBUG_MODE:
        print(f"  Found {len(clients)} audio clients in config")
    
    if not clients:
        print("  ⚠ Audio MITM is not configured. Add [audio] section in config.ini.")
        return
    
    if len(clients) < 2:
        print("  ⚠ Audio MITM needs at least 2 clients.")
        return
    
    if len(clients) % 2 != 0:
        print("  ⚠ Audio clients count is odd; the last one will be ignored.")
    
    # Логируем информацию о клиентах
    if DEBUG_MODE:
        for i, client in enumerate(clients):
            proxy_info = f", proxy={client.proxy[:25]}..." if client.proxy else ""
            print(f"  Client {i+1}: name={client.name}, user_id={client.user_id[:10]}..., wait_for={client.wait_for}{proxy_info}")
    
    for client in clients:
        AUDIO_CLIENTS[client.name] = client
    
    tasks = []
    
    # Создаём комнаты для пар клиентов
    for idx in range(0, len(clients) - 1, 2):
        room_id = generate_random_id()
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        file_path = AUDIO_LOGS_DIR / f"audio_{room_id}_{timestamp}.mp3"
        
        if DEBUG_MODE:
            print(f"  [Room] Creating room: room_id={room_id}")
        
        try:
            recorder = MediaRecorder(file=file_path)
            if DEBUG_MODE:
                print(f"  [Room] MediaRecorder initialized: {file_path}")
        except Exception as e:
            print(f"  ❌ Error initializing MediaRecorder: {e}")
            continue
            
        room = AudioRoom(room_id=room_id, recorder=recorder, file_path=file_path)
        AUDIO_ROOMS[room_id] = room
        
        for client in (clients[idx], clients[idx + 1]):
            if DEBUG_MODE:
                print(f"  [Room] Registering client {client.name} in room {room_id}")
            room.add_member(Member(
                client=client, 
                redirect=MediaRedirect(recorder=recorder)
            ))
            
            # Создаём задачу подключения (с фиксацией client через default argument)
            async def connect_and_wait(c: AudioClient = client):  # Важно! Фиксируем client
                if DEBUG_MODE:
                    print(f"  ⏳ [{c.name}] Connecting to audio.nekto.me...")
                try:
                    await c.init(wait=False)  # Подключаемся без блокировки
                    if DEBUG_MODE:
                        print(f"  ✅ [{c.name}] Connected, waiting for events...")
                    await c.wait()  # Ждем событий в фоне
                except Exception as e:
                    import traceback
                    print(f"  ❌ [{c.name}] Error: {type(e).__name__}: {e}")
                    if DEBUG_MODE:
                        traceback.print_exc()
                    log.error(f"Audio client {c.name} failed", error=str(e))
            
            task = asyncio.create_task(connect_and_wait())
            if DEBUG_MODE:
                print(f"  [Task] Created task for {client.name}")
            tasks.append(task)
    
    # Задачи уже запущены в фоне через create_task, не блокируем старт сервера
    if tasks:
        if DEBUG_MODE:
            print(f"  🚀 Started {len(tasks)} audio tasks in background")
        print(f"  ✅ Audio MITM ready\n")
    else:
        print("  ⚠ No audio tasks to start\n")


async def stop_audio_async():
    """Остановка всех аудио клиентов и комнат"""
    log.info("Stopping all audio clients and rooms...")
    
    # Остановка всех комнат
    for room_id, room in list(AUDIO_ROOMS.items()):
        try:
            await room.stop()
        except Exception as e:
            log.error(f"Error stopping room {room_id}: {e}")
    
    AUDIO_ROOMS.clear()
    
    # Отключение всех клиентов
    for client_name, client in list(AUDIO_CLIENTS.items()):
        try:
            if client.connected:
                await client.disconnect()
        except Exception as e:
            log.error(f"Error disconnecting client {client_name}: {e}")
    
    AUDIO_CLIENTS.clear()
    log.info("All audio clients and rooms stopped")


async def restart_audio_async():
    """Перезапуск аудио системы с новыми конфигами"""
    log.info("Restarting audio system with new config...")
    
    # Сначала останавливаем все
    await stop_audio_async()
    
    # Небольшая задержка
    await asyncio.sleep(2)
    
    # Запускаем заново
    await start_audio_async()


def list_live_rooms() -> List[Dict[str, Any]]:
    """Список активных комнат"""
    return [room.to_dict() for room in AUDIO_ROOMS.values()]


def get_live_room(room_id: str) -> Optional[Dict[str, Any]]:
    """Получение информации о комнате"""
    room = AUDIO_ROOMS.get(room_id)
    if room:
        return room.to_dict()
    return None
