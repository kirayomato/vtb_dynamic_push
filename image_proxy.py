import requests
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from query_weibo import get_headers
from datetime import datetime
import threading
from typing import List, Dict, Any

app = FastAPI()

# 设置模板目录
templates = Jinja2Templates(directory="templates")

# 请求记录存储
request_logs: List[Dict[str, Any]] = []
log_lock = threading.Lock()
url_set = set()  # 用于记录已处理的URL

# 最大记录数
MAX_LOGS = 100


def add_log(url: str, status: str = "success", error: str = None):
    """添加请求记录 - 相同链接只记录第一次"""
    with log_lock:
        # 如果URL已存在，不记录
        if url in url_set:
            return

        # 记录新URL
        url_set.add(url)

        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "url": url,
            "status": status,
            "error": error,
            "thumbnail": (url if status == "success" else None),
        }
        request_logs.insert(0, log_entry)

        # 限制记录数量
        if len(request_logs) > MAX_LOGS:
            removed = request_logs.pop()
            # 从集合中移除对应的URL
            if removed.get("url"):
                url_set.discard(removed["url"])


async def proxy_image(
    request: Request, url: str = Query(..., description="Target image URL")
):
    """代理图片的核心函数"""
    # 验证URL格式
    url = url.split("?", 1)[0]
    if not (
        url.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".flv"))
        and any(item in url for item in ("sina", "weibo"))
    ):
        raise HTTPException(status_code=400, detail="Invalid URL format")

    headers = get_headers("0")

    try:
        # 发送代理请求
        resp = requests.get(
            url,
            headers=headers,
            stream=True,
            timeout=30,
            allow_redirects=True,
        )
        resp.raise_for_status()

        # 记录成功日志
        add_log(url, "success")

        # 构建响应
        def iter_content():
            for chunk in resp.iter_content(chunk_size=8192):
                yield chunk

        response = StreamingResponse(
            iter_content(),
            status_code=resp.status_code,
            media_type=resp.headers.get("Content-Type", "application/octet-stream"),
        )

        # 复制关键头部
        for header in ["Cache-Control", "Expires", "ETag", "Content-Length"]:
            if header in resp.headers:
                response.headers[header] = resp.headers[header]

        return response

    except requests.exceptions.Timeout:
        add_log(url, "error", "Upstream request timeout")
        raise HTTPException(status_code=504, detail="Upstream request timeout")
    except requests.exceptions.RequestException as e:
        add_log(url, "error", f"Upstream error: {str(e)}")
        raise HTTPException(status_code=502, detail=f"Upstream error: {str(e)}")
    except Exception as e:
        add_log(url, "error", f"Internal server error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# 主页路由
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """主页 - 显示请求记录"""
    # 统计信息
    total = len(request_logs)
    success = sum(1 for log in request_logs if log["status"] == "success")
    failed = total - success

    return templates.TemplateResponse(
        "proxy.html",
        {
            "request": request,
            "logs": request_logs,
            "total": total,
            "success": success,
            "failed": failed,
        },
    )


@app.post("/clear")
async def clear_logs():
    """清空请求记录"""
    with log_lock:
        request_logs.clear()
        url_set.clear()
    return {"message": "Logs cleared successfully"}


@app.get("/api/logs")
async def get_logs():
    """获取请求记录的JSON数据"""
    with log_lock:
        # 统计信息
        total = len(request_logs)
        success = sum(1 for log in request_logs if log["status"] == "success")
        failed = total - success

        return {
            "logs": request_logs,
            "total": total,
            "success": success,
            "failed": failed,
        }


# 注册路由
@app.get("/proxy")
async def handle_proxy(
    request: Request, url: str = Query(..., description="Target image URL")
):
    return await proxy_image(request, url)


def image_proxy():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5001)


if __name__ == "__main__":
    image_proxy()
