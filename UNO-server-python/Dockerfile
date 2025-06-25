# 基于官方 Python 镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 设置 pip 使用国内镜像
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 复制依赖文件
COPY requirements.txt ./

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 暴露端口
EXPOSE 3000

# 启动服务
CMD ["python", "server.py"] 