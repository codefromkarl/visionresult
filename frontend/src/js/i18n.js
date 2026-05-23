/**
 * 国际化（i18n）模块
 * 
 * 支持中文（zh）和英文（en）双语切换
 * 语言偏好存储在 localStorage 中
 */

const I18N = {
    zh: {
        // 页面标题
        title: '🔍 Visual Insight Agent',
        subtitle: '多模态图片分析系统 — 视觉分析 + 证据链推理',

        // 导航
        navUpload: '上传分析',
        navHistory: '历史记录',

        // 上传区域
        uploadHint: '拖拽图片到此处或点击上传',
        uploadSupport: '支持 JPG、PNG、GIF、WebP 格式',
        uploadAnalyze: '开始分析',
        uploadVerbose: '记录推理链路（Verbose 模式）',

        // 进度
        progressAnalyzing: '分析中...',
        progressUploading: '上传中...',

        // 报告
        reportTitle: '📊 分析报告',
        reportMarkdown: '📄 Markdown',
        reportHTML: '🌐 HTML',
        reportTrace: '🔍 推理链路',
        reportHideTrace: '❌ 隐藏链路',

        // 推理链路
        traceTitle: '🧠 思考链条与调用证据链',
        tracePipeline: '⚙️ Pipeline 执行详情',
        traceNoData: '此报告未记录推理链路（需要 verbose 模式）',
        traceNoPipeline: '无 Pipeline 执行数据',
        traceNoReasoning: '无推理链路数据',
        traceSuccess: '成功',
        traceFailed: '失败',
        traceSkipped: '跳过',

        // 分析过程
        eventsTitle: '📋 分析过程',
        eventsTotal: '事件数',
        eventsErrors: '错误',
        eventsWarnings: '警告',
        eventsRetries: '重试',
        eventsDuration: '总耗时',

        // 报告内容标签（对应 buildReportMarkdown）
        rptTitle: '图片分析报告',
        rptTaskId: '任务 ID',
        rptFilename: '文件名',
        rptStatus: '状态',
        rptCreatedAt: '创建时间',
        rptCompletedAt: '完成时间',
        rptSceneDesc: '场景描述',
        rptSceneType: '场景类型',
        rptLocation: '地点推测',
        rptLocationLabel: '地点',
        rptConfidence: '置信度',
        rptTime: '时间推测',
        rptTimePeriod: '时间段',
        rptSeason: '季节',
        rptDetectedText: '检测文字',
        rptKeyEvidence: '关键证据',
        rptError: '错误信息',

        // Pipeline 阶段名
        stagePreprocess: '图片预处理',
        stageOCR: 'OCR文字识别',
        stageVLM: 'VLM场景分析',
        stageEntity: '实体抽取',
        stageSearch: '联网验证',
        stageFusion: '证据融合',
        stageReport: '报告生成',

        // 事件名格式化
        evtStart: '▶️ 开始',
        evtEnd: '✅ 完成',
        evtFail: '❌ 失败',
        evtRetry: '🔄 重试',
        evtOk: '✅ 成功',
        evtTimeout: '⏰ 超时',
        evtReceived: '📥 接收',
        evtCreated: '🆕 创建',
        evtConnect: '🔗 连接',
        evtNode: '📦 节点',
        evtVLM: '👁️ VLM',
        evtPipeline: '⚙️ Pipeline',
        evtRequest: '🌐 请求',
        evtBackgroundTask: '🔄 后台任务',
        evtProgress: '📊 进度',
        evtSSE: '📡 SSE',
        evtImageCompressed: '🖼️ 图片压缩',

        // 通用
        unknown: '未知',
        loading: '加载中...',
        success: '分析完成！',
        failed: '分析失败',
        noReport: '没有可下载的报告',

        // 推理策略
        strategyRule: '规则匹配',
        strategyLLM: 'LLM推理',
        strategyUncertain: '不确定',
        actionRuleMatch: '规则匹配',
        actionLLMInference: 'LLM推理',
    },

    en: {
        // Page title
        title: '🔍 Visual Insight Agent',
        subtitle: 'Multimodal Image Analysis — Vision + Evidence Chain Reasoning',

        // Navigation
        navUpload: 'Upload',
        navHistory: 'History',

        // Upload area
        uploadHint: 'Drag image here or click to upload',
        uploadSupport: 'Supports JPG, PNG, GIF, WebP formats',
        uploadAnalyze: 'Start Analysis',
        uploadVerbose: 'Record reasoning trace (Verbose mode)',

        // Progress
        progressAnalyzing: 'Analyzing...',
        progressUploading: 'Uploading...',

        // Report
        reportTitle: '📊 Analysis Report',
        reportMarkdown: '📄 Markdown',
        reportHTML: '🌐 HTML',
        reportTrace: '🔍 Reasoning Trace',
        reportHideTrace: '❌ Hide Trace',

        // Trace
        traceTitle: '🧠 Reasoning Chain & Evidence',
        tracePipeline: '⚙️ Pipeline Execution Details',
        traceNoData: 'No reasoning trace recorded (requires verbose mode)',
        traceNoPipeline: 'No pipeline execution data',
        traceNoReasoning: 'No reasoning trace data',
        traceSuccess: 'Success',
        traceFailed: 'Failed',
        traceSkipped: 'Skipped',

        // Events
        eventsTitle: '📋 Analysis Process',
        eventsTotal: 'Events',
        eventsErrors: 'Errors',
        eventsWarnings: 'Warnings',
        eventsRetries: 'Retries',
        eventsDuration: 'Duration',

        // Report content labels (for buildReportMarkdown)
        rptTitle: 'Image Analysis Report',
        rptTaskId: 'Task ID',
        rptFilename: 'Filename',
        rptStatus: 'Status',
        rptCreatedAt: 'Created At',
        rptCompletedAt: 'Completed At',
        rptSceneDesc: 'Scene Description',
        rptSceneType: 'Scene Type',
        rptLocation: 'Location Guess',
        rptLocationLabel: 'Location',
        rptConfidence: 'Confidence',
        rptTime: 'Time Guess',
        rptTimePeriod: 'Time of Day',
        rptSeason: 'Season',
        rptDetectedText: 'Detected Text',
        rptKeyEvidence: 'Key Evidence',
        rptError: 'Error Info',

        // Pipeline stage names
        stagePreprocess: 'Image Preprocessing',
        stageOCR: 'OCR Text Recognition',
        stageVLM: 'VLM Scene Analysis',
        stageEntity: 'Entity Extraction',
        stageSearch: 'Web Verification',
        stageFusion: 'Evidence Fusion',
        stageReport: 'Report Generation',

        // Event name formatting
        evtStart: '▶️ Start',
        evtEnd: '✅ Done',
        evtFail: '❌ Failed',
        evtRetry: '🔄 Retry',
        evtOk: '✅ Success',
        evtTimeout: '⏰ Timeout',
        evtReceived: '📥 Received',
        evtCreated: '🆕 Created',
        evtConnect: '🔗 Connect',
        evtNode: '📦 Node',
        evtVLM: '👁️ VLM',
        evtPipeline: '⚙️ Pipeline',
        evtRequest: '🌐 Request',
        evtBackgroundTask: '🔄 Background Task',
        evtProgress: '📊 Progress',
        evtSSE: '📡 SSE',
        evtImageCompressed: '🖼️ Image Compressed',

        // Common
        unknown: 'Unknown',
        loading: 'Loading...',
        success: 'Analysis complete!',
        failed: 'Analysis failed',
        noReport: 'No report to download',

        // Reasoning strategies
        strategyRule: 'Rule Match',
        strategyLLM: 'LLM Reasoning',
        strategyUncertain: 'Uncertain',
        actionRuleMatch: 'Rule Match',
        actionLLMInference: 'LLM Reasoning',
    },
};

// 当前语言（默认中文）
let currentLang = localStorage.getItem('lang') || 'zh';

/**
 * 获取当前语言
 */
export function getLang() {
    return currentLang;
}

/**
 * 设置语言
 */
export function setLang(lang) {
    if (lang !== 'zh' && lang !== 'en') return;
    currentLang = lang;
    localStorage.setItem('lang', lang);
    applyI18n();
}

/**
 * 翻译函数
 */
export function t(key) {
    return I18N[currentLang]?.[key] ?? I18N.zh[key] ?? key;
}

/**
 * 将 i18n 应用到所有带 data-i18n 属性的元素
 */
export function applyI18n() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.dataset.i18n;
        const text = t(key);
        if (el.tagName === 'INPUT' && el.hasAttribute('placeholder')) {
            el.placeholder = text;
        } else {
            el.textContent = text;
        }
    });

    // 更新语言按钮的 active 状态
    document.querySelectorAll('.lang-btn').forEach(btn => {
        const btnLang = btn.dataset.lang;
        btn.classList.toggle('active', btnLang === currentLang);
    });

    // 更新 html lang 属性
    document.documentElement.lang = currentLang === 'en' ? 'en' : 'zh';
}

/**
 * 初始化 i18n
 */
export function initI18n() {
    applyI18n();
}

export default { I18N, getLang, setLang, t, applyI18n, initI18n };
