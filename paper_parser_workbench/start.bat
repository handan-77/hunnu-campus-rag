@echo off
chcp 65001 >nul
echo ========================================
echo   学术文献解析与报告生成系统
echo   启动脚本
echo ========================================
echo.

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

REM 检查依赖
echo [1/3] 检查并安装依赖...
pip install -r requirements.txt -q

echo [2/3] 启动Streamlit服务...
echo.
echo ========================================
echo   访问地址: http://localhost:8501
echo   按 Ctrl+C 停止服务
echo ========================================
echo.

REM 启动应用
streamlit run app.py --server.port 8501 --server.headless true

pause
