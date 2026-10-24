; MathOCR Windows installer by Bouronikos Christos <chrisbouronikos@gmail.com>.
; Support development: https://paypal.me/christosbouronikos

#define MyAppName "MathOCR"
#define MyAppVersion "1.0.6"
#define MyAppPublisher "Bouronikos Christos"
#define MyAppURL "https://paypal.me/christosbouronikos"
#define MyAppExeName "MathOCR.exe"

[Setup]
AppId={{CC0597D0-412E-49C8-BC45-7AE2C4CA02DD}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL=mailto:chrisbouronikos@gmail.com
; Default to per-user installation without requiring UAC administrator elevation.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Resolve every relative path below from the repository root (this .iss lives in
; packaging\windows\), so LicenseFile, [Files] Source, and OutputDir all work
; regardless of the compiler's working directory.
SourceDir={#SourcePath}..\..
LicenseFile=LICENSE
OutputDir=dist
OutputBaseFilename=MathOCR-Setup
SetupIconFile=packaging\MathOCR.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
CloseApplicationsFilter=*{#MyAppExeName}

[Files]
Source: "dist\MathOCR\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; WorkingDir: "{app}"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
