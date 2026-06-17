import math
from typing import List
from ..config import settings


class AeroAcousticsSimulator:
    def __init__(self):
        self.rho = settings.air_density
        self.c0 = settings.speed_of_sound
        self.whistle_d = settings.whistle_diameter
        self.whistle_l = settings.whistle_length
        self.arrow_d = settings.arrow_diameter
        self.strouhal_number = 0.2

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

    def spl_from_power(self, acoustic_power: float, distance: float = 1.0) -> float:
        if distance <= 0:
            distance = 0.01
        intensity = acoustic_power / (4 * math.pi * distance ** 2)
        reference_intensity = 1e-12
        spl = 10 * math.log10(intensity / reference_intensity)
        return spl

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
        spl = self.spl_from_power(acoustic_power, distance)
        propagation_dist = self.calculate_propagation_distance(spl)
        directivity = self.calculate_directivity_pattern()

        re = (self.rho * velocity * self.whistle_d) / settings.air_viscosity
        strouhal = self.strouhal_number

        return {
            "whistle_frequency": frequency,
            "sound_pressure_level": spl,
            "propagation_distance": propagation_dist,
            "directivity_pattern": directivity,
            "strouhal_number": strouhal
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

        for i in range(grid_size):
            row = []
            for j in range(grid_size):
                x = (j - grid_size / 2) * grid_spacing
                y = (i - grid_size / 2) * grid_spacing
                distance = math.sqrt((x - sx) ** 2 + (y - sy) ** 2)

                if distance < 0.1:
                    distance = 0.1

                angle = math.atan2(y - sy, x - sx)
                angle_idx = int((angle / (2 * math.pi) + 0.5) * 36) % 36
                directivity = 1.0 + 0.3 * math.cos(angle) + 0.1 * math.cos(2 * angle)

                local_power = acoustic_power * directivity
                spl = self.spl_from_power(local_power, distance)
                row.append(round(spl, 2))

            field.append(row)

        return field

    def calculate_strouhal_number(self, frequency: float, velocity: float) -> float:
        return (frequency * self.whistle_d) / velocity
