"""
Test CDX API URL preservation behavior.

This test module verifies that when a user creates a project with a full URL
(instead of just a domain), the CDX API correctly preserves the full URL
for prefix matching rather than converting it to domain-only matching.

Fixes bug where URLs like "https://example.com/specific-page" were being
converted to "example.com" in CDX queries.
"""
import pytest
from unittest.mock import Mock, patch
from app.services.wayback_machine import CDXAPIClient


class TestCDXURLPreservation:
    """Test cases for URL preservation in CDX API calls"""
    
    def test_full_url_with_https_preserves_url_and_uses_prefix_match(self):
        """Test that full HTTPS URLs are preserved and use prefix matching"""
        client = CDXAPIClient()
        
        # Test with full HTTPS URL
        full_url = "https://example.com/specific/path/page.html"
        url = client._build_cdx_url(
            domain_name=full_url,
            from_date="20200101", 
            to_date="20231231"
        )
        
        # Verify the URL contains the full original URL for prefix matching
        assert "url=https://example.com/specific/path/page.html" in url
        assert "matchType=prefix" in url
        assert "matchType=domain" not in url
    
    def test_full_url_with_http_preserves_url_and_uses_prefix_match(self):
        """Test that full HTTP URLs are preserved and use prefix matching"""
        client = CDXAPIClient()
        
        # Test with full HTTP URL  
        full_url = "http://example.com/specific/path/page.html"
        url = client._build_cdx_url(
            domain_name=full_url,
            from_date="20200101",
            to_date="20231231"
        )
        
        # Verify the URL contains the full original URL for prefix matching
        assert "url=http://example.com/specific/path/page.html" in url
        assert "matchType=prefix" in url
        assert "matchType=domain" not in url
    
    def test_domain_only_uses_domain_matching(self):
        """Test that domain-only input uses domain matching"""
        client = CDXAPIClient()
        
        # Test with domain only
        domain = "example.com"
        url = client._build_cdx_url(
            domain_name=domain,
            from_date="20200101",
            to_date="20231231"
        )
        
        # Verify domain matching is used
        assert "url=example.com" in url
        assert "matchType=domain" in url
        assert "matchType=prefix" not in url
    
    def test_explicit_prefix_with_url_path_uses_url_path(self):
        """Test that explicit prefix matching with url_path works correctly"""
        client = CDXAPIClient()
        
        # Test explicit prefix matching
        domain = "example.com"
        url_path = "https://example.com/api/v1/"
        url = client._build_cdx_url(
            domain_name=domain,
            match_type="prefix",
            url_path=url_path,
            from_date="20200101",
            to_date="20231231"
        )
        
        # Verify url_path is used for prefix matching
        assert "url=https://example.com/api/v1/" in url
        assert "matchType=prefix" in url
        assert "matchType=domain" not in url
    
    def test_complex_url_with_query_params_preserves_full_url(self):
        """Test that complex URLs with query parameters are preserved"""
        client = CDXAPIClient()
        
        # Test with complex URL containing query parameters
        complex_url = "https://example.com/search?q=test&category=news&sort=date"
        url = client._build_cdx_url(
            domain_name=complex_url,
            from_date="20200101",
            to_date="20231231"
        )
        
        # Verify the complex URL is preserved
        assert "url=https://example.com/search?q=test&category=news&sort=date" in url
        assert "matchType=prefix" in url
    
    def test_url_with_fragments_preserves_full_url(self):
        """Test that URLs with fragment identifiers are preserved"""
        client = CDXAPIClient()
        
        # Test with URL containing fragment
        url_with_fragment = "https://example.com/article.html#section2"
        url = client._build_cdx_url(
            domain_name=url_with_fragment,
            from_date="20200101",
            to_date="20231231"
        )
        
        # Verify the URL with fragment is preserved
        assert "url=https://example.com/article.html#section2" in url
        assert "matchType=prefix" in url
    
    def test_subdomain_url_preserves_full_url(self):
        """Test that URLs with subdomains are preserved"""
        client = CDXAPIClient()
        
        # Test with subdomain URL
        subdomain_url = "https://api.example.com/v2/data/feed.json"
        url = client._build_cdx_url(
            domain_name=subdomain_url,
            from_date="20200101",
            to_date="20231231"
        )
        
        # Verify the subdomain URL is preserved
        assert "url=https://api.example.com/v2/data/feed.json" in url
        assert "matchType=prefix" in url
    
    def test_logging_messages_for_url_detection(self):
        """Test that appropriate logging messages are generated"""
        client = CDXAPIClient()
        
        with patch('app.services.wayback_machine.logger') as mock_logger:
            # Test full URL detection logging
            full_url = "https://example.com/specific/page"
            client._build_cdx_url(
                domain_name=full_url,
                from_date="20200101",
                to_date="20231231"
            )
            
            # Verify logging calls
            mock_logger.info.assert_any_call(
                f"Full URL detected: using prefix match with {full_url}"
            )
            mock_logger.info.assert_any_call(
                f"Building CDX URL: matchType=prefix, query_url={full_url}"
            )
    
    def test_logging_messages_for_domain_only(self):
        """Test logging messages for domain-only matching"""
        client = CDXAPIClient()
        
        with patch('app.services.wayback_machine.logger') as mock_logger:
            # Test domain-only logging
            domain = "example.com"
            client._build_cdx_url(
                domain_name=domain,
                from_date="20200101",
                to_date="20231231"
            )
            
            # Verify logging calls
            mock_logger.info.assert_any_call(
                f"Domain match: using domain {domain}"
            )
            mock_logger.info.assert_any_call(
                f"Building CDX URL: matchType=domain, query_url={domain}"
            )
    
    def test_edge_case_url_starting_with_http_in_path(self):
        """Test edge case where domain contains 'http' but isn't a full URL"""
        client = CDXAPIClient()
        
        # Domain that contains 'http' but isn't a full URL
        domain = "httpbin.org"
        url = client._build_cdx_url(
            domain_name=domain,
            from_date="20200101",
            to_date="20231231"
        )
        
        # Should use domain matching, not prefix
        assert "url=httpbin.org" in url
        assert "matchType=domain" in url
        assert "matchType=prefix" not in url
    
    def test_attachment_filter_logging_uses_query_url(self):
        """Test that attachment filter logging uses the correct query_url"""
        client = CDXAPIClient()
        
        with patch('app.services.wayback_machine.logger') as mock_logger:
            full_url = "https://example.com/documents/"
            client._build_cdx_url(
                domain_name=full_url,
                from_date="20200101",
                to_date="20231231",
                include_attachments=True
            )
            
            # Verify attachment logging uses query_url, not domain_name
            mock_logger.info.assert_any_call(
                f"Including PDF attachments for target: {full_url}"
            )


class TestDomainCreationIntegration:
    """Integration tests for domain creation with URL preservation"""
    
    @pytest.mark.asyncio
    async def test_project_with_full_url_preserves_url_in_cdx_query(self):
        """Integration test: creating a project with full URL preserves it in CDX"""
        # This would require database setup and full integration
        # For now, we test the core logic in isolation
        
        # Simulate domain creation with full URL
        full_url = "https://news.ycombinator.com/newest"
        
        # Test that our CDX client handles it correctly
        client = CDXAPIClient()
        cdx_url = client._build_cdx_url(
            domain_name=full_url,
            from_date="20230101",
            to_date="20231231"
        )
        
        # Verify the URL is preserved for prefix matching
        assert "url=https://news.ycombinator.com/newest" in cdx_url
        assert "matchType=prefix" in cdx_url
        
        # This ensures that when a user creates a project with this URL,
        # the CDX API will search for pages under this specific path,
        # not just pages on the news.ycombinator.com domain


@pytest.mark.integration
class TestRealCDXAPIBehavior:
    """Integration tests with actual CDX API behavior (if enabled)"""
    
    @pytest.mark.skip(reason="Requires actual CDX API access")
    @pytest.mark.asyncio
    async def test_real_cdx_api_with_url_preservation(self):
        """Test with real CDX API to ensure URL preservation works end-to-end"""
        # This test would be enabled for manual testing against real CDX API
        client = CDXAPIClient()
        
        # Test domain-only query
        domain_records, domain_stats = await client.fetch_cdx_records(
            domain_name="example.com",
            from_date="20230101",
            to_date="20230201",
            max_pages=1
        )
        
        # Test URL-specific query  
        url_records, url_stats = await client.fetch_cdx_records(
            domain_name="https://example.com/",
            from_date="20230101", 
            to_date="20230201",
            max_pages=1
        )
        
        # URL query should return subset of domain query
        assert len(url_records) <= len(domain_records)
        
        # All URL records should start with the specified URL prefix
        for record in url_records:
            assert record.original_url.startswith("https://example.com/")


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])