import re
import io
from fastapi import FastAPI, Request, Depends, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sys import exit

app = FastAPI()

# 设置模板路径
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
# 存储日志数据的列表
log_data = []
updated = True


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/logs", response_class=JSONResponse)
async def get_logs():
    # 返回所有日志数据
    global updated
    if updated:
        update = True
    else:
        update = False
    updated = False
    return update, log_data


@app.post("/write-file", response_class=JSONResponse)
async def write_file(content: str = Body(..., media_type="text/plain")):
    with open("WeiboCookies.json", "w") as file:  # 使用 "a" 模式追加内容
        file.write(content + "\n")
    return {"message": "Content written successfully"}

# ANSI 转义码和 HTML 颜色对照
ansi_to_html_colors = {
    30: "#000000",  # 黑色
    31: "#FF0000",  # 红色
    32: "#00FF00",  # 绿色
    33: "#FFFF00",  # 黄色
    34: "#0000FF",  # 蓝色
    35: "#FF00FF",  # 洋红
    36: "#00FFFF",  # 青色
    37: "#FFFFFF",  # 白色
    90: "#808080",  # 亮黑色（灰色）
    91: "#FF8080",  # 亮红色
    92: "#80FF80",  # 亮绿色
    93: "#FFFF80",  # 亮黄色
    94: "#8080FF",  # 亮蓝色
    95: "#FF80FF",  # 亮洋红
    96: "#80FFFF",  # 亮青色
    97: "#FFFFFF"   # 亮白色
}

# 解析 ANSI 转义序列的正则表达式
ansi_escape = re.compile(r'\x1b\[(?P<code>[0-9;]+)m')

# 将 ANSI 转义码转换为 HTML span 标签


def ansi_code_to_html(text):
    match = ansi_escape.match(text)
    if match is not None:
        codes = match.group('code').split(';')
        code = int(codes[0])
        return ansi_to_html_colors[code]
    else:
        return None


class OutputList(io.StringIO):
    def __init__(self):
        super().__init__()
        self.output_list = log_data

    def write(self, s):
        log = {}
        t = s.split()
        color = ansi_code_to_html(t[6][:5])
        if color:
            log['color'] = color
            t[6] = t[6][5:]
            log['msg'] = ' '.join(t)[:-4]
        else:
            log['color'] = '#FFFFFF'
            log['msg'] = ' '.join(t)
        self.output_list.append(log)
        super().write(s)
        global updated
        updated = True
