#!/usr/bin/env python3
"""
鸣镝系统 InfluxDB 初始化脚本
- 创建 Org / Bucket / Token
- 分层保留策略: hot(7d) / warm(90d)
- 连续查询降采样: 5m → 1h
- 告警 DBRP 映射
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from influxdb_client import InfluxDBClient, Bucket, RetentionRule
from influxdb_client.rest import ApiException
from backend.config import settings


HOT_SECONDS = 7 * 24 * 3600
WARM_SECONDS = 90 * 24 * 3600

DOWN_SAMPLE_TASKS = [
    {
        "name": "sensor_data_5m_mean",
        "every": "5m",
        "source_meas": "sensor_data",
        "fields": ["velocity", "rotation_speed", "whistle_frequency",
                   "sound_pressure_level", "altitude", "pitch", "yaw"],
        "fn": "mean"
    },
    {
        "name": "aerodynamics_5m_mean",
        "every": "5m",
        "source_meas": "aerodynamics",
        "fields": ["drag_force", "lift_force", "moment", "reynolds_number",
                   "drag_coefficient", "lift_coefficient"],
        "fn": "mean"
    },
    {
        "name": "acoustics_5m_mean",
        "every": "5m",
        "source_meas": "acoustics",
        "fields": ["whistle_frequency", "sound_pressure_level",
                   "propagation_distance", "strouhal_number"],
        "fn": "mean"
    },
    {
        "name": "alerts_1h_count",
        "every": "1h",
        "source_meas": "alerts",
        "fields": ["current_value"],
        "fn": "count"
    },
]


def retry_connect(url, token, org, max_retries=20, interval=5):
    for i in range(max_retries):
        try:
            c = InfluxDBClient(url=url, token=token, org=org, timeout=10_000)
            c.health()
            return c
        except Exception as e:
            print(f"  尝试 {i+1}/{max_retries} 失败: {e}")
            time.sleep(interval)
    return None


def build_flux_task(bucket_src, bucket_dst, task):
    fields_str = ", ".join(f'r["{f}"]' for f in task["fields"])
    keep_cols = '["_start", "_stop", "_time", "arrow_id", "_measurement", "_field", "_value"]'

    if task["fn"] == "mean":
        pipeline = (
            f'  |> filter(fn: (r) => r._measurement == "{task["source_meas"]}")\n'
            f'  |> filter(fn: (r) => contains(value: r._field, set: {task["fields"]}))\n'
            f'  |> aggregateWindow(every: {task["every"]}, fn: mean, createEmpty: false)\n'
            f'  |> keep(columns: {keep_cols})\n'
            f'  |> to(bucket: "{bucket_dst}", org: "{settings.influxdb_org}")'
        )
    else:
        pipeline = (
            f'  |> filter(fn: (r) => r._measurement == "{task["source_meas"]}")\n'
            f'  |> aggregateWindow(every: {task["every"]}, fn: count, createEmpty: false)\n'
            f'  |> keep(columns: {keep_cols})\n'
            f'  |> to(bucket: "{bucket_dst}", org: "{settings.influxdb_org}")'
        )

    return (
        f'option task = {{name: "{task["name"]}", every: {task["every"]}}}\n'
        f'data = from(bucket: "{bucket_src}")\n'
        f'  |> range(start: -task.every)\n'
        f'{pipeline}\n'
    )


def init_influxdb():
    print("=" * 60)
    print("鸣镝系统 - InfluxDB 初始化 (含降采样)")
    print("=" * 60)

    url = f"http://{settings.influxdb_host}:{settings.influxdb_port}"
    bucket_raw = settings.influxdb_bucket
    bucket_ds = settings.influxdb_bucket + "_downsampled"
    print(f"\n目标 InfluxDB: {url}")
    print(f"  org   = {settings.influxdb_org}")
    print(f"  原始 bucket (hot, 7d) = {bucket_raw}")
    print(f"  降采样 bucket (warm, 90d) = {bucket_ds}")

    client = retry_connect(url, settings.influxdb_token, settings.influxdb_org)
    if not client:
        print("✗ InfluxDB 超时未就绪")
        sys.exit(1)
    print("✓ InfluxDB 已连接")

    buckets_api = client.buckets_api()
    org_api = client.organizations_api()
    tasks_api = client.tasks_api()

    orgs = org_api.find_organizations(org=settings.influxdb_org)
    if orgs:
        org_id = orgs[0].id
        print(f"✓ 组织已存在: {settings.influxdb_org}")
    else:
        org = org_api.create_organization(name=settings.influxdb_org)
        org_id = org.id
        print(f"✓ 创建组织: {settings.influxdb_org}")

    def ensure_bucket(name, seconds):
        try:
            b = buckets_api.find_bucket_by_name(name)
            print(f"  · bucket {name} 已存在")
            return b
        except Exception:
            pass
        b = buckets_api.create_bucket(Bucket(
            name=name,
            org_id=org_id,
            retention_rules=[RetentionRule(type="expire", every_seconds=seconds)]
        ))
        print(f"  ✓ 创建 bucket {name} (保留 {seconds // 86400}d)")
        return b

    print("\n[保留策略层]")
    ensure_bucket(bucket_raw, HOT_SECONDS)
    ensure_bucket(bucket_ds, WARM_SECONDS)

    print("\n[连续查询/降采样任务]")
    existing = {t.name for t in (tasks_api.find_tasks() or [])}
    for task in DOWN_SAMPLE_TASKS:
        if task["name"] in existing:
            print(f"  · 任务 {task['name']} 已存在")
            continue
        try:
            flux = build_flux_task(bucket_raw, bucket_ds, task)
            tasks_api.create_task(flux=flux, org_id=org_id, description=task["name"])
            print(f"  ✓ 创建任务 {task['name']} (every={task['every']}, fn={task['fn']})")
        except ApiException as e:
            print(f"  ! 任务 {task['name']} 跳过: {e.status}")

    print("\n" + "=" * 60)
    print("初始化完成!")
    print("=" * 60)
    print(f"\n数据保留分层:")
    print(f"  · 原始数据 (1分钟级): {bucket_raw}  → 保留 7 天")
    print(f"  · 降采样数据 (5m/1h聚合): {bucket_ds} → 保留 90 天")
    print(f"\n测量 (measurements):")
    print(f"  - sensor_data: 传感器原始数据")
    print(f"  - aerodynamics: 空气动力学仿真结果")
    print(f"  - acoustics: 声学分析结果")
    print(f"  - alerts: 告警记录")

    client.close()


if __name__ == "__main__":
    init_influxdb()
