from datetime import datetime
from typing import List, Optional
from .config import settings
from .models import AlertMessage, SensorData
from .physics import AeroDynamicsSimulator


class AlertManager:
    def __init__(self, mqtt_publisher=None, influx_store=None):
        self.mqtt_publisher = mqtt_publisher
        self.influx_store = influx_store
        self.aero_sim = AeroDynamicsSimulator()
        self._last_alerts = {}

    def check_frequency_alert(self, data: SensorData) -> Optional[AlertMessage]:
        freq = data.whistle_frequency
        if freq < settings.alert_frequency_min:
            return AlertMessage(
                arrow_id=data.arrow_id,
                alert_type="frequency_low",
                message=f"哨音频率过低: {freq:.1f} Hz",
                timestamp=data.timestamp or datetime.utcnow(),
                severity="warning",
                current_value=freq,
                threshold=settings.alert_frequency_min
            )
        elif freq > settings.alert_frequency_max:
            return AlertMessage(
                arrow_id=data.arrow_id,
                alert_type="frequency_high",
                message=f"哨音频率过高: {freq:.1f} Hz",
                timestamp=data.timestamp or datetime.utcnow(),
                severity="warning",
                current_value=freq,
                threshold=settings.alert_frequency_max
            )
        return None

    def check_range_alert(self, data: SensorData) -> Optional[AlertMessage]:
        launch_angle = data.pitch if data.pitch else 0.3
        estimated_range = self.aero_sim.estimate_range(data.velocity, launch_angle)

        if estimated_range < settings.alert_range_min:
            return AlertMessage(
                arrow_id=data.arrow_id,
                alert_type="range_insufficient",
                message=f"预估射程不足: {estimated_range:.1f} m",
                timestamp=data.timestamp or datetime.utcnow(),
                severity="critical",
                current_value=estimated_range,
                threshold=settings.alert_range_min
            )
        return None

    def check_spl_alert(self, data: SensorData) -> Optional[AlertMessage]:
        spl = data.sound_pressure_level
        if spl < settings.alert_spl_min:
            return AlertMessage(
                arrow_id=data.arrow_id,
                alert_type="spl_low",
                message=f"声压级过低: {spl:.1f} dB",
                timestamp=data.timestamp or datetime.utcnow(),
                severity="warning",
                current_value=spl,
                threshold=settings.alert_spl_min
            )
        return None

    def check_all(self, data: SensorData) -> List[AlertMessage]:
        alerts = []

        alert = self.check_frequency_alert(data)
        if alert:
            alerts.append(alert)

        alert = self.check_range_alert(data)
        if alert:
            alerts.append(alert)

        alert = self.check_spl_alert(data)
        if alert:
            alerts.append(alert)

        self._process_alerts(alerts)

        return alerts

    def _process_alerts(self, alerts: List[AlertMessage]):
        for alert in alerts:
            alert_key = f"{alert.arrow_id}_{alert.alert_type}"
            last_time = self._last_alerts.get(alert_key)

            if last_time and (alert.timestamp - last_time).total_seconds() < 30:
                continue

            self._last_alerts[alert_key] = alert.timestamp

            alert_dict = {
                "arrow_id": alert.arrow_id,
                "alert_type": alert.alert_type,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
                "severity": alert.severity,
                "current_value": alert.current_value,
                "threshold": alert.threshold
            }

            if self.influx_store:
                try:
                    self.influx_store.write_alert(alert_dict)
                except Exception as e:
                    print(f"Failed to write alert to InfluxDB: {e}")

            if self.mqtt_publisher:
                try:
                    self.mqtt_publisher.publish_alert(alert_dict)
                except Exception as e:
                    print(f"Failed to publish MQTT alert: {e}")

    def get_estimated_range(self, velocity: float, pitch: float = 0.3) -> float:
        return self.aero_sim.estimate_range(velocity, pitch)
