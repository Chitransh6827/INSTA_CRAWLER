# tier_system.py
# User Tier Management System

class TierSystem:
    """
    Manages user tiers and their limitations
    """
    
    TIERS = {
        "basic": {
            "name": "Basic",
            "max_accounts": 10,
            "max_posts": 20,
            "max_google_pages": 2,
            "price": 0,
            "description": "Perfect for small-scale research",
            "features": [
                "Up to 10 unique accounts",
                "Up to 20 posts processed",
                "2 Google search pages",
                "Basic contact extraction",
                "Hashtag analysis"
            ],
            "color": "#718096"
        },
        "premium": {
            "name": "Premium",
            "max_accounts": 50,
            "max_posts": 100,
            "max_google_pages": 5,
            "price": 29.99,
            "description": "Ideal for marketing professionals",
            "features": [
                "Up to 50 unique accounts",
                "Up to 100 posts processed",
                "5 Google search pages",
                "Advanced contact extraction",
                "Comprehensive hashtag analysis",
                "Priority processing",
                "Email export feature"
            ],
            "color": "#667eea"
        },
        "enterprise": {
            "name": "Enterprise",
            "max_accounts": 200,
            "max_posts": 500,
            "max_google_pages": 10,
            "price": 99.99,
            "description": "For large-scale business intelligence",
            "features": [
                "Up to 200 unique accounts",
                "Up to 500 posts processed",
                "10 Google search pages",
                "Premium contact extraction",
                "Deep hashtag & sentiment analysis",
                "API access",
                "Bulk export options",
                "24/7 priority support",
                "Custom reporting"
            ],
            "color": "#f093fb"
        }
    }
    
    @staticmethod
    def get_tier_info(tier_name):
        """Get information about a specific tier"""
        return TierSystem.TIERS.get(tier_name.lower(), TierSystem.TIERS["basic"])
    
    @staticmethod
    def validate_tier(tier_name):
        """Validate if tier exists"""
        return tier_name.lower() in TierSystem.TIERS
    
    @staticmethod
    def get_tier_limits(tier_name):
        """Get the limits for a specific tier"""
        tier_info = TierSystem.get_tier_info(tier_name)
        return {
            "max_accounts": tier_info["max_accounts"],
            "max_posts": tier_info["max_posts"],
            "max_google_pages": tier_info["max_google_pages"]
        }
    
    @staticmethod
    def apply_tier_restrictions(target_accounts, max_pages, tier_name):
        """Apply tier restrictions to user input"""
        limits = TierSystem.get_tier_limits(tier_name)
        
        restricted_accounts = min(target_accounts, limits["max_accounts"])
        restricted_pages = min(max_pages, limits["max_google_pages"])
        
        return {
            "accounts": restricted_accounts,
            "pages": restricted_pages,
            "max_posts": limits["max_posts"],
            "was_restricted": (
                target_accounts > limits["max_accounts"] or 
                max_pages > limits["max_google_pages"]
            )
        }
    
    @staticmethod
    def get_upgrade_suggestion(current_tier, requested_accounts, requested_pages):
        """Suggest tier upgrade if needed"""
        current_limits = TierSystem.get_tier_limits(current_tier)
        
        if (requested_accounts <= current_limits["max_accounts"] and 
            requested_pages <= current_limits["max_google_pages"]):
            return None
        
        # Find the minimum tier that can handle the request
        for tier_name, tier_info in TierSystem.TIERS.items():
            if (requested_accounts <= tier_info["max_accounts"] and 
                requested_pages <= tier_info["max_google_pages"]):
                return {
                    "suggested_tier": tier_name,
                    "tier_info": tier_info,
                    "reason": f"To process {requested_accounts} accounts and {requested_pages} pages"
                }
        
        return {
            "suggested_tier": "enterprise",
            "tier_info": TierSystem.TIERS["enterprise"],
            "reason": "For maximum processing capacity"
        }


class UserSession:
    """
    Simple user session management (in production, use proper database)
    """
    
    def __init__(self):
        # In production, this would be stored in a database
        self.users = {
            "demo_user": {
                "tier": "basic",
                "usage_today": 0,
                "max_daily_usage": 5  # Basic users get 5 scrapes per day
            }
        }
    
    def get_user_tier(self, user_id="demo_user"):
        """Get user's current tier"""
        user = self.users.get(user_id, {"tier": "basic"})
        return user["tier"]
    
    def can_user_scrape(self, user_id="demo_user"):
        """Check if user can perform scraping based on daily limits"""
        user = self.users.get(user_id, {"usage_today": 0, "max_daily_usage": 5})
        return user["usage_today"] < user["max_daily_usage"]
    
    def increment_usage(self, user_id="demo_user"):
        """Increment user's daily usage"""
        if user_id not in self.users:
            self.users[user_id] = {"tier": "basic", "usage_today": 0, "max_daily_usage": 5}
        self.users[user_id]["usage_today"] += 1
    
    def upgrade_user(self, user_id, new_tier):
        """Upgrade user to new tier"""
        if user_id not in self.users:
            self.users[user_id] = {"usage_today": 0}
        
        self.users[user_id]["tier"] = new_tier
        
        # Update daily limits based on tier
        daily_limits = {
            "basic": 5,
            "premium": 25,
            "enterprise": 100
        }
        self.users[user_id]["max_daily_usage"] = daily_limits.get(new_tier, 5)
    
    def reset_usage(self, user_id="demo_user"):
        """Reset user's daily usage counter to zero"""
        if user_id in self.users:
            self.users[user_id]["usage_today"] = 0


# Global session instance (in production, use proper session management)
user_session = UserSession()
