# Aplica atualização do Network Monitor fora do processo principal.
# Baixa o setup, encerra o app (força após timeout) e inicia o instalador.
param(
    [Parameter(Mandatory = $true)][string]$Url,
    [Parameter(Mandatory = $true)][string]$OutFile,
    [Parameter(Mandatory = $true)][int]$AppPid,
    [int]$TimeoutSec = 10,
    [string]$ProcessName = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Log([string]$Message) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$stamp] $Message"
}

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $dir = Split-Path -Parent $OutFile
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    Write-Log "Baixando instalador..."
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
    if (-not (Test-Path $OutFile) -or ((Get-Item $OutFile).Length -lt 1024)) {
        throw "Download incompleto: $OutFile"
    }
    Write-Log "Download concluído: $OutFile"
}
catch {
    Write-Log "Falha no download: $_"
    exit 1
}

function Stop-AppProcess([int]$TargetPid, [string]$Name, [int]$WaitSec) {
    $proc = Get-Process -Id $TargetPid -ErrorAction SilentlyContinue
    if (-not $proc) {
        Write-Log "Processo $TargetPid já encerrado."
        return
    }

    Write-Log "Solicitando encerramento do PID $TargetPid..."
    try {
        $null = $proc.CloseMainWindow()
    }
    catch {
        # processo sem janela principal
    }

    try {
        Wait-Process -Id $TargetPid -Timeout $WaitSec -ErrorAction Stop
        Write-Log "Processo encerrou graciosamente."
        return
    }
    catch {
        Write-Log "Timeout de ${WaitSec}s — forçando encerramento..."
    }

    Stop-Process -Id $TargetPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1

    if ($Name) {
        Get-Process -Name $Name -ErrorAction SilentlyContinue |
            Where-Object { $_.Id -ne $PID } |
            ForEach-Object {
                Write-Log "Encerrando processo residual $($_.Name) ($($_.Id))"
                Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            }
    }

    Start-Sleep -Seconds 1
}

Stop-AppProcess -TargetPid $AppPid -Name $ProcessName -WaitSec $TimeoutSec

Write-Log "Iniciando instalador..."
try {
    Start-Process -FilePath $OutFile
}
catch {
    Write-Log "Falha ao iniciar instalador: $_"
    exit 2
}

Write-Log "Instalador iniciado."
exit 0
