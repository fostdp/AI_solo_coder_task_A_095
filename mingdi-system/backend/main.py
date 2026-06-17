from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from typing import Optional, List
import logging
import math
import os

from .config import settings
from .models import SensorData, FlightStatus
from .influx_client import InfluxDBStore
from .udp_listener import UDPListener
from .mqtt_publisher import MQTTPublisher
from .alerts import AlertManager
from .store import store
from .physics import AeroDynamicsSimulator, AeroAcousticsSimulator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

influx_store: Optional[InfluxDBStore] = None
udp_listener: Optional[UDPListener] = None
mqtt_publisher: Optional[MQTTPublisher] = None
alert_manager: Optional[AlertManager] = None
aero_sim: Optional[AeroDynamicsSimulator] = None
acoustics_sim: Optional[AeroAcousticsSimulator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global influx_store, udp_listener, mqtt_publisher, alert_manager
    global aero_sim, acoustics_sim

    logger.info("Starting up MingDi system...")

    influx_store = InfluxDBStore()
    aero_sim = AeroDynamicsSimulator()
    acoustics_sim = AeroAcousticsSimulator()

    mqtt_publisher = MQTTPublisher()
    mqtt_publisher.connect()

    alert_manager = AlertManager(mqtt_publisher=mqtt_publisher, influx_store=influx_store)

    store.init(influx_store, alert_manager)

    udp_listener = UDPListener()
    udp_listener.set_callback(store.process_sensor_data)
    udp_listener.start()

    logger.info("MingDi system started successfully")

    yield

    logger.info("Shutting down MingDi system...")
    if udp_listener:
        udp_listener.stop()
    if mqtt_publisher:
        mqtt_publisher.disconnect()
    if influx_store:
        influx_store.close()
    logger.info("MingDi system shutdown complete")


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.version,
        "status": "running"
    }


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "udp_listener": udp_listener.running if udp_listener else False}


@app.get("/api/config")
async def get_config():
    return {
        "arrow": {
            "mass": settings.arrow_mass,
            "length": settings.arrow_length,
            "diameter": settings.arrow_diameter,
            "whistle_diameter": settings.whistle_d,
            "whistle_length": settings.whistle_l
        },
        "air": {
            "density": settings.air_density,
            "viscosity": settings.air_viscosity,
            "speed_of_sound": settings.speed_of_sound
        },
        "alerts": {
            "frequency_min": settings.alert_frequency_min,
            "frequency_max": settings.alert_frequency_max,
            "range_min": settings.alert_range_min,
            "spl_min": settings.alert_spl_min
        }
    }


@app.post("/api/sensor/data")
async def receive_sensor_data(data: SensorData):
    try:
        result = store.process_sensor_data(data)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error processing sensor data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sensor/data")
async def get_sensor_data(
    arrow_id: Optional[str] = Query(None),
    start: str = Query("-1h"),
    limit: int = Query(100)
):
    try:
        data = influx_store.query_sensor_data(arrow_id=arrow_id, start=start, limit=limit)
        return {"count": len(data), "data": data}
    except Exception as e:
        logger.error(f"Error querying sensor data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/arrow/{arrow_id}/status")
async def get_arrow_status(arrow_id: str):
    try:
        latest = influx_store.query_latest_status(arrow_id)
        if not latest:
            raise HTTPException(status_code=404, detail=f"Arrow {arrow_id} not found")

        estimated_range = alert_manager.get_estimated_range(
            latest["velocity"],
            latest.get("pitch", 0.3)
        )

        status = FlightStatus(
            arrow_id=arrow_id,
            timestamp=latest["timestamp"],
            velocity=latest["velocity"],
            rotation_speed=latest["rotation_speed"],
            altitude=latest.get("altitude", 0),
            whistle_frequency=latest["whistle_frequency"],
            sound_pressure_level=latest["sound_pressure_level"],
            estimated_range=estimated_range,
            is_alert=(
                latest["whistle_frequency"] < settings.alert_frequency_min
                or latest["whistle_frequency"] > settings.alert_frequency_max
                or estimated_range < settings.alert_range_min
                or latest["sound_pressure_level"] < settings.alert_spl_min
            )
        )

        return status.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting arrow status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/aerodynamics/simulate")
async def simulate_aerodynamics(
    velocity: float = Query(..., gt=0),
    angle_of_attack: float = Query(0.0),
    rotation_speed: float = Query(0.0)
):
    try:
        result = aero_sim.simulate(velocity, angle_of_attack, rotation_speed)
        return result
    except Exception as e:
        logger.error(f"Error in aerodynamics simulation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/aerodynamics/trajectory")
async def simulate_trajectory(
    initial_velocity: float = Query(..., gt=0),
    launch_angle: float = Query(0.3),
    initial_rotation: float = Query(0.0)
):
    try:
        trajectory = aero_sim.calculate_trajectory(
            initial_velocity, launch_angle, initial_rotation
        )
        return {"points": len(trajectory), "trajectory": trajectory}
    except Exception as e:
        logger.error(f"Error in trajectory simulation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/acoustics/simulate")
async def simulate_acoustics(
    velocity: float = Query(..., gt=0),
    rotation_speed: float = Query(0.0),
    distance: float = Query(1.0)
):
    try:
        result = acoustics_sim.simulate(velocity, rotation_speed, distance)
        return result
    except Exception as e:
        logger.error(f"Error in acoustics simulation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/acoustics/sound-field")
async def get_sound_field(
    velocity: float = Query(..., gt=0),
    rotation_speed: float = Query(0.0),
    grid_size: int = Query(30),
    grid_spacing: float = Query(1.0)
):
    try:
        field = acoustics_sim.calculate_sound_field(
            source_position=(0, 0),
            velocity=velocity,
            rotation_speed=rotation_speed,
            grid_size=grid_size,
            grid_spacing=grid_spacing
        )
        return {"grid_size": grid_size, "grid_spacing": grid_spacing, "field": field}
    except Exception as e:
        logger.error(f"Error calculating sound field: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/alerts")
async def get_alerts(
    arrow_id: Optional[str] = Query(None),
    start: str = Query("-24h"),
    limit: int = Query(50)
):
    try:
        alerts = influx_store.query_alerts(arrow_id=arrow_id, start=start, limit=limit)
        return {"count": len(alerts), "alerts": alerts}
    except Exception as e:
        logger.error(f"Error querying alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/flow-streamlines")
async def get_flow_streamlines(
    velocity: float = Query(50.0),
    grid_size: int = Query(20)
):
    try:
        streamlines = []
        for i in range(grid_size):
            streamline = []
            y_start = -5 + (10 * i / (grid_size - 1))
            x, y = -10.0, y_start
            for step in range(50):
                speed_factor = 1.0 - 0.3 * math.exp(-(y ** 2 / 2))
                vx = velocity * speed_factor
                vy = 0.05 * velocity * math.sin(x * 0.1)
                x += vx * 0.1
                y += vy * 0.1
                if x > 15:
                    break
                streamline.append({"x": round(x, 3), "y": round(y, 3)})
            streamlines.append(streamline)
        return {"streamlines": streamlines, "velocity": velocity}
    except Exception as e:
        logger.error(f"Error generating streamlines: {e}")
        raise HTTPException(status_code=500, detail=str(e))
