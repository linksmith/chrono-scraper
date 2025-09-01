#!/bin/bash

# Automated performance monitoring and scaling daemon for Chrono Scraper
# Monitors resource usage and automatically applies scaling policies
# Optimized for Hetzner CX32 (8GB RAM, 4 vCPU)
# Usage: ./scripts/auto-scaler.sh [start|stop|status] [options]

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
DAEMON_NAME="chrono-auto-scaler"
PID_FILE="/var/run/${DAEMON_NAME}.pid"
LOG_FILE="/var/log/${DAEMON_NAME}.log"
CONFIG_FILE="/etc/chrono-scraper/auto-scaler.conf"
LOCK_FILE="/tmp/${DAEMON_NAME}.lock"

# Default settings (can be overridden by config file)
MONITORING_INTERVAL=30           # Check every 30 seconds
SCALING_COOLDOWN=300             # Wait 5 minutes between scaling actions
MEMORY_WARNING_THRESHOLD=85      # 85% memory usage warning
MEMORY_CRITICAL_THRESHOLD=92     # 92% memory usage critical
CPU_WARNING_THRESHOLD=80         # 80% CPU usage warning
CPU_CRITICAL_THRESHOLD=90        # 90% CPU usage critical
SCALE_DOWN_AFTER_WARNING_TIME=180 # Scale down after 3 minutes of warning
SCALE_UP_DELAY=60               # Wait 1 minute before scaling up
ENABLE_AGGRESSIVE_SCALING=true   # Allow aggressive scaling in critical situations
ENABLE_EMAIL_ALERTS=false       # Send email alerts (requires mail setup)
EMAIL_TO=""                     # Alert email address
WEBHOOK_URL=""                  # Webhook for external notifications
MAX_SCALE_ACTIONS_PER_HOUR=10   # Prevent scaling storms

# Runtime state
LAST_SCALING_ACTION=0
SCALING_ACTION_COUNT=0
SCALING_ACTION_HOUR=0
CURRENT_PROFILE="unknown"
WARNING_START_TIME=0
CRITICAL_START_TIME=0

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.hetzner-cx32.yml"
MONITOR_SCRIPT="$SCRIPT_DIR/monitor-resources-hetzner.sh"
SCALING_SCRIPT="$SCRIPT_DIR/scale-services.sh"

# Function to load configuration
load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        source "$CONFIG_FILE"
        log_message "INFO" "Configuration loaded from $CONFIG_FILE"
    else
        log_message "INFO" "Using default configuration (no config file found)"
    fi
}

# Function to log messages
log_message() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local log_entry="[$timestamp] [$level] $message"
    
    echo -e "$log_entry" | tee -a "$LOG_FILE"
    
    # Also log to system log
    logger -t "$DAEMON_NAME" "[$level] $message"
}

# Function to send alerts
send_alert() {
    local level="$1"
    local subject="$2"
    local message="$3"
    
    log_message "$level" "$subject: $message"
    
    # Email alerts
    if [[ "$ENABLE_EMAIL_ALERTS" == "true" ]] && [[ -n "$EMAIL_TO" ]]; then
        if command -v mail >/dev/null 2>&1; then
            echo "$message" | mail -s "[Chrono Scraper] $subject" "$EMAIL_TO"
        fi
    fi
    
    # Webhook alerts
    if [[ -n "$WEBHOOK_URL" ]]; then
        local payload="{\"level\":\"$level\",\"subject\":\"$subject\",\"message\":\"$message\",\"timestamp\":\"$(date -Iseconds)\"}"
        curl -X POST -H "Content-Type: application/json" -d "$payload" "$WEBHOOK_URL" >/dev/null 2>&1 || true
    fi
}

# Function to get current resource usage
get_resource_usage() {
    local memory_info=$(free -m | grep "Mem:")
    local used_mem=$(echo $memory_info | awk '{print $3}')
    local total_mem=$(echo $memory_info | awk '{print $2}')
    local memory_percent=$(( (used_mem * 100) / total_mem ))
    
    local load_1min=$(uptime | grep -o 'load average.*' | cut -d' ' -f3 | tr -d ',')
    local cpu_percent=$(echo "$load_1min * 100 / 4" | bc -l | cut -d'.' -f1)  # 4 cores
    
    echo "$memory_percent $cpu_percent"
}

# Function to detect current scaling profile
detect_current_profile() {
    local running_services=$(docker ps --format "{{.Names}}" | grep "^chrono_" | wc -l)
    
    if [[ $running_services -le 3 ]]; then
        echo "minimal"
    elif [[ $running_services -le 5 ]]; then
        echo "essential"
    elif [[ $running_services -le 8 ]]; then
        echo "standard"
    elif [[ $running_services -le 10 ]]; then
        echo "full"
    else
        echo "development"
    fi
}

# Function to check if scaling is allowed
is_scaling_allowed() {
    local current_time=$(date +%s)
    local current_hour=$(date +%H)
    
    # Reset action counter every hour
    if [[ $current_hour -ne $SCALING_ACTION_HOUR ]]; then
        SCALING_ACTION_COUNT=0
        SCALING_ACTION_HOUR=$current_hour
    fi
    
    # Check cooldown period
    if [[ $((current_time - LAST_SCALING_ACTION)) -lt $SCALING_COOLDOWN ]]; then
        log_message "DEBUG" "Scaling blocked by cooldown period"
        return 1
    fi
    
    # Check maximum actions per hour
    if [[ $SCALING_ACTION_COUNT -ge $MAX_SCALE_ACTIONS_PER_HOUR ]]; then
        log_message "WARN" "Maximum scaling actions per hour reached ($SCALING_ACTION_COUNT/$MAX_SCALE_ACTIONS_PER_HOUR)"
        return 1
    fi
    
    return 0
}

# Function to record scaling action
record_scaling_action() {
    LAST_SCALING_ACTION=$(date +%s)
    SCALING_ACTION_COUNT=$((SCALING_ACTION_COUNT + 1))
    log_message "INFO" "Scaling action recorded ($SCALING_ACTION_COUNT/$MAX_SCALE_ACTIONS_PER_HOUR this hour)"
}

# Function to execute scaling action
execute_scaling_action() {
    local action="$1"
    local target="$2"
    local reason="$3"
    
    if ! is_scaling_allowed; then
        log_message "WARN" "Scaling action blocked: $action $target ($reason)"
        return 1
    fi
    
    log_message "INFO" "Executing scaling action: $action $target ($reason)"
    
    if [[ -f "$SCALING_SCRIPT" ]]; then
        if "$SCALING_SCRIPT" "$action" "$target" --force --compose-file "$COMPOSE_FILE"; then
            record_scaling_action
            CURRENT_PROFILE=$(detect_current_profile)
            send_alert "INFO" "Scaling Action Successful" "Action: $action $target, Reason: $reason, New Profile: $CURRENT_PROFILE"
            return 0
        else
            send_alert "ERROR" "Scaling Action Failed" "Failed to execute: $action $target, Reason: $reason"
            return 1
        fi
    else
        log_message "ERROR" "Scaling script not found: $SCALING_SCRIPT"
        return 1
    fi
}

# Function to analyze resource usage and determine scaling action
analyze_and_scale() {
    local usage=($(get_resource_usage))
    local memory_percent=${usage[0]}
    local cpu_percent=${usage[1]%.*}  # Remove decimal
    local current_time=$(date +%s)
    
    log_message "DEBUG" "Current usage: Memory ${memory_percent}%, CPU ${cpu_percent}%"
    
    # Critical resource usage - immediate action
    if [[ $memory_percent -ge $MEMORY_CRITICAL_THRESHOLD ]] || [[ $cpu_percent -ge $CPU_CRITICAL_THRESHOLD ]]; then
        if [[ $CRITICAL_START_TIME -eq 0 ]]; then
            CRITICAL_START_TIME=$current_time
            send_alert "CRITICAL" "Critical Resource Usage Detected" "Memory: ${memory_percent}%, CPU: ${cpu_percent}%"
        fi
        
        # Immediate aggressive scaling for critical situations
        case "$CURRENT_PROFILE" in
            "development"|"full")
                execute_scaling_action "scale-down" "utilities" "Critical resource usage: Memory ${memory_percent}%, CPU ${cpu_percent}%"
                ;;
            "standard")
                execute_scaling_action "scale-down" "browser" "Critical resource usage: Memory ${memory_percent}%, CPU ${cpu_percent}%"
                ;;
            "essential")
                execute_scaling_action "scale-down" "workers" "Critical resource usage: Memory ${memory_percent}%, CPU ${cpu_percent}%"
                ;;
            *)
                if [[ "$ENABLE_AGGRESSIVE_SCALING" == "true" ]]; then
                    execute_scaling_action "emergency-stop" "" "Critical resource usage: Memory ${memory_percent}%, CPU ${cpu_percent}%"
                fi
                ;;
        esac
        
    # Warning level resource usage - gradual scaling
    elif [[ $memory_percent -ge $MEMORY_WARNING_THRESHOLD ]] || [[ $cpu_percent -ge $CPU_WARNING_THRESHOLD ]]; then
        if [[ $WARNING_START_TIME -eq 0 ]]; then
            WARNING_START_TIME=$current_time
            send_alert "WARN" "High Resource Usage Detected" "Memory: ${memory_percent}%, CPU: ${cpu_percent}%"
        elif [[ $((current_time - WARNING_START_TIME)) -ge $SCALE_DOWN_AFTER_WARNING_TIME ]]; then
            # Scale down after sustained warning level usage
            case "$CURRENT_PROFILE" in
                "development"|"full")
                    execute_scaling_action "scale-down" "utilities" "Sustained high resource usage: Memory ${memory_percent}%, CPU ${cpu_percent}%"
                    ;;
                "standard")
                    execute_scaling_action "scale-down" "frontend" "Sustained high resource usage: Memory ${memory_percent}%, CPU ${cpu_percent}%"
                    ;;
            esac
            WARNING_START_TIME=$current_time  # Reset timer
        fi
        
        # Clear critical timer if we're back to warning level
        CRITICAL_START_TIME=0
        
    # Normal resource usage - consider scaling up
    else
        # Reset warning and critical timers
        WARNING_START_TIME=0
        CRITICAL_START_TIME=0
        
        # Consider scaling up if resources are very low and we're in a minimal profile
        if [[ $memory_percent -lt 60 ]] && [[ $cpu_percent -lt 50 ]]; then
            case "$CURRENT_PROFILE" in
                "minimal")
                    # Wait before scaling up to ensure stability
                    sleep "$SCALE_UP_DELAY"
                    local new_usage=($(get_resource_usage))
                    if [[ ${new_usage[0]} -lt 60 ]]; then
                        execute_scaling_action "scale-up" "essential" "Low resource usage, scaling up: Memory ${memory_percent}%, CPU ${cpu_percent}%"
                    fi
                    ;;
                "essential")
                    if [[ $memory_percent -lt 50 ]] && [[ $cpu_percent -lt 40 ]]; then
                        sleep "$SCALE_UP_DELAY"
                        local new_usage=($(get_resource_usage))
                        if [[ ${new_usage[0]} -lt 50 ]]; then
                            execute_scaling_action "scale-up" "standard" "Very low resource usage, scaling up: Memory ${memory_percent}%, CPU ${cpu_percent}%"
                        fi
                    fi
                    ;;
            esac
        fi
    fi
}

# Function to perform health checks
perform_health_checks() {
    local unhealthy_services=()
    
    # Check critical services
    local critical_services=("postgres" "redis" "backend")
    for service in "${critical_services[@]}"; do
        local container_name="chrono_$(echo $service | sed 's/-/_/g')"
        if ! docker ps --format "{{.Names}}" | grep -q "^${container_name}$"; then
            unhealthy_services+=("$service (stopped)")
        else
            local health=$(docker inspect --format="{{.State.Health.Status}}" "$container_name" 2>/dev/null || echo "unknown")
            if [[ "$health" == "unhealthy" ]]; then
                unhealthy_services+=("$service (unhealthy)")
            fi
        fi
    done
    
    if [[ ${#unhealthy_services[@]} -gt 0 ]]; then
        send_alert "ERROR" "Critical Services Unhealthy" "Unhealthy services: ${unhealthy_services[*]}"
        
        # Attempt to restart unhealthy services
        for service_info in "${unhealthy_services[@]}"; do
            local service=$(echo "$service_info" | cut -d' ' -f1)
            log_message "INFO" "Attempting to restart unhealthy service: $service"
            docker compose -f "$COMPOSE_FILE" restart "$service" || true
        done
    fi
}

# Function to cleanup old logs
cleanup_logs() {
    # Keep only last 7 days of logs
    find "$(dirname "$LOG_FILE")" -name "${DAEMON_NAME}*.log" -mtime +7 -delete 2>/dev/null || true
    
    # Rotate current log if it's too large (>10MB)
    if [[ -f "$LOG_FILE" ]] && [[ $(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE") -gt 10485760 ]]; then
        mv "$LOG_FILE" "${LOG_FILE}.$(date +%Y%m%d-%H%M%S)"
        touch "$LOG_FILE"
        log_message "INFO" "Log file rotated due to size"
    fi
}

# Function to start the daemon
start_daemon() {
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Daemon is already running with PID $(cat "$PID_FILE")"
        exit 1
    fi
    
    # Create necessary directories
    mkdir -p "$(dirname "$PID_FILE")" "$(dirname "$LOG_FILE")"
    
    # Load configuration
    load_config
    
    # Create lock file
    exec 200>"$LOCK_FILE"
    if ! flock -n 200; then
        echo "Another instance is already running"
        exit 1
    fi
    
    # Start daemon
    echo "Starting $DAEMON_NAME..."
    log_message "INFO" "Starting auto-scaler daemon"
    
    # Detect current profile
    CURRENT_PROFILE=$(detect_current_profile)
    log_message "INFO" "Initial profile detected: $CURRENT_PROFILE"
    
    # Write PID file
    echo $$ > "$PID_FILE"
    
    # Main monitoring loop
    while true; do
        # Perform health checks every 5 minutes
        if [[ $(($(date +%s) % 300)) -eq 0 ]]; then
            perform_health_checks
            cleanup_logs
        fi
        
        # Analyze and scale
        analyze_and_scale
        
        # Sleep for monitoring interval
        sleep "$MONITORING_INTERVAL"
    done
}

# Function to stop the daemon
stop_daemon() {
    if [[ -f "$PID_FILE" ]]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "Stopping $DAEMON_NAME (PID: $pid)..."
            kill "$pid"
            
            # Wait for graceful shutdown
            local count=0
            while kill -0 "$pid" 2>/dev/null && [[ $count -lt 30 ]]; do
                sleep 1
                ((count++))
            done
            
            if kill -0 "$pid" 2>/dev/null; then
                echo "Force killing daemon..."
                kill -9 "$pid"
            fi
            
            rm -f "$PID_FILE"
            echo "Daemon stopped"
            log_message "INFO" "Auto-scaler daemon stopped"
        else
            echo "Daemon not running (PID file exists but process not found)"
            rm -f "$PID_FILE"
        fi
    else
        echo "Daemon not running (no PID file found)"
    fi
    
    # Remove lock file
    rm -f "$LOCK_FILE"
}

# Function to show daemon status
show_status() {
    if [[ -f "$PID_FILE" ]]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "Daemon is running (PID: $pid)"
            
            # Show recent log entries
            echo ""
            echo "Recent log entries:"
            tail -10 "$LOG_FILE" 2>/dev/null || echo "No log file found"
            
            # Show current resource usage
            echo ""
            echo "Current resource usage:"
            local usage=($(get_resource_usage))
            echo "Memory: ${usage[0]}% (Warning: ${MEMORY_WARNING_THRESHOLD}%, Critical: ${MEMORY_CRITICAL_THRESHOLD}%)"
            echo "CPU: ${usage[1]}% (Warning: ${CPU_WARNING_THRESHOLD}%, Critical: ${CPU_CRITICAL_THRESHOLD}%)"
            echo "Current profile: $(detect_current_profile)"
            
            exit 0
        else
            echo "Daemon not running (stale PID file found)"
            rm -f "$PID_FILE"
            exit 1
        fi
    else
        echo "Daemon not running"
        exit 1
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 {start|stop|restart|status|test|config} [options]"
    echo ""
    echo "Commands:"
    echo "  start      Start the auto-scaling daemon"
    echo "  stop       Stop the auto-scaling daemon"
    echo "  restart    Restart the auto-scaling daemon"
    echo "  status     Show daemon status and recent activity"
    echo "  test       Run a single monitoring cycle (no scaling)"
    echo "  config     Show current configuration"
    echo ""
    echo "Options:"
    echo "  --config FILE    Use custom configuration file"
    echo "  --dry-run        Show what would be done without executing"
    echo "  --verbose        Enable verbose logging"
    echo ""
    echo "Configuration file: $CONFIG_FILE"
    echo "Log file: $LOG_FILE"
    echo "PID file: $PID_FILE"
    exit 0
}

# Parse command line arguments
ACTION=""
CUSTOM_CONFIG=""
DRY_RUN=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        start|stop|restart|status|test|config)
            ACTION="$1"
            shift
            ;;
        --config)
            CUSTOM_CONFIG="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            show_usage
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            ;;
    esac
done

# Override config file if specified
if [[ -n "$CUSTOM_CONFIG" ]]; then
    CONFIG_FILE="$CUSTOM_CONFIG"
fi

# Validate required files
if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "Error: Docker Compose file not found: $COMPOSE_FILE"
    exit 1
fi

# Execute action
case "$ACTION" in
    "start")
        # Check if we should daemonize
        if [[ -t 1 ]]; then
            # Running in terminal, daemonize
            nohup "$0" start --config "$CONFIG_FILE" </dev/null >/dev/null 2>&1 &
            echo "Daemon starting in background..."
        else
            # Already daemonized, run main loop
            start_daemon
        fi
        ;;
    "stop")
        stop_daemon
        ;;
    "restart")
        stop_daemon
        sleep 2
        "$0" start --config "$CONFIG_FILE"
        ;;
    "status")
        show_status
        ;;
    "test")
        load_config
        echo "Running single monitoring cycle..."
        CURRENT_PROFILE=$(detect_current_profile)
        echo "Current profile: $CURRENT_PROFILE"
        analyze_and_scale
        echo "Test completed"
        ;;
    "config")
        load_config
        echo "Current configuration:"
        echo "  Monitoring interval: ${MONITORING_INTERVAL}s"
        echo "  Scaling cooldown: ${SCALING_COOLDOWN}s"
        echo "  Memory warning threshold: ${MEMORY_WARNING_THRESHOLD}%"
        echo "  Memory critical threshold: ${MEMORY_CRITICAL_THRESHOLD}%"
        echo "  CPU warning threshold: ${CPU_WARNING_THRESHOLD}%"
        echo "  CPU critical threshold: ${CPU_CRITICAL_THRESHOLD}%"
        echo "  Aggressive scaling: $ENABLE_AGGRESSIVE_SCALING"
        echo "  Email alerts: $ENABLE_EMAIL_ALERTS"
        echo "  Max scaling actions per hour: $MAX_SCALE_ACTIONS_PER_HOUR"
        ;;
    *)
        if [[ -z "$ACTION" ]]; then
            echo "Error: No action specified"
        else
            echo "Error: Unknown action: $ACTION"
        fi
        show_usage
        ;;
esac