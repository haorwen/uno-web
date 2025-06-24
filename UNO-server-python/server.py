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

# 辅助函数
async def send(ws, data):
    try:
        await ws.send(json.dumps(data))
    except Exception as e:
        pass

def get_room_players_info(room):
    return [{ 'id': p.id, 'name': p.name } for p in room.players]

async def emit_all_players(room, data):
    for p in room.players:
        await send(p.socket, data)

# JOIN_ROOM
async def join_room(data, ws, wss):
    room_code = data.get('roomCode')
    user_info = data.get('userInfo')
    room = room_collection.get(room_code)
    if not room:
        await send(ws, {
            'message': '房间不存在',
            'type': 'RES_JOIN_ROOM',
            'data': None
        })
        return
    if room.status == 'GAMING':
        await send(ws, {
            'message': '该房间已开始游戏',
            'type': 'RES_JOIN_ROOM',
            'data': None
        })
        return
    if room.status == 'END':
        await send(ws, {
            'message': '该房间游戏已结束',
            'type': 'RES_JOIN_ROOM',
            'data': None
        })
        return
    # 检查是否已在房间
    for p in room.players:
        if p.id == user_info['id']:
            await send(ws, {
                'message': '您已在房间中',
                'type': 'RES_JOIN_ROOM',
                'data': None
            })
            return
    player = Player(user_info, ws)
    room.players.append(player)
    # 通知所有玩家
    await emit_all_players(room, {
        'message': f'玩家 {user_info["name"]} 进入',
        'type': 'PLAYER_LIST_UPDATE',
        'data': get_room_players_info(room)
    })
    await send(ws, {
        'message': '加入房间成功',
        'type': 'RES_JOIN_ROOM',
        'data': {
            'code': room.code,
            'status': room.status,
            'players': get_room_players_info(room)
        }
    })

# LEAVE_ROOM
async def leave_room(data, ws, wss):
    room_code = data.get('roomCode')
    user_info = data.get('userInfo')
    room = room_collection.get(room_code)
    if not room:
        await send(ws, {
            'message': '房间不存在',
            'type': 'RES_LEAVE_ROOM',
            'data': None
        })
        return
    idx = None
    for i, p in enumerate(room.players):
        if p.id == user_info['id']:
            idx = i
            break
    if idx is not None:
        room.players.pop(idx)
        # 如果只剩 1 人，结束游戏
        if len(room.players) < 2:
            room.status = 'END'
            await emit_all_players(room, {
                'message': '人数不足，游戏结束',
                'type': 'GAME_OVER',
                'data': None
            })
        else:
            await emit_all_players(room, {
                'message': f'玩家 {user_info["name"]} 离开房间',
                'type': 'PLAYER_LIST_UPDATE',
                'data': get_room_players_info(room)
            })
        await send(ws, {
            'message': '您已离开房间',
            'type': 'RES_LEAVE_ROOM',
            'data': None
        })
    else:
        await send(ws, {
            'message': '您不在房间中',
            'type': 'RES_LEAVE_ROOM',
            'data': None
        })

# DISSOLVE_ROOM
async def dissolve_room(data, ws, wss):
    code = data
    room = room_collection.get(code)
    if room:
        await emit_all_players(room, {
            'message': '房间已解散',
            'type': 'RES_DISSOLVE_ROOM',
            'data': None
        })
        del room_collection[code]
    await send(ws, {
        'message': '房间已解散',
        'type': 'RES_DISSOLVE_ROOM',
        'data': None
    })

# UNO 牌型和发牌逻辑
UNO_COLORS = ['red', 'yellow', 'green', 'blue']
UNO_NUMBERS = list(range(0, 10))
UNO_ACTIONS = ['skip', 'reverse', 'draw2']
UNO_WILDS = ['wild', 'wild_draw4']

def generate_uno_deck():
    deck = []
    # 普通牌
    for color in UNO_COLORS:
        deck.append({'color': color, 'value': 0})  # 0 只有一张
        for n in range(1, 10):
            deck.append({'color': color, 'value': n})
            deck.append({'color': color, 'value': n})  # 1-9 各两张
        for action in UNO_ACTIONS:
            deck.append({'color': color, 'value': action})
            deck.append({'color': color, 'value': action})  # action 各两张
    # 万能牌
    for _ in range(4):
        deck.append({'color': 'black', 'value': 'wild'})
        deck.append({'color': 'black', 'value': 'wild_draw4'})
    random.shuffle(deck)
    return deck

def deal_cards(deck, num_players, cards_per_player=7):
    hands = []
    for _ in range(num_players):
        hand = [deck.pop() for _ in range(cards_per_player)]
        hands.append(hand)
    return hands

# START_GAME
async def start_game(data, ws, wss):
    room_code = data
    room = room_collection.get(room_code)
    if not room:
        await send(ws, {
            'message': '房间不存在',
            'type': 'RES_START_GAME',
            'data': None
        })
        return
    if len(room.players) < 2:
        await send(ws, {
            'message': '当前人数不足两人，无法开始游戏',
            'type': 'RES_START_GAME',
            'data': None
        })
        return
    # 初始化房间状态
    room.status = 'GAMING'
    room.game_cards = generate_uno_deck()
    hands = deal_cards(room.game_cards, len(room.players))
    for i, player in enumerate(room.players):
        player.cards = hands[i]
        player.uno = False
    # 翻第一张牌做为起始牌
    while True:
        first_card = room.game_cards.pop()
        if first_card['color'] != 'black':
            room.last_card = first_card
            break
        else:
            room.game_cards.insert(0, first_card)  # 万能牌放回底部
    room.order = 0
    # 通知所有玩家
    for i, player in enumerate(room.players):
        await send(player.socket, {
            'message': '游戏开始，您的手牌如下',
            'type': 'GAME_START',
            'data': {
                'userCards': player.cards,
                'firstCard': room.last_card,
                'players': get_room_players_info(room),
                'order': room.order
            }
        })
    await emit_all_players(room, {
        'message': '游戏已开始',
        'type': 'RES_START_GAME',
        'data': None
    })

# GET_ONE_CARD
async def get_one_card(data, ws, wss):
    room_code = data
    room = room_collection.get(room_code)
    if not room:
        await send(ws, {
            'message': '房间不存在',
            'type': 'RES_GET_ONE_CARD',
            'data': None
        })
        return
    player = next((p for p in room.players if p.socket == ws), None)
    if not player:
        await send(ws, {
            'message': '玩家不存在',
            'type': 'RES_GET_ONE_CARD',
            'data': None
        })
        return
    if not room.game_cards:
        await send(ws, {
            'message': '牌堆已空',
            'type': 'RES_GET_ONE_CARD',
            'data': None
        })
        return
    card = room.game_cards.pop()
    player.cards.append(card)
    # 如果玩家手牌大于1且UNO状态为True，重置UNO状态
    if len(player.cards) > 1 and player.uno:
        player.uno = False
    await send(ws, {
        'message': '摸牌成功',
        'type': 'RES_GET_ONE_CARD',
        'data': {
            'userCards': player.cards,
            'card': card
        }
    })

# NEXT_TURN
async def next_turn(data, ws, wss):
    room_code = data
    room = room_collection.get(room_code)
    if not room:
        await send(ws, {
            'message': '房间不存在',
            'type': 'RES_NEXT_TURN',
            'data': None
        })
        return
    # 轮到下一个玩家
    room.order = (room.order + 1) % len(room.players)
    await emit_all_players(room, {
        'message': '进入下一回合',
        'type': 'NEXT_TURN',
        'data': {
            'order': room.order,
            'players': get_room_players_info(room),
            'lastCard': room.last_card
        }
    })

# 事件注册
for event in EVENTS:
    if event == 'CREATE_ROOM':
        controllers[event] = create_room
    elif event == 'CREATE_USER':
        controllers[event] = create_user
    elif event == 'JOIN_ROOM':
        controllers[event] = join_room
    elif event == 'LEAVE_ROOM':
        controllers[event] = leave_room
    elif event == 'DISSOLVE_ROOM':
        controllers[event] = dissolve_room
    elif event == 'START_GAME':
        controllers[event] = start_game
    elif event == 'GET_ONE_CARD':
        controllers[event] = get_one_card
    elif event == 'NEXT_TURN':
        controllers[event] = next_turn
    else:
        async def not_impl(data, ws, wss, event=event):
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