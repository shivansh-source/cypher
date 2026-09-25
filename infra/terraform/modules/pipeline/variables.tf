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

variable "github_owner_id" {
  type        = string
  default     = ""
  description = "Numeric id of the repo owner, as shown in the OIDC `sub` claim (repo:<owner>@<id>/...)."
}

variable "github_repo_id" {
  type        = string
  default     = ""
  description = "Numeric id of the repo, as shown in the OIDC `sub` claim (.../<repo>@<id>:...)."
}
