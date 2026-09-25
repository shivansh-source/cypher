output "gha_role_arn" {
  description = "Set as the AWS_ROLE_ARN repo variable used by the scheduled-ingest workflow."
  value       = aws_iam_role.gha_ingest.arn
}

output "bastion_instance_profile" {
  value = aws_iam_instance_profile.bastion_exporter.name
}

output "api_reader_user" {
  description = "Create its access key by hand: aws iam create-access-key --user-name <this>."
  value       = aws_iam_user.api_reader.name
}
