/**
 * State Manager - 集中状态管理
 * 
 * 使用发布-订阅模式管理应用状态，确保状态变更可追踪、可预测。
 */

class StateManager {
    constructor() {
        // 应用状态
        this.state = {
            // 分析任务状态
            task: {
                id: null,
                status: 'idle', // idle | uploading | processing | completed | failed
                progress: 0,
                stage: '',
                error: null
            },
            
            // 文件状态
            file: {
                selected: null,
                preview: null,
                name: null,
                size: 0,
                type: ''
            },
            
            // 事件状态
            events: {
                items: [],
                stats: {
                    total: 0,
                    errors: 0,
                    warnings: 0,
                    retries: 0,
                    duration: 0
                },
                isLoading: false
            },
            
            // 报告状态
            report: {
                data: null,
                markdown: '',
                trace: null,
                isTraceVisible: false
            },
            
            // UI 状态
            ui: {
                isVerboseMode: false,
                activeView: 'upload', // upload | processing | result
                toasts: []
            }
        };
        
        // 订阅者列表
        this.subscribers = new Map();
        
        // 状态历史（用于调试）
        this.history = [];
        this.maxHistorySize = 50;
    }
    
    /**
     * 获取状态（支持路径访问）
     * @param {string} path - 状态路径，如 'task.status'
     * @returns {*}
     */
    get(path) {
        if (!path) return this.state;
        
        const keys = path.split('.');
        let value = this.state;
        
        for (const key of keys) {
            if (value === undefined || value === null) return undefined;
            value = value[key];
        }
        
        return value;
    }
    
    /**
     * 设置状态（支持路径访问）
     * @param {string} path - 状态路径
     * @param {*} value - 新值
     */
    set(path, value) {
        if (!path) return;
        
        const keys = path.split('.');
        let current = this.state;
        
        // 遍历到倒数第二层
        for (let i = 0; i < keys.length - 1; i++) {
            const key = keys[i];
            if (current[key] === undefined || current[key] === null) {
                current[key] = {};
            }
            current = current[key];
        }
        
        // 设置最后一层的值
        const lastKey = keys[keys.length - 1];
        const oldValue = current[lastKey];
        current[lastKey] = value;
        
        // 记录历史
        this._recordHistory(path, oldValue, value);
        
        // 通知订阅者
        this._notify(path, value, oldValue);
    }
    
    /**
     * 批量更新状态
     * @param {Object} updates - 状态更新对象，如 { 'task.status': 'processing', 'task.progress': 50 }
     */
    batch(updates) {
        const changes = [];
        
        for (const [path, value] of Object.entries(updates)) {
            const keys = path.split('.');
            let current = this.state;
            
            for (let i = 0; i < keys.length - 1; i++) {
                const key = keys[i];
                if (current[key] === undefined || current[key] === null) {
                    current[key] = {};
                }
                current = current[key];
            }
            
            const lastKey = keys[keys.length - 1];
            const oldValue = current[lastKey];
            current[lastKey] = value;
            
            changes.push({ path, value, oldValue });
            this._recordHistory(path, oldValue, value);
        }
        
        // 批量通知
        for (const change of changes) {
            this._notify(change.path, change.value, change.oldValue);
        }
    }
    
    /**
     * 订阅状态变更
     * @param {string} path - 状态路径（支持通配符 '*'）
     * @param {Function} callback - 回调函数
     * @returns {Function} 取消订阅函数
     */
    subscribe(path, callback) {
        if (!this.subscribers.has(path)) {
            this.subscribers.set(path, new Set());
        }
        
        this.subscribers.get(path).add(callback);
        
        // 返回取消订阅函数
        return () => {
            const subs = this.subscribers.get(path);
            if (subs) {
                subs.delete(callback);
                if (subs.size === 0) {
                    this.subscribers.delete(path);
                }
            }
        };
    }
    
    /**
     * 重置状态
     * @param {string} section - 状态部分（如 'task', 'events'）
     */
    reset(section) {
        const defaults = {
            task: {
                id: null,
                status: 'idle',
                progress: 0,
                stage: '',
                error: null
            },
            file: {
                selected: null,
                preview: null,
                name: null,
                size: 0,
                type: ''
            },
            events: {
                items: [],
                stats: {
                    total: 0,
                    errors: 0,
                    warnings: 0,
                    retries: 0,
                    duration: 0
                },
                isLoading: false
            },
            report: {
                data: null,
                markdown: '',
                trace: null,
                isTraceVisible: false
            }
        };
        
        if (section && defaults[section]) {
            this.set(section, { ...defaults[section] });
        }
    }
    
    /**
     * 获取状态快照（用于调试）
     */
    getSnapshot() {
        return JSON.parse(JSON.stringify(this.state));
    }
    
    /**
     * 获取状态历史
     */
    getHistory() {
        return [...this.history];
    }
    
    /**
     * 内部方法：记录历史
     */
    _recordHistory(path, oldValue, newValue) {
        this.history.push({
            timestamp: Date.now(),
            path,
            oldValue,
            newValue
        });
        
        // 限制历史大小
        if (this.history.length > this.maxHistorySize) {
            this.history.shift();
        }
    }
    
    /**
     * 内部方法：通知订阅者
     */
    _notify(path, newValue, oldValue) {
        // 通知精确路径的订阅者
        const exactSubs = this.subscribers.get(path);
        if (exactSubs) {
            exactSubs.forEach(callback => {
                try {
                    callback(newValue, oldValue, path);
                } catch (error) {
                    console.error(`State subscriber error for path "${path}":`, error);
                }
            });
        }
        
        // 通知父路径的订阅者
        const parts = path.split('.');
        for (let i = parts.length - 1; i > 0; i--) {
            const parentPath = parts.slice(0, i).join('.');
            const parentSubs = this.subscribers.get(parentPath);
            if (parentSubs) {
                const parentValue = this.get(parentPath);
                parentSubs.forEach(callback => {
                    try {
                        callback(parentValue, undefined, parentPath);
                    } catch (error) {
                        console.error(`State subscriber error for parent path "${parentPath}":`, error);
                    }
                });
            }
        }
        
        // 通知通配符订阅者
        const wildcardSubs = this.subscribers.get('*');
        if (wildcardSubs) {
            wildcardSubs.forEach(callback => {
                try {
                    callback(this.state, path);
                } catch (error) {
                    console.error('State wildcard subscriber error:', error);
                }
            });
        }
    }
}

// 创建全局状态管理器实例
const stateManager = new StateManager();

// 导出
export default stateManager;

// 便捷方法
export const getState = (path) => stateManager.get(path);
export const setState = (path, value) => stateManager.set(path, value);
export const batchUpdate = (updates) => stateManager.batch(updates);
export const subscribe = (path, callback) => stateManager.subscribe(path, callback);
export const resetState = (section) => stateManager.reset(section);
