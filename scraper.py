# scraper.py
# Enhanced Instagram Scraper Integration with Parallel Processing
# Combines legacy support with new high-performance enhanced_scraper.py


import time
import re
import json
import redis
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
# Import enhanced scraper functions
try:
    # Redis connection (localhost:6379 by default)
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
except Exception as e:
    print(f"⚠️ Redis not available: {e}")
    redis_client = None

# Import enhanced scraper functions
try:
    from enhanced_scraper import (
        run_parallel_scraper,
        scrape_specific_user as enhanced_scrape_specific_user,
        logger
    )
    ENHANCED_AVAILABLE = True
    print("✅ Enhanced scraper loaded successfully!")
except ImportError as e:
    print(f"⚠️ Enhanced scraper not available: {e}")
    ENHANCED_AVAILABLE = False

def build_google_url(keyword, start=0):
    query = "+".join(keyword.split())
    return f"https://www.google.com/search?q=site:instagram.com+{query}&start={start}"

def extract_contact_info(text):
    emails = re.findall(r"[\w\.-]+@[\w\.-]+", text)
    phones = re.findall(r"\+?\d[\d\s\-]{8,}\d", text)
    return emails, phones

def extract_hashtags(text):
    return re.findall(r"#\w+", text)

def run_scraper(keyword, target_unique_accounts=5, max_google_pages=5, user_tier="basic"):
    """
    Main scraper function with automatic fallback to enhanced version
    """
    # Redis cache key for this search
    cache_key = f"scraper:search:{keyword}:{target_unique_accounts}:{max_google_pages}:{user_tier}"
    if redis_client:
        cached = redis_client.get(cache_key)
        if cached:
            print(f"♻️ Returning cached results for '{keyword}' (accounts={target_unique_accounts}, pages={max_google_pages}, tier={user_tier})")
            return json.loads(cached)

    # Try to use enhanced scraper first for better performance
    if ENHANCED_AVAILABLE:
        try:
            print("🚀 Using enhanced parallel scraper...")
            results = run_parallel_scraper(
                keyword=keyword,
                target_unique_accounts=target_unique_accounts,
                max_google_pages=max_google_pages,
                user_tier=user_tier,
                max_workers=4
            )
            # Convert enhanced results to legacy format for backward compatibility
            if results:
                legacy_format = []
                for result in results:
                    legacy_result = {
                        "post_url": result.url,
                        "username": result.username,
                        "emails": result.emails,
                        "phones": result.phones,
                        "hashtags": result.hashtags,
                        "mentions": result.mentions,
                        "caption": result.caption,
                        "timestamp": result.timestamp
                    }
                    legacy_format.append(legacy_result)
                print(f"✅ Enhanced scraper completed! Found {len(legacy_format)} results")
                if redis_client:
                    redis_client.setex(cache_key, 3600, json.dumps(legacy_format))  # Cache for 1 hour
                return legacy_format
            else:
                print("⚠️ Enhanced scraper returned no results, falling back to legacy...")
        except Exception as e:
            print(f"❌ Enhanced scraper failed: {e}")
            print("🔄 Falling back to legacy scraper...")
    else:
        print("🔄 Using legacy scraper (enhanced not available)...")
    
    # Legacy scraper implementation (fallback)
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
    
    print(f"🎫 User Tier: {user_tier.upper()}")
    print(f"📊 Tier Limits - Max Accounts: {limits['max_accounts']}, Max Posts: {limits['max_posts']}")
    print(f"🎯 Current Request - Accounts: {target_unique_accounts}, Google Pages: {max_google_pages}")
    
    # Setup Selenium with webdriver-manager
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # Use webdriver-manager to automatically handle ChromeDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(10)

    # Step 1: Google Search (Paginated)
    links = []
    start = 0
    print(f"🔍 Searching Google for Instagram links with keyword: {keyword}")
    
    while len(links) < 50 and start < max_google_pages * 10:
        try:
            search_url = build_google_url(keyword, start)
            print(f"📄 Searching page {start//10 + 1}: {search_url}")
            driver.get(search_url)
            time.sleep(2)
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # Debug: Save the first page to see what we're getting
            if start == 0:
                with open("debug_google_search.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                print("💾 Saved debug_google_search.html for inspection")

            page_links = 0
            for a_tag in soup.select("a"):
                href = a_tag.get("href", "")
                if "instagram.com/" in href and ("instagram.com/p/" in href or "instagram.com/reel/" in href):
                    # Clean up the URL
                    if href.startswith("/url?q="):
                        cleaned_url = href.replace("/url?q=", "").split("&")[0]
                    else:
                        cleaned_url = href
                    
                    if cleaned_url.startswith("http") and cleaned_url not in links:
                        links.append(cleaned_url)
                        page_links += 1
                        print(f"✅ Found Instagram link: {cleaned_url}")
            
            print(f"📊 Found {page_links} new links on this page. Total: {len(links)}")
            
        except TimeoutException:
            print(f"⏰ Timeout on Google search page {start}, skipping...")
        except Exception as e:
            print(f"❌ Error on Google search page {start}: {str(e)}")

        start += 10
        
        # Break if no links found in last few pages
        if start > 20 and len(links) == 0:
            print("⚠️ No Instagram links found, stopping search")
            break

    print(f"🎯 Total Instagram links found: {len(links)}")

    # Step 2: Scrape Posts
    results = []
    unique_usernames = set()
    processed_urls = set()

    for i, url in enumerate(links[:max_posts_to_process]):  # Use tier-based limit
        if url in processed_urls:
            continue
        processed_urls.add(url)

        print(f"🔗 Processing post {i+1}/{min(len(links), max_posts_to_process)}: {url}")

        try:
            driver.get(url)
            time.sleep(3)
            page_html = driver.page_source
            soup = BeautifulSoup(page_html, 'html.parser')
        except TimeoutException:
            print(f"⏰ Timeout on post: {url}, skipping...")
            continue
        except Exception as e:
            print(f"❌ Error accessing post {url}: {str(e)}")
            continue

        username = ""
        try:
            # Try multiple selectors for username
            username_element = soup.find("a", href=re.compile(r"^/[^/]+/$"))
            if not username_element:
                username_element = soup.find("span", string=re.compile(r"@\w+"))
            if username_element:
                username = username_element.text.strip().replace("@", "")
        except Exception as e:
            print(f"⚠️ Could not extract username from {url}: {str(e)}")
            username = "N/A"

        if username in unique_usernames:
            print(f"⚠️ Username {username} already processed, skipping")
            continue

        unique_usernames.add(username)

        # Extract text content
        comments = [span.get_text() for span in soup.find_all("span") if span.get_text().strip()]
        all_text = " ".join(comments)
        emails, phones = extract_contact_info(all_text)
        hashtags = extract_hashtags(all_text)

        personal_comments = []
        for comment in comments:
            if re.search(r"[\w\.-]+@[\w\.-]+", comment) or re.search(r"\+?\d[\d\s\-]{8,}\d", comment):
                personal_comments.append(comment)

        result = {
            "url": url,
            "username": username,
            "emails": emails,
            "phones": phones,
            "hashtags": hashtags,
            "comments_found": len(comments),
            "personal_comments": personal_comments[:5]
        }
        
        results.append(result)
        print(f"✅ Processed {username}: {len(emails)} emails, {len(phones)} phones, {len(hashtags)} hashtags")

        if len(unique_usernames) >= target_unique_accounts:
            print(f"🎯 Reached target of {target_unique_accounts} unique accounts")
            break

    driver.quit()
    print(f"🏁 Scraping complete! Found {len(results)} results")
    if redis_client:
        redis_client.setex(cache_key, 3600, json.dumps(results))  # Cache for 1 hour
    return results

def scrape_specific_user(username, max_posts=10, user_tier="basic"):
    """
    Scrape posts from a specific Instagram user with enhanced performance
    """
    # Redis cache key for this user scrape
    cache_key = f"scraper:user:{username}:{max_posts}:{user_tier}"
    if redis_client:
        cached = redis_client.get(cache_key)
        if cached:
            print(f"♻️ Returning cached user scrape for '{username}' (posts={max_posts}, tier={user_tier})")
            return json.loads(cached)

    # Try to use enhanced scraper first for better performance
    if ENHANCED_AVAILABLE:
        try:
            print("🚀 Using enhanced user scraper...")
            result = enhanced_scrape_specific_user(
                username=username,
                max_posts=max_posts,
                user_tier=user_tier
            )
            if result and "error" not in result:
                print(f"✅ Enhanced user scraper completed! Found {len(result.get('posts', []))} posts")
                if redis_client:
                    redis_client.setex(cache_key, 3600, json.dumps(result))  # Cache for 1 hour
                return result
            else:
                print(f"⚠️ Enhanced user scraper returned error or no results: {result}")
                print("🔄 Falling back to legacy user scraper...")
        except Exception as e:
            print(f"❌ Enhanced user scraper failed: {e}")
            print("🔄 Falling back to legacy user scraper...")
    else:
        print("🔄 Using legacy user scraper (enhanced not available)...")
    
    # Legacy implementation (fallback)
    # Define tier limits
    tier_limits = {
        "basic": {"max_posts": 10, "max_user_posts": 5},
        "premium": {"max_posts": 50, "max_user_posts": 25},
        "enterprise": {"max_posts": 200, "max_user_posts": 100}
    }
    
    # Validate tier and apply limits
    if user_tier not in tier_limits:
        user_tier = "basic"
    
    limits = tier_limits[user_tier]
    max_posts = min(max_posts, limits["max_user_posts"])
    
    print(f"🎫 User Tier: {user_tier.upper()}")
    print(f"👤 Scraping specific user: @{username}")
    print(f"📊 Max posts to process: {max_posts}")
    
    # Setup Selenium with more stealth options
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")  # Speed up loading
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(20)  # Increased timeout
    
    # Execute script to remove webdriver property
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    try:
        # Clean username (remove @ if present)
        clean_username = username.replace("@", "").strip()
        profile_url = f"https://www.instagram.com/{clean_username}/"
        
        print(f"🔗 Accessing profile: {profile_url}")
        
        # Add random delay to avoid detection
        time.sleep(2 + (hash(username) % 3))  # 2-4 second delay
        
        driver.get(profile_url)
        time.sleep(5)  # Longer wait for page load
        
        # Check if profile exists
        page_source = driver.page_source
        if "Page Not Found" in page_source or "This page isn't available" in page_source or "Sorry, this page isn't available" in page_source:
            print(f"❌ Profile @{clean_username} not found")
            driver.quit()
            return {"error": f"Instagram profile @{clean_username} not found"}
        
        # Check if profile is private
        if "This Account is Private" in page_source or "This account is private" in page_source:
            print(f"🔒 Profile @{clean_username} is private")
            driver.quit()
            return {"error": f"Instagram profile @{clean_username} is private"}
        
        # Check if we're blocked or rate limited
        if "Try again later" in page_source or "Please wait a few minutes" in page_source:
            print(f"⚠️ Rate limited or temporarily blocked")
            driver.quit()
            return {"error": "Instagram is temporarily blocking requests. Please try again in a few minutes."}
        
        # Get profile information
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Extract profile data
        profile_data = {
            "username": clean_username,
            "profile_url": profile_url,
            "bio": "",
            "follower_count": "N/A",
            "following_count": "N/A",
            "posts_count": "N/A",
            "external_url": "",
            "posts": []
        }
        
        # Try to extract bio and stats
        try:
            # Look for bio text
            bio_elements = soup.find_all("span", {"dir": "auto"})
            for element in bio_elements:
                text = element.get_text().strip()
                if len(text) > 20 and not text.startswith("@"):  # Likely bio text
                    profile_data["bio"] = text
                    break
        except Exception as e:
            print(f"⚠️ Could not extract bio: {str(e)}")
        
        # Look for post links with multiple strategies
        post_links = []
        links = soup.find_all("a", href=True)
        
        print(f"🔍 Found {len(links)} total links on profile page")
        
        for link in links:
            href = link.get("href")
            if href:
                # Strategy 1: Direct post/reel links
                if "/p/" in href or "/reel/" in href:
                    full_url = f"https://www.instagram.com{href}" if href.startswith("/") else href
                    # Clean up the URL (remove query parameters)
                    full_url = full_url.split('?')[0]
                    if full_url not in post_links:
                        post_links.append(full_url)
                        print(f"📌 Found post: {full_url}")
                        if len(post_links) >= max_posts:
                            break
        
        # If no posts found, try alternative extraction
        if len(post_links) == 0:
            print("⚠️ No posts found with primary method, trying alternative extraction...")
            
            # Look for any Instagram URLs in the page
            import re
            instagram_pattern = r'https://www\.instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+/'
            all_urls = re.findall(instagram_pattern, driver.page_source)
            
            for url in set(all_urls):  # Remove duplicates
                if url not in post_links:
                    post_links.append(url)
                    print(f"📌 Found post (alternative): {url}")
                    if len(post_links) >= max_posts:
                        break
        
        print(f"📊 Found {len(post_links)} posts to analyze")
        
        # Analyze each post
        for i, post_url in enumerate(post_links[:max_posts]):
            print(f"🔗 Processing post {i+1}/{len(post_links[:max_posts])}: {post_url}")
            
            try:
                # Add random delay between posts
                time.sleep(1 + (i % 2))  # 1-2 second delay
                
                driver.get(post_url)
                time.sleep(3)
                
                # Check if post is accessible
                post_page_source = driver.page_source
                if "Page Not Found" in post_page_source or "This page isn't available" in post_page_source:
                    print(f"⚠️ Post not accessible: {post_url}")
                    continue
                
                if "Try again later" in post_page_source:
                    print(f"⚠️ Rate limited on post: {post_url}")
                    break  # Stop processing more posts if rate limited
                
                post_soup = BeautifulSoup(post_page_source, 'html.parser')
                
                # Extract post data
                post_data = {
                    "url": post_url,
                    "caption": "",
                    "hashtags": [],
                    "mentions": [],
                    "comments": [],
                    "emails": [],
                    "phones": [],
                    "engagement_indicators": []
                }
                
                # Extract all text content
                all_spans = post_soup.find_all("span")
                all_text_content = []
                
                for span in all_spans:
                    text = span.get_text().strip()
                    if text and len(text) > 3:  # Filter out very short text
                        all_text_content.append(text)
                
                full_text = " ".join(all_text_content)
                
                # Extract hashtags and mentions
                hashtags = extract_hashtags(full_text)
                mentions = re.findall(r"@\w+", full_text)
                
                # Extract contact info
                emails, phones = extract_contact_info(full_text)
                
                # Look for caption (longest meaningful text)
                potential_captions = [text for text in all_text_content 
                                    if len(text) > 30 and not text.startswith("@") 
                                    and "ago" not in text.lower() and "like" not in text.lower()]
                if potential_captions:
                    post_data["caption"] = potential_captions[0][:200] + "..." if len(potential_captions[0]) > 200 else potential_captions[0]
                
                # Store extracted data
                post_data["hashtags"] = hashtags[:10]  # Limit hashtags
                post_data["mentions"] = mentions[:5]   # Limit mentions
                post_data["emails"] = emails
                post_data["phones"] = phones
                
                # Look for engagement indicators
                engagement_texts = ["likes", "views", "comments", "shares"]
                for text in all_text_content:
                    for indicator in engagement_texts:
                        if indicator in text.lower() and any(char.isdigit() for char in text):
                            post_data["engagement_indicators"].append(text)
                            break  # Only add one engagement indicator per text
                
                profile_data["posts"].append(post_data)
                print(f"✅ Extracted: {len(hashtags)} hashtags, {len(emails)} emails, {len(phones)} phones")
                
            except TimeoutException:
                print(f"⏰ Timeout on post: {post_url}, skipping...")
                continue
            except Exception as e:
                print(f"❌ Error processing post {post_url}: {str(e)}")
                continue
        
        # Extract profile-level contact info from bio
        if profile_data["bio"]:
            bio_emails, bio_phones = extract_contact_info(profile_data["bio"])
            profile_data["bio_emails"] = bio_emails
            profile_data["bio_phones"] = bio_phones
        else:
            profile_data["bio_emails"] = []
            profile_data["bio_phones"] = []
        
        # If no posts were successfully processed, still return profile data
        posts_processed = len(profile_data["posts"])
        if posts_processed == 0 and len(post_links) > 0:
            print(f"⚠️ No posts could be processed, but profile exists")
            profile_data["warning"] = "Profile found but no posts could be analyzed. This might be due to privacy settings or rate limiting."
        
        print(f"🏁 Profile scraping complete! Analyzed {posts_processed} posts out of {len(post_links)} found")
        return profile_data
        
    except Exception as e:
        print(f"❌ Error scraping profile: {str(e)}")
        return {"error": f"Failed to scrape profile: {str(e)}"}
    finally:
        if redis_client and 'profile_data' in locals():
            redis_client.setex(cache_key, 3600, json.dumps(profile_data))  # Cache for 1 hour
        driver.quit()
