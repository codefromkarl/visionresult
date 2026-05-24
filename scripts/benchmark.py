#!/usr/bin/env python3
"""Performance benchmark script for Vision Insight Agent.

Usage:
    python scripts/benchmark.py [--host http://localhost:8000] [--requests 100] [--concurrent 10]
"""

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image
import io


@dataclass
class BenchmarkResult:
    """Benchmark result for a single request."""
    
    status_code: int
    latency_ms: float
    success: bool
    error: str | None = None


@dataclass
class BenchmarkSummary:
    """Summary of benchmark results."""
    
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_time_seconds: float
    requests_per_second: float
    latency_min_ms: float
    latency_max_ms: float
    latency_mean_ms: float
    latency_median_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    error_distribution: dict[str, int]


def create_test_image(width: int = 100, height: int = 100) -> bytes:
    """Create a test image."""
    img = Image.new("RGB", (width, height), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def send_request(
    client: httpx.AsyncClient,
    url: str,
    image_bytes: bytes,
) -> BenchmarkResult:
    """Send a single analysis request."""
    start_time = time.time()
    
    try:
        files = {"file": ("test.png", image_bytes, "image/png")}
        response = await client.post(f"{url}/api/v1/analyze", files=files)
        latency_ms = (time.time() - start_time) * 1000
        
        return BenchmarkResult(
            status_code=response.status_code,
            latency_ms=latency_ms,
            success=response.status_code == 200,
            error=None if response.status_code == 200 else response.text[:100],
        )
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        return BenchmarkResult(
            status_code=0,
            latency_ms=latency_ms,
            success=False,
            error=str(e)[:100],
        )


async def run_benchmark(
    host: str,
    num_requests: int,
    concurrency: int,
) -> BenchmarkSummary:
    """Run benchmark with specified parameters."""
    image_bytes = create_test_image()
    
    print(f"🚀 Starting benchmark:")
    print(f"   Host: {host}")
    print(f"   Requests: {num_requests}")
    print(f"   Concurrency: {concurrency}")
    print()
    
    results: list[BenchmarkResult] = []
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(concurrency)
        
        async def bounded_request() -> BenchmarkResult:
            async with semaphore:
                return await send_request(client, host, image_bytes)
        
        # Send all requests
        tasks = [bounded_request() for _ in range(num_requests)]
        results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    
    # Calculate statistics
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    latencies = [r.latency_ms for r in results]
    
    # Error distribution
    error_dist: dict[str, int] = {}
    for r in failed:
        error_key = f"{r.status_code}: {r.error}" if r.error else str(r.status_code)
        error_dist[error_key] = error_dist.get(error_key, 0) + 1
    
    # Calculate percentiles
    sorted_latencies = sorted(latencies)
    p95_idx = int(len(sorted_latencies) * 0.95)
    p99_idx = int(len(sorted_latencies) * 0.99)
    
    return BenchmarkSummary(
        total_requests=num_requests,
        successful_requests=len(successful),
        failed_requests=len(failed),
        total_time_seconds=round(total_time, 2),
        requests_per_second=round(num_requests / total_time, 2),
        latency_min_ms=round(min(latencies), 2) if latencies else 0,
        latency_max_ms=round(max(latencies), 2) if latencies else 0,
        latency_mean_ms=round(statistics.mean(latencies), 2) if latencies else 0,
        latency_median_ms=round(statistics.median(latencies), 2) if latencies else 0,
        latency_p95_ms=round(sorted_latencies[p95_idx], 2) if latencies else 0,
        latency_p99_ms=round(sorted_latencies[p99_idx], 2) if latencies else 0,
        error_distribution=error_dist,
    )


def print_summary(summary: BenchmarkSummary) -> None:
    """Print benchmark summary."""
    print("=" * 60)
    print("📊 Benchmark Results")
    print("=" * 60)
    print()
    
    print(f"Total Requests:      {summary.total_requests}")
    print(f"Successful:          {summary.successful_requests} ({summary.successful_requests/summary.total_requests*100:.1f}%)")
    print(f"Failed:              {summary.failed_requests} ({summary.failed_requests/summary.total_requests*100:.1f}%)")
    print()
    
    print(f"Total Time:          {summary.total_time_seconds}s")
    print(f"Requests/sec:        {summary.requests_per_second}")
    print()
    
    print("Latency Distribution:")
    print(f"  Min:               {summary.latency_min_ms}ms")
    print(f"  Max:               {summary.latency_max_ms}ms")
    print(f"  Mean:              {summary.latency_mean_ms}ms")
    print(f"  Median:            {summary.latency_median_ms}ms")
    print(f"  P95:               {summary.latency_p95_ms}ms")
    print(f"  P99:               {summary.latency_p99_ms}ms")
    print()
    
    if summary.error_distribution:
        print("Error Distribution:")
        for error, count in sorted(summary.error_distribution.items(), key=lambda x: -x[1]):
            print(f"  {error}: {count}")
    print()
    
    # Performance assessment
    print("Performance Assessment:")
    if summary.requests_per_second >= 10:
        print("  ✅ Throughput: Excellent (>= 10 req/s)")
    elif summary.requests_per_second >= 5:
        print("  ⚠️  Throughput: Good (>= 5 req/s)")
    else:
        print("  ❌ Throughput: Poor (< 5 req/s)")
    
    if summary.latency_p95_ms <= 1000:
        print("  ✅ P95 Latency: Excellent (<= 1s)")
    elif summary.latency_p95_ms <= 3000:
        print("  ⚠️  P95 Latency: Good (<= 3s)")
    else:
        print("  ❌ P95 Latency: Poor (> 3s)")
    
    if summary.successful_requests / summary.total_requests >= 0.99:
        print("  ✅ Success Rate: Excellent (>= 99%)")
    elif summary.successful_requests / summary.total_requests >= 0.95:
        print("  ⚠️  Success Rate: Good (>= 95%)")
    else:
        print("  ❌ Success Rate: Poor (< 95%)")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Vision Insight Agent Benchmark")
    parser.add_argument(
        "--host",
        type=str,
        default="http://localhost:8000",
        help="API host URL",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=50,
        help="Number of requests to send",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=5,
        help="Number of concurrent requests",
    )
    
    args = parser.parse_args()
    
    summary = asyncio.run(
        run_benchmark(args.host, args.requests, args.concurrent)
    )
    print_summary(summary)


if __name__ == "__main__":
    main()
