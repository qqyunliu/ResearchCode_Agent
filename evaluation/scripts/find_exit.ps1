$content = Get-Content 'F:\LIUQINGYUN\ResearchCode_Agent\evaluation\scripts\validate_dataset.py'
for ($i = 0; $i -lt $content.Count; $i++) {
    if ($content[$i] -match 'sys\.exit|total_error|return_code') {
        Write-Host "$($i+1): $($content[$i].Trim())"
    }
}
