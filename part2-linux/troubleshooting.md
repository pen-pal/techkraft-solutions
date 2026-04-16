# Part 2A: Linux Troubleshooting — Unresponsive Web Server (10.0.1.50)

## Diagnostic Methodology

I follow a **layer-by-layer** approach: Network → Service → OS Resources → Logs. This avoids wasting time on application-level debugging when the root cause might be a full disk or a misconfigured security group.

---

## Step 1 — Verify Network Connectivity from the Jump Host

```bash
# Basic ICMP reachability (if ICMP is allowed by the SG)
ping -c 5 10.0.1.50

# Check if the SSH port is accepting connections (more reliable than ping)
nc -zv -w 5 10.0.1.50 22

# Trace the network path to identify where packets are dropping
traceroute -T -p 22 10.0.1.50

# Check from the AWS side — is the instance even running?
aws ec2 describe-instance-status --instance-ids <instance-id> \
  --query 'InstanceStatuses[*].{State:InstanceState.Name,System:SystemStatus.Status,Instance:InstanceStatus.Status}'

# Check the security group and NACLs attached to the instance
aws ec2 describe-instances --instance-ids <instance-id> \
  --query 'Reservations[*].Instances[*].{SG:SecurityGroups,SubnetId:SubnetId}'
aws ec2 describe-network-acls --filters "Name=association.subnet-id,Values=<subnet-id>"

# Check the route table associated with the instance's subnet
aws ec2 describe-route-tables --filters "Name=association.subnet-id,Values=<subnet-id>"
```

**What I'm looking for:**
- `ping` failing → Could be SG/NACL blocking ICMP, or the instance is truly down.
- `nc` timing out on port 22 → SG doesn't allow SSH from jump host, NACL blocking, or sshd isn't running.
- `describe-instance-status` showing `impaired` → Possible underlying hardware issue; stop/start the instance to migrate to new hardware.

---

## Step 2 — Confirm SSH Service Is Running

If network connectivity looks fine (port 22 is reachable but connection stalls/resets), access the instance via **AWS Systems Manager Session Manager** or the **EC2 Serial Console** (if enabled):

```bash
# Via AWS Systems Manager
aws ssm send-command \
  --instance-ids i-xxxxxxxxx \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["systemctl status sshd", "ss -tlnp | grep :22"]'

# If SSM Agent is installed and the instance has the right IAM role:
aws ssm start-session --target <instance-id>

# Once on the instance, check sshd status:
systemctl status sshd
journalctl -u sshd --since "1 hour ago" --no-pager

# Verify sshd is listening on port 22:
ss -tlnp | grep :22

# Check sshd configuration for issues:
sshd -t    # Config syntax check
cat /etc/ssh/sshd_config | grep -E '(Port|ListenAddress|PermitRootLogin|AllowUsers|MaxSessions)'

# Check if iptables/nftables is blocking locally:
iptables -L -n -v
nft list ruleset 2>/dev/null
```

---

## Step 3 — SSH Running but Still Can't Connect — Possible Causes

| Cause | How to Verify | Fix |
|---|---|---|
| **Host-based firewall (iptables/nftables/firewalld)** | `iptables -L -n`, `firewall-cmd --list-all` | Flush offending rules or add allow rule for jump host IP |
| **TCP wrappers** | `cat /etc/hosts.deny`, `cat /etc/hosts.allow` | Remove deny entry or add allow for jump host |
| **MaxSessions / MaxStartups exhausted** | `ss -tn state established '( dport = :22 )'` | Kill stale sessions; raise limits in sshd_config |
| **Disk full → sshd can't write to /var/log** | Check in Step 4 | Clear disk space |
| **SSH key/auth issues (but we see timeout, not rejection)** | `journalctl -u sshd` | Less likely for a timeout — more relevant for "permission denied" |
| **Kernel OOM killed sshd** | `dmesg \| grep -i oom` | Restart sshd; investigate memory pressure |
| **Instance in a "zombie" state** | EC2 console → system/instance reachability checks | Stop and start the instance (NOT reboot — forces re-migration) |
| **MTU / networking misconfiguration** | `ip link show`, check MTU values | Reset MTU to 9001 (for VPC) or 1500 |

---

## Step 4 — Check CPU, Memory, and Disk Usage

```bash
# Real-time system overview:
top -bn1 | head -20
# or
htop   # if installed

# Detailed CPU stats
mpstat -P ALL 1 5

# CPU load averages (1, 5, 15 minutes):
uptime
cat /proc/loadavg

# Per-core utilization
sar -u ALL 1 3

# Top CPU-consuming processes
ps aux --sort=-%cpu | head -20

# Memory usage:
free -h
# Look for: high "used", low "available", heavy swap usage

# Per-process memory (top consumers):
ps aux --sort=-%mem | head -15

# Detailed memory info
cat /proc/meminfo

# Swap usage
swapon --show
cat /proc/swaps

# Detailed with sar
sar -r 1 3

# Disk usage — the #1 silent killer:
df -h               # Filesystem usage
df -i               # Inode usage (can be full even if disk space looks fine)

# Largest directories
du -h --max-depth=1 / 2>/dev/null | sort -rh | head -20

# Find large files if disk is full:
find / -type f -size +100M -exec ls -lh {} \; 2>/dev/null | sort -k5 -rh

# Swap activity — watch si/so columns
vmstat 1 5

# IO wait (high iowait = disk bottleneck):
iostat -xz 1 5
```

---

## Step 5 — Check Recent System Logs

```bash
# Last 100 lines of all logs
journalctl -n 100

# Logs from last hour
journalctl --since "1 hour ago"

# Error logs only
journalctl -p err -b

# Warning and above
journalctl -p warning -b

# General system logs (last 30 minutes):
journalctl --since "30 min ago" --priority=err --no-pager

# Kernel messages (hardware errors, OOM, disk errors):
dmesg -T | tail -50
dmesg -T | grep -iE '(error|oom|kill|fail|panic|hardware)'
grep -i "out of memory\|oom\|killed process" /var/log/syslog
journalctl -k | grep -i "out of memory\|oom\|killed process"

# Disk errors
grep -i "i/o error\|read error\|write error\|sector" /var/log/syslog
smartctl -a /dev/sda  # If SMART is available

# Network errors
grep -i "network\|connection\|timeout\|refused" /var/log/syslog | tail -50

# Hardware errors
grep -i "hardware\|mce\|machine check\|ecc" /var/log/syslog
mcelog --client  # If mcelog is running

# === Continuous Log Monitoring ===
# Tail logs in real-time
tail -f /var/log/syslog | grep --line-buffered -i "error\|fail"
journalctl -f -p err

# Auth/SSH specific logs:
journalctl -u sshd --since "1 hour ago"
tail -100 /var/log/auth.log      # Debian/Ubuntu
tail -100 /var/log/secure         # RHEL/CentOS

# Cloud-init logs (if the instance recently (re)started):
tail -50 /var/log/cloud-init-output.log

# Application logs (could be the root cause of resource exhaustion):
journalctl -u your-app-service --since "1 hour ago"
tail -100 /var/log/nginx/error.log   # If nginx is on this host

# Check for recent reboots or shutdowns:
last reboot | head -5
last shutdown | head -5
who -b    # Last boot time
```

---

## Summary: Most Likely Root Causes (ranked by frequency)

1. **Disk full** (`/var/log` or `/` at 100%) — sshd silently fails.
2. **Security Group / NACL change** — someone modified rules, blocking port 22 from jump host.
3. **OOM killer terminated sshd** — application memory leak consumed all RAM.
4. **Instance system check failure** — underlying hardware issue (stop/start fixes this).
5. **iptables/nftables rule** — local firewall change blocking connections.
6. **CPU saturation** (load average >> core count) — connection attempt queued indefinitely.