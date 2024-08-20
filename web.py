import re
from flask import Flask, render_template, jsonify
import io

app = Flask(__name__)
log_data = []


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/logs')
def get_logs():
    # 返回所有日志数据
    return jsonify(log_data)


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
        return "#000000"


class OutputList(io.StringIO):
    def __init__(self):
        super().__init__()
        self.output_list = log_data

    def write(self, s):
        log = {}
        t = s.split()
        log['color'] = ansi_code_to_html(t[6][:5])
        t[6] = t[6][5:-4]
        log['msg'] = ' '.join(t)
        self.output_list.append(log)
        super().write(s)
