// 主要 JavaScript 功能

// 通用的 AJAX 請求函數
async function makeRequest(url, method = 'GET', data = null) {
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json',
        }
    };
    
    if (data) {
        options.body = JSON.stringify(data);
    }
    
    try {
        const response = await fetch(url, options);
        return {
            ok: response.ok,
            status: response.status,
            data: await response.json()
        };
    } catch (error) {
        return {
            ok: false,
            error: error.message
        };
    }
}

// 顯示提示訊息
function showMessage(message, type = 'info', duration = 3000) {
    // 移除現有的訊息
    const existingMessage = document.querySelector('.floating-message');
    if (existingMessage) {
        existingMessage.remove();
    }
    
    // 建立新訊息元素
    const messageEl = document.createElement('div');
    messageEl.className = `floating-message floating-message-${type}`;
    messageEl.textContent = message;
    messageEl.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 6px;
        color: white;
        font-weight: bold;
        z-index: 9999;
        animation: slideIn 0.3s ease-out;
        max-width: 400px;
        word-wrap: break-word;
    `;
    
    // 設定背景顏色
    switch (type) {
        case 'success':
            messageEl.style.background = '#27ae60';
            break;
        case 'error':
            messageEl.style.background = '#e74c3c';
            break;
        case 'warning':
            messageEl.style.background = '#f39c12';
            break;
        default:
            messageEl.style.background = '#3498db';
    }
    
    document.body.appendChild(messageEl);
    
    // 自動移除
    setTimeout(() => {
        if (messageEl.parentNode) {
            messageEl.style.animation = 'slideOut 0.3s ease-in';
            setTimeout(() => {
                if (messageEl.parentNode) {
                    messageEl.remove();
                }
            }, 300);
        }
    }, duration);
}

// 添加滑入滑出動畫的 CSS
const animationStyles = document.createElement('style');
animationStyles.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(animationStyles);

// 表單驗證函數
function validateForm(formId, rules) {
    const form = document.getElementById(formId);
    if (!form) return false;
    
    let isValid = true;
    
    for (const fieldName in rules) {
        const field = form.querySelector(`[name="${fieldName}"]`);
        if (!field) continue;
        
        const rule = rules[fieldName];
        const value = field.value.trim();
        
        // 移除之前的錯誤樣式
        field.classList.remove('error');
        
        // 必填驗證
        if (rule.required && !value) {
            showFieldError(field, rule.requiredMessage || `${fieldName} 為必填欄位`);
            isValid = false;
            continue;
        }
        
        // 最小長度驗證
        if (rule.minLength && value.length < rule.minLength) {
            showFieldError(field, rule.minLengthMessage || `${fieldName} 至少需要 ${rule.minLength} 個字符`);
            isValid = false;
            continue;
        }
        
        // 電子郵件驗證
        if (rule.email && value && !isValidEmail(value)) {
            showFieldError(field, rule.emailMessage || '請輸入有效的電子郵件地址');
            isValid = false;
            continue;
        }
        
        // 自定義驗證
        if (rule.validator && !rule.validator(value)) {
            showFieldError(field, rule.validatorMessage || '輸入格式不正確');
            isValid = false;
            continue;
        }
    }
    
    return isValid;
}

function showFieldError(field, message) {
    field.classList.add('error');
    
    // 移除現有錯誤訊息
    const existingError = field.parentNode.querySelector('.field-error');
    if (existingError) {
        existingError.remove();
    }
    
    // 添加新錯誤訊息
    const errorEl = document.createElement('div');
    errorEl.className = 'field-error';
    errorEl.textContent = message;
    errorEl.style.cssText = `
        color: #e74c3c;
        font-size: 0.9rem;
        margin-top: 4px;
    `;
    
    field.parentNode.appendChild(errorEl);
}

function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

// 載入狀態管理
function setButtonLoading(button, loading = true) {
    if (loading) {
        button.dataset.originalText = button.textContent;
        button.innerHTML = '<span class="loading"></span> 處理中...';
        button.disabled = true;
    } else {
        button.textContent = button.dataset.originalText || button.textContent;
        button.disabled = false;
    }
}

// 確認對話框
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// 格式化日期
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-TW', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

// 防抖函數（避免重複快速點擊）
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 節流函數
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    }
}

// 複製文本到剪貼簿
async function copyToClipboard(text) {
    try {
        if (navigator.clipboard) {
            await navigator.clipboard.writeText(text);
            return true;
        } else {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            
            try {
                document.execCommand('copy');
                return true;
            } catch (err) {
                return false;
            } finally {
                document.body.removeChild(textArea);
            }
        }
    } catch (err) {
        return false;
    }
}

// 頁面載入完成時的初始化
document.addEventListener('DOMContentLoaded', function() {
    // 為所有按鈕添加點擊效果
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(button => {
        button.addEventListener('click', function() {
            this.style.transform = 'scale(0.98)';
            setTimeout(() => {
                this.style.transform = '';
            }, 100);
        });
    });
    
    // 為表單輸入添加焦點效果
    const inputs = document.querySelectorAll('input, textarea, select');
    inputs.forEach(input => {
        input.addEventListener('focus', function() {
            this.parentNode.classList.add('focused');
        });
        
        input.addEventListener('blur', function() {
            this.parentNode.classList.remove('focused');
            // 移除錯誤樣式和訊息
            this.classList.remove('error');
            const errorEl = this.parentNode.querySelector('.field-error');
            if (errorEl) {
                errorEl.remove();
            }
        });
    });
});

// 導出到全域
window.QuizApp = {
    makeRequest,
    showMessage,
    validateForm,
    setButtonLoading,
    confirmAction,
    formatDate,
    debounce,
    throttle,
    copyToClipboard
};
