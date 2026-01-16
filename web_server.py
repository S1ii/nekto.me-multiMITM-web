from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager
import uvicorn
import asyncio
import logging
import os
import json
import glob
from datetime import datetime

from src.chat_manager import ChatManager
from src.client import Client
from src.config import get_clients

# Настройка минимального логирования
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

manager: Optional[ChatManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global manager
    manager = ChatManager()
    
    clients = list(get_clients())
    male_clients = [c for c in clients if c.search_parameters.get('mySex') == 'M']
    female_clients = [c for c in clients if c.search_parameters.get('mySex') == 'F']
    
    print("\n" + "="*60)
    print("🚀 NektoMe Chat Manager")
    print("="*60)
    
    # Создаем комнаты
    for i in range(min(len(male_clients), len(female_clients))):
        room = manager.create_room(male_clients[i], female_clients[i])
        print(f"  ✓ Room {i+1}: M:{male_clients[i].token[:10]} ↔ F:{female_clients[i].token[:10]}")
    
    # Подключаем клиентов
    all_clients = male_clients + female_clients
    connected = 0
    
    for client in all_clients:
        try:
            await client.connect()
            connected += 1
        except Exception as e:
            print(f"  ✗ Failed: {client.token[:10]} - {str(e)[:40]}")
    
    print(f"\n  📊 Connected: {connected}/{len(all_clients)} clients")
    print(f"  🌐 Dashboard: http://localhost:8000")
    print("="*60 + "\n")
    
    yield
    
    # Shutdown
    print("\n⏹ Shutting down...")

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

@app.get("/api/logs")
async def get_logs(search: str = "", sort: str = "newest"):
    """Get list of all log files with metadata"""
    logs = []
    
    if not os.path.exists(LOGS_DIR):
        return logs
    
    for filepath in glob.glob(os.path.join(LOGS_DIR, "*.json")):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            filename = os.path.basename(filepath)
            
            # Extract summary data
            log_summary = {
                "filename": filename,
                "room_id": data.get("room_id", "unknown"),
                "start_time": data.get("start_time"),
                "end_time": data.get("end_time"),
                "messages_count": data.get("messages_count", len(data.get("messages", []))),
                "client_m_token": data.get("client_m_token", "")[:8],
                "client_f_token": data.get("client_f_token", "")[:8],
                "file_size": os.path.getsize(filepath)
            }
            
            # Apply search filter
            if search:
                search_lower = search.lower()
                # Search in messages
                messages = data.get("messages", [])
                has_match = any(
                    search_lower in msg.get("message", "").lower() 
                    for msg in messages
                )
                # Also search in room_id and tokens
                if not has_match:
                    has_match = (
                        search_lower in log_summary["room_id"].lower() or
                        search_lower in log_summary["filename"].lower()
                    )
                if not has_match:
                    continue
            
            logs.append(log_summary)
            
        except (json.JSONDecodeError, IOError):
            continue
    
    # Sort logs
    if sort == "newest":
        logs.sort(key=lambda x: x.get("start_time") or "", reverse=True)
    elif sort == "oldest":
        logs.sort(key=lambda x: x.get("start_time") or "")
    elif sort == "messages":
        logs.sort(key=lambda x: x.get("messages_count", 0), reverse=True)
    
    return logs


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
    
    return {
        "total_logs": total_logs,
        "total_messages": total_messages,
        "oldest_date": oldest_date,
        "newest_date": newest_date,
        "total_size": total_size
    }


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
        host="0.0.0.0", 
        port=8000,
        log_level="warning"
    )