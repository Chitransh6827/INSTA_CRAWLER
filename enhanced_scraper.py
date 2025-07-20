# enhanced_scraper.py
# High-Performance Instagram Scraper with Parallel Processing, Deduplication, and Batch Saving

import time
import re
import json
import csv
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set, Optional
import threading
from dataclasses import dataclass, asdict
import logging
from collections import deque
import hashlib
import random

# Selenium imports with undetected chromedriver
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AdaptiveRateLimiter:
    """Intelligent rate limiter that adapts based on success/failure patterns"""
    def __init__(self, base_delay: float = 1.0, max_delay: float = 30.0):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.current_delay = base_delay
        self.request_times = deque(maxlen=50)
        self.error_count = 0
        self.success_count = 0
        self.lock = threading.Lock()
    
    def wait(self):
        """Smart delay based on recent performance"""
        with self.lock:
            now = time.time()
            self.request_times.append(now)
            
            # Calculate error rate
            total_requests = self.error_count + self.success_count
            error_rate = self.error_count / max(total_requests, 1)
            
            # Dynamic delay calculation
            if error_rate > 0.3:  # High error rate
                self.current_delay = min(self.base_delay * (2 ** min(self.error_count, 5)), self.max_delay)
                self.current_delay += random.uniform(0, self.current_delay * 0.1)  # Add jitter
            elif error_rate > 0.1:  # Medium error rate
                self.current_delay = self.base_delay * 1.5
            else:  # Low error rate
                self.current_delay = self.base_delay * 0.5
            
            # Respect rate limits (max 20 requests per minute)
            if len(self.request_times) >= 15:
                time_diff = now - self.request_times[0]
                if time_diff < 60:
                    additional_delay = (60 - time_diff) / len(self.request_times)
                    self.current_delay = max(self.current_delay, additional_delay)
            
            if self.current_delay > 0:
                time.sleep(self.current_delay)
    
    def record_success(self):
        """Record successful request"""
        with self.lock:
            self.success_count += 1
            self.error_count = max(0, self.error_count - 1)  # Gradually reduce error count
    
    def record_failure(self):
        """Record failed request"""
        with self.lock:
            self.error_count += 1

class CircuitBreaker:
    """Circuit breaker pattern for robust error handling"""
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.lock = threading.Lock()
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        with self.lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    logger.info("🔄 Circuit breaker: Attempting recovery")
                else:
                    raise Exception("Circuit breaker is OPEN - too many failures")
        
        try:
            result = func(*args, **kwargs)
            self.reset()
            return result
        except Exception as e:
            self.record_failure()
            raise e
    
    def reset(self):
        """Reset circuit breaker on success"""
        with self.lock:
            self.failure_count = 0
            self.state = "CLOSED"
    
    def record_failure(self):
        """Record failure and potentially open circuit"""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.warning(f"⚠️ Circuit breaker OPENED after {self.failure_count} failures")
    
    def can_execute(self) -> bool:
        """Check if circuit breaker allows execution"""
        with self.lock:
            if self.state == "CLOSED":
                return True
            elif self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    return True
                return False
            else:  # HALF_OPEN
                return True
    
    def record_success(self):
        """Record successful operation"""
        self.reset()
    
    def get_status(self) -> Dict:
        """Get current circuit breaker status"""
        with self.lock:
            return {
                'state': self.state,
                'failure_count': self.failure_count,
                'last_failure_time': self.last_failure_time
            }

class EnhancedDeduplicationManager:
    """Enhanced deduplication with hashing, persistence, and post count tracking"""
    def __init__(self, persist_file: str = "dedup_cache.json", max_posts_per_user: int = 5):
        self.processed_url_hashes: Set[str] = set()
        self.username_post_counts: Dict[str, int] = {}  # Track posts per username
        self.max_posts_per_user = max_posts_per_user
        self.persist_file = persist_file
        self.lock = threading.Lock()
        self.load_cache()
    
    def _hash_value(self, value: str) -> str:
        """Create hash for efficient storage"""
        return hashlib.md5(value.encode()).hexdigest()
    
    def load_cache(self):
        """Load existing cache from file"""
        try:
            if os.path.exists(self.persist_file):
                with open(self.persist_file, 'r') as f:
                    data = json.load(f)
                    self.processed_url_hashes = set(data.get('urls', []))
                    self.username_post_counts = data.get('username_post_counts', {})
                logger.info(f"📂 Loaded {len(self.processed_url_hashes)} URLs and {len(self.username_post_counts)} usernames from cache")
        except Exception as e:
            logger.warning(f"Could not load dedup cache: {e}")
    
    def save_cache(self):
        """Persist cache to file"""
        try:
            with open(self.persist_file, 'w') as f:
                json.dump({
                    'urls': list(self.processed_url_hashes),
                    'username_post_counts': self.username_post_counts
                }, f)
        except Exception as e:
            logger.warning(f"Could not save dedup cache: {e}")
    
    def is_url_processed(self, url: str) -> bool:
        """Check if URL has been processed"""
        with self.lock:
            url_hash = self._hash_value(url)
            return url_hash in self.processed_url_hashes
    
    def is_username_processed(self, username: str) -> bool:
        """Check if username has reached maximum posts limit"""
        with self.lock:
            username_clean = username.lower().strip()
            current_count = self.username_post_counts.get(username_clean, 0)
            return current_count >= self.max_posts_per_user
    
    def can_process_user(self, username: str) -> bool:
        """Check if we can still process posts from this user"""
        with self.lock:
            username_clean = username.lower().strip()
            current_count = self.username_post_counts.get(username_clean, 0)
            return current_count < self.max_posts_per_user
    
    def get_user_post_count(self, username: str) -> int:
        """Get current post count for a user"""
        with self.lock:
            username_clean = username.lower().strip()
            return self.username_post_counts.get(username_clean, 0)
    
    def add_url(self, url: str):
        """Add URL to processed set"""
        with self.lock:
            url_hash = self._hash_value(url)
            self.processed_url_hashes.add(url_hash)
    
    def add_username(self, username: str):
        """Add/increment post count for username"""
        with self.lock:
            username_clean = username.lower().strip()
            current_count = self.username_post_counts.get(username_clean, 0)
            self.username_post_counts[username_clean] = current_count + 1
            logger.debug(f"📊 User @{username}: {self.username_post_counts[username_clean]}/{self.max_posts_per_user} posts processed")
    
    def mark_url_processed(self, url: str):
        """Mark URL as processed (alias for add_url)"""
        self.add_url(url)
    
    def mark_username_processed(self, username: str):
        """Mark username as processed (alias for add_username)"""
        self.add_username(username)

class PerformanceMonitor:
    """Monitor and track scraper performance metrics"""
    def __init__(self):
        self.start_time = time.time()
        self.requests_made = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_processing_time = 0
        self.lock = threading.Lock()
    
    def record_request(self, processing_time: float, success: bool):
        """Record request metrics"""
        with self.lock:
            self.requests_made += 1
            self.total_processing_time += processing_time
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
    
    def get_stats(self) -> Dict:
        """Get current performance statistics"""
        with self.lock:
            runtime = time.time() - self.start_time
            avg_processing_time = self.total_processing_time / max(self.requests_made, 1)
            success_rate = self.successful_requests / max(self.requests_made, 1)
            requests_per_minute = (self.requests_made / max(runtime, 1)) * 60
            
            return {
                "runtime_seconds": round(runtime, 2),
                "total_requests": self.requests_made,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate": round(success_rate * 100, 2),
                "avg_processing_time": round(avg_processing_time, 2),
                "requests_per_minute": round(requests_per_minute, 2)
            }
    
    def log_stats(self):
        """Log current statistics"""
        stats = self.get_stats()
        logger.info(f"📊 Performance Stats: {stats['success_rate']}% success rate, "
                   f"{stats['requests_per_minute']} req/min, "
                   f"{stats['avg_processing_time']}s avg time")
    
    def record_operation(self, operation_type: str, processing_time: float, success: bool):
        """Record operation with type, time, and success status"""
        self.record_request(processing_time, success)
        # Could add operation type tracking here if needed
    
    def generate_report(self) -> Dict:
        """Generate comprehensive performance report"""
        return self.get_stats()

@dataclass
class ScrapedPost:
    """Data class for scraped post information"""
    url: str
    username: str
    emails: List[str]
    phones: List[str]
    hashtags: List[str]
    mentions: List[str]
    caption: str
    comments_found: int
    timestamp: str
    batch_id: str

class AdaptiveBatchManager:
    """Enhanced batch manager with adaptive sizing and performance optimization"""
    def __init__(self, initial_batch_size: int = 5, results_dir: str = "results", 
                 max_batch_size: int = 20, min_batch_size: int = 2):
        self.current_batch_size = initial_batch_size
        self.max_batch_size = max_batch_size
        self.min_batch_size = min_batch_size
        self.results_dir = results_dir
        self.current_batch: List[ScrapedPost] = []
        self.batch_counter = 1
        self.lock = threading.Lock()
        self.performance_history = deque(maxlen=10)
        self.last_save_time = time.time()
        
        # Create results directory if it doesn't exist
        os.makedirs(results_dir, exist_ok=True)
    
    def add_result(self, result: ScrapedPost):
        """Add result to current batch and save if batch is full"""
        with self.lock:
            self.current_batch.append(result)
            if len(self.current_batch) >= self.current_batch_size:
                self._save_batch()
    
    def save_final_batch(self):
        """Save any remaining results in the final batch"""
        with self.lock:
            if self.current_batch:
                self._save_batch()
    
    def _save_batch(self):
        """Save current batch with performance tracking"""
        if not self.current_batch:
            return
        
        start_time = time.time()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_name = f"scrape_batch_{self.batch_counter}_{timestamp}"
        
        try:
            # Save as JSON with compression
            json_file = os.path.join(self.results_dir, f"{batch_name}.json")
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump([asdict(result) for result in self.current_batch], 
                         f, indent=2, ensure_ascii=False, separators=(',', ':'))
            
            # Save as CSV
            csv_file = os.path.join(self.results_dir, f"{batch_name}.csv")
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                if self.current_batch:
                    writer = csv.DictWriter(f, fieldnames=asdict(self.current_batch[0]).keys())
                    writer.writeheader()
                    for result in self.current_batch:
                        # Convert lists to strings for CSV
                        row_data = asdict(result)
                        for key, value in row_data.items():
                            if isinstance(value, list):
                                row_data[key] = '; '.join(str(v) for v in value)
                        writer.writerow(row_data)
            
            # Track performance
            save_time = time.time() - start_time
            self.performance_history.append({
                'batch_size': len(self.current_batch),
                'save_time': save_time,
                'efficiency': len(self.current_batch) / save_time
            })
            
            logger.info(f"💾 Saved batch {self.batch_counter} with {len(self.current_batch)} results in {save_time:.2f}s")
            logger.info(f"📁 Files: {json_file}, {csv_file}")
            
            # Adjust batch size based on performance
            self._adjust_batch_size()
            
            self.current_batch.clear()
            self.batch_counter += 1
            self.last_save_time = time.time()
            
        except Exception as e:
            logger.error(f"❌ Error saving batch: {e}")
    
    def _adjust_batch_size(self):
        """Dynamically adjust batch size based on performance"""
        if len(self.performance_history) < 3:
            return
        
        # Calculate recent performance trend
        recent_efficiency = [h['efficiency'] for h in list(self.performance_history)[-3:]]
        trend = recent_efficiency[-1] - recent_efficiency[0]
        
        if trend > 1.0:  # Performance improving
            self.current_batch_size = min(self.current_batch_size + 1, self.max_batch_size)
            logger.debug(f"📈 Increased batch size to {self.current_batch_size}")
        elif trend < -1.0:  # Performance degrading
            self.current_batch_size = max(self.current_batch_size - 1, self.min_batch_size)
            logger.debug(f"📉 Decreased batch size to {self.current_batch_size}")
        
        # Force save if too much time has passed
        if time.time() - self.last_save_time > 300:  # 5 minutes
            logger.info("⏰ Forcing batch save due to time limit")
            if self.current_batch:
                self._save_batch()

def create_undetected_driver(headless: bool = True) -> uc.Chrome:
    """Create an undetected Chrome driver with optimized settings"""
    options = uc.ChromeOptions()
    
    if headless:
        options.add_argument("--headless")
    
    # Performance optimizations
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")  # Faster loading
    options.add_argument("--disable-javascript")  # Even faster, but may break some sites
    options.add_argument("--disable-css")
    
    # Memory optimizations
    options.add_argument("--memory-pressure-off")
    options.add_argument("--max_old_space_size=4096")
    
    # Network optimizations
    options.add_argument("--aggressive-cache-discard")
    options.add_argument("--disable-background-timer-throttling")
    
    try:
        driver = uc.Chrome(options=options, version_main=None)
        driver.set_page_load_timeout(8)  # Fast timeout for better performance
        return driver
    except Exception as e:
        logger.error(f"Failed to create undetected driver: {e}")
        # Fallback to regular webdriver if undetected fails
        from selenium import webdriver
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(8)
        return driver

def extract_contact_info(text: str) -> tuple:
    """Extract emails and phone numbers from text"""
    # Enhanced email regex
    emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    
    # Enhanced phone regex for international formats
    phones = re.findall(r'(?:\+\d{1,3}[-.\s]?)?\(?(?:\d{1,4})\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}', text)
    # Filter out short numbers (likely not phone numbers)
    phones = [phone for phone in phones if len(re.sub(r'[^\d]', '', phone)) >= 8]
    
    return list(set(emails)), list(set(phones))  # Remove duplicates

def extract_hashtags_enhanced(text: str) -> List[str]:
    """Enhanced hashtag extraction supporting international characters and underscores"""
    # Support hashtags with letters, numbers, underscores, and international characters
    hashtags = re.findall(r'#[\w\u00c0-\u024f\u1e00-\u1eff]+(?:_[\w\u00c0-\u024f\u1e00-\u1eff]+)*', text, re.IGNORECASE)
    return list(set(hashtags))  # Remove duplicates

def extract_mentions(text: str) -> List[str]:
    """Extract @mentions from text"""
    mentions = re.findall(r'@[A-Za-z0-9._]+', text)
    return list(set(mentions))  # Remove duplicates

def build_google_url(keyword: str, start: int = 0) -> str:
    """Build Google search URL for Instagram posts"""
    query = "+".join(keyword.split())
    return f"https://www.google.com/search?q=site:instagram.com+{query}&start={start}"

def scrape_post(url: str, dedup_manager: EnhancedDeduplicationManager, batch_manager: AdaptiveBatchManager, 
                rate_limiter: AdaptiveRateLimiter, circuit_breaker: CircuitBreaker,
                performance_monitor: PerformanceMonitor, retry_count: int = 2) -> Optional[ScrapedPost]:
    """
    Scrape a single Instagram post with retry logic and advanced optimizations
    This function is designed for parallel execution
    """
    # Check circuit breaker first
    if not circuit_breaker.can_execute():
        logger.warning(f"🚫 Circuit breaker OPEN, skipping URL: {url}")
        performance_monitor.record_operation('skipped_circuit_breaker', 0, False)
        return None
        
    # Check if URL already processed
    if dedup_manager.is_url_processed(url):
        logger.debug(f"⏭️ Skipping already processed URL: {url}")
        performance_monitor.record_operation('skipped_duplicate', 0, True)
        return None
    
    # Apply rate limiting
    rate_limiter.wait()
    
    start_time = time.time()
    driver = None
    
    for attempt in range(retry_count + 1):
        try:
            performance_monitor.record_operation('attempt_started', time.time() - start_time, True)
            
            # Create driver for this thread
            driver = create_undetected_driver()
            
            # Navigate to post
            driver.get(url)
            
            # Wait for page to load with adaptive timeout
            wait = WebDriverWait(driver, 5)  # Reduced from 10 to 5 seconds
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # Get page source
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Extract username
            username = ""
            try:
                # Multiple strategies for username extraction
                username_element = soup.find("a", href=re.compile(r"^/[^/]+/$"))
                if not username_element:
                    username_element = soup.find("span", string=re.compile(r"@\w+"))
                if username_element:
                    username = username_element.text.strip().replace("@", "")
                else:
                    # Extract from URL as fallback
                    username_match = re.search(r'instagram\.com/([^/]+)/', url)
                    if username_match:
                        username = username_match.group(1)
            except Exception:
                username = "unknown"
            
            # Check if username already processed (reached max posts limit)
            if username and dedup_manager.is_username_processed(username):
                user_count = dedup_manager.get_user_post_count(username)
                logger.debug(f"⏭️ Skipping user @{username} - already processed {user_count} posts (max: {dedup_manager.max_posts_per_user})")
                dedup_manager.add_url(url)  # Still mark URL as processed
                return None
            
            # Extract all text content
            text_elements = soup.find_all(["span", "div", "p"], string=True)
            all_text = " ".join([elem.get_text() for elem in text_elements if elem.get_text().strip()])

            # Extract caption (longest meaningful text)
            potential_captions = [elem.get_text().strip() for elem in text_elements 
                                if len(elem.get_text().strip()) > 30 
                                and not elem.get_text().strip().startswith("@")
                                and "ago" not in elem.get_text().lower()]

            caption = potential_captions[0][:200] + "..." if potential_captions and len(potential_captions[0]) > 200 else (potential_captions[0] if potential_captions else "")

            # Always include caption in contact info extraction
            contact_text = all_text
            if caption and caption not in contact_text:
                contact_text += " " + caption

            # Extract information using enhanced functions
            emails, phones = extract_contact_info(contact_text)
            hashtags = extract_hashtags_enhanced(contact_text)
            mentions = extract_mentions(contact_text)
            
            # Extract caption (longest meaningful text)
            potential_captions = [elem.get_text().strip() for elem in text_elements 
                                if len(elem.get_text().strip()) > 30 
                                and not elem.get_text().strip().startswith("@")
                                and "ago" not in elem.get_text().lower()]
            
            caption = potential_captions[0][:200] + "..." if potential_captions and len(potential_captions[0]) > 200 else (potential_captions[0] if potential_captions else "")
            
            # Create result
            result = ScrapedPost(
                url=url,
                username=username,
                emails=emails,
                phones=phones,
                hashtags=hashtags[:20],  # Limit hashtags
                mentions=mentions[:10],  # Limit mentions
                caption=caption,
                comments_found=len(text_elements),
                timestamp=datetime.now().isoformat(),
                batch_id=f"batch_{batch_manager.batch_counter}"
            )
            
            # Mark as processed
            dedup_manager.add_url(url)
            if username:
                dedup_manager.add_username(username)
                current_count = dedup_manager.get_user_post_count(username)
                logger.info(f"✅ Processed @{username} ({current_count}/{dedup_manager.max_posts_per_user}): {len(emails)} emails, {len(phones)} phones, {len(hashtags)} hashtags")
            else:
                logger.info(f"✅ Processed post: {len(emails)} emails, {len(phones)} phones, {len(hashtags)} hashtags")
            
            # Add to batch
            batch_manager.add_result(result)
            
            # Record successful operation
            circuit_breaker.record_success()
            performance_monitor.record_operation('scrape_success', time.time() - start_time, True)
            rate_limiter.record_success()
            
            return result
            
        except TimeoutException:
            error_msg = f"⏰ Timeout on post (attempt {attempt + 1}): {url}"
            logger.warning(error_msg)
            circuit_breaker.record_failure()
            rate_limiter.record_failure()
            performance_monitor.record_operation('timeout', time.time() - start_time, False)
            
            if attempt == retry_count:
                logger.error(f"❌ Failed to process after {retry_count + 1} attempts: {url}")
                
        except Exception as e:
            error_msg = f"❌ Error processing post (attempt {attempt + 1}): {url} - {str(e)}"
            logger.error(error_msg)
            circuit_breaker.record_failure()
            rate_limiter.record_failure()
            performance_monitor.record_operation('error', time.time() - start_time, False)
            
            if attempt == retry_count:
                logger.error(f"❌ Failed to process after {retry_count + 1} attempts: {url}")
                
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            driver = None
        
        # Exponential backoff for retries with jitter
        if attempt < retry_count:
            backoff_time = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(backoff_time)
    
    # Record final failure
    performance_monitor.record_operation('final_failure', time.time() - start_time, False)
    return None

def collect_instagram_links(keyword: str, max_google_pages: int = 2) -> List[str]:
    """Collect Instagram links from Google search"""
    links = []
    driver = create_undetected_driver()
    
    try:
        for page in range(max_google_pages):
            start = page * 10
            search_url = build_google_url(keyword, start)
            logger.info(f"📄 Searching Google page {page + 1}: {search_url}")
            
            try:
                driver.get(search_url)
                wait = WebDriverWait(driver, 5)
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # Save debug file for first page
                if page == 0:
                    debug_file = os.path.join("results", "debug_google_search.html")
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    logger.info(f"💾 Saved debug file: {debug_file}")
                
                # Extract Instagram links
                page_links = 0
                for a_tag in soup.select("a"):
                    href = a_tag.get("href", "")
                    if "instagram.com/" in href and ("instagram.com/p/" in href or "instagram.com/reel/" in href):
                        # Clean up URL
                        if href.startswith("/url?q="):
                            cleaned_url = href.replace("/url?q=", "").split("&")[0]
                        else:
                            cleaned_url = href
                        
                        if cleaned_url.startswith("http") and cleaned_url not in links:
                            links.append(cleaned_url)
                            page_links += 1
                            logger.debug(f"✅ Found Instagram link: {cleaned_url}")
                
                logger.info(f"📊 Found {page_links} new links on page {page + 1}. Total: {len(links)}")
                
            except TimeoutException:
                logger.warning(f"⏰ Timeout on Google search page {page + 1}")
            except Exception as e:
                logger.error(f"❌ Error on Google search page {page + 1}: {str(e)}")
    
    finally:
        driver.quit()
    
    logger.info(f"🎯 Total Instagram links collected: {len(links)}")
    return links

def run_parallel_scraper(keyword: str, target_unique_accounts: int = 5, max_google_pages: int = 2, 
                        user_tier: str = "basic", max_workers: int = 4) -> List[ScrapedPost]:
    """
    Main scraper function with parallel processing and all enhancements
    """
    # Define tier limits
    tier_limits = {
        "basic": {"max_accounts": 10, "max_posts": 20, "max_google_pages": 2},
        "premium": {"max_accounts": 50, "max_posts": 100, "max_google_pages": 5},
        "enterprise": {"max_accounts": 200, "max_posts": 500, "max_google_pages": 10}
    }
    
    # Validate tier and apply limits
    if user_tier not in tier_limits:
        user_tier = "basic"
    
    limits = tier_limits[user_tier]
    
    # Apply tier restrictions
    target_unique_accounts = min(target_unique_accounts, limits["max_accounts"])
    max_google_pages = min(max_google_pages, limits["max_google_pages"])
    max_posts_to_process = limits["max_posts"]
    
    logger.info(f"🎫 User Tier: {user_tier.upper()}")
    logger.info(f"📊 Tier Limits - Max Accounts: {limits['max_accounts']}, Max Posts: {limits['max_posts']}")
    logger.info(f"🎯 Current Request - Accounts: {target_unique_accounts}, Google Pages: {max_google_pages}")
    logger.info(f"🔧 Max Workers: {max_workers}")
    logger.info(f"👥 User Post Limit: Max {dedup_manager.max_posts_per_user} posts per user")
    
    # Initialize advanced managers
    dedup_manager = EnhancedDeduplicationManager()
    batch_manager = AdaptiveBatchManager(initial_batch_size=5, results_dir="results")
    rate_limiter = AdaptiveRateLimiter()
    circuit_breaker = CircuitBreaker()
    performance_monitor = PerformanceMonitor()
    
    # Step 1: Collect Instagram links
    logger.info(f"🔍 Collecting Instagram links for keyword: {keyword}")
    instagram_links = collect_instagram_links(keyword, max_google_pages)
    
    if not instagram_links:
        logger.warning("⚠️ No Instagram links found!")
        return []
    
    # Limit posts to process based on tier
    links_to_process = instagram_links[:max_posts_to_process]
    logger.info(f"📋 Processing {len(links_to_process)} links with {max_workers} parallel workers")
    
    # Step 2: Parallel scraping
    results = []
    unique_accounts_found = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all scraping tasks with advanced managers
        future_to_url = {
            executor.submit(scrape_post, url, dedup_manager, batch_manager, 
                          rate_limiter, circuit_breaker, performance_monitor): url 
            for url in links_to_process
        }
        
        # Process completed tasks
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
                    unique_accounts_found += 1
                    logger.info(f"🎯 Progress: {unique_accounts_found}/{target_unique_accounts} unique accounts found")
                    
                    # Stop if we've reached our target
                    if unique_accounts_found >= target_unique_accounts:
                        logger.info(f"🎯 Reached target of {target_unique_accounts} unique accounts!")
                        # Cancel remaining futures
                        for f in future_to_url:
                            f.cancel()
                        break
                        
            except Exception as e:
                logger.error(f"❌ Error processing {url}: {str(e)}")
    
    # Save any remaining results in final batch
    batch_manager.save_final_batch()
    
    # Generate comprehensive performance report
    performance_report = performance_monitor.generate_report()
    circuit_status = circuit_breaker.get_status()
    
    logger.info(f"🏁 Enhanced parallel scraping complete!")
    logger.info(f"📊 Results: {len(results)} posts processed, {unique_accounts_found} unique accounts")
    logger.info(f"💾 Results saved in adaptive batches to 'results' directory")
    logger.info(f"⚡ Performance: {performance_report['avg_processing_time']:.2f}s avg, {performance_report['success_rate']:.1f}% success rate")
    logger.info(f"🛡️ Circuit Breaker: {circuit_status['state']} (Failures: {circuit_status['failure_count']})")
    logger.info(f"📈 Rate Limiter: {rate_limiter.current_delay:.2f}s current delay")
    
    # Save performance metrics
    metrics_file = os.path.join("results", f"performance_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    try:
        with open(metrics_file, 'w') as f:
            json.dump({
                'performance': performance_report,
                'circuit_breaker': circuit_status,
                'rate_limiter': {'current_delay': rate_limiter.current_delay},
                'scraping_summary': {
                    'total_processed': len(results),
                    'unique_accounts': unique_accounts_found,
                    'timestamp': datetime.now().isoformat()
                }
            }, f, indent=2)
        logger.info(f"📊 Performance metrics saved to {metrics_file}")
    except Exception as e:
        logger.warning(f"⚠️ Could not save performance metrics: {e}")
    
    
    return results

# Backward compatibility functions
def run_scraper(keyword: str, target_unique_accounts: int = 5, max_google_pages: int = 5, user_tier: str = "basic"):
    """
    Backward compatibility wrapper for the enhanced scraper
    """
    return run_parallel_scraper(
        keyword=keyword,
        target_unique_accounts=target_unique_accounts,
        max_google_pages=max_google_pages,
        user_tier=user_tier,
        max_workers=4
    )

def scrape_specific_user(username: str, max_posts: int = 10, user_tier: str = "basic"):
    """
    Enhanced specific user scraping with parallel processing
    """
    # Define tier limits
    tier_limits = {
        "basic": {"max_posts": 10, "max_user_posts": 5},
        "premium": {"max_posts": 50, "max_user_posts": 25},
        "enterprise": {"max_posts": 200, "max_user_posts": 100}
    }
    
    if user_tier not in tier_limits:
        user_tier = "basic"
    
    limits = tier_limits[user_tier]
    max_posts = min(max_posts, limits["max_user_posts"])
    
    logger.info(f"🎫 User Tier: {user_tier.upper()}")
    logger.info(f"👤 Scraping specific user: @{username}")
    logger.info(f"📊 Max posts to process: {max_posts}")
    
    driver = create_undetected_driver()
    
    try:
        # Clean username
        clean_username = username.replace("@", "").strip()
        profile_url = f"https://www.instagram.com/{clean_username}/"
        
        logger.info(f"🔗 Accessing profile: {profile_url}")
        driver.get(profile_url)
        
        # Wait for page load
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        page_source = driver.page_source
        
        # Check for errors
        if any(error in page_source for error in ["Page Not Found", "This page isn't available", "Sorry, this page isn't available"]):
            return {"error": f"Instagram profile @{clean_username} not found"}
        
        if any(private in page_source for private in ["This Account is Private", "This account is private"]):
            return {"error": f"Instagram profile @{clean_username} is private"}
        
        if any(blocked in page_source for blocked in ["Try again later", "Please wait a few minutes"]):
            return {"error": "Instagram is temporarily blocking requests. Please try again in a few minutes."}
        
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Extract profile data
        profile_data = {
            "username": clean_username,
            "profile_url": profile_url,
            "bio": "",
            "posts": []
        }
        
        # Extract bio
        try:
            bio_elements = soup.find_all("span", {"dir": "auto"})
            for element in bio_elements:
                text = element.get_text().strip()
                if len(text) > 20 and not text.startswith("@"):
                    profile_data["bio"] = text
                    break
        except Exception:
            pass
        
        # Find post links
        post_links = []
        links = soup.find_all("a", href=True)
        
        for link in links:
            href = link.get("href")
            if href and ("/p/" in href or "/reel/" in href):
                full_url = f"https://www.instagram.com{href}" if href.startswith("/") else href
                full_url = full_url.split('?')[0]  # Remove query parameters
                if full_url not in post_links:
                    post_links.append(full_url)
                    if len(post_links) >= max_posts:
                        break
        
        logger.info(f"📊 Found {len(post_links)} posts to analyze")
        
        # Initialize advanced managers for user scraping
        dedup_manager = EnhancedDeduplicationManager()
        batch_manager = AdaptiveBatchManager(initial_batch_size=3, results_dir="results")
        rate_limiter = AdaptiveRateLimiter(base_delay=1.5)  # More conservative for user scraping
        circuit_breaker = CircuitBreaker()
        performance_monitor = PerformanceMonitor()
        
        # Process posts in parallel (with smaller worker count for single user)
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_url = {
                executor.submit(scrape_post, url, dedup_manager, batch_manager, 
                              rate_limiter, circuit_breaker, performance_monitor): url 
                for url in post_links[:max_posts]
            }
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    if result:
                        profile_data["posts"].append(asdict(result))
                except Exception as e:
                    logger.error(f"❌ Error processing post {url}: {str(e)}")
        
        # Save final batch
        batch_manager.save_final_batch()
        
        # Generate performance report for user scraping
        performance_report = performance_monitor.generate_report()
        logger.info(f"⚡ User scraping performance: {performance_report['avg_processing_time']:.2f}s avg, {performance_report['success_rate']:.1f}% success rate")
        
        # Extract profile-level contact info
        if profile_data["bio"]:
            bio_emails, bio_phones = extract_contact_info(profile_data["bio"])
            profile_data["bio_emails"] = bio_emails
            profile_data["bio_phones"] = bio_phones
        else:
            profile_data["bio_emails"] = []
            profile_data["bio_phones"] = []
        
        logger.info(f"🏁 Enhanced profile scraping complete! Analyzed {len(profile_data['posts'])} posts")
        return profile_data
        
    except Exception as e:
        logger.error(f"❌ Error scraping profile: {str(e)}")
        return {"error": f"Failed to scrape profile: {str(e)}"}
    finally:
        driver.quit()

# Test function (only run when called directly, not when imported)
if __name__ == "__main__":
    # Test the enhanced scraper
    logger.info("🧪 Testing Enhanced Scraper")
    results = run_parallel_scraper(
        keyword="rooms for rent",
        target_unique_accounts=3,
        max_google_pages=1,
        user_tier="basic",
        max_workers=3
    )
    logger.info(f"✅ Test completed! Found {len(results)} results")
