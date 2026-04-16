#!/usr/bin/env python3
"""
ec2_monitor.py — Query EC2 + CloudWatch for running instances and report
CPU utilisation, flagging any above a configurable threshold.

Usage:
    python ec2_monitor.py --region us-east-1 --threshold 80 --output report.json
    python ec2_monitor.py --config config.json --output report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    stream=sys.stderr,
)
log = logging.getLogger("ec2_monitor")


def load_config(path: str) -> dict[str, Any]:
    """Load optional JSON config; return {} if missing or unreadable."""
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Ignoring config '%s': %s", path, e)
        return {}


def get_running_instances(
    ec2, tag_filters: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """List running EC2 instances, optionally filtered by tag key/value."""
    filters = [{"Name": "instance-state-name", "Values": ["running"]}]
    if tag_filters:
        for k, v in tag_filters.items():
            filters.append({"Name": f"tag:{k}", "Values": [v]})

    instances: list[dict[str, Any]] = []
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(Filters=filters):
        for res in page["Reservations"]:
            for inst in res["Instances"]:
                tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                instances.append({
                    "instance_id": inst["InstanceId"],
                    "name": tags.get("Name", "N/A"),
                    "instance_type": inst["InstanceType"],
                    "tags": tags,
                })
    return instances


def get_cpu_stats(cw, instance_id: str) -> dict[str, float | None]:
    """Fetch avg/min/max CPU over the last hour at 5-minute intervals."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=1)
    try:
        resp = cw.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=start,
            EndTime=end,
            Period=300,  # 5-minute intervals
            Statistics=["Average", "Minimum", "Maximum"],
        )
    except (BotoCoreError, ClientError) as e:
        log.warning("CloudWatch error for %s: %s", instance_id, e)
        return {"average": None, "minimum": None, "maximum": None}

    points = resp.get("Datapoints", [])
    if not points:
        return {"average": None, "minimum": None, "maximum": None}

    return {
        "average": round(sum(p["Average"] for p in points) / len(points), 2),
        "minimum": round(min(p["Minimum"] for p in points), 2),
        "maximum": round(max(p["Maximum"] for p in points), 2),
    }


def build_report(
    region: str, threshold: float, tag_filters: dict[str, str] | None
) -> dict[str, Any]:
    """Build the CPU report for one region."""
    session = boto3.Session(region_name=region)
    ec2 = session.client("ec2")
    cw = session.client("cloudwatch")

    try:
        instances = get_running_instances(ec2, tag_filters)
    except (BotoCoreError, ClientError) as e:
        log.error("Failed to list instances in %s: %s", region, e)
        return {"region": region, "error": str(e), "instances": []}

    log.info("Found %d running instance(s) in %s", len(instances), region)

    for inst in instances:
        inst["cpu"] = get_cpu_stats(cw, inst["instance_id"])
        avg = inst["cpu"]["average"]
        inst["alert"] = avg is not None and avg > threshold
        if inst["alert"]:
            log.warning(
                "%s (%s): avg CPU %.2f%% exceeds threshold %.1f%%",
                inst["instance_id"], inst["name"], avg, threshold,
            )

    return {
        "region": region,
        "threshold": threshold,
        "total_instances": len(instances),
        "instances_above_threshold": sum(1 for i in instances if i["alert"]),
        "instances": instances,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor EC2 CPU utilisation via CloudWatch.")
    parser.add_argument("--region", help="AWS region (overrides config)")
    parser.add_argument("--threshold", type=float, help="CPU %% alert threshold (overrides config)")
    parser.add_argument("--output", default="ec2_report.json", help="Output JSON file (default: ec2_report.json)")
    parser.add_argument("--config", default="config.json", help="Config file (default: config.json)")
    args = parser.parse_args()

    # Config supplies defaults; CLI flags override. Using None as the argparse
    # default lets us tell "user didn't pass it" apart from "user passed the
    # same value as the default".
    cfg = load_config(args.config)
    regions = [args.region] if args.region else cfg.get("regions", ["us-east-1"])
    threshold = args.threshold if args.threshold is not None else cfg.get("alert_threshold", 80.0)
    tag_filters = cfg.get("instance_tags") or None  # e.g. {"Environment": "production"}

    reports = [build_report(r, threshold, tag_filters) for r in regions]
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": threshold,
        "notification_email": cfg.get("notification_email"),
        "tag_filters": tag_filters,
        "reports": reports,
    }

    Path(args.output).write_text(json.dumps(output, indent=2, default=str))
    log.info("Report written to %s", args.output)

    total = sum(r.get("total_instances", 0) for r in reports)
    alerts = sum(r.get("instances_above_threshold", 0) for r in reports)
    print(f"\nScanned {total} instance(s) across {', '.join(regions)}")
    print(f"{alerts} above {threshold}% threshold — report saved to {args.output}")

    if alerts > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()