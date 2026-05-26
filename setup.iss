; Inno Setup script for Desktop Duck
; Download Inno Setup from https://jrsoftware.org/isinfo.php
; Open this file in Inno Setup Compiler and click Compile.

[Setup]
AppName=Desktop Duck
AppVersion=1.0
DefaultDirName={autopf}\DesktopDuck
DefaultGroupName=Desktop Duck
OutputDir=.\installer
OutputBaseFilename=DesktopDuck-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Files]
Source: "dist\DesktopDuck.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "downPic\*"; DestDir: "{app}\downPic"; Flags: ignoreversion recursesubdirs
Source: "Pic\*"; DestDir: "{app}\Pic"; Flags: ignoreversion recursesubdirs

[Dirs]
Name: "{app}\Audio"

[Icons]
Name: "{autoprograms}\Desktop Duck"; Filename: "{app}\DesktopDuck.exe"
Name: "{autodesktop}\Desktop Duck"; Filename: "{app}\DesktopDuck.exe"
Name: "{userstartup}\Desktop Duck"; Filename: "{app}\DesktopDuck.exe"; Parameters: "--autostart"

[Run]
Filename: "{app}\DesktopDuck.exe"; Description: "启动 Desktop Duck"; Flags: nowait postinstall skipifsilent
