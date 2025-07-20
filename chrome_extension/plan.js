// plan.js for Chrome extension
// Handles plan selection and redirects to popup.html on success

document.addEventListener('DOMContentLoaded', function() {
    let selectedPlan = null;
    const planOptions = document.querySelectorAll('.plan-option');
    const selectPlanBtn = document.getElementById('selectPlanBtn');
    const planError = document.getElementById('planError');

    planOptions.forEach(option => {
        option.addEventListener('click', function() {
            planOptions.forEach(opt => opt.classList.remove('selected'));
            this.classList.add('selected');
            selectedPlan = this.getAttribute('data-plan');
            selectPlanBtn.disabled = false;
        });
    });

    selectPlanBtn.addEventListener('click', async function() {
        if (!selectedPlan) return;
        planError.style.display = 'none';
        const { inpostly_username } = await chrome.storage.local.get('inpostly_username');
        try {
            const response = await fetch('http://localhost:500/upgrade-session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tier: selectedPlan, user_id: inpostly_username })
            });
            const data = await response.json();
            if (data.success) {
                await chrome.storage.local.set({ inpostly_plan: selectedPlan });
                window.location.href = 'popup.html';
            } else {
                planError.textContent = data.message || 'Plan selection failed.';
                planError.style.display = 'block';
            }
        } catch (err) {
            planError.textContent = 'Could not connect to backend.';
            planError.style.display = 'block';
        }
    });
});
