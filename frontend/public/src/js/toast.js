/**
 * Toast Manager - Toast 通知管理器
 * 
 * 提供用户友好的通知系统，替代原生 alert()
 */

class ToastManager {
    constructor() {
        this.container = null;
        this.toasts = [];
        this.maxToasts = 5;
        this.defaultDuration = 5000;
        
        // 初始化容器
        this._initContainer();
    }
    
    /**
     * 初始化 Toast 容器
     */
    _initContainer() {
        // 检查是否已存在
        this.container = document.getElementById('toast-container');
        
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'toast-container';
            this.container.className = 'toast-container';
            this.container.setAttribute('role', 'alert');
            this.container.setAttribute('aria-live', 'polite');
            document.body.appendChild(this.container);
        }
    }
    
    /**
     * 显示成功通知
     * @param {string} message - 消息内容
     * @param {Object} options - 配置选项
     */
    success(message, options = {}) {
        return this._show('success', '✅', '成功', message, options);
    }
    
    /**
     * 显示错误通知
     * @param {string} message - 消息内容
     * @param {Object} options - 配置选项
     */
    error(message, options = {}) {
        return this._show('error', '❌', '错误', message, { ...options, duration: options.duration || 8000 });
    }
    
    /**
     * 显示警告通知
     * @param {string} message - 消息内容
     * @param {Object} options - 配置选项
     */
    warning(message, options = {}) {
        return this._show('warning', '⚠️', '警告', message, options);
    }
    
    /**
     * 显示信息通知
     * @param {string} message - 消息内容
     * @param {Object} options - 配置选项
     */
    info(message, options = {}) {
        return this._show('info', 'ℹ️', '提示', message, options);
    }
    
    /**
     * 显示加载通知
     * @param {string} message - 消息内容
     * @returns {Object} 包含 update 和 close 方法
     */
    loading(message) {
        const id = this._show('info', '⏳', '处理中', message, { 
            duration: 0, 
            closable: false,
            showProgress: false 
        });
        
        return {
            update: (newMessage) => this._update(id, newMessage),
            close: () => this.close(id),
            success: (msg) => {
                this.close(id);
                return this.success(msg);
            },
            error: (msg) => {
                this.close(id);
                return this.error(msg);
            }
        };
    }
    
    /**
     * 内部方法：显示 Toast
     */
    _show(type, icon, title, message, options = {}) {
        const {
            duration = this.defaultDuration,
            closable = true,
            showProgress = duration > 0
        } = options;
        
        // 限制 Toast 数量
        if (this.toasts.length >= this.maxToasts) {
            this._remove(this.toasts[0].id);
        }
        
        // 生成 ID
        const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        
        // 创建 Toast 元素
        const toast = document.createElement('div');
        toast.id = id;
        toast.className = `toast toast--${type}`;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'assertive');
        
        toast.innerHTML = `
            <span class="toast-icon">${icon}</span>
            <div class="toast-content">
                <div class="toast-title">${title}</div>
                <div class="toast-message">${message}</div>
            </div>
            ${closable ? `<button class="toast-close" aria-label="关闭">&times;</button>` : ''}
            ${showProgress ? `<div class="toast-progress" style="width: 100%"></div>` : ''}
        `;
        
        // 添加事件监听
        if (closable) {
            const closeBtn = toast.querySelector('.toast-close');
            closeBtn.addEventListener('click', () => this.close(id));
        }
        
        // 添加到容器
        this.container.appendChild(toast);
        
        // 记录 Toast
        const toastData = { id, type, element: toast, timer: null };
        this.toasts.push(toastData);
        
        // 设置进度条动画
        if (showProgress) {
            const progressBar = toast.querySelector('.toast-progress');
            progressBar.style.transition = `width ${duration}ms linear`;
            
            // 触发动画
            requestAnimationFrame(() => {
                progressBar.style.width = '0%';
            });
        }
        
        // 设置自动关闭
        if (duration > 0) {
            toastData.timer = setTimeout(() => {
                this.close(id);
            }, duration);
        }
        
        return id;
    }
    
    /**
     * 更新 Toast 内容
     */
    _update(id, message) {
        const toastData = this.toasts.find(t => t.id === id);
        if (!toastData) return;
        
        const messageEl = toastData.element.querySelector('.toast-message');
        if (messageEl) {
            messageEl.textContent = message;
        }
    }
    
    /**
     * 关闭 Toast
     */
    close(id) {
        this._remove(id);
    }
    
    /**
     * 关闭所有 Toast
     */
    closeAll() {
        [...this.toasts].forEach(toast => {
            this._remove(toast.id);
        });
    }
    
    /**
     * 内部方法：移除 Toast
     */
    _remove(id) {
        const index = this.toasts.findIndex(t => t.id === id);
        if (index === -1) return;
        
        const toastData = this.toasts[index];
        
        // 清除定时器
        if (toastData.timer) {
            clearTimeout(toastData.timer);
        }
        
        // 添加退出动画
        toastData.element.classList.add('toast--exiting');
        
        // 动画结束后移除
        setTimeout(() => {
            if (toastData.element.parentNode) {
                toastData.element.parentNode.removeChild(toastData.element);
            }
            this.toasts.splice(index, 1);
        }, 200);
    }
}

// 创建全局实例
const toast = new ToastManager();

// 导出
export default toast;

// 便捷方法
export const showSuccess = (msg, opts) => toast.success(msg, opts);
export const showError = (msg, opts) => toast.error(msg, opts);
export const showWarning = (msg, opts) => toast.warning(msg, opts);
export const showInfo = (msg, opts) => toast.info(msg, opts);
export const showLoading = (msg) => toast.loading(msg);
