output "overprivileged_role_arn" {
  value = aws_iam_role.loan_ops_analyst.arn
}

output "no_mfa_user_name" {
  value = aws_iam_user.loan_ops_no_mfa.name
}

output "stale_key_user_name" {
  value = aws_iam_user.loan_ops_stale_key.name
}

output "stale_key_access_key_id" {
  value = aws_iam_access_key.stale.id
}

output "stale_key_create_date" {
  value = aws_iam_access_key.stale.create_date
}

# aws_iam_access_key.secret is sensitive and intentionally NOT output here.
