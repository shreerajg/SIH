param(
    [switch]$IncludeToys
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Locate the actual repository root safely. This works even if the pack is extracted
# into a subfolder under C:\SIH.
$probe = (Resolve-Path $PSScriptRoot).Path
$repoRoot = $null
for ($i = 0; $i -lt 5; $i++) {
    if ((Test-Path (Join-Path $probe 'backend')) -and (Test-Path (Join-Path $probe 'frontend')) -and (Test-Path (Join-Path $probe 'data'))) {
        $repoRoot = $probe
        break
    }
    $parent = Split-Path $probe -Parent
    if ($parent -eq $probe -or [string]::IsNullOrWhiteSpace($parent)) { break }
    $probe = $parent
}
if (-not $repoRoot) {
    throw "Could not locate SIH repository root (expected backend, frontend and data folders). Move/extract this pack somewhere under C:\SIH and rerun."
}

$finalRoot = Join-Path $repoRoot 'data\raw\verified_bis_2026_09_03'
$stageRoot = "$finalRoot.__staging__"

if (Test-Path $finalRoot) {
    throw "Safety stop: $finalRoot already exists. This script will NOT overwrite existing verified data. Rename/remove it manually only if you intentionally want to rerun."
}
if (Test-Path $stageRoot) { Remove-Item -Recurse -Force $stageRoot }
New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null

$allowedHosts = @('www.bis.gov.in','bis.gov.in')
$files = @(
  @{ Scenario='water_heater'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2024/09/2082-PM_V6_-approved.pdf'; Out='water_heater\IS_2082_2018_Product_Manual_Sep_2024.pdf' },
  @{ Scenario='water_heater'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2024/09/302-2-21-PM_-approved.pdf'; Out='water_heater\IS_302_Part2_Sec21_2024_Product_Manual_Sep_2024.pdf' },
  @{ Scenario='water_heater'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2025/01/Electrical-Appliances-for-domestic-water-heating-QCO-2025.pdf'; Out='water_heater\Domestic_Water_Heating_QCO_2025.pdf' },
  @{ Scenario='pressure_cooker'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2025/02/PM-IS-2347.pdf'; Out='pressure_cooker\IS_2347_2023_Product_Manual_Feb_2025.pdf' },
  @{ Scenario='pressure_cooker'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2020/01/Pressure_cooker_QCO.pdf'; Out='pressure_cooker\Domestic_Pressure_Cooker_QCO_2020.pdf' },
  @{ Scenario='pressure_cooker'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2020/07/Extension-Order-Pressure-Cooker.pdf'; Out='pressure_cooker\Domestic_Pressure_Cooker_QCO_Amendment_2020.pdf' },
  @{ Scenario='helmet'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2024/12/PM_IS_4151_-Dec-24.pdf'; Out='helmet\IS_4151_2015_Product_Manual_Dec_2024.pdf' },
  @{ Scenario='helmet'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2020/12/Helmet-for-riders-of-Two-Wheeler-Motor-Vehicles-Quality-Control-Order-2020.pdf'; Out='helmet\Helmet_Two_Wheeler_QCO_2020.pdf' },
  @{ Scenario='regulatory'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2026/06/Notification-of-Transition-Facilitation-Quality-Control-Order-2026.pdf'; Out='regulatory\Transition_Facilitation_QCO_2026.pdf' },
  @{ Scenario='regulatory'; Kind='html'; Url='https://www.bis.gov.in/product-certification/products-under-compulsory-certification/scheme-i-mark-scheme/?lang=en'; Out='regulatory\BIS_Current_Scheme_I_Compulsory_Certification.html' }
)

if ($IncludeToys) {
    $files += @(
      @{ Scenario='toys'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2023/11/PM-9873-Nov-2023.pdf'; Out='toys\Safety_of_Toys_Product_Manual_Nov_2023.pdf' },
      @{ Scenario='toys'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2020/03/Toy_QC_order.pdf'; Out='toys\Toys_QCO_2020.pdf' },
      @{ Scenario='toys'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2020/09/Toys-Extension.pdf'; Out='toys\Toys_QCO_Amendment_2020.pdf' },
      @{ Scenario='toys'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2020/12/Toys-Quality-Control-Second-Amendment-Order-2020.pdf'; Out='toys\Toys_QCO_Second_Amendment_2020.pdf' },
      @{ Scenario='toys'; Kind='pdf'; Url='https://www.bis.gov.in/wp-content/uploads/2024/10/Toys-QCO-2024.pdf'; Out='toys\Toys_QCO_Amendment_2024.pdf' }
    )
}

$report = @()
$allOk = $true

function Test-PdfMagic([string]$Path) {
    $fs = [System.IO.File]::OpenRead($Path)
    try {
        $buf = New-Object byte[] 5
        $read = $fs.Read($buf, 0, 5)
        if ($read -ne 5) { return $false }
        $sig = [System.Text.Encoding]::ASCII.GetString($buf)
        return ($sig -eq '%PDF-')
    } finally { $fs.Dispose() }
}

Write-Host "Repository root: $repoRoot" -ForegroundColor Cyan
Write-Host "Staging official files only. Existing project manifests/DB are NOT modified." -ForegroundColor Yellow

foreach ($f in $files) {
    $dest = Join-Path $stageRoot $f.Out
    New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
    $tmp = "$dest.download"
    try {
        $uri = [Uri]$f.Url
        if ($allowedHosts -notcontains $uri.Host.ToLowerInvariant()) {
            throw "Host not allow-listed: $($uri.Host)"
        }

        Write-Host "Downloading [$($f.Scenario)] $($f.Url)" -ForegroundColor Gray
        Invoke-WebRequest -Uri $f.Url -OutFile $tmp -UseBasicParsing -Headers @{'User-Agent'='Mozilla/5.0'}
        $length = (Get-Item $tmp).Length
        if ($length -lt 1024) { throw "Downloaded file is suspiciously small ($length bytes)" }

        if ($f.Kind -eq 'pdf') {
            if (-not (Test-PdfMagic $tmp)) { throw "Downloaded file is not a real PDF (%PDF- signature missing)" }
        } else {
            $text = Get-Content -Raw -Path $tmp
            if ($text.Length -lt 5000 -or $text -notmatch 'Bureau of Indian Standards|Products under Compulsory Certification|Scheme') {
                throw "Downloaded HTML failed BIS-content validation"
            }
        }

        Move-Item -Force $tmp $dest
        $hash = (Get-FileHash -Algorithm SHA256 $dest).Hash.ToLowerInvariant()
        $report += [pscustomobject]@{ scenario=$f.Scenario; url=$f.Url; target=$f.Out; status='OK'; bytes=$length; sha256=$hash }
        Write-Host "  VALIDATED -> $($f.Out)" -ForegroundColor Green
    } catch {
        $allOk = $false
        if (Test-Path $tmp) { Remove-Item -Force $tmp }
        $report += [pscustomobject]@{ scenario=$f.Scenario; url=$f.Url; target=$f.Out; status='FAILED'; bytes=0; sha256=''; error=$_.Exception.Message }
        Write-Host "  FAILED -> $($_.Exception.Message)" -ForegroundColor Red
    }
}

$manifestPath = Join-Path $PSScriptRoot 'source_manifest_verified_v2.json'
if (Test-Path $manifestPath) { Copy-Item $manifestPath (Join-Path $stageRoot 'source_manifest_verified_v2.json') }
$report | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $stageRoot 'download_validation_report.json')
$report | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $stageRoot 'download_validation_report.csv')

if (-not $allOk) {
    Write-Host "" 
    Write-Host "SAFETY STOP: One or more sources failed validation." -ForegroundColor Red
    Write-Host "Nothing was promoted to the final verified folder and no project manifest/database was changed." -ForegroundColor Yellow
    Write-Host "Inspect: $stageRoot\download_validation_report.json" -ForegroundColor Yellow
    exit 2
}

Move-Item $stageRoot $finalRoot
Write-Host "" 
Write-Host "ALL DOWNLOADS VALIDATED." -ForegroundColor Green
Write-Host "Safe corpus folder: $finalRoot" -ForegroundColor Cyan
Write-Host "Next: give CLAUDE_SAFE_IMPORT_PROMPT.txt to Claude. Claude must perform a dry-run review before merging/ingesting." -ForegroundColor Cyan
