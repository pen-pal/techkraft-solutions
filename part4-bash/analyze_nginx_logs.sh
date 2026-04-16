#!/usr/bin/env bash
# analyze_nginx_logs.sh — Nginx access log analyser
#
# Handles both common and combined log formats.
# Uses only awk, sed, sort, uniq — no external dependencies.
#
# Usage: ./analyze_nginx_logs.sh <log_file> [top_n]
# Example: ./analyze_nginx_logs.sh /var/log/nginx/access.log

set -euo pipefail

LOG_FILE="${1:-}"
TOP_N="${2:-10}"

if [[ -z "$LOG_FILE" ]]; then
    echo "Usage: $(basename "$0") <log_file> [top_n]" >&2
    exit 1
fi

if [[ ! -r "$LOG_FILE" ]]; then
    echo "Error: cannot read '$LOG_FILE'" >&2
    exit 1
fi

if [[ ! -s "$LOG_FILE" ]]; then
    echo "Log file is empty." >&2
    exit 0
fi

# ---------------------------------------------------------------------------
# Single awk pass — emits "ip <TAB> status <TAB> endpoint" for valid lines,
# counts malformed ones, and writes all counters to a trailer prefixed "#".
# Format-agnostic: finds the request string between the first pair of quotes
# and the status code as the first 3-digit number after it. Works for both
# common and combined log formats, and tolerates extra fields.
# ---------------------------------------------------------------------------
parsed=$(awk '
{
    # IP must start with a digit (IPv4/IPv6) — skip "-" and other junk
    if ($1 !~ /^[0-9a-fA-F]/) { bad++; next }

    # Find request string between first pair of double quotes
    q1 = index($0, "\"");                        if (!q1) { bad++; next }
    rest = substr($0, q1 + 1)
    q2 = index(rest, "\"");                      if (!q2) { bad++; next }

    request = substr(rest, 1, q2 - 1)            # METHOD URI PROTO
    after   = substr(rest, q2 + 1)               # space STATUS SIZE ...

    # URI = second token of the request
    split(request, r, " ")
    endpoint = (r[2] == "" ? "/" : r[2])
    sub(/\?.*/, "", endpoint)                    # drop query string

    # Status = first 3-digit number after the closing quote
    n = split(after, a, " ")
    status = ""
    for (i = 1; i <= n; i++) {
        if (a[i] ~ /^[1-5][0-9][0-9]$/) { status = a[i]; break }
    }
    if (status == "") { bad++; next }

    print $1 "\t" status "\t" endpoint
}
END {
    print "#malformed\t" (bad + 0)
}
' "$LOG_FILE")

# Split the malformed counter off the trailer
malformed=$(echo "$parsed" | sed -n 's/^#malformed\t//p')
parsed=$(echo "$parsed"    | sed '/^#/d')

# ---------------------------------------------------------------------------
# Aggregates via pipeline: sort | uniq -c | sort -rn
# ---------------------------------------------------------------------------
total=$(echo "$parsed" | sed '/^$/d' | wc -l | tr -d ' ')

if [[ "$total" -eq 0 ]]; then
    echo "No valid log entries found." >&2
    exit 0
fi

e4=$(echo "$parsed" | awk -F'\t' '$2 ~ /^4/' | wc -l | tr -d ' ')
e5=$(echo "$parsed" | awk -F'\t' '$2 ~ /^5/' | wc -l | tr -d ' ')
unique_ips=$(echo "$parsed" | awk -F'\t' '{print $1}' | sort -u | wc -l | tr -d ' ')

# Helpers — thousands separator and percentage (awk does both)
fmt() { awk -v n="$1" 'BEGIN{
    s=""; while(n>=1000){ s=sprintf(",%03d%s",n%1000,s); n=int(n/1000) }
    printf "%d%s", n, s
}'; }
pct() { awk -v a="$1" -v b="$2" 'BEGIN{ printf "%.2f", b ? a*100/b : 0 }'; }

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
printf "\n=== Nginx Log Analysis Report ===\n"
printf "Log file:         %s\n" "$LOG_FILE"
printf "Total Requests:   %s\n" "$(fmt "$total")"
printf "Unique IPs:       %s\n" "$(fmt "$unique_ips")"
printf "4xx Errors:       %s (%s%%)\n" "$(fmt "$e4")" "$(pct "$e4" "$total")"
printf "5xx Errors:       %s (%s%%)\n" "$(fmt "$e5")" "$(pct "$e5" "$total")"
[[ "$malformed" -gt 0 ]] && printf "Malformed lines:  %s (skipped)\n" "$(fmt "$malformed")"

# Top N IPs
printf "\nTop %d IPs:\n" "$TOP_N"
printf "  %-5s %-40s %s\n" "Rank" "IP Address" "Requests"
printf "  %-5s %-40s %s\n" "-----" "----------------------------------------" "--------"
echo "$parsed" | awk -F'\t' '{print $1}' | sort | uniq -c | sort -rn | head -n "$TOP_N" \
    | awk '{printf "  %-5d %-40s %s requests\n", NR, $2, $1}'

# Top N endpoints
printf "\nTop %d Endpoints:\n" "$TOP_N"
printf "  %-5s %-50s %s\n" "Rank" "Endpoint" "Requests"
printf "  %-5s %-50s %s\n" "-----" "--------------------------------------------------" "--------"
echo "$parsed" | awk -F'\t' '{print $3}' | sort | uniq -c | sort -rn | head -n "$TOP_N" \
    | awk '{printf "  %-5d %-50s %s requests\n", NR, $2, $1}'

echo