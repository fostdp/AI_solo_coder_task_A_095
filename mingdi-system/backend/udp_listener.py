import socket
import json
import threading
import logging
from datetime import datetime
from typing import Callable, Optional
from .config import settings
from .models import SensorData

logger = logging.getLogger(__name__)


class UDPListener:
    def __init__(self, host: str = None, port: int = None):
        self.host = host or settings.udp_host
        self.port = port or settings.udp_port
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.on_data_received: Optional[Callable] = None

    def set_callback(self, callback: Callable):
        self.on_data_received = callback

    def start(self):
        if self.running:
            return

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.settimeout(1.0)
        self.running = True

        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

        logger.info(f"UDP listener started on {self.host}:{self.port}")

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.socket.recvfrom(4096)
                self._handle_data(data.decode('utf-8'), addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"UDP receive error: {e}")

    def _handle_data(self, data_str: str, addr: tuple):
        try:
            data = json.loads(data_str)

            sensor_data = SensorData(
                arrow_id=data.get("arrow_id", "unknown"),
                timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.utcnow(),
                velocity=float(data["velocity"]),
                rotation_speed=float(data.get("rotation_speed", 0)),
                whistle_frequency=float(data.get("whistle_frequency", 0)),
                sound_pressure_level=float(data.get("sound_pressure_level", 0)),
                altitude=float(data.get("altitude", 0)),
                pitch=float(data.get("pitch", 0)),
                yaw=float(data.get("yaw", 0))
            )

            if self.on_data_received:
                self.on_data_received(sensor_data)

            logger.debug(f"Received sensor data from {addr} for arrow {sensor_data.arrow_id}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data from {addr}: {e}")
        except (KeyError, ValueError) as e:
            logger.error(f"Invalid sensor data from {addr}: {e}")

    def stop(self):
        self.running = False
        if self.socket:
            self.socket.close()
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("UDP listener stopped")
