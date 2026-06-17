import math
from typing import Tuple, List
from ..config import settings


class SSTKOmegaModel:
    """
    Menter SST k-ω 湍流模型（简化工程版本）。
    在边界层内自动切换 k-ω（近壁）与 k-ε（外流），
    通过 Blending Function F1/F2 实现混合。
    跨音速区通过 compressibility correction 抑制激波前
    湍动能过预测。
    """

    def __init__(self, rho: float, mu: float):
        self.rho = rho
        self.mu = mu

        self.sigma_k1 = 0.85
        self.sigma_w1 = 0.5
        self.beta1 = 0.075
        self.a1 = 0.31

        self.sigma_k2 = 1.0
        self.sigma_w2 = 0.856
        self.beta2 = 0.0828

        self.kappa = 0.41

    def blending_f1(self, k: float, omega: float, y: float, velocity: float) -> float:
        cd_komega = 2 * self.sigma_w2 * self.rho * k / max(omega, 1e-10) * 0.01
        arg1 = min(
            math.sqrt(k) / (0.09 * omega * max(y, 1e-6)),
            500 * self.mu / (self.rho * omega * max(y, 1e-6) ** 2)
        )
        arg1 = min(arg1, 4 * self.rho * self.sigma_w2 * k / max(cd_komega, 1e-20))
        return math.tanh(arg1 ** 4)

    def blending_f2(self, k: float, omega: float, velocity: float) -> float:
        arg2 = max(2 * math.sqrt(k) / (0.09 * omega * max(velocity * 1e-4, 1e-6)),
                   4 * self.sigma_w2 * k / max(omega, 1e-10))
        return math.tanh(arg2 ** 2)

    def eddy_viscosity(self, k: float, omega: float, velocity: float) -> float:
        f2 = self.blending_f2(k, omega, velocity)
        strain_rate = velocity / 0.1
        return self.a1 * self.rho * k / max(self.a1 * omega, strain_rate * f2)

    def compute_turbulent_quantities(
        self, velocity: float, length_scale: float, turbulence_intensity: float = 0.05
    ) -> dict:
        re = self.rho * velocity * length_scale / self.mu

        k = 1.5 * (velocity * turbulence_intensity) ** 2

        c_mu = 0.09
        l_turb = 0.07 * length_scale
        omega = math.sqrt(k) / (c_mu * l_turb)

        omega = max(omega, 1.0)

        if re > 1e6:
            k *= 1.5

        y_wall = length_scale * 0.01
        f1 = self.blending_f1(k, omega, y_wall, velocity)
        sigma_k = f1 * self.sigma_k1 + (1 - f1) * self.sigma_k2
        sigma_w = f1 * self.sigma_w1 + (1 - f1) * self.sigma_w2
        beta = f1 * self.beta1 + (1 - f1) * self.beta2

        ma = velocity / settings.speed_of_sound
        if ma > 0.3:
            compressibility_factor = 1.0 + 1.5 * max(0, ma - 0.3)
            k /= compressibility_factor
            omega *= compressibility_factor

        mut = self.eddy_viscosity(k, omega, velocity)

        return {
            "k": k,
            "omega": omega,
            "mut": mut,
            "f1": f1,
            "f2": self.blending_f2(k, omega, velocity),
            "sigma_k": sigma_k,
            "sigma_w": sigma_w,
            "beta": beta
        }


class AeroDynamicsSimulator:
    def __init__(self):
        self.rho = settings.air_density
        self.mu = settings.air_viscosity
        self.L = settings.arrow_length
        self.D = settings.arrow_diameter
        self.mass = settings.arrow_mass
        self.whistle_d = settings.whistle_diameter
        self.frontal_area = math.pi * (self.D / 2) ** 2
        self.c0 = settings.speed_of_sound
        self.sst_model = SSTKOmegaModel(self.rho, self.mu)

    def calculate_mach_number(self, velocity: float) -> float:
        return velocity / self.c0

    def calculate_reynolds_number(self, velocity: float, length_scale: float = None) -> float:
        if length_scale is None:
            length_scale = self.D
        return (self.rho * velocity * length_scale) / self.mu

    def calculate_drag_coefficient(self, re: float, angle_of_attack: float = 0.0, mach: float = 0.0) -> float:
        cd_body = 1.2 + 0.3 * math.exp(-((re - 3e3) / 8e3) ** 2)
        cd_aoa = 4.0 * math.sin(angle_of_attack) ** 2

        cd_compressibility = 0.0
        if mach > 0.3:
            cd_compressibility = 0.4 * (mach - 0.3) ** 2
        if mach > 0.8:
            beta_prandtl = math.sqrt(abs(1 - mach ** 2))
            cd_wave = 0.8 / max(beta_prandtl, 0.05) - 0.8
            cd_wave = min(cd_wave, 2.5)
            cd_compressibility += cd_wave * math.exp(-3 * (mach - 1.0) ** 2)

        if mach > 1.0:
            cd_supersonic = 1.5 * (1 - 0.3 * math.exp(-0.5 * (mach - 1.0)))
            cd_compressibility = max(cd_compressibility, cd_supersonic - cd_body)

        sst = self.sst_model.compute_turbulent_quantities(
            mach * self.c0 if mach > 0 else 50.0, self.D
        )
        mut_ratio = sst["mut"] / self.mu
        cd_turb_correction = 0.0
        if mut_ratio > 1:
            cd_turb_correction = 0.02 * math.log10(1 + mut_ratio)

        cd = cd_body + cd_aoa + cd_compressibility + cd_turb_correction
        return cd

    def calculate_lift_coefficient(self, angle_of_attack: float, re: float, mach: float = 0.0) -> float:
        cl_alpha = 1.8
        stall_angle = 0.3

        if abs(angle_of_attack) < stall_angle:
            cl = cl_alpha * angle_of_attack * (1 - 0.3 * abs(angle_of_attack))
        else:
            sign = 1 if angle_of_attack > 0 else -1
            cl = sign * cl_alpha * stall_angle * math.exp(-(abs(angle_of_attack) - stall_angle) / 0.2)

        if mach > 0.0 and mach < 1.0:
            beta_pg = math.sqrt(max(1 - mach ** 2, 0.01))
            cl /= beta_pg
        elif mach >= 1.0:
            cl *= 1.0 / math.sqrt(mach ** 2 - 1 + 0.01)

        cl = max(min(cl, 3.0), -3.0)

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
        mach = self.calculate_mach_number(velocity)
        cd = self.calculate_drag_coefficient(re, angle_of_attack, mach)
        cl = self.calculate_lift_coefficient(angle_of_attack, re, mach)

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
        mach = self.calculate_mach_number(velocity)
        drag, lift, moment = self.calculate_forces(velocity, angle_of_attack, rotation_speed)
        cd = self.calculate_drag_coefficient(re, angle_of_attack, mach)
        cl = self.calculate_lift_coefficient(angle_of_attack, re, mach)
        pressure_dist = self.calculate_pressure_distribution(velocity)

        sst = self.sst_model.compute_turbulent_quantities(velocity, self.D)

        return {
            "drag_force": drag,
            "lift_force": lift,
            "moment": moment,
            "reynolds_number": re,
            "drag_coefficient": cd,
            "lift_coefficient": cl,
            "mach_number": mach,
            "pressure_distribution": pressure_dist,
            "turbulent_kinetic_energy": sst["k"],
            "specific_dissipation_rate": sst["omega"],
            "eddy_viscosity_ratio": sst["mut"] / self.mu
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
