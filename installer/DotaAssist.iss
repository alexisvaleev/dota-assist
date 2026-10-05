; Dota Assist — Inno Setup installer script
; Build:  iscc installer\DotaAssist.iss   (after scripts\build.py)
; Output: installer\Output\DotaAssist-Setup.exe

#define AppName "Dota Assist"
#define AppVersion "0.1.0"
#define AppExe "DotaAssist.exe"

[Setup]
AppId={{B7E2A1C4-9D3F-4E8A-A6B1-2F5C8D9E0A1B}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=Output
OutputBaseFilename=DotaAssist-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Ярлык на рабочем столе"; GroupDescription: "Дополнительно:"
Name: "installgsi"; Description: "Установить GSI-конфиг в папку Dota 2 (найденную автоматически)"; GroupDescription: "Интеграция:"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\gsi\gamestate_integration_dotaassist.cfg"; DestDir: "{app}\gsi"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
; editable copies next to exe — override the bundled ones (see app/paths.py)
Source: "..\app\calibration.json"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "..\data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.pyc"
Source: "..\config.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Code]
var
  DotaCfgDir: string;

function FindDotaCfgDir(): string;
var
  SteamPath, DotaPath: string;
begin
  Result := '';
  if not RegQueryStringValue(HKLM,
      'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath', SteamPath) then
    RegQueryStringValue(HKCU, 'SOFTWARE\Valve\Steam', 'SteamPath', SteamPath);
  if SteamPath = '' then exit;

  DotaPath := SteamPath + '\steamapps\common\dota 2 beta';
  if not DirExists(DotaPath) then exit;

  Result := DotaPath + '\game\dota\cfg\gamestate_integration';
end;

function InitializeSetup(): Boolean;
begin
  DotaCfgDir := FindDotaCfgDir();
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DstDir, Src, Dst: string;
begin
  if CurStep = ssPostInstall then begin
    if WizardIsTaskSelected('installgsi') then begin
      if DotaCfgDir <> '' then begin
        DstDir := DotaCfgDir;
        ForceDirectories(DstDir);
        Src := ExpandConstant('{app}\gsi\gamestate_integration_dotaassist.cfg');
        Dst := DstDir + '\gamestate_integration_dotaassist.cfg';
        if FileCopy(Src, Dst, False) then
          MsgBox('GSI-конфиг установлен в:' + #13#10 + Dst + #13#10#13#10 +
                 'Не забудь добавить -gamestateintegration в параметры запуска Dota.',
                 mbInformation, MB_OK)
        else
          MsgBox('Не удалось скопировать GSI-конфиг.', mbError, MB_OK);
      end else
        MsgBox('Dota 2 не найдена автоматически.' + #13#10 +
               'Скопируй gamestate_integration_dotaassist.cfg из папки ' +
               'установки\gsi в <dota>\game\dota\cfg\gamestate_integration\',
               mbInformation, MB_OK);
    end;
  end;
end;
