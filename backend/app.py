from flask import Flask
from flask_cors import CORS
from vpp_api import vpp_blueprint
from tasks import start_scheduler

app = Flask(__name__)
CORS(app)

app.register_blueprint(vpp_blueprint)

start_scheduler()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
