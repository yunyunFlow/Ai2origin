param(
    [Parameter(Mandatory=$true)][string]$Plan,
    [string]$OutDir,
    [string]$OriginExe,
    [switch]$Run,
    [switch]$AllowOtherVersion,
    [ValidateRange(10,600)][int]$TimeoutSeconds=180,
    [switch]$InternalWorker
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$culture = [Globalization.CultureInfo]::InvariantCulture
$quote = [char]34
$originMissing = -1.23456789e-300

function Write-Json($Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 40), (New-Object Text.UTF8Encoding($false)))
}
function Get-ComProperty($Object, [string]$Name) {
    $value = $Object.GetType().InvokeMember($Name, [Reflection.BindingFlags]::GetProperty, $null, $Object, @())
    Write-Output -NoEnumerate $value
}
function Resolve-Server {
    # Inspect both registry views. Do not register, repair or change the default.
    foreach ($view in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
        $registry = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::ClassesRoot, $view)
        try {
            $key = $registry.OpenSubKey("Origin.Application\CLSID")
            if ($null -eq $key) { continue }
            try { $clsid = [string]$key.GetValue("") } finally { $key.Dispose() }
            foreach ($serverView in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
                $serverRoot = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::ClassesRoot, $serverView)
                try {
                    $serverKey = $serverRoot.OpenSubKey("CLSID\" + $clsid + "\LocalServer32")
                    if ($null -eq $serverKey) { continue }
                    try { $command = [Environment]::ExpandEnvironmentVariables([string]$serverKey.GetValue("")) } finally { $serverKey.Dispose() }
                    if ($command -match '^"([^"]+\.exe)"' -or $command -match '^(.+?\.exe)(?:\s|$)') {
                        $candidate = $matches[1].Trim()
                        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return [IO.Path]::GetFullPath($candidate) }
                    }
                } finally { $serverRoot.Dispose() }
            }
        } finally { $registry.Dispose() }
    }
    throw "Origin.Application COM registration has no existing server. Check the installed Origin version; this script changes no registration."
}
function Assert-PlainText([string]$Text) {
    if ($Text -match '[";\r\n%$\\]') { throw "Unsupported LabTalk text control character" }
}
function Assert-DrawingStatement([string]$Command) {
    # A prepared plan contains drawing statements, not arbitrary scripts.
    if ($Command -match '[;\r\n]' -or $Command -notmatch '^(plotxy |plotvm |layer[ .-]|page\.|range Curve[0-9]+=![0-9]+$|set Curve[0-9]+ |label |axis |legendupdate |Legend\.|SeriesKey[0-9]*\.|Title\.|AxisTitle[XY]\.|ScaleTitle\.|CBT[0-9]+\.|Group[0-9]+\.|xb\.|yl\.)') {
        throw "Plan contains an unsupported drawing statement"
    }
}
function Invoke-LT($App, [string]$Command) {
    Assert-DrawingStatement $Command
    $script:lastCommand = $Command
    if (-not $App.Execute($Command + ";")) { throw "Origin drawing statement failed: $Command" }
}

function Test-PreparedPlan($Prepared, [string]$PlanFolder) {
    if ($Prepared.schema_version -is [bool] -or $Prepared.schema_version -ne 1 -or @($Prepared.plots).Count -lt 1) { throw 'Invalid plan' }
    $ids=@{}; $graphs=@{}; $books=@{}
    foreach ($plot in $Prepared.plots) {
        if ($plot.id -notmatch '^[A-Za-z][A-Za-z0-9_-]{0,47}$' -or $plot.graph_id -notmatch '^Plot[0-9]+$' -or $ids.ContainsKey([string]$plot.id) -or $graphs.ContainsKey([string]$plot.graph_id)) { throw 'Invalid or duplicate plot identity' }
        $ids[[string]$plot.id]=$true; $graphs[[string]$plot.graph_id]=$true
        if (@($plot.books).Count -lt 1 -or @($plot.commands).Count -lt 1) { throw 'Empty plot data or commands' }
        foreach ($command in $plot.commands) { Assert-DrawingStatement ([string]$command) }
        foreach ($book in $plot.books) {
            if ($book.name -notmatch '^Data[0-9]+(?:Raw)?$' -or $books.ContainsKey([string]$book.name)) { throw 'Invalid or duplicate book identity' }
            $books[[string]$book.name]=$true
            $rows=@($book.rows).Count; $cols=@($book.headers).Count
            if ($rows -lt 1 -or $cols -lt 2 -or $rows*$cols -gt 2000000) { throw 'Invalid or oversized worksheet' }
            $headers=@{}
            foreach ($header in $book.headers) {
                Assert-PlainText ([string]$header)
                if (-not [string]$header -or $headers.ContainsKey([string]$header)) { throw 'Invalid or duplicate column header' }
                $headers[[string]$header]=$true
            }
            foreach ($row in $book.rows) {
                if (@($row).Count -ne $cols) { throw 'Worksheet row width mismatch' }
                foreach ($value in $row) {
                    if ($null -eq $value) { continue }
                    if ($value -is [bool] -or $value -is [string] -or $value -is [System.Management.Automation.PSCustomObject]) { throw 'Worksheet values must be JSON numbers or null' }
                    $cell=[double]$value
                    if ([double]::IsInfinity($cell) -or [double]::IsNaN($cell) -or $cell -eq $originMissing) { throw 'Non-finite or reserved worksheet value' }
                }
            }
        }
        if ($plot.metadata.kind -eq 'heatmap') {
            if ($plot.metadata.color_levels -is [bool] -or $plot.metadata.color_levels -lt 2 -or $plot.metadata.color_levels -gt 256 -or @($plot.metadata.colorbar_palette).Count -ne $plot.metadata.color_levels) {throw 'Invalid prepared palette size'}
            foreach ($color in $plot.metadata.colorbar_palette) {if ([string]$color -notmatch '^#[0-9a-fA-F]{6}$') {throw 'Invalid prepared palette color'}}
            $asset=$plot.metadata.colorbar_asset
            if ($asset.name -notmatch '^[A-Za-z][A-Za-z0-9_-]*-colorbar\.png$') { throw 'Invalid colorbar asset name' }
            $path=Join-Path $PlanFolder $asset.name
            if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.sha256) { throw 'Colorbar asset hash mismatch' }
        }
    }
}
function Assert-Worksheet($App, [string]$Sheet, [double[,]]$ExpectedMatrix) {
    $rows = $ExpectedMatrix.GetLength(0)
    $cols = $ExpectedMatrix.GetLength(1)
    $back = $App.GetWorksheet($Sheet, 0, 0, $rows-1, $cols-1, 2)
    if ($null -eq $back -or $back.Rank -ne 2 -or $back.GetLength(0) -ne $rows -or $back.GetLength(1) -ne $cols) {
        throw "Read-back matrix dimensions differ: $Sheet"
    }
    for ($r=0; $r -lt $rows; $r++) {
        for ($c=0; $c -lt $cols; $c++) {
            $expected = $ExpectedMatrix[$r,$c]
            $actual = [double]$back.GetValue($r+$back.GetLowerBound(0), $c+$back.GetLowerBound(1))
            $missing = [double]::IsNaN($actual) -or $actual -eq $originMissing
            if ($expected -eq $originMissing) {
                if (-not $missing) { throw "Padding changed: $Sheet row=$r col=$c actual=$actual" }
            } elseif ($missing -or [Math]::Abs($actual-$expected) -gt 1e-12 * (1+[Math]::Abs($expected))) {
                throw "Numerical read-back mismatch: $Sheet row=$r col=$c expected=$expected actual=$actual"
            }
        }
    }
    return $rows * $cols
}
function Assert-LogAxis($App, $Plot) {
    if ($Plot.metadata.x_scale -ne 'log10') { return }
    if ([double]$App.LTVar('layer.x.type') -ne 2) { throw 'Native logarithmic axis type drift' }
    foreach ($pair in @(@('layer.x.from',0),@('layer.x.to',1))) {
        $expected = [double]$Plot.metadata.x_range[[int]$pair[1]]
        $actual = [double]$App.LTVar([string]$pair[0])
        if ([Math]::Abs($actual-$expected) -gt 1e-12*(1+[Math]::Abs($expected))) { throw 'Native logarithmic axis range drift' }
    }
}
function Assert-ColorMap($App, $Plot) {
    if ($Plot.metadata.kind -ne 'heatmap') {return 0}
    if ([double]$App.LTVar('layer.cmap.numcolors') -ne [double]$Plot.metadata.color_levels) {throw 'Native color-level count drift'}
    foreach ($pair in @(@('layer.cmap.zmin',0),@('layer.cmap.zmax',1))) {
        if ([Math]::Abs([double]$App.LTVar([string]$pair[0])-[double]$Plot.metadata.color_range[[int]$pair[1]]) -gt 1e-12) {throw 'Native color range drift'}
    }
    $palette=@($Plot.metadata.colorbar_palette)
    for ($i=0;$i -lt $palette.Count;$i++) {
        $hex=[string]$palette[$i]
        if ($hex -notmatch '^#[0-9a-fA-F]{6}$') {throw 'Invalid prepared palette color'}
        if (-not $App.Execute('double a2oExpectedColor=color("'+$hex+'");')) {throw 'Palette color evaluation failed'}
        if ([double]$App.LTVar('layer.cmap.color'+($i+1)) -ne [double]$App.LTVar('a2oExpectedColor')) {throw ('Native palette color drift at '+($i+1))}
    }
    return $palette.Count
}
function Assert-GraphStyle($App, $Plot, $Style) {
    if (-not $App.Execute('double a2oFontID=font("'+[string]$Style.font.family+'");')) { throw 'Font index evaluation failed' }
    $expectedFont=[double]$App.LTVar('a2oFontID')
    foreach ($axis in @('x','y')) {
        if ([double]$App.LTVar('layer.'+$axis+'2.ticks') -ne 0) { throw 'Opposite-axis tick drift' }
        if ([double]$App.LTVar('layer.'+$axis+'.label.fsize') -ne [double]$Style.font.tick_size_pt) { throw 'Tick font size drift' }
        if ([double]$App.LTVar('layer.'+$axis+'.label.font') -ne $expectedFont) { throw 'Tick font family drift' }
    }
    if ($Plot.metadata.y_ticks -eq $false) {
        if ([double]$App.LTVar('layer.y.ticks') -ne 0 -or
            [double]$App.LTVar('layer.y.showLabels') -ne 0 -or
            [double]$App.LTVar('layer.y2.showLabels') -ne 0) { throw 'Hidden Y-axis ticks or labels drifted' }
    }
    $axisTitles=@('xb','AxisTitleY')
    if ($Plot.metadata.kind -eq 'raincloud' -and $Plot.metadata.orientation -eq 'vertical') { $axisTitles=@('AxisTitleX','AxisTitleY') }
    foreach ($name in $axisTitles) {
        if ([double]$App.LTVar($name+'.fsize') -ne [double]$Style.font.axis_title_size_pt) { throw 'Axis title size drift' }
        if ([double]$App.LTVar($name+'.font') -ne $expectedFont) { throw 'Axis title family drift' }
    }
    $legendCount=0
    if ($Plot.metadata.kind -in @('line','scatter','line_symbol')) { $legendCount=@($Plot.metadata.series).Count }
    for ($i=1;$i -le $legendCount;$i++) {
        if ([double]$App.LTVar('SeriesKey'+$i+'.fsize') -ne [double]$Style.font.legend_size_pt) { throw 'Legend size drift' }
        if ([double]$App.LTVar('SeriesKey'+$i+'.font') -ne $expectedFont) { throw 'Legend family drift' }
    }
}
function Measure-LabelGap($App, [string]$Image) {
    if (-not ('A2OInk' -as [type])) {
        Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System; using System.Drawing; using System.Drawing.Imaging;
using System.Runtime.InteropServices; using System.Collections.Generic;
public class A2OInk {
 static List<int[]> Runs(bool[] a) {
  var r=new List<int[]>(); int start=-1,last=-1;
  for(int i=0;i<a.Length;i++) if(a[i]) {
   if(start<0) start=i;
   else if(i-last>15) {r.Add(new int[]{start,last});start=i;} last=i;
  } if(start>=0) r.Add(new int[]{start,last});return r;
 }
 public static double[] Gap(string path,double left,double top,double width,double height) {
  using(var b=new Bitmap(path)) {
   int l=(int)Math.Round(left*b.Width/100), t=(int)Math.Round(top*b.Height/100);
   int r=(int)Math.Round((left+width)*b.Width/100), d=(int)Math.Round((top+height)*b.Height/100);
   var data=b.LockBits(new Rectangle(0,0,b.Width,b.Height),ImageLockMode.ReadOnly,PixelFormat.Format24bppRgb);
   byte[] p=new byte[data.Stride*b.Height];Marshal.Copy(data.Scan0,p,0,p.Length);b.UnlockBits(data);
   bool[] yy=new bool[b.Width],xx=new bool[b.Height];
   for(int y=0;y<b.Height;y++) for(int x=0;x<b.Width;x++) {
    int k=y*data.Stride+x*3;if(p[k]>=40||p[k+1]>=40||p[k+2]>=40) continue;
    if(y>t+12&&y<d-12&&x<l-20) yy[x]=true;
    if(y>d+20&&x>l+12&&x<r-12) xx[y]=true;
   }
   var yr=Runs(yy);var xr=Runs(xx);
   if(yr.Count<2||xr.Count<2) return new double[]{-1,-1,r-l};
   return new double[]{yr[1][0]-yr[0][1]-1,xr[xr.Count-1][0]-xr[xr.Count-2][1]-1,r-l};
  }
 }
}
'@
    }
    return [A2OInk]::Gap($Image,[double]$App.LTVar('layer.left'),[double]$App.LTVar('layer.top'),[double]$App.LTVar('layer.width'),[double]$App.LTVar('layer.height'))
}
function Align-LabelGap($App, $Plot, [string]$Image) {
    $gap=Measure-LabelGap $App $Image
    if ($gap[0] -lt 0) { return @{status='NO_NUMERIC_GROUP_AXIS';image=[IO.Path]::GetFileName($Image)} }
    $fraction=($gap[0]-$gap[1])/$gap[2]
    $from=[double]$App.LTVar('layer.x.from'); $to=[double]$App.LTVar('layer.x.to')
    $current=[double]$App.LTVar('AxisTitleY.x')
    if ($Plot.metadata.x_scale -eq 'log10') {
        $position=[Math]::Pow(10,[Math]::Log10($current)+$fraction*([Math]::Log10($to)-[Math]::Log10($from)))
    } else { $position=$current+$fraction*($to-$from) }
    if (-not $App.Execute('AxisTitleY.x='+$position.ToString('G17',$culture)+';')) { throw 'Axis title gap adjustment failed' }
    return @{status='ALIGNED_FROM_RENDER';before_y_px=$gap[0];target_x_px=$gap[1];fraction_delta=$fraction}
}
function Stop-OwnedSession([string]$StatePath) {
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { return }
    $state = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $process = Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) { return }
    if ($process.StartTime.ToUniversalTime().ToString("o") -ne $state.started_utc -or
        $process.Path -ine $state.executable) {
        throw "Session identity changed; refusing process termination"
    }
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
}
function Remove-OwnedAssets([string]$Folder) {
    $receipt = Join-Path $Folder "_assets.json"
    if (-not (Test-Path -LiteralPath $receipt -PathType Leaf)) { return }
    # Windows PowerShell 5.1 can wrap a JSON array in one pipeline result.
    # Keep the parsed array directly, so each asset has a scalar path.
    $assets = Get-Content -LiteralPath $receipt -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($asset in $assets) {
        $path = [IO.Path]::GetFullPath([string]$asset.path)
        if ([IO.Path]::GetDirectoryName($path) -ine [IO.Path]::GetTempPath().TrimEnd('\') -or
            [IO.Path]::GetFileName($path) -notmatch '^ai2origin-[0-9a-f]{32}\.png$') { throw "Unexpected temporary asset identity" }
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $item = Get-Item -LiteralPath $path
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
                (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.sha256) { throw "Owned palette changed; refusing cleanup" }
            Remove-Item -LiteralPath $path
        }
    }
}

$planPath = (Resolve-Path -LiteralPath $Plan).ProviderPath
$prepared = Get-Content -LiteralPath $planPath -Raw -Encoding UTF8 | ConvertFrom-Json
Test-PreparedPlan $prepared (Split-Path -Parent $planPath)
$selectedExe = Resolve-Server
if ($OriginExe -and [IO.Path]::GetFullPath($OriginExe) -ine $selectedExe) {
    throw "Requested executable differs from COM registration. Select the intended installation explicitly; no automatic re-registration is performed."
}
$version = (Get-Item -LiteralPath $selectedExe).VersionInfo.FileVersion
if (-not $AllowOtherVersion -and $version -notmatch '^(9\.8|2021)(\.|$)') {
    throw "Expected Origin 2021. Other versions require -AllowOtherVersion and their own checks."
}
$executableHash = (Get-FileHash -LiteralPath $selectedExe -Algorithm SHA256).Hash.ToLowerInvariant()
Add-Type -AssemblyName System.Drawing
$fonts = New-Object Drawing.Text.InstalledFontCollection
try {
    $fontName = [string]$prepared.style.font.family
    if ($fontName -notin @($fonts.Families | ForEach-Object {$_.Name})) { throw "Configured Origin font is not installed: $fontName. Choose an installed font explicitly." }
} finally { $fonts.Dispose() }
# Check-only is the default; it never activates COM or creates output files.
if (-not $Run -and -not $InternalWorker) {
    [pscustomobject]@{status="CHECK_ONLY"; origin_version=$version; executable_sha256=$executableHash; plots=@($prepared.plots).Count} | ConvertTo-Json -Compress
    exit 0
}
if (-not $OutDir) { throw "Specify a new output directory for -Run" }
$outputPath = [IO.Path]::GetFullPath($OutDir)
if ($outputPath -match '[";\r\n%$]') { throw "Output path contains LabTalk control characters" }

if (-not $InternalWorker) {
    if (Test-Path -LiteralPath $outputPath) { throw "Refusing to overwrite output directory" }
    if (@(Get-Process -Name Origin,Origin64 -ErrorAction SilentlyContinue).Count -gt 0) {
        throw "An Origin session is open. Leave it intact; complete this native run when Origin is idle."
    }
    New-Item -ItemType Directory -Path $outputPath | Out-Null
    $statePath = Join-Path $outputPath "_session.json"
    $job = $null
    try {
        $job = Start-Job -ScriptBlock {
            param($scriptFile, $planFile, $outputFolder, $exe, $other)
            & $scriptFile -Plan $planFile -OutDir $outputFolder -OriginExe $exe -AllowOtherVersion:$other -InternalWorker
        } -ArgumentList $PSCommandPath,$planPath,$outputPath,$selectedExe,([bool]$AllowOtherVersion)
        $done = Wait-Job -Job $job -Timeout $TimeoutSeconds
        if ($null -eq $done) {
            Write-Json (Join-Path $outputPath "FAILED.json") @{status="HOLD_TIMEOUT"; native_acceptance="FAILED"}
            throw "Origin native run exceeded its time limit; partial outputs are not accepted."
        }
        Receive-Job -Job $job -ErrorAction Stop
        if ($job.State -ne "Completed" -or -not (Test-Path -LiteralPath (Join-Path $outputPath "native-receipt.json"))) {
            throw "Native worker did not finish"
        }
    } catch {
        if (-not (Test-Path -LiteralPath (Join-Path $outputPath 'FAILED.json'))) {
            Write-Json (Join-Path $outputPath 'FAILED.json') @{status='FAILED';message=$_.Exception.Message;native_acceptance='FAILED'}
        }
        throw
    } finally {
        if ($null -ne $job) { Stop-Job -Job $job -ErrorAction SilentlyContinue; Remove-Job -Job $job -Force -ErrorAction SilentlyContinue }
        Stop-OwnedSession $statePath
        Remove-OwnedAssets $outputPath
    }
    exit 0
}

# Independent COM class: never attach to an existing author session.
$app = $null
$statePath = Join-Path $outputPath "_session.json"
$numericCells = 0
$paletteColors = 0
$verifiedSheets = @()
$ownedAssets = @()
try {
    if (@(Get-Process -Name Origin,Origin64 -ErrorAction SilentlyContinue).Count -gt 0) {
        throw "Origin became busy before worker activation; refusing to proceed."
    }
    $app = New-Object -ComObject "Origin.Application"
    $app.Visible = 0
    $processes = @(Get-Process -Name Origin,Origin64 -ErrorAction SilentlyContinue)
    if ($processes.Count -ne 1 -or $processes[0].Path -ine $selectedExe) {
        throw "Could not establish exclusive native session identity"
    }
    Write-Json $statePath @{pid=$processes[0].Id; started_utc=$processes[0].StartTime.ToUniversalTime().ToString("o"); executable=$selectedExe}
    if (-not $app.NewProject()) { throw "NewProject failed" }
    foreach ($plot in $prepared.plots) {
        if ($plot.id -notmatch '^[A-Za-z][A-Za-z0-9_-]{0,47}$' -or $plot.graph_id -notmatch '^Plot[0-9]+$') {
            throw "Invalid plot identity"
        }
        foreach ($book in $plot.books) {
            if ($book.name -notmatch '^Data[0-9]+(?:Raw)?$') { throw "Invalid book identity" }
            $rowCount = @($book.rows).Count
            $columnCount = @($book.headers).Count
            if ($rowCount -lt 1 -or $columnCount -lt 2 -or $rowCount * $columnCount -gt 2000000) { throw "Invalid or oversized worksheet" }
            $matrix = New-Object 'double[,]' $rowCount,$columnCount
            for ($r=0; $r -lt $rowCount; $r++) {
                if (@($book.rows[$r]).Count -ne $columnCount) { throw "Worksheet row width mismatch" }
                for ($c=0; $c -lt $columnCount; $c++) {
                    $value = $book.rows[$r][$c]
                    if ($null -ne $value -and [double]$value -eq $originMissing) { throw "Input equals Origin's reserved missing-value sentinel" }
                    $matrix[$r,$c] = if ($null -eq $value) { $originMissing } else { [double]$value }
                    $cell = $matrix[$r,$c]
                    if ([double]::IsInfinity($cell) -or [double]::IsNaN($cell)) { throw "Non-finite worksheet value" }
                }
            }
            if (-not $app.Execute("newbook name:=$($book.name) sheet:=1;wks.ncols=$columnCount;")) { throw "Worksheet creation failed" }
            $sheet = "[$($book.name)]Sheet1"
            if (-not $app.PutWorksheet($sheet, $matrix, 0, 0)) { throw "PutWorksheet failed" }
            for ($c=0; $c -lt $columnCount; $c++) {
                Assert-PlainText ([string]$book.headers[$c])
                $number = $c + 1
                $label = [string]$book.headers[$c]
                if (-not $app.Execute("wks.col$number.lname$=$quote$label$quote;")) { throw "Column label failed" }
            }
            $numericCells += Assert-Worksheet $app $sheet $matrix
            $verifiedSheets += @{sheet=$sheet; matrix=$matrix}
        }
        foreach ($command in $plot.commands) { Invoke-LT $app ([string]$command) }
        Assert-LogAxis $app $plot
        if ($plot.metadata.kind -eq "heatmap") {
            $range = @([double]$app.LTVar("layer.cmap.zmin"), [double]$app.LTVar("layer.cmap.zmax"))
            for ($i=0; $i -lt 2; $i++) {
                if ([Math]::Abs($range[$i] - [double]$plot.metadata.color_range[$i]) -gt 1e-12) { throw "Native color range drift" }
            }
            $asset = $plot.metadata.colorbar_asset
            if ($asset.name -notmatch '^[A-Za-z][A-Za-z0-9_-]*-colorbar\.png$') { throw "Invalid colorbar asset name" }
            $assetPath = Join-Path (Split-Path -Parent $planPath) $asset.name
            if ((Get-FileHash -LiteralPath $assetPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.sha256) { throw "Colorbar asset hash mismatch" }
            if ($assetPath -match '[";\r\n%$]') { throw "Unsupported asset path" }
            # Origin 2021's image X-function cannot consume this tested WSL
            # UNC path. Stage only the generated palette in an exclusive
            # native temp file, verify it, embed it, and remove it in finally.
            $stagedAsset = Join-Path ([IO.Path]::GetTempPath()) ("ai2origin-" + [Guid]::NewGuid().ToString("N") + ".png")
            [IO.File]::Copy($assetPath, $stagedAsset, $false)
            $ownedAssets += @{path=$stagedAsset; sha256=$asset.sha256}
            Write-Json (Join-Path $outputPath "_assets.json") @($ownedAssets)
            if ((Get-FileHash -LiteralPath $stagedAsset -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.sha256) { throw "Staged palette hash mismatch" }
            $escapedAsset = $stagedAsset.Replace('\','\\')
            $barScript = 'string cbname$="";insertImg2g fname:="'+$escapedAsset+'" type:=bmp xyp:=page x:=86 y:=18 oname:=cbname$;GObject cbar=%(cbname$);cbar.attach=2;cbar.dx=.065*(layer.x.to-layer.x.from);cbar.dy=layer.y.to-layer.y.from;cbar.x=layer.x.from+1.08*(layer.x.to-layer.x.from);cbar.y=layer.y.from+.5*(layer.y.to-layer.y.from);'
            if ($plot.metadata.x_scale -eq 'log10') {
                # Place a frame-attached decoration against temporary linear
                # frame coordinates, then restore the verified physical axis.
                $lower=([double]$plot.metadata.x_range[0]).ToString('G17',$culture)
                $upper=([double]$plot.metadata.x_range[1]).ToString('G17',$culture)
                $barScript = 'string cbname$="";insertImg2g fname:="'+$escapedAsset+'" type:=bmp xyp:=page x:=86 y:=18 oname:=cbname$;GObject cbar=%(cbname$);cbar.attach=0;layer.x.type=1;layer.x.from=0;layer.x.to=100;cbar.dx=6.5;cbar.dy=layer.y.to-layer.y.from;cbar.x=108;cbar.y=layer.y.from+.5*(layer.y.to-layer.y.from);layer.x.type=2;layer.x.from='+$lower+';layer.x.to='+$upper+';'
            }
            foreach ($statement in $barScript.Split(';')) {
                if (-not $statement) { continue }
                $script:lastCommand = $statement
                if (-not $app.Execute($statement + ';')) { throw "Palette bitmap placement failed: $statement" }
            }
        }
        Assert-LogAxis $app $plot
        $paletteColors += Assert-ColorMap $app $plot
        $imageName = [string]$plot.id
        Assert-GraphStyle $app $plot $prepared.style
        $widthCm = ([double]$prepared.style.figure.width_mm / 10).ToString("G17",$culture)
        $dpi = [int]$prepared.style.export.raster_dpi
        $layoutName='_layout-'+$imageName
        if (-not $app.Execute("expGraph type:=png filename:=$quote$layoutName$quote path:=$quote$outputPath$quote overwrite:=rename sysopts:=0 tr.Margin:=2 tr1.width:=$widthCm tr1.unit:=1 tr2.PNG.dotsperinch:=$dpi;")) { throw 'Layout export failed' }
        $layoutPath=Join-Path $outputPath ($layoutName+'.png')
        $alignment=Align-LabelGap $app $plot $layoutPath
        $export = "expGraph type:=png filename:=$quote$imageName$quote path:=$quote$outputPath$quote overwrite:=rename sysopts:=0 tr.Margin:=2 tr1.width:=$widthCm tr1.unit:=1 tr2.PNG.dotsperinch:=$dpi;"
        if (-not $app.Execute($export)) { throw "PNG export failed" }
        $imagePath = Join-Path $outputPath ($imageName + ".png")
        if (-not (Test-Path -LiteralPath $imagePath -PathType Leaf) -or (Get-Item -LiteralPath $imagePath).Length -lt 1000) {
            throw "Native PNG missing or empty"
        }
        $finalGap=Measure-LabelGap $app $imagePath
        if ($alignment.status -eq 'ALIGNED_FROM_RENDER' -and [Math]::Abs($finalGap[0]-$finalGap[1]) -gt 3) { throw "Axis label gaps differ: $imageName y=$($finalGap[0]) x=$($finalGap[1])" }
        $alignment.final_y_px=$finalGap[0]; $alignment.final_x_px=$finalGap[1]
        Write-Json (Join-Path $outputPath ($imageName+'-layout.json')) $alignment
    }
    $projectPath = Join-Path $outputPath "figures.opju"
    if (-not $app.Save($projectPath) -or -not (Test-Path -LiteralPath $projectPath -PathType Leaf)) { throw "OPJU save failed" }
    if (-not $app.NewProject() -or -not $app.Load($projectPath)) { throw "Saved OPJU could not reopen" }
    $reopenedCells = 0
    foreach ($item in $verifiedSheets) { $reopenedCells += Assert-Worksheet $app $item.sheet $item.matrix }
    $graphs = Get-ComProperty $app "GraphPages"
    try {
        $graphCount = [int](Get-ComProperty $graphs "Count")
        if ($graphCount -ne @($prepared.plots).Count) { throw "Saved graph count differs: actual=$graphCount expected=$(@($prepared.plots).Count)" }
        foreach ($plot in $prepared.plots) {
            if (-not $app.Execute("win -a $($plot.graph_id);")) { throw "Saved graph page missing" }
            Assert-LogAxis $app $plot
            [void](Assert-ColorMap $app $plot)
            Assert-GraphStyle $app $plot $prepared.style
            $imageName = [string]$plot.id + "-reopened"
            if (-not $app.Execute("expGraph type:=png filename:=$quote$imageName$quote path:=$quote$outputPath$quote overwrite:=rename sysopts:=0 tr.Margin:=2 tr1.width:=$widthCm tr1.unit:=1 tr2.PNG.dotsperinch:=$dpi;")) {
                throw "Reopened graph export failed"
            }
            if (-not (Test-Path -LiteralPath (Join-Path $outputPath ($imageName + ".png")) -PathType Leaf)) {
                throw "Reopened graph PNG missing"
            }
        }
    } finally { if ($null -ne $graphs) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($graphs) } }
    # Origin holds the saved project open exclusively. Close this owned COM
    # session before hashing the final on-disk bytes.
    [void]$app.Exit()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)
    $app = $null
    $outputs = @(Get-ChildItem -LiteralPath $outputPath -File | Where-Object {$_.Extension -in @(".png",".opju")} | ForEach-Object {
        @{name=$_.Name; bytes=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    })
    Write-Json (Join-Path $outputPath "native-receipt.json") @{
        schema_version=1; status="NATIVE_EXPORTED"; origin_version=$version; executable_sha256=$executableHash;
        runner_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant();
        plan_sha256=(Get-FileHash -LiteralPath $planPath -Algorithm SHA256).Hash.ToLowerInvariant();
        numeric_readback_cells=$numericCells; numeric_readback="PASS"; outputs=$outputs;
        project_reopen="PASS"; reopened_readback_cells=$reopenedCells; reopened_graph_count=@($prepared.plots).Count;
        reopened_exports=@($prepared.plots).Count;
        style_readback="PASS_BEFORE_AND_AFTER_REOPEN"; native_log_axes=@($prepared.plots | Where-Object {$_.metadata.x_scale -eq 'log10'}).Count;
        palette_readback='PASS_BEFORE_AND_AFTER_REOPEN';palette_colors_verified=$paletteColors;
        font=$fontName; raster_dpi=$dpi; requested_width_mm=[double]$prepared.style.figure.width_mm;
        visual_review="REQUIRED"; scientific_validation="NOT_CLAIMED"
    }
    Write-Output "NATIVE_EXPORTED; numerical read-back passed; inspect the actual PNGs."
} catch {
    Write-Json (Join-Path $outputPath "FAILED.json") @{status="FAILED"; message=$_.Exception.Message; last_command=$script:lastCommand; script_stack=$_.ScriptStackTrace; native_acceptance="FAILED"}
    throw
} finally {
    if ($null -ne $app) {
        try { [void]$app.Exit() } catch {}
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)
    }
    Remove-OwnedAssets $outputPath
}
