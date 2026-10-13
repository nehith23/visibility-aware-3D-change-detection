@echo off
rem Double-click to set up (first time) and run the corridor comparisons. Log: logs\run_all.log
rem Needs the corridor videos in data\corridor\ (unzip corridor_videos.zip from the release into data\).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_all_windows.ps1 %*
set RC=%errorlevel%
echo.
if %RC% neq 0 (echo FAILED, see logs\run_all.log) else (echo Finished. Results are in results\)
pause
exit /b %RC%
