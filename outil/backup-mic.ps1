# Enregistrement de secours, indépendant de l'outil : le micro seul, en Matroska + FLAC (un fichier
# coupé en cours d'écriture reste lisible). Sur haut-parleurs, le micro entend aussi les autres.
# S'arrête avec le fichier STOP du dossier de la réunion, ou Ctrl+C.
# Usage : pwsh -File backup-mic.ps1 -Out "<dossier de la réunion>" -Mic "<nom dshow exact>"
# Le nom exact du micro se lit avec : ffmpeg -hide_banner -list_devices true -f dshow -i dummy
param(
    [Parameter(Mandatory = $true)][string]$Out,
    [Parameter(Mandatory = $true)][string]$Mic
)
$ErrorActionPreference = "Stop"
$dir = Join-Path $Out "secours"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$n = 1
while (Test-Path (Join-Path $dir "micro-secours-$n.mka")) { $n++ }
$f = Join-Path $dir "micro-secours-$n.mka"
$host.UI.RawUI.WindowTitle = "Secours micro : $(Split-Path $Out -Leaf)"
Write-Host "Secours (micro seul) : $f"
# Clusters of 1 s, flushed at once: when the recorder is stopped hard, at most a second is lost.
$argList = @('-hide_banner', '-nostdin', '-y', '-f', 'dshow', '-i', "audio=`"$Mic`"", '-ac', '1', '-ar', '16000', '-c:a', 'flac',
    '-flush_packets', '1', '-cluster_time_limit', '1000', "`"$f`"")
$p = Start-Process ffmpeg -ArgumentList $argList -NoNewWindow -PassThru -RedirectStandardError "$f.log"
try {
    while (-not $p.HasExited) {
        if (Test-Path (Join-Path $Out "STOP")) { Write-Host "STOP trouvé : arrêt du secours"; Stop-Process -Id $p.Id; break }
        Start-Sleep -Seconds 2
    }
} finally {
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -ErrorAction SilentlyContinue }
    $size = if (Test-Path $f) { [math]::Round((Get-Item $f).Length / 1MB, 1) } else { 0 }
    Write-Host "Secours terminé : $f ($size Mo)"
}
