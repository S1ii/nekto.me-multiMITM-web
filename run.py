from src.chat import Chat
from src.config import get_clients, get_debug

import asyncio
import logging
import warnings

# Подавляем все ошибки от socketio и engineio
logging.getLogger('socketio').setLevel(logging.CRITICAL)
logging.getLogger('engineio').setLevel(logging.CRITICAL)
logging.getLogger('socketio.client').setLevel(logging.CRITICAL)
logging.getLogger('engineio.client').setLevel(logging.CRITICAL)

# Подавляем предупреждения asyncio о незавершенных задачах
warnings.filterwarnings("ignore", category=RuntimeWarning, module="asyncio")

async def main() -> None:
    chat = Chat()
    for client in get_clients():
        chat.add_member(client)    
    await chat.start()

if __name__ == "__main__":
    get_debug()
    # Подавляем вывод исключений из незавершенных задач
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        # Закрываем все задачи без вывода ошибок
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.close()