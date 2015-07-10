#!flask/bin/python
from ig_app import app

app.debug = True
app.run(threaded=True, host='::', port=8080)
