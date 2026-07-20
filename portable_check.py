from __future__ import annotations

import json
import os
import platform
import site
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DLL_HANDLES = []


def preload_nvidia_dlls() -> dict:
    discovered = []
    result = {"dll_directories": discovered, "preload_ok": False, "preload_error": None}
    try:
        for site_dir in site.getsitepackages():
            nvidia_root = Path(site_dir) / "nvidia"
            if not nvidia_root.exists():
                continue
            for bin_dir in sorted(nvidia_root.rglob("bin")):
                if not bin_dir.is_dir():
                    continue
                value = str(bin_dir.resolve())
                if value in discovered:
                    continue
                discovered.append(value)
                try:
                    DLL_HANDLES.append(os.add_dll_directory(value))
                except (AttributeError, OSError):
                    pass
                os.environ["PATH"] = value + os.pathsep + os.environ.get("PATH", "")

        import onnxruntime as ort
        if hasattr(ort, "preload_dlls"):
            try:
                ort.preload_dlls(cuda=True, cudnn=True, msvc=True, directory="")
            except TypeError:
                ort.preload_dlls(directory="")
        result["preload_ok"] = True
    except Exception as exc:
        result["preload_error"] = repr(exc)
    return result




def find_required_cuda_dlls() -> dict:
    required = {
        "cudart64_12.dll": False,
        "cublas64_12.dll": False,
        "cublasLt64_12.dll": False,
        "cudnn64_9.dll": False,
        "cufft64_11.dll": False,
        "curand64_10.dll": False,
    }
    found_paths = {}
    for site_dir in site.getsitepackages():
        nvidia_root = Path(site_dir) / "nvidia"
        if not nvidia_root.exists():
            continue
        for dll in nvidia_root.rglob("*.dll"):
            key = dll.name.lower()
            for required_name in list(required):
                if key == required_name.lower():
                    required[required_name] = True
                    found_paths[required_name] = str(dll.resolve())
    return {
        "required": required,
        "found_paths": found_paths,
        "missing": [name for name, present in required.items() if not present],
    }

status = {
    "python": sys.version,
    "platform": platform.platform(),
    "runtime": str(Path(sys.executable).resolve()),
    "imports": {},
    "gpu_dll_preload": preload_nvidia_dlls(),
    "cuda_dll_check": find_required_cuda_dlls(),
}

for name in ["PySide6", "numpy", "cv2", "PIL", "psutil", "onnx", "onnxruntime", "insightface", "scipy", "skimage"]:
    try:
        module = __import__(name)
        status["imports"][name] = {"ok": True, "version": getattr(module, "__version__", None)}
    except Exception as exc:
        status["imports"][name] = {"ok": False, "error": repr(exc)}

try:
    import numpy as np
    import onnx
    import onnxruntime as ort
    from onnx import TensorProto, helper

    status["onnxruntime_device"] = ort.get_device()
    status["providers"] = ort.get_available_providers()

    # Build and execute a tiny model. This confirms that CUDA can create and run
    # a real session; merely listing CUDAExecutionProvider is not sufficient.
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1])
    z = helper.make_tensor_value_info("z", TensorProto.FLOAT, [1])
    graph = helper.make_graph([helper.make_node("Add", ["x", "y"], ["z"])], "cuda_probe", [x, y], [z])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = min(model.ir_version, 10)

    requested = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    session = ort.InferenceSession(model.SerializeToString(), providers=requested)
    actual = session.get_providers()
    output = session.run(None, {"x": np.array([1.0], np.float32), "y": np.array([2.0], np.float32)})[0]
    status["cuda_probe"] = {
        "requested_providers": requested,
        "actual_providers": actual,
        "output": output.tolist(),
        "cuda_active": bool(actual and actual[0] == "CUDAExecutionProvider"),
    }
except Exception as exc:
    status["cuda_probe"] = {"cuda_active": False, "error": repr(exc)}

out = ROOT / "runtime_status.json"
out.write_text(json.dumps(status, indent=2), encoding="utf-8")
failed = [name for name, value in status["imports"].items() if not value["ok"]]
print(json.dumps(status, indent=2))
if failed:
    print("FAILED IMPORTS:", ", ".join(failed), file=sys.stderr)
    raise SystemExit(1)

missing_dlls = status["cuda_dll_check"]["missing"]
if missing_dlls:
    print("MISSING CUDA DLLS:", ", ".join(missing_dlls), file=sys.stderr)
    raise SystemExit(2)

if not status.get("cuda_probe", {}).get("cuda_active", False):
    print("CUDA PROBE FAILED: CUDAExecutionProvider did not become the active provider.", file=sys.stderr)
    raise SystemExit(3)
