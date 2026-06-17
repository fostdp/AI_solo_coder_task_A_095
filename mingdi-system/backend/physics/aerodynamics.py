import math
from typing import Tuple, List
from ..config import settings


class AeroDynamicsSimulator:
    def __init__(self):
        self.rho = settings.air_density
        self.mu = settings.air_viscosity
        self.L = settings.arrow_length
        self.D = settings.arrow_diameter
        self.mass = settings.arrow_mass
        self.whistle_d = settings.whistle_diameter
        self.frontal_area = math.pi * (self.D / 2) ** 2

    def calculate_reynolds_number(self, velocity: float, length_scale: float = None) -> float:
        if length_scale is None:
            length_scale = self.D
        return (self.rho * velocity * length_scale) / self.mu

    def calculate_drag_coefficient(self, re: float, angle_of_attack: float = 0.0) -> float:
        cd_body = 1.2 + 0.3 * math.exp(-((re - 3e3) / 8e3) ** 2)
        cd_aoa = 4.0 * math.sin(angle_of_attack) ** 2
        cd = cd_body + cd_aoa
        return cd

    def calculate_lift_coefficient(self, angle_of_attack: float, re: float) -> float:
        cl_alpha = 1.8
        stall_angle = 0.3

        if abs(angle_of_attack) < stall_angle:
            cl = cl_alpha * angle_of_attack * (1 - 0.3 * abs(angle_of_attack))
        else:
            sign = 1 if angle_of_attack > 0 else -1
            cl = sign * cl_alpha * stall_angle * math.exp(-(abs(angle_of_attack) - stall_angle) / 0.2)

        return cl

    def calculate_pressure_distribution(
        self, velocity: float, num_points: int = 20
    ) -> List[float]:
        pressures = []
        dynamic_pressure = 0.5 * self.rho * velocity ** 2
        for i in range(num_points):
            x = i / (num_points - 1)
            cp = 1.0 - 0.9 * x - 0.1 * math.sin(math.pi * x) * math.exp(-x * 2)
            p = dynamic_pressure * cp
            pressures.append(p)
        return pressures

    def calculate_forces(
        self,
        velocity: float,
        angle_of_attack: float = 0.0,
        rotation_speed: float = 0.0
    ) -> Tuple[float, float, float]:
        re = self.calculate_reynolds_number(velocity)
        cd = self.calculate_drag_coefficient(re, angle_of_attack)
        cl = self.calculate_lift_coefficient(angle_of_attack, re)

        dynamic_pressure = 0.5 * self.rho * velocity ** 2

        drag = cd * dynamic_pressure * self.frontal_area
        lift = cl * dynamic_pressure * self.frontal_area

        magnus_coeff = 0.001
        magnus_force = magnus_coeff * self.rho * velocity * rotation_speed * self.D * self.L * abs(math.sin(angle_of_attack))
        lift += magnus_force

        moment = lift * self.L * 0.15 - drag * self.D * 0.3

        return drag, lift, moment

    def simulate(
        self,
        velocity: float,
        angle_of_attack: float = 0.0,
        rotation_speed: float = 0.0
    ) -> dict:
        re = self.calculate_reynolds_number(velocity)
        drag, lift, moment = self.calculate_forces(velocity, angle_of_attack, rotation_speed)
        cd = self.calculate_drag_coefficient(re, angle_of_attack)
        cl = self.calculate_lift_coefficient(angle_of_attack, re)
        pressure_dist = self.calculate_pressure_distribution(velocity)

        return {
            "drag_force": drag,
            "lift_force": lift,
            "moment": moment,
            "reynolds_number": re,
            "drag_coefficient": cd,
            "lift_coefficient": cl,
            "pressure_distribution": pressure_dist
        }

    def estimate_rotation_speed(
        self, velocity: float, initial_rotation: float = 0.0
    ) -> float:
        spin_decay = math.exp(-0.005 * velocity / 50)
        equilibrium_rotation = 80.0 + 0.5 * velocity

        target_rotation = equilibrium_rotation
        if initial_rotation > target_rotation:
            return initial_rotation * spin_decay
        else:
            return initial_rotation + (target_rotation - initial_rotation) * 0.01

    def calculate_trajectory(
        self,
        initial_velocity: float,
        launch_angle: float,
        initial_rotation: float = 0.0,
        dt: float = 0.01,
        max_time: float = 15.0
    ) -> List[dict]:
        trajectory = []
        vx = initial_velocity * math.cos(launch_angle)
        vy = initial_velocity * math.sin(launch_angle)
        x, y = 0.0, 0.0
        rotation = initial_rotation
        t = 0.0

        while t < max_time and y >= -0.1:
            speed = math.sqrt(vx ** 2 + vy ** 2)
            flight_angle = math.atan2(vy, vx) if speed > 0 else 0.0

            aoa = 0.0
            drag, lift, moment = self.calculate_forces(speed, aoa, rotation)

            drag_ax = -drag * (vx / speed) / self.mass if speed > 0 else 0
            drag_ay = -drag * (vy / speed) / self.mass if speed > 0 else 0

            lift_dir_x = -math.sin(flight_angle)
            lift_dir_y = math.cos(flight_angle)
            lift_ax = lift * lift_dir_x / self.mass
            lift_ay = lift * lift_dir_y / self.mass

            ax = drag_ax + lift_ax
            ay = drag_ay + lift_ay - 9.81

            vx += ax * dt
            vy += ay * dt
            x += vx * dt
            y += vy * dt

            rotation = self.estimate_rotation_speed(speed, rotation)
            t += dt

            trajectory.append({
                "time": round(t, 4),
                "x": round(x, 4),
                "y": round(max(0, y), 4),
                "velocity": round(speed, 4),
                "rotation_speed": round(rotation, 4),
                "altitude": round(max(0, y), 4),
                "pitch": round(flight_angle, 4),
                "aoa": round(aoa, 4)
            })

        return trajectory

    def estimate_range(self, initial_velocity: float, launch_angle: float) -> float:
        trajectory = self.calculate_trajectory(initial_velocity, launch_angle)
        if not trajectory:
            return 0.0
        if len(trajectory) < 2:
            return trajectory[-1]["x"]
        p1 = trajectory[-2]
        p2 = trajectory[-1]
        if p1["y"] > 0 and p2["y"] <= 0:
            ratio = p1["y"] / (p1["y"] - p2["y"] + 1e-6)
            return p1["x"] + (p2["x"] - p1["x"]) * ratio
        return trajectory[-1]["x"]
