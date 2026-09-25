variable "bucket_name" {
  type        = string
  description = "Existing raw-findings bucket (created outside Terraform)."
}

variable "github_repo" {
  type        = string
  description = "owner/name of the repo whose workflows may assume the ingest role."
}

variable "github_branch" {
  type    = string
  default = "main"
}
