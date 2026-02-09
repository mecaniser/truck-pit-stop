"""
Metrics Parser

Reads metrics from prometheus_client registry and returns structured data
for the admin performance dashboard.
"""
from typing import Any
from prometheus_client import REGISTRY, CollectorRegistry
from prometheus_client.metrics import MetricWrapperBase


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
    
    # Look for truckpitstop_http_requests_total or similar
    for name, data in all_metrics.items():
        if "requests_total" in name and "http" in name:
            for sample in data.get("samples", []):
                # Skip _created timestamp samples, but keep _total (the actual counter value)
                if sample["name"].endswith("_created"):
                    continue
                labels = sample["labels"]
                value = sample["value"]
                
                # Count by status
                status = labels.get("status", labels.get("status_code", ""))
                if status:
                    status_str = str(status)
                    if status_str.startswith("2"):
                        result["requests_by_status"]["2xx"] += int(value)
                    elif status_str.startswith("4"):
                        result["requests_by_status"]["4xx"] += int(value)
                    elif status_str.startswith("5"):
                        result["requests_by_status"]["5xx"] += int(value)
                
                result["requests_total"] += int(value)
                
                # Count by endpoint
                handler = labels.get("handler", labels.get("path", "unknown"))
                if handler and handler != "unknown":
                    endpoint_counts[handler] = endpoint_counts.get(handler, 0) + int(value)
    
    # Sort endpoints by count
    result["requests_by_endpoint"] = [
        {"path": path, "count": count}
        for path, count in sorted(endpoint_counts.items(), key=lambda x: -x[1])[:10]
    ]
    
    # Parse latency histograms
    for name, data in all_metrics.items():
        if "latency" in name or "duration" in name:
            if "http" in name:
                buckets = {}
                total_sum = 0
                total_count = 0
                
                for sample in data.get("samples", []):
                    if "_bucket" in sample["name"]:
                        le = sample["labels"].get("le", "")
                        if le and le != "+Inf":
                            buckets[float(le)] = sample["value"]
                    elif "_sum" in sample["name"]:
                        total_sum += sample["value"]
                    elif "_count" in sample["name"]:
                        total_count += sample["value"]
                
                if total_count > 0:
                    result["avg_latency_ms"] = round((total_sum / total_count) * 1000, 2)
                
                # Estimate percentiles from buckets
                if buckets and total_count > 0:
                    sorted_buckets = sorted(buckets.items())
                    result["p50_latency_ms"] = _estimate_percentile(sorted_buckets, total_count, 0.50) * 1000
                    result["p95_latency_ms"] = _estimate_percentile(sorted_buckets, total_count, 0.95) * 1000
                    result["p99_latency_ms"] = _estimate_percentile(sorted_buckets, total_count, 0.99) * 1000
    
    # Parse in-progress requests
    for name, data in all_metrics.items():
        if "inprogress" in name or "in_progress" in name:
            for sample in data.get("samples", []):
                result["requests_in_progress"] += int(sample["value"])
    
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
                status = sample["labels"].get("status", "")
                if status == "success":
                    result["logins"]["success"] += int(sample["value"])
                elif status == "failure":
                    result["logins"]["failure"] += int(sample["value"])
        
        # Logout metrics
        if "auth_logout" in name:
            for sample in data.get("samples", []):
                result["logouts"] += int(sample["value"])
        
        # Repair orders
        if "repair_orders_created" in name:
            for sample in data.get("samples", []):
                result["orders_created"] += int(sample["value"])
        
        # Quotes
        if "quotes_total" in name:
            for sample in data.get("samples", []):
                status = sample["labels"].get("status", "")
                if status in result["quotes"]:
                    result["quotes"][status] += int(sample["value"])
        
        # Payments
        if "payments_total" in name:
            for sample in data.get("samples", []):
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
    
    for name, data in all_metrics.items():
        # Python info
        if name == "python_info":
            for sample in data.get("samples", []):
                labels = sample["labels"]
                result["python_version"] = f"{labels.get('major', '?')}.{labels.get('minor', '?')}.{labels.get('patchlevel', '?')}"
        
        # GC collections
        if "gc_collections" in name:
            for sample in data.get("samples", []):
                result["gc_collections"] += int(sample["value"])
        
        # Process CPU
        if "process_cpu_seconds" in name:
            for sample in data.get("samples", []):
                result["process_cpu_seconds"] = round(sample["value"], 2)
        
        # Process memory
        if "process_resident_memory" in name or "process_virtual_memory" in name:
            for sample in data.get("samples", []):
                if sample["value"] > result["process_memory_bytes"]:
                    result["process_memory_bytes"] = int(sample["value"])
        
        # Active users gauge
        if "active_users" in name:
            for sample in data.get("samples", []):
                result["active_users"] = int(sample["value"])
    
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
