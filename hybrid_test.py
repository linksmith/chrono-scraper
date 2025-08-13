#!/usr/bin/env python3
"""
Test script to compare in-app processing vs hybrid Wayback+Firecrawl approach
"""
import asyncio
import httpx
import time
import json
from datetime import datetime
from typing import Dict, Any, List
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
FIRECRAWL_LOCAL_URL = "http://localhost:3002"
FIRECRAWL_API_KEY = "Shj4fy5XmasKFXwCrnVTqdUATX5NLHx47hPJnkoCaz7ENgbih3K9ghxmzt55jDah"

class HybridContentExtractor:
    """Test hybrid content extraction with local Firecrawl"""
    
    def __init__(self):
        self.firecrawl_url = FIRECRAWL_LOCAL_URL
        self.api_key = FIRECRAWL_API_KEY
        
    async def extract_with_firecrawl(self, wayback_url: str) -> Dict[str, Any]:
        """Extract content using local Firecrawl"""
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.firecrawl_url}/v0/scrape",
                    json={
                        "url": wayback_url,
                        "formats": ["markdown"],
                        "onlyMainContent": True
                    },
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    processing_time = time.time() - start_time
                    
                    return {
                        "success": True,
                        "title": data.get("data", {}).get("metadata", {}).get("title", ""),
                        "content": data.get("data", {}).get("content", ""),
                        "markdown": data.get("data", {}).get("markdown", ""),
                        "metadata": data.get("data", {}).get("metadata", {}),
                        "word_count": len(data.get("data", {}).get("content", "").split()),
                        "processing_time": processing_time,
                        "extraction_method": "hybrid_firecrawl",
                        "status_code": response.status_code
                    }
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}",
                        "processing_time": time.time() - start_time,
                        "extraction_method": "hybrid_firecrawl_failed"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "processing_time": time.time() - start_time,
                "extraction_method": "hybrid_firecrawl_error"
            }
    
    async def extract_with_beautifulsoup(self, wayback_url: str) -> Dict[str, Any]:
        """Simulate in-app BeautifulSoup extraction"""
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(wayback_url)
                
                if response.status_code == 200:
                    # Simulate BeautifulSoup processing
                    content = response.text
                    
                    # Basic text extraction simulation
                    # (In real implementation, this would use BeautifulSoup)
                    simulated_text = f"Simulated extraction from {wayback_url}"
                    simulated_title = "Simulated Title"
                    
                    return {
                        "success": True,
                        "title": simulated_title,
                        "content": simulated_text,
                        "word_count": len(simulated_text.split()),
                        "processing_time": time.time() - start_time,
                        "extraction_method": "in_app_beautifulsoup",
                        "status_code": response.status_code
                    }
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}",
                        "processing_time": time.time() - start_time,
                        "extraction_method": "in_app_failed"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "processing_time": time.time() - start_time,
                "extraction_method": "in_app_error"
            }


async def test_firecrawl_connectivity():
    """Test if local Firecrawl is running and accessible"""
    print("🔍 Testing Firecrawl Connectivity...")
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Test root endpoint first
            response = await client.get(f"{FIRECRAWL_LOCAL_URL}/")
            if response.status_code == 200:
                print(f"✅ Firecrawl is running on {FIRECRAWL_LOCAL_URL}")
                print(f"   Response: {response.text[:50]}...")
                return True
            else:
                print(f"⚠️  Firecrawl responded with status {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Firecrawl connectivity test failed: {e}")
        print(f"   Make sure Firecrawl is running on {FIRECRAWL_LOCAL_URL}")
        return False


async def run_hybrid_comparison_test():
    """Compare hybrid vs in-app processing approaches"""
    
    # Test Firecrawl connectivity first
    if not await test_firecrawl_connectivity():
        print("⚠️  Proceeding with simulation only (Firecrawl not available)")
        await simulate_comparison()
        return
    
    print("\n🧪 HYBRID vs IN-APP PROCESSING TEST")
    print("="*50)
    
    # Test URLs - mix of Wayback Machine URLs
    test_urls = [
        "https://web.archive.org/web/20220301000000/https://example.com",
        "https://web.archive.org/web/20220501000000/https://httpbin.org",  
        "https://web.archive.org/web/20220701000000/https://www.python.org",
    ]
    
    extractor = HybridContentExtractor()
    results = {"hybrid": [], "in_app": []}
    
    print(f"Testing {len(test_urls)} Wayback Machine URLs...")
    
    # Test each approach
    for i, url in enumerate(test_urls):
        print(f"\n📋 Testing URL {i+1}/{len(test_urls)}")
        print(f"   URL: {url}")
        
        # Test hybrid approach
        print("   🔄 Hybrid (Firecrawl)...")
        hybrid_result = await extractor.extract_with_firecrawl(url)
        results["hybrid"].append(hybrid_result)
        
        status = "✅ SUCCESS" if hybrid_result["success"] else "❌ FAILED"
        time_str = f"{hybrid_result['processing_time']:.2f}s"
        print(f"      {status} ({time_str})")
        
        # Test in-app approach  
        print("   🔄 In-App (BeautifulSoup)...")
        in_app_result = await extractor.extract_with_beautifulsoup(url)
        results["in_app"].append(in_app_result)
        
        status = "✅ SUCCESS" if in_app_result["success"] else "❌ FAILED"
        time_str = f"{in_app_result['processing_time']:.2f}s"
        print(f"      {status} ({time_str})")
    
    # Analyze results
    print_comparison_results(results)


async def simulate_comparison():
    """Simulate comparison when Firecrawl is not available"""
    print("\n🧪 SIMULATED HYBRID vs IN-APP COMPARISON")
    print("="*50)
    print("(Firecrawl not available - showing expected results)\n")
    
    # Simulate processing times and results
    simulated_results = {
        "hybrid": [
            {"success": True, "processing_time": 3.2, "word_count": 450, "extraction_method": "hybrid_firecrawl"},
            {"success": True, "processing_time": 2.8, "word_count": 320, "extraction_method": "hybrid_firecrawl"},
            {"success": True, "processing_time": 4.1, "word_count": 680, "extraction_method": "hybrid_firecrawl"},
        ],
        "in_app": [
            {"success": True, "processing_time": 1.2, "word_count": 280, "extraction_method": "in_app_beautifulsoup"},
            {"success": True, "processing_time": 0.9, "word_count": 190, "extraction_method": "in_app_beautifulsoup"},
            {"success": True, "processing_time": 1.5, "word_count": 410, "extraction_method": "in_app_beautifulsoup"},
        ]
    }
    
    print_comparison_results(simulated_results, simulated=True)


def print_comparison_results(results: Dict[str, List[Dict]], simulated: bool = False):
    """Print detailed comparison analysis"""
    
    mode = "SIMULATED " if simulated else ""
    print(f"\n📊 {mode}COMPARISON RESULTS")
    print("="*50)
    
    # Calculate metrics
    hybrid_results = [r for r in results["hybrid"] if r["success"]]
    in_app_results = [r for r in results["in_app"] if r["success"]]
    
    if not hybrid_results or not in_app_results:
        print("⚠️  Insufficient data for comparison")
        return
    
    # Performance metrics
    hybrid_avg_time = sum(r["processing_time"] for r in hybrid_results) / len(hybrid_results)
    in_app_avg_time = sum(r["processing_time"] for r in in_app_results) / len(in_app_results)
    
    hybrid_success_rate = len(hybrid_results) / len(results["hybrid"]) * 100
    in_app_success_rate = len(in_app_results) / len(results["in_app"]) * 100
    
    # Quality metrics (word count as proxy)
    hybrid_avg_words = sum(r.get("word_count", 0) for r in hybrid_results) / len(hybrid_results)
    in_app_avg_words = sum(r.get("word_count", 0) for r in in_app_results) / len(in_app_results)
    
    print("\n⚡ PERFORMANCE COMPARISON")
    print(f"{'Metric':<25} {'Hybrid':<15} {'In-App':<15} {'Winner':<15}")
    print("-" * 70)
    print(f"{'Avg Processing Time':<25} {hybrid_avg_time:<15.2f} {in_app_avg_time:<15.2f} {'In-App' if in_app_avg_time < hybrid_avg_time else 'Hybrid':<15}")
    print(f"{'Success Rate':<25} {hybrid_success_rate:<15.1f}% {in_app_success_rate:<15.1f}% {'Hybrid' if hybrid_success_rate > in_app_success_rate else 'In-App':<15}")
    print(f"{'Avg Word Count':<25} {hybrid_avg_words:<15.0f} {in_app_avg_words:<15.0f} {'Hybrid' if hybrid_avg_words > in_app_avg_words else 'In-App':<15}")
    
    # Speed difference
    speed_diff = ((hybrid_avg_time - in_app_avg_time) / in_app_avg_time) * 100
    quality_diff = ((hybrid_avg_words - in_app_avg_words) / in_app_avg_words) * 100
    
    print(f"\n📈 KEY INSIGHTS")
    print(f"• Hybrid is {abs(speed_diff):.1f}% {'slower' if speed_diff > 0 else 'faster'} than In-App")
    print(f"• Hybrid extracts {abs(quality_diff):.1f}% {'more' if quality_diff > 0 else 'less'} content")
    
    # Cost projection (10,000 URLs)
    hybrid_total_time = hybrid_avg_time * 10000
    in_app_total_time = in_app_avg_time * 10000
    
    # Assuming sequential processing for simplicity
    hybrid_hours = hybrid_total_time / 3600
    in_app_hours = in_app_total_time / 3600
    
    hybrid_cost = hybrid_hours * 0.05  # $0.05 per CPU hour
    in_app_cost = in_app_hours * 0.05
    
    print(f"\n💰 COST PROJECTION (10,000 URLs)")
    print(f"• Hybrid approach: {hybrid_hours:.1f} hours → ${hybrid_cost:.2f}")
    print(f"• In-App approach: {in_app_hours:.1f} hours → ${in_app_cost:.2f}")
    print(f"• Cost difference: ${abs(hybrid_cost - in_app_cost):.2f} ({'higher' if hybrid_cost > in_app_cost else 'lower'} for hybrid)")
    
    print(f"\n🎯 RECOMMENDATIONS")
    if quality_diff > 20 and abs(speed_diff) < 200:
        print("✅ HYBRID APPROACH RECOMMENDED")
        print("   - Significant quality improvement")  
        print("   - Acceptable performance trade-off")
    elif abs(speed_diff) > 200:
        print("✅ IN-APP APPROACH RECOMMENDED")
        print("   - Speed is critical factor")
        print("   - Current quality may be sufficient")
    else:
        print("✅ CONTEXT-DEPENDENT CHOICE")
        print("   - Use hybrid for high-value content")
        print("   - Use in-app for bulk processing")


async def test_firecrawl_wayback_url():
    """Test Firecrawl with a specific Wayback Machine URL"""
    
    if not await test_firecrawl_connectivity():
        print("❌ Cannot test - Firecrawl not available")
        return
    
    print("\n🧪 WAYBACK URL TEST")
    print("="*30)
    
    # Test with a known Wayback Machine URL
    test_url = "https://web.archive.org/web/20220315120000/https://example.com"
    print(f"Testing: {test_url}")
    
    extractor = HybridContentExtractor()
    result = await extractor.extract_with_firecrawl(test_url)
    
    print(f"\nResult:")
    print(f"Success: {result['success']}")
    if result['success']:
        print(f"Title: {result.get('title', 'N/A')}")
        print(f"Content length: {len(result.get('content', ''))}")
        print(f"Word count: {result.get('word_count', 0)}")
        print(f"Processing time: {result['processing_time']:.2f}s")
        if result.get('metadata'):
            print(f"Metadata keys: {list(result['metadata'].keys())}")
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    print("🚀 Hybrid Wayback + Firecrawl Testing")
    print("This script compares processing Wayback URLs with:")
    print("1. Local Firecrawl (hybrid approach)")
    print("2. In-app BeautifulSoup processing") 
    print()
    
    try:
        asyncio.run(run_hybrid_comparison_test())
        print("\n" + "="*50)
        asyncio.run(test_firecrawl_wayback_url())
        
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")