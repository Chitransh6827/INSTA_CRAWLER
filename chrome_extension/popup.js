// popup.js - Chrome extension popup logic
// Communicates with Flask backend at http://localhost:500

let currentResults = [];
let isProcessing = false;

// Check login status on load
document.addEventListener('DOMContentLoaded', async function() {
    const { inpostly_logged_in, inpostly_plan } = await chrome.storage.local.get(['inpostly_logged_in', 'inpostly_plan']);
    if (!inpostly_logged_in) {
        window.location.href = 'login.html';
        return;
    }
    // Show current plan in header (as a badge in the topbar)
    const topbar = document.querySelector('.topbar-actions');
    if (topbar && inpostly_plan) {
        let planBadge = document.getElementById('planBadge');
        if (!planBadge) {
            planBadge = document.createElement('span');
            planBadge.id = 'planBadge';
            planBadge.style.cssText = 'background:var(--success);color:white;padding:0.15rem 0.6rem;border-radius:12px;font-size:0.90rem;font-weight:600;letter-spacing:0.5px;margin-right:0.5rem;';
            topbar.insertBefore(planBadge, topbar.firstChild);
        }
        planBadge.textContent = inpostly_plan.charAt(0).toUpperCase() + inpostly_plan.slice(1) + ' Plan';
    }
    // Attach form handler only if logged in
    const searchForm = document.getElementById('searchForm');
    if (searchForm) {
        searchForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            if (isProcessing) return;
            const keyword = document.getElementById('keyword').value.trim();
            const uniqueAccounts = parseInt(document.getElementById('unique_accounts').value);
            if (!keyword) {
                alert('Please enter a search keyword');
                return;
            }
            await startScraping(keyword, uniqueAccounts);
        });
    }
    // Logout button
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async function() {
            await chrome.storage.local.remove(['inpostly_logged_in', 'inpostly_username', 'inpostly_plan']);
            window.location.href = 'login.html';
        });
    }
    // Change Plan button
    const changePlanBtn = document.getElementById('changePlanBtn');
    if (changePlanBtn) {
        changePlanBtn.addEventListener('click', function() {
            window.location.href = 'plan.html';
        });
    }
});

async function startScraping(keyword, uniqueAccounts) {
    isProcessing = true;
    const searchBtn = document.getElementById('searchBtn');
    const btnText = searchBtn.querySelector('.btn-text');
    const spinner = searchBtn.querySelector('.spinner');
    const progressContainer = document.getElementById('progressContainer');
    searchBtn.disabled = true;
    btnText.textContent = 'Processing...';
    spinner.style.display = 'block';
    progressContainer.style.display = 'block';
    let progress = 0;
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const progressInterval = setInterval(() => {
        progress += Math.random() * 15;
        if (progress > 90) progress = 90;
        progressBar.style.width = progress + '%';
        progressText.textContent = `Processing... ${Math.round(progress)}%`;
    }, 500);
    try {
        const response = await fetch('http://localhost:500/scrape', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                keyword: keyword,
                unique_accounts: uniqueAccounts,
                user_id: 'chrome_ext_user'
            })
        });
        const data = await response.json();
        clearInterval(progressInterval);
        progressBar.style.width = '100%';
        progressText.textContent = 'Complete!';
        if (data.error) {
            throw new Error(data.message || data.error);
        }
        currentResults = data.results || [];
        displayResults(currentResults, data.tier_info);
        updateStats(currentResults);
        updateDownloadButtonVisibility(currentResults);
    } catch (error) {
        clearInterval(progressInterval);
        console.error('Scraping failed:', error);
        alert('Scraping failed: ' + error.message);
    } finally {
        isProcessing = false;
        searchBtn.disabled = false;
        btnText.textContent = 'Start Scraping';
        spinner.style.display = 'none';
        setTimeout(() => {
            progressContainer.style.display = 'none';
            progressBar.style.width = '0%';
        }, 2000);
    }
}

function displayResults(results, tierInfo) {
    const resultsContainer = document.getElementById('resultsContainer');
    const resultsBody = document.getElementById('resultsBody');
    const resultsSubtitle = document.getElementById('resultsSubtitle');
    resultsContainer.style.display = 'block';
    resultsSubtitle.textContent = `Found ${results.length} results`;
    if (results.length === 0) {
        resultsBody.innerHTML = `
            <div style="text-align: center; padding: 2rem; color: var(--text-muted);">
                <i class="fas fa-search" style="font-size: 3rem; margin-bottom: 1rem; opacity: 0.3;"></i>
                <p>No results found. Try a different keyword or adjust your search parameters.</p>
            </div>
        `;
        return;
    }
    resultsBody.innerHTML = results.map((result, index) => `
        <div class="result-item">
            <div class="result-header">
                <div class="result-avatar">
                    ${result.username ? result.username.charAt(0).toUpperCase() : (index + 1)}
                </div>
                <div class="result-info">
                    <h4><a href="${result.url}" target="_blank" class="username-link">@${result.username || 'Unknown'}</a></h4>
                    <p class="post-url">${result.url}</p>
                    <div class="post-indicator">
                        <span class="post-badge">Post ${result.batch_id ? result.batch_id.split('_')[1] || '1' : '1'}</span>
                    </div>
                </div>
            </div>
            <div class="result-details">
                <div class="detail-group">
                    <div class="detail-label">Emails Found</div>
                    <div class="detail-value">
                        ${result.emails.length > 0 ? result.emails.join(', ') : 'None found'}
                    </div>
                </div>
                <div class="detail-group">
                    <div class="detail-label">Phone Numbers</div>
                    <div class="detail-value">
                        ${result.phones.length > 0 ? result.phones.join(', ') : 'None found'}
                    </div>
                </div>
                <div class="detail-group">
                    <div class="detail-label">Comments Analyzed</div>
                    <div class="detail-value">${result.comments_found || 0}</div>
                </div>
                <div class="detail-group">
                    <div class="detail-label">Hashtags</div>
                    <div class="detail-value">
                        <div class="hashtags">
                            ${result.hashtags.slice(0, 5).map(tag => `<span class="hashtag">${tag}</span>`).join('')}
                            ${result.hashtags.length > 5 ? `<span class="hashtag">+${result.hashtags.length - 5} more</span>` : ''}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `).join('');
    updateDownloadButtonVisibility(results);
}

function updateStats(results) {
    // You can implement stats display in the popup if needed
}

function downloadResultsAsJSON(results) {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(results, null, 2));
    const dlAnchorElem = document.createElement('a');
    dlAnchorElem.setAttribute("href", dataStr);
    dlAnchorElem.setAttribute("download", "scraping_results.json");
    document.body.appendChild(dlAnchorElem);
    dlAnchorElem.click();
    dlAnchorElem.remove();
}

function updateDownloadButtonVisibility(results) {
    const btn = document.getElementById('downloadResultsBtn');
    if (btn) {
        if (results && results.length > 0) {
            btn.style.display = 'block';
            btn.onclick = () => downloadResultsAsJSON(results);
        } else {
            btn.style.display = 'none';
        }
    }
}
