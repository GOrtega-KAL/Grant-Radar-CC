# Recopilacion diaria.ps1
#
# Lanza la recopilacion `--no-claude` una vez al dia, sin llamar a Claude y
# sin coste. Es la pieza que convierte Grant-Radar en un radar que vigila, en
# vez de un script que alguien ejecuta: cada recopilacion publica
# `estado_recopilacion.json` y el panel avisa de cuantas convocatorias esperan
# analisis (AGENTS.md 49.5).
#
# NO analiza ni publica `convocatorias.json`. Eso sigue siendo una decision
# manual y de pago, como debe ser.
#
# Por que no llama a "poetry":
#
#   1. En una tarea programada el PATH no es el de tu sesion interactiva, y
#      "poetry" puede sencillamente no encontrarse;
#   2. este equipo tiene una variable VIRTUAL_ENV heredada que apunta al .venv
#      de la carpeta ORIGINAL, no al de esta copia; con ella presente, poetry
#      puede ejecutar en silencio contra el entorno equivocado (ver CLAUDE.md).
#
# Llamar directamente al interprete del entorno esquiva las dos cosas, y de
# paso hace la tarea inmune a que se reinstale o mueva poetry.
#
# Registro: ver la seccion "Como programarla" al final de este archivo.

$ErrorActionPreference = "Stop"

# La raiz del proyecto es la carpeta que contiene a "scripts".
$Raiz = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Raiz ".venv\Scripts\python.exe"
$Script = Join-Path $Raiz "Grant-Radar-prueba.py"
$DirLogs = Join-Path $Raiz "grant_radar_data\logs"

# Se limpia por si acaso: aunque no usemos poetry, un VIRTUAL_ENV heredado
# puede confundir a cualquier herramienta que el pipeline invoque despues.
$env:VIRTUAL_ENV = $null

if (-not (Test-Path $Python)) {
    Write-Error "No se encuentra el interprete del entorno: $Python. Ejecuta 'poetry install' en $Raiz."
    exit 1
}
if (-not (Test-Path $Script)) {
    Write-Error "No se encuentra $Script."
    exit 1
}
if (-not (Test-Path $DirLogs)) {
    New-Item -ItemType Directory -Path $DirLogs -Force | Out-Null
}

$Marca = Get-Date -Format "yyyy-MM-dd_HHmm"
$Log = Join-Path $DirLogs "recopilacion_$Marca.log"

Set-Location $Raiz
"=== Grant-Radar - recopilacion diaria - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" |
    Out-File -FilePath $Log -Encoding utf8

# La salida completa va al log. Tarda unos 10-15 minutos.
& $Python $Script --no-claude *>> $Log
$Codigo = $LASTEXITCODE

"=== fin, codigo $Codigo - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" |
    Out-File -FilePath $Log -Append -Encoding utf8

# Se conservan los ultimos 30 registros: uno al dia, un mes de historial.
# El historial que de verdad importa no esta aqui sino en la auditoria
# (grant_radar_data/grant_radar_audit.json), que es lo que lee
# --staleness-report; estos logs son solo para diagnosticar una tarea fallida.
Get-ChildItem -Path $DirLogs -Filter "recopilacion_*.log" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 30 |
    Remove-Item -Force -ErrorAction SilentlyContinue

if ($Codigo -ne 0) {
    Write-Error "La recopilacion termino con codigo $Codigo. Revisa $Log"
    exit $Codigo
}

Write-Output "Recopilacion completada. Registro: $Log"


<#
COMO PROGRAMARLA (una sola vez, en PowerShell como tu usuario)

    $accion = New-ScheduledTaskAction -Execute "powershell.exe" `
      -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\guillermo.ortega\Desktop\Guillermo\Grant-Radar - Claude Code\scripts\Recopilacion diaria.ps1"'
    $disparador = New-ScheduledTaskTrigger -Daily -At 7:00am
    $ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
      -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    Register-ScheduledTask -TaskName "Grant-Radar diario" -Action $accion `
      -Trigger $disparador -Settings $ajustes -Description "Recopilacion sin coste; no llama a Claude"

`-StartWhenAvailable` importa: si el equipo esta apagado a las 7:00, la tarea
se ejecuta en cuanto arranque, en vez de saltarse el dia.

COMPROBAR QUE ESTA VIVA

    Get-ScheduledTask -TaskName "Grant-Radar diario"
    Get-ScheduledTaskInfo -TaskName "Grant-Radar diario"   # ultima ejecucion y resultado

PROBARLA SIN ESPERAR AL DIA SIGUIENTE

    Start-ScheduledTask -TaskName "Grant-Radar diario"

RETIRARLA

    Unregister-ScheduledTask -TaskName "Grant-Radar diario" -Confirm:$false

QUE MIRAR DESPUES, SIN COSTE Y SIN RED

    .\.venv\Scripts\python.exe "Grant-Radar-prueba.py" --staleness-report

UN AVISO SOBRE LAS FUENTES PUBLICAS

Cada recopilacion consulta siete fuentes durante unos 10-15 minutos. Una al dia
esta muy por debajo de lo que provoco el HTTP 429 de boe.es el 19/08/2026 (ocho
en un dia), pero conviene no encadenar ejecuciones manuales el mismo dia que
corra la programada.
#>
