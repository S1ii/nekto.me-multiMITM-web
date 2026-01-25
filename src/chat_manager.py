from typing import Dict, List, Optional
from src.client import Client
from src.config import get_auto_search
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
    client_leader: Client  # Первый клиент в паре (всегда ищет первым)
    client_follower: Client  # Второй клиент в паре (ищет после лидера)
    leader_sex: str  # 'M' or 'F' - пол лидера
    follower_sex: str  # 'M' or 'F' - пол фолловера
    messages: List[dict] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    is_active: bool = False
    manual_control: Optional[str] = None  # 'L' or 'F' - кто под ручным управлением (Leader/Follower)
    is_paused: bool = False  # Поиск приостановлен
    
    def get_user_messages_count(self) -> int:
        """Возвращает количество только пользовательских сообщений (без system)"""
        return sum(1 for msg in self.messages if msg.get('from') in ('L', 'F'))
    
    def get_controlled_client(self) -> Optional[Client]:
        if self.manual_control == 'L':
            return self.client_leader
        elif self.manual_control == 'F':
            return self.client_follower
        return None
    
    def get_auto_client(self) -> Optional[Client]:
        if self.manual_control == 'L':
            return self.client_follower
        elif self.manual_control == 'F':
            return self.client_leader
        return None
    
    def get_pair_type(self) -> str:
        """Возвращает тип пары: MM, FF, MF, FM"""
        return f"{self.leader_sex}{self.follower_sex}"

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
    
    def _create_system_message(self, message: str) -> dict:
        """Создает системное сообщение"""
        return {
            "timestamp": datetime.now().isoformat(),
            "from": "system",
            "message": message,
            "is_manual": False
        }
    
    def create_room(self, client_leader: Client, client_follower: Client, 
                     leader_sex: str, follower_sex: str) -> DialogRoom:
        """Создает новую комнату для диалога"""
        room_id = generate_random_id()
        is_paused = not get_auto_search()
        room = DialogRoom(
            id=room_id,
            client_leader=client_leader,
            client_follower=client_follower,
            leader_sex=leader_sex,
            follower_sex=follower_sex,
            is_paused=is_paused
        )
        self.rooms[room_id] = room
        
        # Привязываем обработчики событий
        self._setup_client_handlers(client_leader, room, 'L')  # Leader
        self._setup_client_handlers(client_follower, room, 'F')  # Follower
        
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
        # Только Leader начинает поиск (если не на паузе)
        if client.sex_in_room == 'L' and not room.is_paused:
            system_msg = self._create_system_message(f"{room.leader_sex} searching...")
            room.messages.append(system_msg)
            await self._broadcast_message(room, system_msg)
            
            await client.search()
            await self._broadcast_room_update(room)
        elif client.sex_in_room == 'L' and room.is_paused:
             # Если поиск отключен, сообщаем об этом
            system_msg = self._create_system_message(f"Auto-search disabled. Waiting for manual start.")
            room.messages.append(system_msg)
            await self._broadcast_message(room, system_msg)
            await self._broadcast_room_update(room)
    
    async def _on_dialog_opened(self, data: Dict, client: Client, room: DialogRoom):
        """Диалог открыт"""
        # ВАЖНО: Если пауза - не активируем диалог
        if room.is_paused:
            # Закрываем диалог так как мы на паузе
            if hasattr(client, 'dialog_id'):
                payload = {"action": "anon.leaveDialog", "dialogId": client.dialog_id}
                if client.is_connected():
                    await client.safe_emit("action", data=payload)
                delattr(client, 'dialog_id')
            return
        
        room.is_active = True
        room.start_time = datetime.now()
        room.messages = []  # Очищаем при новом диалоге
        
        # Определяем пол клиента для сообщения
        client_sex = room.leader_sex if client.sex_in_room == 'L' else room.follower_sex
        
        # Системное сообщение
        system_msg = self._create_system_message(f"{client_sex} found dialog")
        room.messages.append(system_msg)
        await self._broadcast_message(room, system_msg)
        
        # Если Leader нашел диалог, запускаем поиск для Follower (если не на паузе)
        if client.sex_in_room == 'L' and not room.is_paused:
            other_client = room.client_follower
            if not hasattr(other_client, 'dialog_id'):
                search_msg = self._create_system_message(f"{room.follower_sex} searching...")
                room.messages.append(search_msg)
                await self._broadcast_message(room, search_msg)
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
        await client.safe_emit("action", payload)
        
        # ВАЖНО: Обрабатываем сообщение только если это НЕ наш собственный клиент
        # Это предотвращает дублирование - каждое сообщение обрабатывается только получателем
        if sender_id == client.id:
            return  # Пропускаем свои сообщения
        
        # Определяем от кого пришло сообщение (по роли в комнате)
        is_from_leader = client.sex_in_room == 'F'  # Если мы Follower, значит получили от Leader
        
        # Определяем пол отправителя для UI
        sender_sex = room.leader_sex if is_from_leader else room.follower_sex
        
        # Сохраняем сообщение ОДИН раз
        message_entry = {
            "timestamp": datetime.now().isoformat(),
            "from": sender_sex,  # Показываем реальный пол (M/F)
            "role": "L" if is_from_leader else "F",  # Роль в паре
            "sender_id": sender_id,
            "message": message,
            "is_manual": False  # Это сообщение от реального собеседника, не наше ручное
        }
        room.messages.append(message_entry)
        
        # Определяем другого клиента в комнате
        other_client = room.client_follower if client.sex_in_room == 'L' else room.client_leader
        other_role = 'F' if client.sex_in_room == 'L' else 'L'
        
        # КЛЮЧЕВАЯ ЛОГИКА: Пересылаем только если другой клиент НЕ под ручным управлением
        # Если под ручным управлением - сообщения идут только в UI, бот не отвечает
        if room.manual_control != other_role:
            if hasattr(other_client, 'dialog_id') and other_client.is_connected():
                payload = {
                    "action": "anon.message",
                    "dialogId": other_client.dialog_id,
                    "randomId": generate_random_id(),
                    "message": message,
                    "fileId": None,
                }
                await other_client.safe_emit("action", data=payload)
        
        # Отправляем обновление в UI ОДИН раз (всегда показываем входящие)
        await self._broadcast_message(room, message_entry)
    
    async def _on_typing(self, data: Dict, client: Client, room: DialogRoom):
        """Обработка индикатора печати"""
        other_client = room.client_follower if client.sex_in_room == 'L' else room.client_leader
        
        if hasattr(other_client, 'dialog_id') and other_client.is_connected():
            payload = {
                "action": "dialog.setTyping",
                "dialogId": other_client.dialog_id,
                "voice": data.get("voice"),
                "typing": data.get("typing")
            }
            await other_client.safe_emit("action", data=payload)
    
    async def _on_dialog_closed(self, data: Dict, client: Client, room: DialogRoom):
        """Диалог закрыт"""
        # Определяем, кто закрыл диалог (роль и пол)
        closer_role = client.sex_in_room  # 'L' or 'F'
        closer_sex = room.leader_sex if closer_role == 'L' else room.follower_sex
        other_client = room.client_follower if closer_role == 'L' else room.client_leader
        other_role = 'F' if closer_role == 'L' else 'L'
        other_sex = room.follower_sex if closer_role == 'L' else room.leader_sex
        
        # Если мы под ручным управлением и закрылся НЕ наш клиент — игнорируем
        if room.manual_control and room.manual_control != closer_role:
            system_msg = self._create_system_message(
                f"Interlocutor for {closer_sex} left. Your dialog ({room.manual_control}) stays active."
            )
            room.messages.append(system_msg)
            await self._broadcast_message(room, system_msg)
            # Важно: НЕ закрываем диалог у other_client и НЕ сбрасываем room.is_active
            return

        # В остальных случаях (ручное управление не включено или закрыл наш подконтрольный) — закрываем всё
        # MITM логика: показываем пол ДРУГОГО клиента (так как для собеседника other это выглядит как если бы other ушел)
        if room.is_active:
            system_msg = self._create_system_message(f"{other_sex} closed dialog")
            room.messages.append(system_msg)
            await self._broadcast_message(room, system_msg)
            
            self._save_room_log(room)
            room.is_active = False
            room.manual_control = None

        # Закрываем диалог у другого клиента
        if hasattr(other_client, 'dialog_id'):
            payload = {"action": "anon.leaveDialog", "dialogId": other_client.dialog_id}
            if other_client.is_connected():
                await other_client.safe_emit("action", data=payload)
            delattr(other_client, 'dialog_id')
        
        # Удаляем dialog_id у клиента, который закрыл
        if hasattr(client, 'dialog_id'):
            delattr(client, 'dialog_id')
        
        # Запускаем поиск только для Leader (если не на паузе)
        # Follower начнет поиск автоматически когда Leader найдет диалог (в _on_dialog_opened)
        if not room.is_paused:
            await asyncio.sleep(1)
            
            search_msg = self._create_system_message(f"{room.leader_sex} searching...")
            room.messages.append(search_msg)
            await self._broadcast_message(room, search_msg)
            await room.client_leader.search()
        
        await self._broadcast_room_update(room)
    
    async def send_manual_message(self, room_id: str, role: str, message: str) -> bool:
        """Отправка сообщения в ручном режиме
        Args:
            role: 'L' for Leader or 'F' for Follower
        """
        room = self.rooms.get(room_id)
        if not room or not room.is_active:
            return False
        
        client = room.client_leader if role == 'L' else room.client_follower
        client_sex = room.leader_sex if role == 'L' else room.follower_sex
        
        if not hasattr(client, 'dialog_id'):
            return False
        
        # Проверяем подключение перед отправкой
        if not client.is_connected():
            self.logger.warning(f"Клиент {role} ({client_sex}) не подключен, сообщение не отправлено")
            return False
        
        payload = {
            "action": "anon.message",
            "dialogId": client.dialog_id,
            "randomId": generate_random_id(),
            "message": message,
            "fileId": None,
        }
        success = await client.safe_emit("action", data=payload)
        if not success:
            return False
        
        # Записываем сообщение
        message_entry = {
            "timestamp": datetime.now().isoformat(),
            "from": client_sex,  # Показываем реальный пол
            "role": role,
            "sender_id": client.id,
            "message": message,
            "is_manual": True
        }
        room.messages.append(message_entry)
        await self._broadcast_message(room, message_entry)
        
        return True
    
    async def toggle_manual_control(self, room_id: str, role: str) -> bool:
        """Переключение ручного управления
        Args:
            role: 'L' for Leader or 'F' for Follower
        """
        room = self.rooms.get(room_id)
        if not room or not room.is_active:
            return False
        
        # Определяем клиентов
        controlled_client = room.client_leader if role == 'L' else room.client_follower
        controlled_sex = room.leader_sex if role == 'L' else room.follower_sex
        other_client = room.client_follower if role == 'L' else room.client_leader
        other_role = 'F' if role == 'L' else 'L'
        other_sex = room.follower_sex if role == 'L' else room.leader_sex
        
        if room.manual_control == role:
            # Выключаем ручное управление
            room.manual_control = None
            system_msg = self._create_system_message(f"{controlled_sex} bot enabled")
        else:
            # Включаем ручное управление
            room.manual_control = role
            
            # Закрываем диалог у другого клиента (который НЕ под управлением)
            if hasattr(other_client, 'dialog_id'):
                payload = {"action": "anon.leaveDialog", "dialogId": other_client.dialog_id}
                if other_client.is_connected():
                    await other_client.safe_emit("action", data=payload)
                delattr(other_client, 'dialog_id')
            
            system_msg = self._create_system_message(
                f"{controlled_sex} manual control enabled. {other_sex} dialog closed."
            )
        
        room.messages.append(system_msg)
        await self._broadcast_message(room, system_msg)
        await self._broadcast_room_update(room)
        return True
    
    async def force_close_dialog(self, room_id: str) -> bool:
        """Принудительное закрытие диалога"""
        room = self.rooms.get(room_id)
        if not room or not room.is_active:
            return False
        
        system_msg = self._create_system_message("Dialog force closed by admin")
        room.messages.append(system_msg)
        await self._broadcast_message(room, system_msg)
        
        self._save_room_log(room)
        room.is_active = False
        room.manual_control = None
        
        # Закрываем диалог у обоих клиентов
        for client in [room.client_leader, room.client_follower]:
            if hasattr(client, 'dialog_id'):
                payload = {"action": "anon.leaveDialog", "dialogId": client.dialog_id}
                if client.is_connected():
                    await client.safe_emit("action", data=payload)
                delattr(client, 'dialog_id')
        
        await self._broadcast_room_update(room)
        
        # Запускаем поиск только для Leader (если не на паузе)
        if not room.is_paused:
            await asyncio.sleep(1)
            
            search_msg = self._create_system_message(f"{room.leader_sex} searching...")
            room.messages.append(search_msg)
            await self._broadcast_message(room, search_msg)
            await room.client_leader.search()
        
        await self._broadcast_room_update(room)
        return True
    
    async def restart_search(self, room_id: str) -> bool:
        """Остановить текущий поиск/диалог и начать заново"""
        room = self.rooms.get(room_id)
        if not room:
            return False
        
        system_msg = self._create_system_message("Search restarted by admin")
        room.messages.append(system_msg)
        await self._broadcast_message(room, system_msg)
        
        # Если был активный диалог, сохраняем лог
        if room.is_active:
            self._save_room_log(room)
        
        room.is_active = False
        room.manual_control = None
        
        # Закрываем диалоги если они были открыты
        for client in [room.client_leader, room.client_follower]:
            if hasattr(client, 'dialog_id'):
                if client.is_connected():
                    payload = {"action": "anon.leaveDialog", "dialogId": client.dialog_id}
                    await client.safe_emit("action", data=payload)
                delattr(client, 'dialog_id')
        
        await self._broadcast_room_update(room)
        
        # Запускаем новый поиск только для Leader (если не на паузе)
        if not room.is_paused:
            await asyncio.sleep(1)
            
            search_msg = self._create_system_message(f"{room.leader_sex} searching...")
            room.messages.append(search_msg)
            await self._broadcast_message(room, search_msg)
            await room.client_leader.search()
        
        await self._broadcast_room_update(room)
        return True
    
    async def toggle_pause(self, room_id: str) -> bool:
        """Переключение паузы поиска"""
        room = self.rooms.get(room_id)
        if not room:
            return False
        
        room.is_paused = not room.is_paused
        
        if room.is_paused:
            # Остановить поиск - закрыть все активные диалоги
            system_msg = self._create_system_message("Search paused by admin")
            room.messages.append(system_msg)
            await self._broadcast_message(room, system_msg)
            
            # Если был активный диалог, сохраняем лог
            if room.is_active:
                self._save_room_log(room)
            
            room.is_active = False
            room.manual_control = None
            
            # Отменяем активный поиск и закрываем диалоги
            for client in [room.client_leader, room.client_follower]:
                # Отменяем поиск если он активен
                if client.is_connected():
                    try:
                        payload = {"action": "search.stop"}
                        await client.safe_emit("action", data=payload)
                    except Exception:
                        pass
                
                # Закрываем диалог если он был открыт
                if hasattr(client, 'dialog_id'):
                    if client.is_connected():
                        payload = {"action": "anon.leaveDialog", "dialogId": client.dialog_id}
                        await client.safe_emit("action", data=payload)
                    delattr(client, 'dialog_id')
        else:
            # Возобновить поиск
            system_msg = self._create_system_message("Search resumed by admin")
            room.messages.append(system_msg)
            await self._broadcast_message(room, system_msg)
            
            # Запускаем поиск для Leader
            await asyncio.sleep(0.5)
            
            search_msg = self._create_system_message(f"{room.leader_sex} searching...")
            room.messages.append(search_msg)
            await self._broadcast_message(room, search_msg)
            await room.client_leader.search()
        
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
            "pair_type": room.get_pair_type(),
            "leader_token": room.client_leader.token[:10],
            "follower_token": room.client_follower.token[:10],
            "leader_sex": room.leader_sex,
            "follower_sex": room.follower_sex,
            "start_time": room.start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "duration": int((datetime.now() - room.start_time).total_seconds()),
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
            "messages_count": room.get_user_messages_count(),
            "is_paused": room.is_paused,
            "pair_type": room.get_pair_type(),
            "leader_sex": room.leader_sex,
            "follower_sex": room.follower_sex,
            "leader_connected": hasattr(room.client_leader, 'id'),
            "follower_connected": hasattr(room.client_follower, 'id'),
            "leader_in_dialog": hasattr(room.client_leader, 'dialog_id'),
            "follower_in_dialog": hasattr(room.client_follower, 'dialog_id'),
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
            "messages_count": room.get_user_messages_count(),
            "is_paused": room.is_paused,
            "pair_type": room.get_pair_type(),
            "leader_sex": room.leader_sex,
            "follower_sex": room.follower_sex,
            "messages": room.messages[-50:],  # Последние 50 сообщений
            "start_time": room.start_time.isoformat() if room.is_active else None,
            "leader_token": room.client_leader.token[:10],
            "follower_token": room.client_follower.token[:10],
            "leader_connected": hasattr(room.client_leader, 'id'),
            "follower_connected": hasattr(room.client_follower, 'id'),
            "leader_in_dialog": hasattr(room.client_leader, 'dialog_id'),
            "follower_in_dialog": hasattr(room.client_follower, 'dialog_id'),
        }
    
    def get_all_rooms_status(self) -> List[dict]:
        """Получение статуса всех комнат"""
        return [self.get_room_status(room_id) for room_id in self.rooms.keys()]
    
    async def stop_all_searches(self):
        """Остановка всех поисков во всех комнатах"""
        self.logger.info("Stopping all searches...")
        
        for room in self.rooms.values():
            if room.is_active:
                # Закрываем активные диалоги
                for client in [room.client_leader, room.client_follower]:
                    if hasattr(client, 'dialog_id') and client.is_connected():
                        try:
                            payload = {"action": "anon.leaveDialog", "dialogId": client.dialog_id}
                            await client.safe_emit("action", data=payload)
                        except Exception as e:
                            self.logger.error(f"Error leaving dialog: {e}")
                        
                        if hasattr(client, 'dialog_id'):
                            delattr(client, 'dialog_id')
                
                # Сохраняем лог если были сообщения
                if room.messages:
                    self._save_room_log(room)
            
            room.is_active = False
            room.is_paused = True
        
        self.logger.info("All searches stopped")
    
    async def disconnect_all(self):
        """Отключение всех клиентов"""
        self.logger.info("Disconnecting all clients...")
        
        clients_to_disconnect = set()
        for room in self.rooms.values():
            clients_to_disconnect.add(room.client_leader)
            clients_to_disconnect.add(room.client_follower)
        
        for client in clients_to_disconnect:
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception as e:
                self.logger.error(f"Error disconnecting client {client.token[:10]}: {e}")
        
        self.logger.info(f"Disconnected {len(clients_to_disconnect)} clients")