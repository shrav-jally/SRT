# Add untracked files in batches to avoid long single git operations
param(
    [int]$BatchSize = 100
)

Get-Process -Name git -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
if (Test-Path .git\index.lock) { Remove-Item -Force .git\index.lock -ErrorAction SilentlyContinue }

git ls-files -o --exclude-standard > untracked_list.txt
if (-not (Test-Path 'untracked_list.txt')) { Write-Output 'NO_UNTRACKED' ; exit }
$u = Get-Content -LiteralPath 'untracked_list.txt'
$total = $u.Count
if ($total -eq 0) { Write-Output 'NO_UNTRACKED' ; exit }

$batchIndex = 0
for ($i = 0; $i -lt $total; $i += $BatchSize) {
    $batchIndex++
    $end = [math]::Min($i + $BatchSize - 1, $total - 1)
    $batch = $u[$i..$end]
    Write-Output ("Processing batch {0}: items {1}-{2}" -f $batchIndex, ($i+1), ($end+1))

    # Ensure no git processes and remove stale lock
    Get-Process -Name git -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
    if (Test-Path .git\index.lock) { Remove-Item -Force .git\index.lock -ErrorAction SilentlyContinue }

    # Run a single git add for the batch
    try {
        git add -f -- @($batch) 2>> git_add_errors.log
    } catch {
        Write-Output "git add failed on batch $batchIndex"
        Add-Content git_add_errors.log "Batch $batchIndex git add exception: $_"
        continue
    }

    # Check staged
    git status --porcelain > git_staged_status.txt
    $staged = Get-Content git_staged_status.txt | Where-Object { $_ -match '^[AM]' }
    if ($staged) {
        $msg = "Add workspace files (batch $batchIndex)"
        git commit -m $msg --no-gpg-sign > "git_commit_batch_${batchIndex}.log" 2>&1
        git push origin main > "git_push_batch_${batchIndex}.log" 2>&1
    } else {
        Write-Output "No staged changes for batch $batchIndex"
    }
}

git log -1 --oneline > git_last_commit.log 2>&1
Write-Output 'BATCH_SCRIPT_DONE'
