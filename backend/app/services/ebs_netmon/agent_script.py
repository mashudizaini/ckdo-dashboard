"""
Generates the PowerShell diagnostic agent — version 2 of the script in
sumber/Oracle_EBS_HO_Plant_Performance_Diagnostic_Script.md.

What changed from v1, and why:
  - .NET Ping instead of ping.exe text, so loss / avg / p95 / jitter are
    computed on the laptop instead of eyeballed from 11 text files.
  - Path MTU discovery (DF bit, binary search) — an MTU/MSS mismatch on the
    IPsec tunnel (NET-06) looks exactly like "EBS hangs on big screens".
  - TCP connect + HTTP TTFB to EBS itself, not just ICMP to its host.
  - Wi-Fi signal, proxy, Java, power plan, uptime: the CLI-0x usual suspects.
  - CIM perf classes instead of Get-Counter: counter names are localised on
    Indonesian Windows, CIM class names are not.
  - Posts a JSON summary to the dashboard (one-time token), still writes
    every raw file to the Desktop folder like v1, and zips it.

The template is ASCII-only on purpose: Windows PowerShell 5.1 reads a BOM-less
script as ANSI, so a single UTF-8 dash would corrupt a string literal.
"""
from datetime import datetime

AGENT_VERSION = "2.0"

TEMPLATE = r"""# ============================================================
# Oracle EBS HO -> Plant Diagnostic Agent (CKDO Dashboard)
# Version   : __VERSION__   generated __GENERATED__
# Run       : powershell -ExecutionPolicy Bypass -File .\EBS_HO_Diagnostic.ps1
# Options   : -Count 100  -Pathping  -NoUpload  -Condition Slow  -Note "text"
# Upload    : valid until __EXPIRES__ (after that use -NoUpload and upload
#             the summary.json file manually in the dashboard)
# ============================================================
param(
    [int]$Count = __COUNT__,
    [switch]$Pathping,
    [switch]$NoUpload,
    [ValidateSet('', 'Normal', 'Slow', 'Hang', 'Restart')][string]$Condition = '',
    [string]$Note = ''
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$EBS_HOST      = '__EBS_HOST__'
$EBS_PORTS     = @(__EBS_PORTS__)
$EBS_URL       = '__EBS_URL__'
$INGEST_URL    = '__INGEST_URL__'
$COMPARE_HOSTS = @(__COMPARE__)
$IsPS5 = $PSVersionTable.PSVersion.Major -le 5

if ($IsPS5) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    [Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
}

$TimeStamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$OutputDir = Join-Path ([Environment]::GetFolderPath('Desktop')) "EBS_Diagnostic_$TimeStamp"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$TotalSteps = 12

function Step([int]$n, [string]$text) { Write-Host ("[{0}/{1}] {2}" -f $n, $TotalSteps, $text) -ForegroundColor Cyan }
function SafeName([string]$s) { return ($s -replace '[^\w\.-]', '_') }

function Get-Stats($rtts, [int]$N) {
    $arr = @($rtts)
    $ok = $arr.Count
    $loss = $null
    if ($N -gt 0) { $loss = [math]::Round(($N - $ok) * 100.0 / $N, 1) }
    $o = [ordered]@{ sent = $N; received = $ok; loss_pct = $loss; min = $null; avg = $null; max = $null; p95 = $null; jitter = $null }
    if ($ok -gt 0) {
        $m = $arr | Measure-Object -Minimum -Maximum -Average
        $o.min = [math]::Round($m.Minimum, 1)
        $o.max = [math]::Round($m.Maximum, 1)
        $o.avg = [math]::Round($m.Average, 1)
        $sorted = @($arr | Sort-Object)
        $idx = [math]::Min($sorted.Count - 1, [int][math]::Floor($sorted.Count * 0.95))
        $o.p95 = [math]::Round($sorted[$idx], 1)
        $o.jitter = 0
        if ($ok -gt 1) {
            $d = 0.0
            for ($i = 1; $i -lt $ok; $i++) { $d += [math]::Abs($arr[$i] - $arr[$i - 1]) }
            $o.jitter = [math]::Round($d / ($ok - 1), 1)
        }
    }
    return $o
}

function Get-PingStats([string]$Target, [int]$N, [int]$IntervalMs = 200) {
    $p = New-Object System.Net.NetworkInformation.Ping
    $rtts = New-Object System.Collections.Generic.List[double]
    $lines = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $N; $i++) {
        try {
            $r = $p.Send($Target, 2000)
            if ($r.Status -eq 'Success') {
                $rtts.Add([double]$r.RoundtripTime)
                $lines.Add(("{0:HH:mm:ss.fff} reply time={1}ms" -f (Get-Date), $r.RoundtripTime))
            } else {
                $lines.Add(("{0:HH:mm:ss.fff} {1}" -f (Get-Date), $r.Status))
            }
        } catch {
            $lines.Add(("{0:HH:mm:ss.fff} error {1}" -f (Get-Date), $_.Exception.Message))
        }
        Start-Sleep -Milliseconds $IntervalMs
    }
    $lines | Out-File (Join-Path $OutputDir ("ping_" + (SafeName $Target) + ".txt"))
    $s = Get-Stats $rtts $N
    $s.host = $Target
    return $s
}

function Get-PathMtu([string]$Target) {
    $p = New-Object System.Net.NetworkInformation.Ping
    $opt = New-Object System.Net.NetworkInformation.PingOptions(64, $true)
    $lo = 548; $hi = 1472; $best = $null
    while ($lo -le $hi) {
        $mid = [int][math]::Floor(($lo + $hi) / 2)
        $buf = New-Object byte[] $mid
        $ok = $false
        foreach ($attempt in 1..2) {
            try { $r = $p.Send($Target, 1500, $buf, $opt); if ($r.Status -eq 'Success') { $ok = $true; break } } catch {}
        }
        if ($ok) { $best = $mid; $lo = $mid + 1 } else { $hi = $mid - 1 }
    }
    if ($best) { return ($best + 28) }
    return $null
}

function Get-TcpStats([string]$Target, [int]$Port, [int]$N = 10) {
    $rtts = New-Object System.Collections.Generic.List[double]
    $err = $null
    for ($i = 0; $i -lt $N; $i++) {
        $c = New-Object System.Net.Sockets.TcpClient
        $sw = [Diagnostics.Stopwatch]::StartNew()
        try {
            $iar = $c.BeginConnect($Target, $Port, $null, $null)
            if ($iar.AsyncWaitHandle.WaitOne(3000)) {
                $c.EndConnect($iar)
                $sw.Stop()
                $rtts.Add($sw.Elapsed.TotalMilliseconds)
            } else { $err = 'timeout 3s' }
        } catch { $err = $_.Exception.Message } finally { $c.Close() }
        Start-Sleep -Milliseconds 200
    }
    $s = Get-Stats $rtts $N
    $s.port = $Port
    $s.error = $err
    return $s
}

function Get-HttpStats([string]$Url, [int]$N = 5) {
    $rtts = New-Object System.Collections.Generic.List[double]
    $status = $null; $err = $null
    for ($i = 0; $i -lt $N; $i++) {
        $sw = [Diagnostics.Stopwatch]::StartNew()
        try {
            if ($IsPS5) {
                $req = [System.Net.HttpWebRequest]::Create($Url)
                $req.Method = 'GET'; $req.Timeout = 15000; $req.AllowAutoRedirect = $false
                $req.Headers.Add('Cache-Control', 'no-cache')
                $resp = $req.GetResponse()
                $sw.Stop(); $status = [int]$resp.StatusCode; $resp.Close()
            } else {
                $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -SkipCertificateCheck -MaximumRedirection 0 -TimeoutSec 15 -ErrorAction Stop
                $sw.Stop(); $status = [int]$resp.StatusCode
            }
            $rtts.Add($sw.Elapsed.TotalMilliseconds)
        } catch {
            $sw.Stop()
            $r = $_.Exception.Response
            if ($r) { $rtts.Add($sw.Elapsed.TotalMilliseconds); try { $status = [int]$r.StatusCode } catch {} }
            else { $err = $_.Exception.Message }
        }
        Start-Sleep -Milliseconds 300
    }
    $s = Get-Stats $rtts $N
    $s.status = $status
    $s.error = $err
    $s.url = $Url
    return $s
}

Write-Host ''
Write-Host '=====================================================' -ForegroundColor Yellow
Write-Host ' Oracle EBS HO -> Plant Diagnostic Agent v__VERSION__' -ForegroundColor Yellow
Write-Host '=====================================================' -ForegroundColor Yellow
Write-Host "Computer : $env:COMPUTERNAME"
Write-Host "EBS Host : $EBS_HOST"
Write-Host "Output   : $OutputDir"
Write-Host ''

if (-not $Condition) {
    Write-Host 'Bagaimana kondisi Oracle EBS SAAT INI?'
    Write-Host '  1 = Normal   2 = Lambat   3 = Hang / tidak merespons   4 = Harus restart browser'
    $ans = Read-Host 'Pilih 1-4 (Enter = Normal)'
    switch ($ans) { '2' { $Condition = 'Slow' } '3' { $Condition = 'Hang' } '4' { $Condition = 'Restart' } default { $Condition = 'Normal' } }
}
if (-not $Note -and $Condition -ne 'Normal') { $Note = Read-Host 'Modul / transaksi EBS yang sedang dipakai (opsional)' }
$StartedAt = Get-Date

# ------------------------------------------------------------ 1. System
Step 1 'System information'
$cs = Get-CimInstance Win32_ComputerSystem
$cpuInfo = Get-CimInstance Win32_Processor | Select-Object -First 1
$os = Get-CimInstance Win32_OperatingSystem
$cs, $cpuInfo, $os | Format-List * | Out-File (Join-Path $OutputDir '01_System.txt')
$powerPlan = (powercfg /getactivescheme 2>$null | Out-String).Trim()
$uptimeH = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalHours, 1)

# ------------------------------------------------------------ 2. IP / DNS
Step 2 'IP configuration and DNS resolution'
ipconfig /all | Out-File (Join-Path $OutputDir '02_IPConfig.txt')
$ebsIp = $EBS_HOST
$dnsMs = $null
if ($EBS_HOST -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
    try {
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $res = Resolve-DnsName $EBS_HOST -Type A -DnsOnly -ErrorAction Stop
        $sw.Stop(); $dnsMs = [math]::Round($sw.Elapsed.TotalMilliseconds, 1)
        $ebsIp = ($res | Where-Object { $_.IPAddress } | Select-Object -First 1).IPAddress
        $res | Out-File (Join-Path $OutputDir '11_DNS.txt')
    } catch { "DNS FAILED: $($_.Exception.Message)" | Out-File (Join-Path $OutputDir '11_DNS.txt') }
}

# ------------------------------------------------------------ 3. Route / adapter
Step 3 'Route and network adapter used to reach EBS'
$route = $null
try { $route = Find-NetRoute -RemoteIPAddress $ebsIp -ErrorAction Stop | Where-Object { $_.NextHop } | Select-Object -First 1 } catch {}
if (-not $route) { $route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1 }
$gateway = $null; $ifAlias = $null
if ($route) { $gateway = $route.NextHop; $ifAlias = $route.InterfaceAlias }
if ($gateway -eq '0.0.0.0') { $gateway = $null }
$adapter = $null
if ($ifAlias) { $adapter = Get-NetAdapter -InterfaceAlias $ifAlias -ErrorAction SilentlyContinue }
Get-NetAdapter | Select-Object Name, InterfaceDescription, Status, LinkSpeed, MediaType, PhysicalMediaType, MacAddress |
    Format-Table -AutoSize | Out-File (Join-Path $OutputDir '08_NetworkAdapter.txt')
Get-NetIPConfiguration | Out-File (Join-Path $OutputDir '08_NetworkConfiguration.txt')
$connection = 'unknown'
if ($adapter) {
    $desc = "$($adapter.InterfaceDescription) $($adapter.Name)"
    if ($desc -match 'Fortinet|FortiClient|VPN|TAP|Wintun|WireGuard') { $connection = 'VPN' }
    elseif ("$($adapter.PhysicalMediaType)" -match '802\.11|Wireless' -or $desc -match 'Wi-?Fi|Wireless|WLAN|802\.11') { $connection = 'Wi-Fi' }
    else { $connection = 'LAN' }
}
$wifi = $null
$wlanRaw = (netsh wlan show interfaces 2>$null | Out-String)
$wlanRaw | Out-File (Join-Path $OutputDir '08_Wifi.txt')
if ($wlanRaw -match '(?m)^\s*Signal\s*:\s*(\d+)%') {
    $wifi = [ordered]@{ signal_pct = [int]$Matches[1] }
    if ($wlanRaw -match '(?m)^\s*SSID\s*:\s*(.+)$') { $wifi.ssid = $Matches[1].Trim() }
    if ($wlanRaw -match '(?m)^\s*Radio type\s*:\s*(.+)$') { $wifi.radio = $Matches[1].Trim() }
    if ($wlanRaw -match '(?m)^\s*Channel\s*:\s*(\d+)') { $wifi.channel = [int]$Matches[1] }
    if ($wlanRaw -match '(?m)^\s*Receive rate \(Mbps\)\s*:\s*([\d\.]+)') { $wifi.rx_mbps = [double]$Matches[1] }
    if ($wlanRaw -match '(?m)^\s*Transmit rate \(Mbps\)\s*:\s*([\d\.]+)') { $wifi.tx_mbps = [double]$Matches[1] }
    if ($wlanRaw -match '(?m)^\s*BSSID\s*:\s*(\S+)') { $wifi.bssid = $Matches[1].Trim() }
}
$inet = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
$proxy = [ordered]@{ enabled = [bool]$inet.ProxyEnable; server = $inet.ProxyServer; pac = $inet.AutoConfigURL; bypass = $inet.ProxyOverride
                     winhttp = (netsh winhttp show proxy 2>$null | Out-String).Trim() }

# ------------------------------------------------------------ 4. Gateway
Step 4 "Ping laptop -> HO gateway ($gateway), $Count packets"
$pingGw = $null
if ($gateway) { $pingGw = Get-PingStats $gateway $Count }

# ------------------------------------------------------------ 5. EBS ping
Step 5 "Ping laptop -> Oracle EBS ($ebsIp), $Count packets"
$pingEbs = Get-PingStats $ebsIp $Count

# ------------------------------------------------------------ 6. Compare
Step 6 'Ping comparison targets (internet / other sites)'
$compare = @()
foreach ($h in $COMPARE_HOSTS) { if ($h) { $compare += Get-PingStats $h 20 } }

# ------------------------------------------------------------ 7. TCP / HTTP
Step 7 'TCP connect and HTTP response time to EBS'
$tcp = @()
foreach ($port in $EBS_PORTS) { if ($port) { $tcp += Get-TcpStats $ebsIp ([int]$port) 10 } }
$http = $null
if ($EBS_URL) { $http = Get-HttpStats $EBS_URL 5 }

# ------------------------------------------------------------ 8. MTU
Step 8 'Path MTU discovery to EBS (Do-Not-Fragment)'
$pathMtu = Get-PathMtu $ebsIp
"Path MTU to ${ebsIp}: $pathMtu" | Out-File (Join-Path $OutputDir '12_PathMTU.txt')

# ------------------------------------------------------------ 9. Tracert
Step 9 'Traceroute to EBS'
$tr = (tracert -d -h 15 -w 1000 $ebsIp | Out-String)
$tr | Out-File (Join-Path $OutputDir '06_Tracert_EBS.txt')
$hops = @($tr -split "`n" | Where-Object { $_ -match '^\s*\d+\s' }).Count
if ($Pathping) {
    Write-Host '      pathping runs ~5 minutes...'
    pathping -n -q 50 $ebsIp | Out-File (Join-Path $OutputDir '07_Pathping_EBS.txt')
}

# ------------------------------------------------------------ 10. Resources
Step 10 'CPU / RAM / Disk snapshot (5 seconds)'
$cpuSamples = @()
foreach ($i in 1..5) {
    $cpuSamples += (Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'").PercentProcessorTime
    Start-Sleep -Seconds 1
}
$cpuPct = [math]::Round(($cpuSamples | Measure-Object -Average).Average, 1)
$os2 = Get-CimInstance Win32_OperatingSystem
$ramAvail = [math]::Round($os2.FreePhysicalMemory * 100.0 / $os2.TotalVisibleMemorySize, 1)
$diskPct = $null
try { $diskPct = [math]::Min(100, [double](Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk -Filter "Name='_Total'").PercentDiskTime) } catch {}
$cores = [math]::Max(1, [int]$cs.NumberOfLogicalProcessors)
$topCpu = Get-CimInstance Win32_PerfFormattedData_PerfProc_Process |
    Where-Object { $_.Name -notin @('_Total', 'Idle') } | Sort-Object PercentProcessorTime -Descending | Select-Object -First 6 |
    ForEach-Object { [ordered]@{ name = $_.Name; cpu_pct = [math]::Round($_.PercentProcessorTime / $cores, 1) } }
$topMem = Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 6 |
    ForEach-Object { [ordered]@{ name = $_.ProcessName; mem_mb = [math]::Round($_.WorkingSet64 / 1MB, 0) } }
"CPU avg 5s: $cpuPct %`nRAM available: $ramAvail %`nDisk time: $diskPct %" | Out-File (Join-Path $OutputDir '09_Resources.txt')

# ------------------------------------------------------------ 11. Client software
Step 11 'Browser, Java and active EBS connections'
$browser = $null
try { $browser = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice' -ErrorAction Stop).ProgId } catch {}
$java = @()
foreach ($k in 'HKLM:\SOFTWARE\JavaSoft\Java Runtime Environment', 'HKLM:\SOFTWARE\WOW6432Node\JavaSoft\Java Runtime Environment') {
    $v = Get-ItemProperty $k -ErrorAction SilentlyContinue
    if ($v -and $v.CurrentVersion) { $java += "$k = $($v.CurrentVersion)" }
}
try { $java += ((& java -version 2>&1) | Select-Object -First 1 | Out-String).Trim() } catch {}
$estab = @()
try { $estab = @(Get-NetTCPConnection -State Established -RemoteAddress $ebsIp -ErrorAction Stop) } catch {}
Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Sort-Object RemoteAddress |
    Format-Table -AutoSize | Out-File (Join-Path $OutputDir '10_TCP_Connections.txt')

# ------------------------------------------------------------ 12. Summary
Step 12 'Writing summary'
$summary = [ordered]@{
    agent_version = '__VERSION__'
    hostname = $env:COMPUTERNAME
    user = "$env:USERDOMAIN\$env:USERNAME"
    started_at = $StartedAt.ToString('o')
    finished_at = (Get-Date).ToString('o')
    condition = $Condition
    note = $Note
    connection = $connection
    ebs_host = $EBS_HOST
    ebs_ip = $ebsIp
    dns_ms = $dnsMs
    system = [ordered]@{
        manufacturer = $cs.Manufacturer; model = $cs.Model
        cpu = $cpuInfo.Name; cores = $cpuInfo.NumberOfCores; logical = $cs.NumberOfLogicalProcessors
        ram_gb = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
        os = "$($os.Caption) $($os.Version)"; uptime_hours = $uptimeH; power_plan = $powerPlan
        powershell = "$($PSVersionTable.PSVersion)"
    }
    network = [ordered]@{
        interface = $ifAlias
        adapter = $(if ($adapter) { $adapter.InterfaceDescription } else { $null })
        link_speed = $(if ($adapter) { "$($adapter.LinkSpeed)" } else { $null })
        gateway = $gateway; wifi = $wifi; proxy = $proxy
    }
    ping_gateway = $pingGw
    ping_ebs = $pingEbs
    ping_compare = $compare
    tcp_ebs = $tcp
    http_ebs = $http
    path_mtu = $pathMtu
    tracert_hops = $hops
    tracert = $tr
    resources = [ordered]@{ cpu_pct = $cpuPct; ram_avail_pct = $ramAvail; disk_pct = $diskPct; top_cpu = @($topCpu); top_mem = @($topMem) }
    client = [ordered]@{ browser = $browser; java = $java; ebs_established = $estab.Count }
}
$json = $summary | ConvertTo-Json -Depth 6
$jsonPath = Join-Path $OutputDir 'summary.json'
[IO.File]::WriteAllText($jsonPath, $json, (New-Object System.Text.UTF8Encoding($false)))

$zip = "$OutputDir.zip"
try { Compress-Archive -Path "$OutputDir\*" -DestinationPath $zip -Force } catch {}

$uploaded = $false
if (-not $NoUpload -and $INGEST_URL) {
    try {
        $body = [Text.Encoding]::UTF8.GetBytes($json)
        if ($IsPS5) { $r = Invoke-RestMethod -Method Post -Uri $INGEST_URL -Body $body -ContentType 'application/json; charset=utf-8' -TimeoutSec 60 }
        else { $r = Invoke-RestMethod -Method Post -Uri $INGEST_URL -Body $body -ContentType 'application/json; charset=utf-8' -TimeoutSec 60 -SkipCertificateCheck }
        $uploaded = $true
        Write-Host ''
        Write-Host ("Terkirim ke dashboard. Verdict: {0}  {1}" -f $r.verdict, $r.verdict_text) -ForegroundColor Green
    } catch {
        Write-Host ''
        Write-Host "Upload gagal: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host 'Upload summary.json secara manual di dashboard (Client Test > Upload hasil agen).' -ForegroundColor Red
    }
}

Write-Host ''
Write-Host '=====================================================' -ForegroundColor Yellow
Write-Host ' DIAGNOSTIC COMPLETED' -ForegroundColor Yellow
Write-Host '=====================================================' -ForegroundColor Yellow
if ($pingGw) { Write-Host ("Gateway : avg {0} ms  max {1} ms  loss {2}%  jitter {3} ms" -f $pingGw.avg, $pingGw.max, $pingGw.loss_pct, $pingGw.jitter) }
Write-Host ("EBS     : avg {0} ms  max {1} ms  loss {2}%  jitter {3} ms" -f $pingEbs.avg, $pingEbs.max, $pingEbs.loss_pct, $pingEbs.jitter)
Write-Host ("MTU     : {0}    CPU {1}%   RAM free {2}%   Koneksi {3}" -f $pathMtu, $cpuPct, $ramAvail, $connection)
Write-Host "Folder  : $OutputDir"
if (-not $uploaded) { Write-Host "Zip     : $zip" }
Write-Host ''
Write-Host 'PENTING: jalankan juga Network Test dari dalam Oracle EBS dan catat Round Trip Time + Data Rate.'
"""


def _ps_quote(s: str) -> str:
    """Single-quoted PowerShell literal content (only ' needs escaping)."""
    return (s or "").replace("'", "''")


def render(ebs_host: str, ebs_ports: list, ebs_url: str, ingest_url: str,
           compare_hosts: list, count: int, expires_at: datetime | None) -> str:
    ports = ", ".join(str(int(p)) for p in (ebs_ports or []) if str(p).strip().isdigit())
    compare = ", ".join(f"'{_ps_quote(h)}'" for h in compare_hosts if h)
    text = (TEMPLATE
            .replace("__VERSION__", AGENT_VERSION)
            .replace("__GENERATED__", datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("__EXPIRES__", expires_at.strftime("%Y-%m-%d %H:%M UTC") if expires_at else "-")
            .replace("__COUNT__", str(int(count)))
            .replace("__EBS_HOST__", _ps_quote(ebs_host))
            .replace("__EBS_PORTS__", ports)
            .replace("__EBS_URL__", _ps_quote(ebs_url))
            .replace("__INGEST_URL__", _ps_quote(ingest_url))
            .replace("__COMPARE__", compare))
    # CRLF: Notepad and PowerShell ISE both behave with it; ASCII guaranteed.
    return text.replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii", "replace").decode("ascii")
