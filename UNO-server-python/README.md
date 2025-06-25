# UNO-server-python

这是 UNO 游戏的 Python WebSocket 服务器实现，接口与原 TypeScript 版 UNO-server 完全一致。

## 依赖

- Python 3.7+
- websockets

## 安装依赖

```bash
pip install websockets
```

## 启动服务器

```bash
python server.py
```

服务器启动后，监听在 `ws://0.0.0.0:3000`，与原版 UNO-server 保持一致。

## 事件接口

支持以下事件：
- CREATE_ROOM
- JOIN_ROOM
- LEAVE_ROOM
- DISSOLVE_ROOM
- CREATE_USER
- START_GAME
- OUT_OF_THE_CARD
- GET_ONE_CARD
- NEXT_TURN
- SUBMIT_COLOR
- UNO

具体事件参数和响应格式请参考原项目。 