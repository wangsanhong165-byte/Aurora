# ADR：桌面会话边界

状态：接受。

继续使用现有 React Store，不增加全局状态依赖。保留现有 Transport 消息名称，在 `command`、`command_response` 和相关错误上增加可选 `request_id`，由 Promise broker 做确定性关联。页面只发送高层命令，不持有 WebSocket、AudioContext、录音器、Electron IPC 或 Cubism 参数。
