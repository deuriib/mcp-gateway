from __future__ import annotations

import threading
from typing import Any

_DEFAULT_BUCKETS: list[float] = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5]


def _prefixed(name: str) -> str:
    if name.startswith("mcp_gway_"):
        return name
    return f"mcp_gway_{name}"


def _escape_label(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _label_str(labels: dict[str, str], extra: dict[str, str] | None = None) -> str:
    combined: dict[str, str] = {}
    combined.update(labels)
    if extra:
        combined.update(extra)
    if not combined:
        return ""
    parts = []
    for k in sorted(combined.keys()):
        v = _escape_label(str(combined[k]))
        parts.append(f'{k}="{v}"')
    return "{" + ",".join(parts) + "}"


def _hist_bucket_label(
    labels_dict: dict[str, str], labelnames: list[str], le_str: str
) -> str:
    parts: list[str] = []
    for k in labelnames:
        v = _escape_label(str(labels_dict.get(k, "")))
        parts.append(f'{k}="{v}"')
    parts.append(f'le="{_escape_label(le_str)}"')
    return "{" + ",".join(parts) + "}"


def _hist_labels_only(labels_dict: dict[str, str], labelnames: list[str]) -> str:
    if not labelnames:
        return ""
    parts = []
    for k in labelnames:
        v = _escape_label(str(labels_dict.get(k, "")))
        parts.append(f'{k}="{v}"')
    return "{" + ",".join(parts) + "}"


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._metrics: dict[str, dict[str, Any]] = {}

    def counter(
        self, name: str, help_text: str, labelnames: list[str] | None = None
    ) -> None:
        labelnames = labelnames or []
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = {
                    "help": help_text,
                    "type": "counter",
                    "labelnames": list(labelnames),
                    "data": {},  # type: ignore[dict]
                }
            else:
                # update help if needed
                self._metrics[name]["help"] = help_text

    def gauge(
        self, name: str, help_text: str, labelnames: list[str] | None = None
    ) -> None:
        labelnames = labelnames or []
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = {
                    "help": help_text,
                    "type": "gauge",
                    "labelnames": list(labelnames),
                    "data": {},
                }
            else:
                self._metrics[name]["help"] = help_text

    def histogram(
        self,
        name: str,
        help_text: str,
        labelnames: list[str] | None = None,
        buckets: list[float] | None = None,
    ) -> None:
        labelnames = labelnames or []
        buckets = sorted(buckets) if buckets is not None else list(_DEFAULT_BUCKETS)
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = {
                    "help": help_text,
                    "type": "histogram",
                    "labelnames": list(labelnames),
                    "buckets": list(buckets),
                    "data": {},
                }
            else:
                self._metrics[name]["help"] = help_text
                # do not overwrite buckets if already exists

    def inc(
        self, name: str, labels: dict[str, str] | None = None, amount: int = 1
    ) -> None:
        labels = labels or {}
        with self._lock:
            meta = self._metrics.get(name)
            if meta is None:
                # auto-create counter with labelnames from labels keys sorted
                meta = {
                    "help": "",
                    "type": "counter",
                    "labelnames": sorted(labels.keys()),
                    "data": {},
                }
                self._metrics[name] = meta
            # normalize label tuple key
            key = self._label_key(meta["labelnames"], labels)
            data: dict[tuple[str, ...], int] = meta["data"]
            data[key] = data.get(key, 0) + amount

    def set(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        labels = labels or {}
        with self._lock:
            meta = self._metrics.get(name)
            if meta is None:
                meta = {
                    "help": "",
                    "type": "gauge",
                    "labelnames": sorted(labels.keys()),
                    "data": {},
                }
                self._metrics[name] = meta
            key = self._label_key(meta["labelnames"], labels)
            data: dict[tuple[str, ...], float] = meta["data"]
            data[key] = float(value)

    def observe(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        labels = labels or {}
        with self._lock:
            meta = self._metrics.get(name)
            if meta is None:
                meta = {
                    "help": "",
                    "type": "histogram",
                    "labelnames": sorted(labels.keys()),
                    "buckets": list(_DEFAULT_BUCKETS),
                    "data": {},
                }
                self._metrics[name] = meta
            buckets: list[float] = meta.get("buckets", list(_DEFAULT_BUCKETS))  # type: ignore[assignment]
            key = self._label_key(meta["labelnames"], labels)
            data: dict[tuple[str, ...], dict[str, Any]] = meta["data"]
            entry = data.get(key)
            if entry is None:
                entry = {"bucket_counts": [0] * len(buckets), "sum": 0.0, "count": 0}
                data[key] = entry
            # update buckets cumulative counts not needed now, just counts per bucket cumulative later
            # For each bucket where value <= le, increment
            for i, le in enumerate(buckets):
                if value <= le:
                    entry["bucket_counts"][i] += 1  # type: ignore[index]
            # Note: we store per-bucket non-cumulative but exposition will make cumulative
            # Instead we store counts per bucket threshold increment only for buckets where <= value
            # But to get cumulative easily, we can store bucket_counts as per-bucket with cumulative logic:
            # Our loop already increments only buckets where value <= le, which for cumulative means
            # all buckets >= value should be incremented. That's what we do above? Actually value <= le means bucket threshold >= value, so those buckets count the observation.
            # e.g., value 0.04, buckets 0.05,0.1 -> both >=0.04, both should be 1 cumulative. Our loop does increment both. For value 0.2, buckets 0.05,0.1,0.5 => only 0.5 qualifies. That's correct cumulative.
            entry["sum"] = float(entry["sum"]) + float(value)  # type: ignore[operator]
            entry["count"] = int(entry["count"]) + 1  # type: ignore[operator]
            # Need to also handle later cumulative: for earlier buckets that didn't qualify, they stay 0, which matches cumulative.
            # For histogram we need cumulative, but our increment above already makes cumulative because we increment all buckets >= value.

    def _label_key(
        self, labelnames: list[str], labels: dict[str, str]
    ) -> tuple[str, ...]:
        return tuple(str(labels.get(k, "")) for k in labelnames)

    def _labels_dict(
        self, labelnames: list[str], key: tuple[str, ...]
    ) -> dict[str, str]:
        return {k: v for k, v in zip(labelnames, key)}

    def exposition(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name in sorted(self._metrics.keys()):
                meta = self._metrics[name]
                prefixed = _prefixed(name)
                help_text = meta["help"]
                mtype = meta["type"]
                labelnames: list[str] = meta["labelnames"]
                data = meta["data"]
                buckets: list[float] = meta.get("buckets", [])  # type: ignore[assignment]
                lines.append(f"# HELP {prefixed} {help_text}")
                lines.append(f"# TYPE {prefixed} {mtype}")
                if mtype == "counter":
                    # sort by label tuple string
                    for key in sorted(data.keys()):
                        labels_dict = self._labels_dict(labelnames, key)
                        val = data[key]
                        lbl = _label_str(labels_dict)
                        if lbl:
                            lines.append(f"{prefixed}{lbl} {val}")
                        else:
                            lines.append(f"{prefixed} {val}")
                elif mtype == "gauge":
                    for key in sorted(data.keys()):
                        labels_dict = self._labels_dict(labelnames, key)
                        val = data[key]
                        lbl = _label_str(labels_dict)
                        # format without trailing .0 if integer?
                        if isinstance(val, float) and val.is_integer():
                            val_str = str(int(val))
                        else:
                            val_str = str(val)
                        if lbl:
                            lines.append(f"{prefixed}{lbl} {val_str}")
                        else:
                            lines.append(f"{prefixed} {val_str}")
                elif mtype == "histogram":
                    if not data:
                        for le in buckets:
                            le_str = _format_le(le)
                            lbl = f'{{le="{_escape_label(le_str)}"}}'
                            lines.append(f"{prefixed}_bucket{lbl} 0")
                        lines.append(f'{prefixed}_bucket{{le="+Inf"}} 0')
                        lines.append(f"{prefixed}_sum 0")
                        lines.append(f"{prefixed}_count 0")
                        continue
                    for key in sorted(data.keys()):
                        labels_dict = self._labels_dict(labelnames, key)
                        entry = data[key]
                        bucket_counts: list[int] = entry["bucket_counts"]  # type: ignore[assignment]
                        count_val: int = entry["count"]  # type: ignore[assignment]
                        sum_val: float = entry["sum"]  # type: ignore[assignment]
                        for i, le in enumerate(buckets):
                            le_str = _format_le(le)
                            lbl = _hist_bucket_label(labels_dict, labelnames, le_str)
                            lines.append(f"{prefixed}_bucket{lbl} {bucket_counts[i]}")
                        lbl_inf = _hist_bucket_label(labels_dict, labelnames, "+Inf")
                        lines.append(f"{prefixed}_bucket{lbl_inf} {count_val}")
                        lbl_no_le = _hist_labels_only(labels_dict, labelnames)
                        sum_str = _format_sum(sum_val)
                        if lbl_no_le:
                            lines.append(f"{prefixed}_sum{lbl_no_le} {sum_str}")
                            lines.append(f"{prefixed}_count{lbl_no_le} {count_val}")
                        else:
                            lines.append(f"{prefixed}_sum {sum_str}")
                            lines.append(f"{prefixed}_count {count_val}")
                else:
                    continue
        if not lines:
            return ""
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._metrics.clear()


def _format_le(le: float) -> str:
    if le == int(le):
        # Keep as int string? But Prometheus often uses e.g., 5 not 5.0, but for 0.05 need decimal
        # For histogram, 5 should be "5", 0.05 should be "0.05"
        # If le is integer value like 1, 5, format as "1" or "5"
        return (
            str(int(le))
            if le == int(le) and le not in (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5)
            else str(le)
        )
    # Remove trailing zeros
    s = str(le)
    return s


def _format_sum(val: float) -> str:
    # Keep as Python repr, but for integer sums ensure decimal?
    # Tests check _sum contains float value; we just str.
    if val == int(val):
        # Prometheus expects sum as float, e.g., "0.04" for single observe 0.04 -> not integer
        # So keep as is
        return str(val)
    return str(val)
