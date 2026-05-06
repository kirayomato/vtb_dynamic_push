import json
import re
import io
from collections import deque
from datetime import datetime
from dataclasses import dataclass, asdict
from fastapi import FastAPI, Request, Body
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 配置
LEVEL_COLORS = {
    "ERROR": "#FF0000",
    "WARNING": "#FFFF00",
    "DEBUG": "#80FFFF",
    "INFO": "#FFFFFF",
}
ANSI_COLORS = {
    30: "#000000",
    31: "#FF0000",
    32: "#00FF00",
    33: "#FFFF00",
    34: "#0000FF",
    35: "#FF00FF",
    36: "#00FFFF",
    37: "#FFFFFF",
    90: "#808080",
    91: "#FF8080",
    92: "#80FF80",
    93: "#FFFF80",
    94: "#8080FF",
    95: "#FF80FF",
    96: "#80FFFF",
    97: "#FFFFFF",
}
ANSI_RE = re.compile(r"\x1b\[([0-9;]+)m")
URL_RE = re.compile(r"url: (https?://\S+)")


@dataclass
class LogEntry:
    id: int
    timestamp: str
    message: str
    color: str
    level: str
    urls: list[str] | None
    raw: str


class LogStore:
    def __init__(self, max_size=1000):
        self.logs = deque(maxlen=max_size)
        self.id = 0
        self.last_hash = None

    def add(self, text: str):
        text = text.strip()
        if not text or hash(text) == self.last_hash:
            return
        self.last_hash = hash(text)
        text = text.split("|")
        # 解析级别和颜色
        level, color = "INFO", LEVEL_COLORS["INFO"]
        for lvl, clr in LEVEL_COLORS.items():
            if lvl in text[3]:
                level, color = lvl, clr
                break

        # 处理ANSI转义
        def replace_ansi(m):
            nonlocal color
            code = int(m.group(1).split(";")[0])
            color = ANSI_COLORS.get(code, color)
            return ""

        text[4] = ANSI_RE.sub(replace_ansi, text[4])
        message = "|".join(text[:3] + [text[4]])
        # 提取URL
        urls = [match.group(1) for match in URL_RE.finditer(text[4])]

        self.logs.append(
            asdict(
                LogEntry(
                    id=self.id,
                    timestamp=datetime.now().isoformat(),
                    message=message,
                    color=color,
                    level=level,
                    urls=urls if urls else None,
                    raw=text,
                )
            )
        )
        self.id += 1

    def get_since(self, since_id: int, limit: int = 25) -> list:
        """获取指定ID之后的新日志"""
        return [log for log in reversed(self.logs) if log["id"] > since_id][:limit][
            ::-1
        ]

    def get_latest(self, limit: int = 25) -> list:
        """获取最新日志"""
        return list(self.logs)[-limit:][::-1]

    def get_history(
        self, before_id: int | None, limit: int = 25
    ) -> tuple[list, int | None, bool]:
        """获取历史日志，返回 (日志列表, 最旧ID, 是否还有更多)"""
        logs_list = list(self.logs)

        if before_id is None:
            result = logs_list[-limit:][::-1]
        else:
            idx = next(
                (i for i, log in enumerate(logs_list) if log["id"] == before_id), None
            )
            result = logs_list[max(0, idx - limit) : idx][::-1] if idx else []

        oldest_id = result[-1]["id"] if result else None
        has_more = len(result) == limit and oldest_id and oldest_id > 0
        return result, oldest_id, has_more


log_store = LogStore()


class LogCapture(io.StringIO):
    def write(self, s):
        log_store.add(s)
        return super().write(s)


output_stream = LogCapture()


# 路由
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/logs")
async def get_logs(since_id: int = 0, limit: int = 100):
    logs = log_store.get_since(since_id, limit)
    return {"logs": logs, "latest_id": log_store.id - 1, "has_more": len(logs) == limit}


@app.get("/logs/latest")
async def get_latest(limit: int = 100):
    return {"logs": log_store.get_latest(limit), "total": len(log_store.logs)}


@app.get("/logs/history")
async def get_history(before_id: int = None, limit: int = 50):
    logs, oldest_id, has_more = log_store.get_history(before_id, limit)
    return {
        "logs": logs,
        "oldest_id": oldest_id,
        "has_more": has_more,
        "total_loaded": len(logs),
    }


@app.post("/add_log")
async def add_log(content: str = Body(..., media_type="text/plain")):
    """添加日志用于测试"""
    try:
        log_store.add(content)
        return {"message": "日志添加成功", "id": log_store.id - 1}
    except Exception as e:
        return {"error": f"添加日志失败: {e}"}


@app.post("/add_log_raw")
async def add_log_raw(content: str = Body(..., media_type="text/plain")):
    """添加日志用于测试"""
    try:
        log_store.logs.append(
            asdict(
                LogEntry(
                    id=log_store.id,
                    timestamp=datetime.now().isoformat(),
                    message=content,
                    color="#80FFFF",
                    level="DEBUG",
                    urls=None,
                    raw=content,
                )
            )
        )
        log_store.id += 1
        return {"message": "日志添加成功", "id": log_store.id - 1}
    except Exception as e:
        return {"error": f"添加日志失败: {e}"}


@app.post("/write-{file_type}")
async def write_cookies(
    file_type: str, content: str = Body(..., media_type="text/plain")
):
    filename = {"weibo": "WeiboCookies.json", "bili": "BiliCookies.json"}.get(file_type)
    if not filename:
        return {"error": "无效的类型"}
    try:
        json.loads(content)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return {"message": "保存成功"}
    except json.JSONDecodeError:
        return {"error": "无效JSON格式"}
    except Exception as e:
        return {"error": f"保存失败: {e}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
