"""
Metrics Parser

Reads metrics from prometheus_client registry and returns structured data
for the admin performance dashboard.
"""
import gc
import platform
import resource
import time
from typing import Any
from prometheus_client import REGISTRY


def get_metric_value(metric_name: str, labels: dict = None) -> float:
    """Get a single metric value by name and optional labels."""
    for metric in REGISTRY.collect():
        if metric.name == metric_name:
            for sample in metric.samples:
                if labels is None:
                    return sample.value
                # Check if all labels match
                if all(sample.labels.get(k) == v for k, v in labels.items()):
                    return sample.value
    return 0.0


def get_all_samples(metric_name: str) -> list[dict]:
    """Get all samples for a metric with their labels."""
    samples = []
    for metric in REGISTRY.collect():
        if metric.name == metric_name or metric.name.startswith(f"{metric_name}_"):
            for sample in metric.samples:
                samples.append({
                    "name": sample.name,
                    "labels": dict(sample.labels),
                    "value": sample.value,
                })
    return samples


def get_performance_stats() -> dict[str, Any]:
    """
    Collect all performance metrics from the Prometheus registry.
    
    Returns structured data for the admin dashboard.
    """
    # Collect all metrics
    all_metrics = {}
    for metric in REGISTRY.collect():
        all_metrics[metric.name] = {
            "type": metric.type,
            "samples": [
                {"name": s.name, "labels": dict(s.labels), "value": s.value}
                for s in metric.samples
            ]
        }
    
    # HTTP metrics
    http_stats = _parse_http_metrics(all_metrics)
    
    # Business metrics
    business_stats = _parse_business_metrics(all_metrics)
    
    # System metrics
    system_stats = _parse_system_metrics(all_metrics)
    
    return {
        "http": http_stats,
        "business": business_stats,
        "system": system_stats,
    }


def _iter_samples(all_metrics: dict[str, dict[str, Any]]):
    for metric_data in all_metrics.values():
        for sample in metric_data.get("samples", []):
            yield sample


def _is_created_sample(sample_name: str) -> bool:
    return sample_name.endswith("_created")


def _is_http_request_total_sample(sample_name: str, labels: dict[str, Any]) -> bool:
    if not sample_name.endswith("_total"):
        return False
    if "http" not in sample_name or "request" not in sample_name:
        return False
    # Instrumentator request counters include handler/method/status labels.
    return "handler" in labels or "method" in labels or "status" in labels


def _parse_http_metrics(all_metrics: dict) -> dict:
    """Parse HTTP-related metrics."""
    result = {
        "requests_total": 0,
        "requests_by_status": {"2xx": 0, "4xx": 0, "5xx": 0},
        "requests_by_endpoint": [],
        "avg_latency_ms": 0.0,
        "p50_latency_ms": 0.0,
        "p95_latency_ms": 0.0,
        "p99_latency_ms": 0.0,
        "requests_in_progress": 0,
    }

    # Parse request counts by status
    endpoint_counts = {}

    for sample in _iter_samples(all_metrics):
        sample_name = sample["name"]
        if _is_created_sample(sample_name):
            continue
        labels = sample["labels"]

        if _is_http_request_total_sample(sample_name, labels):
            value = int(sample["value"])
            result["requests_total"] += value

            status = str(labels.get("status") or labels.get("status_code") or "")
            if status.startswith("2"):
                result["requests_by_status"]["2xx"] += value
            elif status.startswith("4"):
                result["requests_by_status"]["4xx"] += value
            elif status.startswith("5"):
                result["requests_by_status"]["5xx"] += value

            handler = labels.get("handler") or labels.get("path") or labels.get("route")
            if handler and handler not in ("unknown", "none"):
                endpoint_counts[handler] = endpoint_counts.get(handler, 0) + value

        if "requests_inprogress" in sample_name or "requests_in_progress" in sample_name:
            result["requests_in_progress"] += int(sample["value"])

    # Sort endpoints by count
    result["requests_by_endpoint"] = [
        {"path": path, "count": count}
        for path, count in sorted(endpoint_counts.items(), key=lambda x: -x[1])[:10]
    ]

    # Parse one authoritative HTTP latency histogram.
    histogram_candidates = [
        name
        for name, data in all_metrics.items()
        if data.get("type") == "histogram" and "http" in name and ("duration" in name or "latency" in name)
    ]
    selected_histogram = None
    for preferred_suffix in (
        "http_request_duration_seconds",
        "request_duration_seconds",
        "http_request_latency_seconds",
    ):
        selected_histogram = next(
            (name for name in histogram_candidates if name.endswith(preferred_suffix)),
            None,
        )
        if selected_histogram:
            break
    if not selected_histogram and histogram_candidates:
        selected_histogram = sorted(histogram_candidates)[0]

    if selected_histogram:
        buckets: dict[float, float] = {}
        total_sum = 0.0
        total_count = 0.0
        for sample in all_metrics[selected_histogram].get("samples", []):
            sample_name = sample["name"]
            if _is_created_sample(sample_name):
                continue
            if sample_name.endswith("_bucket"):
                le = sample["labels"].get("le", "")
                if le and le != "+Inf":
                    buckets[float(le)] = float(sample["value"])
            elif sample_name.endswith("_sum"):
                total_sum += float(sample["value"])
            elif sample_name.endswith("_count"):
                total_count += float(sample["value"])

        if total_count > 0:
            result["avg_latency_ms"] = round((total_sum / total_count) * 1000, 2)
            if buckets:
                sorted_buckets = sorted(buckets.items())
                result["p50_latency_ms"] = round(_estimate_percentile(sorted_buckets, total_count, 0.50) * 1000, 2)
                result["p95_latency_ms"] = round(_estimate_percentile(sorted_buckets, total_count, 0.95) * 1000, 2)
                result["p99_latency_ms"] = round(_estimate_percentile(sorted_buckets, total_count, 0.99) * 1000, 2)

    return result


def _parse_business_metrics(all_metrics: dict) -> dict:
    """Parse business-related metrics."""
    result = {
        "logins": {"success": 0, "failure": 0},
        "logouts": 0,
        "orders_created": 0,
        "quotes": {"created": 0, "approved": 0, "declined": 0},
        "payments": {"success": 0, "failure": 0},
    }

    for name, data in all_metrics.items():
        # Login metrics
        if "auth_login" in name:
            for sample in data.get("samples", []):
                if _is_created_sample(sample["name"]):
                    continue
                status = sample["labels"].get("status", "")
                if status == "success":
                    result["logins"]["success"] += int(sample["value"])
                elif status == "failure":
                    result["logins"]["failure"] += int(sample["value"])

        # Logout metrics
        if "auth_logout" in name:
            for sample in data.get("samples", []):
                if _is_created_sample(sample["name"]):
                    continue
                result["logouts"] += int(sample["value"])

        # Repair orders
        if "repair_orders_created" in name:
            for sample in data.get("samples", []):
                if _is_created_sample(sample["name"]):
                    continue
                result["orders_created"] += int(sample["value"])

        # Quotes
        if name.endswith("quotes") or "quotes_total" in name:
            for sample in data.get("samples", []):
                if _is_created_sample(sample["name"]):
                    continue
                status = sample["labels"].get("status", "")
                if status in result["quotes"]:
                    result["quotes"][status] += int(sample["value"])

        # Payments
        if name.endswith("payments") or "payments_total" in name:
            for sample in data.get("samples", []):
                if _is_created_sample(sample["name"]):
                    continue
                status = sample["labels"].get("status", "")
                if status == "success":
                    result["payments"]["success"] += int(sample["value"])
                elif status in ("failure", "failed"):
                    result["payments"]["failure"] += int(sample["value"])

    return result


def _parse_system_metrics(all_metrics: dict) -> dict:
    """Parse system-related metrics."""
    result = {
        "python_version": "unknown",
        "gc_collections": 0,
        "process_cpu_seconds": 0.0,
        "process_memory_bytes": 0,
        "active_users": 0,
    }

    login_success_total = 0
    logout_total = 0

    for name, data in all_metrics.items():
        # Python info
        if name == "python_info":
            for sample in data.get("samples", []):
                labels = sample["labels"]
                major = labels.get("major")
                minor = labels.get("minor")
                patch = labels.get("patchlevel")
                if major is not None and minor is not None and patch is not None:
                    result["python_version"] = f"{major}.{minor}.{patch}"
                elif labels.get("version"):
                    result["python_version"] = labels["version"]

        # GC collections
        if "gc_collections" in name:
            for sample in data.get("samples", []):
                if _is_created_sample(sample["name"]):
                    continue
                result["gc_collections"] += int(sample["value"])

        # Process CPU
        if "process_cpu_seconds" in name:
            for sample in data.get("samples", []):
                if _is_created_sample(sample["name"]):
                    continue
                result["process_cpu_seconds"] = round(sample["value"], 2)

        # Process memory
        if "process_resident_memory" in name or "process_virtual_memory" in name:
            for sample in data.get("samples", []):
                if _is_created_sample(sample["name"]):
                    continue
                if sample["value"] > result["process_memory_bytes"]:
                    result["process_memory_bytes"] = int(sample["value"])

        # Active users gauge
        if "active_users" in name:
            for sample in data.get("samples", []):
                if _is_created_sample(sample["name"]):
                    continue
                result["active_users"] = int(sample["value"])

        # Keep auth counters for a fallback active-user approximation.
        if "auth_login" in name:
            for sample in data.get("samples", []):
                if _is_created_sample(sample["name"]):
                    continue
                if sample["labels"].get("status") == "success":
                    login_success_total += int(sample["value"])
        if "auth_logout" in name:
            for sample in data.get("samples", []):
                if _is_created_sample(sample["name"]):
                    continue
                logout_total += int(sample["value"])

    # Fallbacks for environments without process_* collectors (e.g., macOS local dev).
    if result["python_version"] == "unknown":
        result["python_version"] = platform.python_version()

    if result["gc_collections"] == 0:
        try:
            result["gc_collections"] = sum(g.get("collections", 0) for g in gc.get_stats())
        except Exception:
            pass

    if result["process_cpu_seconds"] == 0:
        result["process_cpu_seconds"] = round(time.process_time(), 2)

    if result["process_memory_bytes"] == 0:
        try:
            ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if platform.system() == "Darwin":
                # macOS already reports bytes
                result["process_memory_bytes"] = int(ru_maxrss)
            else:
                # Linux reports KiB
                result["process_memory_bytes"] = int(ru_maxrss * 1024)
        except Exception:
            pass

    if result["active_users"] == 0:
        result["active_users"] = max(login_success_total - logout_total, 0)

    return result


def _estimate_percentile(sorted_buckets: list[tuple], total_count: float, percentile: float) -> float:
    """
    Estimate a percentile from histogram buckets.
    
    This is an approximation - for exact percentiles, use summary metrics.
    """
    if not sorted_buckets or total_count == 0:
        return 0.0
    
    target = total_count * percentile
    prev_bound = 0.0
    prev_count = 0.0
    
    for bound, count in sorted_buckets:
        if count >= target:
            # Linear interpolation within the bucket
            bucket_count = count - prev_count
            if bucket_count > 0:
                fraction = (target - prev_count) / bucket_count
                return prev_bound + (bound - prev_bound) * fraction
            return bound
        prev_bound = bound
        prev_count = count
    
    # Return the highest bucket bound
    return sorted_buckets[-1][0] if sorted_buckets else 0.0
