# TechKraft — Senior DevOps/Infrastructure Engineer Take-Home Assignment

**Candidate:** Manish Khadka<br>
**Email:** [ManishKhadka@protonmail.com](mailto:ManishKhadka@protonmail.com)<br>
**Date:** 16 April 2026

---

## Repository Structure

```
./
├── README.md                              ← You are here
├── part1-terraform/
│   └── analysis.md                        ← Terraform code review (9 security issues, 9 architectural problems)
├── part2-linux/
│   ├── troubleshooting.md                 ← Systematic troubleshooting runbook
│   ├── Dockerfile                         ← Multi-stage Docker build
│   ├── app.py                             ← Flask application (provided)
│   └── requirements.txt                   ← Python dependencies
├── part3-python/
│   ├── ec2_monitor.py                     ← EC2 CPU monitoring script (boto3 + CloudWatch)
│   └── config.json                        ← Configuration file
├── part4-bash/
│   └── analyze_nginx_logs.sh              ← Nginx log analyser (single-pass awk)
├── part5-network/
│   └── architecture.md                    ← Redundant DNS design with Route 53
├── part6-cicd/
│   └── improvements.md                    ← Pipeline review + production-ready workflow
└── (bonus) k8s/
    └── deployment.yaml                    ← Bonus: K8s manifests (Deployment, Service, HPA, PDB)
```

---

## Approach & Assumptions

### General Approach

- Prioritised **production-readiness and security** throughout — every answer considers what happens when things go wrong, not just the happy path.
- Where the assignment said "minimum X issues," I aimed to exceed that to demonstrate depth.
- Focused on **why** something is a problem, not just identifying it — this reflects how I'd mentor the 11-engineer team.

### Key Assumptions

1. **AWS is the primary cloud** — solutions are AWS-native where possible, with awareness of the on-prem Proxmox/pfSense environment.
2. **Nepal-based team** — latency to ap-south-1 (Mumbai) is prioritised for DNS and user-facing architecture.
3. **Budget-conscious** — TechKraft is growing, so solutions balance robustness with cost. I call out expensive options (like Route 53 Resolver endpoints) and suggest phased adoption.
4. **Team skill level is developing** — solutions favour managed services (Route 53, ECS, managed RDS) over self-hosted alternatives to reduce operational burden.
5. **Application deployed in ecs for ci/cd** - our application is hosted in ecs whose cicd we need to improve.

---

## Part-by-Part Summary

### Part 1 — Terraform Analysis

Identified **9 security issues** (hardcoded password, open SSH, missing encryption, etc.) and **9 architectural problems** (no IGW, no ALB, no state backend, etc.). Provided a production-readiness roadmap covering network redesign, compute improvements, and observability.

### Part 2A — Linux Troubleshooting

Structured as a **layer-by-layer diagnostic runbook**: Network → Service → OS Resources → Logs. Each step includes the exact commands, what to look for, and the most likely root causes ranked by real-world frequency (disk full > SG change > OOM > hardware failure).

### Part 2B — Dockerfile

Multi-stage build: builder stage compiles C extensions, production stage uses `python:3.11-slim` with a non-root user, health check, and gunicorn as the production WSGI server. Optimised for layer caching (requirements installed before app code).

### Part 3 — Python EC2 Monitor

Full-featured CLI tool with: multi-region scanning, argparse, boto3 pagination, CloudWatch metric aggregation, severity-based alerting (WARNING/CRITICAL), JSON report output, and proper error handling. Config file supports runtime overrides.

### Part 4 — Bash Nginx Log Analyser

Single-pass `awk` implementation for efficiency on large log files. Handles both combined and common log formats, gracefully skips malformed lines, and outputs a colour-formatted table with top IPs, endpoints, and error rates.

### Part 5 — DNS Architecture

Designed a Route 53-based architecture with: public + private hosted zones, latency-based routing (Mumbai for Nepal users), health-check-driven failover, hybrid DNS resolution for on-prem integration, and a 5-week phased migration plan with rollback strategy.

### Part 6 — CI/CD Pipeline Review

Identified **7 problems** in the current workflow. Proposed a new pipeline with: lint/SAST → test matrix → Docker build + Trivy scan → staging deploy → integration tests → manual approval → canary production deploy. Includes ECS circuit breaker rollback and Slack notifications.

### Bonus — Kubernetes

Complete manifests: Deployment (rolling update, topology spread, security context, 3 probes), Service, HPA (CPU + memory scaling with asymmetric scale-up/down), PodDisruptionBudget, and ConfigMap. All secrets via `secretKeyRef`.

---

## Time Spent

| Part                  | Allocated   | Actual       | Notes                                            |
| --------------------- | ----------- | ------------ | ------------------------------------------------ |
| Part 1 — Terraform    | 30 min      | ~30 min      | Exceeded minimum issue count significantly       |
| Part 2 — Linux/Docker | 25 min      | ~30 min      | Troubleshooting runbook is reusable for the team |
| Part 3 — Python       | 30 min      | ~80 min      | Multi-region support added beyond requirements   |
| Part 4 — Bash         | 20 min      | ~45 min      | Single-pass awk for performance                  |
| Part 5 — Network      | 20 min      | ~60 min      | Cost estimates and migration timeline included   |
| Part 6 — CI/CD        | 15 min      | ~120 min     | Full working GitHub Actions YAML                 |
| K8s Bonus             | —           | ~15 min      | PDB and topology constraints added               |
| **Total**             | **140 min** | **~380 min** |                                                  |

---

## Tools & Versions

- **Terraform:** HCL syntax targeting Terraform >= 1.5, AWS Provider >= 5.0
- **Python:** 3.11+ with boto3, argparse, json, logging (stdlib)
- **Docker:** Multi-stage build, compatible with Docker Engine 24+
- **Bash:** POSIX-compatible (bash 4+), uses awk/sed/sort (GNU coreutils)
- **Kubernetes:** API versions apps/v1, autoscaling/v2, policy/v1 (K8s >= 1.27)
- **ECS-hosted application:** deployments target Amazon ECS, which drives the use of ecs update-service, the deployment circuit breaker for automatic rollback, and task-definition reverts for manual rollback.

---

## Mentorship & Team Considerations

A few notes on how I'd approach upskilling the 11-engineer team:

- **Part 1:** I'd run a "Terraform anti-patterns" lunch-and-learn using this exact code as a teaching exercise. Engineers learn more from broken code than from documentation.
- **Part 2:** The troubleshooting runbook is written as a sharable playbook. I'd add it to a team wiki/runbook repository so on-call engineers have a step-by-step guide.
- **Part 3:** The Python script follows patterns (argparse, logging, type hints) that I'd establish as team coding standards via a shared linting config.
- **Part 6:** The CI/CD pipeline includes `environment` protection rules — these create natural review checkpoints where senior engineers can coach juniors on deployment safety.

---

*Thank you for reviewing my submission. I'm happy to discuss any section in more detail during a follow-up conversation.*
