param(
    [string]$Model = 'gemma3:1b',
    [int]$TimeoutSeconds = 300
)
$ErrorActionPreference = 'Stop'
$base = 'http://localhost:11434'
Write-Host "Checking local Ollama: $base"
try { $tags = Invoke-RestMethod -Uri "$base/api/tags" -Method Get -TimeoutSec 10 }
catch { Write-Host "Ollama server is not reachable: $($_.Exception.Message)"; exit 1 }
$names = @($tags.models | ForEach-Object { $_.name })
Write-Host "Available models: $($names -join ', ')"
if ($Model -notin $names -and "$Model`:latest" -notin $names) {
    Write-Host "Model '$Model' not found in Ollama. Use an exact name from 'ollama list'."
    exit 2
}
Write-Host 'Loaded models:'
try { ollama ps } catch { Write-Host 'Could not query ollama ps' }
$payload = @{
    model = $Model
    stream = $false
    think = $false
    messages = @(@{role='system'; content='Answer ONLY a JSON object with a legal Rubiks cube move.'},
                 @{role='user'; content='Return exactly the JSON object {"move":"U"}.'})
    format = @{
        type = 'object'
        properties = @{move = @{type='string'; enum=@('U','R',"U'")}}
        required = @('move')
        additionalProperties = $false
    }
    options = @{num_predict = 64}
} | ConvertTo-Json -Depth 10
Write-Host "Requesting a single local response from $Model (limit ${TimeoutSeconds}s)..."
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
    $reply = Invoke-RestMethod -Uri "$base/api/chat" -Method Post -ContentType 'application/json' -Body $payload -TimeoutSec $TimeoutSeconds
    $sw.Stop()
    Write-Host "Elapsed: $([math]::Round($sw.Elapsed.TotalSeconds,2)) seconds"
    Write-Host "Response: $($reply.message.content)"
    Write-Host "Load duration (ns): $($reply.load_duration)"
    Write-Host "Evaluated tokens: $($reply.eval_count)"
} catch {
    $sw.Stop()
    Write-Host "Local request failed after $([math]::Round($sw.Elapsed.TotalSeconds,2)) seconds: $($_.Exception.Message)"
    exit 3
}
