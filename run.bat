@echo off
setlocal
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Create it using: py -3.12 -m venv .venv
  exit /b 1
)
.venv\Scripts\python.exe app.py
