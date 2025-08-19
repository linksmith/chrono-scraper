# System Utilities & Commands (Linux)

## File System Operations
```bash
# Directory navigation
ls -la                    # List files with details
ls -lh                    # Human-readable file sizes
cd /path/to/directory     # Change directory
pwd                       # Print working directory
find . -name "*.py"       # Find Python files recursively
find . -type f -name "test_*"  # Find test files

# File operations
cat filename.txt          # Display file contents
head -20 filename.txt     # First 20 lines
tail -f logs/app.log      # Follow log file
less filename.txt         # Paginated file viewer
grep -r "pattern" src/    # Recursive text search
grep -i "error" logs/     # Case-insensitive search
```

## Text Processing
```bash
# Search and filter
grep -n "pattern" file.txt     # Show line numbers
grep -A 5 -B 5 "error" log     # Show context lines
awk '{print $1}' file.txt      # Print first column
sed 's/old/new/g' file.txt     # Replace text
cut -d',' -f1,3 file.csv       # Extract CSV columns
sort file.txt | uniq           # Sort and remove duplicates
```

## Process Management
```bash
# Process monitoring
ps aux                    # List all processes
ps aux | grep python      # Find Python processes
top                       # Real-time process monitor
htop                      # Enhanced process monitor
kill -9 <pid>            # Force kill process
killall python          # Kill all Python processes
jobs                     # List background jobs
fg                       # Bring job to foreground
bg                       # Send job to background
```

## Network & System Info
```bash
# Network operations
netstat -tulpn           # Show listening ports
ss -tulpn                # Modern netstat alternative
lsof -i :8000           # Show what's using port 8000
curl -I http://localhost:8000  # Check HTTP headers
ping google.com          # Test connectivity
wget https://example.com # Download file

# System information
uname -a                 # System information
df -h                    # Disk usage
du -sh *                 # Directory sizes
free -h                  # Memory usage
uptime                   # System uptime
whoami                   # Current user
id                       # User ID and groups
```

## Archive & Compression
```bash
# Create archives
tar -czf backup.tar.gz folder/     # Create compressed archive
zip -r archive.zip folder/         # Create ZIP archive

# Extract archives
tar -xzf backup.tar.gz             # Extract tar.gz
unzip archive.zip                  # Extract ZIP
tar -tf backup.tar.gz              # List archive contents
```

## File Permissions & Ownership
```bash
# Permissions
chmod 755 script.sh      # Make executable
chmod -R 644 files/      # Recursive permission change
chown user:group file    # Change ownership
ls -la                   # View permissions

# Permission notation
# 755 = rwxr-xr-x (owner: rwx, group: r-x, others: r-x)
# 644 = rw-r--r-- (owner: rw, group: r, others: r)
```

## Environment & Variables
```bash
# Environment variables
env                      # Show all environment variables
echo $PATH              # Show PATH variable
export VAR=value        # Set environment variable
unset VAR               # Remove environment variable
printenv | grep PYTHON # Show Python-related vars

# Shell history
history                 # Show command history
!123                    # Run command #123 from history
!!                      # Run last command
ctrl+r                  # Reverse search history
```

## Log Analysis
```bash
# Log monitoring
tail -f /var/log/app.log          # Follow log file
grep "ERROR" /var/log/app.log     # Find errors
journalctl -u service_name        # System service logs
journalctl -f                     # Follow system logs
less +F /var/log/app.log          # Follow with less

# Log rotation and cleanup
find /var/log -name "*.log" -mtime +30 -delete  # Delete old logs
logrotate /etc/logrotate.conf     # Rotate logs
```

## Performance Monitoring
```bash
# Resource usage
iostat                   # I/O statistics
vmstat                   # Virtual memory stats
sar                      # System activity reporter
tcpdump                  # Network packet capture
strace -p <pid>          # Trace system calls
```

## Git Operations (Project Context)
```bash
# Repository operations
git status               # Check working directory status
git log --oneline        # Compact commit history
git diff                 # Show unstaged changes
git diff --staged        # Show staged changes
git branch -a            # Show all branches
git remote -v            # Show remote repositories

# File operations
git add .                # Stage all changes
git add -u               # Stage modified files only
git commit -m "message"  # Commit with message
git push origin main     # Push to remote
git pull origin main     # Pull from remote
```

## Docker Context Commands
```bash
# Container operations
docker ps                # List running containers
docker ps -a             # List all containers
docker logs container_name  # View container logs
docker exec -it container bash  # Interactive shell
docker inspect container # Detailed container info

# System cleanup
docker system prune      # Clean unused Docker objects
docker volume prune      # Clean unused volumes
docker image prune       # Clean unused images
```

## Useful Aliases (Can be added to ~/.bashrc)
```bash
alias ll='ls -la'
alias la='ls -A'
alias l='ls -CF'
alias grep='grep --color=auto'
alias ..='cd ..'
alias ...='cd ../..'
alias h='history'
alias c='clear'
```