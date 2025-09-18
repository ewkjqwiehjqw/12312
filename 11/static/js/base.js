// Base JavaScript utilities and security functions

// CSRF and XSS Protection
function sanitizeInput(input) {
    if (typeof input !== 'string') return input;
    
    const div = document.createElement('div');
    div.textContent = input;
    return div.innerHTML;
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// Loading screen management
function showLoading(message = 'Loading...') {
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {
        const messageElement = loadingScreen.querySelector('h3');
        if (messageElement) messageElement.textContent = message;
        loadingScreen.style.display = 'flex';
    }
}

function hideLoading() {
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {
        loadingScreen.style.display = 'none';
    }
}

// API utilities with security headers
const apiClient = {
    baseURL: window.location.origin,
    
    async request(method, url, data = null, options = {}) {
        const config = {
            method: method.toUpperCase(),
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                ...options.headers
            },
            credentials: 'include',
            ...options
        };
        
        // Add auth token if available
        const token = localStorage.getItem('authToken');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        
        // Add body for POST/PUT requests
        if (data && ['POST', 'PUT', 'PATCH'].includes(config.method)) {
            config.body = JSON.stringify(data);
        }
        
        try {
            const response = await fetch(`${this.baseURL}${url}`, config);
            
            // Handle authentication errors
            if (response.status === 401) {
                await this.handleUnauthorized();
                throw new Error('Authentication required');
            }
            
            // Handle rate limiting
            if (response.status === 429) {
                throw new Error('Too many requests. Please try again later.');
            }
            
            const responseData = await response.json();
            
            if (!response.ok) {
                throw new Error(responseData.detail || 'Request failed');
            }
            
            return responseData;
        } catch (error) {
            console.error('API Request Error:', error);
            throw error;
        }
    },
    
    async handleUnauthorized() {
        // Try to refresh token
        const refreshToken = localStorage.getItem('refreshToken');
        if (refreshToken) {
            try {
                const response = await fetch(`${this.baseURL}/auth/refresh`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ refresh_token: refreshToken })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    localStorage.setItem('authToken', data.access_token);
                    localStorage.setItem('refreshToken', data.refresh_token);
                    return true;
                }
            } catch (error) {
                console.log('Token refresh failed:', error);
            }
        }
        
        // Clear tokens and redirect to login
        localStorage.removeItem('authToken');
        localStorage.removeItem('refreshToken');
        
        const currentPath = window.location.pathname;
        if (currentPath !== '/auth/login' && currentPath !== '/auth/register') {
            window.location.href = `/auth/login?redirect=${encodeURIComponent(currentPath)}`;
        }
        
        return false;
    },
    
    get(url, options = {}) {
        return this.request('GET', url, null, options);
    },
    
    post(url, data, options = {}) {
        return this.request('POST', url, data, options);
    },
    
    put(url, data, options = {}) {
        return this.request('PUT', url, data, options);
    },
    
    delete(url, options = {}) {
        return this.request('DELETE', url, null, options);
    }
};

// Form validation utilities
const formValidator = {
    email(email) {
        const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return regex.test(email);
    },
    
    password(password) {
        if (password.length < 8) return false;
        if (!/[A-Z]/.test(password)) return false;
        if (!/[a-z]/.test(password)) return false;
        if (!/\d/.test(password)) return false;
        if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) return false;
        return true;
    },
    
    username(username) {
        if (username.length < 3 || username.length > 50) return false;
        return /^[a-zA-Z0-9]+$/.test(username);
    },
    
    required(value) {
        return value && value.toString().trim().length > 0;
    },
    
    minLength(value, min) {
        return value && value.toString().length >= min;
    },
    
    maxLength(value, max) {
        return value && value.toString().length <= max;
    }
};

// Toast notifications
function showToast(message, type = 'info', duration = 5000) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <div class="toast-content">
            <span class="toast-message">${escapeHtml(message)}</span>
            <button class="toast-close" onclick="this.parentElement.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;
    
    // Add toast styles if not already present
    if (!document.getElementById('toast-styles')) {
        const style = document.createElement('style');
        style.id = 'toast-styles';
        style.textContent = `
            .toast {
                position: fixed;
                top: 20px;
                right: 20px;
                min-width: 300px;
                max-width: 500px;
                padding: 1rem;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                z-index: 10000;
                animation: slideInRight 0.3s ease;
            }
            
            .toast-info { background: #e3f2fd; color: #1565c0; border-left: 4px solid #2196f3; }
            .toast-success { background: #e8f5e8; color: #2e7d32; border-left: 4px solid #4caf50; }
            .toast-warning { background: #fff3e0; color: #ef6c00; border-left: 4px solid #ff9800; }
            .toast-error { background: #ffebee; color: #c62828; border-left: 4px solid #f44336; }
            
            .toast-content { display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
            .toast-close { background: none; border: none; cursor: pointer; opacity: 0.7; }
            .toast-close:hover { opacity: 1; }
            
            @keyframes slideInRight {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
        `;
        document.head.appendChild(style);
    }
    
    document.body.appendChild(toast);
    
    // Auto remove after duration
    if (duration > 0) {
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, duration);
    }
}

// Security monitoring
function monitorSecurity() {
    // Monitor for XSS attempts in innerHTML
    const originalInnerHTML = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML') || 
                              Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'innerHTML');
    
    if (originalInnerHTML && originalInnerHTML.set) {
        Object.defineProperty(Element.prototype, 'innerHTML', {
            set: function(value) {
                if (typeof value === 'string' && /<script|javascript:|on\w+=/i.test(value)) {
                    console.warn('Potential XSS attempt blocked');
                    return;
                }
                originalInnerHTML.set.call(this, value);
            },
            get: originalInnerHTML.get,
            configurable: true
        });
    }
    
    // Monitor for suspicious form submissions
    document.addEventListener('submit', function(e) {
        const form = e.target;
        const formData = new FormData(form);
        
        for (let [key, value] of formData.entries()) {
            if (typeof value === 'string' && /<script|javascript:|on\w+=/i.test(value)) {
                console.warn('Suspicious form data detected');
                e.preventDefault();
                showToast('Invalid input detected. Please check your data.', 'error');
                return;
            }
        }
    });
}

// Initialize security monitoring and common features
document.addEventListener('DOMContentLoaded', function() {
    // monitorSecurity(); // disabled to avoid blocking legitimate HTML
    
    // Hide loading screen after page load
    setTimeout(hideLoading, 500);
    
    // Add click handlers for mobile menu
    const mobileToggle = document.querySelector('.mobile-toggle');
    const navMenu = document.querySelector('.nav-menu');
    
    if (mobileToggle && navMenu) {
        mobileToggle.addEventListener('click', function() {
            navMenu.classList.toggle('active');
            mobileToggle.classList.toggle('active');
        });
    }
});

// Export utilities for use in other scripts
window.utils = {
    sanitizeInput,
    escapeHtml,
    showLoading,
    hideLoading,
    apiClient,
    formValidator,
    showToast
}; 