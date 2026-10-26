param([string]$Model = 'D:\GitHub\Strata-data\models\Ornith-122b\Ornith-1.5-122B-UD-Q2_K_XL.gguf',
      [string]$ModelName = 'ornith-1.5-122b-q2k-xl',
      [int]$Port = 8080,
      [int]$Context = 32768)
$env:PATH = 'D:\GitHub\Strata\.venv\Lib\site-packages\nvidia\cu13\bin\x86_64;D:\GitHub\Strata-data\llama.cpp-b11669;' + $env:PATH
& 'D:\GitHub\Strata-data\llama.cpp-b11669\llama-server.exe' `
    -m $Model --alias $ModelName `
    --host 127.0.0.1 --port $Port `
    --jinja --fit on `
    --ctx-size $Context `
    --cache-type-k q8_0 --cache-type-v q8_0 `
    --flash-attn on `
    --threads 14 --threads-batch 14 `
    --spec-type draft-mtp --spec-draft-n-max 2 --spec-draft-n-min 1 `
    --metrics
