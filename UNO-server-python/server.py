import asyncio
import websockets
import json
import random
import string
from collections import defaultdict
import time

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
        self.id = user_info.get('id')
        self.name = user_info.get('name')
        self.socket = ws
        self.cards = []
        self.uno = False
        self.lastCard = None
        self.socketInstance = ws  # 兼容 TS

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'cards': self.cards,
            'uno': self.uno,
            'lastCard': self.lastCard,
            'socketInstance': None  # 不传递 socket
        }

class Room:
    def __init__(self, creator_info, ws, code):
        self.roomId = code
        self.roomName = f"UNO房间{code}"
        self.owner = Player(creator_info, ws).to_dict()
        self.roomCode = code
        self.players = [Player(creator_info, ws)]
        self.gameCards = []
        self.userCards = {}
        self.lastCard = None
        self.order = 0
        self.status = 'WAITING'
        self.winnerOrder = []
        self.createTime = int(time.time() * 1000)
        self.startTime = -1
        self.endTime = -1
        self.accumulation = 0
        self.playOrder = 1

    def to_dict(self):
        return {
            'roomId': self.roomId,
            'roomName': self.roomName,
            'owner': self.owner,
            'roomCode': self.roomCode,
            'players': [p.to_dict() for p in self.players],
            'gameCards': [],  # 不传递真实牌堆
            'userCards': {},  # 兼容 TS
            'lastCard': self.lastCard,
            'order': self.order,
            'status': self.status,
            'winnerOrder': [p.to_dict() for p in self.winnerOrder],
            'createTime': self.createTime,
            'startTime': self.startTime,
            'endTime': self.endTime,
            'accumulation': self.accumulation,
            'playOrder': self.playOrder
        }

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
    await send(ws, {
        'type': 'RES_CREATE_ROOM',
        'data': room.to_dict(),
        'message': '房间创建成功'
    })
    await update_player_list(room, f"玩家 {room.players[0].name} 进入")

# CREATE_USER
async def create_user(data, ws, wss):
    key = data['id'] + data['name']
    if key in user_collection:
        await send(ws, {
            'type': 'RES_CREATE_USER',
            'data': None,
            'message': '人员已存在，请重新输入昵称'
        })
        return
    user = User(data)
    user_collection[key] = user
    await send(ws, {
        'type': 'RES_CREATE_USER',
        'data': { 'id': user.id, 'name': user.name },
        'message': '玩家信息创建成功'
    })

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
            'type': 'RES_JOIN_ROOM',
            'data': None,
            'message': '房间不存在'
        })
        return
    if room.status == 'GAMING':
        await send(ws, {
            'type': 'RES_JOIN_ROOM',
            'data': None,
            'message': '该房间已开始游戏'
        })
        return
    if room.status == 'END':
        await send(ws, {
            'type': 'RES_JOIN_ROOM',
            'data': None,
            'message': '该房间游戏已结束'
        })
        return
    for p in room.players:
        if p.id == user_info['id']:
            await send(ws, {
                'type': 'RES_JOIN_ROOM',
                'data': None,
                'message': '您已在房间中'
            })
            return
    player = Player(user_info, ws)
    room.players.append(player)
    await update_player_list(room, f"玩家 {user_info['name']} 进入")
    await send(ws, {
        'type': 'RES_JOIN_ROOM',
        'data': room.to_dict(),
        'message': '加入房间成功'
    })

# LEAVE_ROOM
async def leave_room(data, ws, wss):
    room_code = data.get('roomCode')
    user_info = data.get('userInfo')
    room = room_collection.get(room_code)
    if not room:
        await send(ws, {
            'type': 'RES_LEAVE_ROOM',
            'data': None,
            'message': '房间不存在'
        })
        return
    idx = None
    for i, p in enumerate(room.players):
        if p.id == user_info['id']:
            idx = i
            break
    if idx is not None:
        room.players.pop(idx)
        await update_player_list(room, f"玩家 {user_info['name']} 离开房间")
        if len(room.players) < 2:
            room.status = 'END'
            room.endTime = int(time.time() * 1000)
            room.winnerOrder = sorted(room.players, key=lambda x: len(x.cards))
            await emit_all_players(room, {
                'type': 'GAME_IS_OVER',
                'data': {
                    'winnerOrder': [p.to_dict() for p in room.winnerOrder],
                    'endTime': room.endTime
                },
                'message': '人数不足，游戏结束'
            })
        await send(ws, {
            'type': 'RES_LEAVE_ROOM',
            'data': None,
            'message': '您已离开房间'
        })
    else:
        await send(ws, {
            'type': 'RES_LEAVE_ROOM',
            'data': None,
            'message': '您不在房间中'
        })

# DISSOLVE_ROOM
async def dissolve_room(data, ws, wss):
    code = data
    room = room_collection.get(code)
    if room:
        await emit_all_players(room, {
            'type': 'RES_DISSOLVE_ROOM',
            'data': None,
            'message': '房间已解散'
        })
        del room_collection[code]
    await send(ws, {
        'type': 'RES_DISSOLVE_ROOM',
        'data': None,
        'message': '房间已解散'
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
            'type': 'RES_START_GAME',
            'data': None,
            'message': '房间不存在'
        })
        return
    if len(room.players) < 2:
        await send(ws, {
            'type': 'RES_START_GAME',
            'data': None,
            'message': '当前人数不足两人，无法开始游戏'
        })
        return
    room.status = 'GAMING'
    room.startTime = int(time.time() * 1000)
    room.gameCards = generate_uno_deck()
    hands = deal_cards(room.gameCards, len(room.players))
    for i, player in enumerate(room.players):
        player.cards = hands[i]
        player.uno = False
        player.lastCard = None
        room.userCards[player.id] = player.cards
    while True:
        first_card = room.gameCards.pop()
        if first_card['color'] != 'black':
            room.lastCard = first_card
            break
        else:
            room.gameCards.insert(0, first_card)
    room.order = 0
    for i, player in enumerate(room.players):
        await send(player.socket, {
            'type': 'GAME_IS_START',
            'data': {
                'roomInfo': room.to_dict(),
                'userCards': player.cards
            },
            'message': '游戏开始啦'
        })
    await emit_all_players(room, {
        'type': 'RES_START_GAME',
        'data': None,
        'message': '游戏已开始'
    })

# 发送 DEAL_CARDS（摸牌/罚牌）
async def send_deal_cards(player, num):
    await send(player.socket, {
        'type': 'RES_DEAL_CARDS',
        'data': player.cards,
        'message': f'获得卡牌 {num} 张'
    })

# 发送 CHANGE_UNO_STATUS
async def send_uno_status(player, status):
    await send(player.socket, {
        'type': 'CHANGE_UNO_STATUS',
        'data': {
            'playerId': player.id,
            'playerName': player.name,
            'unoStatus': status
        },
        'message': None
    })

# 发送 SELECT_COLOR
async def send_select_color(player):
    await send(player.socket, {
        'type': 'SELECT_COLOR',
        'data': None,
        'message': '请选择颜色'
    })

# GET_ONE_CARD
async def get_one_card(data, ws, wss):
    room_code = data
    room = room_collection.get(room_code)
    if not room:
        await send(ws, {
            'type': 'RES_GET_ONE_CARD',
            'data': None,
            'message': '房间不存在'
        })
        return
    player = next((p for p in room.players if p.socket == ws), None)
    if not player:
        await send(ws, {
            'type': 'RES_GET_ONE_CARD',
            'data': None,
            'message': '玩家不存在'
        })
        return
    if not room.gameCards:
        await send(ws, {
            'type': 'RES_GET_ONE_CARD',
            'data': None,
            'message': '牌堆已空'
        })
        return
    card = room.gameCards.pop()
    player.cards.append(card)
    if len(player.cards) > 1 and player.uno:
        player.uno = False
        await send_uno_status(player, False)
    await send(ws, {
        'type': 'RES_GET_ONE_CARD',
        'data': {
            'userCards': player.cards,
            'card': card
        },
        'message': '摸牌成功'
    })
    await send_deal_cards(player, 1)

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
            'lastCard': room.lastCard
        }
    })

# 校验出牌是否合法
def is_valid_play(card, last_card):
    if card['color'] == 'black':
        return True
    if card['color'] == last_card['color']:
        return True
    if card['value'] == last_card['value']:
        return True
    return False

# OUT_OF_THE_CARD
async def out_of_the_card(data, ws, wss):
    room_code = data.get('roomCode')
    cards_index = data.get('cardsIndex')
    room = room_collection.get(room_code)
    if not room:
        await send(ws, {
            'type': 'RES_OUT_OF_THE_CARD',
            'data': None,
            'message': '房间不存在'
        })
        return
    player = next((p for p in room.players if p.socket == ws), None)
    if not player:
        await send(ws, {
            'type': 'RES_OUT_OF_THE_CARD',
            'data': None,
            'message': '玩家不存在'
        })
        return
    if not cards_index:
        await send(ws, {
            'type': 'RES_OUT_OF_THE_CARD',
            'data': None,
            'message': '请选择要出的牌'
        })
        return
    try:
        out_cards = [player.cards[i] for i in cards_index]
    except Exception:
        await send(ws, {
            'type': 'RES_OUT_OF_THE_CARD',
            'data': None,
            'message': '出牌索引无效'
        })
        return
    last_card = room.lastCard
    if not all(is_valid_play(card, last_card) for card in out_cards):
        await send(ws, {
            'type': 'RES_OUT_OF_THE_CARD',
            'data': None,
            'message': '出牌不符合规则，请重新出牌'
        })
        return
    for i in sorted(cards_index, reverse=True):
        player.cards.pop(i)
    room.lastCard = out_cards[-1]
    skip = False
    draw_count = 0
    reverse = False
    if room.lastCard['color'] == 'black':
        await send_select_color(player)
        if room.lastCard['value'] == 'wild_draw4':
            draw_count = 4
            skip = True
        elif room.lastCard['value'] == 'wild':
            skip = True
    elif room.lastCard['value'] == 'skip':
        skip = True
    elif room.lastCard['value'] == 'draw2':
        draw_count = 2
        skip = True
    elif room.lastCard['value'] == 'reverse':
        reverse = True
    if len(player.cards) == 0:
        room.status = 'END'
        room.endTime = int(time.time() * 1000)
        room.winnerOrder = sorted(room.players, key=lambda x: len(x.cards))
        await emit_all_players(room, {
            'type': 'GAME_IS_OVER',
            'data': {
                'winnerOrder': [p.to_dict() for p in room.winnerOrder],
                'endTime': room.endTime
            },
            'message': f'玩家 {player.name} 赢得了游戏！'
        })
        return
    elif len(player.cards) == 1 and not player.uno:
        player.cards.extend([room.gameCards.pop(), room.gameCards.pop()])
        await send(ws, {
            'type': 'RES_OUT_OF_THE_CARD',
            'data': player.cards,
            'message': '请记得UNO！获得手牌2张'
        })
        await send_deal_cards(player, 2)
    else:
        await send(ws, {
            'type': 'RES_OUT_OF_THE_CARD',
            'data': player.cards,
            'message': '出牌成功'
        })
    if reverse and len(room.players) > 2:
        room.players.reverse()
        room.order = (len(room.players) - room.order - 1) % len(room.players)
    if skip:
        room.order = (room.order + 2) % len(room.players)
    else:
        room.order = (room.order + 1) % len(room.players)
    if draw_count > 0:
        next_player = room.players[room.order]
        for _ in range(draw_count):
            if room.gameCards:
                next_player.cards.append(room.gameCards.pop())
        await send(next_player.socket, {
            'type': 'DRAW_PENALTY',
            'data': next_player.cards,
            'message': f'你被罚摸{draw_count}张牌'
        })
        await send_deal_cards(next_player, draw_count)
    await emit_all_players(room, {
        'type': 'NEXT_TURN',
        'data': {
            'order': room.order,
            'players': [p.to_dict() for p in room.players],
            'lastCard': room.lastCard
        },
        'message': f'玩家 {player.name} 出牌'
    })

# 辅助：推送 UPDATE_ROOM_INFO
async def update_room_info(room, message=None):
    await emit_all_players(room, {
        'type': 'UPDATE_ROOM_INFO',
        'data': room.to_dict(),
        'message': message or '房间信息已更新'
    })

# SUBMIT_COLOR 响应 RES_SUBMIT_COLOR
async def submit_color(data, ws, wss):
    color = data.get('color')
    room_code = data.get('roomCode')
    room = room_collection.get(room_code)
    if not room:
        await send(ws, {
            'type': 'RES_SUBMIT_COLOR',
            'data': None,
            'message': '房间不存在'
        })
        return
    if not room.lastCard or room.lastCard['color'] != 'black':
        await send(ws, {
            'type': 'RES_SUBMIT_COLOR',
            'data': None,
            'message': '当前牌不是万能牌，不能变色'
        })
        return
    room.lastCard['color'] = color
    await send(ws, {
        'type': 'RES_SUBMIT_COLOR',
        'data': color,
        'message': '变色成功'
    })
    await emit_all_players(room, {
        'type': 'COLOR_IS_CHANGE',
        'data': color,
        'message': f'卡牌颜色更改为：{color}'
    })
    room.order = (room.order + 1) % len(room.players)
    await emit_all_players(room, {
        'type': 'NEXT_TURN',
        'data': {
            'order': room.order,
            'players': [p.to_dict() for p in room.players],
            'lastCard': room.lastCard
        },
        'message': '进入下一回合'
    })
    await update_room_info(room)

# UNO
async def uno(data, ws, wss):
    room_code = data
    room = room_collection.get(room_code)
    if not room:
        await send(ws, {
            'type': 'RES_UNO',
            'data': None,
            'message': '房间不存在'
        })
        return
    player = next((p for p in room.players if p.socket == ws), None)
    if not player:
        await send(ws, {
            'type': 'RES_UNO',
            'data': None,
            'message': '玩家不存在'
        })
        return
    if len(player.cards) >= 2 or (len(player.cards) == 1 and player.cards[0]['value'] in ['skip', 'reverse', 'draw2', 'wild', 'wild_draw4']):
        await send(ws, {
            'type': 'RES_UNO',
            'data': None,
            'message': '不符合UNO条件'
        })
        return
    player.uno = True
    await send_uno_status(player, True)
    await emit_all_players(room, {
        'type': 'RES_UNO',
        'data': None,
        'message': f'玩家{player.name} UNO!'
    })

# 玩家列表推送
async def update_player_list(room, message):
    await emit_all_players(room, {
        'type': 'UPDATE_PLAYER_LIST',
        'data': [p.to_dict() for p in room.players],
        'message': message
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
    elif event == 'OUT_OF_THE_CARD':
        controllers[event] = out_of_the_card
    elif event == 'SUBMIT_COLOR':
        controllers[event] = submit_color
    elif event == 'UNO':
        controllers[event] = uno
    else:
        async def not_impl(data, ws, wss, event=event):
            await send(ws, {'type': f'RES_{event}', 'data': None, 'message': f'{event} 暂未实现'})
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