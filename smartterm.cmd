@echo off
rem SmartTerm: uso  smartterm.cmd "D:\pasta\do\projeto" [--model-path C:\modelos\modelo.gguf]
"%~dp0.venv\Scripts\python.exe" "%~dp0smartterm.py" %*
