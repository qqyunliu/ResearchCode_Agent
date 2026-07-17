# Measure repository statistics for evaluation
param(
    [string]$RepoPath = "F:\LIUQINGYUN\ResearchCode_Agent\evaluation\workspaces\ruoyi-vue"
)

$ErrorActionPreference = "Stop"

# Count files by extension (excluding .git, target, node_modules)
$excludeDirs = @('.git', 'target', 'node_modules', '.svn')

function Count-Files {
    param([string[]]$Extensions)
    $count = 0
    foreach ($ext in $Extensions) {
        $files = Get-ChildItem -Path $RepoPath -Recurse -File -Filter $ext -ErrorAction SilentlyContinue |
            Where-Object {
                $path = $_.FullName
                $skip = $false
                foreach ($dir in $excludeDirs) {
                    if ($path -match [regex]::Escape("\$dir\")) { $skip = $true; break }
                }
                -not $skip
            }
        $count += ($files | Measure-Object).Count
    }
    return $count
}

function Count-Lines {
    param([string[]]$Extensions)
    $totalLines = 0
    foreach ($ext in $Extensions) {
        $files = Get-ChildItem -Path $RepoPath -Recurse -File -Filter $ext -ErrorAction SilentlyContinue |
            Where-Object {
                $path = $_.FullName
                $skip = $false
                foreach ($dir in $excludeDirs) {
                    if ($path -match [regex]::Escape("\$dir\")) { $skip = $true; break }
                }
                -not $skip
            }
        foreach ($file in $files) {
            try {
                $lines = (Get-Content $file.FullName -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
                $totalLines += $lines
            } catch {
                # Skip binary/unreadable files
            }
        }
    }
    return $totalLines
}

$javaCount = Count-Files -Extensions @("*.java")
$vueCount = Count-Files -Extensions @("*.vue")
$jsCount = Count-Files -Extensions @("*.js", "*.jsx")
$tsCount = Count-Files -Extensions @("*.ts", "*.tsx")
$pyCount = Count-Files -Extensions @("*.py")
$xmlCount = Count-Files -Extensions @("*.xml")
$ymlCount = Count-Files -Extensions @("*.yml", "*.yaml")
$jsonCount = Count-Files -Extensions @("*.json")
$sqlCount = Count-Files -Extensions @("*.sql")
$htmlCount = Count-Files -Extensions @("*.html")
$cssCount = Count-Files -Extensions @("*.css")

$totalSupported = $javaCount + $vueCount + $jsCount + $tsCount + $pyCount

# Line counts for supported languages
$javaLines = Count-Lines -Extensions @("*.java")
$vueLines = Count-Lines -Extensions @("*.vue")
$jsLines = Count-Lines -Extensions @("*.js", "*.jsx")
$tsLines = Count-Lines -Extensions @("*.ts", "*.tsx")
$pyLines = Count-Lines -Extensions @("*.py")
$totalLines = $javaLines + $vueLines + $jsLines + $tsLines + $pyLines

# Git info
Push-Location $RepoPath
$commitSha = git rev-parse HEAD 2>$null
$branch = git rev-parse --abbrev-ref HEAD 2>$null
$remoteUrl = git remote get-url origin 2>$null
Pop-Location

$result = @{
    repo_id = "ruoyi-vue"
    commit_sha = $commitSha
    branch = $branch
    remote_url = $remoteUrl
    license = "MIT"
    clone_time = (Get-Date -Format "o")
    file_counts = @{
        java = $javaCount
        vue = $vueCount
        js = $jsCount
        ts = $tsCount
        python = $pyCount
        xml = $xmlCount
        yml = $ymlCount
        json = $jsonCount
        sql = $sqlCount
        html = $htmlCount
        css = $cssCount
        total_supported = $totalSupported
    }
    line_counts = @{
        java = $javaLines
        vue = $vueLines
        js = $jsLines
        ts = $tsLines
        python = $pyLines
        total = $totalLines
    }
}

$result | ConvertTo-Json -Depth 5
