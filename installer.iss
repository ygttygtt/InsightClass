; Inno Setup 安装程序配置
; 用于打包 InsightClass Web 桌面应用

[Setup]
AppName=InsightClass 深见课堂
AppVersion=1.0.0
AppPublisher=InsightClass Team
AppPublisherURL=https://gitee.com/ygttygtt/InsightClass
DefaultDirName={autopf}\InsightClass
DefaultGroupName=InsightClass
OutputDir=installer_output
OutputBaseFilename=InsightClass-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; Uncomment to add an icon:
; SetupIconFile=assets\icon.ico
; UninstallDisplayIcon={app}\InsightClass.exe

[Files]
; PyInstaller onedir 输出的整个文件夹
Source: "dist\InsightClass\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"

[Icons]
; 开始菜单快捷方式
Name: "{group}\InsightClass 深见课堂"; Filename: "{app}\InsightClass.exe"
Name: "{group}\卸载 InsightClass"; Filename: "{uninstallexe}"
; 桌面快捷方式
Name: "{commondesktop}\InsightClass 深见课堂"; Filename: "{app}\InsightClass.exe"; Tasks: desktopicon

[Run]
; 安装完成后可选启动
Filename: "{app}\InsightClass.exe"; Description: "启动 InsightClass"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\configs\ssl"
Type: filesandordirs; Name: "{app}\experiments"
Type: filesandordirs; Name: "{app}\configs\cameras.yaml"
Type: filesandordirs; Name: "{app}\configs\app.yaml"
