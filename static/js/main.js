document.addEventListener('DOMContentLoaded', () => {
    // --- State ---
    let currentUser = null;
    
    // --- DOM Elements ---
    const authView = document.getElementById('auth-view');
    const dashboardView = document.getElementById('dashboard-view');
    const loginForm = document.getElementById('login-form');
    const signupForm = document.getElementById('signup-form');
    const loginContainer = document.querySelector('.auth-container');
    const signupContainer = document.getElementById('signup-container');
    const switchToSignup = document.getElementById('switch-to-signup');
    const switchToLogin = document.getElementById('switch-to-login');
    const logoutBtn = document.getElementById('logout-btn');
    const roleBadge = document.getElementById('user-role-badge');
    const themeToggle = document.getElementById('theme-toggle');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');
    const sendBtn = document.getElementById('send-btn');
    const micBtn = document.getElementById('mic-btn');
    const typingIndicator = document.getElementById('typing-indicator');
    const suggestionChips = document.querySelectorAll('.suggestion-chip');

    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;

    // --- initialization ---
    checkAuth();

    // --- Theme Toggle ---
    themeToggle.addEventListener('click', () => {
        document.body.classList.toggle('light-theme');
        const icon = themeToggle.querySelector('i');
        if (document.body.classList.contains('light-theme')) {
            icon.classList.replace('ph-sun', 'ph-moon');
        } else {
            icon.classList.replace('ph-moon', 'ph-sun');
        }
    });

    // --- UI Switchers ---
    switchToSignup.addEventListener('click', (e) => {
        e.preventDefault();
        loginContainer.style.display = 'none';
        signupContainer.style.display = 'block';
    });

    switchToLogin.addEventListener('click', (e) => {
        e.preventDefault();
        signupContainer.style.display = 'none';
        loginContainer.style.display = 'block';
    });

    // --- Toast Notification ---
    function showToast(message, type = 'success') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast show ${type}`;
        
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }

    // --- Authentication ---
    function checkAuth() {
        const storedUser = localStorage.getItem('hr_user');
        if (storedUser) {
            currentUser = JSON.parse(storedUser);
            showDashboard();
        } else {
            showAuth();
        }
    }

    function showAuth() {
        authView.style.display = 'flex';
        dashboardView.style.display = 'none';
    }

    function showDashboard() {
        authView.style.display = 'none';
        dashboardView.style.display = 'flex';
        roleBadge.textContent = currentUser.role.charAt(0).toUpperCase() + currentUser.role.slice(1);
    }

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;

        try {
            const res = await fetch('/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();
            
            if (res.ok) {
                currentUser = data.user;
                localStorage.setItem('hr_user', JSON.stringify(currentUser));
                showToast('Login successful');
                showDashboard();
            } else {
                showToast(data.error || 'Login failed', 'error');
            }
        } catch (error) {
            showToast('Network error', 'error');
        }
    });

    signupForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('signup-name').value;
        const email = document.getElementById('signup-email').value;
        const password = document.getElementById('signup-password').value;
        const role = document.getElementById('signup-role').value;

        try {
            const res = await fetch('/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, email, password, role })
            });
            const data = await res.json();
            
            if (res.ok) {
                showToast('Account created successfully! Please sign in.');
                switchToLogin.click();
            } else {
                showToast(data.error || 'Signup failed', 'error');
            }
        } catch (error) {
            showToast('Network error', 'error');
        }
    });

    logoutBtn.addEventListener('click', async () => {
        try {
            await fetch('/logout', { method: 'POST' });
        } catch (e) {
            // Ignore if request fails, still clean up frontend state
        }
        currentUser = null;
        localStorage.removeItem('hr_user');
        chatMessages.innerHTML = `
            <div class="message system">
                <div class="message-content">
                    <p>Welcome! I'm your AI HR Assistant.</p>
                    <div class="suggestions">
                        <button class="suggestion-chip">What is my leave balance?</button>
                        <button class="suggestion-chip">I want to apply for sick leave</button>
                        <button class="suggestion-chip">Show company holidays</button>
                    </div>
                </div>
            </div>
        `;
        rebindChips();
        showAuth();
        showToast('Logged out successfully');
    });

    // --- Chat System ---
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function appendMessage(role, content, tools = null) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        
        let html = `<div class="message-content">`;
        
        // Format newlines as <br>
        const formattedContent = content ? content.replace(/\n/g, '<br>') : '';
        html += `<p>${formattedContent}</p>`;
        
        // Render tool calls if exist
        if (tools && tools.length > 0) {
            html += `<div class="tool-calls-container">`;
            tools.forEach(tool => {
                html += `
                    <div class="tool-call">
                        <i class="ph ph-wrench"></i> 
                        Executed: <strong>${tool.tool}</strong>
                    </div>
                `;
            });
            html += `</div>`;
        }
        
        html += `</div>`;
        msgDiv.innerHTML = html;
        chatMessages.appendChild(msgDiv);
        scrollToBottom();
    }

    function setTyping(isTyping) {
        typingIndicator.style.display = isTyping ? 'flex' : 'none';
        sendBtn.disabled = isTyping;
        chatInput.disabled = isTyping;
        if (!isTyping) {
            chatInput.focus();
        }
        scrollToBottom();
    }

    async function sendMessage(query) {
        if (!query.trim() || !currentUser) return;
        
        appendMessage('user', query);
        chatInput.value = '';
        setTyping(true);

        try {
            const res = await fetch('/agent/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: query,
                    user_id: currentUser.id,
                    role: currentUser.role
                })
            });
            const data = await res.json();
            
            if (res.ok) {
                appendMessage(
                    'agent', 
                    data.response || "No response text.", 
                    data.tool_calls_made
                );
            } else {
                appendMessage('system', `Error: ${data.error || 'Failed to process request'}`);
            }
        } catch (error) {
            appendMessage('system', 'Network error. Could not reach the agent.');
        } finally {
            setTyping(false);
        }
    }

    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        sendMessage(chatInput.value);
    });

    // --- Voice Support ---
    micBtn.addEventListener('click', () => {
        if (!isRecording) {
            startRecording();
        } else {
            stopRecording();
        }
    });

    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];

            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };

            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                await sendVoiceMessage(audioBlob);
                
                // Stop all tracks to release the microphone
                stream.getTracks().forEach(track => track.stop());
            };

            mediaRecorder.start();
            isRecording = true;
            micBtn.classList.add('recording');
            micBtn.querySelector('i').className = 'ph ph-stop-circle';
            chatInput.placeholder = 'Listening... Click stop to send';
        } catch (err) {
            console.error('Microphone access denied:', err);
            showToast('Microphone access denied or not available', 'error');
        }
    }

    function stopRecording() {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            isRecording = false;
            micBtn.classList.remove('recording');
            micBtn.querySelector('i').className = 'ph ph-microphone';
            chatInput.placeholder = 'Ask me anything...';
        }
    }

    async function sendVoiceMessage(audioBlob) {
        if (!currentUser) return;

        setTyping(true);

        const formData = new FormData();
        formData.append('audio', audioBlob, 'voice_query.webm');
        formData.append('user_id', currentUser.id);
        formData.append('role', currentUser.role);

        try {
            const res = await fetch('/agent/voice-chat', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            if (res.ok) {
                // Show what the user said (translated to English by the backend)
                if (data.transcribed_query) {
                    appendMessage('user', `🎤 ${data.transcribed_query}`);
                }
                
                appendMessage(
                    'agent',
                    data.response || "No response text.",
                    data.tool_calls_made
                );
            } else {
                appendMessage('system', `Error: ${data.error || 'Failed to process voice request'}`);
            }
        } catch (error) {
            console.error('Voice message error:', error);
            appendMessage('system', 'Network error. Could not reach the agent for voice message.');
        } finally {
            setTyping(false);
        }
    }

    function rebindChips() {
        document.querySelectorAll('.suggestion-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                sendMessage(chip.textContent);
            });
        });
    }

    rebindChips();
});
