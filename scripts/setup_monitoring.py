#!/usr/bin/env python3
"""
Database Monitoring and Alerting Setup
Comprehensive monitoring system for Chrono Scraper v2 database operations

This script sets up a complete monitoring infrastructure including:
- Prometheus metrics collection
- Grafana dashboards for visualization  
- Alert manager integration
- Custom database health checks
- Performance monitoring and trending
- Automated anomaly detection

Usage:
    python setup_monitoring.py --install-all
    python setup_monitoring.py --setup-prometheus
    python setup_monitoring.py --create-dashboards
    python setup_monitoring.py --test-alerts
"""

import os
import json
import yaml
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
import subprocess
import time
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MonitoringSetup:
    """Database monitoring and alerting setup"""
    
    def __init__(self):
        self.project_root = Path("/home/bizon/Development/chrono-scraper-fastapi-2")
        self.monitoring_dir = self.project_root / "monitoring"
        self.monitoring_dir.mkdir(exist_ok=True)
        
    def setup_prometheus_exporter(self):
        """Setup PostgreSQL Prometheus exporter"""
        logger.info("Setting up PostgreSQL Prometheus exporter...")
        
        # Create exporter configuration
        exporter_config = {
            'version': '3.8',
            'services': {
                'postgres_exporter': {
                    'image': 'prometheuscommunity/postgres-exporter:latest',
                    'container_name': 'chrono_postgres_exporter',
                    'environment': {
                        'DATA_SOURCE_NAME': 'postgresql://chrono_scraper:chrono_scraper_dev@postgres:5432/chrono_scraper?sslmode=disable'
                    },
                    'ports': ['9187:9187'],
                    'depends_on': ['postgres'],
                    'restart': 'unless-stopped',
                    'networks': ['default']
                },
                'redis_exporter': {
                    'image': 'oliver006/redis_exporter:latest',
                    'container_name': 'chrono_redis_exporter',
                    'environment': {
                        'REDIS_ADDR': 'redis://redis:6379'
                    },
                    'ports': ['9121:9121'],
                    'depends_on': ['redis'],
                    'restart': 'unless-stopped',
                    'networks': ['default']
                }
            }
        }
        
        # Write exporter docker-compose override
        exporter_file = self.project_root / "docker-compose.monitoring.yml"
        with open(exporter_file, 'w') as f:
            yaml.dump(exporter_config, f, default_flow_style=False)
        
        logger.info(f"Prometheus exporters configuration written to {exporter_file}")
        
    def create_prometheus_config(self):
        """Create Prometheus configuration"""
        logger.info("Creating Prometheus configuration...")
        
        prometheus_config = {
            'global': {
                'scrape_interval': '15s',
                'evaluation_interval': '15s'
            },
            'rule_files': [
                'alerts/*.yml'
            ],
            'alerting': {
                'alertmanagers': [{
                    'static_configs': [{
                        'targets': ['alertmanager:9093']
                    }]
                }]
            },
            'scrape_configs': [
                {
                    'job_name': 'prometheus',
                    'static_configs': [{
                        'targets': ['localhost:9090']
                    }]
                },
                {
                    'job_name': 'postgres',
                    'static_configs': [{
                        'targets': ['postgres_exporter:9187']
                    }],
                    'scrape_interval': '30s'
                },
                {
                    'job_name': 'redis',
                    'static_configs': [{
                        'targets': ['redis_exporter:9121']
                    }],
                    'scrape_interval': '30s'
                },
                {
                    'job_name': 'chrono-backend',
                    'static_configs': [{
                        'targets': ['backend:8000']
                    }],
                    'metrics_path': '/api/v1/metrics'
                },
                {
                    'job_name': 'node-exporter',
                    'static_configs': [{
                        'targets': ['node-exporter:9100']
                    }]
                }
            ]
        }
        
        prometheus_dir = self.monitoring_dir / "prometheus"
        prometheus_dir.mkdir(exist_ok=True)
        
        config_file = prometheus_dir / "prometheus.yml"
        with open(config_file, 'w') as f:
            yaml.dump(prometheus_config, f, default_flow_style=False)
        
        logger.info(f"Prometheus configuration written to {config_file}")
        
    def create_alert_rules(self):
        """Create Prometheus alert rules"""
        logger.info("Creating Prometheus alert rules...")
        
        alerts_dir = self.monitoring_dir / "prometheus" / "alerts"
        alerts_dir.mkdir(exist_ok=True)
        
        # Database alerts
        db_alerts = {
            'groups': [{
                'name': 'database.rules',
                'rules': [
                    {
                        'alert': 'PostgreSQLDown',
                        'expr': 'pg_up == 0',
                        'for': '0m',
                        'labels': {'severity': 'critical'},
                        'annotations': {
                            'summary': 'PostgreSQL instance is down',
                            'description': 'PostgreSQL instance {{ $labels.instance }} is down for more than 1 minute'
                        }
                    },
                    {
                        'alert': 'PostgreSQLHighConnections',
                        'expr': '(pg_stat_activity_count / pg_settings_max_connections) * 100 > 80',
                        'for': '5m',
                        'labels': {'severity': 'warning'},
                        'annotations': {
                            'summary': 'High database connections',
                            'description': 'PostgreSQL has {{ $value }}% connection usage'
                        }
                    },
                    {
                        'alert': 'PostgreSQLReplicationLag',
                        'expr': 'pg_stat_replication_replay_lag > 300',
                        'for': '5m',
                        'labels': {'severity': 'warning'},
                        'annotations': {
                            'summary': 'PostgreSQL replication lag',
                            'description': 'PostgreSQL replication lag is {{ $value }} seconds'
                        }
                    },
                    {
                        'alert': 'PostgreSQLDeadlocks',
                        'expr': 'rate(pg_stat_database_deadlocks[5m]) > 0',
                        'for': '1m',
                        'labels': {'severity': 'warning'},
                        'annotations': {
                            'summary': 'PostgreSQL deadlocks detected',
                            'description': 'Deadlock rate is {{ $value }} per second'
                        }
                    },
                    {
                        'alert': 'PostgreSQLSlowQueries',
                        'expr': 'pg_stat_activity_max_tx_duration > 300',
                        'for': '2m',
                        'labels': {'severity': 'warning'},
                        'annotations': {
                            'summary': 'Slow PostgreSQL queries',
                            'description': 'Longest transaction running for {{ $value }} seconds'
                        }
                    },
                    {
                        'alert': 'PostgreSQLTableBloat',
                        'expr': 'pg_stat_user_tables_n_dead_tup / (pg_stat_user_tables_n_live_tup + pg_stat_user_tables_n_dead_tup) * 100 > 30',
                        'for': '15m',
                        'labels': {'severity': 'warning'},
                        'annotations': {
                            'summary': 'High table bloat detected',
                            'description': 'Table {{ $labels.table }} has {{ $value }}% dead tuples'
                        }
                    }
                ]
            }]
        }
        
        # System alerts
        system_alerts = {
            'groups': [{
                'name': 'system.rules',
                'rules': [
                    {
                        'alert': 'DiskSpaceHigh',
                        'expr': '(node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 < 15',
                        'for': '5m',
                        'labels': {'severity': 'warning'},
                        'annotations': {
                            'summary': 'Disk space is running low',
                            'description': 'Disk {{ $labels.mountpoint }} has {{ $value }}% free space'
                        }
                    },
                    {
                        'alert': 'HighMemoryUsage',
                        'expr': '(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100 > 90',
                        'for': '10m',
                        'labels': {'severity': 'warning'},
                        'annotations': {
                            'summary': 'High memory usage',
                            'description': 'Memory usage is above 90%'
                        }
                    },
                    {
                        'alert': 'HighCPUUsage',
                        'expr': '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 90',
                        'for': '15m',
                        'labels': {'severity': 'warning'},
                        'annotations': {
                            'summary': 'High CPU usage',
                            'description': 'CPU usage is above 90%'
                        }
                    }
                ]
            }]
        }
        
        # Application-specific alerts
        app_alerts = {
            'groups': [{
                'name': 'application.rules',
                'rules': [
                    {
                        'alert': 'ScrapingJobsFailed',
                        'expr': 'increase(celery_task_failed_total{task_name=~"scraping.*"}[10m]) > 10',
                        'for': '2m',
                        'labels': {'severity': 'warning'},
                        'annotations': {
                            'summary': 'High scraping job failure rate',
                            'description': '{{ $value }} scraping jobs failed in the last 10 minutes'
                        }
                    },
                    {
                        'alert': 'MeilisearchDown',
                        'expr': 'meilisearch_up == 0',
                        'for': '1m',
                        'labels': {'severity': 'critical'},
                        'annotations': {
                            'summary': 'Meilisearch is down',
                            'description': 'Meilisearch search engine is not responding'
                        }
                    },
                    {
                        'alert': 'RedisDown',
                        'expr': 'redis_up == 0',
                        'for': '1m',
                        'labels': {'severity': 'critical'},
                        'annotations': {
                            'summary': 'Redis is down',
                            'description': 'Redis cache server is not responding'
                        }
                    }
                ]
            }]
        }
        
        # Write alert files
        with open(alerts_dir / "database.yml", 'w') as f:
            yaml.dump(db_alerts, f, default_flow_style=False)
        
        with open(alerts_dir / "system.yml", 'w') as f:
            yaml.dump(system_alerts, f, default_flow_style=False)
            
        with open(alerts_dir / "application.yml", 'w') as f:
            yaml.dump(app_alerts, f, default_flow_style=False)
        
        logger.info(f"Alert rules written to {alerts_dir}")
        
    def create_alertmanager_config(self):
        """Create Alertmanager configuration"""
        logger.info("Creating Alertmanager configuration...")
        
        alertmanager_config = {
            'global': {
                'smtp_smarthost': 'localhost:587',
                'smtp_from': 'alerts@chrono-scraper.local'
            },
            'route': {
                'group_by': ['alertname', 'cluster'],
                'group_wait': '10s',
                'group_interval': '10s',
                'repeat_interval': '1h',
                'receiver': 'web.hook'
            },
            'receivers': [
                {
                    'name': 'web.hook',
                    'email_configs': [{
                        'to': 'admin@chrono-scraper.local',
                        'subject': '[ALERT] Chrono Scraper - {{ .GroupLabels.alertname }}',
                        'body': '''
{{ range .Alerts }}
Alert: {{ .Annotations.summary }}
Description: {{ .Annotations.description }}
Labels: {{ range .Labels.SortedPairs }}{{ .Name }}={{ .Value }} {{ end }}
{{ end }}
'''
                    }],
                    'webhook_configs': [{
                        'url': 'http://backend:8000/api/v1/alerts/webhook',
                        'send_resolved': True
                    }]
                }
            ]
        }
        
        alertmanager_dir = self.monitoring_dir / "alertmanager"
        alertmanager_dir.mkdir(exist_ok=True)
        
        config_file = alertmanager_dir / "alertmanager.yml"
        with open(config_file, 'w') as f:
            yaml.dump(alertmanager_config, f, default_flow_style=False)
        
        logger.info(f"Alertmanager configuration written to {config_file}")
        
    def create_grafana_dashboards(self):
        """Create Grafana dashboards"""
        logger.info("Creating Grafana dashboards...")
        
        grafana_dir = self.monitoring_dir / "grafana"
        dashboards_dir = grafana_dir / "dashboards"
        dashboards_dir.mkdir(parents=True, exist_ok=True)
        
        # Database Overview Dashboard
        db_dashboard = {
            "dashboard": {
                "id": None,
                "title": "PostgreSQL Database Overview",
                "tags": ["postgresql", "database"],
                "timezone": "browser",
                "panels": [
                    {
                        "id": 1,
                        "title": "Database Connections",
                        "type": "stat",
                        "targets": [{
                            "expr": "pg_stat_activity_count",
                            "legendFormat": "Active Connections"
                        }],
                        "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0}
                    },
                    {
                        "id": 2,
                        "title": "Database Size",
                        "type": "stat",
                        "targets": [{
                            "expr": "pg_database_size_bytes",
                            "legendFormat": "Database Size"
                        }],
                        "gridPos": {"h": 8, "w": 6, "x": 6, "y": 0}
                    },
                    {
                        "id": 3,
                        "title": "Transaction Rate",
                        "type": "graph",
                        "targets": [{
                            "expr": "rate(pg_stat_database_xact_commit[5m])",
                            "legendFormat": "Commits/sec"
                        }, {
                            "expr": "rate(pg_stat_database_xact_rollback[5m])",
                            "legendFormat": "Rollbacks/sec"
                        }],
                        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0}
                    },
                    {
                        "id": 4,
                        "title": "Cache Hit Ratio",
                        "type": "graph",
                        "targets": [{
                            "expr": "pg_stat_database_blks_hit / (pg_stat_database_blks_hit + pg_stat_database_blks_read) * 100",
                            "legendFormat": "Cache Hit Ratio %"
                        }],
                        "yAxes": [{
                            "min": 0,
                            "max": 100,
                            "unit": "percent"
                        }],
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8}
                    },
                    {
                        "id": 5,
                        "title": "Table Operations",
                        "type": "table",
                        "targets": [{
                            "expr": "pg_stat_user_tables_n_tup_ins",
                            "format": "table"
                        }],
                        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8}
                    }
                ],
                "time": {"from": "now-1h", "to": "now"},
                "refresh": "30s"
            }
        }
        
        # Application Performance Dashboard
        app_dashboard = {
            "dashboard": {
                "id": None,
                "title": "Chrono Scraper Application Metrics",
                "tags": ["application", "performance"],
                "panels": [
                    {
                        "id": 1,
                        "title": "Scraping Jobs Status",
                        "type": "graph",
                        "targets": [{
                            "expr": "celery_task_total{task_name=~\"scraping.*\",state=\"SUCCESS\"}",
                            "legendFormat": "Successful"
                        }, {
                            "expr": "celery_task_total{task_name=~\"scraping.*\",state=\"FAILURE\"}",
                            "legendFormat": "Failed"
                        }],
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0}
                    },
                    {
                        "id": 2,
                        "title": "Pages Scraped per Hour",
                        "type": "stat",
                        "targets": [{
                            "expr": "increase(scrape_pages_completed_total[1h])",
                            "legendFormat": "Pages/hour"
                        }],
                        "gridPos": {"h": 8, "w": 6, "x": 12, "y": 0}
                    },
                    {
                        "id": 3,
                        "title": "Search Operations",
                        "type": "graph",
                        "targets": [{
                            "expr": "rate(meilisearch_search_requests_total[5m])",
                            "legendFormat": "Search Requests/sec"
                        }],
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8}
                    }
                ],
                "time": {"from": "now-6h", "to": "now"},
                "refresh": "1m"
            }
        }
        
        # Write dashboards
        with open(dashboards_dir / "postgresql-overview.json", 'w') as f:
            json.dump(db_dashboard, f, indent=2)
        
        with open(dashboards_dir / "application-metrics.json", 'w') as f:
            json.dump(app_dashboard, f, indent=2)
        
        # Create dashboard provisioning config
        provisioning_dir = grafana_dir / "provisioning" / "dashboards"
        provisioning_dir.mkdir(parents=True, exist_ok=True)
        
        dashboard_config = {
            'apiVersion': 1,
            'providers': [{
                'name': 'chrono-dashboards',
                'type': 'file',
                'disableDeletion': False,
                'updateIntervalSeconds': 10,
                'allowUiUpdates': True,
                'options': {
                    'path': '/etc/grafana/provisioning/dashboards'
                }
            }]
        }
        
        with open(provisioning_dir / "dashboards.yml", 'w') as f:
            yaml.dump(dashboard_config, f, default_flow_style=False)
        
        logger.info(f"Grafana dashboards created in {dashboards_dir}")
        
    def create_monitoring_compose(self):
        """Create monitoring stack docker-compose"""
        logger.info("Creating monitoring stack docker-compose...")
        
        monitoring_stack = {
            'version': '3.8',
            'services': {
                'prometheus': {
                    'image': 'prom/prometheus:latest',
                    'container_name': 'chrono_prometheus',
                    'ports': ['9090:9090'],
                    'volumes': [
                        './monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml',
                        './monitoring/prometheus/alerts:/etc/prometheus/alerts',
                        'prometheus_data:/prometheus'
                    ],
                    'command': [
                        '--config.file=/etc/prometheus/prometheus.yml',
                        '--storage.tsdb.path=/prometheus',
                        '--web.console.libraries=/usr/share/prometheus/console_libraries',
                        '--web.console.templates=/usr/share/prometheus/consoles',
                        '--storage.tsdb.retention.time=90d',
                        '--web.enable-lifecycle',
                        '--web.enable-admin-api'
                    ],
                    'restart': 'unless-stopped',
                    'networks': ['monitoring']
                },
                'alertmanager': {
                    'image': 'prom/alertmanager:latest',
                    'container_name': 'chrono_alertmanager',
                    'ports': ['9093:9093'],
                    'volumes': [
                        './monitoring/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml',
                        'alertmanager_data:/alertmanager'
                    ],
                    'restart': 'unless-stopped',
                    'networks': ['monitoring']
                },
                'grafana': {
                    'image': 'grafana/grafana:latest',
                    'container_name': 'chrono_grafana',
                    'ports': ['3001:3000'],
                    'environment': {
                        'GF_SECURITY_ADMIN_PASSWORD': 'admin123',
                        'GF_USERS_ALLOW_SIGN_UP': 'false',
                        'GF_INSTALL_PLUGINS': 'grafana-piechart-panel,grafana-worldmap-panel'
                    },
                    'volumes': [
                        './monitoring/grafana/provisioning:/etc/grafana/provisioning',
                        './monitoring/grafana/dashboards:/etc/grafana/dashboards',
                        'grafana_data:/var/lib/grafana'
                    ],
                    'restart': 'unless-stopped',
                    'networks': ['monitoring']
                },
                'node_exporter': {
                    'image': 'prom/node-exporter:latest',
                    'container_name': 'chrono_node_exporter',
                    'ports': ['9100:9100'],
                    'volumes': [
                        '/proc:/host/proc:ro',
                        '/sys:/host/sys:ro',
                        '/:/rootfs:ro'
                    ],
                    'command': [
                        '--path.procfs=/host/proc',
                        '--path.rootfs=/rootfs',
                        '--path.sysfs=/host/sys',
                        '--collector.filesystem.ignored-mount-points=^/(sys|proc|dev|host|etc)($$|/)'
                    ],
                    'restart': 'unless-stopped',
                    'networks': ['monitoring']
                }
            },
            'volumes': {
                'prometheus_data': {},
                'grafana_data': {},
                'alertmanager_data': {}
            },
            'networks': {
                'monitoring': {
                    'driver': 'bridge'
                },
                'default': {
                    'external': True,
                    'name': 'chrono-scraper-fastapi-2_default'
                }
            }
        }
        
        compose_file = self.monitoring_dir / "docker-compose.yml"
        with open(compose_file, 'w') as f:
            yaml.dump(monitoring_stack, f, default_flow_style=False)
        
        logger.info(f"Monitoring stack compose file written to {compose_file}")
        
    def create_health_check_script(self):
        """Create comprehensive health check script"""
        logger.info("Creating health check script...")
        
        health_check_script = '''#!/bin/bash
# Database health check script for monitoring integration

set -e

DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-chrono_scraper}"
DB_USER="${POSTGRES_USER:-chrono_scraper}"
DB_PASS="${POSTGRES_PASSWORD:-chrono_scraper_dev}"

METRICS_FILE="/tmp/db_health_metrics"

# Function to send metric to Prometheus
send_metric() {
    local metric_name="$1"
    local metric_value="$2"
    local labels="$3"
    echo "${metric_name}${labels} ${metric_value}" >> "$METRICS_FILE"
}

# Clear metrics file
> "$METRICS_FILE"

# Test database connectivity
if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" >/dev/null 2>&1; then
    send_metric "postgresql_up" "1" ""
    echo "Database connectivity: OK"
else
    send_metric "postgresql_up" "0" ""
    echo "Database connectivity: FAILED"
    exit 1
fi

# Check connection count
CONN_COUNT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT count(*) FROM pg_stat_activity;")
send_metric "postgresql_connections_active" "$CONN_COUNT" ""

# Check database size
DB_SIZE=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT pg_database_size(current_database());")
send_metric "postgresql_database_size_bytes" "$DB_SIZE" ""

# Check for slow queries
SLOW_QUERIES=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
SELECT count(*) FROM pg_stat_activity 
WHERE state = 'active' AND now() - query_start > interval '30 seconds'
AND query NOT LIKE '%pg_stat_activity%';")
send_metric "postgresql_slow_queries" "$SLOW_QUERIES" ""

# Check table bloat for key tables
for table in scrape_pages pages domains users; do
    BLOAT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
    SELECT COALESCE(
        CASE WHEN n_live_tup > 0 
        THEN round((n_dead_tup::float/n_live_tup::float)*100, 2) 
        ELSE 0 END, 0
    ) FROM pg_stat_user_tables WHERE tablename = '$table';")
    send_metric "postgresql_table_bloat_percent" "$BLOAT" "{table=\"$table\"}"
done

# Check Redis connectivity if available
if command -v redis-cli >/dev/null 2>&1; then
    if redis-cli -h "${REDIS_HOST:-redis}" ping >/dev/null 2>&1; then
        send_metric "redis_up" "1" ""
    else
        send_metric "redis_up" "0" ""
    fi
fi

# Output metrics for Prometheus node exporter textfile collector
if [ -d "/var/lib/node_exporter/textfile_collector" ]; then
    cp "$METRICS_FILE" "/var/lib/node_exporter/textfile_collector/db_health.prom"
fi

echo "Health check completed - metrics written to $METRICS_FILE"
'''
        
        health_script = self.monitoring_dir / "health_check.sh"
        with open(health_script, 'w') as f:
            f.write(health_check_script)
        
        os.chmod(health_script, 0o755)
        logger.info(f"Health check script created at {health_script}")
        
    def install_monitoring_stack(self):
        """Install complete monitoring stack"""
        logger.info("Installing complete monitoring stack...")
        
        try:
            # Create all configurations
            self.setup_prometheus_exporter()
            self.create_prometheus_config()
            self.create_alert_rules()
            self.create_alertmanager_config()
            self.create_grafana_dashboards()
            self.create_monitoring_compose()
            self.create_health_check_script()
            
            # Start monitoring services
            logger.info("Starting monitoring services...")
            os.chdir(self.monitoring_dir)
            subprocess.run(["docker", "compose", "up", "-d"], check=True)
            
            # Wait for services to be ready
            logger.info("Waiting for services to be ready...")
            time.sleep(30)
            
            # Verify services
            self.verify_monitoring_services()
            
            logger.info("✅ Monitoring stack installation completed!")
            self.print_access_info()
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install monitoring stack: {e}")
            raise
        except Exception as e:
            logger.error(f"Installation error: {e}")
            raise
    
    def verify_monitoring_services(self):
        """Verify monitoring services are running"""
        services = {
            'Prometheus': 'http://localhost:9090/-/healthy',
            'Alertmanager': 'http://localhost:9093/-/healthy',
            'Grafana': 'http://localhost:3001/api/health'
        }
        
        for service, url in services.items():
            try:
                import urllib.request
                urllib.request.urlopen(url, timeout=10)
                logger.info(f"✅ {service} is healthy")
            except Exception as e:
                logger.warning(f"⚠️  {service} health check failed: {e}")
    
    def print_access_info(self):
        """Print access information for monitoring services"""
        print("\n" + "="*50)
        print("🎉 MONITORING STACK READY")
        print("="*50)
        print("📊 Grafana:      http://localhost:3001 (admin/admin123)")
        print("🔥 Prometheus:   http://localhost:9090")
        print("🚨 Alertmanager: http://localhost:9093")
        print("📈 Node Exporter: http://localhost:9100")
        print("🗃️  PostgreSQL Exporter: http://localhost:9187")
        print("🔴 Redis Exporter: http://localhost:9121")
        print("="*50)
        print("\n📝 Next Steps:")
        print("1. Configure notification channels in Grafana")
        print("2. Set up SMTP for email alerts")
        print("3. Customize alert thresholds in prometheus/alerts/")
        print("4. Add custom dashboards in Grafana")
        print("5. Set up log aggregation (ELK stack)")
        print("\n🔧 Maintenance:")
        print("- Run health checks: ./monitoring/health_check.sh")
        print("- View logs: docker compose -f monitoring/docker-compose.yml logs")
        print("- Restart: docker compose -f monitoring/docker-compose.yml restart")
    
    def test_alerts(self):
        """Test alert system"""
        logger.info("Testing alert system...")
        
        # Simulate high connection alert
        test_alert = {
            "receiver": "web.hook",
            "status": "firing",
            "alerts": [{
                "status": "firing",
                "labels": {
                    "alertname": "TestAlert",
                    "severity": "warning",
                    "instance": "localhost:9187"
                },
                "annotations": {
                    "summary": "Test alert from monitoring setup",
                    "description": "This is a test alert to verify the alerting system is working"
                }
            }],
            "groupLabels": {"alertname": "TestAlert"},
            "commonLabels": {"severity": "warning"},
            "commonAnnotations": {},
            "externalURL": "http://localhost:9093"
        }
        
        try:
            import urllib.request
            import urllib.parse
            import json
            
            data = json.dumps(test_alert).encode('utf-8')
            req = urllib.request.Request(
                'http://localhost:9093/api/v1/alerts',
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    logger.info("✅ Test alert sent successfully")
                else:
                    logger.warning(f"⚠️  Test alert failed with status {response.status}")
                    
        except Exception as e:
            logger.warning(f"⚠️  Alert test failed: {e}")


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description='Database Monitoring Setup')
    parser.add_argument('--install-all', action='store_true', help='Install complete monitoring stack')
    parser.add_argument('--setup-prometheus', action='store_true', help='Setup Prometheus only')
    parser.add_argument('--create-dashboards', action='store_true', help='Create Grafana dashboards')
    parser.add_argument('--test-alerts', action='store_true', help='Test alert system')
    
    args = parser.parse_args()
    
    if not any(vars(args).values()):
        parser.print_help()
        return
    
    setup = MonitoringSetup()
    
    try:
        if args.install_all:
            setup.install_monitoring_stack()
        elif args.setup_prometheus:
            setup.setup_prometheus_exporter()
            setup.create_prometheus_config()
            setup.create_alert_rules()
        elif args.create_dashboards:
            setup.create_grafana_dashboards()
        elif args.test_alerts:
            setup.test_alerts()
            
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())