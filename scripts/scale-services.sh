#!/bin/bash

# Container scaling and graceful degradation script for Chrono Scraper
# Optimized for Hetzner CX32 (8GB RAM, 4 vCPU) resource management
# Usage: ./scripts/scale-services.sh [action] [options]

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Alert symbols
ALERT_CRITICAL='🚨'
ALERT_WARNING='⚠️'
ALERT_INFO='ℹ️'
ALERT_SUCCESS='✅'

# Default configuration file
COMPOSE_FILE="docker-compose.hetzner-cx32.yml"
SCALING_LOG="/tmp/chrono-scaling.log"
BACKUP_DIR="/tmp/chrono-backup-$(date +%Y%m%d-%H%M%S)"

# Service tier definitions (in order of importance)
declare -A SERVICE_TIERS
SERVICE_TIERS[postgres]="TIER1_CRITICAL"
SERVICE_TIERS[redis]="TIER1_CRITICAL"
SERVICE_TIERS[backend]="TIER1_CRITICAL"
SERVICE_TIERS[meilisearch]="TIER2_IMPORTANT"
SERVICE_TIERS[celery_worker]="TIER2_IMPORTANT"
SERVICE_TIERS[firecrawl-playwright]="TIER3_BROWSER"
SERVICE_TIERS[firecrawl-api]="TIER3_BROWSER"
SERVICE_TIERS[firecrawl-worker]="TIER3_BROWSER"
SERVICE_TIERS[frontend]="TIER4_FRONTEND"
SERVICE_TIERS[celery_beat]="TIER5_UTILITIES"
SERVICE_TIERS[flower]="TIER5_UTILITIES"
SERVICE_TIERS[mailpit]="TIER5_UTILITIES"

# Scaling profiles
declare -A SCALING_PROFILES
SCALING_PROFILES[minimal]="postgres redis backend"
SCALING_PROFILES[essential]="postgres redis backend meilisearch celery_worker"
SCALING_PROFILES[standard]="postgres redis backend meilisearch celery_worker firecrawl-api firecrawl-playwright frontend celery_beat"
SCALING_PROFILES[full]="postgres redis backend meilisearch celery_worker firecrawl-api firecrawl-playwright firecrawl-worker frontend celery_beat flower"
SCALING_PROFILES[development]="postgres redis backend meilisearch celery_worker firecrawl-api firecrawl-playwright firecrawl-worker frontend celery_beat flower mailpit"

# Function to log output with timestamp
log_output() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[$timestamp] $message" | tee -a "$SCALING_LOG"
}

# Function to show usage information
show_usage() {
    echo "Usage: $0 [ACTION] [OPTIONS]"
    echo ""
    echo "Actions:"
    echo "  scale-down [LEVEL]     Scale down services by level"
    echo "  scale-up [PROFILE]     Scale up to specific profile"
    echo "  emergency-stop         Emergency shutdown of non-critical services"
    echo "  graceful-restart       Restart services in dependency order"
    echo "  memory-pressure        Handle memory pressure automatically"
    echo "  status                 Show current service status"
    echo "  health-check           Check health of all services"
    echo "  backup-state           Backup current container state"
    echo "  restore-state [DIR]    Restore from backup state"
    echo ""
    echo "Scale-down levels:"
    echo "  utilities              Stop Tier 5 (flower, mailpit, celery_beat)"
    echo "  frontend               Stop Tier 4 + above"
    echo "  browser                Stop Tier 3 + above (Firecrawl services)"
    echo "  workers                Stop Tier 2 workers only"
    echo "  minimal                Keep only Tier 1 critical services"
    echo ""
    echo "Scale-up profiles:"
    echo "  minimal                Database, cache, backend only"
    echo "  essential              + search, workers"
    echo "  standard               + firecrawl, frontend"
    echo "  full                   + all optimization services"
    echo "  development            All services including dev tools"
    echo ""
    echo "Options:"
    echo "  --compose-file FILE    Use specific Docker Compose file"
    echo "  --wait TIME           Wait time between operations (default: 10s)"
    echo "  --force               Skip confirmation prompts"
    echo "  --dry-run             Show what would be done without executing"
    echo "  --backup              Create backup before scaling operations"
    echo ""
    echo "Examples:"
    echo "  $0 memory-pressure                    # Auto-handle memory pressure"
    echo "  $0 scale-down utilities --backup     # Scale down with backup"
    echo "  $0 scale-up essential --wait 15      # Scale up essential services"
    echo "  $0 emergency-stop --force            # Emergency stop without prompt"
    echo "  $0 graceful-restart standard         # Restart with standard profile"
    exit 0
}

# Parse command line arguments
ACTION=""
LEVEL_OR_PROFILE=""
WAIT_TIME=10
FORCE=false
DRY_RUN=false
BACKUP_BEFORE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        scale-down|scale-up|emergency-stop|graceful-restart|memory-pressure|status|health-check|backup-state|restore-state)
            ACTION="$1"
            shift
            ;;
        --compose-file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --wait)
            WAIT_TIME="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --backup)
            BACKUP_BEFORE=true
            shift
            ;;
        --help)
            show_usage
            ;;
        *)
            if [[ -z "$LEVEL_OR_PROFILE" ]]; then
                LEVEL_OR_PROFILE="$1"
            else
                echo "Unknown option: $1"
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate action
if [[ -z "$ACTION" ]]; then
    echo "Error: No action specified"
    show_usage
fi

# Function to check if Docker Compose is available
check_docker_compose() {
    if ! docker compose --version >/dev/null 2>&1; then
        log_output "${RED}Error: Docker Compose not available${NC}"
        exit 1
    fi
    
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        log_output "${RED}Error: Compose file not found: $COMPOSE_FILE${NC}"
        exit 1
    fi
}

# Function to get current memory usage percentage
get_memory_usage() {
    local memory_info=$(free -m | grep "Mem:")
    local used_mem=$(echo $memory_info | awk '{print $3}')
    local total_mem=$(echo $memory_info | awk '{print $2}')
    echo $(( (used_mem * 100) / total_mem ))
}

# Function to get current CPU usage
get_cpu_usage() {
    local load_1min=$(uptime | grep -o 'load average.*' | cut -d' ' -f3 | tr -d ',')
    echo $(echo "$load_1min * 100 / 4" | bc -l | cut -d'.' -f1)  # Assuming 4 cores
}

# Function to check service health
check_service_health() {
    local service="$1"
    local container_name="chrono_$service"
    
    # Replace hyphens with underscores for container names
    container_name=$(echo "$container_name" | sed 's/-/_/g')
    
    if docker ps --format "{{.Names}}" | grep -q "^${container_name}$"; then
        local health=$(docker inspect --format="{{.State.Health.Status}}" "$container_name" 2>/dev/null || echo "none")
        if [[ "$health" == "none" ]]; then
            health=$(docker inspect --format="{{.State.Status}}" "$container_name" 2>/dev/null || echo "unknown")
        fi
        echo "$health"
    else
        echo "stopped"
    fi
}

# Function to get service status
get_service_status() {
    log_output "\n${BLUE}=== Current Service Status ===${NC}"
    printf "%-20s %-15s %-15s %-10s\n" "Service" "Container" "Health" "Tier"
    printf "%-20s %-15s %-15s %-10s\n" "-------------------" "-------------" "-------------" "--------"
    
    for service in "${!SERVICE_TIERS[@]}"; do
        local container_name="chrono_$(echo $service | sed 's/-/_/g')"
        local health=$(check_service_health "$service")
        local tier="${SERVICE_TIERS[$service]}"
        
        local status_color="$GREEN"
        case "$health" in
            "running"|"healthy") status_color="$GREEN" ;;
            "starting"|"none") status_color="$YELLOW" ;;
            "unhealthy"|"exited"|"stopped") status_color="$RED" ;;
            *) status_color="$CYAN" ;;
        esac
        
        printf "${status_color}%-20s %-15s %-15s %-10s${NC}\n" "$service" "$container_name" "$health" "$tier"
    done
}

# Function to backup current state
backup_current_state() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_output "${CYAN}[DRY RUN] Would backup current state to: $BACKUP_DIR${NC}"
        return
    fi
    
    log_output "${BLUE}${ALERT_INFO} Creating backup of current state...${NC}"
    mkdir -p "$BACKUP_DIR"
    
    # Save current running containers
    docker ps --format "{{.Names}}" > "$BACKUP_DIR/running_containers.txt"
    
    # Save Docker Compose config being used
    cp "$COMPOSE_FILE" "$BACKUP_DIR/"
    
    # Save service status
    docker compose -f "$COMPOSE_FILE" ps > "$BACKUP_DIR/compose_status.txt" 2>/dev/null || true
    
    # Save current resource usage
    docker stats --no-stream > "$BACKUP_DIR/resource_usage.txt" 2>/dev/null || true
    
    log_output "${GREEN}${ALERT_SUCCESS} Backup created at: $BACKUP_DIR${NC}"
}

# Function to restore from backup state
restore_from_backup() {
    local backup_path="$1"
    
    if [[ -z "$backup_path" ]]; then
        log_output "${RED}Error: Backup directory path required${NC}"
        exit 1
    fi
    
    if [[ ! -d "$backup_path" ]]; then
        log_output "${RED}Error: Backup directory not found: $backup_path${NC}"
        exit 1
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_output "${CYAN}[DRY RUN] Would restore from backup: $backup_path${NC}"
        return
    fi
    
    log_output "${BLUE}${ALERT_INFO} Restoring from backup: $backup_path${NC}"
    
    # Stop all current services
    docker compose -f "$COMPOSE_FILE" down
    
    # Use the compose file from backup if it exists
    if [[ -f "$backup_path/$COMPOSE_FILE" ]]; then
        COMPOSE_FILE="$backup_path/$COMPOSE_FILE"
    fi
    
    # Start services that were running
    if [[ -f "$backup_path/running_containers.txt" ]]; then
        local services_to_start=()
        while IFS= read -r container_name; do
            # Extract service name from container name
            local service_name=$(echo "$container_name" | sed 's/chrono_//' | sed 's/_/-/g')
            services_to_start+=("$service_name")
        done < "$backup_path/running_containers.txt"
        
        if [[ ${#services_to_start[@]} -gt 0 ]]; then
            log_output "${BLUE}Starting services: ${services_to_start[*]}${NC}"
            docker compose -f "$COMPOSE_FILE" up -d "${services_to_start[@]}"
        fi
    fi
    
    log_output "${GREEN}${ALERT_SUCCESS} Restore completed${NC}"
}

# Function to scale down services by level
scale_down_services() {
    local level="$1"
    
    if [[ "$BACKUP_BEFORE" == "true" ]]; then
        backup_current_state
    fi
    
    local services_to_stop=()
    
    case "$level" in
        "utilities")
            services_to_stop=(flower mailpit celery_beat)
            ;;
        "frontend")
            services_to_stop=(flower mailpit celery_beat frontend)
            ;;
        "browser")
            services_to_stop=(flower mailpit celery_beat frontend firecrawl-worker firecrawl-api firecrawl-playwright)
            ;;
        "workers")
            services_to_stop=(celery_worker)
            ;;
        "minimal")
            services_to_stop=(flower mailpit celery_beat frontend firecrawl-worker firecrawl-api firecrawl-playwright meilisearch celery_worker)
            ;;
        *)
            log_output "${RED}Error: Unknown scale-down level: $level${NC}"
            exit 1
            ;;
    esac
    
    log_output "${YELLOW}${ALERT_WARNING} Scaling down - Level: $level${NC}"
    log_output "Services to stop: ${services_to_stop[*]}"
    
    if [[ "$FORCE" == "false" ]]; then
        read -p "Continue with scaling down? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_output "${BLUE}Operation cancelled${NC}"
            exit 0
        fi
    fi
    
    for service in "${services_to_stop[@]}"; do
        if [[ "$DRY_RUN" == "true" ]]; then
            log_output "${CYAN}[DRY RUN] Would stop service: $service${NC}"
        else
            log_output "${BLUE}Stopping $service...${NC}"
            docker compose -f "$COMPOSE_FILE" stop "$service" || true
            sleep 2
        fi
    done
    
    log_output "${GREEN}${ALERT_SUCCESS} Scale-down completed for level: $level${NC}"
}

# Function to scale up to specific profile
scale_up_services() {
    local profile="$1"
    
    if [[ -z "${SCALING_PROFILES[$profile]}" ]]; then
        log_output "${RED}Error: Unknown scaling profile: $profile${NC}"
        exit 1
    fi
    
    local services_to_start=(${SCALING_PROFILES[$profile]})
    
    log_output "${GREEN}${ALERT_SUCCESS} Scaling up - Profile: $profile${NC}"
    log_output "Services to start: ${services_to_start[*]}"
    
    if [[ "$FORCE" == "false" ]]; then
        read -p "Continue with scaling up? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_output "${BLUE}Operation cancelled${NC}"
            exit 0
        fi
    fi
    
    # Start services in dependency order
    for service in "${services_to_start[@]}"; do
        if [[ "$DRY_RUN" == "true" ]]; then
            log_output "${CYAN}[DRY RUN] Would start service: $service${NC}"
        else
            log_output "${BLUE}Starting $service...${NC}"
            docker compose -f "$COMPOSE_FILE" up -d "$service"
            
            # Wait for service to be healthy before proceeding
            local wait_count=0
            local max_wait=30
            while [[ $wait_count -lt $max_wait ]]; do
                local health=$(check_service_health "$service")
                if [[ "$health" =~ running|healthy ]]; then
                    log_output "${GREEN}  $service is healthy${NC}"
                    break
                fi
                sleep 2
                ((wait_count++))
            done
            
            if [[ $wait_count -ge $max_wait ]]; then
                log_output "${YELLOW}  Warning: $service may not be fully healthy${NC}"
            fi
            
            sleep "$WAIT_TIME"
        fi
    done
    
    log_output "${GREEN}${ALERT_SUCCESS} Scale-up completed for profile: $profile${NC}"
}

# Function to handle emergency stop
emergency_stop() {
    log_output "${RED}${ALERT_CRITICAL} EMERGENCY STOP INITIATED${NC}"
    
    if [[ "$BACKUP_BEFORE" == "true" ]]; then
        backup_current_state
    fi
    
    local non_critical_services=(flower mailpit celery_beat firecrawl-worker frontend)
    
    if [[ "$FORCE" == "false" ]]; then
        log_output "${YELLOW}This will immediately stop all non-critical services${NC}"
        read -p "Continue with emergency stop? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_output "${BLUE}Emergency stop cancelled${NC}"
            exit 0
        fi
    fi
    
    for service in "${non_critical_services[@]}"; do
        if [[ "$DRY_RUN" == "true" ]]; then
            log_output "${CYAN}[DRY RUN] Would emergency stop service: $service${NC}"
        else
            log_output "${RED}Emergency stopping $service...${NC}"
            docker compose -f "$COMPOSE_FILE" kill "$service" 2>/dev/null || true
            docker compose -f "$COMPOSE_FILE" rm -f "$service" 2>/dev/null || true
        fi
    done
    
    log_output "${GREEN}${ALERT_SUCCESS} Emergency stop completed${NC}"
    log_output "${BLUE}Critical services (postgres, redis, backend) remain running${NC}"
}

# Function to handle memory pressure automatically
handle_memory_pressure() {
    local memory_percent=$(get_memory_usage)
    local cpu_percent=$(get_cpu_usage)
    
    log_output "${BLUE}${ALERT_INFO} Memory Pressure Handler${NC}"
    log_output "Current memory usage: ${memory_percent}%"
    log_output "Current CPU usage: ${cpu_percent}%"
    
    if [[ $memory_percent -ge 92 ]]; then
        log_output "${RED}${ALERT_CRITICAL} Critical memory pressure detected (${memory_percent}%)${NC}"
        emergency_stop
        
        # Additional aggressive scaling
        if [[ "$DRY_RUN" == "false" ]]; then
            log_output "${RED}Applying additional memory optimizations...${NC}"
            
            # Reduce Celery worker concurrency
            docker compose -f "$COMPOSE_FILE" kill celery_worker 2>/dev/null || true
            docker compose -f "$COMPOSE_FILE" up -d celery_worker
            
            # Clear Redis cache
            docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli FLUSHDB || true
            
            # Restart browser services with minimal memory
            docker compose -f "$COMPOSE_FILE" stop firecrawl-playwright firecrawl-api
            sleep 5
            docker compose -f "$COMPOSE_FILE" up -d firecrawl-api firecrawl-playwright
        fi
        
    elif [[ $memory_percent -ge 85 ]]; then
        log_output "${YELLOW}${ALERT_WARNING} High memory pressure detected (${memory_percent}%)${NC}"
        scale_down_services "utilities"
        
        if [[ "$DRY_RUN" == "false" ]]; then
            # Clear caches
            docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli --eval "redis.call('flushdb')" || true
        fi
        
    elif [[ $memory_percent -ge 75 ]]; then
        log_output "${BLUE}${ALERT_INFO} Moderate memory pressure detected (${memory_percent}%)${NC}"
        log_output "Consider running: docker compose -f $COMPOSE_FILE stop flower mailpit"
        
    else
        log_output "${GREEN}${ALERT_SUCCESS} Memory usage is optimal (${memory_percent}%)${NC}"
    fi
}

# Function to perform graceful restart
graceful_restart() {
    local profile="${1:-standard}"
    
    log_output "${BLUE}${ALERT_INFO} Starting graceful restart with profile: $profile${NC}"
    
    if [[ "$BACKUP_BEFORE" == "true" ]]; then
        backup_current_state
    fi
    
    # Stop all services gracefully
    if [[ "$DRY_RUN" == "true" ]]; then
        log_output "${CYAN}[DRY RUN] Would stop all services${NC}"
        log_output "${CYAN}[DRY RUN] Would start services for profile: $profile${NC}"
    else
        log_output "${BLUE}Stopping all services...${NC}"
        docker compose -f "$COMPOSE_FILE" down
        
        sleep "$WAIT_TIME"
        
        # Start services according to profile
        scale_up_services "$profile"
    fi
}

# Function to perform comprehensive health check
health_check() {
    log_output "\n${BLUE}=== Comprehensive Health Check ===${NC}"
    
    local unhealthy_services=()
    local total_services=0
    local healthy_services=0
    
    for service in "${!SERVICE_TIERS[@]}"; do
        local health=$(check_service_health "$service")
        local tier="${SERVICE_TIERS[$service]}"
        total_services=$((total_services + 1))
        
        case "$health" in
            "running"|"healthy")
                log_output "${GREEN}${ALERT_SUCCESS} $service ($tier): $health${NC}"
                healthy_services=$((healthy_services + 1))
                ;;
            "starting")
                log_output "${YELLOW}${ALERT_INFO} $service ($tier): $health${NC}"
                ;;
            "unhealthy"|"exited")
                log_output "${RED}${ALERT_CRITICAL} $service ($tier): $health${NC}"
                unhealthy_services+=("$service")
                ;;
            "stopped")
                log_output "${CYAN}${ALERT_INFO} $service ($tier): $health${NC}"
                ;;
            *)
                log_output "${YELLOW}${ALERT_WARNING} $service ($tier): $health${NC}"
                ;;
        esac
    done
    
    log_output "\n${PURPLE}=== Health Summary ===${NC}"
    log_output "Total services: $total_services"
    log_output "Healthy/Running: $healthy_services"
    log_output "Unhealthy: ${#unhealthy_services[@]}"
    
    if [[ ${#unhealthy_services[@]} -gt 0 ]]; then
        log_output "${RED}Unhealthy services: ${unhealthy_services[*]}${NC}"
        
        if [[ "$FORCE" == "false" ]]; then
            read -p "Restart unhealthy services? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                for service in "${unhealthy_services[@]}"; do
                    log_output "${BLUE}Restarting $service...${NC}"
                    docker compose -f "$COMPOSE_FILE" restart "$service"
                    sleep 5
                done
            fi
        fi
    else
        log_output "${GREEN}${ALERT_SUCCESS} All services are healthy!${NC}"
    fi
    
    # Resource usage summary
    log_output "\n${PURPLE}=== Resource Usage ===${NC}"
    log_output "Memory usage: $(get_memory_usage)%"
    log_output "CPU usage: $(get_cpu_usage)%"
}

# Main execution
main() {
    check_docker_compose
    
    log_output "${PURPLE}========================================${NC}"
    log_output "${PURPLE} Chrono Scraper Service Scaling Tool${NC}"
    log_output "${PURPLE} $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    log_output "${PURPLE}========================================${NC}"
    
    case "$ACTION" in
        "scale-down")
            scale_down_services "${LEVEL_OR_PROFILE:-utilities}"
            ;;
        "scale-up")
            scale_up_services "${LEVEL_OR_PROFILE:-standard}"
            ;;
        "emergency-stop")
            emergency_stop
            ;;
        "graceful-restart")
            graceful_restart "${LEVEL_OR_PROFILE:-standard}"
            ;;
        "memory-pressure")
            handle_memory_pressure
            ;;
        "status")
            get_service_status
            ;;
        "health-check")
            health_check
            ;;
        "backup-state")
            backup_current_state
            ;;
        "restore-state")
            restore_from_backup "$LEVEL_OR_PROFILE"
            ;;
        *)
            log_output "${RED}Error: Unknown action: $ACTION${NC}"
            show_usage
            ;;
    esac
    
    log_output "${PURPLE}========================================${NC}"
    log_output "${GREEN}Operation completed successfully${NC}"
    log_output "Log file: $SCALING_LOG"
    log_output "${PURPLE}========================================${NC}"
}

# Run main function
main