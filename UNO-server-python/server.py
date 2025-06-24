import asyncio
import websockets
import json
from collections import defaultdict

PORT = 3000

# 事件列表
EVENTS = [
    'CREATE_ROOM',
    'JOIN_ROOM',
    'LEAVE_ROOM',
    'DISSOLVE_ROOM',
    'CREATE_USER',
    'START_GAME',
    'OUT_OF_THE_CARD',
    'GET_ONE_CARD',
    'NEXT_TURN',
    'SUBMIT_COLOR',
    'UNO'
]

# 客户端集合
clients = set()

# 事件处理器注册表
controllers = {}

# 事件分发
async def handle_event(event_type, data, websocket, wss):
    handler = controllers.get(event_type)
    if handler:
        await handler(data, websocket, wss)
    else:
        await websocket.send(json.dumps({
            'message': f'未知事件: {event_type}',
            'type': 'ERROR',
            'data': None
        }))

# 事件处理器示例（需后续完善）
async def create_room(data, ws, wss):
    await ws.send(json.dumps({
        'message': '房间创建成功',
        'type': 'RES_CREATE_ROOM',
        'data': None
    }))

# 注册所有事件（后续需完善每个事件的处理逻辑）
for event in EVENTS:
    controllers[event] = create_room  # 先全部指向 create_room 占位

async def handler(websocket, path):
    clients.add(websocket)
    try:
        await websocket.send(json.dumps({
            'message': '欢迎来到UNO世界！',
        }))
        async for message in websocket:
            try:
                msg = json.loads(message)
                event_type = msg.get('type')
                data = msg.get('data')
                await handle_event(event_type, data, websocket, clients)
            except Exception as e:
                await websocket.send(json.dumps({'message': str(e), 'type': 'ERROR', 'data': None}))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.remove(websocket)

async def main():
    async with websockets.serve(handler, '0.0.0.0', PORT):
        print(f'Server started on ws://0.0.0.0:{PORT}')
        await asyncio.Future()  # run forever

if __name__ == '__main__':
    asyncio.run(main()) 