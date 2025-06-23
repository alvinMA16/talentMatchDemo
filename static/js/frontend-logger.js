// Frontend Logger - 接收并显示后端日志
class FrontendLogger {
    constructor() {
        this.eventSource = null;
        this.isConnected = false;
        this.logBuffer = [];
        this.maxBufferSize = 500;
        this.showInConsole = true;
        this.showInUI = false;
        this.logContainer = null;
        
        // 初始化
        this.init();
    }
    
    init() {
        // 检查是否在开发环境中
        this.showInConsole = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
        
        // 如果在开发环境，自动连接日志流
        if (this.showInConsole) {
            this.connect();
            
            // 添加快捷键切换UI显示
            document.addEventListener('keydown', (e) => {
                // Ctrl + Shift + L 切换日志UI显示
                if (e.ctrlKey && e.shiftKey && e.key === 'L') {
                    e.preventDefault();
                    this.toggleLogUI();
                }
            });
            
            // 页面加载完成后显示提示
            window.addEventListener('load', () => {
                if (this.showInConsole) {
                    console.log('%c🚀 TalentMatch Frontend Logger', 'color: #28a745; font-weight: bold; font-size: 14px;');
                    console.log('%c📡 已连接后端日志流，实时显示系统运行状态', 'color: #17a2b8; font-size: 12px;');
                    console.log('%c⌨️  按 Ctrl+Shift+L 切换页面日志显示', 'color: #6c757d; font-size: 11px;');
                    console.log('%c' + '='.repeat(60), 'color: #dee2e6;');
                }
            });
        }
    }
    
    connect() {
        if (this.eventSource) {
            this.eventSource.close();
        }
        
        try {
            this.eventSource = new EventSource('/api/logs/stream');
            
            this.eventSource.onopen = () => {
                this.isConnected = true;
                if (this.showInConsole) {
                    console.log('%c✅ 日志流连接成功', 'color: #28a745; font-weight: bold;');
                }
            };
            
            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleLogMessage(data);
                } catch (e) {
                    console.error('解析日志消息失败:', e);
                }
            };
            
            this.eventSource.onerror = (error) => {
                this.isConnected = false;
                if (this.showInConsole) {
                    console.warn('%c⚠️ 日志流连接中断，尝试重连...', 'color: #ffc107; font-weight: bold;');
                }
                
                // 5秒后尝试重连
                setTimeout(() => {
                    if (!this.isConnected) {
                        this.connect();
                    }
                }, 5000);
            };
            
        } catch (error) {
            console.error('创建日志流连接失败:', error);
        }
    }
    
    handleLogMessage(data) {
        switch (data.type) {
            case 'init':
                if (this.showInConsole) {
                    console.log('%c🔗 ' + data.message, 'color: #17a2b8;');
                }
                break;
                
            case 'log':
                this.displayLog(data);
                break;
                
            case 'heartbeat':
                // 心跳消息，不需要显示
                break;
        }
    }
    
    displayLog(logData) {
        const { timestamp, message } = logData;
        
        // 添加到缓冲区
        this.logBuffer.push(logData);
        if (this.logBuffer.length > this.maxBufferSize) {
            this.logBuffer.shift();
        }
        
        // 在浏览器控制台显示
        if (this.showInConsole) {
            this.displayInConsole(message);
        }
        
        // 在页面UI中显示（如果启用）
        if (this.showInUI && this.logContainer) {
            this.displayInUI(logData);
        }
    }
    
    displayInConsole(message) {
        // 根据日志类型设置样式
        let style = 'color: #6c757d;';
        
        if (message.includes('🤖 MODEL REQUEST')) {
            style = 'color: #007bff; font-weight: bold;';
        } else if (message.includes('🤖 MODEL RESPONSE')) {
            if (message.includes('✅ SUCCESS')) {
                style = 'color: #28a745; font-weight: bold;';
            } else if (message.includes('❌ ERROR')) {
                style = 'color: #dc3545; font-weight: bold;';
            }
        } else if (message.includes('⚙️  PROCESSING')) {
            if (message.includes('🚀 START')) {
                style = 'color: #17a2b8;';
            } else if (message.includes('✅ COMPLETE')) {
                style = 'color: #28a745;';
            } else if (message.includes('❌ ERROR')) {
                style = 'color: #dc3545;';
            }
        } else if (message.includes('📦 BATCH')) {
            style = 'color: #6f42c1;';
        } else if (message.includes('🔒 DESENSITIZATION')) {
            style = 'color: #fd7e14;';
        }
        
        console.log(`%c${message}`, style);
    }
    
    displayInUI(logData) {
        if (!this.logContainer) return;
        
        const logEntry = document.createElement('div');
        logEntry.className = 'log-entry';
        
        // 根据日志类型添加CSS类
        if (logData.message.includes('❌ ERROR')) {
            logEntry.classList.add('log-error');
        } else if (logData.message.includes('✅ SUCCESS') || logData.message.includes('✅ COMPLETE')) {
            logEntry.classList.add('log-success');
        } else if (logData.message.includes('🚀 START')) {
            logEntry.classList.add('log-start');
        }
        
        logEntry.innerHTML = `
            <span class="log-timestamp">${logData.timestamp}</span>
            <span class="log-message">${this.escapeHtml(logData.message)}</span>
        `;
        
        this.logContainer.appendChild(logEntry);
        
        // 自动滚动到底部
        this.logContainer.scrollTop = this.logContainer.scrollHeight;
        
        // 限制显示的日志条数
        const logEntries = this.logContainer.querySelectorAll('.log-entry');
        if (logEntries.length > this.maxBufferSize) {
            logEntries[0].remove();
        }
    }
    
    toggleLogUI() {
        this.showInUI = !this.showInUI;
        
        if (this.showInUI) {
            this.createLogUI();
            console.log('%c📱 日志UI已开启', 'color: #28a745; font-weight: bold;');
        } else {
            this.removeLogUI();
            console.log('%c📱 日志UI已关闭', 'color: #6c757d;');
        }
    }
    
    createLogUI() {
        // 如果已存在则不重复创建
        if (document.getElementById('frontend-log-panel')) return;
        
        const logPanel = document.createElement('div');
        logPanel.id = 'frontend-log-panel';
        logPanel.innerHTML = `
            <div class="log-header">
                <span class="log-title">🔍 System Logs</span>
                <div class="log-controls">
                    <button class="log-btn log-btn-clear" onclick="frontendLogger.clearLogs()">清空</button>
                    <button class="log-btn log-btn-close" onclick="frontendLogger.toggleLogUI()">×</button>
                </div>
            </div>
            <div class="log-content" id="log-content-container">
                <!-- 日志内容将在这里显示 -->
            </div>
        `;
        
        document.body.appendChild(logPanel);
        this.logContainer = document.getElementById('log-content-container');
        
        // 添加样式
        this.addLogUIStyles();
        
        // 显示已缓存的日志
        this.logBuffer.forEach(logData => {
            this.displayInUI(logData);
        });
    }
    
    removeLogUI() {
        const logPanel = document.getElementById('frontend-log-panel');
        if (logPanel) {
            logPanel.remove();
            this.logContainer = null;
        }
    }
    
    clearLogs() {
        if (this.logContainer) {
            this.logContainer.innerHTML = '';
        }
        this.logBuffer = [];
        console.clear();
        console.log('%c🧹 日志已清空', 'color: #28a745;');
    }
    
    addLogUIStyles() {
        if (document.getElementById('frontend-logger-styles')) return;
        
        const style = document.createElement('style');
        style.id = 'frontend-logger-styles';
        style.textContent = `
            #frontend-log-panel {
                position: fixed;
                bottom: 20px;
                right: 20px;
                width: 600px;
                height: 400px;
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid #dee2e6;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                z-index: 9999;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 12px;
                backdrop-filter: blur(10px);
            }
            
            .log-header {
                background: #f8f9fa;
                padding: 8px 12px;
                border-bottom: 1px solid #dee2e6;
                border-radius: 8px 8px 0 0;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .log-title {
                font-weight: bold;
                color: #495057;
            }
            
            .log-controls {
                display: flex;
                gap: 8px;
            }
            
            .log-btn {
                background: none;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                cursor: pointer;
                transition: all 0.2s;
            }
            
            .log-btn:hover {
                background: #e9ecef;
            }
            
            .log-btn-close {
                font-size: 14px;
                font-weight: bold;
                color: #dc3545;
            }
            
            .log-content {
                height: calc(100% - 40px);
                overflow-y: auto;
                padding: 8px;
                background: #000;
                color: #fff;
                border-radius: 0 0 8px 8px;
            }
            
            .log-entry {
                margin-bottom: 2px;
                line-height: 1.3;
                word-wrap: break-word;
            }
            
            .log-timestamp {
                color: #6c757d;
                margin-right: 8px;
                font-size: 10px;
            }
            
            .log-message {
                color: #fff;
            }
            
            .log-entry.log-error .log-message {
                color: #ff6b6b;
            }
            
            .log-entry.log-success .log-message {
                color: #51cf66;
            }
            
            .log-entry.log-start .log-message {
                color: #74c0fc;
            }
            
            /* 滚动条样式 */
            .log-content::-webkit-scrollbar {
                width: 6px;
            }
            
            .log-content::-webkit-scrollbar-track {
                background: #2d3748;
            }
            
            .log-content::-webkit-scrollbar-thumb {
                background: #4a5568;
                border-radius: 3px;
            }
            
            .log-content::-webkit-scrollbar-thumb:hover {
                background: #68767e;
            }
        `;
        
        document.head.appendChild(style);
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
            this.isConnected = false;
        }
        this.removeLogUI();
    }
}

// 创建全局实例
const frontendLogger = new FrontendLogger();

// 页面卸载时断开连接
window.addEventListener('beforeunload', () => {
    frontendLogger.disconnect();
}); 