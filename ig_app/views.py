# -*- coding: utf-8 -*-

from ig_app import app, celery
from flask import Flask, request, jsonify, redirect, render_template, url_for, flash, send_from_directory
import json
from ig_app.forms import RunJobForm
from job import job
from os import listdir
from os.path import isfile, join
import string

valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)


def get_xls_files():
    path = join(app.static_folder, 'xls')
    files = [f for f in listdir(path) if isfile(join(path, f)) and '.xls' in f]
    # files = os.listdir(os.path.join(app.static_folder, 'xls'))
    return files


def get_resource_as_string(name, charset='utf-8'):
    with app.open_resource(name) as f:
        return f.read().decode(charset)


@app.route('/dwnld/<path:filename>', methods=['GET', 'POST'])
def dwnld(filename):
    return send_from_directory(join(app.static_folder, 'xls'), filename)

app.jinja_env.globals['get_resource_as_string'] = get_resource_as_string


def get_running_tasks():
    i = celery.control.inspect()
    active = i.active()
    return active


@app.route('/', methods=['POST', 'GET'])
def index():
    files = get_xls_files()
    app.logger.debug(repr(files))
    form = RunJobForm(request.form)
    runs = []
    for key, value in get_running_tasks().iteritems():
        runs += value
    if request.method == 'POST':
        if form.validate():
            result = {}
            result['iserror'] = False
            app.logger.debug(form.hotel.data)
            result['savedsuccess'] = True
            hotel = ''.join(c for c in form.hotel.data if c in valid_chars)
            task = job.s(hotel,
                         recent_media_limit=form.recent_media_limit.data,
                         recent_media_drange=form.recent_media_drange.data,
                         user_media_limit=form.user_media_limit.data).apply_async()
            app.logger.debug(task.id)
            flash('Run crawler task_id'.format(task.id))
            return redirect(url_for('index'))
        else:
            app.logger.debug('no post')
            return redirect(url_for('index'))

    if request.method == 'GET':
        return render_template("index.html",
                               title='IGCrawler',
                               form=form,
                               files=files,
                               runs=runs)


@app.route('/status/<task_id>')
def taskstatus(task_id):
    task = job.AsyncResult(task_id)
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'current': 0,
            'total': 1,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'current': task.info.get('current', 0),
            'total': task.info.get('total', 1),
            'status': task.info.get('status', '')
        }
        if 'result' in task.info:
            response['result'] = task.info['result']
    else:
        # something went wrong in the background job
        response = {
            'state': task.state,
            'current': 1,
            'total': 1,
            'status': str(task.info),  # this is the exception raised
        }
    return jsonify(response)


@app.route('/running')
def running():
    return jsonify(get_running_tasks())
