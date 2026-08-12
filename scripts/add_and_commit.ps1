# Batch-add untracked files and push
Get-Process -Name git -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
if (Test-Path .git\index.lock) { Remove-Item -Force .git\index.lock -ErrorAction SilentlyContinue }

git ls-files -o --exclude-standard > untracked_list.txt
$u = @()
if (Test-Path 'untracked_list.txt') { $u = Get-Content -LiteralPath 'untracked_list.txt' }
foreach ($line in $u) {
    if ($line -ne '') {
        git add -f -- "$line" 2>> git_add_errors.log
    }
}

git status --porcelain > git_staged_status.txt
if (Test-Path git_staged_status.txt) {
    $staged = Get-Content git_staged_status.txt | Where-Object { $_ -match '^[AM]' }
    if ($staged) {
        git commit -m 'Add all workspace files (batched)' --no-gpg-sign > git_batched_commit.log 2>&1
        git push origin main > git_batched_push.log 2>&1
    } else {
        Write-Output 'NO_STAGED_CHANGES'
    }
} else {
    Write-Output 'NO_STAGED_FILE'
}

git log -1 --oneline > git_last_commit.log 2>&1
Write-Output 'SCRIPT_DONE'
