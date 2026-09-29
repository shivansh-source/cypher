"""Export real AWS network topology in the shape ``network_topology_connector.py`` reads.

Run by an operator or CI, not by ``cypher``::

    python -m infra.inventory.export_network_topology --region ap-south-1 > topology.json

then point ``NETWORK_TOPOLOGY_EXPORT_PATH`` at the file. This is read-only
(``ec2:DescribeVpcs``, ``DescribeSubnets``, ``DescribeInstances``,
``DescribeSecurityGroups``).

What this observes, and what it deliberately does not guess
--------------------------------------------------------------
- **Segments are AWS subnets, one-to-one.** A subnet is a real, observable network boundary;
  it is not a judgement call. ``segment_reachability`` between two *different* subnets is left
  empty here: computing real cross-subnet reachability needs route table and NACL analysis this
  script does not attempt, and the schema is explicit that an unlisted pair means "no assumed
  reachability" — an honest empty answer, not a limitation to work around by guessing.
- **``internet_facing`` means "this instance's security group has an ingress rule naming a
  real address outside the VPC's own CIDR block"** — checked with :mod:`ipaddress`, not just a
  literal ``0.0.0.0/0`` check. A rule scoped to one external IP (an operator's home address, for
  example) still means traffic to that instance crosses the public internet, so it is
  internet-facing under this definition even though it is not open to everyone. A rule whose
  source is another security group (already-owned-something pivoting) or a CIDR inside the
  VPC's own range does not count: reaching the instance that way requires a foothold inside the
  VPC first, which is not "internet-facing" under any definition.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from typing import Any


def _is_external_cidr(
    cidr: str, vpc_network: ipaddress.IPv4Network | ipaddress.IPv6Network
) -> bool:
    """Whether ``cidr`` reaches outside the VPC's own address space.

    Returns:
        True if any address in ``cidr`` falls outside ``vpc_network`` (so reaching the instance
        this way requires traffic to cross the public internet, however narrowly the rule is
        scoped) — False if ``cidr`` is entirely inside the VPC's own CIDR.

    Must never:
        Read a security-group-referencing rule (no ``CidrIp``/``CidrIpv6``) as external — that
        case is handled by the caller, which only calls this for IP-range rules.
    """
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
    # isinstance, not just a `.version` check: subnet_of() itself requires both sides to be the
    # same concrete IPv4/IPv6 type, and narrowing that way (rather than a version-number compare)
    # is what lets the type checker see these two calls are safe.
    if isinstance(network, ipaddress.IPv4Network) and isinstance(
        vpc_network, ipaddress.IPv4Network
    ):
        return not network.subnet_of(vpc_network)
    if isinstance(network, ipaddress.IPv6Network) and isinstance(
        vpc_network, ipaddress.IPv6Network
    ):
        return not network.subnet_of(vpc_network)
    return True  # different address families: an IPv6 rule can never be "inside" an IPv4 VPC CIDR.


def is_internet_facing(security_groups: list[dict[str, Any]], vpc_cidr_block: str) -> bool:
    """Whether any ingress rule across ``security_groups`` reaches outside the VPC's own CIDR.

    Args:
        security_groups: Each group's ``IpPermissions`` as ``describe_security_groups`` returns
            it (a list of ``{"IpRanges": [...], "Ipv6Ranges": [...], "UserIdGroupPairs": [...]}``).
        vpc_cidr_block: The VPC's own primary IPv4 CIDR.

    Returns:
        True if any rule's ``CidrIp``/``CidrIpv6`` falls outside the VPC's CIDR. Rules that only
        reference another security group are ignored (see the module docstring).
    """
    vpc_network = ipaddress.ip_network(vpc_cidr_block)
    for group in security_groups:
        for permission in group.get("IpPermissions", []):
            for entry in permission.get("IpRanges", []) + permission.get("Ipv6Ranges", []):
                cidr = entry.get("CidrIp") or entry.get("CidrIpv6")
                if cidr and _is_external_cidr(cidr, vpc_network):
                    return True
    return False


def topology_from_aws(
    vpc: dict[str, Any],
    subnets: list[dict[str, Any]],
    instances: list[dict[str, Any]],
    security_groups_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the export document from raw ``describe_*`` responses.

    Args:
        vpc: One ``describe_vpcs`` entry (``VpcId``, ``CidrBlock``).
        subnets: ``describe_subnets`` entries for that VPC.
        instances: Flattened ``describe_instances`` instance entries (already filtered to
            running instances in that VPC).
        security_groups_by_id: Every security group in the VPC, keyed by ``GroupId``, as
            ``describe_security_groups`` returns them.

    Returns:
        ``{"vpc_id", "vpc_cidr_block", "segments", "segment_reachability", "instances"}``, where
        each instance entry carries ``instance_id``, ``name`` (its ``Name`` tag, or the instance
        id), ``private_ip``, ``segment_id`` (its subnet id), ``internet_facing``, and
        ``instance_arn``.

    Must never:
        Invent a segment that isn't a real subnet, or a reachability edge this function did not
        observe.
    """
    vpc_cidr_block = vpc["CidrBlock"]
    segments = [
        {
            "segment_id": subnet["SubnetId"],
            "name": next(
                (t["Value"] for t in subnet.get("Tags", []) if t["Key"] == "Name"),
                subnet["SubnetId"],
            ),
        }
        for subnet in subnets
    ]

    instance_entries: list[dict[str, Any]] = []
    for instance in instances:
        instance_id = instance["InstanceId"]
        name = next(
            (t["Value"] for t in instance.get("Tags", []) if t["Key"] == "Name"), instance_id
        )
        account_id = instance.get("OwnerId") or ""
        region = instance.get("Placement", {}).get("AvailabilityZone", "")[:-1]
        groups = [
            security_groups_by_id[sg["GroupId"]]
            for sg in instance.get("SecurityGroups", [])
            if sg["GroupId"] in security_groups_by_id
        ]
        instance_entries.append(
            {
                "instance_id": instance_id,
                "name": name,
                "private_ip": instance.get("PrivateIpAddress"),
                "segment_id": instance.get("SubnetId"),
                "internet_facing": is_internet_facing(groups, vpc_cidr_block),
                "instance_arn": (
                    f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"
                    if account_id and region
                    else None
                ),
            }
        )

    return {
        "vpc_id": vpc["VpcId"],
        "vpc_cidr_block": vpc_cidr_block,
        "segments": segments,
        # Cross-subnet reachability is not attempted here; see the module docstring.
        "segment_reachability": [],
        "instances": instance_entries,
    }


def main(argv: list[str] | None = None) -> None:
    """Print the topology JSON for ``--region`` (optionally ``--profile``, ``--vpc-id``) to stdout."""
    import boto3

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--vpc-id", default=None, help="Defaults to the account's default VPC.")
    args = parser.parse_args(argv)

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    ec2 = session.client("ec2")

    if args.vpc_id:
        vpc = ec2.describe_vpcs(VpcIds=[args.vpc_id])["Vpcs"][0]
    else:
        vpcs = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])["Vpcs"]
        if not vpcs:
            vpcs = ec2.describe_vpcs()["Vpcs"]
        vpc = vpcs[0]
    vpc_id = vpc["VpcId"]

    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["Subnets"]
    instances: list[dict[str, Any]] = []
    for reservation in ec2.describe_instances(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )["Reservations"]:
        for instance in reservation["Instances"]:
            # describe_instances reports OwnerId per reservation, not per instance; copy it
            # down so topology_from_aws can build each instance's ARN from a single dict.
            instances.append({**instance, "OwnerId": reservation.get("OwnerId")})
    security_groups = ec2.describe_security_groups(
        Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
    )["SecurityGroups"]
    security_groups_by_id = {group["GroupId"]: group for group in security_groups}

    document = topology_from_aws(vpc, subnets, instances, security_groups_by_id)
    json.dump(document, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
