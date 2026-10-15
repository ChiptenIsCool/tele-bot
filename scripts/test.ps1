$env:PYTHONUTF8 = '1'
python "$PSScriptRoot/dev.py" test @args
exit $LASTEXITCODE
