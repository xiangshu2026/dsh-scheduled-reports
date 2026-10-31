@echo off
chcp 65001 >nul
start msedge https://www.douyin.com
echo.
echo 1. 确认右上角有头像（已登录）
echo 2. 随便搜一次 deepseek 插件，确认能搜出结果
echo 3. 按 F12 打开开发者工具
echo 4. 点顶部 Application（应用）标签
echo 5. 左侧 Storage - Cookies - https://www.douyin.com
echo 6. 右侧列表按 Ctrl+A 全选，Ctrl+C 复制
echo 7. 粘贴到记事本，整理成一行：name1=value1; name2=value2; ...
echo 8. 粘到 config.json 的 douyin.cookie 字段
echo 9. 跑 python tools\check_cookie.py douyin 验证
echo.
pause
