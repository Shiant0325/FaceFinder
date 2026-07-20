from __future__ import annotations

import json
import os
import site
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


_DLL_DIRECTORY_HANDLES = []
_REQUIRED_CUDA_DLLS = (
    "cudart64_12.dll",
    "cublas64_12.dll",
    "cublasLt64_12.dll",
    "cudnn64_9.dll",
    "cufft64_11.dll",
    "curand64_10.dll",
)

_GPU_PRELOAD_INFO: Dict[str, object] = {
    "dll_directories": [],
    "preload_ok": False,
    "preload_error": None,
}


def preload_gpu_dlls() -> Dict[str, object]:
    """Load CUDA 12/cuDNN DLLs installed inside the portable Python runtime.

    The handles returned by ``os.add_dll_directory`` are kept alive globally.
    Releasing those handles removes the directory from the DLL search path on
    Windows and can make ONNX Runtime silently fall back to CPU.
    """
    global _GPU_PRELOAD_INFO
    discovered: List[str] = []
    try:
        for site_dir in site.getsitepackages():
            nvidia_dir = Path(site_dir) / "nvidia"
            if not nvidia_dir.exists():
                continue

            for bin_dir in sorted(nvidia_dir.rglob("bin")):
                if not bin_dir.is_dir():
                    continue
                value = str(bin_dir.resolve())
                if value in discovered:
                    continue
                discovered.append(value)
                try:
                    handle = os.add_dll_directory(value)
                    _DLL_DIRECTORY_HANDLES.append(handle)
                except (AttributeError, OSError):
                    pass
                os.environ["PATH"] = value + os.pathsep + os.environ.get("PATH", "")

        import onnxruntime as ort

        if hasattr(ort, "preload_dlls"):
            try:
                ort.preload_dlls(cuda=True, cudnn=True, msvc=True, directory="")
            except TypeError:
                ort.preload_dlls(directory="")

        found_dlls = {}
        for directory in discovered:
            directory_path = Path(directory)
            for required_name in _REQUIRED_CUDA_DLLS:
                candidate = directory_path / required_name
                if candidate.is_file():
                    found_dlls[required_name] = str(candidate)
        missing_dlls = [name for name in _REQUIRED_CUDA_DLLS if name not in found_dlls]

        _GPU_PRELOAD_INFO = {
            "dll_directories": discovered,
            "preload_ok": not missing_dlls,
            "preload_error": None if not missing_dlls else f"Missing CUDA DLLs: {', '.join(missing_dlls)}",
            "required_dlls": list(_REQUIRED_CUDA_DLLS),
            "found_dlls": found_dlls,
            "missing_dlls": missing_dlls,
        }
    except Exception as exc:
        _GPU_PRELOAD_INFO = {
            "dll_directories": discovered,
            "preload_ok": False,
            "preload_error": repr(exc),
        }
        print(f"[ORT] GPU DLL preload warning: {exc}")
    return dict(_GPU_PRELOAD_INFO)


preload_gpu_dlls()

import cv2
import onnxruntime as ort
from PIL import Image, ImageFile, UnidentifiedImageError
from insightface.app import FaceAnalysis

from portable_paths import app_root, model_root
from utils import ensure_dir, iter_image_files, safe_filename, sha256_file

ImageFile.LOAD_TRUNCATED_IMAGES = True


def l2_normalize(value: np.ndarray) -> np.ndarray:
    value = np.asarray(value, dtype=np.float32)
    norm = np.linalg.norm(value)
    return value if norm == 0 else value / norm


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(l2_normalize(a), l2_normalize(b)))


class FaceEngine:
    def __init__(self, device_mode: str = "auto", det_size: Tuple[int, int] = (320, 320)):
        self.device_mode = device_mode.lower()
        self.det_size = det_size
        self.available_providers = ort.get_available_providers()
        self.fallback_reason: Optional[str] = None

        requested, ctx_id = self._resolve_providers()
        try:
            self._create_app(requested, ctx_id)
        except Exception as exc:
            if self.device_mode != "auto" or requested == ["CPUExecutionProvider"]:
                raise
            self.fallback_reason = f"GPU initialization failed; CPU fallback used: {exc}"
            self._create_app(["CPUExecutionProvider"], -1)

    def _create_app(self, providers: List[str], ctx_id: int) -> None:
        self.requested_providers = list(providers)
        root = model_root()
        # InsightFace downloads/loads buffalo_l under this portable data directory.
        self.app = FaceAnalysis(name="buffalo_l", root=str(root), providers=self.requested_providers)
        self.app.prepare(ctx_id=ctx_id, det_size=self.det_size)

        self.model_providers: Dict[str, List[str]] = {}
        for model_name, model in getattr(self.app, "models", {}).items():
            session = getattr(model, "session", None)
            if session is not None and hasattr(session, "get_providers"):
                self.model_providers[model_name] = list(session.get_providers())

        first_providers = [values[0] for values in self.model_providers.values() if values]
        self.actual_provider = (
            "CUDAExecutionProvider"
            if "CUDAExecutionProvider" in first_providers
            else first_providers[0] if first_providers else self.requested_providers[0]
        )

        # A listed CUDA provider is not enough; require the actual model sessions to use it.
        if self.device_mode == "gpu" and self.actual_provider != "CUDAExecutionProvider":
            details = json.dumps(self.model_providers, indent=2)
            raise RuntimeError(
                "GPU-only mode was selected, but InsightFace models are not running on CUDA.\n"
                f"ONNX Runtime providers: {self.available_providers}\n"
                f"Requested providers: {self.requested_providers}\n"
                f"Actual model providers: {details}\n"
                f"GPU DLL preload: {_GPU_PRELOAD_INFO}\n"
                "Close FaceFinder, run Repair portable GPU runtime, then restart the app."
            )

    def _resolve_providers(self) -> tuple[List[str], int]:
        cuda_available = "CUDAExecutionProvider" in self.available_providers
        if self.device_mode == "gpu":
            if not cuda_available:
                raise RuntimeError(
                    "GPU mode was selected, but CUDAExecutionProvider is unavailable. "
                    "Run REPAIR_GPU_RUNTIME.bat or select CPU/Automatic mode."
                )
            return ["CUDAExecutionProvider", "CPUExecutionProvider"], 0
        if self.device_mode == "cpu":
            return ["CPUExecutionProvider"], -1
        if cuda_available:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"], 0
        return ["CPUExecutionProvider"], -1

    @property
    def using_gpu(self) -> bool:
        return self.actual_provider == "CUDAExecutionProvider"

    def diagnostics(self) -> Dict:
        return {
            "onnx_device": ort.get_device(),
            "available_providers": self.available_providers,
            "requested_providers": self.requested_providers,
            "actual_provider": self.actual_provider,
            "model_providers": self.model_providers,
            "device_mode": self.device_mode,
            "det_size": list(self.det_size),
            "fallback_reason": self.fallback_reason,
            "gpu_dll_preload": dict(_GPU_PRELOAD_INFO),
            "portable_app_root": str(app_root()),
            "portable_model_root": str(model_root()),
        }

    def read_image(self, path: str | Path) -> Optional[np.ndarray]:
        path = Path(path)
        try:
            image = cv2.imread(str(path))
            if image is not None:
                return image
        except Exception as exc:
            print(f"[WARN] OpenCV read failed: {path} | {exc}")

        try:
            with Image.open(path) as pil_image:
                rgb = np.array(pil_image.convert("RGB"))
                return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            print(f"[SKIP] Bad/corrupt image: {path} | {exc}")
        except Exception as exc:
            print(f"[SKIP] Image read error: {path} | {exc}")
        return None

    def get_faces(self, image_bgr: np.ndarray):
        return self.app.get(image_bgr)

    def best_face_embedding(self, image_path: str | Path) -> Optional[np.ndarray]:
        image = self.read_image(image_path)
        if image is None:
            return None
        faces = self.get_faces(image)
        if not faces:
            return None
        largest = max(
            faces,
            key=lambda face: (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1]),
        )
        return l2_normalize(largest.embedding)

    def build_reference_embedding(self, reference_dir: str | Path, output_path: str | Path) -> int:
        embeddings: List[np.ndarray] = []
        for image_path in iter_image_files(reference_dir):
            embedding = self.best_face_embedding(image_path)
            if embedding is not None:
                embeddings.append(embedding)

        if not embeddings:
            raise RuntimeError("No usable face was detected in the selected reference images.")

        average = l2_normalize(np.mean(np.stack(embeddings), axis=0))
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(output_path, average)
        return len(embeddings)

    def load_reference(self, path: str | Path) -> np.ndarray:
        return l2_normalize(np.load(path))

    def crop_face(self, image_bgr: np.ndarray, bbox, output_path: str | Path) -> str:
        height, width = image_bgr.shape[:2]
        x1, y1, x2, y2 = [int(value) for value in bbox]
        pad_x = int((x2 - x1) * 0.20)
        pad_y = int((y2 - y1) * 0.20)
        x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
        x2, y2 = min(width, x2 + pad_x), min(height, y2 + pad_y)
        crop = image_bgr[y1:y2, x1:x2]
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if crop.size == 0 or not cv2.imwrite(str(output_path), crop):
            raise OSError(f"Could not save crop: {output_path}")
        return str(output_path)

    def scan_image(
        self,
        reference_embedding: np.ndarray,
        image_path: str | Path,
        threshold: float,
        matches_dir: str | Path,
        person_id: str,
        person_name: str,
        finding_name: str,
    ) -> List[Dict]:
        image_path = Path(image_path)
        image = self.read_image(image_path)
        if image is None:
            return []
        faces = self.get_faces(image)
        if not faces:
            return []

        rows: List[Dict] = []
        matches_dir = ensure_dir(matches_dir)
        image_hash: Optional[str] = None

        for index, face in enumerate(faces):
            similarity = cosine_similarity(reference_embedding, face.embedding)
            if similarity < threshold:
                continue

            if image_hash is None:
                image_hash = sha256_file(image_path)
            stem = safe_filename(image_path.stem)[:80]
            crop_name = f"{image_hash[:12]}_{stem}_face{index}_sim{similarity:.3f}.jpg"
            crop_path = matches_dir / crop_name
            self.crop_face(image, face.bbox, crop_path)
            rows.append(
                {
                    "person_id": person_id,
                    "person_name": person_name,
                    "finding_name": finding_name,
                    "original_image_path": str(image_path),
                    "image_path": str(image_path),
                    "crop_path": str(crop_path),
                    "similarity": similarity,
                    "threshold": threshold,
                    "face_bbox": json.dumps([float(value) for value in face.bbox]),
                    "image_hash": image_hash,
                    "review_status": "Unreviewed",
                }
            )
        return rows
