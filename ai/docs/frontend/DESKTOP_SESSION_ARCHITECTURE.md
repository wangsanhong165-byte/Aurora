# Desktop Session Architecture

桌面会话层位于 React 页面和 Runtime/浏览器/Electron 基础设施之间。依赖方向为 UI → 高层会话命令 → RuntimeAdapter/CommandBroker；入站消息由 RuntimeClient 唯一解析，再投影为 Store 和角色语义事件。

`DesktopSessionWorkspace` 是组合根，不是新的业务上帝对象。连接与协议仍在 runtime 模块；确定性管理请求由 `CommandBroker` 管理；音频播放器和录音器由会话生命周期创建并销毁；Electron 能力由 `ElectronWindowBridge` 隔离；抽屉和聊天模式继续属于 Workspace UI。

销毁顺序为停止录音、使音频代际失效并关闭 AudioContext、拒绝待处理命令、断开 WebSocket、取消事件订阅和设置保存定时器。角色渲染、AvatarController 和 Cubism 参数混合边界不变。

该结构允许舞台和抽屉组件重排而不迁移连接、音频或协议逻辑。
