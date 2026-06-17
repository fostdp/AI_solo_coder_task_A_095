from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class SensorData(BaseModel):
    arrow_id: str = Field(..., description="响箭唯一标识")
    timestamp: Optional[datetime] = None
    velocity: float = Field(..., gt=0, description="飞行速度 m/s")
    rotation_speed: float = Field(..., ge=0, description="转速 rad/s")
    whistle_frequency: float = Field(..., gt=0, description="哨音频率 Hz")
    sound_pressure_level: float = Field(..., description="声压级 dB")
    altitude: Optional[float] = Field(0.0, description="飞行高度 m")
    pitch: Optional[float] = Field(0.0, description="俯仰角 rad")
    yaw: Optional[float] = Field(0.0, description="偏航角 rad")


class AeroDynamicsResult(BaseModel):
    drag_force: float
    lift_force: float
    moment: float
    reynolds_number: float
    drag_coefficient: float
    lift_coefficient: float
    pressure_distribution: list[float]


class AeroAcousticsResult(BaseModel):
    whistle_frequency: float
    sound_pressure_level: float
    propagation_distance: float
    directivity_pattern: list[float]
    strouhal_number: float


class AlertMessage(BaseModel):
    arrow_id: str
    alert_type: str
    message: str
    timestamp: datetime
    severity: str
    current_value: float
    threshold: float


class FlightStatus(BaseModel):
    arrow_id: str
    timestamp: datetime
    velocity: float
    rotation_speed: float
    altitude: float
    whistle_frequency: float
    sound_pressure_level: float
    estimated_range: float
    is_alert: bool = False
