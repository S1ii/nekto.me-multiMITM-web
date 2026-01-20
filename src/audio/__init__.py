# Global debug flag for audio module
DEBUG_MODE = False

def set_debug_mode(enabled: bool):
    """Set debug mode for audio module logging"""
    global DEBUG_MODE
    DEBUG_MODE = enabled

from src.audio.audio_manager import (
    start_audio_async,
    list_live_rooms,
    get_live_room,
    get_all_audio_status,
    stop_audio_async,
    restart_audio_async,
)

__all__ = [
    "start_audio_async",
    "list_live_rooms",
    "get_live_room",
    "get_all_audio_status",
    "stop_audio_async",
    "restart_audio_async",
    "set_debug_mode",
]
