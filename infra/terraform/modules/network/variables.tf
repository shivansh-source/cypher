variable "vpc_cidr" { type = string }
variable "public_cidr" { type = string }
variable "az" { type = string }
variable "my_ip_cidr" { type = string }

variable "portal_http_cidrs" {
  type        = list(string)
  description = "CIDRs allowed to reach the portal on port 80"
}
