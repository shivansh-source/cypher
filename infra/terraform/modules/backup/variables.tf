variable "db_volume_id" {
  type        = string
  description = "Root EBS volume ID of the DB instance -- the one host V-06 backs up"
}

variable "snapshot_time" {
  type        = string
  default     = "03:00"
  description = "UTC time DLM runs the daily snapshot"
}

variable "retain_count" {
  type    = number
  default = 3
}
