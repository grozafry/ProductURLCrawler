# E-commerce Product Crawler

An asynchronous web crawler built to extract product pages from e-commerce websites. The crawler uses Playwright for reliable web scraping and can handle modern JavaScript-heavy e-commerce sites that traditional crawlers often struggle with.

## Features

- Parallel crawling of multiple domains
- Smart product page detection using both URL patterns and content analysis
- Configurable crawl depth and page limits per domain
- Automatic handling of infinite scroll and dynamically loaded content
- Comprehensive error handling and retry mechanisms
- Detailed logging for monitoring and debugging
- Structured JSON output of discovered URLs


## Approach to Finding Product URLs
This code uses a 2-layer check to identify product URLs -
1. Do a regex match against some commonly used keywords present in product URLs for example /product/, /p/ etc. If a match is found, then it is a product URL.
2. If a match is not found, goto the URL using playwright. Search for some keywords that are commonly present on a product URL page. For example - 'Add to cart', 'Size Charts', 'inclusive of all taxes' etc. If a match is found, then it is a product URL. Otherwise it is a non-product URL.

## Scope for improvement in finding product URLs
A better but more costly approach would be to first collect all of the URLs for the domain. And then ask an LLM to identify which of those URLs are product page URLs. This is a much smarter approach because the URLs can be different across different ecommerce websites.
But it would still have some limitations. First is cost. Any ecommerce website will contain thousands of links and using that much data as input to an LLM would be very costly. Second issue is, in many cases even the LLMs won't be able to accurately identify if a URL is product URL or not.


## Prerequisites

- Python 3.7+
- Playwright
- asyncio

## Running the Crawler

### Installation

pip install playwright
playwright install chromium


### Basic Usage

from ecommerce_crawler import EcommerceCrawler

domains = ['amazon.com', 'myntra.com']
crawler = EcommerceCrawler(
    domains=domains,
    max_pages_per_domain=150,
    max_depth=5,
    timeout=30000,
    headless=True
)

results = asyncio.run(crawler.run_crawler())
crawler.save_results(results)

# Run the crawler
python crawler.py 


### Configuration Options

- `max_pages_per_domain`: Controls how many pages to crawl per domain (default: 500)
- `max_depth`: Sets the maximum crawl depth from homepage (default: 10)
- `timeout`: Page load timeout in milliseconds (default: 30000)
- `headless`: Run browser in headless mode (default: True)

The crawler saves results in the `crawler_output` directory:
- `product_urls.json`: Contains discovered product URLs
- `crawled_urls.json`: List of all crawled URLs

## Known Limitations

- Might not be able to bypass sites that actively block automated access
- Requires JavaScript to be enabled for proper functionality
- Memory usage increases with number of parallel crawls
- May miss some dynamically generated URLs
- Rate limiting on certain e-commerce platforms can affect crawl speed
- Some modern anti-bot systems might detect and block the crawler

########

1. regex

2. Look for e-commerce specific terms like "Add to Cart", "Buy Now", "Price", "Reviews".

3. Product pages are typically deeply nested in the site's hierarchy (home → category → product).
Category pages have many child links, but product pages have few.
Graph Representation: Represent the entire site as a graph, and product pages are typically leaf nodes in this graph.

4. llm