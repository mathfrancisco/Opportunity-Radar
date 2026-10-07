param(
  [string]$Chrome = 'C:\Users\mathf\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe',
  [string]$BaseUrl = 'http://127.0.0.1:54154'
)

$ErrorActionPreference = 'Stop'
$output = Join-Path $PSScriptRoot 'screenshots'
New-Item -ItemType Directory -Force -Path $output | Out-Null

$pages = 'inbox', 'detail', 'pipeline', 'overview'
$viewports = @(
  @{ Name = '1440'; Size = '1440,1100' },
  @{ Name = '768'; Size = '768,1100' },
  @{ Name = '360'; Size = '360,900' }
)

foreach ($page in $pages) {
  foreach ($viewport in $viewports) {
    $file = Join-Path $output "$page-$($viewport.Name).png"
    & $Chrome --headless --disable-gpu --hide-scrollbars "--window-size=$($viewport.Size)" "--screenshot=$file" "$BaseUrl/$page.html"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $file)) { throw "Capture failed: $page / $($viewport.Name)" }
    Write-Output "$page-$($viewport.Name): $((Get-Item $file).Length) bytes"
  }
}
