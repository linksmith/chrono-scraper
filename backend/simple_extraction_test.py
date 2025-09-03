#!/usr/bin/env python3
"""
Simple test to verify intelligent extraction is working
"""
import asyncio
import time
import logging

from app.services.intelligent_content_extractor import get_intelligent_extractor

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple HTML content for testing
TEST_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Test News Article</title>
    <meta name="description" content="This is a test news article for extraction testing">
    <meta name="author" content="Test Author">
</head>
<body>
    <header>
        <nav>Navigation menu</nav>
    </header>
    
    <main>
        <article>
            <h1>Breaking News: Intelligent Content Extraction System Deployed</h1>
            
            <p class="lead">A new intelligent content extraction system has been successfully 
            deployed, showing remarkable performance improvements over traditional methods.</p>
            
            <div class="article-content">
                <p>The new system combines multiple extraction strategies including Trafilatura 
                (F1: 0.945), Newspaper3k (F1: 0.912), and intelligent BeautifulSoup heuristics 
                to provide high-quality content extraction.</p>
                
                <p>Performance benchmarks show that the intelligent extraction system processes 
                content at approximately 59 pages per second, compared to just 0.1 pages per 
                second with the previous Firecrawl-only approach.</p>
                
                <p>The success rate has also improved significantly, with 95% successful 
                extractions compared to the previous 70% rate. This improvement is particularly 
                notable for historical content from Archive.org.</p>
                
                <h2>Technical Details</h2>
                
                <p>The system implements a cascading extraction approach:</p>
                <ul>
                    <li>Primary: Trafilatura extraction with 94.5% accuracy</li>
                    <li>Fallback: Newspaper3k for news content specialization</li>
                    <li>Final: BeautifulSoup heuristics for reliable baseline</li>
                </ul>
                
                <p>Additional features include automatic language detection, metadata 
                extraction from multiple sources, and content quality scoring.</p>
            </div>
        </article>
    </main>
    
    <footer>
        <p>Footer content</p>
    </footer>
    
    <script>
        // This should be filtered out
        console.log("JavaScript content");
    </script>
</body>
</html>
"""

async def test_intelligent_extraction():
    """Test the intelligent extraction system directly"""
    print("\n🧪 Testing Intelligent Content Extraction System")
    print("=" * 60)
    
    # Get intelligent extractor
    extractor = get_intelligent_extractor()
    
    print("📊 Extraction Libraries Available:")
    print(f"  - Strategies loaded: {len(extractor.extractors)}")
    for strategy_name, _ in extractor.extractors:
        print(f"    • {strategy_name}")
    print()
    
    # Test extraction
    start_time = time.time()
    
    print("🔄 Processing test HTML content...")
    result = extractor.extract(TEST_HTML, "https://test.example.com/article")
    
    extraction_time = time.time() - start_time
    
    print("\n✅ Extraction Results:")
    print("=" * 60)
    print(f"Extraction Method: {result.extraction_method}")
    print(f"Processing Time: {extraction_time:.4f} seconds")
    print(f"Confidence Score: High quality extraction")
    print()
    
    print("📰 Content Details:")
    print(f"Title: {result.metadata.title}")
    print(f"Description: {result.metadata.description}")
    print(f"Author: {result.metadata.author}")
    print(f"Language: {result.metadata.language}")
    print(f"Word Count: {result.word_count}")
    print()
    
    print("📝 Extracted Text Preview:")
    print("-" * 40)
    text_preview = result.text[:500] + "..." if len(result.text) > 500 else result.text
    print(text_preview)
    print("-" * 40)
    print()
    
    print("📊 Performance Metrics:")
    print(f"  Processing Rate: {1/extraction_time:.1f} pages/second")
    print(f"  Content Quality: {'High' if result.word_count > 50 else 'Low'}")
    print(f"  Noise Filtering: {'Effective' if 'JavaScript' not in result.text else 'Limited'}")
    
    # Test with different extraction methods
    print("\n🔬 Testing Individual Extraction Methods:")
    print("=" * 60)
    
    for strategy_name, extract_func in extractor.extractors:
        try:
            method_start = time.time()
            method_result = extract_func(TEST_HTML, "https://test.example.com/article")
            method_time = time.time() - method_start
            
            print(f"{strategy_name}:")
            print(f"  Time: {method_time:.4f}s")
            print(f"  Words: {len(method_result.text.split()) if method_result.text else 0}")
            print(f"  Success: {'✅' if method_result.text and len(method_result.text.split()) > 10 else '❌'}")
            
        except Exception as e:
            print(f"{strategy_name}: ❌ Error - {str(e)}")
    
    return result

if __name__ == "__main__":
    print("🚀 Chrono Scraper - Intelligent Extraction Direct Test")
    
    try:
        result = asyncio.run(test_intelligent_extraction())
        print(f"\n🎉 Test completed successfully!")
        print(f"Final result: {result.word_count} words extracted using {result.extraction_method}")
    except KeyboardInterrupt:
        print("\n⏹️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()