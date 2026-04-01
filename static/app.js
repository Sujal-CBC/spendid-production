/**
 * SPENDiD - Financial Chatbot Application
 * Modern UI with enhanced UX and real-time updates
 */

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const chatMessages = document.getElementById('chat-messages');
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const sessionDisplay = document.getElementById('session-display');
    const progressBar = document.querySelector('.progress-bar-fill');
    const progressPercentage = document.querySelector('.progress-percentage');
    const categoryList = document.getElementById('category-list');
    const budgetCard = document.getElementById('budget-data');
    const noDataHint = document.getElementById('no-data-hint');
    const savingsVal = document.getElementById('savings-val');
    const clearBtn = document.getElementById('clear-session');

    // Session Management
    let sessionId = localStorage.getItem('spendid_session_id') || null;
    let isProcessing = false;

    // Initialize
    initializeApp();

    function initializeApp() {
        if (sessionId) {
            sessionDisplay.textContent = sessionId.substring(0, 8);
            fetchState();
        }
        
        setupEventListeners();
        setupQuickActions();
        setupHintChips();
    }

    function setupEventListeners() {
        // Form submission
        chatForm.addEventListener('submit', handleSubmit);
        
        // Input enter key
        userInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
            }
        });

        // Clear session
        clearBtn.addEventListener('click', handleClearSession);

        // Navigation items
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
            });
        });
    }

    function setupQuickActions() {
        document.querySelectorAll('.quick-action-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const message = btn.dataset.message;
                if (message) {
                    userInput.value = message;
                    handleSubmit(new Event('submit'));
                }
            });
        });
    }

    function setupHintChips() {
        document.querySelectorAll('.hint-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const message = chip.dataset.message;
                if (message) {
                    userInput.value = message;
                    userInput.focus();
                }
            });
        });
    }

    async function handleSubmit(e) {
        e.preventDefault();
        
        if (isProcessing) return;
        
        const message = userInput.value.trim();
        if (!message) return;

        isProcessing = true;
        
        // Remove welcome message if exists
        const welcomeMsg = document.querySelector('.welcome-message');
        if (welcomeMsg) {
            welcomeMsg.style.opacity = '0';
            welcomeMsg.style.transform = 'translateY(-20px)';
            setTimeout(() => welcomeMsg.remove(), 300);
        }

        // Add user message
        addMessage(message, 'user');
        userInput.value = '';
        
        // Show typing indicator
        showTypingIndicator();

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message, session_id: sessionId })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            await handleStreamResponse(response);
            
        } catch (error) {
            console.error('Error:', error);
            hideTypingIndicator();
            addMessage('Sorry, I encountered an error. Please try again.', 'ai', true);
        } finally {
            isProcessing = false;
        }
    }

    async function handleStreamResponse(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let aiMessageDiv = null;
        let aiContentDiv = null;

        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');
                
                for (const line of lines) {
                    if (!line.trim()) continue;
                    
                    try {
                        const data = JSON.parse(line);
                        
                        if (data.type === 'chunk') {
                            hideTypingIndicator();
                            
                            if (!aiMessageDiv) {
                                aiMessageDiv = createAIMessageContainer();
                                aiContentDiv = aiMessageDiv.querySelector('.message-content');
                            }
                            
                            // Typewriter effect for chunks
                            await typeText(aiContentDiv, data.content);
                            
                        } else if (data.type === 'done') {
                            if (data.session_id) {
                                sessionId = data.session_id;
                                localStorage.setItem('spendid_session_id', sessionId);
                                sessionDisplay.textContent = sessionId.substring(0, 8);
                            }
                            if (data.state) {
                                updateUI(data.state);
                            }
                        }
                    } catch (e) {
                        console.error('Error parsing stream line:', e, line);
                    }
                }
            }
        } finally {
            reader.releaseLock();
        }
    }

    function createAIMessageContainer() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message ai';
        messageDiv.innerHTML = `
            <div class="message-avatar"><i class="fas fa-robot"></i></div>
            <div class="message-content"></div>
        `;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return messageDiv;
    }

    async function typeText(element, text) {
        // Accumulate text and parse markdown for bold
        let accumulatedText = element.dataset.rawText || '';
        accumulatedText += text;
        element.dataset.rawText = accumulatedText;
        
        // Convert markdown bold (**text**) to HTML <strong>
        const formattedText = parseMarkdownBold(escapeHtml(accumulatedText));
        element.innerHTML = formattedText;
        
        chatMessages.scrollTop = chatMessages.scrollHeight;
        await new Promise(r => setTimeout(r, 5 + Math.random() * 10));
    }

    function addMessage(text, type, isError = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        
        // Parse markdown bold for static messages
        const formattedText = parseMarkdownBold(escapeHtml(text));
        
        if (type === 'ai') {
            messageDiv.innerHTML = `
                <div class="message-avatar"><i class="fas fa-robot"></i></div>
                <div class="message-content" ${isError ? 'style="color: var(--accent-rose);"' : ''}>${formattedText}</div>
            `;
        } else {
            messageDiv.innerHTML = `
                <div class="message-avatar"><i class="fas fa-user"></i></div>
                <div class="message-content">${formattedText}</div>
            `;
        }
        
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function parseMarkdownBold(text) {
        // Convert **text** to <strong>text</strong>
        // Use a regex that handles nested content properly
        return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    }

    function showTypingIndicator() {
        const existing = document.getElementById('typing-indicator');
        if (existing) existing.remove();

        const indicator = document.createElement('div');
        indicator.id = 'typing-indicator';
        indicator.className = 'message ai';
        indicator.innerHTML = `
            <div class="message-avatar"><i class="fas fa-robot"></i></div>
            <div class="message-content">
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
        chatMessages.appendChild(indicator);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function hideTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.style.opacity = '0';
            setTimeout(() => indicator.remove(), 200);
        }
    }

    function handleClearSession() {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-icon"><i class="fas fa-exclamation-triangle"></i></div>
                <h3>Reset Session?</h3>
                <p>This will clear your current profile and chat history. This action cannot be undone.</p>
                <div class="modal-actions">
                    <button class="modal-btn secondary" id="cancel-reset">Cancel</button>
                    <button class="modal-btn danger" id="confirm-reset">Reset</button>
                </div>
            </div>
        `;
        
        // Add modal styles
        const style = document.createElement('style');
        style.textContent = `
            .modal-overlay {
                position: fixed;
                inset: 0;
                background: rgba(0,0,0,0.7);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 1000;
                animation: fadeIn 0.2s ease;
            }
            .modal-content {
                background: var(--bg-card);
                border: 1px solid var(--glass-border);
                border-radius: var(--radius-lg);
                padding: var(--space-xl);
                text-align: center;
                max-width: 360px;
                animation: scaleIn 0.2s ease;
            }
            .modal-icon {
                width: 56px;
                height: 56px;
                background: rgba(244, 63, 94, 0.1);
                border-radius: var(--radius-full);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.5rem;
                color: var(--accent-rose);
                margin: 0 auto var(--space-md);
            }
            .modal-content h3 {
                font-size: 1.25rem;
                font-weight: 700;
                margin-bottom: var(--space-sm);
            }
            .modal-content p {
                color: var(--text-secondary);
                font-size: 0.9375rem;
                margin-bottom: var(--space-lg);
            }
            .modal-actions {
                display: flex;
                gap: var(--space-md);
            }
            .modal-btn {
                flex: 1;
                padding: var(--space-md);
                border-radius: var(--radius-md);
                border: none;
                font-size: 0.9375rem;
                font-weight: 600;
                cursor: pointer;
                transition: all var(--transition-fast);
                font-family: inherit;
            }
            .modal-btn.secondary {
                background: var(--glass-bg);
                color: var(--text-secondary);
                border: 1px solid var(--glass-border);
            }
            .modal-btn.secondary:hover {
                background: var(--glass-highlight);
                color: var(--text-primary);
            }
            .modal-btn.danger {
                background: var(--accent-rose);
                color: white;
            }
            .modal-btn.danger:hover {
                background: #e11d48;
                transform: translateY(-1px);
            }
            @keyframes scaleIn {
                from { transform: scale(0.9); opacity: 0; }
                to { transform: scale(1); opacity: 1; }
            }
        `;
        document.head.appendChild(style);
        document.body.appendChild(modal);

        modal.querySelector('#cancel-reset').addEventListener('click', () => {
            modal.remove();
            style.remove();
        });

        modal.querySelector('#confirm-reset').addEventListener('click', () => {
            localStorage.removeItem('spendid_session_id');
            window.location.reload();
        });

        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
                style.remove();
            }
        });
    }

    async function fetchState() {
        try {
            const response = await fetch(`/state/${sessionId}`);
            if (!response.ok) throw new Error('Failed to fetch state');
            const state = await response.json();
            updateUI(state);
        } catch (error) {
            console.error('Error fetching state:', error);
        }
    }

    function updateUI(state) {
        // Update Progress
        const fields = ['zipcode', 'age', 'number_of_people', 'has_house', 'salary', 'is_net_salary', 'past_credit_debt', 'student_loan', 'other_debt'];
        const filled = fields.filter(f => state[f] !== null && state[f] !== undefined && state[f] !== '').length;
        const progress = Math.round((filled / fields.length) * 100);
        
        progressBar.style.width = `${progress}%`;
        if (progressPercentage) {
            progressPercentage.textContent = `${progress}%`;
        }

        // Update Profile List with animation
        document.querySelectorAll('#profile-details li').forEach(li => {
            const field = li.dataset.field;
            const valSpan = li.querySelector('.val');
            const oldValue = valSpan.textContent;
            let newValue = '---';
            
            if (state[field] !== null && state[field] !== undefined && state[field] !== '') {
                if (field === 'salary') {
                    newValue = `$${Number(state[field]).toLocaleString()}`;
                } else if (field === 'has_house') {
                    newValue = state[field] ? 'Homeowner' : 'Renter';
                } else if (field === 'past_credit_debt') {
                    newValue = state[field] ? `$${Number(state[field]).toLocaleString()}` : 'None';
                } else {
                    newValue = state[field];
                }
            }
            
            if (oldValue !== newValue && newValue !== '---') {
                valSpan.style.color = 'var(--accent-emerald)';
                setTimeout(() => {
                    valSpan.style.color = '';
                }, 1000);
            }
            
            valSpan.textContent = newValue;
        });

        // Update Budget Highlights - Use budget_data (user's updated budget)
        const budgetSource = state.api_results?.budget_data || state.api_results;
        if (budgetSource && budgetSource.transformed) {
            noDataHint.classList.add('hidden');
            budgetCard.classList.remove('hidden');
            
            const transformed = budgetSource.transformed;
            const topCategories = [
                { key: 'Rent or Mortgage Payment', icon: 'fa-house' },
                { key: 'Groceries', icon: 'fa-basket-shopping' },
                { key: 'Dining Out', icon: 'fa-utensils' },
                { key: 'Car Payments', icon: 'fa-car' },
                { key: 'Education', icon: 'fa-graduation-cap' }
            ];
            
            // Get existing items
            const existingItems = {};
            categoryList.querySelectorAll('.category-item').forEach(item => {
                const key = item.dataset.categoryKey;
                if (key) existingItems[key] = item;
            });
            
            topCategories.forEach((cat, index) => {
                if (transformed[cat.key] !== undefined) {
                    const newValue = `$${Number(transformed[cat.key]).toLocaleString()}`;
                    
                    if (existingItems[cat.key]) {
                        // Update existing item
                        const item = existingItems[cat.key];
                        const valueEl = item.querySelector('strong');
                        const oldValue = valueEl.textContent;
                        
                        if (oldValue !== newValue) {
                            // Highlight the change
                            valueEl.style.color = 'var(--accent-emerald)';
                            valueEl.textContent = newValue;
                            setTimeout(() => {
                                valueEl.style.color = '';
                            }, 1000);
                        }
                    } else {
                        // Create new item with animation
                        const item = document.createElement('div');
                        item.className = 'category-item fade-in';
                        item.dataset.categoryKey = cat.key;
                        item.innerHTML = `
                            <span><i class="fas ${cat.icon}" style="margin-right: 8px; color: var(--text-tertiary);"></i>${cat.key}</span>
                            <strong>${newValue}</strong>
                        `;
                        categoryList.appendChild(item);
                    }
                }
            });

            // Get savings from the correct budget source
            const budgetPayload = budgetSource.budget || {};
            if (budgetPayload.savings !== undefined) {
                const savings = budgetPayload.savings;
                const currentSavings = parseInt(savingsVal.textContent.replace(/[$,]/g, '')) || 0;
                if (currentSavings !== savings) {
                    animateValue(savingsVal, currentSavings, savings, 1000, true);
                }
            }
        }
    }

    function animateValue(element, start, end, duration, isCurrency = false) {
        const startTime = performance.now();
        
        function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            // Easing function
            const easeOutQuart = 1 - Math.pow(1 - progress, 4);
            const current = start + (end - start) * easeOutQuart;
            
            if (isCurrency) {
                element.textContent = `$${Math.round(current).toLocaleString()}`;
            } else {
                element.textContent = Math.round(current);
            }
            
            if (progress < 1) {
                requestAnimationFrame(update);
            }
        }
        
        requestAnimationFrame(update);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});
