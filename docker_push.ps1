$Image = "transit-archiver"
$Registry = "docker.lan:5000"
$VersionFile = "docker.version"

$current = Get-Content $VersionFile
$major, $minor = $current -split '\.'
$next = "$major.$([int]$minor + 1)"

Write-Host "Building ${Image}:${Next}"
docker build -t "${Image}:${Next}" -t "${Registry}/${Image}:latest" ./
if ($LASTEXITCODE -ne 0) { throw "docker build failed" }

Write-Host "Pushing ${Registry}/${Image}:latest"
docker push "${Registry}/${Image}:latest"
if ($LASTEXITCODE -ne 0) { throw "docker push failed" }

Set-Content -Path $VersionFile -Value $next -NoNewline -Encoding utf8
Write-Host "Done"