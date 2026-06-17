#!/usr/bin/env python3
"""
鸣镝传感器模拟器
模拟响箭飞行时通过UDP上报传感器数据
每支响箭每1分钟上报一次飞行数据
"""

import socket
import json
import time
import random
import math
import argparse
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.physics import AeroDynamicsSimulator, AeroAcousticsSimulator
from backend.config import settings


class MingDiSensorSimulator:
    def __init__(self, host: str, port: int, arrow_id: str, interval: int = 60):
        self.host = host
        self.port = port
        self.arrow_id = arrow_id
        self.interval = interval
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.aero_sim = AeroDynamicsSimulator()
        self.acoustics_sim = AeroAcousticsSimulator()

        self.velocity = 65.0
        self.rotation_speed = 120.0
        self.altitude = 50.0
        self.pitch = 0.3
        self.yaw = 0.0
        self.flight_time = 0.0
        self.launch_angle = random.uniform(0.2, 0.5)

        self._init_flight()

    def _init_flight(self):
        self.velocity = random.uniform(55.0, 75.0)
        self.rotation_speed = random.uniform(80.0, 150.0)
        self.altitude = 0.0
        self.pitch = self.launch_angle
        self.flight_time = 0.0

    def _update_flight_state(self, dt: float = 60.0):
        self.flight_time += dt

        trajectory = self.aero_sim.calculate_trajectory(
            initial_velocity=self.velocity,
            launch_angle=self.launch_angle,
            initial_rotation=self.rotation_speed,
            dt=0.01,
            max_time=self.flight_time
        )

        if trajectory and len(trajectory) > 0:
            idx = min(len(trajectory) - 1, int(self.flight_time / 0.01))
            point = trajectory[idx] if idx < len(trajectory) else trajectory[-1]
            self.velocity = point["velocity"]
            self.rotation_speed = point["rotation_speed"]
            self.altitude = point["altitude"]

        if self.velocity < 20.0 or self.altitude <= 0:
            self._init_flight()

    def generate_data(self) -> dict:
        self._update_flight_state(self.interval)

        ac_result = self.acoustics_sim.simulate(
            velocity=self.velocity,
            rotation_speed=self.rotation_speed,
            distance=1.0
        )

        noise_v = random.gauss(0, 0.5)
        noise_r = random.gauss(0, 2.0)
        noise_f = random.gauss(0, 5.0)
        noise_spl = random.gauss(0, 0.8)

        data = {
            "arrow_id": self.arrow_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "velocity": round(self.velocity + noise_v, 2),
            "rotation_speed": round(self.rotation_speed + noise_r, 2),
            "whistle_frequency": round(ac_result["whistle_frequency"] + noise_f, 2),
            "sound_pressure_level": round(ac_result["sound_pressure_level"] + noise_spl, 2),
            "altitude": round(self.altitude, 2),
            "pitch": round(self.pitch, 4),
            "yaw": round(self.yaw + random.gauss(0, 0.02), 4)
        }

        return data

    def send_data(self, data: dict):
        try:
            payload = json.dumps(data).encode("utf-8")
            self.socket.sendto(payload, (self.host, self.port))
            print(f"[{data['timestamp']}] Arrow {self.arrow_id}: "
                  f"v={data['velocity']:.1f}m/s, "
                  f"freq={data['whistle_frequency']:.0f}Hz, "
                  f"SPL={data['sound_pressure_level']:.1f}dB")
        except Exception as e:
            print(f"发送数据失败: {e}")

    def run(self, duration: int = 0):
        print(f"鸣镝传感器模拟器启动")
        print(f"  箭号: {self.arrow_id}")
        print(f"  目标: {self.host}:{self.port}")
        print(f"  间隔: {self.interval}秒")
        print(f"  持续: {'无限' if duration == 0 else str(duration) + '秒'}")
        print("-" * 60)

        start_time = time.time()
        try:
            while True:
                if duration > 0 and (time.time() - start_time) > duration:
                    break

                data = self.generate_data()
                self.send_data(data)
                time.sleep(self.interval)

        except KeyboardInterrupt:
            print("\n模拟器已停止")
        finally:
            self.socket.close()


def main():
    parser = argparse.ArgumentParser(description="鸣镝传感器模拟器")
    parser.add_argument("--host", default="localhost", help="UDP目标主机")
    parser.add_argument("--port", type=int, default=5005, help="UDP目标端口")
    parser.add_argument("--arrow-id", default="MD-001", help="响箭标识")
    parser.add_argument("--interval", type=int, default=60, help="上报间隔(秒)")
    parser.add_argument("--duration", type=int, default=0, help="运行时长(秒), 0为无限")
    parser.add_argument("--count", type=int, default=1, help="同时模拟的响箭数量")

    args = parser.parse_args()

    if args.count == 1:
        sim = MingDiSensorSimulator(args.host, args.port, args.arrow_id, args.interval)
        sim.run(args.duration)
    else:
        import threading
        simulators = []
        threads = []

        for i in range(args.count):
            arrow_id = f"MD-{i+1:03d}"
            sim = MingDiSensorSimulator(args.host, args.port, arrow_id, args.interval)
            simulators.append(sim)

            t = threading.Thread(target=sim.run, args=(args.duration,), daemon=True)
            threads.append(t)
            t.start()
            time.sleep(0.5)

        try:
            for t in threads:
                t.join()
        except KeyboardInterrupt:
            print("\n所有模拟器已停止")


if __name__ == "__main__":
    main()
