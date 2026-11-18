#Requires -Version 5.1
<#
.SYNOPSIS
Sign the Prism release installer with an Authenticode certificate.

The certificate must be issued by a trusted CA (OV/EV code signing, Azure
Trusted Signing, etc.) or imported as a PFX. A self-signed certificate only
avoids warnings on machines that explicitly trust it.

.EXAMPLE
.\scripts\sign-release.ps1 -Thumbprint 0123456789ABCDEF...

.EXAMPLE
.\scripts\sign-release.ps1 -PfxPath .\prism-code-signing.pfx
# You will be prompted for the PFX password.
#>
[CmdletBinding(DefaultParameterSetName = 'Thumbprint')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Thumbprint')]
    [string]$Thumbprint,

    [Parameter(Mandatory, ParameterSetName = 'Pfx')]
    [string]$PfxPath,

    [Parameter(ParameterSetName = 'Pfx')]
    [securestring]$PfxPassword,

    [string]$TimestampUrl = 'http://timestamp.digicert.com',

    [string[]]$Files = @()
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$signTool = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin' -Filter 'signtool.exe' -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '\\x64\\' } |
    Sort-Object FullName -Descending |
    Select-Object -First 1

if (-not $signTool) {
    throw 'signtool.exe was not found. Install the Windows SDK signing tools.'
}

if (-not $Files -or $Files.Count -eq 0) {
    $Files = @(Get-ChildItem (Join-Path $root 'installer') -Filter '*.exe' | ForEach-Object { $_.FullName })
}
if ($Files.Count -eq 0) {
    throw 'No executable release files were found to sign.'
}

$signArgs = @('sign', '/fd', 'SHA256', '/tr', $TimestampUrl, '/td', 'SHA256')
if ($PSCmdlet.ParameterSetName -eq 'Pfx') {
    if (-not $PfxPassword) {
        $PfxPassword = Read-Host -AsSecureString 'PFX password'
    }
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($PfxPassword)
    )
    $signArgs += @('/f', (Resolve-Path $PfxPath).Path, '/p', $plain)
} else {
    $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Thumbprint -eq $Thumbprint.Replace(' ', '') } |
        Select-Object -First 1
    if (-not $cert) {
        $cert = Get-ChildItem Cert:\LocalMachine\My -CodeSigningCert |
            Where-Object { $_.Thumbprint -eq $Thumbprint.Replace(' ', '') } |
            Select-Object -First 1
    }
    if (-not $cert) {
        throw "No code-signing certificate with thumbprint $Thumbprint was found."
    }
    $signArgs += @('/sha1', $cert.Thumbprint)
}

foreach ($file in $Files) {
    if (-not (Test-Path $file)) { throw "File not found: $file" }
    Write-Host "Signing $file" -ForegroundColor Cyan
    & $signTool.FullName @signArgs $file
    if ($LASTEXITCODE -ne 0) {
        throw "signtool failed for $file (exit $LASTEXITCODE)."
    }
    & $signTool.FullName verify /pa /all $file
    if ($LASTEXITCODE -ne 0) {
        throw "Signature verification failed for $file."
    }
    Write-Host "Signed and verified: $file" -ForegroundColor Green
}

Write-Host ''
Write-Host 'ZIP archives cannot carry an Authenticode signature. Sign the installer'
Write-Host 'and the executable launchers inside a portable payload before zipping it.'
Write-Host 'Recompute SHA-256 checksums after signing.'
