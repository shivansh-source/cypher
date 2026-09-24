# V-06: the DB instance has EBS snapshots scheduled via DLM; the endpoint-sim
# instance deliberately does not -- no tag is ever applied to it, and nothing
# in this module references it. That absence is the vulnerability itself.

resource "aws_iam_role" "dlm_lifecycle" {
  name = "loanease-dlm-lifecycle-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "dlm.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = {
    Name = "loanease-sim-V06-dlm-role"
  }
}

resource "aws_iam_role_policy" "dlm_lifecycle" {
  name = "loanease-dlm-lifecycle-policy"
  role = aws_iam_role.dlm_lifecycle.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateSnapshot",
          "ec2:CreateSnapshots",
          "ec2:DeleteSnapshot",
          "ec2:DescribeInstances",
          "ec2:DescribeVolumes",
          "ec2:DescribeSnapshots",
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "ec2:CreateTags"
        Resource = "arn:aws:ec2:*::snapshot/*"
      },
    ]
  })
}

resource "aws_ec2_tag" "db_volume_backup" {
  resource_id = var.db_volume_id
  key         = "Backup"
  value       = "true"
}

resource "aws_dlm_lifecycle_policy" "db_daily" {
  description        = "loanease-sim V-06 daily EBS snapshot for tagged DB volumes"
  execution_role_arn = aws_iam_role.dlm_lifecycle.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]

    target_tags = {
      Backup = "true"
    }

    schedule {
      name = "daily-db-snapshot"

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = [var.snapshot_time]
      }

      retain_rule {
        count = var.retain_count
      }

      tags_to_add = {
        SnapshotCreator = "DLM"
        Project         = "loanease-sim"
      }

      copy_tags = true
    }
  }

  depends_on = [aws_ec2_tag.db_volume_backup]
}
