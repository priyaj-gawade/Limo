<#
.SYNOPSIS
    Convenience shorthand to start the full Limo application.
.DESCRIPTION
    Forwards arguments directly to start-all.ps1.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    $RemainingArgs
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartAll = Join-Path $ScriptDir "start-all.ps1"

& $StartAll @RemainingArgs
