; Inno Setup script for kai. Build from the repository root after PyInstaller:
;   iscc /DAppVersion=0.1.0 packaging\windows\kai.iss
; Installs for the current user only (no administrator rights needed).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E4B0F57-3C1A-4D53-9B7E-6A1C2F0D8B41}
AppName=kai
AppVersion={#AppVersion}
AppVerName=kai {#AppVersion}
AppPublisher=ccmai
AppPublisherURL=https://ccmai.org/kai/
AppSupportURL=https://ccmai.org/kai/
DefaultDirName={localappdata}\Programs\kai
DefaultGroupName=kai
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=kai-{#AppVersion}-setup
SetupIconFile=..\..\build\icons\kai.ico
UninstallDisplayIcon={app}\kai.exe
UninstallDisplayName=kai
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start kai when I sign in to Windows"; Flags: unchecked

[Files]
Source: "..\..\dist\kai\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; an update replaces the whole program folder, so no stale files are left behind
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\kai"; Filename: "{app}\kai.exe"
Name: "{autodesktop}\kai"; Filename: "{app}\kai.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "kai"; ValueData: """{app}\kai.exe"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\kai.exe"; Description: "Start kai"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im kai.exe"; Flags: runhidden; RunOnceId: "StopKai"
