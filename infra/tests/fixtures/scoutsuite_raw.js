scoutsuite_results = {
  "account_id": "123456789012",
  "provider_code": "aws",
  "provider_name": "Amazon Web Services",
  "last_run": {
    "time": "2026-09-19 00:00:00+0000",
    "version": "5.14.0"
  },
  "services": {
    "s3": {
      "findings": {
        "s3-bucket-no-mfa-delete": {
          "description": "S3 bucket without MFA delete",
          "level": "danger",
          "items": [
            "s3.buckets.example-bucket"
          ]
        },
        "s3-bucket-no-logging": {
          "description": "S3 bucket without logging enabled",
          "level": "warning",
          "items": [
            "s3.buckets.example-bucket",
            "s3.buckets.another-bucket"
          ]
        },
        "s3-bucket-versioning-ok": {
          "description": "S3 bucket has versioning enabled",
          "level": "good",
          "items": [
            "s3.buckets.example-bucket"
          ]
        }
      }
    }
  }
};
