# Auto Mode 自动模式

## 配置

在 `.env` 文件中添加以下配置：

```env
# 启用自动模式
AUTO_MODE=true

# 通知邮箱（完成购物后发送邮件）
NOTIFICATION_EMAIL=liuqimath@gmail.com

# SMTP配置（用于发送邮件）
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
```

## 功能

1. **自动模式**：
   - 跳过所有用户确认（`input()`）
   - 跳过登录等待（使用已保存的cookies）
   - 完成后自动关闭浏览器
   - 发送邮件通知

2. **eerder-gekocht数据库**：
   - 自动保存eerder-gekocht数据到 `eerder_gekocht_products.json`
   - 作为数据库持久化保存
   - 下次运行时自动加载

3. **使用所有scrap结果**：
   - 合并bonus和eerder-gekocht的所有产品
   - 生成购物清单时使用所有产品

## 手动运行自动模式

```bash
# 方式1: 使用命令行参数
python main.py --auto

# 方式2: 使用环境变量
AUTO_MODE=true python main.py
```

## 邮件通知

完成购物后会自动发送邮件到配置的邮箱地址，包含：
- 完成时间
- 购物车链接
- 提示完成付款

