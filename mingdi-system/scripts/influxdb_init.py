#!/usr/bin/env python3
"""
鸣镝系统 InfluxDB 初始化脚本
用于创建 bucket、设置保留策略、初始化示例数据
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from influxdb_client import InfluxDBClient, BucketsService, Bucket, RetentionRule
from influxdb_client.rest import ApiException
from backend.config import settings


def init_influxdb():
    print("=" * 60)
    print("鸣镝空气动力学仿真与声学分析系统 - InfluxDB 初始化")
    print("=" * 60)

    url = f"http://{settings.influxdb_host}:{settings.influxdb_port}"
    print(f"\n连接到 InfluxDB: {url}")
    print(f"组织: {settings.influxdb_org}")
    print(f"Bucket: {settings.influxdb_bucket}")

    client = InfluxDBClient(
        url=url,
        token=settings.influxdb_token,
        org=settings.influxdb_org
    )

    try:
        health = client.health()
        print(f"\n✓ InfluxDB 连接成功 (状态: {health.status})")
    except Exception as e:
        print(f"\n✗ 无法连接到 InfluxDB: {e}")
        print("  请确保 InfluxDB 已启动并运行")
        sys.exit(1)

    buckets_api = client.buckets_api()
    org_api = client.organizations_api()

    try:
        orgs = org_api.find_organizations(org=settings.influxdb_org)
        if orgs:
            org_id = orgs[0].id
            print(f"✓ 组织已存在: {settings.influxdb_org} (ID: {org_id})")
        else:
            print(f"创建组织: {settings.influxdb_org}")
            org = org_api.create_organization(name=settings.influxdb_org)
            org_id = org.id
            print(f"✓ 组织创建成功 (ID: {org_id})")
    except Exception as e:
        print(f"警告: 组织操作失败: {e}")
        org_id = None

    print(f"\n检查 Bucket: {settings.influxdb_bucket}")
    try:
        existing_bucket = None
        try:
            existing_bucket = buckets_api.find_bucket_by_name(settings.influxdb_bucket)
        except Exception:
            pass

        if existing_bucket:
            print(f"✓ Bucket 已存在: {settings.influxdb_bucket}")
        else:
            print(f"创建 Bucket: {settings.influxdb_bucket}")
            retention_rules = [
                RetentionRule(type="expire", every_seconds=30 * 24 * 60 * 60)
            ]
            bucket = buckets_api.create_bucket(
                bucket_name=settings.influxdb_bucket,
                org_id=org_id,
                retention_rules=retention_rules
            )
            print(f"✓ Bucket 创建成功 (ID: {bucket.id})")

    except ApiException as e:
        print(f"✗ Bucket 创建失败: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("初始化完成!")
    print("=" * 60)
    print(f"\n连接信息:")
    print(f"  URL: {url}")
    print(f"  Token: {settings.influxdb_token}")
    print(f"  组织: {settings.influxdb_org}")
    print(f"  Bucket: {settings.influxdb_bucket}")
    print(f"\n测量 (measurements):")
    print(f"  - sensor_data: 传感器原始数据")
    print(f"  - aerodynamics: 空气动力学仿真结果")
    print(f"  - acoustics: 声学分析结果")
    print(f"  - alerts: 告警记录")

    client.close()


if __name__ == "__main__":
    init_influxdb()
