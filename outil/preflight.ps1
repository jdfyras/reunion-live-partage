# Avant une réunion en mode A : mémoire, gros consommateurs, périphériques audio, Ollama.
# Usage : pwsh -File preflight.ps1
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$o = Get-CimInstance Win32_OperatingSystem
$free = [math]::Round($o.FreePhysicalMemory / 1MB, 1)
$commitFree = [math]::Round($o.FreeVirtualMemory / 1MB, 1)
Write-Host "== Mémoire : $free Go libres, $commitFree Go de marge d'engagement"
if ($free -ge 10 -and $commitFree -ge 12) { Write-Host "   OK pour le mode A (Cohere prend environ 7 Go)" }
elseif ($free -ge 8) { Write-Host "   Juste : ferme ce qui ne sert pas ce soir (onglets, autres sessions Claude Code, WSL)" }
else { Write-Host "   Trop peu : libère de la mémoire, ou mode B (micro seul, faster-whisper)" }
Write-Host "== Plus gros consommateurs (mémoire privée)"
Get-Process | Group-Object ProcessName | ForEach-Object {
    [pscustomobject]@{ Nom = $_.Name; Nb = $_.Count; Go = [math]::Round(($_.Group | Measure-Object PrivateMemorySize64 -Sum).Sum / 1GB, 1) }
} | Sort-Object Go -Descending | Select-Object -First 8 | Format-Table -AutoSize | Out-String | Write-Host
$ollama = Get-Process ollama* -ErrorAction SilentlyContinue
Write-Host ("== Ollama : " + $(if ($ollama) { "en marche, arrête-le pendant la réunion" } else { "arrêté" }))
$py = Get-Process python* -ErrorAction SilentlyContinue
Write-Host "== Processus Python : $(($py | Measure-Object).Count) (un téléchargement ou un ancien enregistrement peut tourner)"
Write-Host "== Périphériques audio"
& (Join-Path $PSScriptRoot ".venv\Scripts\python.exe") -X utf8 (Join-Path $PSScriptRoot "reunion_live.py") --list-devices
