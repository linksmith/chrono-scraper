#!/usr/bin/env python3
"""
Real-time Scaling Dashboard for Chrono Scraper v2
Monitors metrics and provides scaling recommendations in a web interface
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import psutil
import aiohttp
import asyncpg
import redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from scaling.scaling_decision import ScalingDecisionTool, ScalingMetrics

app = FastAPI(title="Chrono Scraper Scaling Dashboard")

class ScalingDashboard:
    """Real-time dashboard for scaling metrics and decisions."""
    
    def __init__(self):
        self.decision_tool = ScalingDecisionTool()
        self.connections: List[WebSocket] = []
        self.current_phase = 1
        self.metrics_history: List[Dict] = []
        self.max_history = 1000  # Keep last 1000 data points
        
    async def add_connection(self, websocket: WebSocket):
        """Add WebSocket connection."""
        await websocket.accept()
        self.connections.append(websocket)
        
    async def remove_connection(self, websocket: WebSocket):
        """Remove WebSocket connection."""
        if websocket in self.connections:
            self.connections.remove(websocket)
    
    async def broadcast_metrics(self, data: Dict):
        """Broadcast metrics to all connected clients."""
        disconnected = []
        for connection in self.connections:
            try:
                await connection.send_json(data)
            except WebSocketDisconnect:
                disconnected.append(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            self.connections.remove(conn)
    
    async def collect_metrics_continuously(self):
        """Continuously collect and broadcast metrics."""
        while True:
            try:
                # Collect current metrics
                metrics = await self.decision_tool.collect_metrics()
                recommendation = self.decision_tool.generate_recommendation(
                    metrics, self.current_phase
                )
                
                # Create dashboard data
                dashboard_data = {
                    "timestamp": datetime.now().isoformat(),
                    "current_phase": self.current_phase,
                    "metrics": {
                        "cpu_usage": metrics.cpu_usage_7day_avg,
                        "memory_usage": metrics.memory_usage_percentage,
                        "memory_used_gb": metrics.memory_usage_current,
                        "memory_total_gb": metrics.memory_total,
                        "active_users": metrics.active_users_30day,
                        "database_size_gb": metrics.database_size_gb,
                        "api_requests_per_minute": metrics.api_requests_per_minute,
                        "response_time_p95": metrics.response_time_p95_ms,
                        "error_rate": metrics.error_rate_percentage,
                        "celery_queue": metrics.celery_queue_length,
                        "disk_usage": metrics.disk_usage_percentage,
                        "revenue_monthly": metrics.revenue_monthly_eur
                    },
                    "recommendation": {
                        "recommended_phase": recommendation.recommended_phase,
                        "trigger_score": recommendation.trigger_score,
                        "estimated_cost": recommendation.estimated_cost_eur,
                        "complexity": recommendation.migration_complexity,
                        "downtime_estimate": recommendation.estimated_downtime_minutes,
                        "justification": recommendation.justification[:3],
                        "should_scale": recommendation.trigger_score >= 0.7
                    },
                    "thresholds": self._get_current_thresholds(),
                    "cost_projection": self._calculate_cost_projection(metrics)
                }
                
                # Store in history
                self.metrics_history.append(dashboard_data)
                if len(self.metrics_history) > self.max_history:
                    self.metrics_history.pop(0)
                
                # Broadcast to connected clients
                await self.broadcast_metrics(dashboard_data)
                
            except Exception as e:
                print(f"Error collecting metrics: {e}")
            
            await asyncio.sleep(30)  # Update every 30 seconds
    
    def _get_current_thresholds(self) -> Dict:
        """Get scaling thresholds for current phase."""
        next_phase = self.current_phase + 1
        if next_phase in self.decision_tool.PHASE_TRIGGERS:
            return self.decision_tool.PHASE_TRIGGERS[next_phase]
        return {}
    
    def _calculate_cost_projection(self, metrics: ScalingMetrics) -> Dict:
        """Calculate cost projections for different phases."""
        projections = {}
        
        for phase in range(1, 6):
            cost = self.decision_tool.PHASE_COSTS.get(phase, 0)
            if metrics.active_users_30day > 0:
                cost_per_user = cost / metrics.active_users_30day
            else:
                cost_per_user = cost
                
            projections[f"phase_{phase}"] = {
                "monthly_cost": cost,
                "cost_per_user": cost_per_user,
                "estimated_capacity": self._estimate_capacity(phase)
            }
        
        return projections
    
    def _estimate_capacity(self, phase: int) -> Dict:
        """Estimate capacity for each phase."""
        capacities = {
            1: {"max_users": 100, "max_requests_per_min": 100, "max_scrapes": 10},
            2: {"max_users": 500, "max_requests_per_min": 500, "max_scrapes": 50},
            3: {"max_users": 2000, "max_requests_per_min": 2000, "max_scrapes": 200},
            4: {"max_users": 10000, "max_requests_per_min": 10000, "max_scrapes": 1000},
            5: {"max_users": 50000, "max_requests_per_min": 50000, "max_scrapes": 5000}
        }
        return capacities.get(phase, capacities[5])

# Global dashboard instance
dashboard = ScalingDashboard()

@app.on_event("startup")
async def startup_event():
    """Start background metrics collection."""
    asyncio.create_task(dashboard.collect_metrics_continuously())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time metrics."""
    await dashboard.add_connection(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        await dashboard.remove_connection(websocket)

@app.get("/", response_class=HTMLResponse)
async def dashboard_page():
    """Main dashboard page."""
    return HTML_DASHBOARD

@app.get("/api/metrics/history")
async def get_metrics_history(hours: int = 24):
    """Get historical metrics data."""
    cutoff = datetime.now() - timedelta(hours=hours)
    
    filtered_history = [
        point for point in dashboard.metrics_history
        if datetime.fromisoformat(point["timestamp"]) >= cutoff
    ]
    
    return {"history": filtered_history, "count": len(filtered_history)}

@app.get("/api/phase/current")
async def get_current_phase():
    """Get current deployment phase."""
    return {"current_phase": dashboard.current_phase}

@app.post("/api/phase/set/{phase}")
async def set_current_phase(phase: int):
    """Set current deployment phase."""
    if 1 <= phase <= 5:
        dashboard.current_phase = phase
        return {"success": True, "current_phase": phase}
    return {"success": False, "error": "Phase must be between 1 and 5"}

@app.get("/api/scaling/analyze")
async def analyze_scaling():
    """Get detailed scaling analysis."""
    metrics = await dashboard.decision_tool.collect_metrics()
    recommendation = dashboard.decision_tool.generate_recommendation(
        metrics, dashboard.current_phase
    )
    
    return {
        "metrics": metrics.__dict__,
        "recommendation": recommendation.__dict__,
        "report": dashboard.decision_tool.format_report(metrics, recommendation)
    }

# HTML Dashboard Template
HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chrono Scraper Scaling Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            line-height: 1.6;
        }
        
        .header {
            background: #1e293b;
            padding: 1rem 2rem;
            border-bottom: 2px solid #334155;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        
        .header h1 {
            color: #3b82f6;
            font-size: 1.5rem;
            font-weight: 700;
        }
        
        .phase-indicator {
            display: inline-block;
            background: #059669;
            color: white;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.875rem;
            font-weight: 600;
            margin-left: 1rem;
        }
        
        .dashboard {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            padding: 1.5rem;
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 0.5rem;
            padding: 1.5rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        
        .card h2 {
            color: #f1f5f9;
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1rem;
            border-bottom: 1px solid #334155;
            padding-bottom: 0.5rem;
        }
        
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1rem;
            margin-bottom: 1rem;
        }
        
        .metric {
            text-align: center;
            padding: 1rem;
            background: #0f172a;
            border-radius: 0.375rem;
            border: 1px solid #334155;
        }
        
        .metric-value {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
        }
        
        .metric-label {
            font-size: 0.875rem;
            color: #94a3b8;
        }
        
        .metric.warning .metric-value {
            color: #f59e0b;
        }
        
        .metric.danger .metric-value {
            color: #ef4444;
        }
        
        .metric.success .metric-value {
            color: #10b981;
        }
        
        .recommendation {
            grid-column: span 2;
        }
        
        .recommendation-content {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 1.5rem;
            align-items: center;
        }
        
        .recommendation-info h3 {
            color: #f1f5f9;
            margin-bottom: 0.5rem;
        }
        
        .recommendation-score {
            font-size: 3rem;
            font-weight: 700;
            text-align: center;
            padding: 1rem;
            border-radius: 0.5rem;
            min-width: 120px;
        }
        
        .recommendation-score.low {
            background: #059669;
            color: white;
        }
        
        .recommendation-score.medium {
            background: #f59e0b;
            color: white;
        }
        
        .recommendation-score.high {
            background: #ef4444;
            color: white;
        }
        
        .chart-container {
            position: relative;
            height: 300px;
            margin-top: 1rem;
        }
        
        .status {
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.75rem;
            font-weight: 600;
        }
        
        .status.connected {
            background: #059669;
            color: white;
        }
        
        .status.disconnected {
            background: #ef4444;
            color: white;
        }
        
        .justification {
            margin-top: 1rem;
        }
        
        .justification li {
            margin-bottom: 0.5rem;
            color: #cbd5e1;
        }
        
        @media (max-width: 768px) {
            .dashboard {
                grid-template-columns: 1fr;
            }
            
            .recommendation {
                grid-column: span 1;
            }
            
            .metrics-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .recommendation-content {
                grid-template-columns: 1fr;
                text-align: center;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Chrono Scraper Scaling Dashboard</h1>
        <span class="phase-indicator" id="phase-indicator">Phase 1</span>
        <span class="status" id="connection-status">Connecting...</span>
    </div>
    
    <div class="dashboard">
        <div class="card">
            <h2>System Metrics</h2>
            <div class="metrics-grid">
                <div class="metric" id="cpu-metric">
                    <div class="metric-value" id="cpu-value">--</div>
                    <div class="metric-label">CPU Usage (%)</div>
                </div>
                <div class="metric" id="memory-metric">
                    <div class="metric-value" id="memory-value">--</div>
                    <div class="metric-label">Memory Usage (%)</div>
                </div>
                <div class="metric" id="disk-metric">
                    <div class="metric-value" id="disk-value">--</div>
                    <div class="metric-label">Disk Usage (%)</div>
                </div>
            </div>
            
            <div class="metrics-grid">
                <div class="metric">
                    <div class="metric-value" id="users-value">--</div>
                    <div class="metric-label">Active Users</div>
                </div>
                <div class="metric">
                    <div class="metric-value" id="db-size-value">--</div>
                    <div class="metric-label">Database (GB)</div>
                </div>
                <div class="metric">
                    <div class="metric-value" id="queue-value">--</div>
                    <div class="metric-label">Queue Length</div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>Performance Metrics</h2>
            <div class="metrics-grid">
                <div class="metric" id="response-time-metric">
                    <div class="metric-value" id="response-time-value">--</div>
                    <div class="metric-label">Response Time (ms)</div>
                </div>
                <div class="metric" id="error-rate-metric">
                    <div class="metric-value" id="error-rate-value">--</div>
                    <div class="metric-label">Error Rate (%)</div>
                </div>
                <div class="metric">
                    <div class="metric-value" id="requests-value">--</div>
                    <div class="metric-label">Requests/min</div>
                </div>
            </div>
            
            <div class="chart-container">
                <canvas id="performance-chart"></canvas>
            </div>
        </div>
        
        <div class="card recommendation">
            <h2>Scaling Recommendation</h2>
            <div class="recommendation-content">
                <div class="recommendation-info">
                    <h3 id="recommendation-title">Analyzing...</h3>
                    <p id="recommendation-description">Collecting metrics and analyzing scaling needs...</p>
                    <ul class="justification" id="justification-list">
                    </ul>
                    <div style="margin-top: 1rem;">
                        <strong>Estimated Cost:</strong> €<span id="estimated-cost">--</span>/month
                    </div>
                </div>
                <div class="recommendation-score" id="recommendation-score">
                    --
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>Historical Trends</h2>
            <div class="chart-container">
                <canvas id="trends-chart"></canvas>
            </div>
        </div>
    </div>
    
    <script>
        // WebSocket connection
        let socket;
        let performanceChart;
        let trendsChart;
        let metricsHistory = [];
        
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
            
            socket.onopen = () => {
                document.getElementById('connection-status').textContent = 'Connected';
                document.getElementById('connection-status').className = 'status connected';
            };
            
            socket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                updateDashboard(data);
            };
            
            socket.onclose = () => {
                document.getElementById('connection-status').textContent = 'Disconnected';
                document.getElementById('connection-status').className = 'status disconnected';
                // Reconnect after 5 seconds
                setTimeout(connectWebSocket, 5000);
            };
            
            socket.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }
        
        function updateDashboard(data) {
            // Update phase indicator
            document.getElementById('phase-indicator').textContent = `Phase ${data.current_phase}`;
            
            // Update system metrics
            updateMetric('cpu', data.metrics.cpu_usage, [70, 85]);
            updateMetric('memory', data.metrics.memory_usage, [75, 90]);
            updateMetric('disk', data.metrics.disk_usage, [80, 95]);
            
            // Update other metrics
            document.getElementById('users-value').textContent = data.metrics.active_users;
            document.getElementById('db-size-value').textContent = data.metrics.database_size_gb.toFixed(1);
            document.getElementById('queue-value').textContent = data.metrics.celery_queue;
            
            // Update performance metrics
            updateMetric('response-time', data.metrics.response_time_p95, [1000, 2000], 'ms');
            updateMetric('error-rate', data.metrics.error_rate, [0.5, 1.0], '%');
            document.getElementById('requests-value').textContent = Math.round(data.metrics.api_requests_per_minute);
            
            // Update recommendation
            updateRecommendation(data.recommendation);
            
            // Store history and update charts
            metricsHistory.push({
                timestamp: new Date(data.timestamp),
                cpu: data.metrics.cpu_usage,
                memory: data.metrics.memory_usage,
                responseTime: data.metrics.response_time_p95,
                errorRate: data.metrics.error_rate,
                triggerScore: data.recommendation.trigger_score
            });
            
            // Keep last 100 points
            if (metricsHistory.length > 100) {
                metricsHistory.shift();
            }
            
            updateCharts();
        }
        
        function updateMetric(id, value, thresholds, suffix = '%') {
            const element = document.getElementById(`${id}-value`);
            const metricElement = document.getElementById(`${id}-metric`);
            
            element.textContent = suffix === 'ms' ? Math.round(value) : value.toFixed(1);
            
            // Update styling based on thresholds
            metricElement.classList.remove('warning', 'danger', 'success');
            if (value >= thresholds[1]) {
                metricElement.classList.add('danger');
            } else if (value >= thresholds[0]) {
                metricElement.classList.add('warning');
            } else {
                metricElement.classList.add('success');
            }
        }
        
        function updateRecommendation(recommendation) {
            const titleElement = document.getElementById('recommendation-title');
            const descElement = document.getElementById('recommendation-description');
            const scoreElement = document.getElementById('recommendation-score');
            const justificationElement = document.getElementById('justification-list');
            const costElement = document.getElementById('estimated-cost');
            
            if (recommendation.should_scale) {
                titleElement.textContent = `Scale to Phase ${recommendation.recommended_phase}`;
                descElement.textContent = `Scaling recommended with ${recommendation.complexity.toLowerCase()} complexity`;
            } else {
                titleElement.textContent = 'Current Phase Sufficient';
                descElement.textContent = 'No immediate scaling required';
            }
            
            // Update score
            const score = Math.round(recommendation.trigger_score * 100);
            scoreElement.textContent = `${score}%`;
            
            scoreElement.classList.remove('low', 'medium', 'high');
            if (score >= 70) {
                scoreElement.classList.add('high');
            } else if (score >= 40) {
                scoreElement.classList.add('medium');
            } else {
                scoreElement.classList.add('low');
            }
            
            // Update justification
            justificationElement.innerHTML = '';
            recommendation.justification.forEach(reason => {
                const li = document.createElement('li');
                li.textContent = reason;
                justificationElement.appendChild(li);
            });
            
            // Update cost
            costElement.textContent = recommendation.estimated_cost.toFixed(2);
        }
        
        function initCharts() {
            // Performance chart
            const perfCtx = document.getElementById('performance-chart').getContext('2d');
            performanceChart = new Chart(perfCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'CPU %',
                        data: [],
                        borderColor: '#3b82f6',
                        tension: 0.1
                    }, {
                        label: 'Memory %',
                        data: [],
                        borderColor: '#10b981',
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 100
                        }
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: '#e2e8f0'
                            }
                        }
                    }
                }
            });
            
            // Trends chart
            const trendsCtx = document.getElementById('trends-chart').getContext('2d');
            trendsChart = new Chart(trendsCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Trigger Score',
                        data: [],
                        borderColor: '#f59e0b',
                        tension: 0.1,
                        yAxisID: 'y1'
                    }, {
                        label: 'Response Time (ms)',
                        data: [],
                        borderColor: '#ef4444',
                        tension: 0.1,
                        yAxisID: 'y2'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y1: {
                            type: 'linear',
                            position: 'left',
                            beginAtZero: true,
                            max: 1
                        },
                        y2: {
                            type: 'linear',
                            position: 'right',
                            beginAtZero: true
                        }
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: '#e2e8f0'
                            }
                        }
                    }
                }
            });
        }
        
        function updateCharts() {
            if (metricsHistory.length === 0) return;
            
            const labels = metricsHistory.map(point => 
                point.timestamp.toLocaleTimeString()
            );
            
            // Update performance chart
            performanceChart.data.labels = labels;
            performanceChart.data.datasets[0].data = metricsHistory.map(p => p.cpu);
            performanceChart.data.datasets[1].data = metricsHistory.map(p => p.memory);
            performanceChart.update('none');
            
            // Update trends chart
            trendsChart.data.labels = labels;
            trendsChart.data.datasets[0].data = metricsHistory.map(p => p.triggerScore);
            trendsChart.data.datasets[1].data = metricsHistory.map(p => p.responseTime);
            trendsChart.update('none');
        }
        
        // Initialize dashboard
        document.addEventListener('DOMContentLoaded', () => {
            initCharts();
            connectWebSocket();
        });
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Chrono Scraper Scaling Dashboard")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    parser.add_argument("--current-phase", type=int, default=1, 
                       help="Current deployment phase")
    
    args = parser.parse_args()
    
    dashboard.current_phase = args.current_phase
    
    print(f"🚀 Starting Scaling Dashboard on http://{args.host}:{args.port}")
    print(f"📊 Current Phase: {args.current_phase}")
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info"
    )