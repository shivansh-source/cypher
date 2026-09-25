variable "ami_id" { type = string }
variable "key_name" { type = string }
variable "public_subnet_id" { type = string }
variable "portal_sg_id" { type = string }
variable "bastion_sg_id" { type = string }
variable "db_sg_id" { type = string }
variable "internal_sg_id" { type = string }
variable "flask_version" { type = string }
variable "werkzeug_version" { type = string }

variable "bastion_instance_profile" {
  type        = string
  default     = null
  description = "IAM instance profile for the bastion, or null for none."
}

variable "bastion_instance_type" {
  type    = string
  default = "m7i-flex.large"
}
