# AI Finance

AI Finance 是一个简单的llm辅助个人财务助手项目，提供自然语言记账、收支分类管理与预算统计等功能。

## 项目结构

```
backend/  # Flask 后端服务 + sqlite 数据库
frontend/ # Vue 3 + Element Plus 前端应用
```

后端提供 `/chat` 等接口用于接收自然语言指令，前端包含聊天界面和账本管理页。

## 快速开始

环境要求：

- Python >= 3.10
- Node.js >= 18

在backend/中建立.env文件并设置api密钥

### Linux / macOS

执行以下命令可一键安装依赖并启动前后端：

```bash
chmod +x deploy.sh
./deploy.sh
```

### Windows

在 PowerShell 中运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
./deploy.ps1
```

前端默认运行在 [http://localhost:5173](http://localhost:5173)，后端接口运行在 [http://localhost:5000](http://localhost:5000)。

## 脚本说明

`deploy.sh`（Linux/macOS）与 `deploy.ps1`（Windows）会完成以下工作：

1. 在 `backend/venv` 下创建虚拟环境并安装后端依赖；
2. 安装前端依赖；
3. 分别启动Waitress WSGI 服务和 Vite 开发服务器，按下 `Ctrl+C` 即可结束。

## License

MIT
