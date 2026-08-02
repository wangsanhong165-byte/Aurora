# Companion UI 蓝灰工作台视觉重构实现计划

> **面向 AI 代理的工作者：** 按照本计划逐项实施；完成每项后运行对应的局部验证，最终进行类型检查、构建、测试和真实页面验收。不要改动计划范围之外的后端、协议或 Live2D 控制逻辑。

**目标：** 将 Companion 工作区调整为明亮一些的蓝灰色专业工作台，并统一工作区图标体系。

**架构：** 保留现有 `Layout -> CompanionWorkspace -> DrawerPanel/HistoryPanel/InputBar` 结构，只抽取和统一视觉 token、图标和状态样式。

**技术栈：** React、TypeScript、Vite、`lucide-react`、现有 CSS token。

### 任务 1：统一视觉 token

**文件：**

- 修改：`frontend/src/styles/index.css`
- 修改：`frontend/src/core/theme.ts`

- [x] 建立蓝灰背景、面板、浮层、边框、主文字、次文字和强调色的单一映射。
- [x] 提高表面之间的明度差，减少无意义的边框和阴影。
- [x] 统一间距、圆角、焦点环和滚动条颜色。
- [x] 保留现有状态语义：连接、警告、危险、思考和说话状态。

### 任务 2：统一导航和抽屉图标

**文件：**

- 修改：`frontend/src/ui/Layout.tsx`
- 修改：`frontend/src/ui/CompanionWorkspace.tsx`
- 修改：`frontend/src/ui/DrawerPanel.tsx`

- [x] 为导航图标和抽屉控制建立统一的尺寸、线宽、居中和状态样式。
- [x] 使用 Lucide 图标替换抽屉字符箭头。
- [x] 保持导航选择、键盘焦点、aria-label 和抽屉宽度调整行为不变。

### 任务 3：重构聊天记录面板

**文件：**

- 修改：`frontend/src/conversation/HistoryPanel.tsx`

- [x] 用统一的 CSS 类和主题 token 替代分散的内联颜色样式。
- [x] 用 `Plus`、`X` 和 `MessageSquare` 统一新建、删除和空状态图标。
- [x] 统一历史条目的默认、悬停、激活、加载和空状态。
- [x] 保持加载、加载历史、删除历史和新建历史回调不变。

### 任务 4：重构底部聊天 dock 和输入区

**文件：**

- 修改：`frontend/src/styles/index.css`
- 修改：`frontend/src/ui/InputBar.tsx`

- [x] 统一 dock 的表面、透明度、边界、阴影和消息气泡层级。
- [x] 让输入区更轻、更有空气，保持角色主体可见。
- [x] 统一发送、录音、停止、禁用、悬停和键盘焦点状态。
- [x] 清理重复的 composer CSS 规则，避免同一控件被两套样式覆盖。

### 任务 5：状态和 fallback 颜色同步

**文件：**

- 视需要修改：`frontend/src/character/CharacterView.tsx`
- 视需要修改：`frontend/src/ui/ErrorBoundary.tsx`

- [x] 仅同步工作区可见的 fallback/error 颜色到新 token。
- [x] 不修改 Live2D 渲染、参数控制、模型加载和动作逻辑。

### 任务 6：验证

- [x] 运行：`npm.cmd run typecheck`
- [x] 运行：`npm.cmd run build`
- [x] 运行：`npm.cmd test`
- [x] 在真实 browser 页面检查常规窗口；当前浏览器未执行窄窗口覆盖测试。
- [x] 检查导航激活、抽屉展开/收起、历史面板可见状态、输入区和焦点状态；未触发会改变用户数据的历史新建/删除操作。
- [x] 检查 `git diff`，确保只包含本次前端视觉范围和批准的文档。
