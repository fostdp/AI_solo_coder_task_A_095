# 鸣镝空气动力学仿真与声学分析系统

汉代鸣镝（响箭）复原研究系统，集空气动力学仿真、声学分析、实时数据监测于一体的全栈应用。

## 系统架构

```
传感器模拟器 (UDP)
       ↓
后端 (FastAPI + InfluxDB + MQTT)
       ↓
前端 (Three.js + Canvas)
```

## 功能特性

### 空气动力学仿真 (CFD)
- 基于雷诺数的阻力系数计算
- 升力系数与攻角关系
- 马格努斯效应（旋转产生的升力）
- 弹道轨迹模拟
- 压力分布计算

### 气动声学分析
- 涡旋脱落频率计算（斯托劳哈尔数）
- 哨音共振频率
- 声功率与声压级
- 传播距离估算
- 指向性模式
- 声场云图可视化

### 实时监测
- UDP传感器数据接收
- InfluxDB时序数据存储
- 实时告警检测（哨音异常/射程不足/声压级过低）
- MQTT告警推送

### 可视化
- Three.js 响箭3D模型
- 气流流线动画
- 声场分布云图
- 实时数据面板

## 项目结构

```
mingdi-system/
├── backend/                    # 后端代码
│   ├── __init__.py
│   ├── config.py              # 配置管理
│   ├── models.py              # 数据模型
│   ├── main.py                # FastAPI主应用
│   ├── store.py               # 数据处理
│   ├── influx_client.py       # InfluxDB客户端
│   ├── udp_listener.py        # UDP监听器
│   ├── mqtt_publisher.py      # MQTT发布器
│   ├── alerts.py              # 告警管理
│   └── physics/               # 物理仿真模块
│       ├── __init__.py
│       ├── aerodynamics.py    # 空气动力学
│       └── aeroacoustics.py   # 气动声学
├── frontend/                  # 前端代码
│   ├── index.html
│   └── js/
│       └── app.js
├── scripts/                   # 脚本工具
│   ├── influxdb_init.py       # InfluxDB初始化
│   └── sensor_simulator.py    # 传感器模拟器
├── requirements.txt
└── .env.example
```

## 快速开始

### 1. 安装依赖

```bash
cd mingdi-system
pip install -r requirements.txt
```

### 2. 启动 InfluxDB

确保 InfluxDB v2.x 已安装并运行，或使用 Docker：

```bash
docker run -d -p 8086:8086 \
  --name influxdb \
  -e DOCKER_INFLUXDB_INIT_MODE=setup \
  -e DOCKER_INFLUXDB_INIT_USERNAME=admin \
  -e DOCKER_INFLUXDB_INIT_PASSWORD=password \
  -e DOCKER_INFLUXDB_INIT_ORG=military-history \
  -e DOCKER_INFLUXDB_INIT_BUCKET=mingdi \
  -e DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=my-token \
  influxdb:2.7
```

### 3. 初始化数据库

```bash
cp .env.example .env
python scripts/influxdb_init.py
```

### 4. 启动后端服务

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 启动传感器模拟器

新开一个终端：

```bash
python scripts/sensor_simulator.py --arrow-id MD-001 --interval 60
```

或同时模拟多支响箭：

```bash
python scripts/sensor_simulator.py --count 3 --interval 60
```

### 6. 访问前端

打开浏览器访问：http://localhost:8000/static/index.html

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/config` | 获取系统配置 |
| POST | `/api/sensor/data` | 上报传感器数据 |
| GET | `/api/sensor/data` | 查询传感器数据 |
| GET | `/api/arrow/{id}/status` | 获取响箭状态 |
| GET | `/api/aerodynamics/simulate` | 空气动力学仿真 |
| GET | `/api/aerodynamics/trajectory` | 弹道轨迹仿真 |
| GET | `/api/acoustics/simulate` | 声学仿真 |
| GET | `/api/acoustics/sound-field` | 声场分布 |
| GET | `/api/alerts` | 查询告警记录 |
| GET | `/api/flow-streamlines` | 获取流线数据 |

## 告警规则

| 告警类型 | 阈值 | 级别 |
|----------|------|------|
| 哨音频率过低 | < 800 Hz | warning |
| 哨音频率过高 | > 2500 Hz | warning |
| 射程不足 | < 150 m | critical |
| 声压级过低 | < 60 dB | warning |

告警通过 MQTT 发布到 `mingdi/alerts` 主题。

## 鸣镝参数

- 箭体长度: 0.85 m
- 箭体直径: 0.008 m
- 箭体质量: 0.025 kg
- 哨口直径: 0.015 m
- 哨口长度: 0.03 m
- 初始速度: 55-75 m/s
- 发射角度: 0.2-0.5 rad
