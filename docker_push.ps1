$Image = "transit-archiver"
$Registry = "docker.lan:5000"
$VersionFile = "docker.version"

$current = Get-Content $VersionFile
$major, $minor = $current -split '\.'
$next = "$major.$([int]$minor + 1)"

$confirm = Read-Host "Current version is $current, build and push version ${next}? [y/N]"
if ($confirm -notmatch '^[Yy]') {
    Write-Host "Cancelled by user."
    exit
}

Write-Host "Building ${Registry}/${Image}:${next}..."
docker build -t "${Registry}/${Image}:${next}" -t "${Registry}/${Image}:latest" ./
if ($LASTEXITCODE -ne 0) { throw "Docker build failed!" }

Write-Host "Pushing ${Registry}/${Image}:${next}..."
docker push "${Registry}/${Image}:${next}"
if ($LASTEXITCODE -ne 0) { throw "Docker push failed!" }

Write-Host "Pushing ${Registry}/${Image}:latest..."
docker push "${Registry}/${Image}:latest"
if ($LASTEXITCODE -ne 0) { throw "Docker push failed!" }

Set-Content -Path $VersionFile -Value $next -NoNewline -Encoding utf8
Write-Host "Done."