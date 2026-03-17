// API base URL - use relative path to work from any host
const API_URL = '/api';

// Global state
let currentSessionId = null;

// DOM elements
let chatMessages, chatInput, sendButton, totalCourses, courseTitles, newChatButton, themeToggle, pastChatsListEl;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Get DOM elements after page loads
    chatMessages = document.getElementById('chatMessages');
    chatInput = document.getElementById('chatInput');
    sendButton = document.getElementById('sendButton');
    totalCourses = document.getElementById('totalCourses');
    courseTitles = document.getElementById('courseTitles');
    newChatButton = document.getElementById('newChatButton');
    themeToggle = document.getElementById('themeToggle');
    pastChatsListEl = document.getElementById('pastChatsList');

    setupEventListeners();
    initializeTheme();
    createNewSession();
    loadCourseStats();
    loadPastChats();
});

// Event Listeners
function setupEventListeners() {
    // Chat functionality
    sendButton.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
    
    // New chat button
    newChatButton.addEventListener('click', startNewChat);
    
    // Theme toggle
    themeToggle.addEventListener('click', toggleTheme);
    
    // Keyboard shortcut for theme toggle (Ctrl/Cmd + Shift + T)
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'T') {
            e.preventDefault();
            toggleTheme();
        }
    });
    
    // Suggested questions
    document.querySelectorAll('.suggested-item').forEach(button => {
        button.addEventListener('click', (e) => {
            const question = e.target.getAttribute('data-question');
            chatInput.value = question;
            sendMessage();
        });
    });
}


// Chat Functions
async function sendMessage() {
    const query = chatInput.value.trim();
    if (!query) return;

    // Disable input
    chatInput.value = '';
    chatInput.disabled = true;
    sendButton.disabled = true;

    // Add user message
    addMessage(query, 'user');

    // Add loading message - create a unique container for it
    const loadingMessage = createLoadingMessage();
    chatMessages.appendChild(loadingMessage);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        const response = await fetch(`${API_URL}/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query,
                session_id: currentSessionId
            })
        });

        if (!response.ok) throw new Error('Query failed');

        const data = await response.json();
        
        // Update session ID if new
        if (!currentSessionId) {
            currentSessionId = data.session_id;
        }

        // Replace loading message with response
        loadingMessage.remove();
        addMessage(data.answer, 'assistant', data.sources, data.source_links);
        loadPastChats();

    } catch (error) {
        // Replace loading message with error
        loadingMessage.remove();
        addMessage(`Error: ${error.message}`, 'assistant');
    } finally {
        chatInput.disabled = false;
        sendButton.disabled = false;
        chatInput.focus();
    }
}

function createLoadingMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.innerHTML = `
        <div class="message-content">
            <div class="loading">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    return messageDiv;
}

function addMessage(content, type, sources = null, sourceLinks = null, isWelcome = false) {
    const messageId = Date.now();
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}${isWelcome ? ' welcome-message' : ''}`;
    messageDiv.id = `message-${messageId}`;
    
    // Convert markdown to HTML for assistant messages
    const displayContent = type === 'assistant' ? marked.parse(content) : escapeHtml(content);
    
    let html = `<div class="message-content">${displayContent}</div>`;
    
    if (sources && sources.length > 0) {
        // Create sources with clickable links when available
        const sourcesHtml = sources.map((source, index) => {
            const link = sourceLinks && sourceLinks[index];
            if (link) {
                return `<a href="${link}" target="_blank" class="source-link">${source}</a>`;
            } else {
                return source;
            }
        }).join(', ');
        
        html += `
            <details class="sources-collapsible">
                <summary class="sources-header">Sources</summary>
                <div class="sources-content">${sourcesHtml}</div>
            </details>
        `;
    }
    
    messageDiv.innerHTML = html;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    return messageId;
}

// Helper function to escape HTML for user messages
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Removed removeMessage function - no longer needed since we handle loading differently

async function startNewChat() {
    // Keep the old session in the past chats list — just start a fresh UI session
    await createNewSession();
    loadPastChats();
}

async function createNewSession() {
    currentSessionId = null;
    chatMessages.innerHTML = '';
    chatInput.value = '';
    chatInput.disabled = false;
    sendButton.disabled = false;
    addMessage('Welcome to the Course Materials Assistant! I can help you with questions about courses, lessons and specific content. What would you like to know?', 'assistant', null, null, true);
}

// Load course statistics
async function loadCourseStats() {
    try {
        console.log('Loading course stats...');
        const response = await fetch(`${API_URL}/courses`);
        if (!response.ok) throw new Error('Failed to load course stats');
        
        const data = await response.json();
        console.log('Course data received:', data);
        
        // Update stats in UI
        if (totalCourses) {
            totalCourses.textContent = data.total_courses;
        }
        
        // Update course titles
        if (courseTitles) {
            if (data.course_titles && data.course_titles.length > 0) {
                courseTitles.innerHTML = data.course_titles
                    .map(title => `<div class="course-title-item">${title}</div>`)
                    .join('');
            } else {
                courseTitles.innerHTML = '<span class="no-courses">No courses available</span>';
            }
        }
        
    } catch (error) {
        console.error('Error loading course stats:', error);
        // Set default values on error
        if (totalCourses) {
            totalCourses.textContent = '0';
        }
        if (courseTitles) {
            courseTitles.innerHTML = '<span class="error">Failed to load courses</span>';
        }
    }
}

// Past Chats Functions

async function loadPastChats() {
    try {
        const response = await fetch(`${API_URL}/sessions`);
        if (!response.ok) throw new Error('Failed to load past chats');

        const data = await response.json();
        const sessions = data.sessions;

        if (!pastChatsListEl) return;

        if (!sessions || sessions.length === 0) {
            pastChatsListEl.innerHTML = '<span class="no-chats">No past chats yet</span>';
            return;
        }

        // Render newest first
        const sorted = [...sessions].reverse();
        pastChatsListEl.innerHTML = sorted.map(session => {
            const date = new Date(session.created_at);
            const dateStr = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            const timeStr = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
            const isActive = session.session_id === currentSessionId ? ' active' : '';
            const summaryPreview = session.summary ? escapeHtml(session.summary.slice(0, 100)) + (session.summary.length > 100 ? '…' : '') : '';
            return `
                <div class="past-chat-item${isActive}" id="chat-${session.session_id}">
                    <div class="past-chat-info" onclick="resumeSession('${session.session_id}')">
                        <span class="past-chat-title">${escapeHtml(session.title)}</span>
                        <span class="past-chat-date">${dateStr} ${timeStr}</span>
                        ${summaryPreview ? `<span class="past-chat-summary">${summaryPreview}</span>` : ''}
                    </div>
                    <button class="past-chat-delete" title="Delete chat" onclick="deleteSession('${session.session_id}')">×</button>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Error loading past chats:', error);
    }
}

function resumeSession(sessionId) {
    currentSessionId = sessionId;
    chatMessages.innerHTML = '';
    addMessage('Resuming previous chat — continue your conversation below.', 'assistant', null, null, true);
    // Highlight the active item
    document.querySelectorAll('.past-chat-item').forEach(el => el.classList.remove('active'));
    const activeEl = document.getElementById(`chat-${sessionId}`);
    if (activeEl) activeEl.classList.add('active');
    chatInput.focus();
}

async function deleteSession(sessionId) {
    try {
        await fetch(`${API_URL}/sessions/${sessionId}`, { method: 'DELETE' });
        if (currentSessionId === sessionId) {
            currentSessionId = null;
            chatMessages.innerHTML = '';
            addMessage('Welcome to the Course Materials Assistant! I can help you with questions about courses, lessons and specific content. What would you like to know?', 'assistant', null, null, true);
        }
        loadPastChats();
    } catch (error) {
        console.error('Error deleting session:', error);
    }
}

// Theme Functions
function initializeTheme() {
    // Get saved theme preference or default to dark
    const savedTheme = localStorage.getItem('theme') || 'dark';
    setTheme(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
}

function setTheme(theme) {
    if (theme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
        themeToggle.setAttribute('aria-label', 'Switch to dark theme');
    } else {
        document.documentElement.removeAttribute('data-theme');
        themeToggle.setAttribute('aria-label', 'Switch to light theme');
    }
    
    // Save theme preference
    localStorage.setItem('theme', theme);
}