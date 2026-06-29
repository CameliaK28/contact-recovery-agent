# Customer Contact Recovery Agent - 部署指南

## 方案一：Render 云端部署（推荐，永久免费）

### 前提条件
- GitHub 账号（免费注册：https://github.com/signup）
- Render 账号（免费注册：https://dashboard.render.com/register）

### 步骤

#### 第1步：创建 GitHub 仓库
1. 登录 GitHub
2. 点击右上角 "+" → "New repository"
3. 仓库名：`contact-recovery-agent`
4. 选择 **Public**（公开）
5. 不要勾选 "Add a README file"
6. 点击 "Create repository"

#### 第2步：推送代码到 GitHub
在本地项目目录打开终端（Git Bash 或 CMD），运行：

```bash
cd C:\Users\15844\WorkBuddy\2026-06-25-21-43-14

# 添加远程仓库（替换 YOUR_USERNAME 为你的 GitHub 用户名）
git remote add origin https://github.com/YOUR_USERNAME/contact-recovery-agent.git

# 推送代码
git push -u origin main
```

如果提示输入账号密码，使用 GitHub Personal Access Token（PAT）：
1. 在 GitHub → Settings → Developer settings → Personal access tokens → Generate new token
2. 勾选 "repo" 权限
3. 生成后用 token 作为密码

#### 第3步：在 Render 上创建 Web Service
1. 登录 https://dashboard.render.com
2. 点击 "New" → "Web Service"
3. 选择 "Build and deploy from a Git repository"
4. 连接你的 GitHub 账号，选择 `contact-recovery-agent` 仓库
5. 配置：
   - **Name**: `contact-recovery-agent`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free
6. 点击 "Create Web Service"

#### 第4步：等待部署完成
- Render 会自动构建和部署
- 首次部署约需 3-5 分钟
- 部署完成后，你会获得一个公网 URL，例如：
  `https://contact-recovery-agent.onrender.com`

#### 第5步：分享给其他人
将上述 URL 发给任何人即可使用！

---

## 方案二：Render 蓝图部署（更快捷）

项目已包含 `render.yaml` 配置文件，可以直接使用 Render Blueprint：

1. 登录 https://dashboard.render.com
2. 点击 "New" → "Web Service"
3. 选择 "Build and deploy from a Git repository"
4. 连接 GitHub 并选择仓库后，Render 会自动识别 `render.yaml` 并配置好所有参数
5. 点击 "Apply" 即可

---

## 注意事项

### Render Free Plan 限制
- 应用在15分钟无请求后会休眠
- 休眠后首次请求需要约30秒唤醒
- 每月750小时免费运行时间
- 不影响正常使用，只是首次打开稍慢

### 搜索速度
- 云端搜索速度可能与本地略有差异（取决于网络环境）
- DuckDuckGo API 在某些地区可能需要更多时间

### 更新代码
当你修改了本地代码后：
```bash
cd C:\Users\15844\WorkBuddy\2026-06-25-21-43-14
git add .
git commit -m "描述你的改动"
git push
```
Render 会自动检测到推送并重新部署。

---

## 方案三：其他可选平台

| 平台 | 免费Tier | 特点 |
|------|----------|------|
| Railway | $5/月免费额度 | 部署更快，界面友好 |
| Fly.io | 3个共享CPU VM免费 | 需要Docker，命令行部署 |
| PythonAnywhere | 1个免费Web App | 仅支持Python，但限制较多 |
| Koyeb | 1个免费Web Service | 界面简洁，支持自动部署 |
