# Variables for Hetzner Cloud Infrastructure
# Chrono Scraper v2 Production Deployment

variable "hcloud_token" {
  description = "Hetzner Cloud API Token - Get from https://console.hetzner.cloud/projects/[project]/security/tokens"
  type        = string
  sensitive   = true
  validation {
    condition     = length(var.hcloud_token) > 0
    error_message = "Hetzner Cloud API token must be provided."
  }
}

variable "cloudflare_api_token" {
  description = "Cloudflare API Token - Get from https://dash.cloudflare.com/profile/api-tokens"
  type        = string
  sensitive   = true
  default     = ""
}

variable "cloudflare_zone_id" {
  description = "Cloudflare Zone ID for your domain"
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Primary domain name for the application"
  type        = string
  default     = "chronoscraper.com"
  validation {
    condition     = can(regex("^[a-z0-9.-]+\\.[a-z]{2,}$", var.domain_name))
    error_message = "Domain name must be a valid domain format."
  }
}

variable "environment" {
  description = "Environment name (production, staging, development)"
  type        = string
  default     = "production"
  validation {
    condition     = contains(["production", "staging", "development"], var.environment)
    error_message = "Environment must be one of: production, staging, development."
  }
}

variable "ssh_public_key" {
  description = "SSH public key for server access (contents of ~/.ssh/id_rsa.pub or similar)"
  type        = string
  validation {
    condition     = can(regex("^ssh-(rsa|dss|ecdsa|ed25519)", var.ssh_public_key))
    error_message = "SSH public key must be in valid SSH public key format."
  }
}

variable "server_type" {
  description = "Hetzner server type for the main application server"
  type        = string
  default     = "cx32"
  validation {
    condition = contains([
      "cx22", "cx32", "cx42", "cx52",  # Intel CX series
      "cpx21", "cpx31", "cpx41", "cpx51",  # AMD CPX series
      "cax21", "cax31", "cax41"  # ARM CAX series
    ], var.server_type)
    error_message = "Server type must be a valid Hetzner Cloud server type within budget constraints."
  }
}

variable "server_location" {
  description = "Hetzner data center location"
  type        = string
  default     = "nbg1"
  validation {
    condition = contains([
      "nbg1",   # Nuremberg, Germany
      "hel1",   # Helsinki, Finland
      "fsn1",   # Falkenstein, Germany
      "ash",    # Ashburn, VA (US)
      "hil"     # Hillsboro, OR (US)
    ], var.server_location)
    error_message = "Location must be a valid Hetzner data center location."
  }
}

variable "additional_volume_size" {
  description = "Size of additional storage volume in GB"
  type        = number
  default     = 100
  validation {
    condition     = var.additional_volume_size >= 10 && var.additional_volume_size <= 10000
    error_message = "Volume size must be between 10 GB and 10,000 GB."
  }
}

variable "backup_enabled" {
  description = "Enable automatic backups (adds ~20% to server cost)"
  type        = bool
  default     = true
}

variable "network_zone" {
  description = "Network zone for the private network"
  type        = string
  default     = "eu-central"
  validation {
    condition = contains([
      "eu-central",
      "us-east",
      "us-west"
    ], var.network_zone)
    error_message = "Network zone must be a valid Hetzner network zone."
  }
}

variable "load_balancer_type" {
  description = "Type of load balancer to provision"
  type        = string
  default     = "lb11"
  validation {
    condition = contains([
      "lb11",   # €4.90/month - 1 Gbps, 20TB traffic
      "lb21",   # €14.90/month - 5 Gbps, 20TB traffic
      "lb31"    # €39.90/month - 10 Gbps, 20TB traffic
    ], var.load_balancer_type)
    error_message = "Load balancer type must be a valid Hetzner load balancer type."
  }
}

variable "enable_ipv6" {
  description = "Enable IPv6 support"
  type        = bool
  default     = true
}

variable "firewall_ssh_port" {
  description = "Custom SSH port for enhanced security"
  type        = number
  default     = 2222
  validation {
    condition     = var.firewall_ssh_port >= 1024 && var.firewall_ssh_port <= 65535
    error_message = "SSH port must be between 1024 and 65535."
  }
}

variable "monitoring_enabled" {
  description = "Enable enhanced monitoring and alerting"
  type        = bool
  default     = true
}

variable "auto_scaling_enabled" {
  description = "Prepare infrastructure for auto-scaling (affects network setup)"
  type        = bool
  default     = false
}

# Cost estimation variables
variable "budget_alert_threshold" {
  description = "Monthly budget threshold in EUR for alerts"
  type        = number
  default     = 45
  validation {
    condition     = var.budget_alert_threshold > 0 && var.budget_alert_threshold <= 100
    error_message = "Budget alert threshold must be between 1 and 100 EUR."
  }
}

# Scaling configuration
variable "scaling_tier" {
  description = "Infrastructure scaling tier (single, multi-server, multi-region)"
  type        = string
  default     = "single"
  validation {
    condition     = contains(["single", "multi-server", "multi-region"], var.scaling_tier)
    error_message = "Scaling tier must be: single, multi-server, or multi-region."
  }
}

# Database configuration
variable "postgres_version" {
  description = "PostgreSQL version for Docker container"
  type        = string
  default     = "15"
}

variable "redis_version" {
  description = "Redis version for Docker container"
  type        = string
  default     = "7-alpine"
}

variable "meilisearch_version" {
  description = "Meilisearch version for Docker container"
  type        = string
  default     = "v1.6"
}

# Application configuration
variable "app_environment" {
  description = "Application environment variables"
  type        = map(string)
  default     = {}
  sensitive   = true
}

# Notification settings
variable "alert_email" {
  description = "Email address for infrastructure alerts"
  type        = string
  default     = ""
  validation {
    condition = var.alert_email == "" || can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", var.alert_email))
    error_message = "Alert email must be a valid email address or empty."
  }
}

variable "slack_webhook_url" {
  description = "Slack webhook URL for notifications"
  type        = string
  default     = ""
  sensitive   = true
}