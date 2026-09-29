"""Tests for infra/inventory/export_network_topology.py.

All inputs are hand-written, shaped like real describe_vpcs/describe_subnets/
describe_instances/describe_security_groups responses, but with synthetic ids and IPs
(documentation ranges: 10.99.0.0/16 for the VPC, 203.0.113.0/24 for an external operator IP).
"""

from __future__ import annotations

from infra.inventory.export_network_topology import is_internet_facing, topology_from_aws

_VPC_CIDR = "10.99.0.0/16"


def _sg(group_id: str, permissions: list[dict[str, object]]) -> dict[str, object]:
    return {"GroupId": group_id, "GroupName": group_id, "IpPermissions": permissions}


def test_internal_and_sg_referencing_rules_are_not_internet_facing() -> None:
    groups = [
        _sg(
            "sg-internal",
            [
                {"IpRanges": [{"CidrIp": "10.99.1.0/24"}], "Ipv6Ranges": []},  # inside the VPC
                {"IpRanges": [], "Ipv6Ranges": [], "UserIdGroupPairs": [{"GroupId": "sg-other"}]},
            ],
        )
    ]
    assert is_internet_facing(groups, _VPC_CIDR) is False


def test_a_single_external_ip_counts_as_internet_facing() -> None:
    """A rule scoped to one real external IP still crosses the public internet to reach it."""
    groups = [_sg("sg-portal", [{"IpRanges": [{"CidrIp": "203.0.113.7/32"}], "Ipv6Ranges": []}])]
    assert is_internet_facing(groups, _VPC_CIDR) is True


def test_wide_open_cidr_counts_as_internet_facing() -> None:
    groups = [_sg("sg-open", [{"IpRanges": [{"CidrIp": "0.0.0.0/0"}], "Ipv6Ranges": []}])]
    assert is_internet_facing(groups, _VPC_CIDR) is True


def test_ipv6_rule_against_an_ipv4_only_vpc_counts_as_internet_facing() -> None:
    groups = [_sg("sg-v6", [{"IpRanges": [], "Ipv6Ranges": [{"CidrIpv6": "2001:db8::/32"}]}])]
    assert is_internet_facing(groups, _VPC_CIDR) is True


def test_multiple_groups_any_external_rule_wins() -> None:
    groups = [
        _sg("sg-internal", [{"IpRanges": [{"CidrIp": "10.99.2.0/24"}], "Ipv6Ranges": []}]),
        _sg("sg-external", [{"IpRanges": [{"CidrIp": "203.0.113.9/32"}], "Ipv6Ranges": []}]),
    ]
    assert is_internet_facing(groups, _VPC_CIDR) is True


def test_no_security_groups_is_not_internet_facing() -> None:
    assert is_internet_facing([], _VPC_CIDR) is False


_VPC = {"VpcId": "vpc-syn0000", "CidrBlock": _VPC_CIDR}
_SUBNET = {
    "SubnetId": "subnet-syn0000",
    "CidrBlock": "10.99.1.0/24",
    "Tags": [{"Key": "Name", "Value": "synthetic-public"}],
}
_SUBNET_NO_NAME = {"SubnetId": "subnet-syn0001", "CidrBlock": "10.99.2.0/24", "Tags": []}
_INSTANCE = {
    "InstanceId": "i-syn0000",
    "OwnerId": "999999999999",
    "PrivateIpAddress": "10.99.1.20",
    "SubnetId": "subnet-syn0000",
    "Placement": {"AvailabilityZone": "ap-south-1a"},
    "Tags": [{"Key": "Name", "Value": "synthetic-portal"}],
    "SecurityGroups": [{"GroupId": "sg-external"}],
}
_SECURITY_GROUPS = {
    "sg-external": _sg(
        "sg-external", [{"IpRanges": [{"CidrIp": "203.0.113.9/32"}], "Ipv6Ranges": []}]
    )
}


def test_topology_from_aws_shapes_segments_and_instances() -> None:
    doc = topology_from_aws(_VPC, [_SUBNET, _SUBNET_NO_NAME], [_INSTANCE], _SECURITY_GROUPS)

    assert doc["vpc_id"] == "vpc-syn0000"
    assert doc["vpc_cidr_block"] == _VPC_CIDR
    assert doc["segment_reachability"] == []  # never guessed; see the module docstring
    assert {s["segment_id"]: s["name"] for s in doc["segments"]} == {
        "subnet-syn0000": "synthetic-public",
        "subnet-syn0001": "subnet-syn0001",  # falls back to the subnet id when untagged
    }

    [instance] = [i for i in doc["instances"] if not i["instance_id"].startswith("gateway-")]
    assert instance["instance_id"] == "i-syn0000"
    assert instance["name"] == "synthetic-portal"
    assert instance["private_ip"] == "10.99.1.20"
    assert instance["segment_id"] == "subnet-syn0000"
    assert instance["internet_facing"] is True
    assert instance["instance_arn"] == "arn:aws:ec2:ap-south-1:999999999999:instance/i-syn0000"


def test_instance_missing_owner_or_az_gets_no_arn_rather_than_a_guessed_one() -> None:
    instance = {**_INSTANCE, "OwnerId": None}
    doc = topology_from_aws(_VPC, [_SUBNET], [instance], _SECURITY_GROUPS)
    assert doc["instances"][0]["instance_arn"] is None


def test_instance_referencing_an_unknown_security_group_id_is_not_internet_facing_by_default() -> (
    None
):
    instance = {**_INSTANCE, "SecurityGroups": [{"GroupId": "sg-does-not-exist"}]}
    doc = topology_from_aws(_VPC, [_SUBNET], [instance], _SECURITY_GROUPS)
    assert doc["instances"][0]["internet_facing"] is False


def test_topology_from_aws_adds_one_reserved_gateway_entry_per_subnet() -> None:
    doc = topology_from_aws(_VPC, [_SUBNET, _SUBNET_NO_NAME], [], _SECURITY_GROUPS)

    gateways = [i for i in doc["instances"] if i["instance_id"].startswith("gateway-")]
    assert {
        (g["instance_id"], g["private_ip"], g["segment_id"], g["instance_arn"]) for g in gateways
    } == {
        ("gateway-subnet-syn0000", "10.99.1.1", "subnet-syn0000", None),
        ("gateway-subnet-syn0001", "10.99.2.1", "subnet-syn0001", None),
    }
    assert all(g["internet_facing"] is False for g in gateways)
