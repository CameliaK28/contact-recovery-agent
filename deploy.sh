#!/bin/bash
# Customer Contact Recovery Agent - GitHub推送脚本
# 运行此脚本将代码推送到GitHub，然后在Render上部署

echo "============================================"
echo "  Customer Contact Recovery Agent 部署助手"
echo "============================================"
echo ""
echo "此脚本将帮你把代码推送到GitHub仓库。"
echo "你需要在 https://github.com 注册账号后运行此脚本。"
echo ""

# 检查git
if ! command -v git &> /dev/null; then
    echo "错误：未找到 git。请先安装 Git。"
    exit 1
fi

# 提示输入GitHub用户名
read -p "请输入你的GitHub用户名: " GH_USERNAME

# 设置远程仓库
REPO_URL="https://github.com/${GH_USERNAME}/contact-recovery-agent.git"

echo ""
echo "将推送代码到: $REPO_URL"
echo ""

# 添加远程仓库
git remote remove origin 2>/dev/null  # 移除已有的origin（如果存在）
git remote add origin "$REPO_URL"

# 推送代码
echo "正在推送代码到GitHub..."
echo "（如果提示输入密码，请使用GitHub Personal Access Token）"
echo "（生成Token: GitHub → Settings → Developer settings → Personal access tokens → Generate new token）"
echo ""

git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================"
    echo "  ✅ 代码已成功推送到GitHub！"
    echo "============================================"
    echo ""
    echo "仓库地址: https://github.com/${GH_USERNAME}/contact-recovery-agent"
    echo ""
    echo "下一步：在Render上部署"
    echo "  1. 打开 https://dashboard.render.com 并登录"
    echo "  2. 点击 'New' → 'Web Service'"
    echo "  3. 选择 'Build and deploy from a Git repository'"
    echo "  4. 连接GitHub账号，选择 'contact-recovery-agent' 仓库"
    echo "  5. 配置信息已自动填写（render.yaml）"
    echo "  6. 点击 'Create Web Service'"
    echo ""
    echo "部署完成后，你会获得一个公网URL，例如："
    echo "  https://contact-recovery-agent.onrender.com"
    echo ""
    echo "把这个URL分享给任何人即可使用！"
else
    echo ""
    echo "推送失败。可能原因："
    echo "  1. GitHub仓库尚未创建（请先在GitHub网页上创建）"
    echo "  2. 认证失败（请使用Personal Access Token作为密码）"
    echo ""
    echo "请检查错误信息后重新运行此脚本。"
fi
