$env:PYTHONUTF8 = '1'
python "$PSScriptRoot/dev.py" hooks
exit $LASTEXITCODE
