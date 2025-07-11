// Talent Match 主要JavaScript功能
document.addEventListener('DOMContentLoaded', function() {
    console.log('Talent Match 应用已加载成功！');
    
    // 初始化Bootstrap tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // 初始化所有模态框
    var modalElements = document.querySelectorAll('.modal');
    modalElements.forEach(function(modalEl) {
        var modal = new bootstrap.Modal(modalEl);
        
        // 当模态框关闭时清空表单
        modalEl.addEventListener('hidden.bs.modal', function () {
            var forms = modalEl.querySelectorAll('form');
            forms.forEach(function(form) {
                form.reset();
            });
        });
    });

    // 为所有删除按钮添加确认提示
    var deleteButtons = document.querySelectorAll('[onclick*="delete"]');
    deleteButtons.forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            if (!confirm('确定要删除吗？此操作不可恢复。')) {
                e.preventDefault();
                e.stopPropagation();
                return false;
            }
        });
    });
});

// 通用工具函数
function showAlert(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
        
        // 自动消失
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
}

// Toast Notification System
function showToast(message, type = 'info', duration = 2000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toastId = 'toast-' + Date.now();
    const toast = document.createElement('div');
    toast.id = toastId;
    toast.className = `toast align-items-center text-white bg-${type} border-0 fade-in`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');

    let icon = '';
    if (type === 'success') icon = '<i class="bi bi-check-circle-fill me-2"></i>';
    if (type === 'danger') icon = '<i class="bi bi-x-octagon-fill me-2"></i>';
    if (type === 'warning') icon = '<i class="bi bi-exclamation-triangle-fill me-2"></i>';
    if (type === 'info') icon = '<i class="bi bi-info-circle-fill me-2"></i>';
    if (type === 'primary') icon = '<i class="bi bi-gear-wide-connected me-2"></i>';


    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${icon}
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;

    container.appendChild(toast);

    const bootstrapToast = new bootstrap.Toast(toast, {
        autohide: false // We will handle hiding manually
    });
    bootstrapToast.show();

    if (duration > 0) {
      setTimeout(() => {
          toast.classList.remove('fade-in');
          toast.classList.add('fade-out');
          toast.addEventListener('animationend', () => {
              bootstrapToast.hide();
              toast.remove();
          }, { once: true });
      }, duration);
    }
    
    return bootstrapToast;
}

// 显示加载状态
function showLoading(button, loadingText = '处理中...') {
    const originalText = button.innerHTML;
    button.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i>${loadingText}`;
    button.disabled = true;
    
    return function() {
        button.innerHTML = originalText;
        button.disabled = false;
    };
}

// 格式化日期
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// 验证表单
function validateForm(formElement) {
    const requiredFields = formElement.querySelectorAll('[required]');
    let isValid = true;
    
    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.classList.add('is-invalid');
            isValid = false;
        } else {
            field.classList.remove('is-invalid');
        }
    });
    
    return isValid;
}

// API请求封装
async function apiRequest(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        },
    };
    
    const mergedOptions = { ...defaultOptions, ...options };
    
    try {
        const response = await fetch(url, mergedOptions);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.message || '请求失败');
        }
        
        return data;
    } catch (error) {
        console.error('API请求错误:', error);
        throw error;
    }
}

// 复制到剪贴板
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showAlert('已复制到剪贴板', 'success');
    }).catch(() => {
        showAlert('复制失败', 'error');
    });
}

// 页面加载动画
window.addEventListener('load', function() {
    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        setTimeout(() => {
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
}); 