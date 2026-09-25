output "bastion_public_ip" {
  value = module.compute.bastion_public_ip
}

output "portal_public_ip" {
  value = module.compute.portal_public_ip
}

output "private_ips" {
  value = module.compute.private_ips
}

output "iam_v03_role_arn" {
  value = module.iam.overprivileged_role_arn
}

output "iam_v04_user" {
  value = module.iam.no_mfa_user_name
}

output "iam_v05_user" {
  value = module.iam.stale_key_user_name
}

output "iam_v05_access_key_id" {
  value = module.iam.stale_key_access_key_id
}

output "iam_v05_key_create_date" {
  value = module.iam.stale_key_create_date
}

output "dlm_policy_id" {
  value = module.backup.dlm_policy_id
}

output "pipeline_gha_role_arn" {
  description = "Set as the AWS_ROLE_ARN repository variable for the scheduled-ingest workflow."
  value       = module.pipeline.gha_role_arn
}

output "pipeline_api_reader_user" {
  description = "Create its access key by hand (aws iam create-access-key) for the API host."
  value       = module.pipeline.api_reader_user
}
