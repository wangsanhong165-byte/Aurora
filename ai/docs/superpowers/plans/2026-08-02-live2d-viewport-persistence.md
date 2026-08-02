# Live2D 位置与缩放持久化实现计划

> **面向 AI 代理的工作者：** 必须使用 executing-plans 技能逐任务执行本计划。

**目标：** 让用户拖动和缩放 Live2D 后，刷新页面、重载模型或切换模型时仍恢复该模型自己的视图状态。

**方案：** 复用前端已有的按模型 `localStorage` 持久化模式，保存归一化的 `x/y/scale`。加载优先级为用户保存值、模型默认 viewport、自动居中默认值。只改前端渲染视图状态，不新增第二套 Live2D 控制链。

**技术栈：** React、TypeScript、Live2D renderer、Node test runner。

### 任务 1：为视图状态持久化定义可测试的边界

**文件：**
- 创建：`frontend/src/character/live2d/viewport-persistence.ts`
- 创建：`frontend/src/character/live2d/viewport-persistence.test.ts`

- [ ] **步骤 1：编写失败测试**
  - 验证不同模型使用不同的存储键。
  - 验证写入并读取 `x/y/scale`。
  - 验证损坏 JSON、非有限数字和超出范围的值会回退到安全默认值。
  - 验证缺少保存值时返回空结果，让调用方使用模型默认配置。

- [ ] **步骤 2：运行测试确认先失败**
  - 运行：`node --test --experimental-strip-types frontend/src/character/live2d/viewport-persistence.test.ts`
  - 预期：失败，因为持久化模块尚不存在。

- [ ] **步骤 3：实现最小持久化模块**
  - 使用注入的最小 storage 接口，避免测试依赖浏览器环境。
  - 使用 `live2d_viewport_<modelName>` 作为按模型键。
  - 读取时只接受有限数字，并通过现有 `normalizeAvatarViewport` 限制范围。

- [ ] **步骤 4：运行测试确认通过**
  - 运行同一条测试命令。
  - 预期：全部通过。

### 任务 2：接入模型加载、拖动和缩放生命周期

**文件：**
- 修改：`frontend/src/character/CharacterView.tsx`
- 修改：`frontend/src/character/avatar-profile.test.ts`（如需覆盖默认 viewport 与用户覆盖优先级）

- [ ] **步骤 1：加载时恢复用户状态**
  - 修改 `applyModelViewport(modelName)`，先读取该模型的用户保存值。
  - 没有有效保存值时，继续使用 `__INITIAL_MODEL_INFO__.avatarProfiles[modelName].viewport`。
  - 通过现有 renderer API 一次性应用 `scale` 和 `x/y`。

- [ ] **步骤 2：交互结束时保存状态**
  - 在鼠标拖动结束时保存当前 `getViewTransform()`。
  - 在滚轮缩放后保存当前 `getViewTransform()`。
  - 在触控缩放结束时保存最终状态，避免每一帧写入。
  - 保存失败只忽略本地存储异常，不影响 Live2D 交互。

- [ ] **步骤 3：运行前端测试与类型检查**
  - 运行：`npm.cmd test -- --runInBand`
  - 运行：`npm.cmd run typecheck`
  - 预期：新增测试和现有测试全部通过。

### 任务 3：构建并进行浏览器端到端验收

**文件：**
- 不新增运行时代码文件。

- [ ] **步骤 1：构建前端**
  - 运行：`npm.cmd run build`
  - 预期：Vite 构建成功。

- [ ] **步骤 2：浏览器交互验收**
  - 在当前模型上拖动到明显偏离中心的位置并调整缩放。
  - 刷新页面，确认模型恢复同一位置和缩放比例。
  - 切换到另一个模型再切回，确认每个模型的视图状态彼此隔离。
  - 确认控制台无由本功能引入的错误。

- [ ] **步骤 3：完成前检查**
  - 运行：`git diff --check`。
  - 复核改动只涉及视图状态持久化及其测试，不提交或覆盖用户已有的其他改动。
