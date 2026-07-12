Set-Location "$PSScriptRoot\backend"
& ".venv\Scripts\uvicorn.exe" main:app --reload --port 8080
