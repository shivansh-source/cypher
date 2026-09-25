# Su₹aksha's daily-ingest pipeline permissions. Deliberately separate from modules/iam,
# which holds the planted (vulnerable) IAM items; everything here is least-privilege.
#
# S3 layout in the existing raw-findings bucket (created outside Terraform):
#   inputs/     raw operator-style inputs the connectors read (Prowler, PMapper, inventory, Wazuh, Greenbone)
#   snapshots/  the snapshot store (current.json + history/)
#   latest/     what prowler_connector.py reads (latest/prowler_connector.json)

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

locals {
  bucket_arn = "arn:aws:s3:::${var.bucket_name}"
  repo_owner = split("/", var.github_repo)[0]
  repo_name  = split("/", var.github_repo)[1]

  # GitHub's OIDC `sub` claim now embeds the numeric owner and repo ids
  # (repo:<owner>@<owner_id>/<repo>@<repo_id>:ref:...). Accept that form, which stays tied to
  # this exact repo even if the name were reused, plus the plain-name form for older tokens.
  github_subjects = concat(
    ["repo:${var.github_repo}:ref:refs/heads/${var.github_branch}"],
    var.github_owner_id != "" && var.github_repo_id != "" ? [
      "repo:${local.repo_owner}@${var.github_owner_id}/${local.repo_name}@${var.github_repo_id}:ref:refs/heads/${var.github_branch}"
    ] : []
  )
}

# ---- GitHub Actions: scan (read-only AWS) + ingest (S3 read/write) ------------------------
resource "aws_iam_role" "gha_ingest" {
  name = "gha-suraksha-ingest"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          # Only this repo's default branch, so a fork or PR branch can never assume it.
          "token.actions.githubusercontent.com:sub" = local.github_subjects
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "gha_security_audit" {
  role       = aws_iam_role.gha_ingest.name
  policy_arn = "arn:aws:iam::aws:policy/SecurityAudit"
}

resource "aws_iam_role_policy_attachment" "gha_view_only" {
  role       = aws_iam_role.gha_ingest.name
  policy_arn = "arn:aws:iam::aws:policy/job-function/ViewOnlyAccess"
}

resource "aws_iam_role_policy" "gha_bucket" {
  name = "suraksha-bucket-access"
  role = aws_iam_role.gha_ingest.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = local.bucket_arn
        Condition = { StringLike = { "s3:prefix" = ["inputs/*", "snapshots/*", "latest/*"] } }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = [for p in ["inputs", "snapshots", "latest"] : "${local.bucket_arn}/${p}/*"]
      },
    ]
  })
}

# ---- Bastion: may only drop host-side exports into inputs/ --------------------------------
resource "aws_iam_role" "bastion_exporter" {
  name = "suraksha-bastion-exporter"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "bastion_put_inputs" {
  name = "put-inputs-only"
  role = aws_iam_role.bastion_exporter.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject"]
      Resource = "${local.bucket_arn}/inputs/*"
    }]
  })
}

resource "aws_iam_instance_profile" "bastion_exporter" {
  name = "suraksha-bastion-exporter"
  role = aws_iam_role.bastion_exporter.name
}

# ---- API reader: read-only on snapshots/. The access key is created by hand, not here, ---
# ---- so its secret never lands in Terraform state.                                   ---
resource "aws_iam_user" "api_reader" {
  name = "suraksha-api-reader"
}

resource "aws_iam_user_policy" "api_reader" {
  name = "read-snapshots"
  user = aws_iam_user.api_reader.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = local.bucket_arn
        Condition = { StringLike = { "s3:prefix" = ["snapshots/*"] } }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${local.bucket_arn}/snapshots/*"
      },
    ]
  })
}
