#!/usr/bin/env python3
"""
Focused Test: Content Extraction Without Firecrawl
This test specifically validates that the robust content extraction system works
and that there are no Firecrawl dependencies causing issues.
"""

import asyncio
import json
import time
import logging
import redis
import psutil
from datetime import datetime
import subprocess
import sys

sys.path.append('/app')

from app.core.config import settings
from app.services.robust_content_extractor import get_robust_extractor
from app.services.intelligent_content_extractor import get_intelligent_extractor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_system_status():
    """Check basic system status"""
    logger.info("🏥 SYSTEM STATUS CHECK")
    logger.info("-" * 50)
    
    try:
        # Memory usage
        memory = psutil.virtual_memory()
        logger.info(f"Memory Usage: {memory.percent:.1f}% ({memory.used / (1024**3):.1f}GB / {memory.total / (1024**3):.1f}GB)")
        
        # Redis status
        redis_client = redis.from_url(settings.REDIS_URL)
        redis_ping = redis_client.ping()
        redis_info = redis_client.info('memory')
        logger.info(f"Redis Status: {'✅ Connected' if redis_ping else '❌ Disconnected'}")
        logger.info(f"Redis Memory: {redis_info.get('used_memory_human', 'Unknown')}")
        
        # Check for Firecrawl processes
        try:
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
            firecrawl_processes = [line for line in result.stdout.split('\n') if 'firecrawl' in line.lower()]
            logger.info(f"Firecrawl Processes: {len(firecrawl_processes)} found")
            if firecrawl_processes:
                for proc in firecrawl_processes[:3]:  # Show max 3
                    logger.info(f"  {proc.strip()}")
        except:
            logger.info("Could not check for Firecrawl processes")
        
        # Check Redis for Firecrawl keys
        all_keys = redis_client.keys('*')
        firecrawl_keys = [k.decode() for k in all_keys if b'firecrawl' in k.lower()]
        logger.info(f"Redis Firecrawl Keys: {len(firecrawl_keys)} found")
        if firecrawl_keys:
            for key in firecrawl_keys[:5]:  # Show max 5
                logger.info(f"  {key}")
        
        return {
            'memory_percent': memory.percent,
            'redis_connected': redis_ping,
            'firecrawl_processes': len(firecrawl_processes) if 'firecrawl_processes' in locals() else 0,
            'firecrawl_redis_keys': len(firecrawl_keys)
        }
        
    except Exception as e:
        logger.error(f"System status check failed: {e}")
        return {'error': str(e)}

async def test_intelligent_extractor():
    """Test the intelligent content extractor directly"""
    logger.info("\n🧠 INTELLIGENT EXTRACTOR TEST")
    logger.info("-" * 50)
    
    try:
        extractor = get_intelligent_extractor()
        logger.info(f"Intelligent Extractor: {type(extractor).__name__}")
        logger.info(f"Available methods: {getattr(extractor, 'available_extractors', 'Unknown')}")
        
        # Test simple HTML extraction
        test_html = """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Test Article</h1>
            <p>This is a test paragraph with some content to extract.</p>
            <p>Another paragraph with more content.</p>
            <div>Some additional content in a div.</div>
        </body>
        </html>
        """
        
        test_url = "https://example.com/test"
        
        start_time = time.time()
        result = await extractor.extract_content(test_html, test_url)
        extraction_time = time.time() - start_time
        
        logger.info(f"Extraction Results:")
        logger.info(f"  Success: {'✅' if result and result.text else '❌'}")
        logger.info(f"  Title: {result.title if result else 'None'}")
        logger.info(f"  Word Count: {result.word_count if result else 0}")
        logger.info(f"  Text Length: {len(result.text) if result and result.text else 0}")
        logger.info(f"  Extraction Time: {extraction_time:.3f}s")
        logger.info(f"  Text Preview: {result.text[:100] + '...' if result and result.text else 'None'}")
        
        return {
            'success': result is not None and result.text,
            'title': result.title if result else None,
            'word_count': result.word_count if result else 0,
            'extraction_time': extraction_time
        }
        
    except Exception as e:
        logger.error(f"Intelligent extractor test failed: {e}")
        return {'success': False, 'error': str(e)}

async def test_robust_extractor():
    """Test the robust content extractor with real URLs"""
    logger.info("\n🤖 ROBUST EXTRACTOR TEST")
    logger.info("-" * 50)
    
    try:
        extractor = get_robust_extractor()
        logger.info(f"Robust Extractor: {type(extractor).__name__}")
        
        # Get extraction metrics first
        metrics = await extractor.get_extraction_metrics()
        logger.info(f"Circuit Breakers Status:")
        for name, status in metrics.get('circuit_breakers', {}).items():
            logger.info(f"  {name}: {status.get('state', 'unknown')} ({status.get('failure_count', 0)} failures)")
        
        # Test with a simple Archive.org URL
        test_urls = [
            "https://web.archive.org/web/20240101000000/https://example.org/",
        ]
        
        results = []
        for url in test_urls:
            logger.info(f"\nTesting URL: {url}")
            start_time = time.time()
            
            try:
                result = await extractor.extract_content(url)
                extraction_time = time.time() - start_time
                
                logger.info(f"  Success: ✅")
                logger.info(f"  Method: {result.extraction_method}")
                logger.info(f"  Title: {result.title}")
                logger.info(f"  Word Count: {result.word_count}")
                logger.info(f"  Text Length: {len(result.text)}")
                logger.info(f"  Extraction Time: {extraction_time:.2f}s")
                
                # Quality assessment
                quality_score = (
                    (1 if result.title else 0) * 0.3 +
                    (min(result.word_count / 50, 1) if result.word_count else 0) * 0.5 +
                    (1 if extraction_time < 10 else 0) * 0.2
                )
                logger.info(f"  Quality Score: {quality_score:.2f}/1.0")
                
                results.append({
                    'url': url,
                    'success': True,
                    'method': result.extraction_method,
                    'word_count': result.word_count,
                    'extraction_time': extraction_time,
                    'quality_score': quality_score
                })
                
            except Exception as e:
                extraction_time = time.time() - start_time
                logger.error(f"  Failed: {e}")
                results.append({
                    'url': url,
                    'success': False,
                    'error': str(e),
                    'extraction_time': extraction_time
                })
        
        return results
        
    except Exception as e:
        logger.error(f"Robust extractor test failed: {e}")
        return [{'success': False, 'error': str(e)}]

async def test_performance_metrics():
    """Test system performance during extraction"""
    logger.info("\n📊 PERFORMANCE METRICS")
    logger.info("-" * 50)
    
    try:
        # Baseline metrics
        baseline_memory = psutil.virtual_memory().percent
        logger.info(f"Baseline Memory: {baseline_memory:.1f}%")
        
        # Redis memory
        redis_client = redis.from_url(settings.REDIS_URL)
        redis_info = redis_client.info('memory')
        baseline_redis = redis_info.get('used_memory', 0) / (1024 * 1024)  # MB
        logger.info(f"Baseline Redis Memory: {baseline_redis:.1f}MB")
        
        # Perform multiple extractions to test stability
        extractor = get_robust_extractor()
        
        extraction_times = []
        for i in range(3):  # Test with 3 extractions
            logger.info(f"Extraction {i+1}/3...")
            start_time = time.time()
            
            try:
                result = await extractor.extract_content("https://web.archive.org/web/20240101000000/https://httpbin.org/html")
                extraction_time = time.time() - start_time
                extraction_times.append(extraction_time)
                logger.info(f"  Completed in {extraction_time:.2f}s")
                
                # Small delay between extractions
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"  Failed: {e}")
                extraction_times.append(float('inf'))
        
        # Final metrics
        final_memory = psutil.virtual_memory().percent
        redis_info = redis_client.info('memory')
        final_redis = redis_info.get('used_memory', 0) / (1024 * 1024)  # MB
        
        avg_extraction_time = sum(t for t in extraction_times if t != float('inf')) / max(1, sum(1 for t in extraction_times if t != float('inf')))
        
        logger.info(f"\nPerformance Summary:")
        logger.info(f"  Memory Change: {final_memory - baseline_memory:+.1f}%")
        logger.info(f"  Redis Memory Change: {final_redis - baseline_redis:+.1f}MB")
        logger.info(f"  Average Extraction Time: {avg_extraction_time:.2f}s")
        logger.info(f"  Successful Extractions: {sum(1 for t in extraction_times if t != float('inf'))}/3")
        
        return {
            'memory_change': final_memory - baseline_memory,
            'redis_memory_change': final_redis - baseline_redis,
            'avg_extraction_time': avg_extraction_time,
            'successful_extractions': sum(1 for t in extraction_times if t != float('inf')),
            'extraction_times': extraction_times
        }
        
    except Exception as e:
        logger.error(f"Performance metrics test failed: {e}")
        return {'error': str(e)}

async def main():
    """Run all focused tests"""
    logger.info("🎯 FOCUSED E2E TEST: CONTENT EXTRACTION WITHOUT FIRECRAWL")
    logger.info("=" * 70)
    
    # Test 1: System Status
    system_status = await test_system_status()
    
    # Test 2: Intelligent Extractor  
    intelligent_results = await test_intelligent_extractor()
    
    # Test 3: Robust Extractor
    robust_results = await test_robust_extractor()
    
    # Test 4: Performance Metrics
    performance_results = await test_performance_metrics()
    
    # Generate Summary Report
    logger.info("\n" + "=" * 70)
    logger.info("🎯 FINAL TEST SUMMARY")
    logger.info("=" * 70)
    
    # Overall assessment
    system_healthy = (
        system_status.get('redis_connected', False) and
        system_status.get('memory_percent', 100) < 90 and
        system_status.get('firecrawl_processes', 1) == 0
    )
    
    intelligent_working = intelligent_results.get('success', False)
    
    robust_working = any(r.get('success', False) for r in robust_results)
    robust_fast = all(r.get('extraction_time', 100) < 30 for r in robust_results if r.get('success'))
    
    performance_good = (
        performance_results.get('memory_change', 100) < 20 and  # Less than 20% memory increase
        performance_results.get('avg_extraction_time', 100) < 30 and  # Less than 30s average
        performance_results.get('successful_extractions', 0) >= 2  # At least 2/3 successful
    )
    
    logger.info(f"System Health: {'✅' if system_healthy else '❌'}")
    logger.info(f"Intelligent Extractor: {'✅' if intelligent_working else '❌'}")
    logger.info(f"Robust Extractor: {'✅' if robust_working else '❌'}")
    logger.info(f"Fast Extraction: {'✅' if robust_fast else '❌'}")
    logger.info(f"Performance: {'✅' if performance_good else '❌'}")
    
    # Key metrics
    logger.info(f"\nKey Metrics:")
    logger.info(f"  Memory Usage: {system_status.get('memory_percent', 0):.1f}%")
    logger.info(f"  Firecrawl Processes: {system_status.get('firecrawl_processes', 0)}")
    logger.info(f"  Firecrawl Redis Keys: {system_status.get('firecrawl_redis_keys', 0)}")
    logger.info(f"  Successful Extractions: {sum(1 for r in robust_results if r.get('success'))}/{len(robust_results)}")
    logger.info(f"  Average Extraction Time: {performance_results.get('avg_extraction_time', 0):.2f}s")
    
    # Final verdict
    all_tests_pass = system_healthy and intelligent_working and robust_working and robust_fast and performance_good
    
    logger.info(f"\n{'🎉 ALL TESTS PASSED' if all_tests_pass else '⚠️  SOME TESTS FAILED'}")
    
    if all_tests_pass:
        logger.info("✅ Firecrawl removal successful - system working with robust extraction")
        logger.info("✅ Content extraction quality is good")
        logger.info("✅ Performance is acceptable")
        logger.info("✅ No Firecrawl dependencies detected")
        logger.info("✅ System ready for production use")
    else:
        logger.info("❌ Some issues detected that need attention")
    
    # Save detailed results
    report = {
        'timestamp': datetime.utcnow().isoformat(),
        'system_status': system_status,
        'intelligent_extractor': intelligent_results,
        'robust_extractor': robust_results,
        'performance_metrics': performance_results,
        'summary': {
            'all_tests_pass': all_tests_pass,
            'system_healthy': system_healthy,
            'intelligent_working': intelligent_working,
            'robust_working': robust_working,
            'robust_fast': robust_fast,
            'performance_good': performance_good
        }
    }
    
    with open('/app/extraction_focused_test_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"\n📊 Detailed report saved to: /app/extraction_focused_test_report.json")
    
    return all_tests_pass

if __name__ == "__main__":
    success = asyncio.run(main())
    exit_code = 0 if success else 1
    exit(exit_code)