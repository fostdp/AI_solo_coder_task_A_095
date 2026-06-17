#!/usr/bin/env python3
"""
鸣镝传感器模拟器 v2
- 支持箭矢配置文件 (config/arrow_profiles.json)
- 不同箭矢形状/速度分布/转速分布
- UDP 上报
"""

import socket
import json
import time
import random
import math
import argparse
import sys
import os
import threading
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.physics import AeroDynamicsSimulator, AeroAcousticsSimulator
from backend.config import settings


def load_profiles(path: str = None) -> dict:
    if path is None:
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "arrow_profiles.json"
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class MingDiSensorSimulator:
    def __init__(self, host: str, port: int, arrow_config: dict, noise: dict):
        self.host = host
        self.port = port
        self.cfg = arrow_config
        self.noise = noise
        self.arrow_id = arrow_config["arrow_id"]
        self.name = arrow_config.get("name", self.arrow_id)
        self.interval = arrow_config.get("interval_seconds", 60)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        shape = arrow_config.get("shape", {})
        self.aero_sim = AeroDynamicsSimulator()
        if shape:
            try:
                self.aero_sim.L = float(shape.get("length_m", self.aero_sim.L))
                self.aero_sim.D = float(shape.get("diameter_m", self.aero_sim.D))
                self.aero_sim.m = float(shape.get("mass_kg", self.aero_sim.m))
            except Exception:
                pass

        self.acoustics_sim = AeroAcousticsSimulator()
        self.whistle_tuning = arrow_config.get("whistle_tuning", {})

        self.flight_time = 0.0
        self._init_flight()

    def _sample(self, rng):
        if isinstance(rng, list) and len(rng) == 2:
            return random.uniform(rng[0], rng[1])
        return float(rng)

    def _init_flight(self):
        vp = self.cfg["velocity_profile"]
        rp = self.cfg["rotation_profile"]
        self.initial_velocity = self._sample(vp["initial"])
        self.initial_rotation = self._sample(rp["initial"])
        self.velocity = self.initial_velocity
        self.rotation_speed = self.initial_rotation
        self.altitude = 0.0
        self.launch_angle = self._sample(self.cfg.get("launch_angle", [0.2, 0.5]))
        self.pitch = self.launch_angle
        self.yaw = 0.0
        self.flight_time = 0.0
        self.v_decay = float(vp.get("decay_per_min", 0.92))
        self.r_decay = float(rp.get("decay_per_min", 0.95))
        self.v_jitter = float(vp.get("jitter_std", 1.5))
        self.vp_mode = vp.get("mode", "fixed_range")
        self.sweep_period = float(vp.get("sweep_period_minutes", 0)) * 60.0
        self._cycle_start = time.time()

    def _current_base_velocity(self) -> float:
        elapsed = time.time() - self._cycle_start
        decay_factor = self.v_decay ** (elapsed / 60.0)
        base = self.initial_velocity * max(decay_factor, 0.2)
        if self.vp_mode == "sweep" and self.sweep_period > 0:
            frac = (elapsed % self.sweep_period) / self.sweep_period
            sweep_multiplier = 0.6 + 0.4 * (0.5 - 0.5 * math.cos(2 * math.pi * frac))
            base = base * sweep_multiplier
        base += random.gauss(0, self.v_jitter)
        return max(10.0, min(450.0, base))

    def _current_rotation(self) -> float:
        elapsed = time.time() - self._cycle_start
        decay_factor = self.r_decay ** (elapsed / 60.0)
        rot = self.initial_rotation * max(decay_factor, 0.3)
        rot += random.gauss(0, self.noise.get("rotation_std", 2.0))
        return max(0.0, rot)

    def generate_data(self) -> dict:
        self.flight_time += self.interval

        self.velocity = self._current_base_velocity()
        self.rotation_speed = self._current_rotation()

        trajectory = self.aero_sim.calculate_trajectory(
            initial_velocity=self.initial_velocity,
            launch_angle=self.launch_angle,
            initial_rotation=self.initial_rotation,
            dt=0.05,
            max_time=min(self.flight_time, 15.0)
        )
        if trajectory:
            point = trajectory[min(len(trajectory) - 1, int(self.flight_time / 0.05))]
            self.altitude = max(0.0, point["altitude"])
            self.velocity = 0.6 * self.velocity + 0.4 * point["velocity"]
            self.pitch = self.launch_angle - (self.flight_time / 100.0)
        else:
            self.altitude = max(0.0, self.altitude + self.velocity * self.pitch * self.interval * 0.01 - 9.81 * self.interval * 0.5)

        if self.velocity < 20.0 or self.altitude <= 0.0:
            if self.flight_time > 60.0:
                self._init_flight()

        ac_result = self.acoustics_sim.simulate(
            velocity=self.velocity,
            rotation_speed=self.rotation_speed,
            distance=1.0
        )
        freq_bias = float(self.whistle_tuning.get("frequency_offset_hz", 0.0))

        data = {
            "arrow_id": self.arrow_id,
            "arrow_name": self.name,
            "shape_profile": self.cfg.get("shape_profile", "standard"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "velocity": round(self.velocity + random.gauss(0, self.noise.get("velocity_std", 0.5)), 2),
            "rotation_speed": round(self.rotation_speed, 2),
            "whistle_frequency": round(ac_result["whistle_frequency"] + freq_bias
                                        + random.gauss(0, self.noise.get("frequency_std", 5.0)), 2),
            "sound_pressure_level": round(ac_result["sound_pressure_level"]
                                           + random.gauss(0, self.noise.get("spl_std", 0.8)), 2),
            "altitude": round(self.altitude, 2),
            "pitch": round(max(0.0, self.pitch), 4),
            "yaw": round(self.yaw + random.gauss(0, 0.02), 4),
            "shape": self.cfg.get("shape")
        }
        return data

    def send_data(self, data: dict):
        try:
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.socket.sendto(payload, (self.host, self.port))
            shape = data.get("shape_profile", "?")
            print(f"[{data['timestamp'][:19]}] {self.arrow_id:6s} ({self.name:10s} shape={shape:9s}) "
                  f"v={data['velocity']:6.1f} m/s  f={data['whistle_frequency']:5.0f} Hz  "
                  f"SPL={data['sound_pressure_level']:4.1f} dB  h={data['altitude']:5.1f} m")
        except Exception as e:
            print(f"[{self.arrow_id}] 发送失败: {e}")

    def run(self, duration: int = 0):
        print(f"  启动 {self.arrow_id} ({self.name}) → {self.host}:{self.port}  every {self.interval}s")
        start = time.time()
        try:
            while True:
                if duration > 0 and (time.time() - start) > duration:
                    break
                data = self.generate_data()
                self.send_data(data)
                time.sleep(self.interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.socket.close()


def main():
    parser = argparse.ArgumentParser(description="鸣镝传感器模拟器 v2")
    parser.add_argument("--config", default=None, help="箭矢配置文件路径")
    parser.add_argument("--host", default=None, help="UDP目标主机 (覆盖配置)")
    parser.add_argument("--port", type=int, default=None, help="UDP目标端口 (覆盖配置)")
    parser.add_argument("--arrow-id", default=None, help="只启动指定箭号")
    parser.add_argument("--duration", type=int, default=0, help="运行时长(秒)")
    parser.add_argument("--once", action="store_true", help="每支箭只发送一次然后退出")
    parser.add_argument("--list", action="store_true", help="列出所有箭矢配置并退出")

    args = parser.parse_args()

    profiles = load_profiles(args.config)
    arrows = [a for a in profiles["arrows"] if a.get("enabled", True)]

    if args.list:
        print(f"{'ID':8s} {'名称':16s} {'形状':10s} {'初速度':12s} {'发射角':10s} {'间隔':6s}")
        print("-" * 70)
        for a in arrows:
            vp = a["velocity_profile"]["initial"]
            la = a["launch_angle"]
            print(f"{a['arrow_id']:8s} {a.get('name','?'):16s} {a.get('shape_profile','?'):10s} "
                  f"{vp[0]:.0f}~{vp[1]:.0f} m/s   {la[0]:.2f}~{la[1]:.2f}   {a.get('interval_seconds',60):>4d}s")
        return

    if args.arrow_id:
        arrows = [a for a in arrows if a["arrow_id"] == args.arrow_id]
        if not arrows:
            print(f"未找到箭号: {args.arrow_id}")
            sys.exit(1)

    g = profiles.get("global", {})
    host = args.host or g.get("udp_host", settings.udp_host)
    port = args.port or int(g.get("udp_port", settings.udp_port))
    noise = g.get("noise", {})

    print("=" * 70)
    print("鸣镝传感器模拟器 v2  启动")
    print(f"  目标 UDP: {host}:{port}")
    print(f"  箭矢数量: {len(arrows)}")
    print("=" * 70)

    if args.once:
        for a in arrows:
            sim = MingDiSensorSimulator(host, port, a, noise)
            sim.send_data(sim.generate_data())
            time.sleep(0.2)
        print("一次性发送完成")
        return

    threads = []
    for a in arrows:
        sim = MingDiSensorSimulator(host, port, a, noise)
        t = threading.Thread(target=sim.run, args=(args.duration,), daemon=True)
        threads.append(t)
        t.start()
        time.sleep(0.3)

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n模拟器已停止")


if __name__ == "__main__":
    main()
