; Inno Setup: installiert s7py pro Benutzer (ohne Administratorrechte).
; Aufruf aus dem Projektroot:
;   ISCC /DAppVersion=0.9.0 packaging\windows\installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{B1380519-65FA-4F95-8C9A-D6C27E02E07A}
AppName=s7py
AppVersion={#AppVersion}
AppVerName=s7py {#AppVersion}
AppPublisher=R@lle (R8lle)
AppCopyright=© 2026 R@lle (R8lle)
VersionInfoVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
VersionInfoProductName=s7py
VersionInfoProductTextVersion={#AppVersion}
VersionInfoDescription=s7py Setup – SPS lesen, SQLite speichern, Live-Diagramm
VersionInfoCompany=R@lle (R8lle)
VersionInfoCopyright=© 2026 R@lle (R8lle)
DefaultDirName={localappdata}\Programs\s7py
DefaultGroupName=s7py
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist\installer
OutputBaseFilename=s7py-{#AppVersion}-setup
SetupIconFile=..\build\s7py.ico
UninstallDisplayIcon={app}\s7py.exe
LicenseFile=..\..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\s7py\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\s7py"; Filename: "{app}\s7py.exe"
Name: "{group}\Schnellhilfe"; Filename: "{app}\_internal\s7py\help\kurzanleitung.md"
Name: "{group}\Bedienungsanleitung"; Filename: "{app}\_internal\s7py\help\anleitung.md"
Name: "{group}\{cm:UninstallProgram,s7py}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\s7py"; Filename: "{app}\s7py.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\s7py.exe"; Description: "{cm:LaunchProgram,s7py}"; Flags: nowait postinstall skipifsilent
