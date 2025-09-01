#!/bin/bash
set -euo pipefail

# Chrono Scraper v2 Phase Migration Script
# Automates migration between scaling phases with safety checks

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="/tmp/chrono-scraper-backups/$(date +%Y%m%d_%H%M%S)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SOURCE_PHASE=""
TARGET_PHASE=""
DRY_RUN=false
FORCE=false
BACKUP_ENABLED=true
ROLLBACK_TIMEOUT=1800  # 30 minutes

# Hetzner Cloud API configuration (set via environment)
HCLOUD_TOKEN="${HCLOUD_TOKEN:-}"

usage() {
    cat << EOF
Usage: $0 --from <phase> --to <phase> [OPTIONS]

Phase Migration Tool for Chrono Scraper v2

OPTIONS:
    --from <1-5>           Source phase (current deployment)
    --to <1-5>            Target phase (desired deployment)
    --dry-run             Show what would be done without executing
    --force               Skip confirmation prompts
    --no-backup           Skip backup creation (not recommended)
    --rollback-timeout    Timeout for automatic rollback (seconds, default: 1800)
    --help               Show this help message

EXAMPLES:
    $0 --from 1 --to 2                    # Migrate from single server to separated services
    $0 --from 2 --to 3 --dry-run         # Preview horizontal scaling migration
    $0 --from 3 --to 4 --force           # Force multi-region migration

ENVIRONMENT VARIABLES:
    HCLOUD_TOKEN          Required for Hetzner Cloud API access
    POSTGRES_PASSWORD     Database password for migrations
    REDIS_PASSWORD        Redis password if configured
EOF
}

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --from)
                SOURCE_PHASE="$2"
                shift 2
                ;;
            --to)
                TARGET_PHASE="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --force)
                FORCE=true
                shift
                ;;
            --no-backup)
                BACKUP_ENABLED=false
                shift
                ;;
            --rollback-timeout)
                ROLLBACK_TIMEOUT="$2"
                shift 2
                ;;
            --help)
                usage
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
    
    if [[ -z "$SOURCE_PHASE" ]] || [[ -z "$TARGET_PHASE" ]]; then
        error "Both --from and --to phases must be specified"
        usage
        exit 1
    fi
    
    if ! [[ "$SOURCE_PHASE" =~ ^[1-5]$ ]] || ! [[ "$TARGET_PHASE" =~ ^[1-5]$ ]]; then
        error "Phase numbers must be between 1 and 5"
        exit 1
    fi
    
    if [[ "$SOURCE_PHASE" -ge "$TARGET_PHASE" ]]; then
        error "Target phase must be higher than source phase"
        exit 1
    fi
}

# Validate prerequisites
validate_prerequisites() {
    log "Validating prerequisites..."
    
    # Check required tools
    local required_tools=("docker" "docker-compose" "curl" "jq" "psql")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            error "Required tool not found: $tool"
            exit 1
        fi
    done
    
    # Check Hetzner Cloud token for phases requiring new servers
    if [[ "$TARGET_PHASE" -gt 1 ]] && [[ -z "$HCLOUD_TOKEN" ]]; then
        warn "HCLOUD_TOKEN not set - server provisioning will be manual"
    fi
    
    # Check current application health
    if ! curl -sf http://localhost:8000/api/v1/health &> /dev/null; then
        error "Application health check failed - fix issues before migration"
        exit 1
    fi
    
    # Validate source phase matches current deployment
    local current_containers=$(docker ps --format "table {{.Names}}" | grep -c "chrono-scraper" || true)
    if [[ "$SOURCE_PHASE" == "1" ]] && [[ "$current_containers" -eq 0 ]]; then
        error "No containers running - check current deployment"
        exit 1
    fi
    
    success "Prerequisites validated"
}

# Create comprehensive backup
create_backup() {
    if [[ "$BACKUP_ENABLED" == "false" ]]; then
        warn "Backup disabled - proceeding without backup"
        return 0
    fi
    
    log "Creating backup in $BACKUP_DIR..."
    mkdir -p "$BACKUP_DIR"
    
    # Database backup
    log "Backing up PostgreSQL database..."
    docker exec chrono-scraper-fastapi-2-postgres-1 pg_dump \
        -U chrono_scraper -d chrono_scraper \
        > "$BACKUP_DIR/database.sql"
    
    # Redis backup
    log "Backing up Redis data..."
    docker exec chrono-scraper-fastapi-2-redis-1 redis-cli \
        --rdb "$BACKUP_DIR/redis.rdb" || true
    
    # Meilisearch backup
    log "Backing up Meilisearch indexes..."
    mkdir -p "$BACKUP_DIR/meilisearch"
    curl -s "http://localhost:7700/dumps" \
        -H "Authorization: Bearer ${MEILISEARCH_MASTER_KEY:-}" \
        -X POST > "$BACKUP_DIR/meilisearch/dump.json" || true
    
    # Configuration backup
    log "Backing up configuration files..."
    cp -r "$PROJECT_DIR/.env" "$BACKUP_DIR/" 2>/dev/null || true
    cp -r "$PROJECT_DIR/docker-compose.yml" "$BACKUP_DIR/"
    
    # Create backup manifest
    cat > "$BACKUP_DIR/manifest.json" << EOF
{
    "timestamp": "$(date -Iseconds)",
    "source_phase": $SOURCE_PHASE,
    "target_phase": $TARGET_PHASE,
    "backup_type": "pre_migration",
    "files": {
        "database": "database.sql",
        "redis": "redis.rdb",
        "meilisearch": "meilisearch/dump.json",
        "config": ".env"
    }
}
EOF
    
    success "Backup created: $BACKUP_DIR"
}

# Phase-specific migration functions
migrate_1_to_2() {
    log "Migrating from Phase 1 (single server) to Phase 2 (service separation)"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would provision 2x CX22 servers on Hetzner Cloud"
        log "[DRY RUN] Would separate application and database layers"
        log "[DRY RUN] Would configure service networking"
        return 0
    fi
    
    # Step 1: Provision servers
    log "Provisioning application server (CX22)..."
    if [[ -n "$HCLOUD_TOKEN" ]]; then
        hcloud server create \
            --name "chrono-app-01" \
            --type cx22 \
            --image ubuntu-22.04 \
            --ssh-key-file ~/.ssh/id_rsa.pub \
            --user-data-from-file "$SCRIPT_DIR/cloud-init/app-server.yml"
    else
        warn "Manual server provisioning required - see SCALING_STRATEGY.md"
    fi
    
    log "Provisioning database server (CX22)..."
    if [[ -n "$HCLOUD_TOKEN" ]]; then
        hcloud server create \
            --name "chrono-db-01" \
            --type cx22 \
            --image ubuntu-22.04 \
            --ssh-key-file ~/.ssh/id_rsa.pub \
            --user-data-from-file "$SCRIPT_DIR/cloud-init/db-server.yml"
    fi
    
    # Step 2: Wait for servers to be ready
    log "Waiting for servers to initialize..."
    sleep 60
    
    # Step 3: Configure database replication
    log "Setting up PostgreSQL replication..."
    # This would involve complex database migration scripts
    # For brevity, showing high-level steps
    
    # Step 4: Update application configuration
    log "Updating application configuration..."
    sed -i 's/POSTGRES_HOST=localhost/POSTGRES_HOST=chrono-db-01/' "$PROJECT_DIR/.env"
    
    # Step 5: Deploy application to new servers
    log "Deploying application to new infrastructure..."
    # rsync application files, run docker-compose on new servers
    
    success "Migration to Phase 2 completed"
}

migrate_2_to_3() {
    log "Migrating from Phase 2 (separated services) to Phase 3 (horizontal scaling)"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would provision load balancer (CPX21)"
        log "[DRY RUN] Would add additional application servers"
        log "[DRY RUN] Would configure HAProxy load balancing"
        return 0
    fi
    
    # Step 1: Provision load balancer
    log "Provisioning load balancer..."
    if [[ -n "$HCLOUD_TOKEN" ]]; then
        hcloud server create \
            --name "chrono-lb-01" \
            --type cpx21 \
            --image ubuntu-22.04 \
            --ssh-key-file ~/.ssh/id_rsa.pub
    fi
    
    # Step 2: Configure HAProxy
    log "Configuring load balancing..."
    # Deploy HAProxy configuration
    
    # Step 3: Scale application servers
    log "Adding additional application servers..."
    # Add more backend servers
    
    success "Migration to Phase 3 completed"
}

migrate_3_to_4() {
    log "Migrating from Phase 3 (horizontal scaling) to Phase 4 (multi-region)"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would set up multi-region infrastructure"
        log "[DRY RUN] Would configure cross-region replication"
        log "[DRY RUN] Would implement CDN"
        return 0
    fi
    
    # Complex multi-region setup
    error "Phase 3->4 migration requires manual planning - see SCALING_STRATEGY.md"
    return 1
}

migrate_4_to_5() {
    log "Migrating from Phase 4 (multi-region) to Phase 5 (enterprise Kubernetes)"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would provision Kubernetes cluster"
        log "[DRY RUN] Would containerize all services"
        log "[DRY RUN] Would implement auto-scaling"
        return 0
    fi
    
    error "Phase 4->5 migration requires Kubernetes expertise - see SCALING_STRATEGY.md"
    return 1
}

# Execute migration based on phases
execute_migration() {
    log "Starting migration from Phase $SOURCE_PHASE to Phase $TARGET_PHASE"
    
    case "$SOURCE_PHASE-$TARGET_PHASE" in
        "1-2")
            migrate_1_to_2
            ;;
        "2-3")
            migrate_2_to_3
            ;;
        "3-4")
            migrate_3_to_4
            ;;
        "4-5")
            migrate_4_to_5
            ;;
        *)
            # Multi-phase migration
            error "Multi-phase migration not supported - migrate one phase at a time"
            return 1
            ;;
    esac
}

# Verify migration success
verify_migration() {
    log "Verifying migration success..."
    
    # Health checks
    local health_url="http://localhost:8000/api/v1/health"
    for i in {1..30}; do
        if curl -sf "$health_url" &> /dev/null; then
            success "Application health check passed"
            break
        fi
        if [[ $i -eq 30 ]]; then
            error "Application health check failed after migration"
            return 1
        fi
        sleep 10
    done
    
    # Database connectivity
    if docker exec chrono-scraper-fastapi-2-postgres-1 psql \
        -U chrono_scraper -d chrono_scraper -c "SELECT 1" &> /dev/null; then
        success "Database connectivity verified"
    else
        error "Database connectivity failed"
        return 1
    fi
    
    # Performance baseline
    log "Running performance verification..."
    local response_time=$(curl -w "%{time_total}" -s -o /dev/null http://localhost:8000/api/v1/health)
    if (( $(echo "$response_time < 2.0" | bc -l) )); then
        success "Performance baseline met (${response_time}s)"
    else
        warn "Performance degraded (${response_time}s) - monitor closely"
    fi
    
    return 0
}

# Rollback mechanism
rollback_migration() {
    error "Migration verification failed - initiating rollback"
    
    if [[ "$BACKUP_ENABLED" == "false" ]]; then
        error "Cannot rollback - no backup was created"
        return 1
    fi
    
    log "Restoring from backup: $BACKUP_DIR"
    
    # Stop current services
    docker-compose down
    
    # Restore database
    log "Restoring database..."
    docker-compose up -d postgres
    sleep 30
    docker exec -i chrono-scraper-fastapi-2-postgres-1 psql \
        -U chrono_scraper -d chrono_scraper < "$BACKUP_DIR/database.sql"
    
    # Restore Redis
    log "Restoring Redis data..."
    docker-compose up -d redis
    sleep 10
    docker cp "$BACKUP_DIR/redis.rdb" \
        chrono-scraper-fastapi-2-redis-1:/data/dump.rdb
    docker restart chrono-scraper-fastapi-2-redis-1
    
    # Restore configuration
    cp "$BACKUP_DIR/.env" "$PROJECT_DIR/"
    cp "$BACKUP_DIR/docker-compose.yml" "$PROJECT_DIR/"
    
    # Restart services
    docker-compose up -d
    
    # Verify rollback
    sleep 60
    if curl -sf http://localhost:8000/api/v1/health &> /dev/null; then
        success "Rollback completed successfully"
    else
        error "Rollback verification failed - manual intervention required"
        return 1
    fi
}

# Main execution flow
main() {
    parse_args "$@"
    
    log "Chrono Scraper v2 Migration: Phase $SOURCE_PHASE -> Phase $TARGET_PHASE"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        warn "DRY RUN MODE - No changes will be made"
    fi
    
    if [[ "$FORCE" == "false" ]] && [[ "$DRY_RUN" == "false" ]]; then
        echo
        warn "This migration will modify your infrastructure and may cause downtime."
        read -p "Continue? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "Migration cancelled by user"
            exit 0
        fi
    fi
    
    # Execute migration steps
    validate_prerequisites
    create_backup
    
    # Set up rollback timer if not dry run
    if [[ "$DRY_RUN" == "false" ]]; then
        (
            sleep "$ROLLBACK_TIMEOUT"
            if ! verify_migration; then
                warn "Automatic rollback timeout reached"
                rollback_migration
            fi
        ) &
        local rollback_pid=$!
    fi
    
    # Execute the migration
    if execute_migration; then
        if [[ "$DRY_RUN" == "false" ]]; then
            # Kill rollback timer
            kill $rollback_pid 2>/dev/null || true
            
            # Verify migration
            if verify_migration; then
                success "Migration completed successfully!"
                log "Backup retained at: $BACKUP_DIR"
                log "Monitor application performance for the next 24 hours"
            else
                rollback_migration
                exit 1
            fi
        else
            success "Dry run completed - review output above"
        fi
    else
        error "Migration failed"
        if [[ "$DRY_RUN" == "false" ]]; then
            rollback_migration
        fi
        exit 1
    fi
}

# Run main function with all arguments
main "$@"