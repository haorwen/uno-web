import asyncio
import websockets
import json
import random
import string
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

# 数据结构
class Player:
    def __init__(self, user_info, ws):
        self.id = user_info['id']
        self.name = user_info['name']
        self.socket = ws
        self.cards = []
        self.uno = False

class Room:
    def __init__(self, creator_info, ws, code):
        self.code = code
        self.status = 'WAITING'  # WAITING, GAMING, END
        self.players = [Player(creator_info, ws)]
        self.last_card = None
        self.game_cards = []
        self.order = 0

class User:
    def __init__(self, user_info):
        self.id = user_info['id']
        self.name = user_info['name']

# 全局集合
room_collection = {}
user_collection = {}

clients = set()
controllers = {}

def random_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

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

# CREATE_ROOM
async def create_room(data, ws, wss):
    code = random_code()
    while code in room_collection:
        code = random_code()
    room = Room(data, ws, code)
    room_collection[code] = room
    await ws.send(json.dumps({
        'message': '房间创建成功',
        'type': 'RES_CREATE_ROOM',
        'data': {
            'code': code,
            'status': room.status,
            'players': [{ 'id': p.id, 'name': p.name } for p in room.players]
        }
    }))

# CREATE_USER
async def create_user(data, ws, wss):
    key = data['id'] + data['name']
    if key in user_collection:
        await ws.send(json.dumps({
            'message': '人员已存在，请重新输入昵称',
            'type': 'RES_CREATE_USER',
            'data': None
        }))
        return
    user = User(data)
    user_collection[key] = user
    await ws.send(json.dumps({
        'message': '玩家信息创建成功',
        'type': 'RES_CREATE_USER',
        'data': { 'id': user.id, 'name': user.name }
    }))

# 事件注册
for event in EVENTS:
    if event == 'CREATE_ROOM':
        controllers[event] = create_room
    elif event == 'CREATE_USER':
        controllers[event] = create_user
    else:
        async def not_impl(data, ws, wss):
            await ws.send(json.dumps({'message': f'{event} 暂未实现', 'type': f'RES_{event}', 'data': None}))
        controllers[event] = not_impl

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