; Inno Setup 安装程序配置
; 用于打包 InsightClass Web 推理服务

[Setup]
AppName=InsightClass Web
AppVersion=0.1.0
AppPublisher=InsightClass Team
AppPublisherURL=https://gitee.com/ygttygtt/InsightClass
DefaultDirName={autopf}\InsightClass-Web
DefaultGroupName=InsightClass
OutputDir=installer_output
OutputBaseFilename=InsightClass-Web-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; Uncomment to add an icon:
; SetupIconFile=assets\icon.ico
; UninstallDisplayIcon={app}\InsightClass.exe

[Files]
; PyInstaller onedir 输出的整个文件夹
Source: "dist\InsightClass-Web\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Dirs]
; 运行时可写目录
Name: "{app}\configs\ssl"
Name: "{app}\experiments"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"

[Icons]
; 开始菜单快捷方式
Name: "{group}\启动 InsightClass 服务"; Filename: "{app}\InsightClass.exe"; Parameters: "serve --port 8000"
Name: "{group}\启动 InsightClass 服务 (HTTPS)"; Filename: "{app}\InsightClass.exe"; Parameters: "serve --port 8000 --https"
Name: "{group}\卸载 InsightClass"; Filename: "{uninstallexe}"
; 桌面快捷方式
Name: "{commondesktop}\InsightClass Web"; Filename: "{app}\InsightClass.exe"; Parameters: "serve --port 8000"; Tasks: desktopicon

[Run]
; 安装完成后可选启动
Filename: "{app}\InsightClass.exe"; Parameters: "serve --port 8000"; Description: "启动 InsightClass Web 服务"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\configs\ssl"
Type: filesandordirs; Name: "{app}\experiments"
Type: filesandordirs; Name: "{app}\configs\cameras.yaml"
Type: filesandordirs; Name: "{app}\configs\app.yaml"
