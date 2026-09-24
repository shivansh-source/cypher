resource "aws_instance" "loan_portal" {
  ami                    = var.ami_id
  instance_type          = "t3.micro"
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.portal_sg_id]
  key_name               = var.key_name

  user_data = templatefile("${path.module}/scripts/loan_portal_bootstrap.sh", {
    flask_version    = var.flask_version
    werkzeug_version = var.werkzeug_version
  })
  user_data_replace_on_change = true

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_size = 12
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "loanease-portal" }

  lifecycle {
    ignore_changes = [ami]
  }
}

resource "aws_instance" "bastion_scanner" {
  ami                    = var.ami_id
  instance_type          = var.bastion_instance_type
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.bastion_sg_id]
  key_name               = var.key_name
  user_data              = file("${path.module}/scripts/scanner_bootstrap.sh")

  user_data_replace_on_change = true

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_size = 100 # feed import used more than expected
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "loanease-bastion-scanner" }

  lifecycle {
    ignore_changes = [ami]
  }
}

resource "aws_instance" "db" {
  ami                    = var.ami_id
  instance_type          = "t3.micro"
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.db_sg_id]
  key_name               = var.key_name
  user_data              = file("${path.module}/scripts/postgres_bootstrap.sh")

  user_data_replace_on_change = true

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_size = 12
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "loanease-db" }

  lifecycle {
    ignore_changes = [ami]
  }
}

resource "aws_instance" "endpoint_sim" {
  ami                    = var.ami_id
  instance_type          = "t3.micro"
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.internal_sg_id]
  key_name               = var.key_name

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_size = 10
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "loanease-endpoint-1" }

  lifecycle {
    ignore_changes = [ami]
  }
}
