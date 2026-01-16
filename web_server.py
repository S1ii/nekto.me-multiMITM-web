from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
import uvicorn
import asyncio
import logging
import os

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

@app.get("/rooms")
async def get_rooms():
    return manager.get_all_rooms_status()

@app.get("/rooms/{room_id}")
async def get_room(room_id: str):
    status = manager.get_room_status(room_id)
    if not status:
        raise HTTPException(status_code=404, detail="Room not found")
    return status

if __name__ == "__main__":
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_level="warning"
    )