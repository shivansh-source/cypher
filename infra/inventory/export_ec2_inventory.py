"""Export an EC2 asset inventory in the shape ``cmdb_connector.py`` reads.

Run by an operator, not by ``cypher``::

    python -m infra.inventory.export_ec2_inventory --region ap-south-1 > inventory.json

then point ``CMDB_EXPORT_PATH`` at the file. This stands in for a real CMDB
where none exists (the LoanEase sandbox): AWS's own instance list is the
inventory of record. It is read-only (``ec2:DescribeInstances``).

Each record's ``cloud_instance_ids`` deliberately holds the instance id
*and* the full instance/volume ARNs. ``infra/connectors/_identity_resolution.py``
matches placeholder asset ids to CMDB identifiers by exact string, and
``prowler_connector.py`` mints its placeholder ids from resource ARNs, so
the ARNs are what let an instance and its volumes be recognised as one
asset.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import boto3

_NAME_TAG = "Name"
_TERMINATED_STATES = ("terminated", "shutting-down")


def _tag(instance: dict[str, Any], key: str) -> str | None:
    for tag in instance.get("Tags") or []:
        if tag.get("Key") == key:
            value = tag.get("Value")
            return str(value) if value else None
    return None


def records_from_describe_instances(
    response: dict[str, Any], region: str, partition: str = "aws"
) -> list[dict[str, Any]]:
    """Convert a ``describe_instances`` response into CMDB-shaped asset records.

    Args:
        response: The raw ``ec2.describe_instances()`` result.
        region: Region the instances live in (used to build ARNs).
        partition: ARN partition.

    Returns:
        One record per non-terminated instance: ``id`` (the Name tag, else
        the instance id), ``hostnames`` (the Name tag), ``ip_addresses``
        (private IPv4 only, since public IPs change on every stop/start and
        are not a stable identifier), and ``cloud_instance_ids`` (instance
        id, instance ARN, attached-volume ARNs).

    Must never:
        Invent an identifier EC2 did not report.
    """
    records: list[dict[str, Any]] = []
    for reservation in response.get("Reservations", []):
        account = reservation.get("OwnerId")
        for instance in reservation.get("Instances", []):
            if instance.get("State", {}).get("Name") in _TERMINATED_STATES:
                continue
            instance_id = instance["InstanceId"]
            name = _tag(instance, _NAME_TAG)
            arn_prefix = f"arn:{partition}:ec2:{region}:{account}:"
            cloud_ids = [instance_id]
            if account:
                cloud_ids.append(f"{arn_prefix}instance/{instance_id}")
                for mapping in instance.get("BlockDeviceMappings", []):
                    volume_id = (mapping.get("Ebs") or {}).get("VolumeId")
                    if volume_id:
                        cloud_ids.append(f"{arn_prefix}volume/{volume_id}")
            private_ip = instance.get("PrivateIpAddress")
            records.append(
                {
                    "id": name or instance_id,
                    "hostnames": [name] if name else [],
                    "ip_addresses": [private_ip] if private_ip else [],
                    "cloud_instance_ids": cloud_ids,
                }
            )
    return records


def main(argv: list[str] | None = None) -> None:
    """Print the inventory JSON for ``--region`` (optionally ``--profile``) to stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True)
    parser.add_argument("--profile", default=None)
    args = parser.parse_args(argv)

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    response = session.client("ec2").describe_instances()
    json.dump(records_from_describe_instances(response, args.region), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
