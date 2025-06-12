# AI Finance

AI Finance 是一个简单的llm辅助个人财务助手项目，提供自然语言记账、收支分类管理与预算统计等功能。

## 项目结构

```
backend/  # Flask 后端服务 + sqlite 数据库
frontend/ # Vue 3 + Element Plus 前端应用
```

后端提供 `/api/chat` 等接口用于接收自然语言指令，前端包含聊天界面和账本管理页。

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

## 管理员功能

初始化数据库时会自动创建默认管理员账号 **admin/admin**。管理员登录后可以访问以
下接口：

- `GET /api/users`：查看所有普通用户；
- `PUT /api/users/<id>/password`：修改指定用户的密码；
- `POST /api/users/batch_delete`：批量删除用户，参数 `user_ids` 为用户 ID 数组。

前端提供了“🛠 用户管理”页面，管理员登录后可在侧边菜单中进入该页面，对用户列表进行查看、修改密码和批量删除操作。

## License

MIT
