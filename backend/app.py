from flask import Flask
from flask_cors import CORS
from vpp_api import vpp_blueprint
from tasks import start_scheduler

# 🔹 KST 타임존 로깅을 위한 import
import logging
from pytz import timezone
from datetime import datetime

# 🔹 KST 타임존으로 시간 찍히게 하는 Formatter 정의
class KSTFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        kst = timezone("Asia/Seoul")
        dt = datetime.fromtimestamp(record.created, tz=kst)
        return dt.strftime('%Y-%m-%d %H:%M:%S')

# 🔹 werkzeug 로거에 적용
log = logging.getLogger('werkzeug')
for handler in log.handlers:
    handler.setFormatter(KSTFormatter('%(asctime)s - %(message)s'))

# Flask 앱 시작
app = Flask(__name__)
CORS(app)

app.register_blueprint(vpp_blueprint)
start_scheduler()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
