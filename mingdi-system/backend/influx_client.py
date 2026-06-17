from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime
from typing import List, Optional
from .config import settings
from .models import SensorData


class InfluxDBStore:
    def __init__(self):
        self.client = InfluxDBClient(
            url=f"http://{settings.influxdb_host}:{settings.influxdb_port}",
            token=settings.influxdb_token,
            org=settings.influxdb_org
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()
        self.bucket = settings.influxdb_bucket
        self.org = settings.influxdb_org

    def write_sensor_data(self, data: SensorData):
        timestamp = data.timestamp or datetime.utcnow()
        point = (
            Point("sensor_data")
            .tag("arrow_id", data.arrow_id)
            .field("velocity", float(data.velocity))
            .field("rotation_speed", float(data.rotation_speed))
            .field("whistle_frequency", float(data.whistle_frequency))
            .field("sound_pressure_level", float(data.sound_pressure_level))
            .field("altitude", float(data.altitude or 0.0))
            .field("pitch", float(data.pitch or 0.0))
            .field("yaw", float(data.yaw or 0.0))
            .time(timestamp, WritePrecision.MS)
        )
        self.write_api.write(bucket=self.bucket, org=self.org, record=point)

    def write_aero_data(self, arrow_id: str, aero_data: dict, timestamp: datetime = None):
        ts = timestamp or datetime.utcnow()
        point = (
            Point("aerodynamics")
            .tag("arrow_id", arrow_id)
            .field("drag_force", float(aero_data["drag_force"]))
            .field("lift_force", float(aero_data["lift_force"]))
            .field("moment", float(aero_data["moment"]))
            .field("reynolds_number", float(aero_data["reynolds_number"]))
            .field("drag_coefficient", float(aero_data["drag_coefficient"]))
            .field("lift_coefficient", float(aero_data["lift_coefficient"]))
            .time(ts, WritePrecision.MS)
        )
        self.write_api.write(bucket=self.bucket, org=self.org, record=point)

    def write_acoustics_data(self, arrow_id: str, ac_data: dict, timestamp: datetime = None):
        ts = timestamp or datetime.utcnow()
        point = (
            Point("acoustics")
            .tag("arrow_id", arrow_id)
            .field("whistle_frequency", float(ac_data["whistle_frequency"]))
            .field("sound_pressure_level", float(ac_data["sound_pressure_level"]))
            .field("propagation_distance", float(ac_data["propagation_distance"]))
            .field("strouhal_number", float(ac_data["strouhal_number"]))
            .time(ts, WritePrecision.MS)
        )
        self.write_api.write(bucket=self.bucket, org=self.org, record=point)

    def write_alert(self, alert_data: dict):
        point = (
            Point("alerts")
            .tag("arrow_id", alert_data["arrow_id"])
            .tag("alert_type", alert_data["alert_type"])
            .tag("severity", alert_data["severity"])
            .field("message", alert_data["message"])
            .field("current_value", float(alert_data["current_value"]))
            .field("threshold", float(alert_data["threshold"]))
            .time(alert_data["timestamp"], WritePrecision.MS)
        )
        self.write_api.write(bucket=self.bucket, org=self.org, record=point)

    def query_sensor_data(
        self,
        arrow_id: Optional[str] = None,
        start: str = "-1h",
        limit: int = 100
    ) -> List[dict]:
        flux_query = f'from(bucket: "{self.bucket}")'
        flux_query += f' |> range(start: {start})'
        flux_query += ' |> filter(fn: (r) => r._measurement == "sensor_data")'
        if arrow_id:
            flux_query += f' |> filter(fn: (r) => r.arrow_id == "{arrow_id}")'
        flux_query += ' |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")'
        flux_query += f' |> sort(columns: ["_time"], desc: true)'
        flux_query += f' |> limit(n: {limit})'

        result = self.query_api.query(flux_query, org=self.org)
        records = []
        for table in result:
            for record in table.records:
                records.append({
                    "timestamp": record.get_time().isoformat(),
                    "arrow_id": record.values.get("arrow_id"),
                    "velocity": record.values.get("velocity"),
                    "rotation_speed": record.values.get("rotation_speed"),
                    "whistle_frequency": record.values.get("whistle_frequency"),
                    "sound_pressure_level": record.values.get("sound_pressure_level"),
                    "altitude": record.values.get("altitude"),
                    "pitch": record.values.get("pitch"),
                    "yaw": record.values.get("yaw")
                })
        return records

    def query_alerts(
        self,
        arrow_id: Optional[str] = None,
        start: str = "-24h",
        limit: int = 50
    ) -> List[dict]:
        flux_query = f'from(bucket: "{self.bucket}")'
        flux_query += f' |> range(start: {start})'
        flux_query += ' |> filter(fn: (r) => r._measurement == "alerts")'
        if arrow_id:
            flux_query += f' |> filter(fn: (r) => r.arrow_id == "{arrow_id}")'
        flux_query += ' |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")'
        flux_query += f' |> sort(columns: ["_time"], desc: true)'
        flux_query += f' |> limit(n: {limit})'

        result = self.query_api.query(flux_query, org=self.org)
        records = []
        for table in result:
            for record in table.records:
                records.append({
                    "timestamp": record.get_time().isoformat(),
                    "arrow_id": record.values.get("arrow_id"),
                    "alert_type": record.values.get("alert_type"),
                    "severity": record.values.get("severity"),
                    "message": record.values.get("message"),
                    "current_value": record.values.get("current_value"),
                    "threshold": record.values.get("threshold")
                })
        return records

    def query_latest_status(self, arrow_id: str) -> Optional[dict]:
        data = self.query_sensor_data(arrow_id=arrow_id, start="-1h", limit=1)
        return data[0] if data else None

    def close(self):
        self.client.close()
