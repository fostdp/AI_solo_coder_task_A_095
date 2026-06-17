import paho.mqtt.client as mqtt
import json
import logging
from typing import Optional
from .config import settings

logger = logging.getLogger(__name__)


class MQTTPublisher:
    def __init__(self, host: str = None, port: int = None):
        self.host = host or settings.mqtt_host
        self.port = port or settings.mqtt_port
        self.topic = settings.mqtt_topic_alerts
        self.client: Optional[mqtt.Client] = None
        self.connected = False

    def connect(self):
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mingdi-backend")
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.connect_async(self.host, self.port, keepalive=60)
            self.client.loop_start()
            logger.info(f"MQTT client connecting to {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"MQTT connection error: {e}")

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            logger.info("MQTT client connected")
        else:
            self.connected = False
            logger.error(f"MQTT connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc, properties=None):
        self.connected = False
        logger.info(f"MQTT client disconnected (code: {rc})")

    def publish_alert(self, alert_data: dict):
        if not self.connected or not self.client:
            logger.warning("MQTT not connected, skipping alert publish")
            return False

        try:
            payload = json.dumps(alert_data, default=str)
            result = self.client.publish(self.topic, payload, qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Alert published to {self.topic}: {alert_data.get('alert_type')}")
                return True
            else:
                logger.error(f"MQTT publish error: {result.rc}")
                return False
        except Exception as e:
            logger.error(f"Error publishing MQTT alert: {e}")
            return False

    def publish_status(self, arrow_id: str, status_data: dict):
        if not self.connected or not self.client:
            return False

        try:
            topic = f"mingdi/status/{arrow_id}"
            payload = json.dumps(status_data, default=str)
            self.client.publish(topic, payload, qos=0)
            return True
        except Exception as e:
            logger.error(f"Error publishing status: {e}")
            return False

    def disconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            logger.info("MQTT client disconnected")
