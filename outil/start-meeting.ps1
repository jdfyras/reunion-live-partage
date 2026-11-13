# Lance l'enregistrement d'une réunion dans sa propre fenêtre, hors de Claude Code :
# une fenêtre à part ne peut pas être coupée quand Claude Code manque de mémoire.
# Usage (PowerShell 7) :
#   pwsh -File start-meeting.ps1 -Out "<dossier de la réunion>" -Title "Kickoff" -Me "<ton prénom>" -Remote "<les autres>" [-Mic "<micro>"] [-Speaker "<sortie>"] [-Headphones]
#   pwsh -File start-meeting.ps1 -Out "<dossier>" -Simulate "<fichier audio>" [-SimStart 600] [-SimDur 120]
param(
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$Title = "Réunion",
    [string]$Me = "Moi",
    [string]$Remote = "Participants",
    [string]$Mic = "",
    [string]$Speaker = "",
    [switch]$Headphones,
    [string]$Simulate = "",
    [double]$SimStart = 0,
    [double]$SimDur = 120
)
$ErrorActionPreference = "Stop"
# Python writes UTF-8; without this, PowerShell reads its output as CP850 and the accents break.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "reunion_live.py"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$a = @("-X", "utf8", $script, "--out", $Out, "--title", $Title, "--me", $Me, "--remote", $Remote)
if ($Mic) { $a += @("--mic", $Mic) }
if ($Speaker) { $a += @("--speaker", $Speaker) }
if ($Headphones) { $a += "--no-echo-gate" }
if ($Simulate) { $a += @("--simulate", $Simulate, "--sim-start", "$SimStart", "--sim-dur", "$SimDur") }
$host.UI.RawUI.WindowTitle = "Réunion en direct : $Title"
Write-Host "Enregistrement local : $Out"
Write-Host "Pour arrêter : crée le fichier STOP dans ce dossier, ou Ctrl+C ici."
& $py @a 2>&1 | Tee-Object -FilePath (Join-Path $Out "recorder.log")
Write-Host "Terminé. Tu peux fermer cette fenêtre."
