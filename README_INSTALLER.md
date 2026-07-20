# Build the offline installer

On a Windows 10/11 x64 PC:

1. Extract this folder to a short writable path, for example `D:\FaceFinderBuilder`.
2. Right-click `BUILD_INSTALLER.bat` and choose **Run as administrator**.
3. Keep internet connected while building. The builder downloads official runtime packages once.
4. The resulting installer is fully offline:

```text
dist\FaceFinder_Setup_Windows_x64.exe
```

The final setup EXE bundles the application runtime, PySide6, InsightFace, ONNX Runtime GPU, pinned CUDA 12.4/cuDNN 9.1 libraries, Buffalo-L model, and the official VC++ x64 redistributable.
