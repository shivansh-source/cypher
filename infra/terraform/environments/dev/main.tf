provider "aws" {
  region  = var.region
  profile = "loanease-sandbox"

  # Every resource gets Project=loanease-sim, which is what the auto-stop Lambda filters on.
  default_tags {
    tags = {
      Project   = "loanease-sim"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_key_pair" "lab" {
  key_name   = "loanease-sandbox"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

module "network" {
  source = "../../modules/network"

  vpc_cidr          = "10.20.0.0/16"
  public_cidr       = "10.20.1.0/24"
  az                = "${var.region}a"
  my_ip_cidr        = var.my_ip_cidr
  portal_http_cidrs = [var.my_ip_cidr]
}

module "pipeline" {
  source = "../../modules/pipeline"

  bucket_name   = var.raw_findings_bucket
  github_repo   = var.github_repo
  github_branch = var.github_branch
}

module "compute" {
  source = "../../modules/compute"

  ami_id                = data.aws_ami.ubuntu.id
  key_name              = aws_key_pair.lab.key_name
  public_subnet_id      = module.network.public_subnet_id
  portal_sg_id          = module.network.portal_sg_id
  bastion_sg_id         = module.network.bastion_sg_id
  db_sg_id              = module.network.db_sg_id
  internal_sg_id        = module.network.internal_sg_id
  flask_version         = var.flask_version
  werkzeug_version      = var.werkzeug_version
  bastion_instance_type = var.bastion_instance_type

  # Lets the bastion's daily export cron write to S3 inputs/ (and nothing else).
  bastion_instance_profile = module.pipeline.bastion_instance_profile
}

module "iam" {
  source     = "../../modules/iam"
  account_id = data.aws_caller_identity.current.account_id
}

module "backup" {
  source       = "../../modules/backup"
  db_volume_id = module.compute.db_root_volume_id
}
