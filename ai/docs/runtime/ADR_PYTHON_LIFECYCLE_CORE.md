# ADR：Python Lifecycle Core 与 Electron Supervisor

状态：接受。

选择 Python 作为唯一生命周期实现语言，因为服务本身、CLI 和进程诊断均以 Python 为中心。Electron 通过长驻 supervisor 的 JSON Lines 接口调用 Core，仅负责桌面进程适配和 UI 状态转发。拒绝在 Node 与 Python 中分别解释同一服务规则。
