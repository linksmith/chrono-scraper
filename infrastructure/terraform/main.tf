# Hetzner Cloud Production Infrastructure for Chrono Scraper v2
# Budget: €50/month maximum
# Architecture: Single server with horizontal scaling capability

terraform {
  required_version = ">= 1.0"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.44"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

# Configure the Hetzner Cloud Provider
provider "hcloud" {
  token = var.hcloud_token
}

# Configure Cloudflare Provider
provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# Variables
variable "hcloud_token" {
  description = "Hetzner Cloud API Token"
  type        = string
  sensitive   = true
}

variable "cloudflare_api_token" {
  description = "Cloudflare API Token"
  type        = string
  sensitive   = true
}

variable "cloudflare_zone_id" {
  description = "Cloudflare Zone ID for chronoscraper.com"
  type        = string
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = "chronoscraper.com"
}

variable "environment" {
  description = "Environment name (production/staging)"
  type        = string
  default     = "production"
}

variable "ssh_public_key" {
  description = "SSH public key for server access"
  type        = string
}

# SSH Key
resource "hcloud_ssh_key" "chrono_scraper_key" {
  name       = "chrono-scraper-${var.environment}"
  public_key = var.ssh_public_key
}

# Network (for future scaling)
resource "hcloud_network" "chrono_scraper_network" {
  name     = "chrono-scraper-${var.environment}"
  ip_range = "10.0.0.0/16"
}

resource "hcloud_network_subnet" "chrono_scraper_subnet" {
  network_id   = hcloud_network.chrono_scraper_network.id
  type         = "cloud"
  network_zone = "eu-central"
  ip_range     = "10.0.1.0/24"
}

# Firewall
resource "hcloud_firewall" "chrono_scraper_firewall" {
  name = "chrono-scraper-${var.environment}"

  rule {
    direction = "in"
    port      = "22"
    protocol  = "tcp"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction = "in"
    port      = "80"
    protocol  = "tcp"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction = "in"
    port      = "443"
    protocol  = "tcp"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # ICMP
  rule {
    direction = "in"
    protocol  = "icmp"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # Allow all outbound
  rule {
    direction      = "out"
    port           = "any"
    protocol       = "tcp"
    destination_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction      = "out"
    port           = "any"
    protocol       = "udp"
    destination_ips = ["0.0.0.0/0", "::/0"]
  }
}

# Primary Server (CX32: 4 vCPU, 8 GB RAM, 80 GB SSD)
resource "hcloud_server" "chrono_scraper_main" {
  name        = "chrono-scraper-${var.environment}-main"
  image       = "ubuntu-22.04"
  server_type = "cx32"
  location    = "nbg1" # Nuremberg
  
  ssh_keys = [hcloud_ssh_key.chrono_scraper_key.id]
  firewall_ids = [hcloud_firewall.chrono_scraper_firewall.id]

  network {
    network_id = hcloud_network.chrono_scraper_network.id
    ip         = "10.0.1.5"
  }

  user_data = templatefile("${path.module}/cloud-init.yml", {
    domain_name = var.domain_name
    environment = var.environment
  })

  labels = {
    environment = var.environment
    role        = "main"
    cost-center = "infrastructure"
  }
}

# Additional Storage Volume
resource "hcloud_volume" "chrono_scraper_data" {
  name     = "chrono-scraper-${var.environment}-data"
  size     = 100
  location = "nbg1"
  format   = "ext4"
  
  labels = {
    environment = var.environment
    purpose     = "data-storage"
  }
}

# Attach volume to server
resource "hcloud_volume_attachment" "chrono_scraper_data_attachment" {
  volume_id = hcloud_volume.chrono_scraper_data.id
  server_id = hcloud_server.chrono_scraper_main.id
  automount = true
}

# Floating IP for zero-downtime deployments
resource "hcloud_floating_ip" "chrono_scraper_ip" {
  type      = "ipv4"
  location  = "nbg1"
  name      = "chrono-scraper-${var.environment}-ip"
  
  labels = {
    environment = var.environment
    purpose     = "load-balancing"
  }
}

# Assign floating IP to server
resource "hcloud_floating_ip_assignment" "chrono_scraper_ip_assignment" {
  floating_ip_id = hcloud_floating_ip.chrono_scraper_ip.id
  server_id      = hcloud_server.chrono_scraper_main.id
}

# Load Balancer (for SSL termination and future scaling)
resource "hcloud_load_balancer" "chrono_scraper_lb" {
  name               = "chrono-scraper-${var.environment}-lb"
  load_balancer_type = "lb11"
  location           = "nbg1"
  
  labels = {
    environment = var.environment
    purpose     = "load-balancing"
  }
}

# Load Balancer Network
resource "hcloud_load_balancer_network" "chrono_scraper_lb_network" {
  load_balancer_id = hcloud_load_balancer.chrono_scraper_lb.id
  network_id       = hcloud_network.chrono_scraper_network.id
  ip               = "10.0.1.10"
}

# Load Balancer Target
resource "hcloud_load_balancer_target" "chrono_scraper_lb_target" {
  type             = "server"
  load_balancer_id = hcloud_load_balancer.chrono_scraper_lb.id
  server_id        = hcloud_server.chrono_scraper_main.id
  use_private_ip   = true
}

# Load Balancer Services
resource "hcloud_load_balancer_service" "chrono_scraper_http" {
  load_balancer_id = hcloud_load_balancer.chrono_scraper_lb.id
  protocol         = "http"
  listen_port      = 80
  destination_port = 80

  health_check {
    protocol = "http"
    port     = 80
    interval = 15
    timeout  = 10
    retries  = 3
    http {
      path         = "/api/v1/health"
      status_codes = ["200"]
    }
  }
}

resource "hcloud_load_balancer_service" "chrono_scraper_https" {
  load_balancer_id = hcloud_load_balancer.chrono_scraper_lb.id
  protocol         = "https"
  listen_port      = 443
  destination_port = 443

  health_check {
    protocol = "http"
    port     = 80
    interval = 15
    timeout  = 10
    retries  = 3
    http {
      path         = "/api/v1/health"
      status_codes = ["200"]
    }
  }

  http {
    redirect_http = true
    sticky_sessions = true
  }
}

# Cloudflare DNS Records
resource "cloudflare_record" "chrono_scraper_a" {
  zone_id = var.cloudflare_zone_id
  name    = "@"
  value   = hcloud_load_balancer.chrono_scraper_lb.ipv4
  type    = "A"
  ttl     = 300
}

resource "cloudflare_record" "chrono_scraper_www" {
  zone_id = var.cloudflare_zone_id
  name    = "www"
  value   = var.domain_name
  type    = "CNAME"
  ttl     = 300
}

resource "cloudflare_record" "chrono_scraper_api" {
  zone_id = var.cloudflare_zone_id
  name    = "api"
  value   = var.domain_name
  type    = "CNAME"
  ttl     = 300
}

# Outputs
output "server_ipv4_address" {
  description = "IPv4 address of the main server"
  value       = hcloud_server.chrono_scraper_main.ipv4_address
}

output "server_ipv6_address" {
  description = "IPv6 address of the main server"
  value       = hcloud_server.chrono_scraper_main.ipv6_address
}

output "floating_ip" {
  description = "Floating IP for zero-downtime deployments"
  value       = hcloud_floating_ip.chrono_scraper_ip.ip_address
}

output "load_balancer_ipv4" {
  description = "Load balancer IPv4 address"
  value       = hcloud_load_balancer.chrono_scraper_lb.ipv4
}

output "load_balancer_ipv6" {
  description = "Load balancer IPv6 address"
  value       = hcloud_load_balancer.chrono_scraper_lb.ipv6
}

output "volume_id" {
  description = "Data volume ID"
  value       = hcloud_volume.chrono_scraper_data.id
}

output "network_id" {
  description = "Network ID for scaling"
  value       = hcloud_network.chrono_scraper_network.id
}

# Cost Estimation (Monthly)
output "estimated_monthly_cost_eur" {
  description = "Estimated monthly cost in EUR"
  value = {
    server           = "6.80"
    volume_100gb     = "9.60"
    load_balancer    = "4.90"
    floating_ip      = "1.19"
    backup_estimate  = "1.36"
    snapshot_estimate = "2.00"
    total           = "25.85"
    remaining_budget = "24.15"
  }
}