output "dlm_policy_id" {
  value = aws_dlm_lifecycle_policy.db_daily.id
}

output "dlm_role_arn" {
  value = aws_iam_role.dlm_lifecycle.arn
}
