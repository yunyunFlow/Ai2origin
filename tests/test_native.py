"""PowerShell consumer regression without launching Origin or changing COM."""
import base64
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
PS=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
if not PS.is_file():PS=Path('/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe')


@unittest.skipUnless(PS.is_file(),'Windows PowerShell unavailable; native numeric consumer not certified here')
class NativeContractTests(unittest.TestCase):
    def test_categorical_y_title_gap_and_frame_center_without_origin(self):
        path=str(ROOT/'scripts/origin.ps1')
        if os.name!='nt':path=subprocess.check_output(['wslpath','-w',path],text=True).strip()
        code=r'''
$ErrorActionPreference='Stop';$culture=[Globalization.CultureInfo]::InvariantCulture
Add-Type -AssemblyName System.Drawing
$tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile(PATH,[ref]$tokens,[ref]$errors)
foreach($name in @('Measure-LabelGap','Align-LabelGap')) {
 $node=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true);Invoke-Expression $node.Extent.Text
}
$script:values=@{'layer.left'=30;'layer.top'=20;'layer.width'=60;'layer.height'=45;'layer.x.from'=0;'layer.x.to'=1;'AxisTitleY.x'=-.23;'layer.y.from'=1;'layer.y.to'=3;'layer.y.type'=1}
$app=[pscustomobject]@{};$app | Add-Member ScriptMethod LTVar {param($name) return $script:values[$name]}
$app | Add-Member ScriptMethod Execute {param($code) $script:last=$code;return $true}
$file=Join-Path ([IO.Path]::GetTempPath()) ('a2o-axis-'+[Guid]::NewGuid().ToString('N')+'.png')
$b=New-Object Drawing.Bitmap 400,400;$g=[Drawing.Graphics]::FromImage($b)
try {
 $g.Clear([Drawing.Color]::White)
 $g.FillRectangle([Drawing.Brushes]::Black,40,100,10,140)
 $g.FillRectangle([Drawing.Brushes]::Black,140,285,40,10)
 $g.FillRectangle([Drawing.Brushes]::Black,140,330,40,10)
 $b.Save($file,[Drawing.Imaging.ImageFormat]::Png)
 if ((Measure-LabelGap $app $file)[0] -ne -1) {throw 'Numeric ambiguity accepted'}
 $gap=Measure-LabelGap $app $file $true
 if ($gap[0] -ne 70 -or $gap[1] -ne 35 -or $gap[2] -ne 240) {throw 'Categorical pixel gap wrong'}
 $result=Align-LabelGap $app ([pscustomobject]@{metadata=[pscustomobject]@{kind='raincloud';orientation='horizontal'}}) $file
 if (-not $result.categorical_y -or $result.status -ne 'ALIGNED_FROM_RENDER' -or $script:last -notmatch 'AxisTitleY.y=2;') {throw 'Categorical title not aligned/centered'}
 $script:values['layer.y.from']=1e-5;$script:values['layer.y.to']=1e-1;$script:values['layer.y.type']=2
 [void](Align-LabelGap $app ([pscustomobject]@{metadata=[pscustomobject]@{kind='raincloud';orientation='horizontal'}}) $file)
 if ($script:last -notmatch 'AxisTitleY.y=0.001;') {throw 'Log Y midpoint is not geometric'}
 $g.FillRectangle([Drawing.Brushes]::Black,85,100,15,140);$b.Save($file,[Drawing.Imaging.ImageFormat]::Png)
 $gap=Measure-LabelGap $app $file
 if ($gap[0] -ne 35 -or $gap[1] -ne 35) {throw 'Numeric label gap regressed'}
 'PASS_NO_ORIGIN_ACTIVATION'
} finally {$g.Dispose();$b.Dispose();Remove-Item -LiteralPath $file -ErrorAction SilentlyContinue}
'''.replace('PATH',"'"+path.replace("'","''")+"'")
        result=subprocess.run([str(PS),'-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(code.encode('utf-16le')).decode()],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PASS_NO_ORIGIN_ACTIVATION',result.stdout)
    def test_native_font_glyph_coverage_without_origin(self):
        path=str(ROOT/'scripts/origin.ps1')
        if os.name!='nt':path=subprocess.check_output(['wslpath','-w',path],text=True).strip()
        code="""
$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Drawing
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile(PATH,[ref]$tokens,[ref]$errors)
$node=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Assert-FontGlyphs'},$true)
Invoke-Expression $node.Extent.Text
Assert-FontGlyphs 'Arial' @('α β τ Å Ω − θ μ','Current (mA)')
$refused=$false
try {Assert-FontGlyphs 'Arial' @([char]::ConvertFromUtf32(0x10ffff))} catch {$refused=$true}
if (-not $refused) {throw 'Missing native glyph was accepted'}
'PASS_NO_ORIGIN_ACTIVATION'
""".replace('PATH',"'"+path.replace("'","''")+"'")
        result=subprocess.run([str(PS),'-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(code.encode('utf-16le')).decode()],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PASS_NO_ORIGIN_ACTIVATION',result.stdout)
    def test_exact_payload_and_small_number_corruption_refusal(self):
        path=str(ROOT/'scripts/origin.ps1')
        if os.name!='nt':
            # A WSL distro identifies its own actual file. No fixed username,
            # project path or guessed Windows C:\\home mapping is embedded.
            path=subprocess.check_output(['wslpath','-w',path],text=True).strip()
        payload=base64.b64encode(struct.pack('<4d',1e-20,1.2345678901234567,0.,-0.0)).decode()
        plan=json.dumps({'headers':['x','y'],'rows':[[1e-20,1.2345678901234567],[None,-0.0]],'data_f64le':payload})
        code=r'''
$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);$originMissing=-1.23456789e-300
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile(PATH,[ref]$tokens,[ref]$errors)
if ($errors.Count) {throw 'Runner parse failure'}
foreach ($name in @('Get-ExactMatrix','Assert-Worksheet')) {
 $node=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true)
 Invoke-Expression $node.Extent.Text
}
$book=PLAN | ConvertFrom-Json
$expected=Get-ExactMatrix $book
$observed=$expected[0,1]
if ([BitConverter]::DoubleToInt64Bits($observed) -ne [BitConverter]::DoubleToInt64Bits([BitConverter]::ToDouble([Convert]::FromBase64String(PAYLOAD),8))) {throw 'Exact double changed'}
if ($expected[1,0] -ne $originMissing -or $expected[1,1] -ne 0) {throw 'Null/zero confused'}
$script:actual=$expected.Clone()
$app=[pscustomobject]@{}
$app | Add-Member ScriptMethod GetWorksheet {param($s,$r0,$c0,$r1,$c1,$flags) return ,$script:actual}
if ((Assert-Worksheet $app '[Data1]Sheet1' $expected) -ne 4) {throw 'Positive fixture failed'}
foreach ($bad in @(0.0,[double]::NaN,[double]::PositiveInfinity)) {
 $script:actual=$expected.Clone();$script:actual[0,0]=$bad;$refused=$false
 try {[void](Assert-Worksheet $app '[Data1]Sheet1' $expected)} catch {$refused=$true}
 if (-not $refused) {throw 'Corrupted small observation was accepted'}
}
$book.data_f64le='AA==';$refused=$false
try {[void](Get-ExactMatrix $book)} catch {$refused=$true}
if (-not $refused) {throw 'Malformed payload was accepted'}
'PASS_NO_ORIGIN_ACTIVATION'
'''.replace('PATH',"'"+path.replace("'","''")+"'").replace('PLAN',"'"+plan+"'").replace('PAYLOAD',"'"+payload+"'")
        result=subprocess.run([str(PS),'-NoProfile','-NonInteractive','-EncodedCommand',
                               base64.b64encode(code.encode('utf-16le')).decode()],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PASS_NO_ORIGIN_ACTIVATION',result.stdout)


if __name__=='__main__':unittest.main()
