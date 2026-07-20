$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Staging = Join-Path $Root 'staging'
$AppStage = Join-Path $Staging 'app'
$PrereqStage = Join-Path $Staging 'prerequisites'
$Runtime = Join-Path $AppStage 'runtime'
$Tools = Join-Path $Root 'build_tools'
$Downloads = Join-Path $Root 'build_downloads'
$Logs = Join-Path $Root 'build_logs'
$BuildTemp = Join-Path $Root 'build_temp'
$BuildAssets = Join-Path $Root 'build_assets'
$Log = Join-Path $Logs 'build.log'
$Dist = Join-Path $Root 'dist'
$PythonVersion = '3.11.9'

New-Item -ItemType Directory -Force -Path $Staging,$AppStage,$PrereqStage,$Tools,$Downloads,$Logs,$BuildTemp,$BuildAssets,$Dist | Out-Null
"`n===== FaceFinder installer build $(Get-Date -Format s) =====" | Out-File $Log -Append -Encoding utf8

function Step([string]$Text) {
    Write-Host "`n[FaceFinder Builder] $Text" -ForegroundColor Cyan
    "[FaceFinder Builder] $Text" | Out-File $Log -Append -Encoding utf8
}

function Test-BuildFile([string]$Path,[long]$MinimumBytes = 1,[switch]$RequireZip,[switch]$RequireExe) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    try {
        $Info = Get-Item -LiteralPath $Path
        if ($Info.Length -lt $MinimumBytes) { return $false }

        if ($RequireExe) {
            $Stream = [System.IO.File]::OpenRead($Path)
            try {
                if ($Stream.ReadByte() -ne 0x4D -or $Stream.ReadByte() -ne 0x5A) { return $false }
            } finally { $Stream.Dispose() }
        }

        if ($RequireZip) {
            Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue
            $Archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
            try {
                if ($Archive.Entries.Count -eq 0) { return $false }
            } finally { $Archive.Dispose() }
        }
        return $true
    } catch {
        return $false
    }
}

function Download(
    [string[]]$Urls,
    [string]$Destination,
    [long]$MinimumBytes = 1,
    [switch]$RequireZip,
    [switch]$RequireExe
) {
    $FileName = Split-Path -Leaf $Destination
    $OfflineAsset = Join-Path $BuildAssets $FileName

    # Prefer a manually supplied offline asset. This makes future builds
    # independent of external release URLs.
    if (Test-BuildFile $OfflineAsset $MinimumBytes -RequireZip:$RequireZip -RequireExe:$RequireExe) {
        Write-Host "Using offline build asset $FileName" -ForegroundColor Green
        Copy-Item -LiteralPath $OfflineAsset -Destination $Destination -Force
        return
    }

    if (Test-BuildFile $Destination $MinimumBytes -RequireZip:$RequireZip -RequireExe:$RequireExe) {
        Write-Host "Using cached $FileName" -ForegroundColor DarkGray
        return
    }

    Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
    Step "Downloading $FileName"

    $Errors = @()
    foreach ($Url in $Urls) {
        for ($attempt=1; $attempt -le 3; $attempt++) {
            $Partial = "$Destination.partial"
            Remove-Item -LiteralPath $Partial -Force -ErrorAction SilentlyContinue
            try {
                Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Partial
                if (-not (Test-BuildFile $Partial $MinimumBytes -RequireZip:$RequireZip -RequireExe:$RequireExe)) {
                    throw "Downloaded file failed validation."
                }
                Move-Item -LiteralPath $Partial -Destination $Destination -Force
                return
            } catch {
                Remove-Item -LiteralPath $Partial -Force -ErrorAction SilentlyContinue
                $Message = "URL $Url, attempt ${attempt}: $($_.Exception.Message)"
                $Errors += $Message
                $Message | Out-File $Log -Append -Encoding utf8
                Start-Sleep -Seconds (2 * $attempt)
            }
        }
    }

    $ErrorText = $Errors -join "`n"
    throw @"
Unable to obtain required build file: $FileName

External links may have changed or the network may be unavailable.
Download the correct file manually and place it here:
$OfflineAsset

Then rerun BUILD_INSTALLER.bat.

Download attempts:
$ErrorText
"@
}

function RunNative([string]$Exe,[string[]]$Arguments,[switch]$AllowFailure) {
    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & $Exe @Arguments 2>&1
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $old }
    foreach ($line in @($output)) {
        if ($null -ne $line) {
            $text = $line.ToString()
            Write-Host $text
            $text | Out-File $Log -Append -Encoding utf8
        }
    }
    if (($code -ne 0) -and (-not $AllowFailure)) {
        throw "Command failed with exit code ${code}: $Exe $($Arguments -join ' ')"
    }
    return [int]$code
}

function Copy-AppSources {
    Step 'Copying FaceFinder application source into installer staging'
    $exclude = @(
        'staging','dist','build_tools','build_downloads','build_logs','build_temp','build_assets','runtime',
        'BUILD_INSTALLER.bat','build_installer.ps1','FaceFinder.iss'
    )
    Get-ChildItem -LiteralPath $Root -Force | Where-Object { $exclude -notcontains $_.Name } | ForEach-Object {
        $destination = Join-Path $AppStage $_.Name
        if ($_.PSIsContainer) {
            Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
        } else {
            Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
        }
    }
}

try {
    Step 'Cleaning previous staging output'
    Remove-Item -LiteralPath $Staging -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $Dist -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $BuildTemp -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $AppStage,$PrereqStage,$BuildTemp,$Dist | Out-Null
    Copy-AppSources

    $PythonZip = Join-Path $Downloads "python-$PythonVersion-embed-amd64.zip"
    Download @("https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip") $PythonZip 5MB -RequireZip
    Step "Extracting private Python $PythonVersion runtime"
    Expand-Archive -LiteralPath $PythonZip -DestinationPath $Runtime -Force
    $Pth = Get-ChildItem $Runtime -Filter 'python*._pth' | Select-Object -First 1
    if (-not $Pth) { throw 'Embedded Python path file was not found.' }
    @('python311.zip','.','..','Lib','Lib\site-packages','import site') | Set-Content $Pth.FullName -Encoding ascii
    New-Item -ItemType Directory -Force -Path (Join-Path $Runtime 'Lib\site-packages') | Out-Null

    $GetPip = Join-Path $Downloads 'get-pip.py'
    Download @('https://bootstrap.pypa.io/get-pip.py') $GetPip 100KB
    $Python = Join-Path $Runtime 'python.exe'
    Step 'Installing pip into the private runtime'
    RunNative $Python @($GetPip,'--no-warn-script-location') | Out-Null
    RunNative $Python @('-m','pip','install','--upgrade','pip','setuptools','wheel','--no-warn-script-location') | Out-Null

    Step 'Installing UI and face-processing dependencies'
    $packages = @(
        'numpy==1.26.4','opencv-python-headless==4.10.0.84','Pillow==10.4.0',
        'onnx==1.17.0','scipy==1.14.1','scikit-image==0.24.0','requests==2.32.3',
        'tqdm==4.67.1','PySide6-Essentials==6.8.2.1','psutil==6.1.1',
        'nvidia-ml-py==12.560.30'
    )
    RunNative $Python (@('-m','pip','install','--only-binary=:all:','--no-warn-script-location') + $packages) | Out-Null
    RunNative $Python @('-m','pip','install','insightface==1.0.1','--no-deps','--no-warn-script-location') | Out-Null

    Step 'Installing offline CUDA 12 / cuDNN 9 runtime inside the application'
    $gpuPackages = @(
        'onnxruntime-gpu==1.20.1',
        'nvidia-cuda-runtime-cu12==12.4.127',
        'nvidia-cuda-nvrtc-cu12==12.4.127',
        'nvidia-cublas-cu12==12.4.5.8',
        'nvidia-cudnn-cu12==9.1.0.70',
        'nvidia-cufft-cu12==11.2.6.59',
        'nvidia-curand-cu12==10.3.10.19',
        'nvidia-nvjitlink-cu12==12.4.127'
    )
    RunNative $Python (@('-m','pip','install','--only-binary=:all:','--no-cache-dir','--no-warn-script-location') + $gpuPackages) | Out-Null
    'gpu-first' | Set-Content (Join-Path $Runtime 'runtime_mode.txt') -Encoding ascii

    $VcRedist = Join-Path $PrereqStage 'vc_redist.x64.exe'
    Download @('https://aka.ms/vs/17/release/vc_redist.x64.exe') $VcRedist 10MB -RequireExe

    Step 'Installing VC++ runtime on the build PC for validation'
    RunNative $VcRedist @('/install','/quiet','/norestart') -AllowFailure | Out-Null

    $ModelZip = Join-Path $Downloads 'buffalo_l.zip'
    Download @(
        'https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip',
        'https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip?download=1'
    ) $ModelZip 100MB -RequireZip

    $ModelsDir = Join-Path $AppStage 'data\insightface\models'
    $ModelTarget = Join-Path $ModelsDir 'buffalo_l'
    $ModelExtract = Join-Path $BuildTemp 'buffalo_l_extract'

    Step 'Bundling the Buffalo-L model for offline first launch'
    Remove-Item -LiteralPath $ModelExtract -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ModelTarget -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $ModelExtract | Out-Null
    New-Item -ItemType Directory -Force -Path $ModelTarget | Out-Null
    Expand-Archive -LiteralPath $ModelZip -DestinationPath $ModelExtract -Force

    # The release archive layout can vary. Locate the required model files
    # recursively rather than assuming the ZIP creates a buffalo_l folder.
    $DetectionModel = Get-ChildItem -LiteralPath $ModelExtract -Recurse -File -Filter 'det_10g.onnx' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $RecognitionModel = Get-ChildItem -LiteralPath $ModelExtract -Recurse -File -Filter 'w600k_r50.onnx' -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if (-not $DetectionModel -or -not $RecognitionModel) {
        $FoundOnnx = Get-ChildItem -LiteralPath $ModelExtract -Recurse -File -Filter '*.onnx' -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty FullName
        $FoundText = if ($FoundOnnx) { $FoundOnnx -join "`n  " } else { '(none)' }
        throw "Buffalo-L archive extracted, but required model files were not found.`nONNX files found:`n  $FoundText"
    }

    # The official Buffalo-L files live together. Copy every model from that
    # directory so detection, recognition, landmarks and age/gender are offline.
    $SourceModelDir = $RecognitionModel.Directory.FullName
    Copy-Item -Path (Join-Path $SourceModelDir '*') -Destination $ModelTarget -Recurse -Force

    $RequiredModels = @(
        'det_10g.onnx',
        'w600k_r50.onnx'
    )
    foreach ($RequiredModel in $RequiredModels) {
        $RequiredPath = Join-Path $ModelTarget $RequiredModel
        if (-not (Test-Path -LiteralPath $RequiredPath -PathType Leaf)) {
            throw "Missing required Buffalo-L model after extraction: $RequiredModel"
        }
    }

    $BundledCount = @(Get-ChildItem -LiteralPath $ModelTarget -File -Filter '*.onnx').Count
    Write-Host "Bundled $BundledCount Buffalo-L ONNX model file(s) into $ModelTarget" -ForegroundColor Green

    Step 'Compiling the Windows FaceFinder launcher EXE'
    $Csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    if (-not (Test-Path $Csc)) { throw 'Microsoft C# compiler was not found.' }
    RunNative $Csc @('/nologo','/target:winexe',"/out:$AppStage\FaceFinder.exe",'/reference:System.Windows.Forms.dll',(Join-Path $Root 'FaceFinderLauncher.cs')) | Out-Null

    Step 'Validating Python imports and CUDA dependency discovery'
    $env:FACEFINDER_INSTALL_DIR = $AppStage
    $env:FACEFINDER_DATA_DIR = (Join-Path $AppStage 'test_data')
    $env:FACEFINDER_MODEL_DIR = (Join-Path $AppStage 'data\insightface')
    $validationCode = RunNative $Python @(Join-Path $AppStage 'portable_check.py') -AllowFailure
    if ($validationCode -ne 0) {
        throw 'CUDA validation failed. The installer will not be produced with a broken GPU runtime. Review runtime_status.json and build_logs\build.log.'
    }
    Remove-Item Env:FACEFINDER_INSTALL_DIR,Env:FACEFINDER_DATA_DIR,Env:FACEFINDER_MODEL_DIR -ErrorAction SilentlyContinue

    $InnoInstaller = Join-Path $Downloads 'innosetup-6.7.3.exe'

    # The old jrsoftware download.php endpoint may return an HTML/error page that
    # gets cached with an .exe extension. Use the immutable official GitHub
    # release asset and validate the PE header before executing it.
    $InnoUrl = 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe'
    $InnoValid = $false
    if (Test-Path -LiteralPath $InnoInstaller -PathType Leaf) {
        try {
            $InnoInfo = Get-Item -LiteralPath $InnoInstaller
            $InnoBytes = [System.IO.File]::ReadAllBytes($InnoInstaller)
            $InnoValid = ($InnoInfo.Length -gt 5MB -and $InnoBytes.Length -ge 2 -and $InnoBytes[0] -eq 0x4D -and $InnoBytes[1] -eq 0x5A)
        } catch {
            $InnoValid = $false
        }
        if (-not $InnoValid) {
            Write-Host 'Removing invalid cached Inno Setup installer.' -ForegroundColor Yellow
            Remove-Item -LiteralPath $InnoInstaller -Force -ErrorAction SilentlyContinue
        }
    }

    Download @($InnoUrl) $InnoInstaller 5MB -RequireExe

    # Validate again after download so a proxy/AV-generated HTML response is
    # rejected before PowerShell attempts to execute it.
    $InnoInfo = Get-Item -LiteralPath $InnoInstaller
    $InnoStream = [System.IO.File]::OpenRead($InnoInstaller)
    try {
        $Byte0 = $InnoStream.ReadByte()
        $Byte1 = $InnoStream.ReadByte()
    } finally {
        $InnoStream.Dispose()
    }
    if ($InnoInfo.Length -le 5MB -or $Byte0 -ne 0x4D -or $Byte1 -ne 0x5A) {
        Remove-Item -LiteralPath $InnoInstaller -Force -ErrorAction SilentlyContinue
        throw 'The downloaded Inno Setup installer is invalid or incomplete. Its cache was removed; rerun BUILD_INSTALLER.bat.'
    }

    $InnoDir = Join-Path $Tools 'InnoSetup'
    $ISCC = Join-Path $InnoDir 'ISCC.exe'

    if (-not (Test-Path -LiteralPath $ISCC -PathType Leaf)) {
        Step 'Installing the Inno Setup compiler locally'
        Remove-Item -LiteralPath $InnoDir -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force -Path $InnoDir | Out-Null

        # Pass each argument directly. Do not embed quote characters in the
        # /DIR value; PowerShell already preserves paths containing spaces.
        $InnoArgs = @(
            '/VERYSILENT',
            '/SUPPRESSMSGBOXES',
            '/NORESTART',
            '/SP-',
            '/CURRENTUSER',
            ("/DIR=$InnoDir")
        )
        RunNative $InnoInstaller $InnoArgs | Out-Null

        # Build a broad candidate list. Some installer versions or enterprise
        # policies ignore /DIR and install to a registered per-user/system path.
        $ISCCCandidates = New-Object System.Collections.Generic.List[string]
        $CandidatePaths = @(
            (Join-Path $InnoDir 'ISCC.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
            (Join-Path $env:LOCALAPPDATA 'Inno Setup 6\ISCC.exe'),
            (Join-Path $env:APPDATA 'Inno Setup 6\ISCC.exe'),
            $(if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' }),
            $(if ($env:ProgramFiles) { Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe' })
        ) | Where-Object { $_ }

        foreach ($Candidate in $CandidatePaths) {
            if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
                $ISCCCandidates.Add([string]$Candidate)
            }
        }

        # Check PATH/App Paths.
        $PathCommand = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
        if ($PathCommand -and $PathCommand.Source -and (Test-Path -LiteralPath $PathCommand.Source -PathType Leaf)) {
            $ISCCCandidates.Add([string]$PathCommand.Source)
        }

        # Check Inno Setup uninstall registry entries for InstallLocation.
        $RegistryRoots = @(
            'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
        )
        foreach ($RegistryRoot in $RegistryRoots) {
            Get-ItemProperty $RegistryRoot -ErrorAction SilentlyContinue |
                Where-Object { $_.DisplayName -like 'Inno Setup*' -and $_.InstallLocation } |
                ForEach-Object {
                    $RegisteredISCC = Join-Path ([string]$_.InstallLocation) 'ISCC.exe'
                    if (Test-Path -LiteralPath $RegisteredISCC -PathType Leaf) {
                        $ISCCCandidates.Add([string]$RegisteredISCC)
                    }
                }
        }

        # Last-resort bounded search of likely roots only.
        if ($ISCCCandidates.Count -eq 0) {
            $SearchRoots = @(
                $InnoDir,
                (Join-Path $env:LOCALAPPDATA 'Programs'),
                $env:LOCALAPPDATA,
                ${env:ProgramFiles(x86)},
                $env:ProgramFiles
            ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Container) } |
                Select-Object -Unique

            foreach ($SearchRoot in $SearchRoots) {
                $FoundISCC = Get-ChildItem -LiteralPath $SearchRoot -Filter 'ISCC.exe' -File -Recurse -ErrorAction SilentlyContinue |
                    Where-Object { $_.FullName -match 'Inno Setup' } |
                    Select-Object -First 1
                if ($FoundISCC) {
                    $ISCCCandidates.Add([string]$FoundISCC.FullName)
                    break
                }
            }
        }

        $ISCC = $ISCCCandidates | Select-Object -Unique | Select-Object -First 1
        if (-not $ISCC) {
            throw @"
Inno Setup installer completed, but ISCC.exe was not found.

Install Inno Setup manually, or place ISCC.exe here:
$InnoDir\ISCC.exe

Then rerun BUILD_INSTALLER.bat. Existing staging/download caches will still be reused where possible.
"@
        }

        Write-Host "Using Inno Setup compiler: $ISCC" -ForegroundColor DarkGray
    }

    Step 'Compiling the single offline installer EXE'
    RunNative $ISCC @((Join-Path $Root 'FaceFinder.iss')) | Out-Null

    $Installer = Join-Path $Dist 'FaceFinder_Setup_Windows_x64.exe'
    if (-not (Test-Path $Installer)) { throw 'Installer EXE was not produced.' }
    $hash = (Get-FileHash $Installer -Algorithm SHA256).Hash
    "SHA256 $hash  FaceFinder_Setup_Windows_x64.exe" | Set-Content (Join-Path $Dist 'SHA256.txt') -Encoding ascii
    Step "Build complete: $Installer"
    Write-Host "SHA256: $hash" -ForegroundColor Green
    exit 0
} catch {
    $message = $_ | Out-String
    $message | Out-File $Log -Append -Encoding utf8
    Write-Host "`nInstaller build failed:`n$message" -ForegroundColor Red
    exit 1
}
