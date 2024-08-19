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


class OutputList(io.StringIO):
    def __init__(self):
        super().__init__()
        self.output_list = log_data

    def write(self, s):
        self.output_list.append(s)
        super().write(s)
