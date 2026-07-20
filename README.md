# FaceFinder

FaceFinder is a free, non-commercial, all-in-one Windows desktop application that privately scans folders and drives, detects and matches faces, and collects photos of the same person into one organized location. Face processing is performed locally on the user’s device, with CPU support and optional NVIDIA GPU acceleration.

> **Important:** FaceFinder is intended only for images you own or are legally authorized to process. Do not use it for surveillance, stalking, identification without consent, or any unlawful purpose.

## Features

- Create multiple named reference-person profiles
- Add and remove reference photos
- Generate averaged face embeddings for improved matching
- Scan multiple local folders or drives
- Detect the same person across large image collections
- Organize matching images into numbered finding folders
- Review matches as Confirmed, False Match, or Unreviewed
- Open the original image or reveal its source folder
- Copy or move selected originals
- Optionally save detected face crops
- Preserve source-folder structure when organizing results
- Prevent filename overwrites and destination collisions
- Pause, resume, or safely stop active scans
- Monitor CPU, RAM, GPU, VRAM, temperature, and active provider
- Use CPU-only, GPU-only, or automatic processing modes
- Operate without uploading personal photographs to a cloud service

## Local-first privacy

FaceFinder performs face detection and matching locally on the device.

The normal application workflow does not upload reference photos, scanned images, face crops, embeddings, findings, or scan databases to a remote server. The application does not contain advertising, analytics, user tracking, account registration, or telemetry submission.

Data created locally may include:

- Reference-person names entered by the user
- Reference photographs
- Numerical face embeddings
- Paths to scanned files and folders
- Face-match similarity scores
- Face bounding-box coordinates
- Image hashes
- Cropped face previews
- SQLite databases
- CSV result files
- JSON scan metadata
- Application settings and diagnostic logs

Anyone with access to the device, installation directory, user profile, backups, or exported findings may be able to access this information. Protect the device and output folders appropriately.

## Internet access

The installed offline edition is designed to include its application runtime, dependencies, and face models.

The **installer builder**, however, uses internet access while creating the offline installer to download official packages such as:

- Embedded Python
- Python dependencies
- ONNX Runtime
- NVIDIA CUDA and cuDNN runtime packages
- Microsoft Visual C++ Redistributable
- InsightFace Buffalo-L model files
- Inno Setup

These downloads are part of the build process and are not uploads of the user’s photographs or face data.

## Processing modes

### Automatic

Attempts to use NVIDIA CUDA acceleration first. If CUDA cannot be initialized, FaceFinder may fall back to CPU processing and reports the actual provider in use.

### GPU only

Requires the loaded InsightFace model sessions to run through `CUDAExecutionProvider`. The engine test fails rather than silently claiming GPU operation when models are actually using the CPU.

### CPU only

Uses `CPUExecutionProvider` exclusively and works without an NVIDIA GPU.

## Requirements

### Installed application

- Windows 10 or Windows 11
- 64-bit x86 processor
- Sufficient free storage for the application, models, and findings
- Optional compatible NVIDIA GPU and driver for CUDA acceleration

### Building the offline installer

- Windows 10 or Windows 11 x64
- PowerShell
- Administrator access for prerequisite validation
- Internet connection during the build
- Several gigabytes of free storage
- Patience during final installer compression

## Source layout

```text
FaceFinder/
├── app.py
├── ui.py
├── workers.py
├── face_engine.py
├── person_store.py
├── storage.py
├── file_organizer.py
├── settings_store.py
├── device_monitor.py
├── portable_check.py
├── portable_paths.py
├── setup_cpu.ps1
├── setup_gpu.ps1
├── build_installer.ps1
├── BUILD_INSTALLER.bat
├── FaceFinder.iss
├── FaceFinderLauncher.cs
├── requirements-portable-core.txt
└── README.md
```

## Build the offline Windows installer

Extract the source to a short writable path, for example:

```text
D:\FaceFinderBuilder
```

Then run:

```text
BUILD_INSTALLER.bat
```

The completed installer is generated under:

```text
dist\FaceFinder_Setup_Windows_x64.exe
```

The builder packages the private Python runtime, required libraries, the InsightFace model pack, CPU/GPU support, and the Microsoft Visual C++ prerequisite into the Windows installer.

## Application data

Depending on the edition and installation settings, writable data is stored either under the application directory or the user’s local application-data directory.

Typical local data includes:

```text
data/
├── persons/
├── insightface/
└── settings.json

Findings/
├── Finding 1/
│   ├── matches/
│   ├── results.sqlite
│   ├── results.csv
│   └── scan_info.json
└── Finding 2/
```

Before sharing diagnostic archives, screenshots, databases, CSV files, JSON files, or logs, inspect them for:

- Personal names
- Full local file paths
- User-account folder names
- Reference photos
- Face crops
- Original image locations
- Scan history

## Security and privacy recommendations

- Use FaceFinder only on images you are authorized to process.
- Store reference photos, embeddings, and findings on an encrypted drive.
- Restrict access to the Windows user account running FaceFinder.
- Delete old findings and reference profiles when no longer needed.
- Do not publish `data/`, `Findings/`, logs, generated databases, or runtime status files.
- Review copied or moved files before sharing them.
- Keep the repository free of real reference photos and generated biometric data.
- Verify release installers with a published SHA-256 checksum.
- Code-sign public Windows installers when possible.

## Repository exclusions

Do not commit generated or sensitive content:

```gitignore
runtime/
staging/
build_temp/
build_logs/
downloads/
tools/
dist/

data/
Findings/
logs/

*.onnx
*.dll
*.exe
*.msi
*.sqlite
*.db
runtime_status.json

__pycache__/
*.py[cod]
.env
.venv/
venv/
```

Model files, NVIDIA runtime files, Microsoft redistributables, and other third-party binaries remain subject to their own licenses and redistribution terms.

## Responsible use

Face recognition can involve biometric and personal data. Laws differ by country and region. The user is responsible for obtaining required consent, maintaining a lawful basis for processing, protecting stored data, honoring deletion requests where applicable, and complying with relevant privacy, biometric-data, employment, surveillance, and data-protection laws.

FaceFinder should not be used to make automated legal, employment, financial, medical, policing, or other high-impact decisions.

## License

FaceFinder is intended to remain free for non-commercial use.

You may use, study, modify, and redistribute the original FaceFinder code for non-commercial purposes under the terms included in the repository’s `LICENSE` file.

Commercial sale, paid distribution, paid access, or incorporation into a commercial product or service is not permitted without prior written permission from the copyright owner.

Third-party libraries, runtimes, and pretrained models are governed by their own licenses. The FaceFinder license does not replace or override those terms.

A suitable license for this intended use is the **PolyForm Noncommercial License 1.0.0**. Add the complete official license text as a separate `LICENSE` file before publishing.

## Disclaimer

Face matching is probabilistic and may produce false positives or false negatives. Always review matches manually before copying, moving, deleting, reporting, or relying on any result.

This software is provided without warranties. Users are responsible for lawful use, data protection, backups, model licensing, dependency licensing, and verification of results.
