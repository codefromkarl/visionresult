/**
 * Visual Insight Agent - 主应用模块
 * 
 * 整合状态管理、UI组件和业务逻辑
 */

import stateManager, { getState, setState, batchUpdate, subscribe, resetState } from './state.js';
import toast, { showSuccess, showError, showWarning, showInfo, showLoading } from './toast.js';
import { t, getLang, setLang, initI18n } from './i18n.js';

// ==================== 常量 ====================
const API_BASE = '/api';
const MAX_EVENTS_DISPLAY = 100;
const POLL_INTERVAL = 2000;

// ==================== DOM 元素缓存 ====================
const elements = {};

// ==================== 初始化 ====================

/**
 * 初始化应用
 */
function init() {
    // 初始化 i18n
    initI18n();
    
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
    
    // 语言切换
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            setLang(btn.dataset.lang);
        });
    });
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
        showError(t('unknown') + ': JPG, PNG, GIF, WebP');
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
    
    resetState('events');
    resetState('report');
    
    batchUpdate({
        'task.status': 'uploading', 'task.progress': 0,
        'task.stage': t('progressUploading'), 'task.error': null, 'ui.activeView': 'processing'
    });
    
    elements.resultContainer.style.display = 'none';
    elements.resultContainer.classList.remove('visible');
    elements.progressContainer.style.display = '';
    elements.progressContainer.classList.add('visible');
    elements.eventsContainer.style.display = 'block';
    elements.eventsContainer.classList.add('visible');
    elements.reportContent.textContent = '';
    elements.eventsTimeline.innerHTML = '';
    elements.eventsStats.innerHTML = '';
    elements.analyzeBtn.disabled = true;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const resp = await fetch(`${API_BASE}/analyze`, { method: 'POST', body: formData });
        if (!resp.ok) throw new Error(`服务器错误: ${resp.status}`);
        
        const ct = resp.headers.get('content-type') || '';
        if (ct.includes('text/event-stream')) {
            await handleSSEStream(resp);
        } else {
            await handleSyncResponse(resp);
        }
    } catch (err) {
        batchUpdate({ 'task.status': 'failed', 'task.error': err.message });
        showError(`${t('failed')}: ${err.message}`);
        elements.analyzeBtn.disabled = false;
    }
}

// ==================== SSE 实时流处理 ====================

async function handleSSEStream(resp) {
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentEvent = '';
    const allEvents = [];
    const startTime = Date.now();
    
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
            if (line.startsWith('event: ')) {
                currentEvent = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
                try {
                    const data = JSON.parse(line.slice(6));
                    processSSEEvent(currentEvent, data, allEvents, startTime);
                } catch (e) { /* skip parse errors */ }
            }
        }
    }
    elements.analyzeBtn.disabled = false;
}

function processSSEEvent(event, data, allEvents, startTime) {
    switch (event) {
        case 'status':
            setState('task.id', data.task_id);
            batchUpdate({ 'task.status': 'processing', 'task.stage': t('progressAnalyzing'), 'task.progress': 5 });
            updateProgress(5);
            updateStage(t('progressAnalyzing'));
            break;
        
        case 'progress': {
            const pct = data.percent || 0;
            const label = data.label || data.stage || '';
            batchUpdate({ 'task.progress': pct, 'task.stage': label });
            updateProgress(pct);
            updateStage(label);
            allEvents.push({ ts: new Date().toISOString(), level: 'INFO', event: `${data.stage}_start`, node: data.stage });
            updateEventsTimeline(allEvents);
            break;
        }
        
        case 'insight': {
            allEvents.push({ ts: new Date().toISOString(), level: 'INFO', event: 'insight', ...data });
            updateEventsTimeline(allEvents);
            const stats = calculateStats(allEvents);
            stats.duration = Date.now() - startTime;
            updateEventsStats(stats);
            break;
        }
        
        case 'complete': {
            const analysis = data.analysis || {};
            const markdown = buildReportMarkdown({
                task_id: data.task_id, status: 'completed',
                filename: 'image',
                created_at: new Date(startTime).toISOString(),
                completed_at: new Date().toISOString(),
                analysis,
            });
            batchUpdate({
                'task.status': 'completed', 'task.progress': 100, 'task.stage': t('success'),
                'report.data': data, 'report.markdown': markdown, 'ui.activeView': 'result',
            });
            elements.progressContainer.style.display = 'none';
            elements.resultContainer.style.display = 'block';
            elements.resultContainer.classList.add('visible');
            elements.reportContent.textContent = markdown;
            if (data.pipeline_trace?.steps?.length) renderTraceFromPipeline(data.pipeline_trace);
            showSuccess(`${t('success')} ${data.total_ms ? (data.total_ms/1000).toFixed(1) : '?'}s`);
            break;
        }
        
        case 'error':
            batchUpdate({ 'task.status': 'failed', 'task.error': data.error });
            showError(`${t('failed')}: ${data.error}`);
            elements.progressContainer.style.display = 'none';
            elements.analyzeBtn.disabled = false;
            break;
    }
}

async function handleSyncResponse(resp) {
    const text = await resp.text();
    if (!text || !text.trim()) throw new Error('空响应');
    let data; try { data = JSON.parse(text); } catch(e) { throw new Error('响应格式错误'); }
    setState('task.id', data.task_id);
    if (data.status === 'completed' && data.analysis) {
        const markdown = buildReportMarkdown(data);
        batchUpdate({ 'task.status': 'completed', 'task.progress': 100, 'task.stage': t('success'), 'report.data': data, 'report.markdown': markdown, 'ui.activeView': 'result' });
        elements.progressContainer.style.display = 'none';
        elements.resultContainer.style.display = 'block';
        elements.resultContainer.classList.add('visible');
        elements.eventsContainer.style.display = 'block';
        elements.eventsContainer.classList.add('visible');
        elements.reportContent.textContent = markdown;
        if (data.pipeline_trace) renderTraceFromPipeline(data.pipeline_trace);
        showSuccess(t('success'));
    } else if (data.status === 'failed') {
        throw new Error(data.error || t('failed'));
    } else {
        setState('task.status', 'processing');
        pollForReport(data.task_id);
    }
}

function renderTraceFromPipeline(trace) {
    if (!trace.steps?.length) return;
    elements.traceTimeline.innerHTML = trace.steps.map(step => `
        <div class="trace-step ${step.status === 'failed' ? 'failed' : ''}">
            <div class="trace-step-header">
                <span class="trace-step-name">${getStageIcon(step.stage_name)} ${getStageName(step.stage_name)}</span>
                <div>
                    <span class="trace-step-status ${step.status}">${step.status === 'success' ? '成功' : step.status === 'failed' ? '失败' : '跳过'}</span>
                    <span class="trace-step-duration">${step.duration_ms || 0}ms</span>
                </div>
            </div>
            ${step.output_summary ? `<div class="trace-step-summary">📤 ${step.output_summary}</div>` : ''}
            ${step.key_findings?.length ? `<ul class="trace-step-findings">${step.key_findings.map(f => `<li>${f}</li>`).join('')}</ul>` : ''}
            ${step.error_message ? `<div class="trace-step-error">❌ ${step.error_message}</div>` : ''}
        </div>
    `).join('');
}

function streamProgress(taskId) {
    // Cloudflare Pages Functions 不支持 SSE
    // 直接使用轮询模式
    pollForReport(taskId);
}

function pollForReport(taskId, maxAttempts = 60) {
    let attempts = 0;
    
    const poll = async () => {
        attempts++;
        if (attempts > maxAttempts) {
            batchUpdate({
                'task.status': 'failed',
                'task.error': t('failed')
            });
            showError(t('failed'));
            return;
        }
        
        try {
            const resp = await fetch(`${API_BASE}/report/${taskId}`);
            
            if (!resp.ok) {
                if (resp.status === 404) {
                    // 任务尚未创建，继续轮询
                    setState('task.stage', `${t('loading')} (${attempts})`);
                    setState('task.progress', Math.min(attempts * 2, 90));
                    setTimeout(poll, POLL_INTERVAL);
                    return;
                }
                throw new Error(`HTTP ${resp.status}`);
            }
            
            const text = await resp.text();
            if (!text || text.trim() === '') {
                setTimeout(poll, POLL_INTERVAL);
                return;
            }
            
            let data;
            try {
                data = JSON.parse(text);
            } catch (e) {
                setTimeout(poll, POLL_INTERVAL);
                return;
            }
            
            if (data.status === 'completed') {
                // 将 Cloudflare 响应格式转换为报告
                const markdown = buildReportMarkdown(data);
                batchUpdate({
                    'task.status': 'completed',
                    'task.progress': 100,
                    'task.stage': t('success'),
                    'report.data': data,
                    'report.markdown': markdown,
                    'ui.activeView': 'result'
                });
                showSuccess(t('success'));
            } else if (data.status === 'failed') {
                batchUpdate({
                    'task.status': 'failed',
                    'task.error': data.error || t('failed')
                });
                showError(`${t('failed')}: ${data.error || t('unknown')}`);
            } else {
                // 仍在处理中
                setState('task.stage', `${t('progressAnalyzing')} (${attempts})`);
                setState('task.progress', Math.min(attempts * 2, 90));
                setTimeout(poll, POLL_INTERVAL);
            }
        } catch (err) {
            console.error('Poll error:', err);
            setTimeout(poll, POLL_INTERVAL);
        }
    };
    
    // 首次轮询延迟 2 秒
    setTimeout(poll, POLL_INTERVAL);
}

function buildReportMarkdown(data) {
    const a = data.analysis || {};
    let md = `# ${t('rptTitle')}\n\n`;
    md += `**${t('rptTaskId')}**: ${data.task_id || data.id || t('unknown')}  \n`;
    md += `**${t('rptFilename')}**: ${data.filename || t('unknown')}  \n`;
    md += `**${t('rptStatus')}**: ${data.status}  \n`;
    md += `**${t('rptCreatedAt')}**: ${data.created_at || ''}  \n`;
    md += `**${t('rptCompletedAt')}**: ${data.completed_at || ''}  \n\n`;
    
    if (a.description) md += `## ${t('rptSceneDesc')}\n\n${a.description}\n\n`;
    if (a.scene_type) md += `## ${t('rptSceneType')}\n\n${a.scene_type}\n\n`;
    
    if (a.location_guess) {
        md += `## ${t('rptLocation')}\n\n`;
        md += `- **${t('rptLocationLabel')}**: ${a.location_guess.location || t('unknown')}\n`;
        md += `- **${t('rptConfidence')}**: ${((a.location_guess.confidence || 0) * 100).toFixed(0)}%\n\n`;
    }
    
    if (a.time_guess) {
        md += `## ${t('rptTime')}\n\n`;
        if (a.time_guess.time_of_day) md += `- **${t('rptTimePeriod')}**: ${a.time_guess.time_of_day}\n`;
        if (a.time_guess.season) md += `- **${t('rptSeason')}**: ${a.time_guess.season}\n`;
        md += '\n';
    }
    
    if (a.detected_text && a.detected_text.length > 0) {
        md += `## ${t('rptDetectedText')}\n\n`;
        a.detected_text.forEach(t => { md += `- ${t}\n`; });
        md += '\n';
    }
    
    if (a.key_evidence && a.key_evidence.length > 0) {
        md += `## ${t('rptKeyEvidence')}\n\n`;
        a.key_evidence.forEach(e => { md += `- ${e}\n`; });
        md += '\n';
    }
    
    if (data.error) md += `## ${t('rptError')}\n\n${data.error}\n\n`;
    
    return md;
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
    // 轮询模式下，报告加载由 pollForReport 处理
    // 这里仅作为 fallback 手动触发
    try {
        const resp = await fetch(`${API_BASE}/report/${taskId}`);
        
        if (!resp.ok) {
            throw new Error(`服务器错误: ${resp.status} ${resp.statusText}`);
        }
        
        const text = await resp.text();
        if (!text || text.trim() === '') {
            throw new Error('服务器返回空响应');
        }
        
        let data;
        try {
            data = JSON.parse(text);
        } catch (jsonError) {
            throw new Error('服务器响应格式错误');
        }
        
        const markdown = buildReportMarkdown(data);
        batchUpdate({
            'task.status': data.status === 'completed' ? 'completed' : 'failed',
            'report.data': data,
            'report.markdown': markdown,
            'ui.activeView': 'result'
        });
        
        if (data.status === 'completed') {
            showSuccess(t('success'));
        } else {
            showError(`状态: ${data.status}`);
        }
        
    } catch (err) {
        batchUpdate({
            'task.status': 'failed',
            'task.error': err.message
        });
        showError(`加载报告失败: ${err.message}`);
    }
}

// ==================== 分析事件生成 ====================

async function addAnalysisEvents(data) {
    const taskId = data.task_id;
    if (!taskId) return;
    
    try {
        // 从 /api/events/{task_id} 获取真实的 pipeline 事件
        const resp = await fetch(`/api/events/${taskId}`);
        if (resp.ok) {
            const result = await resp.json();
            if (result.events && result.events.length > 0) {
                const events = result.events;
                const stats = calculateStats(events);
                batchUpdate({
                    'events.items': events,
                    'events.stats': stats
                });
                return;
            }
        }
    } catch (e) {
        console.error('Failed to load events:', e);
    }
    
    // Fallback: 从 pipeline_trace 构建事件
    const trace = data.pipeline_trace;
    if (trace && trace.steps && trace.steps.length > 0) {
        const events = [];
        let baseTime = data.created_at ? new Date(data.created_at).getTime() : Date.now();
        
        events.push({
            ts: new Date(baseTime).toISOString(),
            level: 'INFO',
            event: 'pipeline_start',
            node: 'Pipeline'
        });
        
        let offset = 100;
        for (const step of trace.steps) {
            events.push({
                ts: new Date(baseTime + offset).toISOString(),
                level: step.status === 'failed' ? 'ERROR' : 'INFO',
                event: `${step.stage_name}_start`,
                node: step.stage_name,
                duration_ms: 0
            });
            offset += Math.max(step.duration_ms || 100, 50);
            events.push({
                ts: new Date(baseTime + offset).toISOString(),
                level: step.status === 'failed' ? 'ERROR' : 'INFO',
                event: `${step.stage_name}_end`,
                node: step.stage_name,
                duration_ms: step.duration_ms || 0
            });
            offset += 100;
            
            // 添加关键发现
            if (step.key_findings) {
                for (const finding of step.key_findings) {
                    events.push({
                        ts: new Date(baseTime + offset).toISOString(),
                        level: 'INFO',
                        event: 'insight',
                        node: step.stage_name,
                        scene_type: finding
                    });
                    offset += 10;
                }
            }
        }
        
        events.push({
            ts: new Date(baseTime + offset).toISOString(),
            level: 'INFO',
            event: 'pipeline_end',
            node: 'Pipeline',
            duration_ms: offset
        });
        
        const stats = calculateStats(events);
        batchUpdate({
            'events.items': events,
            'events.stats': stats
        });
        return;
    }
    
    // 最终 fallback: 基本事件
    const fallbackEvents = [
        { ts: data.created_at, level: 'INFO', event: 'pipeline_start', node: 'Pipeline' },
        { ts: data.completed_at, level: 'INFO', event: 'pipeline_end', node: 'Pipeline' }
    ];
    const stats = calculateStats(fallbackEvents);
    batchUpdate({
        'events.items': fallbackEvents,
        'events.stats': stats
    });
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
    
    if (status === 'uploading' || status === 'processing') {
        elements.progressContainer.classList.add('visible');
        elements.progressContainer.style.display = 'block';
        elements.eventsContainer.classList.add('visible');
        elements.eventsContainer.style.display = 'block';
        elements.resultContainer.classList.remove('visible');
        elements.resultContainer.style.display = 'none';
    } else if (status === 'completed' || status === 'failed') {
        elements.progressContainer.classList.remove('visible');
        elements.progressContainer.style.display = 'none';
        // 分析完成后仍显示分析过程
        elements.eventsContainer.classList.add('visible');
        elements.eventsContainer.style.display = 'block';
        elements.resultContainer.classList.add('visible');
        elements.resultContainer.style.display = 'block';
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
        
        // Insight 事件渲染为卡片
        if (evt.event === 'insight') {
            const results = evt.results || [];
            return `
                <div class="insight-card">
                    <div class="insight-header">
                        <span class="insight-icon">${evt.icon || '📦'}</span>
                        <div class="insight-title-group">
                            <span class="insight-title">${evt.title || evt.node || 'unknown'}</span>
                            <span class="insight-tool">${evt.tool || ''} ${evt.tool_detail ? '| ' + evt.tool_detail : ''}</span>
                        </div>
                        ${evt.duration_ms !== undefined ? `<span class="insight-time">${evt.duration_ms}ms</span>` : ''}
                    </div>
                    <div class="insight-summary">${evt.summary || ''}</div>
                    ${results.length > 0 ? `
                        <div class="insight-results">
                            ${results.map(r => `
                                <div class="insight-result-item">
                                    <span class="insight-result-label">${r.label}</span>
                                    <span class="insight-result-value">${Array.isArray(r.value) ? r.value.join(', ') : r.value}</span>
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            `;
        }
        
        // 普通事件渲染
        const tags = [];
        if (evt.node) tags.push({ text: evt.node, class: 'node' });
        if (evt.duration_ms !== undefined && evt.duration_ms > 0) tags.push({ text: `${evt.duration_ms}ms`, class: 'duration' });
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
            <div class="events-stat-label">${t('eventsTotal')}</div>
        </div>
        <div class="events-stat">
            <div class="events-stat-value ${stats.errors > 0 ? 'error' : ''}">${stats.errors}</div>
            <div class="events-stat-label">${t('eventsErrors')}</div>
        </div>
        <div class="events-stat">
            <div class="events-stat-value ${stats.warnings > 0 ? 'warning' : ''}">${stats.warnings}</div>
            <div class="events-stat-label">${t('eventsWarnings')}</div>
        </div>
        <div class="events-stat">
            <div class="events-stat-value">${stats.retries}</div>
            <div class="events-stat-label">${t('eventsRetries')}</div>
        </div>
        <div class="events-stat">
            <div class="events-stat-value">${stats.duration}ms</div>
            <div class="events-stat-label">${t('eventsDuration')}</div>
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
        elements.traceContainer.style.display = '';
        elements.traceToggleBtn.textContent = t('reportHideTrace');
        
        // 加载推理链路数据
        const taskId = getState('task.id');
        if (taskId && !getState('report.trace')) {
            loadTrace(taskId);
        }
    } else {
        elements.traceContainer.classList.remove('visible');
        elements.traceContainer.style.display = 'none';
        elements.traceToggleBtn.textContent = t('reportTrace');
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
                    <div class="empty-state-text">${t('traceNoData')}</div>
                </div>
            `;
        }
    } catch (err) {
        console.error('Failed to load trace:', err);
        showError(`${t('failed')}: ${err.message}`);
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
                        ${rt.strategy_used === 'rule' ? t('strategyRule') : 
                          rt.strategy_used === 'llm' ? t('strategyLLM') : t('strategyUncertain')}
                    </span>
                </h4>
                <div class="reasoning-probability">${t('rptConfidence')}: ${(rt.final_probability * 100).toFixed(1)}%</div>
                ${rt.steps.length > 0 ? `
                    <div class="reasoning-steps">
                        ${rt.steps.map(step => `
                            <div class="reasoning-step-item">
                                <strong>${step.action === 'rule_match' ? t('actionRuleMatch') : 
                                          step.action === 'llm_inference' ? t('actionLLMInference') : step.action}:</strong>
                                ${step.description}
                                ${step.metadata?.llm_reasoning ? 
                                    `<br><em>${step.metadata.llm_reasoning}</em>` : ''}
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
                <div class="empty-state-text">${t('traceNoReasoning')}</div>
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
                            ${step.status === 'success' ? t('traceSuccess') : 
                              step.status === 'failed' ? t('traceFailed') : t('traceSkipped')}
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
                <div class="empty-state-text">${t('traceNoPipeline')}</div>
            </div>
        `;
    }
}

// ==================== 工具函数 ====================

function formatEventName(eventName) {
    const replacements = {
        'start': t('evtStart'),
        'end': t('evtEnd'),
        'fail': t('evtFail'),
        'retry': t('evtRetry'),
        'ok': t('evtOk'),
        'timeout': t('evtTimeout'),
        'received': t('evtReceived'),
        'created': t('evtCreated'),
        'connect': t('evtConnect'),
        'node': t('evtNode'),
        'vlm': t('evtVLM'),
        'pipeline': t('evtPipeline'),
        'request': t('evtRequest'),
        'background task': t('evtBackgroundTask'),
        'progress': t('evtProgress'),
        'sse': t('evtSSE'),
        'image compressed': t('evtImageCompressed')
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
        'preprocess': t('stagePreprocess'),
        'ocr': t('stageOCR'),
        'vlm_analysis': t('stageVLM'),
        'entity_extraction': t('stageEntity'),
        'web_search': t('stageSearch'),
        'evidence_fusion': t('stageFusion'),
        'report_generation': t('stageReport'),
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
        showError(t('noReport'));
        return;
    }
    
    try {
        const resp = await fetch(`${API_BASE}/report/${taskId}?format=html`);
        
        if (!resp.ok) {
            throw new Error(`${t('failed')}: ${resp.status} ${resp.statusText}`);
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
        
        showSuccess(t('success'));
    } catch (err) {
        console.error('Download failed:', err);
        showError(`${t('failed')}: ${err.message}`);
    }
};

// ==================== 初始化 ====================

// 等待 DOM 加载完成
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
