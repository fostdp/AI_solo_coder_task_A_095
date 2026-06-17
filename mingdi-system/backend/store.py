from datetime import datetime
from .models import SensorData
from .influx_client import InfluxDBStore
from .alerts import AlertManager
from .physics import AeroDynamicsSimulator, AeroAcousticsSimulator


class DataStore:
    def __init__(self):
        self.influx = None
        self.alert_manager = None
        self.aero_sim = AeroDynamicsSimulator()
        self.acoustics_sim = AeroAcousticsSimulator()

    def init(self, influx_store: InfluxDBStore, alert_manager: AlertManager):
        self.influx = influx_store
        self.alert_manager = alert_manager

    def process_sensor_data(self, data: SensorData):
        if data.timestamp is None:
            data.timestamp = datetime.utcnow()

        if self.influx:
            self.influx.write_sensor_data(data)

        aero_result = self.aero_sim.simulate(
            velocity=data.velocity,
            angle_of_attack=data.pitch or 0.0,
            rotation_speed=data.rotation_speed
        )

        if self.influx:
            self.influx.write_aero_data(data.arrow_id, aero_result, data.timestamp)

        ac_result = self.acoustics_sim.simulate(
            velocity=data.velocity,
            rotation_speed=data.rotation_speed
        )

        if self.influx:
            self.influx.write_acoustics_data(data.arrow_id, ac_result, data.timestamp)

        if self.alert_manager:
            self.alert_manager.check_all(data)

        return {
            "sensor": data.model_dump(),
            "aerodynamics": aero_result,
            "acoustics": ac_result
        }


store = DataStore()
