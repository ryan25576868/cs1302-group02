#Requires -Version 5.1
<#
.SYNOPSIS
Create a LOCAL-ONLY self-signed code-signing certificate for testing.

This does NOT create a publicly trusted signature. Other machines will still
show "Unknown publisher" and SmartScreen warnings. Use a CA-issued certificate
for distribution.
#>
[CmdletBinding()]
param(
    [string]$Subject = 'CN=Prism Local Development, O=Prism',
    [int]$ValidYears = 2
)

$ErrorActionPreference = 'Stop'
$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $Subject `
    -KeyUsage DigitalSignature `
    -KeyAlgorithm RSA `
    -KeyLength 3072 `
    -HashAlgorithm SHA256 `
    -CertStoreLocation Cert:\CurrentUser\My `
    -NotAfter (Get-Date).AddYears($ValidYears) `
    -FriendlyName 'Prism local development signing'

$cerPath = Join-Path $PSScriptRoot 'Prism-Local-Development.cer'
Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null

# Trust only on this user account, only for local testing.
certutil -addstore -user Root $cerPath | Out-Null
certutil -addstore -user TrustedPublisher $cerPath | Out-Null

Write-Host ''
Write-Host 'LOCAL DEVELOPMENT CERTIFICATE CREATED' -ForegroundColor Yellow
Write-Host 'This certificate is trusted only by this Windows account.' -ForegroundColor Yellow
Write-Host 'It cannot remove SmartScreen warnings on other people''s machines.' -ForegroundColor Yellow
Write-Host ''
Write-Host "Certificate: $cerPath"
Write-Host "Thumbprint:  $($cert.Thumbprint)"
Write-Host ''
Write-Host "Sign the local installer with:"
Write-Host "  .\scripts\sign-release.ps1 -Thumbprint $($cert.Thumbprint)"
