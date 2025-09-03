# Archive Sources User Guide

## Table of Contents
- [What are Archive Sources?](#what-are-archive-sources)
- [Getting Started](#getting-started)
- [Archive Source Options](#archive-source-options)
- [Selecting Archive Sources](#selecting-archive-sources)
- [Use Case Recommendations](#use-case-recommendations)
- [Performance Considerations](#performance-considerations)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

## What are Archive Sources?

Archive sources are the different web archive services that Chrono Scraper can query to find historical snapshots of web pages. Instead of relying on a single source, Chrono Scraper now supports multiple archive sources with intelligent routing and automatic fallback capabilities.

### Why Multiple Sources Matter

- **Reliability**: If one archive is experiencing issues (like 522 errors), the system can automatically switch to another source
- **Coverage**: Different archives capture different content at different times
- **Performance**: Some archives may be faster for certain types of queries
- **Availability**: Ensures your research continues even if one service is temporarily unavailable

## Getting Started

### Selecting Your Archive Source

When creating a new project, you'll see archive source options in the project configuration:

1. **Wayback Machine** - The Internet Archive's comprehensive historical web archive
2. **Common Crawl** - Open source web crawl data with monthly snapshots  
3. **Hybrid Mode** - Intelligently uses both sources with automatic fallback

### Default Settings

- **New Projects**: Default to **Hybrid Mode** for maximum reliability
- **Fallback**: Enabled by default - automatically switches sources on failures
- **Retry Logic**: Built-in exponential backoff and circuit breaker protection

## Archive Source Options

### 🔵 Wayback Machine
The Internet Archive's Wayback Machine provides the most comprehensive historical web archive dating back to 1996.

**Best For:**
- Historical research requiring maximum time range coverage
- Academic research projects
- Long-term trend analysis
- Government and institutional website analysis

**Characteristics:**
- **Coverage**: 1996 - present
- **Update Frequency**: Continuous crawling
- **Strengths**: Comprehensive coverage, long history, high-quality metadata
- **Considerations**: May experience 522 timeout errors during peak usage

**Example Use Cases:**
- Tracking policy changes on government websites over decades
- Academic research on web evolution
- Legal research requiring historical evidence
- Journalism investigations with long timelines

### 🟢 Common Crawl
Common Crawl provides open source web crawl data with regular monthly snapshots.

**Best For:**
- Recent content analysis (2010 - present)
- Large-scale data processing
- Performance-critical applications
- Modern web content research

**Characteristics:**
- **Coverage**: 2010 - present
- **Update Frequency**: Monthly snapshots
- **Strengths**: Fast queries, open data, reliable infrastructure
- **Considerations**: Less historical depth than Wayback Machine

**Example Use Cases:**
- Monitoring recent news and media changes
- E-commerce competitive analysis
- Social media trend research
- Modern web technology adoption studies

### 🟡 Hybrid Mode (Recommended)
Intelligent routing that automatically selects the best available source and provides seamless fallback.

**Best For:**
- Production applications requiring maximum reliability
- Research projects that need both historical depth and reliability
- General-purpose web archival research
- Mission-critical investigations

**How It Works:**
1. Starts with the highest priority source (usually Wayback Machine)
2. Monitors for failures (522 errors, timeouts, rate limits)
3. Automatically switches to fallback source (Common Crawl)
4. Provides transparent user experience

**Benefits:**
- **Maximum Reliability**: Continues working even if one source fails
- **Best Coverage**: Combines advantages of multiple sources
- **Performance Optimization**: Circuit breakers prevent repeated failed attempts
- **Zero Downtime**: Seamless switching between sources

## Selecting Archive Sources

### During Project Creation

1. **Navigate to Project Creation**: Click "Create New Project"
2. **Configure Target Settings**: Set your domains and date ranges
3. **Choose Archive Source**: 
   - Select **Hybrid** for maximum reliability (recommended)
   - Select **Wayback Machine** for maximum historical coverage
   - Select **Common Crawl** for recent content and performance
4. **Enable Fallback**: Keep fallback enabled unless you specifically need single-source data

### Advanced Configuration

For power users, additional configuration options are available:

```json
{
  "archive_source": "hybrid",
  "fallback_enabled": true,
  "archive_config": {
    "fallback_strategy": "circuit_breaker",
    "fallback_delay_seconds": 1.0,
    "wayback_machine": {
      "timeout_seconds": 120,
      "max_retries": 3,
      "page_size": 5000
    },
    "common_crawl": {
      "timeout_seconds": 180,
      "max_retries": 5,
      "page_size": 5000
    }
  }
}
```

## Use Case Recommendations

### 📚 Academic Research
**Recommended**: **Hybrid Mode**
- Provides maximum historical coverage from Wayback Machine
- Ensures reliability through fallback to Common Crawl
- Circuit breaker prevents research delays from server issues

### 📰 Journalism & Investigation
**Recommended**: **Hybrid Mode**
- Critical that research continues uninterrupted
- May need both recent snapshots and historical context
- Automatic fallback ensures deadline-sensitive work proceeds

### 🏛️ Government & Policy Research
**Recommended**: **Wayback Machine** or **Hybrid Mode**
- Government sites have long histories requiring deep coverage
- Policy changes often span decades
- Wayback Machine has comprehensive government site coverage

### 💼 Business & Competitive Intelligence
**Recommended**: **Common Crawl** or **Hybrid Mode**
- Focus on recent competitive activities and changes
- Performance important for regular monitoring
- Common Crawl's monthly snapshots sufficient for business cycles

### 🔍 Large-Scale Analysis
**Recommended**: **Hybrid Mode**
- Large projects cannot afford single points of failure
- Performance optimization through intelligent routing
- Statistical analyses benefit from maximum data availability

### 🚀 Performance-Critical Applications
**Recommended**: **Common Crawl**
- Fastest query performance
- Reliable infrastructure with predictable response times
- Monthly snapshot model provides consistent data access patterns

## Performance Considerations

### Query Performance

**Wayback Machine**:
- Response Time: 5-30 seconds typical
- Peak Hours: May experience slower responses during US business hours
- Large Queries: May timeout on very broad domain queries

**Common Crawl**:
- Response Time: 2-15 seconds typical
- Consistency: More predictable response times
- Rate Limits: Generous rate limits for reasonable usage

**Hybrid Mode**:
- Initial Response: Performance of primary source
- Fallback Impact: 1-2 second delay when switching sources
- Circuit Breaker: Prevents slow responses from repeated failed attempts

### Optimization Tips

1. **Use Hybrid Mode**: Best balance of performance and reliability
2. **Narrow Date Ranges**: Smaller date ranges improve response times
3. **Domain Specificity**: Specific domains perform better than broad searches
4. **Monitor Circuit Breakers**: System automatically optimizes based on source health

### Resource Usage

The multi-source system uses slightly more resources due to:
- Circuit breaker monitoring
- Performance metrics tracking
- Intelligent routing logic

This overhead is minimal (< 5%) and provides significant reliability benefits.

## Troubleshooting

### Common Issues

#### Archive Source Failure
**Symptoms**: "All configured archive sources failed" error

**Solutions**:
1. **Check Hybrid Mode**: Switch to Hybrid mode if using single source
2. **Verify Internet Connection**: Ensure your connection can reach archive APIs
3. **Try Smaller Date Range**: Large ranges may timeout
4. **Check Status Page**: Visit archive service status pages for outages

#### Slow Performance
**Symptoms**: Queries taking longer than expected

**Solutions**:
1. **Switch to Common Crawl**: Generally faster for recent content
2. **Use Hybrid Mode**: Circuit breakers prevent slow repeated attempts
3. **Narrow Query Scope**: Reduce date range or domain specificity
4. **Check Peak Hours**: Avoid US business hours for Wayback Machine

#### 522 Timeout Errors
**Symptoms**: "522 Connection timeout" errors from Wayback Machine

**Solutions**:
1. **Enable Hybrid Mode**: Automatic fallback to Common Crawl
2. **Wait and Retry**: 522 errors are usually temporary
3. **Use Circuit Breaker**: System automatically stops attempting failed source
4. **Try Off-Peak Hours**: Early morning or late evening often work better

#### Partial Results
**Symptoms**: Fewer results than expected

**Solutions**:
1. **Check Date Ranges**: Ensure dates align with archive coverage
2. **Verify Domain Format**: Use proper domain format (example.com, not www.example.com)
3. **Review Match Type**: Ensure match type (domain/prefix/exact) is correct
4. **Try Alternative Source**: Different archives may have different coverage

### Getting Help

#### System Status
Check the health status of archive sources in the monitoring dashboard:
- Circuit breaker states
- Success rates per source
- Recent error patterns

#### Logs and Diagnostics
Review application logs for detailed error information:
```bash
# Check backend logs
docker compose logs -f backend

# Monitor specific archive source
docker compose logs -f backend | grep -i "archive"
```

#### Performance Metrics
Monitor archive source performance in the admin dashboard:
- Success rates by source
- Average response times
- Error frequency and patterns

## FAQ

### Q: Which archive source should I use?
**A**: For most users, **Hybrid Mode** is recommended as it provides the best combination of reliability, coverage, and performance.

### Q: What happens when an archive source fails?
**A**: In Hybrid Mode, the system automatically switches to an alternative source with a brief delay (1-2 seconds). You'll see a notification about the fallback in the logs.

### Q: Can I change archive sources for existing projects?
**A**: Archive source selection is made during project creation. For existing projects, create a new project with your preferred archive source settings.

### Q: Do different archive sources return different results?
**A**: Yes, different archives may have captured different snapshots at different times. However, the CDX record format is standardized, so the data structure remains consistent.

### Q: How does the circuit breaker work?
**A**: The circuit breaker monitors failure rates for each archive source. When failures exceed a threshold (typically 5 failures), it temporarily stops attempting that source to prevent wasted time. It automatically retests the source after a timeout period.

### Q: What are the costs of using multiple archive sources?
**A**: Archive source queries are generally free, but they do consume bandwidth and processing time. The intelligent routing actually reduces waste by avoiding repeated failed attempts.

### Q: Can I see which archive source was used for my results?
**A**: Yes, the query statistics show which source provided the results, including any fallback attempts that occurred.

### Q: How often are the archives updated?
**A**: 
- **Wayback Machine**: Continuous crawling and updates
- **Common Crawl**: Monthly snapshots, typically released 60-90 days after the crawl month

### Q: Is there a limit to how many queries I can make?
**A**: Archive APIs have reasonable rate limits for normal usage. The system automatically handles rate limiting and will pause/retry when limits are approached.

### Q: What happens if both archive sources fail?
**A**: If all configured sources fail, the system will return an error. This is rare but can happen during widespread internet issues. The system logs detailed error information to help diagnose the problem.