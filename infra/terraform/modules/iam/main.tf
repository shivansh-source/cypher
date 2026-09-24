# V-03: loan-ops-analyst IAM role with an admin-equivalent managed policy it doesn't need.
# Trust policy: assumable only by this account's root, so nothing in the lab actually
# assumes it -- it exists purely to be discovered by Prowler/ScoutSuite as overprivileged.
resource "aws_iam_role" "loan_ops_analyst" {
  name = "loan-ops-analyst"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::${var.account_id}:root" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = {
    Name = "loanease-sim-V03-overprivileged-role"
  }
}

resource "aws_iam_role_policy_attachment" "loan_ops_analyst_admin" {
  role       = aws_iam_role.loan_ops_analyst.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# V-04: IAM user with a console password and no MFA device enforced.
# Prowler's MFA check only fires for users that have console access, so this
# needs a real (random, never revealed) console password, not just an access key.
resource "aws_iam_user" "loan_ops_no_mfa" {
  name = "loan-ops-no-mfa"

  tags = {
    Name = "loanease-sim-V04-no-mfa"
  }
}

resource "aws_iam_user_login_profile" "loan_ops_no_mfa" {
  user                    = aws_iam_user.loan_ops_no_mfa.name
  password_length         = 20
  password_reset_required = false
  # pgp_key intentionally omitted (optional since AWS provider 4.1.0): Terraform generates
  # the password itself and stores it in plaintext in the `password` attribute in state.
  # Nobody needs to log in as this disposable sandbox user, so that's an accepted trade-off
  # here -- just don't read this attribute back out into any file or chat.
}

# No MFA device is created or attached -- that absence is the vulnerability itself.

# V-05: access key created and deliberately never rotated during the build.
# Real CreateDate is today, so this PASSES Prowler's iam_rotate_access_key_90_days
# check until it ages out -- see manifest.yaml for the honest framing on this.
resource "aws_iam_user" "loan_ops_stale_key" {
  name = "loan-ops-stale-key"

  tags = {
    Name = "loanease-sim-V05-stale-key"
  }
}

resource "aws_iam_access_key" "stale" {
  user = aws_iam_user.loan_ops_stale_key.name
}
