import os
import json
import asyncio
import logging
from typing import List, Dict, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse
import re

from playwright.async_api import async_playwright, Page, Browser, TimeoutError

class EcommerceCrawler:
    def __init__(
        self, 
        domains: List[str], 
        max_pages_per_domain: int = 500,
        max_depth: int = 10,
        timeout: int = 30000,  # milliseconds
        headless: bool = True
    ):
        """Initialize with the same parameters as before"""
        self.domains = domains
        self.max_pages_per_domain = max_pages_per_domain
        self.max_depth = max_depth
        self.timeout = timeout
        self.headless = headless
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('crawler_debug.log')
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # URL patterns that indicate a product page
        self.product_url_patterns = [
            '/product/', '/item/', '/p/', '/dp/', '/products/', 
            '/detail/', '/view/', '/show/', 
            '/pd/', '/product-detail/',
            '/buy/', '/shop/product'
        ]
        
        # Page content patterns that indicate a product page
        self.product_page_patterns = [
            'add to cart',
            'add to bag',
            'buy',
            'add to basket',
            'delivery time',
            'sku',
            'item number',
            'model number',
            'in stock',
            'out of stock',
            'quantity',
            'size chart',
            'size guide',
            'sizes',
            'of all taxes'
        ]
        
        # Exclusion patterns - Not a product URL if these patterns in URL
        self.exclusion_patterns = [
            '/category/',
            '/search/',
            '/cart/',
            '/login/',
            '/account/',
            '/wishlist/',
            '/about/',
            '/contact/',
            '/help/',
            '/faq/',
            '.jpg',
            '.jpeg',
            '.png',
            '.gif',
            '.pdf',
            '.css',
            '.js',
            '.html',
            '.htm',
            '.aspx'
        ]
        
        self.output_dir = 'crawler_output'
        os.makedirs(self.output_dir, exist_ok=True)

    def is_product_url_by_pattern(self, url: str) -> bool:
        """
        First step: Check if URL matches product patterns
        """
        try:
            parsed_url = urlparse(url)
            path = parsed_url.path.lower()
            
            # Check exclusions first
            if any(exclusion in path for exclusion in self.exclusion_patterns):
                return False
                
            # Check product URL patterns
            return any(pattern in path for pattern in self.product_url_patterns)
            
        except Exception as e:
            self.logger.error(f"Error in is_product_url_by_pattern for {url}: {e}")
            return False

    async def is_product_page_by_content(self, page: Page) -> bool:
        """
        Second step: Check page content for product indicators
        """
        try:
            # Get page text content
            content = await page.evaluate('() => document.body.innerText')
            content = content.lower()
            
            # Count how many product indicators are found
            indicator_count = sum(1 for pattern in self.product_page_patterns if pattern in content)
            
            # If we find at least 3 indicators, consider it a product page
            return indicator_count >= 3
            
        except Exception as e:
            self.logger.error(f"Error in is_product_page_by_content: {e}")
            return False

    async def extract_links(self, page: Page, base_url: str) -> Tuple[Set[str], Set[str]]:
        """
        Extract both product and non-product links from a page
        """
        product_urls = set()
        non_product_urls = set()
        
        try:
            links = await asyncio.wait_for(
                page.query_selector_all('a'),
                timeout=10
            )
            
            base_domain = urlparse(base_url).netloc.replace('www.', '').replace('shop.', '')
            
            for link in links:
                try:
                    href = await link.get_attribute('href')
                    if not href or href.startswith('#'):
                        continue
                    
                    full_url = urljoin(base_url, href)
                    full_url = self.remove_query_params(full_url)
                    parsed_url = urlparse(full_url)
                    
                    # Only process URLs from the same domain
                    if parsed_url.netloc.replace('www.', '').replace('shop.', '') == base_domain:
                        # First check: URL pattern
                        if self.is_product_url_by_pattern(full_url):
                            product_urls.add(full_url)
                            continue
                            
                        # If not clearly a product URL, we'll add it to non-product URLs
                        # It will be checked for content patterns when visited
                        non_product_urls.add(full_url)
                
                except Exception as e:
                    self.logger.warning(f"Error processing link on {base_url}: {e}")
        
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout while extracting links from {base_url}")
        except Exception as e:
            self.logger.error(f"Error extracting links from {base_url}: {e}")
        
        return product_urls, non_product_urls

    async def crawl_url(self, url: str, page: Page, visited_urls: Set[str], current_depth: int, domain: str) -> Tuple[Set[str], Set[str]]:
        """
        Crawl a specific URL and its sub-pages recursively
        """
        url = self.remove_query_params(url)

        if current_depth > self.max_depth or len(visited_urls) >= self.max_pages_per_domain:
            return set(), visited_urls
        
        if url in visited_urls:
            return set(), visited_urls
        
        product_urls = set()
        visited_urls.add(url)
        
        current_location = self.get_readable_path(url)
        self.logger.info(
            f"{domain}: Crawling {current_location} "
            f"(Depth: {current_depth}/{self.max_depth}) "
            f"(Pages: {len(visited_urls)}/{self.max_pages_per_domain})"
        )
        
        try:
            try:
                await page.goto(url, timeout=self.timeout, wait_until='networkidle')
                
                # Second check: Page content
                # Only perform content check if URL wasn't already identified as product URL
                if not self.is_product_url_by_pattern(url) and await self.is_product_page_by_content(page):
                    product_urls.add(url)
                
            except TimeoutError:
                self.logger.warning(f"Timeout while loading {url}, continuing with partial page load")
            
            try:
                for i in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1000)
            except Exception as e:
                self.logger.warning(f"Error during scrolling on {url}: {e}")
            
            page_product_urls, page_non_product_urls = await self.extract_links(page, url)
            product_urls.update(page_product_urls)
            
            if current_depth < self.max_depth and len(visited_urls) < self.max_pages_per_domain:
                for non_product_url in page_non_product_urls:
                    if len(visited_urls) >= self.max_pages_per_domain:
                        self.logger.info(f"{domain}: Reached maximum pages limit ({self.max_pages_per_domain})")
                        break
                    
                    if non_product_url not in visited_urls:
                        sub_product_urls, visited_urls = await self.crawl_url(
                            non_product_url, 
                            page, 
                            visited_urls, 
                            current_depth + 1,
                            domain
                        )
                        product_urls.update(sub_product_urls)
        
        except Exception as e:
            self.logger.error(f"Error crawling {url}: {str(e)}")
        
        return product_urls, visited_urls

    def get_readable_path(self, url: str) -> str:
        """
        Extract a human-readable path from URL
        """
        try:
            parsed = urlparse(url)
            path = parsed.path.strip('/')
            if not path:
                path = 'homepage'
            return f"{parsed.netloc}/{path}"
        except Exception:
            return url

    def remove_query_params(self, url: str) -> str:
        """
        Removes query parameters from a given URL.
        
        Args:
            url (str): The input URL.
            
        Returns:
            str: The URL without query parameters.
        """
        parsed_url = urlparse(url)
        url_without_query = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))
        return url_without_query

    async def crawl_domain(self, domain: str, browser: Browser) -> Dict[str, Set[str]]:
        """
        Crawl a single domain and discover product URLs
        """
        self.logger.info(f"Starting crawl for domain: {domain}")
        base_url = f'https://{domain}'
        visited_urls = set()
        
        try:
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            page = await context.new_page()
            
            product_urls, visited_urls = await self.crawl_url(base_url, page, visited_urls, 0, domain)
            
            self.logger.info(f"\nDomain {domain} crawl completed:")
            self.logger.info(f"- Final pages crawled: {len(visited_urls)} out of {self.max_pages_per_domain} maximum")
            self.logger.info(f"- Product URLs found: {len(product_urls)}\n")
            
            await page.close()
            await context.close()
            
            return {
                'product_urls': product_urls,
                'crawled_urls': visited_urls
            }
            
        except Exception as e:
            self.logger.error(f"Fatal error crawling domain {domain}: {str(e)}")
            return {
                'product_urls': set(),
                'crawled_urls': visited_urls
            }

    async def run_crawler(self):
        """
        Run crawler for all domains in parallel
        """
        self.logger.info("Starting crawler")
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu'
                    ]
                )
                
                results = {}
                tasks = []
                
                for domain in self.domains:
                    task = asyncio.create_task(self.crawl_domain(domain, browser))
                    tasks.append((domain, task))
                
                for domain, task in tasks:
                    try:
                        domain_results = await task
                        results[domain] = {
                            'product_urls': list(domain_results['product_urls']),
                            'crawled_urls': list(domain_results['crawled_urls'])
                        }
                    except Exception as e:
                        self.logger.error(f"Error processing {domain}: {str(e)}")
                
                await browser.close()
                
            except Exception as e:
                self.logger.error(f"Fatal error in crawler: {str(e)}")
                return {}
            
        return results

    def save_results(self, results: Dict[str, Dict[str, List[str]]]):
        """
        Save crawler results to JSON files
        """
        try:
            product_urls_file = os.path.join(self.output_dir, 'product_urls.json')
            product_urls = {domain: data['product_urls'] for domain, data in results.items()}
            with open(product_urls_file, 'w') as f:
                json.dump(product_urls, f, indent=2)
            
            crawled_urls_file = os.path.join(self.output_dir, 'crawled_urls.json')
            crawled_urls = {domain: data['crawled_urls'] for domain, data in results.items()}
            with open(crawled_urls_file, 'w') as f:
                json.dump(crawled_urls, f, indent=2)
            
            self.logger.info(f"Results saved successfully:")
            self.logger.info(f"- Product URLs: {product_urls_file}")
            self.logger.info(f"- Crawled URLs: {crawled_urls_file}")
            
        except Exception as e:
            self.logger.error(f"Error saving results: {str(e)}")

def main():
    domains = [
        'amazon.com',
        'vastramaniaa.com',
        'www2.hm.com',
        'myntra.com'
    ]
    
    crawler = EcommerceCrawler(
        domains=domains,
        max_pages_per_domain=150,
        max_depth=5,
        timeout=30000,
        headless=False
    )
    
    results = asyncio.run(crawler.run_crawler())
    crawler.save_results(results)

if __name__ == "__main__":
    main()