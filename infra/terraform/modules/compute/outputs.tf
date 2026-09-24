output "bastion_public_ip" {
  value = aws_instance.bastion_scanner.public_ip
}

output "portal_public_ip" {
  value = aws_instance.loan_portal.public_ip
}

output "private_ips" {
  value = {
    db         = aws_instance.db.private_ip
    endpoint_1 = aws_instance.endpoint_sim.private_ip
  }
}

output "db_root_volume_id" {
  value = aws_instance.db.root_block_device[0].volume_id
}
