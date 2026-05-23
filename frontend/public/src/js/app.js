/**
 * Visual Insight Agent - 主应用模块
 * 
 * 整合状态管理、UI组件和业务逻辑
 */

import stateManager, { getState, setState, batchUpdate, subscribe, resetState } from './state.js';
import toast, { showSuccess, showError, showWarning, showInfo, showLoading } from './toast.js';

// ==================== 常量 ====================
const API_BASE = '/api/v1';
const MAX_EVENTS_DISPLAY = 100;
const POLL_INTERVAL = 2000;

// ==================== DOM 元素缓存 ====================
const elements = {};

// ==================== 初始化 ====================

/**
 * 初始化应用
 */
function init() {
    // 缓存 DOM 元素
    cacheElements();
    
    // 绑定事件
    bindEvents();
    
    // 订阅状态变更
    setupSubscriptions();
    
    console.log('🚀 Visual Insight Agent initialized');
}

/**
 * 缓存 DOM 元素
 */
function cacheElements() {
    elements.uploadZone = document.getElementById('uploadZone');
    elements.fileInput = document.getElementById('fileInput');
    elements.previewContainer = document.getElementById('previewContainer');
    elements.previewImg = document.getElementById('previewImg');
    elements.analyzeBtn = document.getElementById('analyzeBtn');
    elements.progressContainer = document.getElementById('progressContainer');
    elements.progressFill = document.getElementById('progressFill');
    elements.progressText = document.getElementById('progressText');
    elements.resultContainer = document.getElementById('resultContainer');
    elements.reportContent = document.getElementById('reportContent');
    elements.eventsContainer = document.getElementById('eventsContainer');
    elements.eventsTimeline = document.getElementById('eventsTimeline');
    elements.eventsStats = document.getElementById('eventsStats');
    elements.traceContainer = document.getElementById('traceContainer');
    elements.traceToggleBtn = document.getElementById('traceToggleBtn');
    elements.reasoningContainer = document.getElementById('reasoningContainer');
    elements.traceTimeline = document.getElementById('traceTimeline');
    elements.verboseCheck = document.getElementById('verboseCheck');
}

/**
 * 绑定事件监听器
 */
function bindEvents() {
    // 上传区域
    elements.uploadZone.addEventListener('click', () => elements.fileInput.click());
    elements.uploadZone.addEventListener('dragover', handleDragOver);
    elements.uploadZone.addEventListener('dragleave', handleDragLeave);
    elements.uploadZone.addEventListener('drop', handleDrop);
    
    // 文件选择
    elements.fileInput.addEventListener('change', handleFileSelect);
    
    // 分析按钮
    elements.analyzeBtn.addEventListener('click', startAnalysis);
    
    // Verbose 模式
    elements.verboseCheck.addEventListener('change', (e) => {
        setState('ui.isVerboseMode', e.target.checked);
    });
    
    // 推理链路切换
    elements.traceToggleBtn.addEventListener('click', toggleTrace);
}

/**
 * 订阅状态变更
 */
function setupSubscriptions() {
    // 监听任务状态变更
    subscribe('task.status', handleTaskStatusChange);
    subscribe('task.progress', updateProgress);
    subscribe('task.stage', updateStage);
    
    // 监听文件状态
    subscribe('file.preview', updatePreview);
    
    // 监听事件状态
    subscribe('events.items', updateEventsTimeline);
    subscribe('events.stats', updateEventsStats);
    
    // 监听报告状态
    subscribe('report.markdown', updateReport);
    subscribe('report.trace', updateTrace);
}

// ==================== 事件处理 ====================

function handleDragOver(e) {
    e.preventDefault();
    elements.uploadZone.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    elements.uploadZone.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    elements.uploadZone.classList.remove('dragover');
    
    if (e.dataTransfer.files.length) {
        handleFile(e.dataTransfer.files[0]);
    }
}

function handleFileSelect(e) {
    if (e.target.files.length) {
        handleFile(e.target.files[0]);
    }
}

function handleFile(file) {
    // 验证文件类型
    if (!file.type.startsWith('image/')) {
        showError('请选择图片文件（JPG、PNG、GIF、WebP）');
        return;
    }
    
    // 验证文件大小（50MB）
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
        showError(`文件太大，最大支持 ${maxSize / (1024 * 1024)}MB`);
        return;
    }
    
    // 更新状态
    const reader = new FileReader();
    reader.onload = (e) => {
        batchUpdate({
            'file.selected': file,
            'file.preview': e.target.result,
            'file.name': file.name,
            'file.size': file.size,
            'file.type': file.type,
            'task.status': 'idle'
        });
        
        elements.analyzeBtn.disabled = false;
    };
    reader.readAsDataURL(file);
}

// ==================== 分析流程 ====================

async function startAnalysis() {
    const file = getState('file.selected');
    if (!file) return;
    
    // 重置状态
    resetState('events');
    resetState('report');
    
    batchUpdate({
        'task.status': 'uploading',
        'task.progress': 0,
        'task.stage': '上传中...',
        'task.error': null,
        'ui.activeView': 'processing'
    });
    
    const verbose = getState('ui.isVerboseMode');
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const url = verbose ? `${API_BASE}/analyze?verbose=true` : `${API_BASE}/analyze`;
        const resp = await fetch(url, {
            method: 'POST',
            body: formData,
        });
        
        // 检查响应是否成功
        if (!resp.ok) {
            let errorMessage = '上传失败';
            try {
                const error = await resp.json();
                errorMessage = error.detail || error.message || errorMessage;
            } catch (jsonError) {
                // 如果 JSON 解析失败，使用状态文本
                errorMessage = `服务器错误: ${resp.status} ${resp.statusText}`;
            }
            throw new Error(errorMessage);
        }
        
        // 解析成功响应
        const text = await resp.text();
        if (!text || text.trim() === '') {
            throw new Error('服务器返回空响应');
        }
        
        let data;
        try {
            data = JSON.parse(text);
        } catch (jsonError) {
            console.error('JSON 解析失败:', text);
            throw new Error('服务器响应格式错误');
        }
        
        setState('task.id', data.task_id);
        setState('task.status', 'processing');
        
        // 开始监听进度
        streamProgress(data.task_id);
        
    } catch (err) {
        batchUpdate({
            'task.status': 'failed',
            'task.error': err.message
        });
        showError(`分析失败: ${err.message}`);
    }
}

function streamProgress(taskId) {
    const eventSource = new EventSource(`${API_BASE}/analyze/${taskId}/stream`);
    
    let events = [];
    
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'event') {
            // 实时事件
            const evt = data.data;
            events.push(evt);
            
            // 限制显示数量
            if (events.length > MAX_EVENTS_DISPLAY) {
                events = events.slice(-MAX_EVENTS_DISPLAY);
            }
            
            // 更新状态
            batchUpdate({
                'events.items': [...events],
                'events.stats': calculateStats(events)
            });
            
            // 更新进度文本
            if (evt.event === 'node_start' && evt.node) {
                const stageNames = {
                    'preprocess': '预处理...',
                    'ocr': '文字识别...',
                    'vlm_analysis': '场景分析...',
                    'entity_extraction': '实体抽取...',
                    'web_search': '联网验证...',
                    'evidence_fusion': '证据融合...',
                    'report_generation': '生成报告...',
                };
                setState('task.stage', stageNames[evt.node] || evt.node);
            }
            
            if (evt.event === 'vlm_request_retry') {
                setState('task.stage', `VLM 重试 ${evt.attempt}/${evt.max_retries}...`);
            }
            
        } else if (data.type === 'progress') {
            // 进度更新
            if (data.progress !== undefined) {
                setState('task.progress', data.progress);
            }
            
            if (data.stage === 'done') {
                eventSource.close();
                setState('task.progress', 100);
                loadReport(taskId);
            }
        }
    };
    
    eventSource.onerror = () => {
        eventSource.close();
        // 回退到轮询
        setTimeout(() => loadReport(taskId), POLL_INTERVAL);
    };
}

function calculateStats(events) {
    const errors = events.filter(e => e.level === 'ERROR').length;
    const warnings = events.filter(e => e.level === 'WARNING').length;
    const retries = events.filter(e => e.event && e.event.includes('retry')).length;
    const totalDuration = events.reduce((sum, e) => sum + (e.duration_ms || 0), 0);
    
    return {
        total: events.length,
        errors,
        warnings,
        retries,
        duration: totalDuration
    };
}

async function loadReport(taskId) {
    try {
        const resp = await fetch(`${API_BASE}/report/${taskId}`);
        
        if (!resp.ok) {
            let errorMessage = '获取报告失败';
            try {
                const error = await resp.json();
                errorMessage = error.detail || error.message || errorMessage;
            } catch (jsonError) {
                errorMessage = `服务器错误: ${resp.status} ${resp.statusText}`;
            }
            throw new Error(errorMessage);
        }
        
        // 解析响应
        const text = await resp.text();
        if (!text || text.trim() === '') {
            throw new Error('服务器返回空响应');
        }
        
        let data;
        try {
            data = JSON.parse(text);
        } catch (jsonError) {
            console.error('JSON 解析失败:', text);
            throw new Error('服务器响应格式错误');
        }
        
        if (data.status === 'completed') {
            batchUpdate({
                'task.status': 'completed',
                'report.data': data,
                'report.markdown': data.report_markdown,
                'ui.activeView': 'result'
            });
            showSuccess('分析完成！');
            
        } else if (data.status === 'failed') {
            batchUpdate({
                'task.status': 'failed',
                'task.error': '分析失败',
                'report.markdown': data.report_markdown || '分析失败',
                'ui.activeView': 'result'
            });
            showError('分析失败');
            
        } else {
            // 继续轮询
            setTimeout(() => loadReport(taskId), POLL_INTERVAL);
        }
        
    } catch (err) {
        batchUpdate({
            'task.status': 'failed',
            'task.error': err.message
        });
        showError(`加载报告失败: ${err.message}`);
    }
}

// ==================== UI 更新 ====================

function handleTaskStatusChange(status) {
    const views = {
        'upload': ['upload'],
        'uploading': ['processing'],
        'processing': ['processing'],
        'completed': ['result'],
        'failed': ['result']
    };
    
    // 更新视图可见性
    const activeViews = views[status] || ['upload'];
    
    // 这里可以添加视图切换逻辑
    if (status === 'uploading' || status === 'processing') {
        elements.progressContainer.classList.add('visible');
        elements.resultContainer.classList.remove('visible');
    } else if (status === 'completed' || status === 'failed') {
        elements.progressContainer.classList.remove('visible');
        elements.resultContainer.classList.add('visible');
    }
}

function updateProgress(progress) {
    elements.progressFill.style.width = `${progress}%`;
}

function updateStage(stage) {
    elements.progressText.innerHTML = `
        <span class="progress-stage">${stage}</span>
        <span class="progress-percent">${getState('task.progress')}%</span>
    `;
}

function updatePreview(preview) {
    if (preview) {
        elements.previewImg.src = preview;
        elements.previewContainer.classList.add('visible');
    } else {
        elements.previewContainer.classList.remove('visible');
    }
}

function updateEventsTimeline(events) {
    // 限制显示数量
    const displayEvents = events.slice(-MAX_EVENTS_DISPLAY);
    
    elements.eventsTimeline.innerHTML = displayEvents.map(evt => {
        const ts = evt.ts ? new Date(evt.ts).toLocaleTimeString('zh-CN', { 
            hour12: false, 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit', 
            fractionalSecondDigits: 3 
        }) : '';
        
        const levelClass = `event-${evt.level || 'INFO'}`;
        const eventClass = evt.event ? (
            evt.event.includes('start') ? 'event-start' :
            evt.event.includes('end') ? 'event-end' :
            evt.event.includes('fail') ? 'event-fail' :
            evt.event.includes('retry') ? 'event-retry' : ''
        ) : '';
        
        // 构建详情标签
        const tags = [];
        if (evt.node) tags.push({ text: evt.node, class: 'node' });
        if (evt.duration_ms !== undefined) tags.push({ text: `${evt.duration_ms}ms`, class: 'duration' });
        if (evt.error) tags.push({ text: evt.error, class: 'error' });
        if (evt.scene_type) tags.push({ text: evt.scene_type, class: 'node' });
        if (evt.location) tags.push({ text: `📍 ${evt.location}`, class: 'node' });
        
        const eventName = formatEventName(evt.event || 'unknown');
        
        return `
            <div class="event-item ${levelClass} ${eventClass}">
                <div class="event-time">${ts}</div>
                <div class="event-name">${eventName}</div>
                <div class="event-details">
                    ${tags.map(t => `<span class="event-tag ${t.class}">${t.text}</span>`).join('')}
                </div>
            </div>
        `;
    }).join('');
    
    // 自动滚动到底部
    elements.eventsTimeline.scrollTop = elements.eventsTimeline.scrollHeight;
}

function updateEventsStats(stats) {
    elements.eventsStats.innerHTML = `
        <div class="events-stat">
            <div class="events-stat-value">${stats.total}</div>
            <div class="events-stat-label">事件数</div>
        </div>
        <div class="events-stat">
            <div class="events-stat-value ${stats.errors > 0 ? 'error' : ''}">${stats.errors}</div>
            <div class="events-stat-label">错误</div>
        </div>
        <div class="events-stat">
            <div class="events-stat-value ${stats.warnings > 0 ? 'warning' : ''}">${stats.warnings}</div>
            <div class="events-stat-label">警告</div>
        </div>
        <div class="events-stat">
            <div class="events-stat-value">${stats.retries}</div>
            <div class="events-stat-label">重试</div>
        </div>
        <div class="events-stat">
            <div class="events-stat-value">${stats.duration}ms</div>
            <div class="events-stat-label">总耗时</div>
        </div>
    `;
}

function updateReport(markdown) {
    elements.reportContent.textContent = markdown;
}

function updateTrace(trace) {
    if (!trace) return;
    
    // 渲染推理链路
    renderTrace(trace);
}

// ==================== 推理链路渲染 ====================

function toggleTrace() {
    const isVisible = getState('report.isTraceVisible');
    setState('report.isTraceVisible', !isVisible);
    
    if (!isVisible) {
        elements.traceContainer.classList.add('visible');
        elements.traceToggleBtn.textContent = '❌ 隐藏链路';
        
        // 加载推理链路数据
        const taskId = getState('task.id');
        if (taskId && !getState('report.trace')) {
            loadTrace(taskId);
        }
    } else {
        elements.traceContainer.classList.remove('visible');
        elements.traceToggleBtn.textContent = '🔍 推理链路';
    }
}

async function loadTrace(taskId) {
    try {
        const resp = await fetch(`${API_BASE}/report/${taskId}?include_trace=true`);
        
        if (!resp.ok) {
            let errorMessage = '获取推理链路失败';
            try {
                const error = await resp.json();
                errorMessage = error.detail || error.message || errorMessage;
            } catch (jsonError) {
                errorMessage = `服务器错误: ${resp.status} ${resp.statusText}`;
            }
            throw new Error(errorMessage);
        }
        
        // 解析响应
        const text = await resp.text();
        if (!text || text.trim() === '') {
            throw new Error('服务器返回空响应');
        }
        
        let data;
        try {
            data = JSON.parse(text);
        } catch (jsonError) {
            console.error('JSON 解析失败:', text);
            throw new Error('服务器响应格式错误');
        }
        
        if (data.pipeline_trace) {
            setState('report.trace', data.pipeline_trace);
        } else {
            elements.traceTimeline.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📭</div>
                    <div class="empty-state-text">此报告未记录推理链路（需要 verbose 模式）</div>
                </div>
            `;
        }
    } catch (err) {
        console.error('Failed to load trace:', err);
        showError(`加载推理链路失败: ${err.message}`);
    }
}

function renderTrace(trace) {
    // 渲染推理链路
    if (trace.reasoning_traces && trace.reasoning_traces.length > 0) {
        elements.reasoningContainer.innerHTML = trace.reasoning_traces.map(rt => `
            <div class="reasoning-card">
                <h4>
                    ${rt.conclusion_category === 'location' ? '📍' : 
                      rt.conclusion_category === 'scene' ? '🏞️' : 
                      rt.conclusion_category === 'time' ? '⏰' : '📝'}
                    ${rt.conclusion_statement}
                    <span class="reasoning-strategy ${rt.strategy_used}">
                        ${rt.strategy_used === 'rule' ? '规则匹配' : 
                          rt.strategy_used === 'llm' ? 'LLM推理' : '不确定'}
                    </span>
                </h4>
                <div class="reasoning-probability">置信度: ${(rt.final_probability * 100).toFixed(1)}%</div>
                ${rt.steps.length > 0 ? `
                    <div class="reasoning-steps">
                        ${rt.steps.map(step => `
                            <div class="reasoning-step-item">
                                <strong>${step.action === 'rule_match' ? '规则匹配' : 
                                          step.action === 'llm_inference' ? 'LLM推理' : step.action}:</strong>
                                ${step.description}
                                ${step.metadata?.llm_reasoning ? 
                                    `<br><em>推理过程: ${step.metadata.llm_reasoning}</em>` : ''}
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `).join('');
    } else {
        elements.reasoningContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <div class="empty-state-text">无推理链路数据</div>
            </div>
        `;
    }
    
    // 渲染 Pipeline 步骤
    if (trace.steps && trace.steps.length > 0) {
        elements.traceTimeline.innerHTML = trace.steps.map(step => `
            <div class="trace-step ${step.status === 'failed' ? 'failed' : ''}">
                <div class="trace-step-header">
                    <span class="trace-step-name">
                        ${getStageIcon(step.stage_name)} ${getStageName(step.stage_name)}
                    </span>
                    <div>
                        <span class="trace-step-status ${step.status}">
                            ${step.status === 'success' ? '成功' : 
                              step.status === 'failed' ? '失败' : '跳过'}
                        </span>
                        <span class="trace-step-duration">${step.duration_ms}ms</span>
                    </div>
                </div>
                ${step.input_summary ? 
                    `<div class="trace-step-summary">📥 ${step.input_summary}</div>` : ''}
                ${step.output_summary ? 
                    `<div class="trace-step-summary">📤 ${step.output_summary}</div>` : ''}
                ${step.key_findings?.length > 0 ? `
                    <ul class="trace-step-findings">
                        ${step.key_findings.map(f => `<li>${f}</li>`).join('')}
                    </ul>
                ` : ''}
                ${step.error_message ? 
                    `<div class="trace-step-error">❌ ${step.error_message}</div>` : ''}
            </div>
        `).join('');
    } else {
        elements.traceTimeline.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">⚙️</div>
                <div class="empty-state-text">无 Pipeline 执行数据</div>
            </div>
        `;
    }
}

// ==================== 工具函数 ====================

function formatEventName(eventName) {
    const replacements = {
        'start': '▶️ 开始',
        'end': '✅ 完成',
        'fail': '❌ 失败',
        'retry': '🔄 重试',
        'ok': '✅ 成功',
        'timeout': '⏰ 超时',
        'received': '📥 接收',
        'created': '🆕 创建',
        'connect': '🔗 连接',
        'node': '📦 节点',
        'vlm': '👁️ VLM',
        'pipeline': '⚙️ Pipeline',
        'request': '🌐 请求',
        'background task': '🔄 后台任务',
        'progress': '📊 进度',
        'sse': '📡 SSE',
        'image compressed': '🖼️ 图片压缩'
    };
    
    let result = eventName.replace(/_/g, ' ');
    
    for (const [key, value] of Object.entries(replacements)) {
        result = result.replace(new RegExp(`\\b${key}\\b`, 'g'), value);
    }
    
    return result;
}

function getStageIcon(stage) {
    const icons = {
        'preprocess': '🖼️',
        'ocr': '📝',
        'vlm_analysis': '👁️',
        'entity_extraction': '🏷️',
        'web_search': '🌐',
        'evidence_fusion': '🔬',
        'report_generation': '📊',
    };
    return icons[stage] || '⚙️';
}

function getStageName(stage) {
    const names = {
        'preprocess': '图片预处理',
        'ocr': 'OCR文字识别',
        'vlm_analysis': 'VLM场景分析',
        'entity_extraction': '实体抽取',
        'web_search': '联网验证',
        'evidence_fusion': '证据融合',
        'report_generation': '报告生成',
    };
    return names[stage] || stage;
}

// ==================== 导出函数（供 HTML 使用） ====================

window.downloadMarkdown = function() {
    const content = getState('report.markdown');
    const taskId = getState('task.id');
    
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `report-${taskId || 'unknown'}.md`;
    a.click();
    URL.revokeObjectURL(url);
};

window.downloadHTML = async function() {
    const taskId = getState('task.id');
    if (!taskId) {
        showError('没有可下载的报告');
        return;
    }
    
    try {
        const resp = await fetch(`${API_BASE}/report/${taskId}?format=html`);
        
        if (!resp.ok) {
            throw new Error(`下载失败: ${resp.status} ${resp.statusText}`);
        }
        
        const html = await resp.text();
        if (!html || html.trim() === '') {
            throw new Error('服务器返回空内容');
        }
        
        const blob = new Blob([html], { type: 'text/html' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `report-${taskId}.html`;
        a.click();
        URL.revokeObjectURL(url);
        
        showSuccess('下载成功');
    } catch (err) {
        console.error('下载失败:', err);
        showError(`下载失败: ${err.message}`);
    }
};

// ==================== 初始化 ====================

// 等待 DOM 加载完成
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
