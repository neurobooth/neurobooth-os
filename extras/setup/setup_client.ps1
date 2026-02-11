#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Configures a Windows client for PowerShell Remoting to remote servers
.DESCRIPTION
    This script sets up the client side configuration for PowerShell Remoting.
    Run this on the machine that will connect to remote servers.
.PARAMETER RemoteServers
    Comma-separated list of remote server names to trust (or * for all)
    Default: "*"
.PARAMETER TestConnection
    Test connection to a specific server after configuration
    Default: "" (skip test)
.PARAMETER TestUser
    Username for connection test (e.g., DOMAIN\username)
    Default: "" (prompt if TestConnection is specified)
.PARAMETER TestPassword
    Password for connection test (will be prompted securely if not provided)
    Default: "" (prompt if TestConnection is specified)
.EXAMPLE
    .\setup_client.ps1
    .\setup_client.ps1 -RemoteServers "SERVER1,SERVER2,SERVER3"
    .\setup_client.ps1 -RemoteServers "*" -TestConnection "SERVER1" -TestUser "DOMAIN\user"
#>

param(
    [Parameter(Mandatory=$false)]
    [string]$RemoteServers = "*",
    
    [Parameter(Mandatory=$false)]
    [string]$TestConnection = "",
    
    [Parameter(Mandatory=$false)]
    [string]$TestUser = "",
    
    [Parameter(Mandatory=$false)]
    [string]$TestPassword = ""
)

# Configuration variables
$TrustedHostsPath = "WSMan:\localhost\Client\TrustedHosts"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PowerShell Remoting Client Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration Parameters:" -ForegroundColor Cyan
Write-Host "  Remote Servers:     $RemoteServers" -ForegroundColor White
Write-Host "  Test Connection:    $(if ($TestConnection) { $TestConnection } else { '(disabled)' })" -ForegroundColor White
Write-Host ""

# Configure TrustedHosts
Write-Host "[1/2] Configuring TrustedHosts for remote servers..." -ForegroundColor Yellow
try {
    Set-Item $TrustedHostsPath -Value $RemoteServers -Force -ErrorAction Stop
    $trustedHosts = (Get-Item $TrustedHostsPath).Value
    Write-Host "  ✓ TrustedHosts set to: $trustedHosts" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed to set TrustedHosts: $_" -ForegroundColor Red
    exit 1
}

# Test connectivity if requested
Write-Host "[2/2] Testing configuration..." -ForegroundColor Yellow

if ($TestConnection) {
    Write-Host "  Testing connection to $TestConnection..." -ForegroundColor Yellow
    
    # Get credentials if not provided
    if (-not $TestUser) {
        $TestUser = Read-Host "  Enter username for $TestConnection (e.g., DOMAIN\user)"
    }
    
    if (-not $TestPassword) {
        $securePassword = Read-Host "  Enter password for $TestUser" -AsSecureString
    } else {
        $securePassword = ConvertTo-SecureString -String $TestPassword -AsPlainText -Force
    }
    
    $credential = New-Object System.Management.Automation.PSCredential ($TestUser, $securePassword)
    
    try {
        # Test WinRM connectivity
        Write-Host "    Testing WinRM connectivity..." -ForegroundColor Gray
        $testWsman = Test-WSMan -ComputerName $TestConnection -ErrorAction Stop
        Write-Host "    ✓ WinRM connectivity successful" -ForegroundColor Green
        
        # Test authenticated command
        Write-Host "    Testing authenticated command..." -ForegroundColor Gray
        $result = Invoke-Command -ComputerName $TestConnection -Credential $credential -ScriptBlock { 
            $env:COMPUTERNAME 
        } -ErrorAction Stop
        Write-Host "    ✓ Successfully connected to: $result" -ForegroundColor Green
        
        # Test process listing (what the Python script does)
        Write-Host "    Testing process enumeration..." -ForegroundColor Gray
        $processes = Invoke-Command -ComputerName $TestConnection -Credential $credential -ScriptBlock { 
            Get-Process | Select-Object -First 5 Name, Id
        } -ErrorAction Stop
        Write-Host "    ✓ Successfully retrieved process list ($($processes.Count) processes)" -ForegroundColor Green
        
        Write-Host "  ✓ All connection tests passed!" -ForegroundColor Green
        
    } catch {
        Write-Host "  ✗ Connection test failed: $_" -ForegroundColor Red
        Write-Host ""
        Write-Host "  Troubleshooting:" -ForegroundColor Yellow
        Write-Host "  1. Ensure the remote server has PowerShell Remoting enabled" -ForegroundColor White
        Write-Host "  2. Verify network connectivity: Test-NetConnection -ComputerName $TestConnection -Port 5985" -ForegroundColor White
        Write-Host "  3. Check that the user has appropriate permissions on the remote server" -ForegroundColor White
        Write-Host "  4. Verify firewall rules allow WinRM traffic" -ForegroundColor White
    }
} else {
    Write-Host "  ✓ Client configured successfully (connection test skipped)" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Configuration Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Computer Name:    " -NoNewline; Write-Host "$env:COMPUTERNAME" -ForegroundColor White
Write-Host "TrustedHosts:     " -NoNewline; Write-Host "$trustedHosts" -ForegroundColor White

Write-Host ""
Write-Host "Manual Connection Test:" -ForegroundColor Cyan
Write-Host @"
`$secpasswd = ConvertTo-SecureString -String 'password' -AsPlainText -Force
`$credential = New-Object System.Management.Automation.PSCredential ('DOMAIN\username', `$secpasswd)
Invoke-Command -ComputerName 'REMOTE-SERVER' -Credential `$credential -ScriptBlock { hostname }
"@ -ForegroundColor Gray

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green