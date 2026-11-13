; Prism per-user installer.
; Compile from the project root:
;   makensis /DAPP_VERSION=1.0.0 desktop\installer.nsi
; Requires the portable payload at dist\portable-extract (see README).

!include "MUI2.nsh"
!include "FileFunc.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "1.0.0"
!endif

!ifndef PAYLOAD_DIR
  !define PAYLOAD_DIR "..\dist\portable-extract"
!endif

!ifndef OUT_FILE
  !define OUT_FILE "..\dist\Prism-Setup-1.0.0.exe"
!endif

!ifndef ICON_FILE
  !define ICON_FILE "..\assets\icon.ico"
!endif

!ifndef INSTALL_DIR
  !define INSTALL_DIR "$LOCALAPPDATA\Programs\Prism"
!endif

Unicode true
Name "Prism"
Caption "Prism ${APP_VERSION}"
OutFile "${OUT_FILE}"
InstallDir "${INSTALL_DIR}"
InstallDirRegKey HKCU "Software\Prism" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
BrandingText "Prism · visual code lab"
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName" "Prism"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "FileDescription" "Prism code visualizer installer"
VIAddVersionKey "CompanyName" "Prism"
Icon "${ICON_FILE}"
UninstallIcon "${ICON_FILE}"

!define MUI_ABORTWARNING
!define MUI_ICON "${ICON_FILE}"
!define MUI_FINISHPAGE_RUN "$INSTDIR\Prism.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch Prism"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Prism" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD_DIR}\*.*"

  ; Per-user integration.
  CreateShortCut "$DESKTOP\Prism.lnk" "$INSTDIR\Prism.exe" "" "$INSTDIR\Prism.exe" 0
  CreateDirectory "$SMPROGRAMS\Prism"
  CreateShortCut "$SMPROGRAMS\Prism\Prism.lnk" "$INSTDIR\Prism.exe" "" "$INSTDIR\Prism.exe" 0
  CreateShortCut "$SMPROGRAMS\Prism\Uninstall Prism.lnk" "$INSTDIR\Uninstall Prism.exe"

  WriteUninstaller "$INSTDIR\Uninstall Prism.exe"

  WriteRegStr HKCU "Software\Prism" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "DisplayName" "Prism"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "Publisher" "Prism"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "DisplayIcon" "$INSTDIR\Prism.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "UninstallString" '"$INSTDIR\Uninstall Prism.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "NoRepair" 1

  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism" "EstimatedSize" "$0"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\Prism.lnk"
  Delete "$SMPROGRAMS\Prism\Prism.lnk"
  Delete "$SMPROGRAMS\Prism\Uninstall Prism.lnk"
  RMDir "$SMPROGRAMS\Prism"

  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prism"
  DeleteRegKey HKCU "Software\Prism"

  ; Keep user data and settings on uninstall.
  RMDir /r "$INSTDIR"
SectionEnd
