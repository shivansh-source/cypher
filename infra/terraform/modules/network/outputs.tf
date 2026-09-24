output "vpc_id" {
  value = aws_vpc.loanease.id
}

# Instances wait for the internet route so their bootstrap scripts can reach apt.
output "public_subnet_id" {
  value      = aws_subnet.public.id
  depends_on = [aws_route_table_association.public]
}

output "portal_sg_id" {
  value = aws_security_group.portal_sg.id
}

output "bastion_sg_id" {
  value = aws_security_group.bastion_sg.id
}

output "db_sg_id" {
  value = aws_security_group.db_sg.id
}

output "internal_sg_id" {
  value = aws_security_group.internal_sg.id
}
