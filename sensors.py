from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional
import glob
import os
import re
import subprocess

import psutil


@dataclass
class SensorValue:
    name: str
    value: Optional[float]


def _read_text(path: str | Path) -> Optional[str]:
    try:
        return Path(path).read_text(errors="ignore").strip()
    except Exception:
        return None


def _read_temp_milli(path: str | Path) -> Optional[float]:
    txt = _read_text(path)
    if txt is None:
        return None
    try:
        raw = float(txt)
    except ValueError:
        return None
    # Linux hwmon temp*_input is usually millidegrees Celsius.
    if raw > 1000:
        return raw / 1000.0
    return raw


def cpu_usage() -> tuple[float, List[float]]:
    total = psutil.cpu_percent(interval=None)
    cores = psutil.cpu_percent(interval=None, percpu=True)
    return total, cores


def memory_usage() -> tuple[float, float, float]:
    mem = psutil.virtual_memory()
    return float(mem.percent), mem.used / 1024**3, mem.total / 1024**3


def storage_usages() -> List[dict]:
    result: List[dict] = []
    seen = set()
    skip_fs = {"tmpfs", "devtmpfs", "overlay", "squashfs", "proc", "sysfs", "devpts", "cgroup", "cgroup2", "securityfs", "pstore", "efivarfs", "debugfs", "tracefs", "fusectl", "configfs"}
    for part in psutil.disk_partitions(all=False):
        if part.mountpoint in seen or part.fstype in skip_fs:
            continue
        seen.add(part.mountpoint)
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except Exception:
            continue
        if usage.total <= 0:
            continue
        result.append({
            "device": part.device,
            "mountpoint": part.mountpoint,
            "fstype": part.fstype,
            "percent": float(usage.percent),
            "used_gb": usage.used / 1024**3,
            "total_gb": usage.total / 1024**3,
            "free_gb": usage.free / 1024**3,
        })
    result.sort(key=lambda x: (x["mountpoint"] != "/", x["mountpoint"]))
    return result


def cpu_temperature_values() -> List[SensorValue]:
    values: List[SensorValue] = []

    try:
        temps = psutil.sensors_temperatures(fahrenheit=False)
    except Exception:
        temps = {}
    for chip, entries in temps.items():
        chip_l = chip.lower()
        if not any(k in chip_l for k in ("coretemp", "k10temp", "cpu", "zenpower", "acpitz", "thinkpad")):
            continue
        for entry in entries:
            label = entry.label or chip
            cur = entry.current
            if cur is None:
                continue
            name = f"{chip}: {label}" if label != chip else chip
            values.append(SensorValue(name=name, value=float(cur)))

    if values:
        return _dedupe(values)

    # Fallback: parse /sys/class/hwmon directly.
    for hw in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        chip = _read_text(Path(hw) / "name") or Path(hw).name
        chip_l = chip.lower()
        if not any(k in chip_l for k in ("coretemp", "k10temp", "cpu", "zenpower", "acpitz", "thinkpad")):
            continue
        for inp in sorted(glob.glob(f"{hw}/temp*_input")):
            idx = re.search(r"temp(\d+)_input", inp)
            label_path = f"{hw}/temp{idx.group(1)}_label" if idx else ""
            label = _read_text(label_path) if label_path else None
            val = _read_temp_milli(inp)
            if val is not None:
                values.append(SensorValue(name=f"{chip}: {label or Path(inp).name}", value=val))
    return _dedupe(values)


def nvme_temperature_values() -> List[SensorValue]:
    values: List[SensorValue] = []

    # Preferred: hwmon under each NVMe controller, no sudo needed on most systems.
    for nvme in sorted(glob.glob("/sys/class/nvme/nvme*")):
        devname = Path(nvme).name
        base = Path(nvme).resolve()
        hwmon_dirs = sorted(base.glob("device/hwmon/hwmon*")) + sorted(base.glob("hwmon*")) + sorted(base.glob("hwmon*/hwmon*"))
        for hw in hwmon_dirs:
            if not hw.is_dir():
                continue
            for inp in sorted(hw.glob("temp*_input")):
                idx = re.search(r"temp(\d+)_input", inp.name)
                label = _read_text(hw / f"temp{idx.group(1)}_label") if idx else None
                val = _read_temp_milli(inp)
                if val is not None:
                    display = devname if not label else f"{devname}: {label}"
                    values.append(SensorValue(name=display, value=val))

    if values:
        return _dedupe(values)

    # Optional command fallback; may fail without tools/permissions.
    for dev in sorted(glob.glob("/dev/nvme*n1")):
        try:
            out = subprocess.check_output(["nvme", "smart-log", dev], text=True, timeout=0.8, stderr=subprocess.DEVNULL)
        except Exception:
            out = ""
        m = re.search(r"temperature\s*:\s*([+-]?\d+(?:\.\d+)?)", out, re.I)
        if m:
            values.append(SensorValue(name=os.path.basename(dev), value=float(m.group(1))))
    return _dedupe(values)


def _dedupe(values: List[SensorValue]) -> List[SensorValue]:
    out: List[SensorValue] = []
    seen: Dict[str, int] = {}
    for v in values:
        name = v.name.strip()
        if name in seen:
            seen[name] += 1
            name = f"{name} #{seen[name]}"
        else:
            seen[name] = 1
        out.append(SensorValue(name=name, value=v.value))
    return out


def average(values: List[SensorValue]) -> Optional[float]:
    nums = [v.value for v in values if v.value is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)
