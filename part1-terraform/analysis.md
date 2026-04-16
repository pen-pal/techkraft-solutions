# Part 1: Infrastructure Analysis — Terraform Code Review

## 1. Security Issues (9 identified)

### Hardcoded Database Password in Plaintext
```hcl
password = "changeme123"
```
- **Why it's dangerous:** The password is committed to version control in plain text. Anyone with repo access (or a leaked `.tfstate` file) can read it. Terraform state also stores this value unencrypted by default.
- **Fix:** Use `aws_secretsmanager_secret` or `aws_ssm_parameter` (SecureString) to store the password. Reference it via a data source or pass it as a `sensitive` variable at apply time. Enable remote state encryption (S3 + KMS).

### SSH (Port 22) Open to the Entire Internet
```hcl
cidr_blocks = ["0.0.0.0/0"]   # port 22
```
- **Why it's dangerous:** Exposes SSH to brute-force attacks worldwide. Bots actively scan for open port 22.
- **Fix:** Restrict to known CIDR ranges (office IP / VPN), or eliminate SSH entirely by using AWS Systems Manager Session Manager. At minimum, use a bastion host in a separate security group.

### HTTP (Port 80) Open to the Internet Without HTTPS
- Only port 80 is opened — no port 443 (HTTPS). All traffic is unencrypted.
- **Fix:** Add an ALB with an ACM-managed TLS certificate. Redirect port 80 → 443. Backend instances should only accept traffic from the ALB's security group, not directly from the internet.

### Security Group Not Attached to EC2 Instances
- `aws_security_group.web` is defined but never referenced in `aws_instance.web`. The instances launch with the VPC's **default** security group, which may allow unintended traffic.
- **Fix:** Add `vpc_security_group_ids = [aws_security_group.web.id]` to the `aws_instance.web` resource.

### Database Uses the Same Security Group as Web Servers
```hcl
vpc_security_group_ids = [aws_security_group.web.id]
```
- The RDS instance reuses the web security group, which allows inbound on ports 80 and 22 — neither of which is the MySQL port (3306). Simultaneously, the web SG's `0.0.0.0/0` rules could expose the database to the internet if it were in a public subnet.
- **Fix:** Create a dedicated `aws_security_group.db` that only allows inbound TCP/3306 from the web servers' security group. No internet-facing rules.

### S3 Bucket Has No Access Controls, Encryption, or Versioning
```hcl
resource "aws_s3_bucket" "uploads" {
  bucket = "techkraft-uploads"
}
```
- Default S3 settings leave the bucket without server-side encryption, versioning, access logging, or a public access block.
- **Fix:** Add `aws_s3_bucket_public_access_block` (block all public access), `aws_s3_bucket_server_side_encryption_configuration` (AES-256 or KMS), `aws_s3_bucket_versioning`, and `aws_s3_bucket_logging`.

### RDS Instance Has No Encryption at Rest
- `storage_encrypted` defaults to `false`. Data on disk is unencrypted.
- **Fix:** Add `storage_encrypted = true` and optionally specify a `kms_key_id`.

### RDS Deletion Protection Disabled & No Final Snapshot
```hcl
skip_final_snapshot    = true
deletion_protection    = false
```
- A single `terraform destroy` or accidental resource removal permanently deletes the database with zero recovery path.
- **Fix:** Set `deletion_protection = true` and `skip_final_snapshot = false` with a `final_snapshot_identifier`.

### No IAM Instance Profile / Least-Privilege IAM
- EC2 instances have no `iam_instance_profile`, meaning applications either can't reach AWS APIs at all or developers embed long-lived access keys on the instance — a serious credential-leak risk.
- **Fix:** Create an IAM role with the minimum required policies and attach it via `iam_instance_profile`.

---

## 2. Architectural Problems (9 identified)

### All Subnets Are Public (No Private Subnets)
- Every subnet has `map_public_ip_on_launch = true`. Backend servers and the database are internet-routable.
- **Fix:** Create private subnets for application and database tiers. Add NAT Gateways (one per AZ for HA) for outbound-only internet access. Only the ALB should live in public subnets.

### No Internet Gateway Defined
- Public subnets exist, but there is no `aws_internet_gateway` or route table associating it. Instances will have public IPs but **no actual internet connectivity** — the Terraform is broken as written.
- **Fix:** Add an `aws_internet_gateway`, an `aws_route_table` with a `0.0.0.0/0 → igw` route, and `aws_route_table_association` for each public subnet.

### No Load Balancer
- Three web servers are deployed with no ALB/NLB in front of them. There is no mechanism for distributing traffic, performing health checks, or terminating TLS.
- **Fix:** Add an `aws_lb` (Application Load Balancer) with a target group, listener (443 with ACM cert), and health check configuration.

### Hardcoded AMI and No Lifecycle Management
```hcl
ami = "ami-0c55b159cbfafe1f0"
```
- This specific AMI may be deprecated, region-locked, or unpatched. No mechanism exists to update it.
- **Fix:** Use an `aws_ami` data source with filters (e.g., latest Amazon Linux 2023 or Ubuntu LTS) or reference AMIs built by a Packer pipeline.

### Only Two Availability Zones, Three Instances
- Subnets span only `us-east-1a` and `us-east-1b`. The third instance round-robins back to AZ `a`, creating an uneven blast radius.
- **Fix:** Add a third AZ (`us-east-1c`) to match the instance count, or use an Auto Scaling Group that distributes evenly.

### No Auto Scaling Group
- A fixed `count = 3` provides no elasticity. If one instance fails, capacity drops by 33% with no automatic recovery.
- **Fix:** Replace the static `aws_instance` resources with an `aws_autoscaling_group` backed by a launch template, with min/max/desired settings and scaling policies.

### RDS Has No Multi-AZ, No Read Replicas, Zero Backups
```hcl
backup_retention_period = 0
```
- Single-AZ RDS with zero backup retention means any AZ outage or disk failure causes total data loss.
- **Fix:** Enable `multi_az = true`, set `backup_retention_period = 7` (minimum), and consider a read replica for read-heavy workloads.

### No Terraform Backend / State Management
- No `backend` block is defined. State defaults to a local `terraform.tfstate` file, which:
  - Cannot be shared across the team safely.
  - Has no locking (concurrent runs corrupt state).
  - Has no encryption.
- **Fix:** Configure an S3 + DynamoDB backend with encryption and state locking.

### Missing Outputs and No Modularity
- Only `web_ips` is output. Critical values (VPC ID, subnet IDs, RDS endpoint, S3 bucket ARN) are missing.
- No use of modules — everything is in one flat file, making reuse and environment promotion impossible.
- **Fix:** Output all critical resource identifiers. Refactor into modules (`modules/vpc`, `modules/compute`, `modules/database`, etc.) and use `terraform-docs` for self-documentation.

---

## 3. Changes for Production-Readiness

### Network & Security Overhaul
- **Three-tier VPC:** Public subnets (ALB only) → Private subnets (app tier) → Isolated subnets (database tier). NAT Gateways per AZ.
- **Security groups follow least privilege:** ALB SG → allows 443 from internet; App SG → allows traffic only from ALB SG; DB SG → allows 3306 only from App SG.
- **AWS WAF** on the ALB for OWASP top-10 protection.
- **VPC Flow Logs** enabled and shipped to CloudWatch or S3 for audit trails.

### Compute
- Replace static instances with an **Auto Scaling Group** behind an ALB.
- Use a **Launch Template** referencing a golden AMI from a Packer pipeline.
- Attach an **IAM Instance Profile** with least-privilege policies.
- Use **Systems Manager Session Manager** instead of SSH — eliminate port 22 entirely.

### Database
- `multi_az = true`, `storage_encrypted = true`, `backup_retention_period = 7`, `deletion_protection = true`.
- Dedicated DB subnet group in isolated subnets.
- Passwords stored in **Secrets Manager** with automatic rotation.

### State & Code Quality
- **Remote backend:** S3 bucket (versioned, encrypted) + DynamoDB table for state locking.
- **Modular Terraform:** Separate modules per concern; environments use `tfvars` files.
- **Tagging strategy:** `Environment`, `Owner`, `CostCenter`, `ManagedBy=terraform` on every resource.
- Pin provider and module versions.

### Observability
- **CloudWatch Alarms** on CPU, memory (via CloudWatch Agent), disk, RDS connections, and ALB 5xx rates.
- **SNS topics** for alert routing to Slack/PagerDuty.
- Consider **Prometheus + Grafana** stack for a unified observability layer across AWS and on-prem Proxmox.

### Cost Optimization
- Evaluate **Graviton instances** (`t4g.medium`) for ~20% savings.
- Use **Reserved Instances** or **Savings Plans** for steady-state workloads.
- Enable **S3 Intelligent-Tiering** for the uploads bucket.
- Right-size RDS based on actual CloudWatch metrics.
