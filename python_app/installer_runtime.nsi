Unicode true
!include "MUI2.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "1.1.0"
!endif
!ifndef PAYLOAD_DIR
  !define PAYLOAD_DIR "..\dist\PrismPy"
!endif
!ifndef OUT_FILE
  !define OUT_FILE "..\installer\Prism-Python-Setup-1.1.0.exe"
!endif

Name "Prism"
OutFile "${OUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\Prism"
InstallDirRegKey HKCU "Software\Prism" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "Prism · Python desktop workspace"

!define MUI_ABORTWARNING
!define MUI_ICON "${__FILEDIR__}\..\assets\icon.ico"
!define MUI_UNICON "${__FILEDIR__}\..\assets\icon.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

VIProductVersion "1.1.0.0"
VIAddVersionKey "ProductName" "Prism"
VIAddVersionKey "FileDescription" "Prism code analysis workspace"
VIAddVersionKey "FileVersion" "1.1.0"
VIAddVersionKey "ProductVersion" "1.1.0"
VIAddVersionKey "LegalCopyright" "Prism"

Section "Prism" SecMain
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD_DIR}\*.*"

  CreateDirectory "$SMPROGRAMS\Prism"
  CreateShortcut "$SMPROGRAMS\Prism\Prism.lnk" "$INSTDIR\runtime\pythonw.exe" '"$INSTDIR\python_app\desktop.py"' "$INSTDIR\assets\icon.ico" 0 SW_SHOWNORMAL "" "$INSTDIR"
  CreateShortcut "$SMPROGRAMS\Prism\Uninstall Prism.lnk" "$INSTDIR\Uninstall Prism.exe"
  CreateShortcut "$DESKTOP\Prism.lnk" "$INSTDIR\runtime\pythonw.exe" '"$INSTDIR\python_app\desktop.py"' "$INSTDIR\assets\icon.ico" 0 SW_SHOWNORMAL "" "$INSTDIR"

  WriteUninstaller "$INSTDIR\Uninstall Prism.exe"
  WriteRegStr HKCU "Software\Prism" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "DisplayName" "Prism"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "Publisher" "Prism"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "DisplayIcon" "$INSTDIR\assets\icon.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "UninstallString" '"$INSTDIR\Uninstall Prism.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\Prism.lnk"
  Delete "$SMPROGRAMS\Prism\Prism.lnk"
  Delete "$SMPROGRAMS\Prism\Uninstall Prism.lnk"
  RMDir "$SMPROGRAMS\Prism"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism"
  DeleteRegKey HKCU "Software\Prism"
SectionEnd
