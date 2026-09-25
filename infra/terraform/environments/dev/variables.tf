variable "region" {
  type    = string
  default = "ap-south-1"
}

variable "my_ip_cidr" {
  type        = string
  description = "Your public IP in /32 form, e.g. 203.0.113.7/32"

  validation {
    condition     = can(cidrhost(var.my_ip_cidr, 0)) && endswith(var.my_ip_cidr, "/32")
    error_message = "my_ip_cidr must be a single IP in /32 form, e.g. 203.0.113.7/32."
  }
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/loanease-sandbox.pub"
}

# Placeholder pins for V-01. Confirm against the NVD entry before treating as final.
variable "flask_version" {
  type    = string
  default = "2.2.2"
}

variable "werkzeug_version" {
  type    = string
  default = "2.2.2"
}

variable "raw_findings_bucket" {
  type        = string
  default     = "loanease-raw-findings-f00321"
  description = "Existing S3 bucket holding pipeline inputs and the snapshot store (created outside Terraform)."
}

variable "github_repo" {
  type        = string
  default     = "shivansh-source/ps105"
  description = "Repo whose workflows may assume the ingest role."
}

variable "github_branch" {
  type    = string
  default = "main"
}

variable "bastion_instance_type" {
  type    = string
  default = "m7i-flex.large"
}
