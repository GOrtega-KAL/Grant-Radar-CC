# Comprobar credenciales antes de commit.ps1
#
# Bloquea un "git commit" si alguno de los archivos preparados (staged)
# contiene un patron que parece una clave real de Anthropic o un token de
# GitHub. Se usa como git hook "pre-commit" (ver .git/hooks/pre-commit),
# pero tambien se puede ejecutar a mano en cualquier momento para revisar
# el estado actual del "staging area" antes de confirmar un commit.
#
# Salida: codigo 0 si no encuentra nada sospechoso (commit permitido),
# codigo 1 si encuentra una posible clave real (commit bloqueado).

$ErrorActionPreference = "Stop"

# Patrones de claves reales que nunca deberian aparecer en un archivo versionado.
$patrones = @(
    "sk-ant-[A-Za-z0-9_-]{20,}",   # Clave de API de Anthropic (Claude)
    "ghp_[A-Za-z0-9]{20,}",        # Token clasico de acceso personal de GitHub
    "github_pat_[A-Za-z0-9_]{20,}" # Token de acceso personal "fine-grained" de GitHub
)

# Archivos que van a formar parte del proximo commit (staged en git).
$archivosPreparados = git diff --cached --name-only --diff-filter=ACM

$encontrado = $false

foreach ($archivo in $archivosPreparados) {
    if (-not (Test-Path $archivo)) { continue }

    # ".env" y "API KEYs.txt" son precisamente donde SI deben vivir las claves
    # reales, pero nunca deberian llegar a estar "staged": si ocurre, es un
    # aviso todavia mas urgente, no una excepcion a ignorar.
    $contenido = Get-Content -Path $archivo -Raw -ErrorAction SilentlyContinue
    if (-not $contenido) { continue }

    foreach ($patron in $patrones) {
        if ($contenido -match $patron) {
            Write-Host "BLOQUEADO: posible clave real detectada en '$archivo' (patron: $patron)" -ForegroundColor Red
            $encontrado = $true
        }
    }
}

if ($encontrado) {
    Write-Host ""
    Write-Host "Commit cancelado. Retira la clave real del archivo (usa .env, que ya esta en .gitignore) antes de continuar." -ForegroundColor Yellow
    exit 1
}

exit 0
