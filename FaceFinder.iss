#define MyAppName "FaceFinder"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "FaceFinder"
#define MyAppExeName "FaceFinder.exe"

[Setup]
AppId={{F42A16F2-692A-45A8-9A8E-C7B5E7CE9F2A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\FaceFinder
DefaultGroupName=FaceFinder
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=FaceFinder_Setup_Windows_x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousGroup=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "staging\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "staging\prerequisites\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

[Icons]
Name: "{group}\FaceFinder"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\FaceFinder Diagnostics"; Filename: "{app}\DEBUG_FACEFINDER.bat"; WorkingDir: "{app}"
Name: "{group}\Uninstall FaceFinder"; Filename: "{uninstallexe}"
Name: "{autodesktop}\FaceFinder"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Microsoft Visual C++ runtime..."; Flags: waituntilterminated runhidden
Filename: "{app}\{#MyAppExeName}"; Description: "Launch FaceFinder"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
end;
