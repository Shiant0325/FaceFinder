from __future__ import annotations

import subprocess
from typing import Dict


def _cpu_ram_metrics() -> Dict:
    try:
        import psutil

        memory = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_used_gb": (memory.total - memory.available) / (1024 ** 3),
            "ram_total_gb": memory.total / (1024 ** 3),
        }
    except Exception:
        return {"cpu_percent": None, "ram_used_gb": None, "ram_total_gb": None}


def _gpu_metrics_pynvml() -> Dict:
    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
        memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        try:
            temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        except Exception:
            temperature = None
        return {
            "gpu_available": True,
            "gpu_name": name,
            "gpu_percent": utilization.gpu,
            "vram_used_gb": memory.used / (1024 ** 3),
            "vram_total_gb": memory.total / (1024 ** 3),
            "gpu_temperature": temperature,
        }
    except Exception:
        return {}


def _gpu_metrics_nvidia_smi() -> Dict:
    try:
        command = [
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=2, check=True)
        line = result.stdout.strip().splitlines()[0]
        name, utilization, used, total, temperature = [part.strip() for part in line.split(",", 4)]
        return {
            "gpu_available": True,
            "gpu_name": name,
            "gpu_percent": float(utilization),
            "vram_used_gb": float(used) / 1024,
            "vram_total_gb": float(total) / 1024,
            "gpu_temperature": float(temperature),
        }
    except Exception:
        return {
            "gpu_available": False,
            "gpu_name": "Not detected",
            "gpu_percent": None,
            "vram_used_gb": None,
            "vram_total_gb": None,
            "gpu_temperature": None,
        }


def get_system_metrics() -> Dict:
    metrics = _cpu_ram_metrics()
    gpu = _gpu_metrics_pynvml() or _gpu_metrics_nvidia_smi()
    metrics.update(gpu)
    return metrics
