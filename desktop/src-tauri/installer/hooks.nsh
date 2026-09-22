!define SZTU_CLEANUP_EXE "${__FILEDIR__}\..\target\installer\stop-runtime.exe"
!macro SztuStopRuntime
  InitPluginsDir
  File /oname=$PLUGINSDIR\sztu-stop-runtime.exe "${SZTU_CLEANUP_EXE}"
  DetailPrint "Stopping SztuCode background processes..."
  ExecWait '"$PLUGINSDIR\sztu-stop-runtime.exe" "$INSTDIR\."' $0
  ${If} $0 != 0
    Abort "Unable to stop SztuCode background processes. Close SztuCode or run this installer as administrator, then retry."
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro SztuStopRuntime
!macroend
!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro SztuStopRuntime
!macroend
