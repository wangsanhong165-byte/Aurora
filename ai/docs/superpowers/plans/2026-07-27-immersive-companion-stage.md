# 沉浸式陪伴舞台 UI 实现计划

> **执行方式：** 当前会话内联执行。步骤使用测试驱动开发，并在实际运行界面完成视觉验收。

**目标：** 将桌面端改为以 Live2D 和持续对话为核心的沉浸式舞台，同时重构抽屉交互、导航层级和拖动性能。

**架构：** `CompanionWorkspace` 负责主流程组合，`Layout` 只管理舞台、抽屉和导航；实时消息与输入固定在舞台，聊天抽屉只展示历史记录。抽屉选择和展开状态分离，宽度更新通过动画帧调度。

**技术栈：** React 18、TypeScript、CSS、Node.js Test Runner、Vite、Electron。

---

### 任务 1：重构工作区状态

**文件：**

- 修改：`frontend/src/ui/workspace-state.ts`
- 修改：`frontend/src/ui/workspace-state.test.ts`

- [ ] 编写失败测试：选择当前导航项保持抽屉展开，独立 `toggle` 操作控制展开状态。
- [ ] 运行 `npm.cmd test`，确认测试因现有切换逻辑失败。
- [ ] 将 `DrawerState` 拆为 `section`、`expanded` 和 `width`，实现 `select`、`toggle`、`resize`。
- [ ] 再次运行测试，确认状态行为通过。

### 任务 2：把实时聊天移到主舞台

**文件：**

- 修改：`frontend/src/ui/Layout.tsx`
- 修改：`frontend/src/ui/CompanionWorkspace.tsx`
- 修改：`frontend/src/conversation/HistoryPanel.tsx`

- [ ] 扩展布局接口，为舞台提供固定的 `conversation` 区域。
- [ ] 在舞台底部组合 `ChatView` 和 `InputBar`。
- [ ] 将聊天抽屉改为始终显示 `HistoryPanel`。
- [ ] 添加独立抽屉箭头按钮及对应无障碍状态。

### 任务 3：替换导航与视觉层级

**文件：**

- 创建：`frontend/src/ui/icons.tsx`
- 修改：`frontend/src/ui/CompanionWorkspace.tsx`
- 修改：`frontend/src/ui/TitleBar.tsx`
- 修改：`frontend/src/ui/StatusBar.tsx`
- 修改：`frontend/src/styles/index.css`

- [ ] 使用统一线性图标替换单字标记。
- [ ] 调整顺序为聊天记录、角色、语音、记忆、能力、设置，开发者入口固定底部。
- [ ] 删除标题栏品牌文字，仅保留窗口控制。
- [ ] 把状态栏改为舞台内低干扰状态点。
- [ ] 删除无功能边框，使用背景明度、空间和透明度建立层级。

### 任务 4：合并抽屉拖动并避免无效 Canvas 重建

**文件：**

- 创建：`frontend/src/ui/frame-coalescer.ts`
- 创建：`frontend/src/ui/frame-coalescer.test.ts`
- 修改：`frontend/src/ui/Layout.tsx`
- 修改：`frontend/src/character/CharacterView.tsx`
- 修改：`frontend/package.json`

- [ ] 编写失败测试：同一动画帧内多次宽度更新只提交最后一次。
- [ ] 实现可取消的动画帧合并器并接入抽屉拖动。
- [ ] Canvas CSS 或像素尺寸未变化时跳过重新赋值和 `resizeRenderer`。
- [ ] 运行全部前端测试和类型检查。

### 任务 5：构建与实机验收

**文件：**

- 验证：`frontend/dist`

- [ ] 运行 `npm.cmd test`，要求全部通过。
- [ ] 运行 `npm.cmd run typecheck`，要求退出码为 0。
- [ ] 运行 `npm.cmd run build`，要求退出码为 0。
- [ ] 在 1280 × 720 运行界面验证输入区、抽屉箭头、图标顺序、标题栏和错误状态。
- [ ] 验证切换与缩放期间无逐帧日志、无控制台错误、Live2D 不重新挂载。

