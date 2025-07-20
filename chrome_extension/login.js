// login.js for Chrome extension
// Handles login and redirects to popup.html on success

document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('loginForm');
    const loginError = document.getElementById('loginError');
    loginForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        loginError.style.display = 'none';
        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;
        try {
            const response = await fetch('http://localhost:500/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`
            });
            if (response.redirected || response.url.endsWith('/')) {
                // Login success (Flask redirects to /)
                await chrome.storage.local.set({ inpostly_logged_in: true, inpostly_username: username });
                window.location.href = 'plan.html';
            } else {
                const text = await response.text();
                if (text.includes('Invalid username or password')) {
                    loginError.textContent = 'Invalid username or password.';
                    loginError.style.display = 'block';
                } else {
                    loginError.textContent = 'Login failed. Please try again.';
                    loginError.style.display = 'block';
                }
            }
        } catch (err) {
            loginError.textContent = 'Could not connect to backend.';
            loginError.style.display = 'block';
        }
    });
});
