; Inno Setup 6 script for the onedir portable folder.
; Build the portable folder first:
;   python -X utf8 tools/make_portable.py
;   python -X utf8 tools/make_portable.py --installer
; ISCC is passed /DMyAppVersion, /DMySourceDir and /DMyOutputDir by make_portable.py.

#define MyAppName "PTT AutoPost"
#define MyAppPublisher "PTT AutoPost authors"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef MySourceDir
  #define MySourceDir "..\dist\PTTAutoPost-0.0.0-portable"
#endif
#ifndef MyOutputDir
  #define MyOutputDir "..\dist\installer"
#endif

[Setup]
AppId={{8A7F2C41-6B3D-4E5A-9C2D-7F1B4A6E8D30}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\PTT AutoPost
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#MyOutputDir}
OutputBaseFilename=PTTAutoPost-{#MyAppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\PTTAutoPost.exe
LicenseFile={#MySourceDir}\LICENSE
InfoAfterFile={#MySourceDir}\THIRD_PARTY_NOTICES.md

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "config\*,logs\*,data\*"

[Dirs]
Name: "{app}\config"; Flags: uninsneveruninstall
Name: "{app}\logs"; Flags: uninsneveruninstall
Name: "{app}\data"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\PTTAutoPost.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\PTTAutoPost.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PTTAutoPost.exe"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
