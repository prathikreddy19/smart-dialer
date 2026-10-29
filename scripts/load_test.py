"""Small standard-library HTTP smoke/load test for the local API."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_health(url: str) -> tuple[float, int]:
    started = time.perf_counter()
    try:
        with urlopen(Request(url, method="GET"), timeout=10) as response:
            response.read()
            return time.perf_counter() - started, response.status
    except HTTPError as exc:
        return time.perf_counter() - started, exc.code
    except URLError:
        return time.perf_counter() - started, 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/health")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    if args.requests < 1 or args.workers < 1:
        parser.error("--requests and --workers must be positive")
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(request_health, args.url) for _ in range(args.requests)]
        results = [future.result() for future in as_completed(futures)]
    latencies = sorted(duration for duration, _ in results)
    successes = sum(status == 200 for _, status in results)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    elapsed = time.perf_counter() - started
    print(f"Requests: {args.requests}; successful: {successes}; elapsed: {elapsed:.2f}s; "
          f"throughput: {args.requests / elapsed:.1f} req/s; p95: {p95 * 1000:.1f} ms")
    return 0 if successes == args.requests else 1


if __name__ == "__main__":
    raise SystemExit(main())
