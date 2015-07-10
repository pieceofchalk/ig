from flask.ext.wtf import Form
from wtforms import SubmitField, IntegerField, TextField
from wtforms.validators import Required

CSRF_ENABLED = True
SECRET_KEY = 'you-will-never-guess'


class RunJobForm(Form):
    # recent_media_limit=100, recent_media_drange=1, user_media_limit=100
    hotel = TextField('hotel', validators=[Required()])
    recent_media_limit = IntegerField('recent_media_limit', default="100")
    recent_media_drange = IntegerField('recent_media_drange', default="1")
    user_media_limit = IntegerField('user_media_limit', default="100")
    submit = SubmitField('Run')
