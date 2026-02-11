#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Configures a Windows machine for PowerShell Remoting
.DESCRIPTION
    This script sets up PowerShell Remoting (WinRM) to allow remote management
    from client machines. Run this on each remote server that needs to be managed.
.PARAMETER ClientMachines
    Comma-separated list of client machine names to trust
    Default: "*" (trust all)
.PARAMETER RemoteUser
    Domain\Username that needs remote access (e.g., DOMAIN\STM)
    Will be added to Remote Management Users group if not already admin
    Default: "" (skip user configuration)
.PARAMETER WinRMPort
    Port for WinRM HTTP listener
    Default: 5985
.PARAMETER NetworkCategory
    Network category to set (Private, Public, DomainAuthenticated)
    Default: "Private"
.PARAMETER WinRMStartupType
    WinRM service startup type (Automatic, Manual)
    Default: "Automatic"
.EXAMPLE
    .\setup_remote_server.ps1
    .\setup_remote_server.ps1 -ClientMachines "CLIENT-PC1,CLIENT-PC2" -RemoteUser "PARTNERS\lw412"
    .\setup_remote_server.ps1 -ClientMachines "*" -RemoteUser "DOMAIN\user" -NetworkCategory "Private"
#>

param(
    [Parameter(Mandatory=$false)]
    [string]$ClientMachines = "*",

    [Parameter(Mandatory=$false)]
    [string]$RemoteUser = "",

    [Parameter(Mandatory=$false)]
    [int]$WinRMPort = 5985,

    [Parameter(Mandatory=$false)]
    [ValidateSet("Private", "Public", "DomainAuthenticated")]
    [string]$NetworkCategory = "Private",

    [Parameter(Mandatory=$false)]
    [ValidateSet("Automatic", "Manual")]
    [string]$WinRMStartupType = "Automatic"
)

# Configuration variables
$FirewallRuleName = "WINRM-HTTP-In-TCP*"
$AdminGroupName = "Administrators"
$RemoteManagementGroupName = "Remote Management Users"
$WinRMServiceName = "WinRM"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PowerShell Remoting Setup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration Parameters:" -ForegroundColor Cyan
Write-Host "  Client Machines:    $ClientMachines" -ForegroundColor White
Write-Host "  Remote User:        $(if ($RemoteUser) { $RemoteUser } else { '(not specified)' })" -ForegroundColor White
Write-Host "  WinRM Port:         $WinRMPort" -ForegroundColor White
Write-Host "  Network Category:   $NetworkCategory" -ForegroundColor White
Write-Host "  Startup Type:       $WinRMStartupType" -ForegroundColor White
Write-Host ""

# Step 1: Enable PowerShell Remoting
Write-Host "[1/7] Enabling PowerShell Remoting..." -ForegroundColor Yellow
try {
    Enable-PSRemoting -Force -ErrorAction Stop
    Write-Host "  [OK] PowerShell Remoting enabled successfully" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Failed to enable PowerShell Remoting: $_" -ForegroundColor Red
    exit 1
}

# Step 2: Configure TrustedHosts
Write-Host "[2/7] Configuring TrustedHosts ($ClientMachines)..." -ForegroundColor Yellow
try {
    Set-Item WSMan:\localhost\Client\TrustedHosts -Value $ClientMachines -Force -ErrorAction Stop
    $trustedHosts = (Get-Item WSMan:\localhost\Client\TrustedHosts).Value
    Write-Host "  [OK] TrustedHosts set to: $trustedHosts" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Failed to set TrustedHosts: $_" -ForegroundColor Red
    exit 1
}

# Step 3: Start and configure WinRM service
Write-Host "[3/7] Configuring $WinRMServiceName service..." -ForegroundColor Yellow
try {
    Set-Service $WinRMServiceName -StartupType $WinRMStartupType -ErrorAction Stop
    Restart-Service $WinRMServiceName -Force -ErrorAction Stop
    $winrmStatus = (Get-Service $WinRMServiceName).Status
    $winrmStartup = (Get-Service $WinRMServiceName).StartType
    Write-Host "  [OK] $WinRMServiceName service is $winrmStatus (Startup: $winrmStartup)" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Failed to configure $WinRMServiceName service: $_" -ForegroundColor Red
    exit 1
}

# Step 4: Configure firewall rules
Write-Host "[4/7] Configuring firewall rules..." -ForegroundColor Yellow
try {
    $firewallRules = Get-NetFirewallRule -Name $FirewallRuleName -ErrorAction SilentlyContinue
    if ($firewallRules) {
        Enable-NetFirewallRule -Name $FirewallRuleName -ErrorAction Stop
        Write-Host "  [OK] WinRM firewall rules enabled" -ForegroundColor Green

        # Display enabled rules
        foreach ($rule in $firewallRules) {
            if ($rule.Enabled) {
                Write-Host "    - $($rule.DisplayName): Enabled" -ForegroundColor Gray
            }
        }
    } else {
        Write-Host "  [WARNING] WinRM firewall rules not found (may have been created with different names)" -ForegroundColor Yellow
        Write-Host "    Expected rule pattern: $FirewallRuleName" -ForegroundColor Gray
    }
} catch {
    Write-Host "  [ERROR] Failed to configure firewall: $_" -ForegroundColor Red
}

# Step 5: Set network profile to specified category
Write-Host "[5/7] Checking network profile..." -ForegroundColor Yellow
try {
    $profiles = Get-NetConnectionProfile
    $needsChange = $profiles | Where-Object { $_.NetworkCategory -ne $NetworkCategory }

    if ($needsChange) {
        Write-Host "  [WARNING] Found network profiles not set to $NetworkCategory. Attempting to change..." -ForegroundColor Yellow
        foreach ($profile in $needsChange) {
            try {
                Set-NetConnectionProfile -InterfaceIndex $profile.InterfaceIndex -NetworkCategory $NetworkCategory -ErrorAction Stop
                Write-Host "    [OK] Changed $($profile.InterfaceAlias) from $($profile.NetworkCategory) to $NetworkCategory" -ForegroundColor Green
            } catch {
                Write-Host "    [ERROR] Could not change $($profile.InterfaceAlias): $_" -ForegroundColor Yellow
                Write-Host "      You may need to change this manually in Network Settings" -ForegroundColor Yellow
            }
        }
    } else {
        Write-Host "  [OK] All network profiles are already set to $NetworkCategory" -ForegroundColor Green
    }

    # Display current profiles
    $currentProfiles = Get-NetConnectionProfile
    foreach ($profile in $currentProfiles) {
        Write-Host "    - $($profile.InterfaceAlias): $($profile.NetworkCategory)" -ForegroundColor Gray
    }
} catch {
    Write-Host "  [WARNING] Could not check network profiles: $_" -ForegroundColor Yellow
}

# Step 6: Configure user permissions
if ($RemoteUser) {
    Write-Host "[6/7] Configuring permissions for $RemoteUser..." -ForegroundColor Yellow
    try {
        # Check if user is already in Administrators group
        $adminMembers = Get-LocalGroupMember -Group $AdminGroupName -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
        $isAdmin = $adminMembers -contains $RemoteUser

        if ($isAdmin) {
            Write-Host "  [OK] $RemoteUser is already in $AdminGroupName group" -ForegroundColor Green
        } else {
            # Try to add to Remote Management Users group
            try {
                Add-LocalGroupMember -Group $RemoteManagementGroupName -Member $RemoteUser -ErrorAction Stop
                Write-Host "  [OK] Added $RemoteUser to $RemoteManagementGroupName group" -ForegroundColor Green
            } catch {
                if ($_.Exception.Message -like "*already a member*") {
                    Write-Host "  [OK] $RemoteUser is already in $RemoteManagementGroupName group" -ForegroundColor Green
                } else {
                    Write-Host "  [ERROR] Failed to add user to $RemoteManagementGroupName" -ForegroundColor Red
                    Write-Host "    Error: $_" -ForegroundColor Red
                    Write-Host "    User may need to be added manually or be made a local administrator" -ForegroundColor Yellow
                }
            }
        }
    } catch {
        Write-Host "  [ERROR] Failed to configure user permissions: $_" -ForegroundColor Red
    }
} else {
    Write-Host "[6/7] Skipping user permissions (no RemoteUser specified)" -ForegroundColor Gray
}

# Step 7: Verify configuration
Write-Host "[7/7] Verifying configuration..." -ForegroundColor Yellow
try {
    # Check listener
    $listeners = Get-WSManInstance -ResourceURI winrm/config/listener -Enumerate -ErrorAction Stop
    $httpListener = $listeners | Where-Object { $_.Transport -eq "HTTP" }

    if ($httpListener) {
        $actualPort = $httpListener.Port
        Write-Host "  [OK] HTTP listener configured on port $actualPort" -ForegroundColor Green
        if ($actualPort -ne $WinRMPort) {
            Write-Host "    [WARNING] Note: Listener is on port $actualPort, not $WinRMPort as specified" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [ERROR] No HTTP listener found" -ForegroundColor Red
    }

    # Test local loopback
    $testResult = Test-WSMan -ComputerName localhost -ErrorAction Stop
    Write-Host "  [OK] Local WinRM test successful" -ForegroundColor Green

} catch {
    Write-Host "  [ERROR] Verification failed: $_" -ForegroundColor Red
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Configuration Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Computer Name:    " -NoNewline; Write-Host "$env:COMPUTERNAME" -ForegroundColor White
Write-Host "WinRM Status:     " -NoNewline; Write-Host "$(Get-Service $WinRMServiceName | Select-Object -ExpandProperty Status)" -ForegroundColor White
Write-Host "Startup Type:     " -NoNewline; Write-Host "$(Get-Service $WinRMServiceName | Select-Object -ExpandProperty StartType)" -ForegroundColor White
Write-Host "TrustedHosts:     " -NoNewline; Write-Host "$trustedHosts" -ForegroundColor White
Write-Host "Listening Port:   " -NoNewline; Write-Host "$WinRMPort (HTTP)" -ForegroundColor White
if ($RemoteUser) {
    Write-Host "Configured User:  " -NoNewline; Write-Host "$RemoteUser" -ForegroundColor White
}

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "1. Run the client setup script on the machine that will connect to this server" -ForegroundColor White
Write-Host "2. Test the connection from the client using:" -ForegroundColor White
Write-Host "   Test-WSMan -ComputerName $env:COMPUTERNAME" -ForegroundColor Gray
Write-Host ""

Write-Host "Setup complete!" -ForegroundColor Green