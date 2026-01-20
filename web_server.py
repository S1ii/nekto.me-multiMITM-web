from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager, suppress
import uvicorn
import asyncio
import logging
import os
import json
import glob
import argparse
from datetime import datetime

from src.chat_manager import ChatManager
from src.client import Client
from src.config import get_clients
from src import config_manager
from src.audio import set_debug_mode as set_audio_debug_mode
from src.audio.audio_manager import (
    start_audio_async,
    AUDIO_LOGS_DIR,
    AUDIO_ROOMS,
    list_live_rooms,
    get_live_room,
    get_all_audio_status,
    stop_audio_async,
    restart_audio_async,
)
from src import search_index

# ============================================
# Command Line Arguments
# ============================================
def parse_args():
    parser = argparse.ArgumentParser(
        description="NektoMe Chat Manager - MITM сервер для перехвата чатов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python web_server.py              - Запустить полностью (чат + аудио)
  python web_server.py --chat       - Только текстовый чат
  python web_server.py --audio      - Только аудио чат
  python web_server.py --chat --audio - Чат и аудио
  python web_server.py --debug      - Полный режим с debug выводом
        """
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Включить текстовый чат и его логи"
    )
    parser.add_argument(
        "--audio",
        action="store_true",
        help="Включить аудио чат и его логи"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Включить расширенный debug вывод"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Хост для запуска сервера (по умолчанию: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Порт для запуска сервера (по умолчанию: 8000)"
    )
    
    args = parser.parse_args()
    
    # Если ни один режим не указан, включаем оба
    if not args.chat and not args.audio:
        args.chat = True
        args.audio = True
    
    return args

# Глобальные флаги режима работы
ARGS = parse_args()
MODE_CHAT = ARGS.chat
MODE_AUDIO = ARGS.audio
DEBUG_MODE = ARGS.debug

# Настройка режима отладки для аудио модуля
set_audio_debug_mode(DEBUG_MODE)

# Настройка логирования в зависимости от режима debug
if DEBUG_MODE:
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    logging.getLogger("uvicorn.access").setLevel(logging.DEBUG)
    logging.getLogger("uvicorn.error").setLevel(logging.DEBUG)
    logging.getLogger("websockets").setLevel(logging.DEBUG)
    logging.getLogger("socketio").setLevel(logging.DEBUG)
else:
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

manager: Optional[ChatManager] = None
audio_task: Optional[asyncio.Task] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global manager
    global audio_task
    
    print("\n" + "="*60)
    print("🚀 NektoMe Chat Manager")
    print("="*60)
    
    # Отображение активных режимов
    modes = []
    if MODE_CHAT:
        modes.append("💬 Чат")
    if MODE_AUDIO:
        modes.append("🎙️ Аудио")
    if DEBUG_MODE:
        modes.append("🐛 Debug")
    print(f"  Режимы: {' | '.join(modes)}")
    print("-"*60)
    
    if DEBUG_MODE:
        print(f"  [DEBUG] MODE_CHAT={MODE_CHAT}, MODE_AUDIO={MODE_AUDIO}")
        print(f"  [DEBUG] Host={ARGS.host}, Port={ARGS.port}")
    
    # Инициализация ChatManager (нужен всегда для WebSocket)
    manager = ChatManager()
    
    # Запуск текстового чата
    if MODE_CHAT:
        clients = list(get_clients())
        male_clients = [c for c in clients if c.search_parameters.get('mySex') == 'M']
        female_clients = [c for c in clients if c.search_parameters.get('mySex') == 'F']
        
        if DEBUG_MODE:
            print(f"  [DEBUG] Найдено клиентов: M={len(male_clients)}, F={len(female_clients)}")
        
        # Создаем комнаты
        for i in range(min(len(male_clients), len(female_clients))):
            room = manager.create_room(male_clients[i], female_clients[i])
            print(f"  ✓ Room {i+1}: M:{male_clients[i].token[:10]} ↔ F:{female_clients[i].token[:10]}")
        
        # Подключаем клиентов
        all_clients = male_clients + female_clients
        connected = 0
        
        for client in all_clients:
            try:
                if DEBUG_MODE:
                    print(f"  [DEBUG] Подключение клиента: {client.token[:10]}...")
                await client.connect()
                connected += 1
                if DEBUG_MODE:
                    print(f"  [DEBUG] Клиент {client.token[:10]} подключен успешно")
            except Exception as e:
                print(f"  ✗ Failed: {client.token[:10]} - {str(e)[:40]}")
                if DEBUG_MODE:
                    import traceback
                    traceback.print_exc()
        
        print(f"\n  📊 Text Chat: {connected}/{len(all_clients)} клиентов подключено")
    else:
        print("  ℹ️  Текстовый чат отключен (используйте --chat для включения)")
    
    # Запуск аудио чата
    if MODE_AUDIO:
        os.makedirs(AUDIO_LOGS_DIR, exist_ok=True)
        if DEBUG_MODE:
            print(f"  [DEBUG] Запуск аудио модуля...")
        audio_task = asyncio.create_task(start_audio_async())
        print("  🎙️  Audio Chat: запущен")
    else:
        print("  ℹ️  Аудио чат отключен (используйте --audio для включения)")
    
    # Initialize search index
    print("  🔍 Инициализация поискового индекса...")
    search_index.ensure_index()
    print(f"  ✓ Индекс готов ({search_index.get_index_stats()['indexed_documents']} документов)")
    
    print(f"\n  🌐 Dashboard: http://localhost:{ARGS.port}")
    print("="*60 + "\n")

    yield
    
    # Shutdown
    print("\n⏹ Shutting down...")
    if DEBUG_MODE:
        print("  [DEBUG] Останавливаем все сервисы...")
    
    if audio_task:
        if DEBUG_MODE:
            print("  [DEBUG] Останавливаем аудио задачу...")
        audio_task.cancel()
        with suppress(asyncio.CancelledError):
            await audio_task

app = FastAPI(title="NektoMe Chat Manager", lifespan=lifespan)

# Статические файлы
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Pydantic модели
class SendMessageRequest(BaseModel):
    room_id: str
    sex: str
    message: str

class ToggleControlRequest(BaseModel):
    room_id: str
    sex: str

class ForceCloseRequest(BaseModel):
    room_id: str

class RestartSearchRequest(BaseModel):
    room_id: str


# Маршруты
@app.get("/")
async def get_dashboard():
    """Отдает главную страницу дашборда"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    manager.websocket_clients.add(websocket)
    
    initial_state = {
        "type": "initial_state",
        "rooms": manager.get_all_rooms_status()
    }
    await websocket.send_json(initial_state)
    
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.websocket_clients.remove(websocket)

@app.post("/send-message")
async def send_message(request: SendMessageRequest):
    success = await manager.send_manual_message(
        request.room_id,
        request.sex,
        request.message
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to send message")
    
    return {"status": "ok"}

@app.post("/toggle-control")
async def toggle_control(request: ToggleControlRequest):
    success = await manager.toggle_manual_control(request.room_id, request.sex)
    
    if not success:
        raise HTTPException(status_code=404, detail="Room not found")
    
    return {"status": "ok"}

@app.post("/force-close")
async def force_close(request: ForceCloseRequest):
    success = await manager.force_close_dialog(request.room_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Room not found or not active")
    
    return {"status": "ok"}

@app.post("/restart-search")
async def restart_search(request: RestartSearchRequest):
    success = await manager.restart_search(request.room_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Room not found")
    
    return {"status": "ok"}


class TogglePauseRequest(BaseModel):
    room_id: str


@app.post("/toggle-pause")
async def toggle_pause(request: TogglePauseRequest):
    success = await manager.toggle_pause(request.room_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Room not found")
    
    return {"status": "ok"}

@app.get("/rooms")
async def get_rooms():
    return manager.get_all_rooms_status()

@app.get("/rooms/{room_id}")
async def get_room(room_id: str):
    status = manager.get_room_status(room_id)
    if not status:
        raise HTTPException(status_code=404, detail="Room not found")
    return status


# ============================================
# Chat Logs API Endpoints
# ============================================

LOGS_DIR = os.path.join(os.path.dirname(__file__), "chat_logs")
AUDIO_LOGS_DIR = os.path.join(os.path.dirname(__file__), "audio_logs")

@app.get("/api/logs")
async def get_logs(page: int = 1, limit: int = 50, sort: str = "newest"):
    """Get paginated list of log files with metadata"""
    logs = []
    
    if not os.path.exists(LOGS_DIR):
        return {"logs": [], "total": 0, "page": page, "limit": limit, "totalPages": 0}
    
    # Get list of all log files
    all_files = glob.glob(os.path.join(LOGS_DIR, "*.json"))
    
    # Sort files by modification time for consistent ordering
    if sort == "newest":
        all_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    elif sort == "oldest":
        all_files.sort(key=lambda x: os.path.getmtime(x))
    
    total = len(all_files)
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    
    # Paginate
    start = (page - 1) * limit
    end = start + limit
    paginated_files = all_files[start:end]
    
    for filepath in paginated_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            filename = os.path.basename(filepath)
            messages = data.get("messages", [])
            
            log_summary = {
                "filename": filename,
                "room_id": data.get("room_id", "unknown"),
                "start_time": data.get("start_time"),
                "end_time": data.get("end_time"),
                "messages_count": data.get("messages_count", len(messages)),
                "duration": data.get("duration", 0),
                "file_size": os.path.getsize(filepath)
            }
            logs.append(log_summary)
            
        except (json.JSONDecodeError, IOError):
            continue
    
    # Sort by messages count if requested (need to re-sort after loading)
    if sort == "messages":
        logs.sort(key=lambda x: x.get("messages_count", 0), reverse=True)
    
    return {
        "logs": logs,
        "total": total,
        "page": page,
        "limit": limit,
        "totalPages": total_pages
    }


@app.get("/api/logs/search")
async def search_logs(q: str = "", page: int = 1, limit: int = 50):
    """Full-text search across all log messages using Whoosh"""
    if not q or not q.strip():
        return {"results": [], "total": 0, "page": page, "limit": limit, "totalPages": 0}
    
    return search_index.search_logs(q, page=page, limit=limit)


@app.post("/api/logs/rebuild-index")
async def rebuild_search_index():
    """Rebuild the search index (admin endpoint)"""
    search_index.rebuild_index()
    stats = search_index.get_index_stats()
    return {"status": "ok", "indexed": stats["indexed_documents"]}


@app.get("/api/logs/stats")
async def get_logs_stats():
    """Get statistics about all chat logs"""
    total_logs = 0
    total_messages = 0
    oldest_date = None
    newest_date = None
    total_size = 0
    
    if not os.path.exists(LOGS_DIR):
        return {
            "total_logs": 0,
            "total_messages": 0,
            "oldest_date": None,
            "newest_date": None,
            "date_range": "-",
            "total_size": 0
        }
    
    for filepath in glob.glob(os.path.join(LOGS_DIR, "*.json")):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            total_logs += 1
            total_messages += data.get("messages_count", len(data.get("messages", [])))
            total_size += os.path.getsize(filepath)
            
            start_time = data.get("start_time")
            if start_time:
                if oldest_date is None or start_time < oldest_date:
                    oldest_date = start_time
                if newest_date is None or start_time > newest_date:
                    newest_date = start_time
                    
        except (json.JSONDecodeError, IOError):
            continue
    
    # Format date_range
    date_range = "-"
    if oldest_date and newest_date:
        try:
            oldest_dt = datetime.fromisoformat(oldest_date)
            newest_dt = datetime.fromisoformat(newest_date)
            date_range = f"{oldest_dt.strftime('%d.%m.%Y')} - {newest_dt.strftime('%d.%m.%Y')}"
        except:
            date_range = f"{oldest_date} - {newest_date}"
    
    return {
        "total_logs": total_logs,
        "total_messages": total_messages,
        "oldest_date": oldest_date,
        "newest_date": newest_date,
        "date_range": date_range,
        "total_size": total_size
    }


# ============================================
# Audio Logs API Endpoints
# ============================================

@app.get("/api/audio/logs")
async def get_audio_logs():
    logs = []

    if not os.path.exists(AUDIO_LOGS_DIR):
        return logs

    for filepath in glob.glob(os.path.join(AUDIO_LOGS_DIR, "*.mp3")):
        filename = os.path.basename(filepath)
        stat = os.stat(filepath)
        logs.append(
            {
                "filename": filename,
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "file_size": stat.st_size,
            }
        )

    logs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return logs


@app.get("/api/audio/logs/{filename}")
async def get_audio_log_file(filename: str):
    if not filename.endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Invalid audio file")

    file_path = os.path.join(AUDIO_LOGS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio log not found")

    return FileResponse(file_path, media_type="audio/mpeg", filename=filename)


@app.get("/api/audio/live")
async def get_audio_live_rooms():
    return list_live_rooms()


@app.get("/api/audio/status")
async def get_audio_status():
    """Получение статуса всех аудио клиентов для UI"""
    return get_all_audio_status()


class AudioRoomActionRequest(BaseModel):
    room_id: str


@app.post("/api/audio/force-close")
async def audio_force_close(request: AudioRoomActionRequest):
    """Принудительное закрытие аудио диалога и перезапуск поиска"""
    room = AUDIO_ROOMS.get(request.room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Audio room not found")
    
    await room.force_close()
    return {"status": "ok", "message": "Dialog force closed, search restarted"}


@app.post("/api/audio/toggle-pause")
async def audio_toggle_pause(request: AudioRoomActionRequest):
    """Переключение паузы для аудио комнаты"""
    room = AUDIO_ROOMS.get(request.room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Audio room not found")
    
    is_paused = await room.toggle_pause()
    return {"status": "ok", "is_paused": is_paused}


@app.get("/api/audio/stream/{room_id}")
async def stream_audio(room_id: str):
    """Stream live audio from active recording"""
    from fastapi.responses import FileResponse
    
    room = AUDIO_ROOMS.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Audio room not found")
    
    if not room.file_path or not room.file_path.exists():
        raise HTTPException(status_code=404, detail="Recording file not found")
    
    # Return the file with proper headers for streaming
    return FileResponse(
        path=str(room.file_path),
        media_type="audio/webm",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

# ============================================
# Config Management API
# ============================================

@app.get("/api/config/text-clients")
async def get_text_clients():
    """Получить список текстовых клиентов"""
    return {"clients": config_manager.get_text_clients_config()}


@app.get("/api/config/audio-clients")
async def get_audio_clients():
    """Получить список аудио клиентов"""
    return {"clients": config_manager.get_audio_clients_config()}


class TextClientUpdate(BaseModel):
    name: str
    token: str
    ua: str
    sex: Optional[str] = None
    wish_sex: Optional[str] = None
    age: Optional[str] = None
    wish_age: Optional[str] = None
    role: Optional[bool] = None
    adult: Optional[bool] = None
    wish_role: Optional[str] = None


class AudioClientUpdate(BaseModel):
    name: str
    token: str
    ua: str
    sex: Optional[str] = None
    search_sex: Optional[str] = None
    age: Optional[str] = None
    search_age: Optional[str] = None
    wait_for: Optional[str] = None
    proxy: Optional[str] = None


@app.post("/api/config/text-client")
async def update_text_client(client: TextClientUpdate):
    """Создать или обновить текстовый клиент"""
    config_manager.update_text_client(client.name, client.dict())
    return {"status": "ok", "message": f"Client '{client.name}' updated"}


@app.post("/api/config/audio-client")
async def update_audio_client(client: AudioClientUpdate):
    """Создать или обновить аудио клиент"""
    config_manager.update_audio_client(client.name, client.dict())
    return {"status": "ok", "message": f"Client '{client.name}' updated"}


@app.delete("/api/config/text-client/{name}")
async def delete_text_client(name: str):
    """Удалить текстовый клиент"""
    config_manager.delete_text_client(name)
    return {"status": "ok", "message": f"Client '{name}' deleted"}


@app.delete("/api/config/audio-client/{name}")
async def delete_audio_client(name: str):
    """Удалить аудио клиент"""
    config_manager.delete_audio_client(name)
    return {"status": "ok", "message": f"Client '{name}' deleted"}


@app.post("/api/config/reload")
async def reload_config():
    """
    Полная перезагрузка конфигов:
    1. Останавливает все поиски (текст + аудио) - только если режим активен
    2. Перечитывает config.ini
    3. Создает новые клиенты
    4. Возобновляет работу
    """
    global manager, audio_task
    
    text_clients_count = 0
    
    if DEBUG_MODE:
        print("[DEBUG] Начинаем перезагрузку конфигурации...")
    
    # Остановка всех текстовых клиентов (только если режим чата активен)
    if MODE_CHAT and manager:
        if DEBUG_MODE:
            print("[DEBUG] Останавливаем текстовые клиенты...")
        await manager.stop_all_searches()
        await manager.disconnect_all()
    
    # Остановка аудио системы (только если режим аудио активен)
    if MODE_AUDIO:
        if audio_task and not audio_task.done():
            if DEBUG_MODE:
                print("[DEBUG] Останавливаем аудио задачу...")
            audio_task.cancel()
            try:
                await audio_task
            except asyncio.CancelledError:
                pass
        
        await stop_audio_async()
    
    # Пауза перед перезапуском
    await asyncio.sleep(2)
    
    # Перезапуск текстовых клиентов (только если режим чата активен)
    if MODE_CHAT:
        if DEBUG_MODE:
            print("[DEBUG] Перезапускаем текстовые клиенты...")
        manager = ChatManager()
        clients = list(get_clients())
        male_clients = [c for c in clients if c.search_parameters.get('mySex') == 'M']
        female_clients = [c for c in clients if c.search_parameters.get('mySex') == 'F']
        
        for i in range(min(len(male_clients), len(female_clients))):
            manager.create_room(male_clients[i], female_clients[i])
        
        all_clients = male_clients + female_clients
        for client in all_clients:
            try:
                await client.connect()
                if DEBUG_MODE:
                    print(f"[DEBUG] Клиент {client.token[:10]} подключен")
            except Exception as e:
                print(f"Error connecting {client.token[:10]}: {e}")
        
        text_clients_count = len(all_clients)
    
    # Перезапуск аудио (только если режим аудио активен)
    if MODE_AUDIO:
        if DEBUG_MODE:
            print("[DEBUG] Перезапускаем аудио модуль...")
        audio_task = asyncio.create_task(start_audio_async())
    
    if DEBUG_MODE:
        print("[DEBUG] Перезагрузка конфигурации завершена")
    
    return {
        "status": "ok",
        "message": "Config reloaded successfully",
        "text_clients": text_clients_count if MODE_CHAT else "disabled",
        "text_rooms": len(manager.rooms) if MODE_CHAT else "disabled",
        "audio_enabled": MODE_AUDIO,
    }


async def stream_audio_file(room_id: str, file_path: str):
    chunk_size = 8192
    with open(file_path, "rb") as audio_file:
        audio_file.seek(0, os.SEEK_END)
        while True:
            data = audio_file.read(chunk_size)
            if data:
                yield data
                continue
            if not get_live_room(room_id):
                break
            await asyncio.sleep(0.5)


@app.get("/api/audio/live/{room_id}")
async def get_audio_live_stream(room_id: str):
    room = get_live_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Live room not found")
    file_path = room.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return StreamingResponse(
        stream_audio_file(room_id, file_path),
        media_type="audio/mpeg",
    )


@app.get("/api/logs/{filename}")
async def get_log(filename: str):
    """Get full content of a specific log file"""
    # Security: prevent directory traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    filepath = os.path.join(LOGS_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Log not found")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Error reading log: {str(e)}")


@app.delete("/api/logs/{filename}")
async def delete_log(filename: str):
    """Delete a specific log file"""
    # Security: prevent directory traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    filepath = os.path.join(LOGS_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Log not found")
    
    try:
        os.remove(filepath)
        return {"status": "ok", "message": f"Log {filename} deleted"}
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"Error deleting log: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(
        app, 
        host=ARGS.host, 
        port=ARGS.port,
        log_level="debug" if DEBUG_MODE else "warning"
    )