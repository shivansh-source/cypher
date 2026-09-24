resource "aws_vpc" "loanease" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "loanease-sim" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.loanease.id

  tags = { Name = "loanease-igw" }
}

# Single public subnet: the Free Plan vCPU limit (8) leaves no room for a NAT instance.
# Inbound access is still locked down by the security groups below.
# Intentional: this is a deliberately exposed sandbox. The portal and bastion
# are reached directly on their public IPs (no NAT, no private subnet).
# nosemgrep: terraform.aws.security.aws-subnet-has-public-ip-address.aws-subnet-has-public-ip-address
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.loanease.id
  cidr_block              = var.public_cidr
  availability_zone       = var.az
  map_public_ip_on_launch = true

  tags = { Name = "loanease-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.loanease.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = { Name = "loanease-public-rt" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# ---------- Security groups ----------

# Bastion, Greenbone scanner and Wazuh manager all live on this one host.
resource "aws_security_group" "bastion_sg" {
  name        = "loanease-bastion-sg"
  description = "Bastion, scanner and Wazuh manager"
  vpc_id      = aws_vpc.loanease.id

  ingress {
    description = "SSH from operator IP"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  ingress {
    description = "Wazuh agent traffic and enrollment from inside the VPC"
    from_port   = 1514
    to_port     = 1515
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  # Greenbone GSA (9392) is deliberately NOT opened. Reach it through an SSH tunnel.

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "portal_sg" {
  name        = "loanease-portal-sg"
  description = "Loan portal (deliberately vulnerable app)"
  vpc_id      = aws_vpc.loanease.id

  ingress {
    description = "HTTP from allowed CIDRs only"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.portal_http_cidrs
  }

  ingress {
    description     = "SSH from operator IP and bastion"
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    cidr_blocks     = [var.my_ip_cidr]
    security_groups = [aws_security_group.bastion_sg.id]
  }

  ingress {
    description     = "All traffic from bastion (Greenbone scans)"
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.bastion_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "db_sg" {
  name        = "loanease-db-sg"
  description = "Postgres"
  vpc_id      = aws_vpc.loanease.id

  # V-02 INTENTIONAL misconfig: open to the whole VPC CIDR, not scoped to the portal SG.
  ingress {
    description = "Postgres from entire VPC (V-02)"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  ingress {
    description     = "All traffic from bastion (SSH, Greenbone scans)"
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.bastion_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "internal_sg" {
  name        = "loanease-internal-sg"
  description = "Endpoint sim"
  vpc_id      = aws_vpc.loanease.id

  ingress {
    description     = "All traffic from bastion (SSH, Greenbone scans)"
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.bastion_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
