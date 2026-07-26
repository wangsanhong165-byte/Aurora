# App.tsx 职责审计

## 重构前事实

`App.tsx` 同时创建 WebSocket 适配器和音频播放器，注册连接、Runtime、TTS、ASR、角色、历史与附件事件，加载并保存设置，调用 Electron IPC，并持有历史、字幕、附件等视图状态。`InputBar` 另行创建录音器并直接上传音频；用户视图和开发者工作台直接发送管理命令并监听通用响应；标题栏直接访问 Electron preload API。

## 收敛结果

应用入口现只装配错误边界、Store 和桌面会话工作区。会话工作区是基础设施组合根；组件不再持有 WebSocket，录音资源已移出 `InputBar`，命令请求通过带 `request_id` 的确定性 Promise 通道完成。原始消息仍只有 `RuntimeClient` 一个解析入口，Live2D 继续只消费语义角色事件。

## 生产引用检查

- `App.tsx`：无 WebSocket、AudioContext、协议解析或 Electron IPC。
- `InputBar`：无 RuntimeAdapter、AudioRecorder 或音频上传。
- `CompanionWorkspace`：只接收视图状态和高层命令。
- `RuntimeClient`：唯一原始 Transport 消息解析入口。
- `AudioPlayer`：拥有队列、代际失效、停止及资源释放。

## App.tsx 最终职责

1. 装配顶层错误边界。
2. 装配现有 Store Provider。
3. 渲染 `DesktopSessionWorkspace`。
