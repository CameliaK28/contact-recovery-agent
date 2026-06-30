# Customer Contact Recovery Agent - 部署指南

## 🎯 目标
让其他人通过一个公网URL（如 `https://xxx.onrender.com`）直接使用你的工具。

---

## 方案一：Render 云端部署（推荐 ✅）

**免费 | 永久 | 无需本地电脑运行**

### 你需要准备的（仅2个账号）
1. **GitHub账号** → https://github.com/signup （免费，2分钟注册）
2. **Render账号** → https://dashboard.render.com/register （免费，2分钟注册）

### 操作步骤（共4步）

---

#### 📌 第1步：在GitHub创建仓库

1. 登录 https://github.com
2. 点击右上角 **"+"** → **"New repository"**
3. 仓库名填写：`contact-recovery-agent`
4. 选择 **Public**（公开，必须选公开）
5. 其他都不勾选 → 点击 **"Create repository"**

---

#### 📌 第2步：推送代码到GitHub

打开 **Git Bash**（Windows自带），粘贴以下命令（把 `YOUR_USERNAME` 换成你的GitHub用户名）：

```bash
cd "C:/Users/15844/WorkBuddy/2026-06-25-21-43-14"
git remote add origin https://github.com/YOUR_USERNAME/contact-recovery-agent.git
git push -u origin main
```

如果弹出输入框，输入：
- **Username**：你的GitHub用户名
- **Password**：你的GitHub **Personal Access Token**（不是登录密码！）

🔑 **生成Token的方法**：
1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. 点击 "Generate new token"
3. 勾选 **"repo"** 权限
4. 点击 "Generate token" → 复制生成的token
5. 用这个token作为密码输入

---

#### 📌 第3步：在Render创建Web服务

1. 登录 https://dashboard.render.com
2. 点击 **"New +"** → **"Web Service"**
3. 选择 **"Build and deploy from a Git repository"**
4. 点击 **"Connect account"** → 授权连接你的GitHub
5. 选择 `contact-recovery-agent` 仓库
6. Render会自动检测到 `render.yaml` 配置文件，自动填好所有参数
7. 确认 **Plan** 选择 **"Free"**
8. 点击 **"Create Web Service"** ✅

---

#### 📌 第4步：分享URL

等待3-5分钟部署完成后，你会得到一个URL，例如：
```
https://contact-recovery-agent.onrender.com
```

**🎉 把这个URL发给任何人，他们就能直接使用了！**

---

## ⚠️ Render Free Plan 注意事项

| 项目 | 说明 |
|------|------|
| 休眠 | 15分钟无请求后自动休眠 |
| 唤醒 | 休眠后首次请求约30秒唤醒（稍慢） |
| 运行时间 | 每月750小时免费（足够24/7运行） |
| 影响 | 只是首次打开稍慢，不影响正常使用 |

---

## 🔄 更新代码（以后修改后重新部署）

```bash
cd "C:/Users/15844/WorkBuddy/2026-06-25-21-43-14"
git add .
git commit -m "描述你的改动"
git push
```
推送后Render自动检测并重新部署，约3分钟生效。

---

## 方案二：其他云平台（备选）

| 平台 | 免费额度 | 部署难度 | 特点 |
|------|----------|----------|------|
| **Railway** | $5/月免费 | 简单 | 界面友好，部署更快 |
| **Koyeb** | 1个免费实例 | 简单 | 支持自动部署 |
| **Fly.io** | 3个免费VM | 中等 | 需要Docker |
| **PythonAnywhere** | 1个免费Web App | 中等 | Python专用，限制多 |

Railway 部署方法类似Render，且界面更友好，但免费额度有限。

---

## 方案三：ngrok 临时隧道（仅短期演示）

如果你想**立刻**给别人看，可以用ngrok创建临时公网隧道：
1. 安装ngrok：https://ngrok.com/download
2. 注册ngrok账号（免费）
3. 运行：`ngrok http 8000`
4. 获得临时URL（如 `https://xxxx.ngrok.io`）

**缺点**：需要本地电脑保持运行，URL每次重启会变。仅适合短期演示。
