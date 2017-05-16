'''
Created on May 16, 2017

@author: andrew
'''

from flask import Flask
from flask.templating import render_template


app = Flask(__name__)

@app.route('/')
def home():
    return app.send_static_file('index.html')

@app.route('/<route>')
def send_static_route(route):
    file_dot_text = route + '.html'
    return app.send_static_file(file_dot_text)

@app.route('/<file_name>.html')
def send_static(file_name):
    """Send your static html file."""
    file_dot_text = file_name + '.html'
    return app.send_static_file(file_dot_text)


@app.after_request
def add_header(response):
    """
    Add headers to both force latest IE rendering engine or Chrome Frame,
    and also to cache the rendered page for 10 minutes.
    """
    response.headers['X-UA-Compatible'] = 'IE=Edge,chrome=1'
    response.headers['Cache-Control'] = 'public, max-age=600'
    return response


@app.errorhandler(404)
def page_not_found(error):
    """Custom 404 page."""
    return render_template('error.html', status=404, error="Page not Found"), 404

@app.errorhandler(403)
def forbidden(error):
    """Custom 403 page."""
    return render_template('error.html', status=403, error="Forbidden"), 403
