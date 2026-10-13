@echo off
rem Held-out room comparisons: set up (first time), reconstruct, then analyse with the frozen
rem settings (heldout\FREEZE.json). Needs the room videos in data\room_clips\
rem (unzip room_videos.zip from the release into data\). Log: logs\run_all.log
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_all_windows.ps1 -Height 1.20 -Pairs "room_A=data\room_clips\before_A,data\room_clips\after_A;room_B=data\room_clips\before_B,data\room_clips\after_B;room_cross=data\room_clips\before_A,data\room_clips\after_B;room_null=data\room_clips\before_A,data\room_clips\before_B"
set RC=%errorlevel%
echo.
if %RC% neq 0 (echo FAILED, see logs\run_all.log) else (echo Finished. Results are in results\room_*)
pause
exit /b %RC%
