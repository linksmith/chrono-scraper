# Output values for Hetzner Cloud Infrastructure
# Chrono Scraper v2 Production Deployment

# Server Information
output "server_info" {
  description = "Main server connection information"
  value = {
    name         = hcloud_server.chrono_scraper_main.name
    ipv4_address = hcloud_server.chrono_scraper_main.ipv4_address
    ipv6_address = hcloud_server.chrono_scraper_main.ipv6_address
    server_type  = hcloud_server.chrono_scraper_main.server_type
    location     = hcloud_server.chrono_scraper_main.location
    status       = hcloud_server.chrono_scraper_main.status
  }
}

output "ssh_connection_command" {
  description = "SSH command to connect to the server"
  value       = "ssh -p ${var.firewall_ssh_port} ubuntu@${hcloud_server.chrono_scraper_main.ipv4_address}"
}

# Network Information
output "network_info" {
  description = "Network configuration details"
  value = {
    network_id    = hcloud_network.chrono_scraper_network.id
    network_range = hcloud_network.chrono_scraper_network.ip_range
    subnet_range  = hcloud_network_subnet.chrono_scraper_subnet.ip_range
    server_private_ip = "10.0.1.5"
  }
}

# Load Balancer Information
output "load_balancer_info" {
  description = "Load balancer configuration details"
  value = {
    name     = hcloud_load_balancer.chrono_scraper_lb.name
    ipv4     = hcloud_load_balancer.chrono_scraper_lb.ipv4
    ipv6     = hcloud_load_balancer.chrono_scraper_lb.ipv6
    location = hcloud_load_balancer.chrono_scraper_lb.location
    type     = hcloud_load_balancer.chrono_scraper_lb.load_balancer_type
  }
}

# Floating IP Information
output "floating_ip_info" {
  description = "Floating IP for zero-downtime deployments"
  value = {
    ip_address = hcloud_floating_ip.chrono_scraper_ip.ip_address
    name       = hcloud_floating_ip.chrono_scraper_ip.name
  }
}

# Storage Information
output "storage_info" {
  description = "Storage volume details"
  value = {
    volume_id   = hcloud_volume.chrono_scraper_data.id
    volume_name = hcloud_volume.chrono_scraper_data.name
    size_gb     = hcloud_volume.chrono_scraper_data.size
    location    = hcloud_volume.chrono_scraper_data.location
    mount_path  = "/mnt/data"
  }
}

# DNS Information (if Cloudflare is configured)
output "dns_records" {
  description = "DNS records created (if Cloudflare is configured)"
  value = var.cloudflare_zone_id != "" ? {
    domain_a_record = "${var.domain_name} -> ${hcloud_load_balancer.chrono_scraper_lb.ipv4}"
    www_cname      = "www.${var.domain_name} -> ${var.domain_name}"
    api_cname      = "api.${var.domain_name} -> ${var.domain_name}"
  } : "Cloudflare not configured - manual DNS setup required"
}

# Application URLs
output "application_urls" {
  description = "Application access URLs"
  value = {
    main_app     = "https://${var.domain_name}"
    api_endpoint = "https://api.${var.domain_name}/api/v1"
    health_check = "https://${var.domain_name}/api/v1/health"
    admin_panel  = "https://${var.domain_name}/admin"
  }
}

# Cost Breakdown
output "monthly_cost_estimate" {
  description = "Estimated monthly costs in EUR (excluding VAT)"
  value = {
    server = {
      type = var.server_type
      cost = var.server_type == "cx22" ? "3.79" : 
             var.server_type == "cx32" ? "6.80" :
             var.server_type == "cx42" ? "16.40" :
             var.server_type == "cpx21" ? "7.55" :
             var.server_type == "cax21" ? "6.49" : "6.80"
    }
    volume = {
      size_gb = var.additional_volume_size
      cost    = format("%.2f", var.additional_volume_size * 0.096)
    }
    load_balancer = {
      type = var.load_balancer_type
      cost = var.load_balancer_type == "lb11" ? "4.90" : 
             var.load_balancer_type == "lb21" ? "14.90" : "39.90"
    }
    floating_ip = "1.19"
    backup = var.backup_enabled ? format("%.2f", 
      (var.server_type == "cx22" ? 3.79 : 
       var.server_type == "cx32" ? 6.80 :
       var.server_type == "cx42" ? 16.40 :
       var.server_type == "cpx21" ? 7.55 :
       var.server_type == "cax21" ? 6.49 : 6.80) * 0.20
    ) : "0.00"
    
    # Total calculation
    total_base = format("%.2f", 
      (var.server_type == "cx22" ? 3.79 : 
       var.server_type == "cx32" ? 6.80 :
       var.server_type == "cx42" ? 16.40 :
       var.server_type == "cpx21" ? 7.55 :
       var.server_type == "cax21" ? 6.49 : 6.80) +
      (var.additional_volume_size * 0.096) +
      (var.load_balancer_type == "lb11" ? 4.90 : 
       var.load_balancer_type == "lb21" ? 14.90 : 39.90) +
      1.19 + 
      (var.backup_enabled ? 
        (var.server_type == "cx22" ? 3.79 : 
         var.server_type == "cx32" ? 6.80 :
         var.server_type == "cx42" ? 16.40 :
         var.server_type == "cpx21" ? 7.55 :
         var.server_type == "cax21" ? 6.49 : 6.80) * 0.20 : 0)
    )
    
    snapshots_estimate = "2.00"
    external_services = "0.00"  # Cloudflare free, UptimeRobot free
    
    total_estimated = format("%.2f", 
      (var.server_type == "cx22" ? 3.79 : 
       var.server_type == "cx32" ? 6.80 :
       var.server_type == "cx42" ? 16.40 :
       var.server_type == "cpx21" ? 7.55 :
       var.server_type == "cax21" ? 6.49 : 6.80) +
      (var.additional_volume_size * 0.096) +
      (var.load_balancer_type == "lb11" ? 4.90 : 
       var.load_balancer_type == "lb21" ? 14.90 : 39.90) +
      1.19 + 
      (var.backup_enabled ? 
        (var.server_type == "cx22" ? 3.79 : 
         var.server_type == "cx32" ? 6.80 :
         var.server_type == "cx42" ? 16.40 :
         var.server_type == "cpx21" ? 7.55 :
         var.server_type == "cax21" ? 6.49 : 6.80) * 0.20 : 0) +
      2.00
    )
    
    budget_remaining = format("%.2f", 50.0 - 
      ((var.server_type == "cx22" ? 3.79 : 
        var.server_type == "cx32" ? 6.80 :
        var.server_type == "cx42" ? 16.40 :
        var.server_type == "cpx21" ? 7.55 :
        var.server_type == "cax21" ? 6.49 : 6.80) +
       (var.additional_volume_size * 0.096) +
       (var.load_balancer_type == "lb11" ? 4.90 : 
        var.load_balancer_type == "lb21" ? 14.90 : 39.90) +
       1.19 + 
       (var.backup_enabled ? 
         (var.server_type == "cx22" ? 3.79 : 
          var.server_type == "cx32" ? 6.80 :
          var.server_type == "cx42" ? 16.40 :
          var.server_type == "cpx21" ? 7.55 :
          var.server_type == "cax21" ? 6.49 : 6.80) * 0.20 : 0) +
       2.00)
    )
  }
}

# Security Information
output "security_info" {
  description = "Security configuration details"
  value = {
    ssh_port        = var.firewall_ssh_port
    firewall_id     = hcloud_firewall.chrono_scraper_firewall.id
    open_ports      = ["80/tcp", "443/tcp", "${var.firewall_ssh_port}/tcp"]
    fail2ban_enabled = true
    ufw_enabled     = true
  }
}

# Deployment Information
output "deployment_info" {
  description = "Next steps for deployment"
  value = {
    step_1 = "SSH to server: ssh -p ${var.firewall_ssh_port} ubuntu@${hcloud_server.chrono_scraper_main.ipv4_address}"
    step_2 = "Clone repository to /opt/chrono-scraper"
    step_3 = "Configure .env file with production secrets"
    step_4 = "Run: docker-compose -f docker-compose.production.yml up -d"
    step_5 = "Configure SSL with: sudo certbot --nginx -d ${var.domain_name}"
    
    helpful_aliases = {
      docker_status = "dps (docker ps formatted)"
      docker_logs   = "dlogs (docker-compose logs -f)"
      docker_stats  = "dstats (docker stats formatted)"
      backup_now    = "backup-now (run backup script)"
      health_check  = "check-health (API health check)"
    }
  }
}

# Monitoring Information
output "monitoring_info" {
  description = "Monitoring and logging details"
  value = {
    system_logs     = "/mnt/data/logs/system-monitoring.log"
    backup_logs     = "/mnt/data/logs/backup.log"
    application_logs = "/mnt/data/logs/"
    backup_schedule  = "Daily at 2:00 AM UTC"
    monitoring_frequency = "Every 5 minutes"
    backup_retention = "7 days"
  }
}

# Scaling Information
output "scaling_roadmap" {
  description = "Future scaling options and costs"
  value = {
    current_capacity = {
      concurrent_users = "50-100"
      daily_users     = "500-1,000"
      scraping_jobs   = "5-10 concurrent"
      database_pages  = "Up to 1M pages"
    }
    
    next_scaling_step = "Upgrade to CX42 (€16.40/month) or add dedicated worker server"
    
    multi_server_architecture = {
      web_server      = "CX42 (€16.40/month) - Frontend + Backend"
      database_server = "CX32 (€6.80/month) - PostgreSQL + Redis"
      worker_server   = "CX32 (€6.80/month) - Celery + Firecrawl"
      total_cost     = "~€50/month for infrastructure"
    }
    
    scaling_triggers = [
      "CPU usage consistently >80%",
      "Memory usage >85%",
      "Response times >500ms",
      "Queue backlog >100 jobs"
    ]
  }
}

# Resource Limits Information
output "resource_allocation" {
  description = "Docker container resource allocation for current server"
  value = {
    server_specs = "4 vCPU, 8 GB RAM, 80 GB SSD + 100 GB Volume"
    
    container_limits = {
      postgres          = "1.5GB RAM, 1.0 CPU"
      redis            = "512MB RAM, 0.5 CPU"
      meilisearch      = "1GB RAM, 0.5 CPU"
      backend          = "1GB RAM, 1.0 CPU"
      frontend         = "256MB RAM, 0.5 CPU"
      celery_worker    = "1GB RAM, 1.0 CPU"
      firecrawl_api    = "512MB RAM, 0.5 CPU"
      firecrawl_playwright = "1.5GB RAM, 1.0 CPU"
      traefik         = "128MB RAM, 0.25 CPU"
    }
    
    total_allocation = "~7.4GB RAM, ~6 vCPUs (with burst capability)"
    system_reserved  = "600MB RAM for OS and monitoring"
  }
}