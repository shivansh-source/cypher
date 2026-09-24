terraform {
  required_version = ">= 1.10"

  backend "s3" {
    bucket       = "loanease-tfstate-d07f64"
    key          = "dev/terraform.tfstate"
    region       = "ap-south-1"
    profile      = "loanease-sandbox"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
