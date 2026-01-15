from abc import ABC
from typing import Dict
from src.client import Client

from src.utils import generate_random_id

import structlog
import asyncio
import json
import os
from datetime import datetime

class BaseChat(ABC):
    
    def add_member(self, client: Client) -> None:
        ...

    async def start(self) -> None:
        ...

class Chat(BaseChat):
    def __init__(self):
        self.members = list()
        self.messages_buffer = dict()
        self.m_client_found_dialog = False  # Флаг для отслеживания, нашел ли клиент M собеседника
        
        # Для логирования чатов
        self.chat_history = dict()  # Хранит историю сообщений для каждого клиента
        self.chat_start_time = dict()  # Время начала каждого диалога
        self.logs_directory = "chat_logs"  # Директория для сохранения логов
        
        # Создаем директорию для логов, если её нет
        if not os.path.exists(self.logs_directory):
            os.makedirs(self.logs_directory)

        self.logger = structlog.get_logger()

    def get_logger(self, client: Client):
        return self.logger.bind(token=client.token[:10])

    def save_chat_log(self, client: Client):
        """Сохраняет историю чата в отдельный файл"""
        if not self.chat_history.get(client):
            return
        
        # Формируем имя файла с timestamp и токеном клиента
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        token_short = client.token[:10]
        sex = client.search_parameters.get("mySex", "Unknown")
        filename = f"chat_{timestamp}_{token_short}_{sex}.json"
        filepath = os.path.join(self.logs_directory, filename)
        
        # Подготавливаем данные для сохранения
        chat_data = {
            "client_token": token_short,
            "client_sex": sex,
            "client_age": client.search_parameters.get("myAge"),
            "wish_sex": client.search_parameters.get("wishSex"),
            "wish_age": client.search_parameters.get("wishAge"),
            "start_time": self.chat_start_time.get(client, datetime.now()).isoformat(),
            "end_time": datetime.now().isoformat(),
            "messages": self.chat_history[client]
        }
        
        # Сохраняем в JSON файл
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(chat_data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Chat log saved to {filename}", filepath=filepath, messages_count=len(self.chat_history[client]))
            print(f"[{token_short}] Чат сохранен в {filename} ({len(self.chat_history[client])} сообщений)")
        except Exception as e:
            self.logger.error(f"Failed to save chat log", error=str(e), filepath=filepath)

    def add_member(self, client: Client):
        self.logger.debug("Add client to chat members...", client=client)
        self.members.append(client)
        client.add_event_handler("messages.new", self.on_message)
        client.add_event_handler("dialog.opened", self.on_dialog_opened)
        client.add_event_handler("dialog.closed", self.on_dialog_closed)
        client.add_event_handler("auth.successToken", self.on_auth)
        client.add_event_handler("dialog.typing", self.on_typing)
        self.messages_buffer[client] = list()
        self.chat_history[client] = list()  # Инициализируем историю для клиента
        self.logger.debug("Added client to members list", client=client, members=self.members)

    async def on_typing(self, data: Dict[str, any], client: Client) -> None:
        log = self.get_logger(client)
        for member in self.members:
            log.debug(f"Sending typing event to client.", typing=data.get("typing"))
            if member.id == client.id: 
                log.debug(f"Member is client, *skip*")
                continue
            if not hasattr(member, "dialog_id"): 
                log.debug(f"Member has not opened dialog!")
                continue
            payload = {
                "action":"dialog.setTyping",
                "dialogId":member.dialog_id,
                "voice":data.get("voice"),
                "typing":data.get("typing")
            }
            log.debug("Member sent the typing event", payload=payload)
            await member.emit("action", data=payload)

    async def on_auth(self, _, client: Client) -> None:
        log = self.get_logger(client)
        if hasattr(client, "dialog_id"):
            log.debug("Client has open dialog.")
            payload = {
                "action":"anon.leaveDialog",
                "dialogId":client.dialog_id
            }
            log.debug("Client close current dialog!")
            return await client.emit(
                "action",
                data=payload, 
            )
        
        # Проверяем пол клиента
        client_sex = client.search_parameters.get("mySex")
        
        # Если клиент женского пола (F), ждем пока клиент M не найдет собеседника
        if client_sex == "F" and not self.m_client_found_dialog:
            log.debug("Client with sex F waits for client M to find dialog.")
            print(f"[{client.token[:10]}] Ожидаю пока клиент M найдет собеседника...")
            return
        
        log.debug("Client begins searching the dialog.")
        print(f"[{client.token[:10]}] Ищу собеседника")
        await client.search()

    async def on_message(self, data: Dict[str, any], client: Client) -> None:
        log = self.get_logger(client)
        payload = {
            "action":"anon.readMessages",
            "dialogId":client.dialog_id,
            "lastMessageId":data.get("id")
        }
        await client.emit("action", payload)
        log.debug("Client reads messages.")
        message = data.get('message')
        sender = data.get("senderId")
        
        # Записываем сообщение в историю чата
        message_entry = {
            "timestamp": datetime.now().isoformat(),
            "sender": "interlocutor" if sender != client.id else "client",
            "sender_id": sender,
            "message": message
        }
        self.chat_history[client].append(message_entry)
        
        if client.id == sender: return
        print(f"[{client.token[:10]}]: {message}")
        self.messages_buffer[client].append(message)
        log.debug("Add message to messages buffer.", message=message, messages_buffer=self.messages_buffer)
        for member in self.members:
            log.debug(f"Sending message to client.")
            if member.id == client.id: 
                log.debug(f"Member is client, *skip*")
                continue
            if not hasattr(member, "dialog_id"): 
                log.debug(f"Member has not opened dialog!")
                continue
            payload = {
                "action":"anon.message",
                "dialogId":member.dialog_id,
                "randomId":generate_random_id(),
                "message":data.get("message"),
                "fileId":None,
            }
            log.debug("Member sent the message.")
            await member.emit("action", data=payload)

    async def on_dialog_opened(self, data: Dict[str, any], client: Client) -> None:
        print(f"[{client.token[:10]}] Нашел собеседника!")
        log = self.get_logger(client)
        log.debug("Client found the dialog.", data=data)
        
        # Записываем время начала диалога
        self.chat_start_time[client] = datetime.now()
        # Очищаем предыдущую историю и начинаем новую
        self.chat_history[client] = []
        
        # Проверяем пол клиента
        client_sex = client.search_parameters.get("mySex")
        
        # Если клиент мужского пола (M) нашел собеседника, устанавливаем флаг
        if client_sex == "M" and not self.m_client_found_dialog:
            self.m_client_found_dialog = True
            log.debug("Client M found dialog, starting search for client F")
            
            # Запускаем поиск для всех клиентов F
            for member in self.members:
                member_sex = member.search_parameters.get("mySex")
                if member_sex == "F" and hasattr(member, "id") and not hasattr(member, "dialog_id"):
                    log.debug("Starting search for client F", member=member)
                    print(f"[{member.token[:10]}] Начинаю поиск собеседника")
                    await member.search()
        
        for member, messages in self.messages_buffer.items():
            if member == client:
                continue
            log.debug("Member will receive messages from the messages buffer", messages=messages, member=member)
            for message in messages:
                payload = {
                    "action":"anon.message",
                    "dialogId":member.dialog_id,
                    "randomId":generate_random_id(),
                    "message":message,
                    "fileId":None,
                }
                await member.emit("action", data=payload)

    async def on_dialog_closed(self, _: Dict[str, any], client: Client) -> None:
        print(f"[{client.token[:10]}] Закрыл диалог.")
        log = self.get_logger(client)
        log.debug("Client closed dialog.")
        
        # Сохраняем историю чата перед закрытием
        if self.chat_history.get(client) and len(self.chat_history[client]) > 0:
            self.save_chat_log(client)
        
        # Сбрасываем флаг, если клиент M закрыл диалог
        client_sex = client.search_parameters.get("mySex")
        if client_sex == "M":
            self.m_client_found_dialog = False
            log.debug("Client M closed dialog, resetting flag")
        
        self.messages_buffer[client].clear()
        for member in self.members:
            if not hasattr(member, "id"):
                continue
            if member.id == client.id: 
                continue
            if not hasattr(member, "dialog_id"):
                continue
            payload = {
                "action":"anon.leaveDialog",
                "dialogId":member.dialog_id,
            }
            self.messages_buffer[member].clear()
            await member.emit("action", data=payload)
        
        # Только клиент M начинает поиск автоматически
        # Клиент F будет ждать, пока M не найдет нового собеседника
        if client_sex == "M":
            log.debug("Client M begins searching new dialog.")
            await client.search()
        else:
            log.debug("Client F waits for client M to find new dialog.")
            print(f"[{client.token[:10]}] Ожидаю пока клиент M найдет собеседника...")

    async def start(self) -> None:
        """Запуск чата с обработкой ошибок подключения"""
        connected_members = []
        
        for member in self.members:
            try:
                await member.connect()
                connected_members.append(member)
            except Exception as e:
                self.logger.error(
                    f"Не удалось подключить клиента {member.token[:10]}: {e}",
                    token=member.token[:10],
                    error=str(e)
                )
                print(f"[{member.token[:10]}] ❌ Ошибка подключения: {e}")
        
        if not connected_members:
            self.logger.error("Не удалось подключить ни одного клиента!")
            print("❌ Не удалось подключить ни одного клиента. Проверьте интернет-соединение.")
            return
        
        if len(connected_members) < len(self.members):
            print(f"⚠️ Подключено {len(connected_members)} из {len(self.members)} клиентов")
        
        await asyncio.gather(
            *[client.wait() for client in connected_members]
        )