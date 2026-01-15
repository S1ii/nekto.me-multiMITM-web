from typing import Dict, List, Optional
from src.client import Client
from src.utils import generate_random_id
import structlog
import asyncio
import json
import os
import logging
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class DialogRoom:
    """Представляет один диалог между двумя клиентами"""
    id: str
    client_m: Client  # Мужской клиент
    client_f: Client  # Женский клиент
    messages: List[dict] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    is_active: bool = False
    manual_control: Optional[str] = None  # 'M' or 'F' - кто под ручным управлением
    
    def get_controlled_client(self) -> Optional[Client]:
        if self.manual_control == 'M':
            return self.client_m
        elif self.manual_control == 'F':
            return self.client_f
        return None
    
    def get_auto_client(self) -> Optional[Client]:
        if self.manual_control == 'M':
            return self.client_f
        elif self.manual_control == 'F':
            return self.client_m
        return None

class ChatManager:
    """Управляет несколькими параллельными диалогами"""
    
    def __init__(self):
        self.rooms: Dict[str, DialogRoom] = {}
        # Отключаем verbose логирование
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)
        )
        self.logger = structlog.get_logger()
        self.logs_directory = "chat_logs"
        self.websocket_clients = set()  # Для real-time обновлений UI
        
        if not os.path.exists(self.logs_directory):
            os.makedirs(self.logs_directory)
    
    def create_room(self, client_m: Client, client_f: Client) -> DialogRoom:
        """Создает новую комнату для диалога"""
        room_id = generate_random_id()
        room = DialogRoom(
            id=room_id,
            client_m=client_m,
            client_f=client_f
        )
        self.rooms[room_id] = room
        
        # Привязываем обработчики событий
        self._setup_client_handlers(client_m, room, 'M')
        self._setup_client_handlers(client_f, room, 'F')
        
        return room
    
    def _setup_client_handlers(self, client: Client, room: DialogRoom, sex: str):
        """Настраивает обработчики событий для клиента в комнате"""
        client.room_id = room.id
        client.sex_in_room = sex
        
        client.add_event_handler("messages.new", 
            lambda data, c: self._on_message(data, c, room))
        client.add_event_handler("dialog.opened", 
            lambda data, c: self._on_dialog_opened(data, c, room))
        client.add_event_handler("dialog.closed", 
            lambda data, c: self._on_dialog_closed(data, c, room))
        client.add_event_handler("auth.successToken", 
            lambda data, c: self._on_auth(data, c, room))
        client.add_event_handler("dialog.typing", 
            lambda data, c: self._on_typing(data, c, room))
    
    async def _on_auth(self, data: Dict, client: Client, room: DialogRoom):
        """Обработка авторизации клиента"""
        # Только мужской клиент начинает поиск
        if client.sex_in_room == 'M':
            # Системное сообщение о начале поиска
            system_msg = {
                "timestamp": datetime.now().isoformat(),
                "from": "system",
                "message": f"{client.sex_in_room} searching...",
                "is_manual": False
            }
            room.messages.append(system_msg)
            await self._broadcast_message(room, system_msg)
            
            await client.search()
            await self._broadcast_room_update(room)
    
    async def _on_dialog_opened(self, data: Dict, client: Client, room: DialogRoom):
        """Диалог открыт"""
        room.is_active = True
        room.start_time = datetime.now()
        room.messages = []  # Очищаем при новом диалоге
        
        # Системное сообщение
        system_msg = {
            "timestamp": datetime.now().isoformat(),
            "from": "system",
            "message": f"{client.sex_in_room} found dialog",
            "is_manual": False
        }
        room.messages.append(system_msg)
        await self._broadcast_message(room, system_msg)
        
        # Если мужской клиент нашел диалог, запускаем поиск для женского
        if client.sex_in_room == 'M':
            other_client = room.client_f
            if not hasattr(other_client, 'dialog_id'):
                # Системное сообщение о начале поиска F
                search_msg_f = {
                    "timestamp": datetime.now().isoformat(),
                    "from": "system",
                    "message": "F searching...",
                    "is_manual": False
                }
                room.messages.append(search_msg_f)
                await self._broadcast_message(room, search_msg_f)
                await other_client.search()
        
        await self._broadcast_room_update(room)
    
    async def _on_message(self, data: Dict, client: Client, room: DialogRoom):
        """Обработка сообщения"""
        message = data.get('message')
        sender_id = data.get('senderId')
        
        # Отмечаем как прочитанное
        payload = {
            "action": "anon.readMessages",
            "dialogId": client.dialog_id,
            "lastMessageId": data.get("id")
        }
        await client.emit("action", payload)
        
        # ВАЖНО: Обрабатываем сообщение только если это НЕ наш собственный клиент
        # Это предотвращает дублирование - каждое сообщение обрабатывается только получателем
        if sender_id == client.id:
            return  # Пропускаем свои сообщения
        
        # Определяем от кого пришло сообщение
        is_from_m = client.sex_in_room == 'F'  # Если мы F, значит получили от M
        
        # Сохраняем сообщение ОДИН раз
        message_entry = {
            "timestamp": datetime.now().isoformat(),
            "from": "M" if is_from_m else "F",
            "sender_id": sender_id,
            "message": message,
            "is_manual": False  # Это сообщение от реального собеседника, не наше ручное
        }
        room.messages.append(message_entry)
        
        # Определяем другого клиента в комнате
        other_client = room.client_f if client.sex_in_room == 'M' else room.client_m
        
        # КЛЮЧЕВАЯ ЛОГИКА: Пересылаем только если другой клиент НЕ под ручным управлением
        # Если под ручным управлением - сообщения идут только в UI, бот не отвечает
        if room.manual_control != other_client.sex_in_room:
            if hasattr(other_client, 'dialog_id'):
                payload = {
                    "action": "anon.message",
                    "dialogId": other_client.dialog_id,
                    "randomId": generate_random_id(),
                    "message": message,
                    "fileId": None,
                }
                await other_client.emit("action", data=payload)
        
        # Отправляем обновление в UI ОДИН раз (всегда показываем входящие)
        await self._broadcast_message(room, message_entry)
    
    async def _on_typing(self, data: Dict, client: Client, room: DialogRoom):
        """Обработка индикатора печати"""
        other_client = room.client_f if client.sex_in_room == 'M' else room.client_m
        
        if hasattr(other_client, 'dialog_id'):
            payload = {
                "action": "dialog.setTyping",
                "dialogId": other_client.dialog_id,
                "voice": data.get("voice"),
                "typing": data.get("typing")
            }
            await other_client.emit("action", data=payload)
    
    async def _on_dialog_closed(self, data: Dict, client: Client, room: DialogRoom):
        """Диалог закрыт"""
        # Определяем, кто закрыл диалог
        closer_sex = client.sex_in_room
        other_client = room.client_f if closer_sex == 'M' else room.client_m
        
        # Если мы под ручным управлением и закрылся НЕ наш клиент — игнорируем
        if room.manual_control and room.manual_control != closer_sex:
            system_msg = {
                "timestamp": datetime.now().isoformat(),
                "from": "system",
                "message": f"Interlocutor for {closer_sex} left. Your dialog ({room.manual_control}) stays active.",
                "is_manual": False
            }
            room.messages.append(system_msg)
            await self._broadcast_message(room, system_msg)
            # Важно: НЕ закрываем диалог у other_client и НЕ сбрасываем room.is_active
            return

        # В остальных случаях (ручное управление не включено или закрыл наш подконтрольный) — закрываем всё
        if room.is_active:
            system_msg = {
                "timestamp": datetime.now().isoformat(),
                "from": "system",
                "message": f"{closer_sex} closed dialog",
                "is_manual": False
            }
            room.messages.append(system_msg)
            await self._broadcast_message(room, system_msg)
            
            self._save_room_log(room)
            room.is_active = False
            room.manual_control = None

        # Закрываем диалог у другого клиента
        if hasattr(other_client, 'dialog_id'):
            payload = {"action": "anon.leaveDialog", "dialogId": other_client.dialog_id}
            await other_client.emit("action", data=payload)
            delattr(other_client, 'dialog_id')
        
        # Удаляем dialog_id у клиента, который закрыл
        if hasattr(client, 'dialog_id'):
            delattr(client, 'dialog_id')
        
        # Запускаем поиск только для M
        # F начнет поиск автоматически когда M найдет диалог (в _on_dialog_opened)
        await asyncio.sleep(1)
        
        # Системное сообщение о начале поиска M
        search_msg_m = {
            "timestamp": datetime.now().isoformat(),
            "from": "system",
            "message": "M searching...",
            "is_manual": False
        }
        room.messages.append(search_msg_m)
        await self._broadcast_message(room, search_msg_m)
        await room.client_m.search()
        
        await self._broadcast_room_update(room)
    
    async def send_manual_message(self, room_id: str, sex: str, message: str) -> bool:
        """Отправка сообщения в ручном режиме"""
        room = self.rooms.get(room_id)
        if not room or not room.is_active:
            return False
        
        client = room.client_m if sex == 'M' else room.client_f
        
        if not hasattr(client, 'dialog_id'):
            return False
        
        payload = {
            "action": "anon.message",
            "dialogId": client.dialog_id,
            "randomId": generate_random_id(),
            "message": message,
            "fileId": None,
        }
        await client.emit("action", data=payload)
        
        # Записываем сообщение
        message_entry = {
            "timestamp": datetime.now().isoformat(),
            "from": sex,
            "sender_id": client.id,
            "message": message,
            "is_manual": True
        }
        room.messages.append(message_entry)
        await self._broadcast_message(room, message_entry)
        
        return True
    
    async def toggle_manual_control(self, room_id: str, sex: str) -> bool:
        """Переключение ручного управления"""
        room = self.rooms.get(room_id)
        if not room or not room.is_active:
            return False
        
        # Определяем клиентов
        controlled_client = room.client_m if sex == 'M' else room.client_f
        other_client = room.client_f if sex == 'M' else room.client_m
        
        if room.manual_control == sex:
            # Выключаем ручное управление - это уже не нужно, т.к. кнопки будут скрыты
            # Пока оставим для обратной совместимости
            room.manual_control = None
            system_msg = {
                "timestamp": datetime.now().isoformat(),
                "from": "system",
                "message": f"{sex} bot enabled",
                "is_manual": False
            }
        else:
            # Включаем ручное управление
            room.manual_control = sex
            
            # Закрываем диалог у другого клиента (который НЕ под управлением)
            if hasattr(other_client, 'dialog_id'):
                payload = {"action": "anon.leaveDialog", "dialogId": other_client.dialog_id}
                await other_client.emit("action", data=payload)
                delattr(other_client, 'dialog_id')
            
            system_msg = {
                "timestamp": datetime.now().isoformat(),
                "from": "system",
                "message": f"{sex} manual control enabled. {other_client.sex_in_room} dialog closed.",
                "is_manual": False
            }
        
        room.messages.append(system_msg)
        await self._broadcast_message(room, system_msg)
        await self._broadcast_room_update(room)
        return True
    
    async def force_close_dialog(self, room_id: str) -> bool:
        """Принудительное закрытие диалога"""
        room = self.rooms.get(room_id)
        if not room or not room.is_active:
            return False
        
        # Системное сообщение о принудительном закрытии
        system_msg = {
            "timestamp": datetime.now().isoformat(),
            "from": "system",
            "message": "Dialog force closed by admin",
            "is_manual": False
        }
        room.messages.append(system_msg)
        await self._broadcast_message(room, system_msg)
        
        self._save_room_log(room)
        room.is_active = False
        room.manual_control = None
        
        # Закрываем диалог у обоих клиентов
        for client in [room.client_m, room.client_f]:
            if hasattr(client, 'dialog_id'):
                payload = {"action": "anon.leaveDialog", "dialogId": client.dialog_id}
                await client.emit("action", data=payload)
                delattr(client, 'dialog_id')  # Удаляем dialog_id чтобы клиент мог начать новый поиск
        
        await self._broadcast_room_update(room)
        
        # Запускаем поиск только для M
        # F начнет поиск автоматически когда M найдет диалог (в _on_dialog_opened)
        await asyncio.sleep(1)
        
        # Системное сообщение о начале поиска M
        search_msg_m = {
            "timestamp": datetime.now().isoformat(),
            "from": "system",
            "message": "M searching...",
            "is_manual": False
        }
        room.messages.append(search_msg_m)
        await self._broadcast_message(room, search_msg_m)
        await room.client_m.search()
        
        await self._broadcast_room_update(room)
        return True
    
    async def restart_search(self, room_id: str) -> bool:
        """Остановить текущий поиск/диалог и начать заново"""
        room = self.rooms.get(room_id)
        if not room:
            return False
        
        # Системное сообщение о перезапуске
        system_msg = {
            "timestamp": datetime.now().isoformat(),
            "from": "system",
            "message": "Search restarted by admin",
            "is_manual": False
        }
        room.messages.append(system_msg)
        await self._broadcast_message(room, system_msg)
        
        # Если был активный диалог, сохраняем лог
        if room.is_active:
            self._save_room_log(room)
        
        room.is_active = False
        room.manual_control = None
        
        # Закрываем диалоги если они были открыты
        for client in [room.client_m, room.client_f]:
            if hasattr(client, 'dialog_id'):
                try:
                    payload = {"action": "anon.leaveDialog", "dialogId": client.dialog_id}
                    await client.emit("action", data=payload)
                except:
                    pass  # Игнорируем ошибки если диалог уже закрыт
                delattr(client, 'dialog_id')
        
        await self._broadcast_room_update(room)
        
        # Запускаем новый поиск только для M
        # F начнет поиск автоматически когда M найдет диалог
        await asyncio.sleep(1)
        
        # Системное сообщение о начале поиска M
        search_msg_m = {
            "timestamp": datetime.now().isoformat(),
            "from": "system",
            "message": "M searching...",
            "is_manual": False
        }
        room.messages.append(search_msg_m)
        await self._broadcast_message(room, search_msg_m)
        await room.client_m.search()
        
        await self._broadcast_room_update(room)
        return True
    
    def _save_room_log(self, room: DialogRoom):
        """Сохранение лога диалога"""
        if not room.messages:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"room_{timestamp}_{room.id[:8]}.json"
        filepath = os.path.join(self.logs_directory, filename)
        
        chat_data = {
            "room_id": room.id,
            "client_m_token": room.client_m.token[:10],
            "client_f_token": room.client_f.token[:10],
            "start_time": room.start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "messages_count": len(room.messages),
            "messages": room.messages
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(chat_data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Room log saved", filename=filename)
        except Exception as e:
            self.logger.error(f"Failed to save room log", error=str(e))
    
    async def _broadcast_room_update(self, room: DialogRoom):
        """Отправка обновления статуса комнаты всем подключенным WebSocket клиентам"""
        if not self.websocket_clients:
            return
        
        update = {
            "type": "room_update",
            "room_id": room.id,
            "is_active": room.is_active,
            "manual_control": room.manual_control,
            "messages_count": len(room.messages),
            "m_connected": hasattr(room.client_m, 'id'),
            "f_connected": hasattr(room.client_f, 'id'),
            "m_in_dialog": hasattr(room.client_m, 'dialog_id'),
            "f_in_dialog": hasattr(room.client_f, 'dialog_id'),
        }
        
        disconnected = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_json(update)
            except:
                disconnected.add(ws)
        
        self.websocket_clients -= disconnected
    
    async def _broadcast_message(self, room: DialogRoom, message: dict):
        """Отправка нового сообщения всем подключенным WebSocket клиентам"""
        if not self.websocket_clients:
            return
        
        update = {
            "type": "new_message",
            "room_id": room.id,
            "message": message
        }
        
        disconnected = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_json(update)
            except:
                disconnected.add(ws)
        
        self.websocket_clients -= disconnected
    
    def get_room_status(self, room_id: str) -> Optional[dict]:
        """Получение статуса комнаты"""
        room = self.rooms.get(room_id)
        if not room:
            return None
        
        return {
            "room_id": room.id,
            "is_active": room.is_active,
            "manual_control": room.manual_control,
            "messages_count": len(room.messages),
            "messages": room.messages[-50:],  # Последние 50 сообщений
            "start_time": room.start_time.isoformat() if room.is_active else None,
            "m_token": room.client_m.token[:10],
            "f_token": room.client_f.token[:10],
            "m_connected": hasattr(room.client_m, 'id'),
            "f_connected": hasattr(room.client_f, 'id'),
            "m_in_dialog": hasattr(room.client_m, 'dialog_id'),
            "f_in_dialog": hasattr(room.client_f, 'dialog_id'),
        }
    
    def get_all_rooms_status(self) -> List[dict]:
        """Получение статуса всех комнат"""
        return [self.get_room_status(room_id) for room_id in self.rooms.keys()]