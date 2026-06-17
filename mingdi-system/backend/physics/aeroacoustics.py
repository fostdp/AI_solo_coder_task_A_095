import math
from typing import List, Tuple
from ..config import settings


class FWHAcousticSolver:
    """
    Ffowcs Williams-Hawkings (FW-H) 方程求解器（简化工程版本）。
    
    FW-H方程: □²p' = ∂/∂t[ρ₀vₙδ(f)] - ∂/∂xᵢ[lᵢδ(f)] + ∂²/∂xᵢ∂xⱼ[TᵢⱼH(f)]
    
    三项声源:
      - 厚度项 (monopole):   表面法向速度 → 低频脉动
      - 载荷项 (dipole):     表面压力脉动 → 主频哨音
      - 四极子项 (quadrupole): Lighthill应力张量 → 跨音速激波噪声
    
    近场修正: 当观测点距声源 r < 2L 时，必须计入
    近场项（1/r²衰减项）和推迟时间空间梯度。
    """

    def __init__(self, rho: float, c0: float, body_length: float, body_diameter: float):
        self.rho = rho
        self.c0 = c0
        self.L = body_length
        self.D = body_diameter

    def thickness_noise(
        self, velocity: float, rotation_speed: float, distance: float, angle: float
    ) -> float:
        vn = velocity * 0.01 + rotation_speed * self.D * 0.002
        surface_area = math.pi * self.D * self.L * 0.3
        cos_theta = math.cos(angle)

        if distance < 0.01:
            distance = 0.01

        thickness_directivity = 0.5 * (1 + cos_theta)

        p_near = self.rho * vn * surface_area / (4 * math.pi * distance ** 2)
        p_far = self.rho * vn * surface_area * self.c0 / (4 * math.pi * distance * self.c0)

        near_field_weight = math.exp(-distance / (2 * self.L))
        p_thickness = p_far * (1 - near_field_weight) + p_near * near_field_weight
        p_thickness *= thickness_directivity

        return p_thickness

    def loading_noise(
        self, velocity: float, rotation_speed: float, distance: float, angle: float
    ) -> float:
        dynamic_pressure = 0.5 * self.rho * velocity ** 2
        surface_pressure = dynamic_pressure * 0.8

        surface_area = math.pi * self.D * self.L * 0.3

        if distance < 0.01:
            distance = 0.01

        omega = rotation_speed if rotation_speed > 0 else velocity * 2 * math.pi / self.L
        k_omega = omega / self.c0

        loading_directivity = math.cos(angle) * (1 + 0.3 * math.cos(2 * angle))

        p_far = surface_pressure * surface_area * k_omega / (4 * math.pi * distance)
        p_near = surface_pressure * surface_area / (4 * math.pi * distance ** 2) * 2

        near_field_weight = math.exp(-distance / (2 * self.L))
        p_loading = p_far * (1 - near_field_weight) + p_near * near_field_weight
        p_loading *= abs(loading_directivity)

        return p_loading

    def quadrupole_noise(
        self, velocity: float, distance: float, angle: float, mach: float = 0.0
    ) -> float:
        if mach < 0.3:
            return 0.0

        volume = math.pi * (self.D / 2) ** 2 * self.L

        Tij_magnitude = self.rho * velocity ** 2 * volume

        if distance < 0.01:
            distance = 0.01

        quadrupole_directivity = (math.sin(2 * angle)) ** 2

        p_far = Tij_magnitude / (4 * math.pi * self.c0 ** 2 * distance)
        p_near = Tij_magnitude * 2 / (4 * math.pi * self.c0 * distance ** 2)

        mach_correction = mach ** 3 / (1 - mach ** 2 + 0.01) ** 2.5 if mach < 1.0 else mach ** 3
        mach_correction = min(mach_correction, 10.0)

        near_field_weight = math.exp(-distance / (2 * self.L))
        p_quad = p_far * (1 - near_field_weight) + p_near * near_field_weight
        p_quad *= abs(quadrupole_directivity) * mach_correction

        return p_quad

    def compute_total_pressure(
        self, velocity: float, rotation_speed: float, distance: float, angle: float
    ) -> float:
        mach = velocity / self.c0

        p_thick = self.thickness_noise(velocity, rotation_speed, distance, angle)
        p_load = self.loading_noise(velocity, rotation_speed, distance, angle)
        p_quad = self.quadrupole_noise(velocity, distance, angle, mach)

        p_total = p_thick + p_load + p_quad
        return p_total


class AeroAcousticsSimulator:
    def __init__(self):
        self.rho = settings.air_density
        self.c0 = settings.speed_of_sound
        self.whistle_d = settings.whistle_diameter
        self.whistle_l = settings.whistle_length
        self.arrow_d = settings.arrow_diameter
        self.arrow_l = settings.arrow_length
        self.strouhal_number = 0.2
        self.fwh_solver = FWHAcousticSolver(
            self.rho, self.c0, self.arrow_l, self.arrow_d
        )

    def calculate_whistle_frequency(self, velocity: float, rotation_speed: float = 0.0) -> float:
        vortex_freq = self.strouhal_number * velocity / self.whistle_d
        cavity_freq = self.c0 / (4 * self.whistle_l) * (1 + 0.3 * self.whistle_d / self.whistle_l)

        doppler_factor = 1.0 + (rotation_speed * self.whistle_d / 2) / self.c0

        freq = (vortex_freq + cavity_freq) / 2 * doppler_factor

        return freq

    def calculate_sound_power(self, velocity: float, rotation_speed: float = 0.0) -> float:
        re = (self.rho * velocity * self.whistle_d) / settings.air_viscosity

        if re < 1000:
            power_coeff = 1e-7 * re
        else:
            power_coeff = 1e-6 * (re / 1000) ** 0.5

        reference_area = math.pi * (self.whistle_d / 2) ** 2
        dynamic_power = 0.5 * self.rho * velocity ** 3 * reference_area
        acoustic_power = power_coeff * dynamic_power

        rotation_contribution = 0.1 * rotation_speed * self.whistle_d / velocity
        acoustic_power *= (1 + rotation_contribution)

        return acoustic_power

    def spl_from_pressure(self, pressure: float) -> float:
        reference_pressure = 2e-5
        if pressure <= 0:
            return 0.0
        return 20 * math.log10(pressure / reference_pressure)

    def spl_from_power(self, acoustic_power: float, distance: float = 1.0) -> float:
        if distance <= 0:
            distance = 0.01
        intensity = acoustic_power / (4 * math.pi * distance ** 2)
        reference_intensity = 1e-12
        spl = 10 * math.log10(intensity / reference_intensity)
        return spl

    def calculate_spl_fwh(
        self, velocity: float, rotation_speed: float, distance: float, angle: float = 0.0
    ) -> Tuple[float, dict]:
        near_field_radius = 2 * self.arrow_l

        p_total = self.fwh_solver.compute_total_pressure(
            velocity, rotation_speed, distance, angle
        )

        if distance < near_field_radius:
            spl = self.spl_from_pressure(abs(p_total))
        else:
            spl_far = self.spl_from_power(self.calculate_sound_power(velocity, rotation_speed), distance)
            spl_near = self.spl_from_pressure(abs(p_total))
            weight = (distance - near_field_radius) / near_field_radius
            weight = max(0, min(1, weight))
            spl = spl_near * (1 - weight) + spl_far * weight

        p_thick = self.fwh_solver.thickness_noise(velocity, rotation_speed, distance, angle)
        p_load = self.fwh_solver.loading_noise(velocity, rotation_speed, distance, angle)
        p_quad = self.fwh_solver.quadrupole_noise(velocity, distance, angle, velocity / self.c0)

        source_breakdown = {
            "thickness_spl": self.spl_from_pressure(abs(p_thick)),
            "loading_spl": self.spl_from_pressure(abs(p_load)),
            "quadrupole_spl": self.spl_from_pressure(abs(p_quad)),
            "near_field_correction": distance < near_field_radius
        }

        return spl, source_breakdown

    def calculate_propagation_distance(
        self,
        spl_source: float,
        spl_threshold: float = 20.0
    ) -> float:
        attenuation = spl_source - spl_threshold
        if attenuation <= 0:
            return float('inf')

        d = 10 ** (attenuation / 20)
        return d

    def calculate_directivity_pattern(self, angle_count: int = 36) -> List[float]:
        pattern = []
        for i in range(angle_count):
            theta = 2 * math.pi * i / angle_count
            directivity = 1.0 + 0.3 * math.cos(theta) + 0.1 * math.cos(2 * theta)
            pattern.append(directivity)
        return pattern

    def simulate(
        self,
        velocity: float,
        rotation_speed: float = 0.0,
        distance: float = 1.0
    ) -> dict:
        frequency = self.calculate_whistle_frequency(velocity, rotation_speed)
        acoustic_power = self.calculate_sound_power(velocity, rotation_speed)

        spl_fwh, source_breakdown = self.calculate_spl_fwh(
            velocity, rotation_speed, distance, angle=0.0
        )

        spl_lighthill = self.spl_from_power(acoustic_power, distance)

        near_field_radius = 2 * self.arrow_l
        if distance < near_field_radius:
            spl = spl_fwh
        else:
            spl = spl_lighthill

        propagation_dist = self.calculate_propagation_distance(spl)
        directivity = self.calculate_directivity_pattern()

        re = (self.rho * velocity * self.whistle_d) / settings.air_viscosity
        strouhal = self.strouhal_number

        return {
            "whistle_frequency": frequency,
            "sound_pressure_level": spl,
            "sound_pressure_level_lighthill": spl_lighthill,
            "sound_pressure_level_fwh": spl_fwh,
            "propagation_distance": propagation_dist,
            "directivity_pattern": directivity,
            "strouhal_number": strouhal,
            "source_breakdown": source_breakdown
        }

    def calculate_sound_field(
        self,
        source_position: tuple,
        velocity: float,
        rotation_speed: float = 0.0,
        grid_size: int = 50,
        grid_spacing: float = 1.0
    ) -> List[List[float]]:
        acoustic_power = self.calculate_sound_power(velocity, rotation_speed)
        field = []
        sx, sy = source_position

        near_field_radius = 2 * self.arrow_l

        for i in range(grid_size):
            row = []
            for j in range(grid_size):
                x = (j - grid_size / 2) * grid_spacing
                y = (i - grid_size / 2) * grid_spacing
                distance = math.sqrt((x - sx) ** 2 + (y - sy) ** 2)

                if distance < 0.1:
                    distance = 0.1

                angle = math.atan2(y - sy, x - sx)
                directivity = 1.0 + 0.3 * math.cos(angle) + 0.1 * math.cos(2 * angle)

                if distance < near_field_radius:
                    p_total = self.fwh_solver.compute_total_pressure(
                        velocity, rotation_speed, distance, angle
                    )
                    local_power = acoustic_power * directivity
                    p_lighthill = math.sqrt(local_power / (4 * math.pi * distance ** 2) * self.rho * self.c0)

                    near_weight = (near_field_radius - distance) / near_field_radius
                    p_effective = p_lighthill * (1 - near_weight) + p_total * near_weight
                    spl = self.spl_from_pressure(abs(p_effective))
                else:
                    local_power = acoustic_power * directivity
                    spl = self.spl_from_power(local_power, distance)

                row.append(round(spl, 2))

            field.append(row)

        return field

    def calculate_strouhal_number(self, frequency: float, velocity: float) -> float:
        return (frequency * self.whistle_d) / velocity
