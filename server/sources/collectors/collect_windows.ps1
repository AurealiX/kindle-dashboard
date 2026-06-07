# Windows 指标采集 —— 输出统一 JSON(字段同 collect_linux.sh)。
# 基于 CIM/Get-Counter。⚠️ 待真机(Windows)验证。
# 用法:powershell -NoProfile -ExecutionPolicy Bypass -File collect_windows.ps1
$ErrorActionPreference = "SilentlyContinue"

# CPU:所有逻辑处理器平均负载
$cpu = [int]((Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average)

# 内存(字节)
$os = Get-CimInstance Win32_OperatingSystem
$memTotal = [int64]$os.TotalVisibleMemorySize * 1024
$memUsed  = $memTotal - ([int64]$os.FreePhysicalMemory * 1024)

# 网络速率(bytes/s):累加所有物理网卡,两次采样差
function Read-Net {
    $s = Get-NetAdapterStatistics -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch 'Loopback' }
    $rx = ($s | Measure-Object -Property ReceivedBytes -Sum).Sum
    $tx = ($s | Measure-Object -Property SentBytes -Sum).Sum
    return @([int64]$rx, [int64]$tx)
}
$n1 = Read-Net; Start-Sleep -Seconds 1; $n2 = Read-Net
$netRx = [math]::Max(0, $n2[0] - $n1[0])
$netTx = [math]::Max(0, $n2[1] - $n1[1])

# 磁盘 IO 速率(bytes/s)
$dr = [int64]((Get-Counter '\PhysicalDisk(_Total)\Disk Read Bytes/sec').CounterSamples.CookedValue)
$dw = [int64]((Get-Counter '\PhysicalDisk(_Total)\Disk Write Bytes/sec').CounterSamples.CookedValue)

# 分区(本地固定盘 DriveType=3)
$disks = @()
foreach ($d in Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3") {
    if ($d.Size -gt 0) {
        $used = [int64]$d.Size - [int64]$d.FreeSpace
        $disks += [ordered]@{
            name  = $d.DeviceID
            used  = $used
            total = [int64]$d.Size
            pct   = [int]([math]::Round($used / $d.Size * 100))
        }
    }
}

$out = [ordered]@{
    cpu_pct    = $cpu
    mem_used   = $memUsed
    mem_total  = $memTotal
    net_rx     = $netRx
    net_tx     = $netTx
    disk_read  = $dr
    disk_write = $dw
    disks      = $disks
}
$out | ConvertTo-Json -Compress -Depth 4
