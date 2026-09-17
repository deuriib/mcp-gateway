# Runbook: MCP Gateway Performance Benchmark

**Spec:** SPEC-PERF-001
**Date:** 2026-09-16
**Owner:** vasquez (CTO)

## Prerequisites

1. Python 3.12+ with `uv` installed
2. MCP Gateway source code cloned (`D:\GitHub\mcp-gateway`)
3. Dependencies installed: `uv sync`
4. Benchmark dependencies: `uv pip install httpx pyyaml psutil`
5. MCP Gateway server running (for HTTP/SSE benchmarks)

## Machine Specification

Document your benchmark machine here for reproducibility:

- **OS:** [e.g., Windows 11, macOS 14, Ubuntu 22.04]
- **CPU:** [e.g., Apple M2 Pro, Intel i7-13700K, AMD Ryzen 9 7900X]
- **RAM:** [e.g., 16 GB, 32 GB]
- **Disk:** [e.g., NVMe SSD, 512 GB]
- **Python:** [e.g., 3.12.5]
- **uv:** [e.g., 0.4.0]

## Quick Start

### 1. Start MCP Gateway Server

```bash
# HTTP transport (recommended for benchmarks)
uv run mcp-gway serve --transport http --host 127.0.0.1 --port 8080

# OR SSE transport
uv run mcp-gway serve --transport sse --host 127.0.0.1 --port 8080

# OR stdio transport (no HTTP health endpoint)
uv run mcp-gway serve --transport stdio
```

### 2. Verify Server is Running

```bash
curl http://127.0.0.1:8080/health
# Expected: {"status": "ok"}
```

### 3. Run Benchmark

```bash
# Default config (10 concurrency, 30s duration)
uv run python docs/specs/30_delivery/bench_perf.py

# Custom config
uv run python docs/specs/30_delivery/bench_perf.py \
  --config docs/specs/30_delivery/perf_config.yaml \
  --concurrency 20 \
  --duration 60

# Custom output directory
uv run python docs/specs/30_delivery/bench_perf.py \
  --output-dir docs/specs/30_delivery/reports/custom
```

### 4. Read Results

Results are saved to `docs/specs/30_delivery/reports/`:
- `perf_report_<timestamp>.json` — Machine-readable data
- `perf_report_<timestamp>.md` — Human-readable summary

## Understanding the Results

### Latency Metrics

- **p50 (median):** 50% of requests complete within this time
- **p95:** 95% of requests complete within this time
- **p99:** 99% of requests complete within this time (SLO target)
- **Throughput (req/s):** Requests per second under concurrent load

### SLO Targets (Hypotheses to Validate)

| Path | p99 Target | Status |
|------|-----------|--------|
| `/mcp` POST | < 150ms | To be validated |
| `/health` | < 50ms | To be validated |
| `/ready` | < 50ms | To be validated |
| `/live` | < 50ms | To be validated |
| `/metrics` | < 50ms | To be validated |

### Code Mode Overhead

- **listToolFiles:** Time to list available tool files
- **readToolFile:** Time to read a tool file stub
- **getToolDocs:** Time to fetch tool documentation
- **executeToolCode:** Time to execute Starlark code in sandbox

## Interpreting `/metrics`

The `/metrics` endpoint exposes Prometheus-format metrics:

```
# HELP mcp_gateway_requests_total Total requests
# TYPE mcp_gateway_requests_total counter
mcp_gateway_requests_total{path="/mcp",method="POST"} 1234

# HELP mcp_gateway_request_duration_seconds Request duration
# TYPE mcp_gateway_request_duration_seconds histogram
mcp_gateway_request_duration_seconds_bucket{path="/mcp",le="0.1"} 1200
mcp_gateway_request_duration_seconds_bucket{path="/mcp",le="0.5"} 1230
mcp_gateway_request_duration_seconds_bucket{path="/mcp",le="1.0"} 1234
```

**Note:** `X-Warning: exposed` header appears only when server is bound to `0.0.0.0` without `MCP_GWAY_ALLOW_REMOTE=1`. Benchmarks should always run against `127.0.0.1`.

## Troubleshooting

### Server Not Starting

```bash
# Check if port is in use
netstat -an | grep 8080

# Use different port
uv run mcp-gway serve --transport http --host 127.0.0.1 --port 8081
```

### High Latency Results

1. Check CPU usage: `top` or Task Manager
2. Check memory: `free -h` or Activity Monitor
3. Check network: `ping 127.0.0.1`
4. Reduce concurrency: `--concurrency 5`

### Benchmark Script Errors

```bash
# Install missing dependencies
uv pip install httpx pyyaml psutil

# Check Python version
python --version  # Should be 3.12+
```

## Reproducibility Checklist

- [ ] Document machine specs above
- [ ] Record git commit hash: `git rev-parse HEAD`
- [ ] Record uv version: `uv --version`
- [ ] Record Python version: `python --version`
- [ ] Record dependencies: `uv pip list`
- [ ] Run benchmark 3 times, report median
- [ ] Compare with previous results if available

## Rollback

Benchmark is read-only observation. No rollback needed.

If benchmark script causes issues:
```bash
git rm docs/specs/30_delivery/bench_perf.py
git rm docs/specs/30_delivery/perf_config.yaml
```