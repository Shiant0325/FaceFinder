from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from utils import ensure_dir, is_image_path, read_json, slugify, write_json


class PersonStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = ensure_dir(data_dir)
        self.persons_dir = ensure_dir(self.data_dir / "persons")

    def list_people(self) -> List[Dict]:
        people: List[Dict] = []
        for profile_path in sorted(self.persons_dir.glob("*/profile.json")):
            profile = read_json(profile_path, {})
            if profile:
                profile["profile_dir"] = str(profile_path.parent)
                profile["embedding_ready"] = (profile_path.parent / "embedding.npy").exists()
                profile["reference_count"] = len(self.reference_images(profile_path.parent.name))
                people.append(profile)
        return people

    def create_person(self, display_name: str) -> Dict:
        display_name = display_name.strip()
        if not display_name:
            raise ValueError("Person name is required.")

        base_slug = slugify(display_name)
        slug = base_slug
        counter = 2
        while (self.persons_dir / slug).exists():
            slug = f"{base_slug}_{counter}"
            counter += 1

        person_dir = ensure_dir(self.persons_dir / slug)
        ensure_dir(person_dir / "reference_images")
        profile = {
            "id": slug,
            "name": display_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        write_json(person_dir / "profile.json", profile)
        return profile

    def delete_person(self, person_id: str) -> None:
        shutil.rmtree(self.persons_dir / person_id, ignore_errors=True)

    def get_person(self, person_id: str) -> Dict:
        profile = read_json(self.persons_dir / person_id / "profile.json", {})
        if not profile:
            raise FileNotFoundError(f"Person profile not found: {person_id}")
        profile["profile_dir"] = str(self.persons_dir / person_id)
        profile["embedding_path"] = str(self.embedding_path(person_id))
        return profile

    def reference_dir(self, person_id: str) -> Path:
        return ensure_dir(self.persons_dir / person_id / "reference_images")

    def embedding_path(self, person_id: str) -> Path:
        return self.persons_dir / person_id / "embedding.npy"

    def reference_images(self, person_id: str) -> List[Path]:
        ref_dir = self.reference_dir(person_id)
        return sorted([p for p in ref_dir.iterdir() if p.is_file() and is_image_path(p)])

    def add_reference_images(self, person_id: str, source_paths: List[str]) -> List[Path]:
        destination_dir = self.reference_dir(person_id)
        copied: List[Path] = []
        for source_value in source_paths:
            source = Path(source_value)
            if not source.exists() or not source.is_file() or not is_image_path(source):
                continue
            destination = destination_dir / source.name
            index = 2
            while destination.exists():
                destination = destination_dir / f"{source.stem}_{index}{source.suffix}"
                index += 1
            shutil.copy2(source, destination)
            copied.append(destination)
        self._touch_profile(person_id)
        return copied

    def remove_reference_image(self, person_id: str, image_path: str | Path) -> None:
        path = Path(image_path)
        reference_dir = self.reference_dir(person_id).resolve()
        try:
            if path.resolve().parent == reference_dir:
                path.unlink(missing_ok=True)
        except OSError:
            pass
        self._touch_profile(person_id)

    def _touch_profile(self, person_id: str) -> None:
        path = self.persons_dir / person_id / "profile.json"
        profile = read_json(path, {})
        if profile:
            profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
            write_json(path, profile)
