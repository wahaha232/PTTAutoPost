@echo off
REM ASCII only on purpose (cmd reads .bat with the OEM code page). All real work is in tools\make_portable.py.
cd /d "%~dp0"
python -X utf8 tools\make_portable.py %*
