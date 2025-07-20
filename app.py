
# app.py
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_cors import CORS
from scraper import run_scraper, scrape_specific_user
from tier_system import TierSystem, user_session

# Demo users for login (username: password)
DEMO_USERS = {
    'demo': 'password123',
    'admin': 'admin123', 
    'test': 'test123',
    'user': 'user123'
}

app = Flask(__name__, template_folder='templates')
CORS(app)
app.secret_key = 'your_secret_key_change_this_in_production'  # Change this in production!

@app.route('/')
def index():
    # Check if user is logged in
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # Get username
    username = session.get('username', 'demo')
    
    # Ensure user has a plan (fallback to basic if missing)
    if not session.get('plan'):
        # Check user_session for existing plan
        user_tier = user_session.get_user_tier(username)
        if user_tier:
            session['plan'] = user_tier
        else:
            # Set default plan
            session['plan'] = 'basic'
            user_session.upgrade_user(username, 'basic')
    
    # Get user's current tier for display - use session plan as source of truth
    user_tier = session.get('plan', 'basic')
    tier_info = TierSystem.get_tier_info(user_tier)
    all_tiers = TierSystem.TIERS
    
    # Ensure user_session is in sync with session
    user_session.upgrade_user(username, user_tier)
    
    return render_template('index.html', 
                         user_tier=user_tier, 
                         tier_info=tier_info,
                         all_tiers=all_tiers,
                         username=username)

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/tiers')
def get_tiers():
    """Get all available tiers"""
    return jsonify(TierSystem.TIERS)

@app.route('/user/tier')
def get_user_tier():
    """Get current user's tier information"""
    user_id = request.args.get('user_id', 'demo_user')
    user_tier = user_session.get_user_tier(user_id)
    tier_info = TierSystem.get_tier_info(user_tier)
    can_scrape = user_session.can_user_scrape(user_id)
    
    return jsonify({
        "current_tier": user_tier,
        "tier_info": tier_info,
        "can_scrape": can_scrape,
        "usage_info": user_session.users.get(user_id, {})
    })

@app.route('/upgrade', methods=['POST'])
def upgrade_tier():
    """Upgrade user tier and update session"""
    # Check if user is logged in
    if not session.get('logged_in'):
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    new_tier = data.get('tier', 'basic')
    username = session.get('username', 'demo')
    
    if not TierSystem.validate_tier(new_tier):
        return jsonify({"error": "Invalid tier"}), 400
    
    # In production, you would process payment here
    # For demo purposes, we'll just upgrade directly
    
    # Update the tier system
    user_session.upgrade_user(username, new_tier)
    
    # Update the session
    session['plan'] = new_tier
    
    return jsonify({
        "success": True,
        "message": f"Successfully upgraded to {new_tier.capitalize()} tier!",
        "new_tier": new_tier,
        "tier_info": TierSystem.get_tier_info(new_tier)
    })

@app.route('/upgrade-session', methods=['POST'])
def upgrade_session_tier():
    """Quick upgrade that immediately updates the user session"""
    if not session.get('logged_in'):
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    new_tier = data.get('tier')
    
    if new_tier not in ['basic', 'premium', 'enterprise']:
        return jsonify({"error": "Invalid tier"}), 400
    
    username = session.get('username', 'demo')
    
    # Update both the tier system and session - this is the key fix!
    user_session.upgrade_user(username, new_tier)
    session['plan'] = new_tier  # Update session to reflect immediately
    
    return jsonify({
        "success": True,
        "message": f"Successfully upgraded to {new_tier.capitalize()} plan!",
        "new_tier": new_tier,
        "tier_info": TierSystem.get_tier_info(new_tier),
        "redirect": True
    })

@app.route('/scrape', methods=['POST'])
def scrape():
    # Allow Chrome extension requests without session
    data = request.json
    user_id = data.get('user_id')
    if user_id == 'chrome_ext_user':
        username = 'chrome_ext_user'
        user_tier = 'basic'
    else:
        # Check if user is logged in
        if not session.get('logged_in'):
            return jsonify({"error": "Not logged in"}), 401
        username = session.get('username', 'demo')
        user_tier = session.get('plan', 'basic')
    
    keyword = data.get('keyword')
    unique_accounts = int(data.get('unique_accounts', 5))
    
    # Get user's tier from session (source of truth)
    user_tier = session.get('plan', 'basic')
    

    # Daily usage limit check disabled for unlimited scraping
    
    # Apply tier restrictions
    restrictions = TierSystem.apply_tier_restrictions(
        unique_accounts, 5, user_tier  # 5 is default max_google_pages
    )
    
    # Check if upgrade is suggested
    upgrade_suggestion = None
    if restrictions["was_restricted"]:
        upgrade_suggestion = TierSystem.get_upgrade_suggestion(
            user_tier, unique_accounts, 5
        )
    
    print(f"🔍 Running scraper for keyword: {keyword}")
    print(f"🎫 User: {username}, Tier: {user_tier}")
    print(f"🎯 Requested: {unique_accounts} accounts, Limited to: {restrictions['accounts']} accounts")
    
    try:
        # Run scraper with tier restrictions
        results = run_scraper(
            keyword, 
            restrictions["accounts"], 
            restrictions["pages"],
            user_tier
        )
        
        # Increment user's daily usage
        user_session.increment_usage(username)
        
        response_data = {
            "results": results,
            "tier_info": {
                "current_tier": user_tier,
                "restrictions_applied": restrictions["was_restricted"],
                "requested_accounts": unique_accounts,
                "processed_accounts": restrictions["accounts"],
                "max_posts_processed": restrictions["max_posts"]
            }
        }
        
        if upgrade_suggestion:
            response_data["upgrade_suggestion"] = upgrade_suggestion
            
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error during scraping: {str(e)}")
        return jsonify({
            "error": "Scraping failed",
            "message": str(e),
            "current_tier": user_tier
        }), 500

@app.route('/scrape-user', methods=['POST'])
def scrape_user():
    """Scrape data from a specific Instagram user"""
    # Check if user is logged in
    if not session.get('logged_in'):
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    instagram_username = data.get('username', '').strip()
    max_posts = int(data.get('max_posts', 10))
    username = session.get('username', 'demo')
    
    if not instagram_username:
        return jsonify({
            "error": "Username required",
            "message": "Please provide an Instagram username"
        }), 400
    
    # Get user's tier from session
    user_tier = session.get('plan', 'basic')
    

    # Daily usage limit check disabled for unlimited scraping
    
    # Apply tier restrictions for user scraping
    tier_limits = {
        "basic": 5,
        "premium": 25,
        "enterprise": 100
    }
    
    max_allowed_posts = tier_limits.get(user_tier, 5)
    restricted_posts = min(max_posts, max_allowed_posts)
    
    print(f"👤 Scraping user: @{instagram_username}")
    print(f"🎫 User: {username}, Tier: {user_tier}")
    print(f"📊 Requested: {max_posts} posts, Limited to: {restricted_posts} posts")
    
    try:
        # Run user-specific scraper
        result = scrape_specific_user(instagram_username, restricted_posts, user_tier)
        
        # Check for errors
        if "error" in result:
            return jsonify(result), 404
        
        # Increment user's daily usage
        user_session.increment_usage(username)
        
        response_data = {
            "profile_data": result,
            "tier_info": {
                "current_tier": user_tier,
                "restrictions_applied": max_posts > restricted_posts,
                "requested_posts": max_posts,
                "processed_posts": restricted_posts,
                "max_allowed_posts": max_allowed_posts
            }
        }
        
        # Handle warnings from scraper
        if "warning" in result:
            response_data["warning"] = result["warning"]
        
        if max_posts > restricted_posts:
            response_data["upgrade_suggestion"] = {
                "message": f"Upgrade to access more posts. Current tier allows {max_allowed_posts} posts per user.",
                "suggested_tier": "premium" if user_tier == "basic" else "enterprise"
            }
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error during user scraping: {str(e)}")
        return jsonify({
            "error": "User scraping failed", 
            "message": str(e),
            "current_tier": user_tier
        }), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember')
        
        # Check demo credentials
        if username in DEMO_USERS and DEMO_USERS[username] == password:
            session['logged_in'] = True
            session['username'] = username
            session['remember'] = bool(remember)
            
            # Always set user to basic plan and go directly to main page
            # This simplifies the flow and eliminates the select_plan step
            session['plan'] = 'basic'
            user_session.upgrade_user(username, 'basic')
            flash('Login successful! You are on the Basic plan.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password. Please try the demo credentials.', 'error')
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/select_plan', methods=['GET', 'POST'])
def select_plan():
    # Check if user is logged in
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        plan = request.form.get('plan', 'basic')
        username = session.get('username', 'demo')
        
        # Update both session and user_session
        session['plan'] = plan
        user_session.upgrade_user(username, plan)
        
        flash(f'Plan updated to {plan.capitalize()}!', 'success')
        return redirect(url_for('index'))
    
    # Get current plan for display
    current_plan = session.get('plan', 'basic')
    all_tiers = TierSystem.TIERS
    
    return render_template('select_plan.html', 
                         current_plan=current_plan,
                         all_tiers=all_tiers)

if __name__ == '__main__':
    print("🚀 Starting Inpostly Web Application...")
    print("📍 Open your browser and go to: http://127.0.0.1:500")
    print("🔑 Use demo credentials - Username: demo, Password: password123")
    print("=" * 60)
    app.run(host='127.0.0.1', port=500, debug=False)
