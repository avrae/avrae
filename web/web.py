'''
Created on May 16, 2017

@author: andrew
'''

import os

from flask import Flask, g, session, redirect, request, url_for, jsonify
from flask.templating import render_template
from requests_oauthlib.oauth2_session import OAuth2Session

import credentials
from utils.dataIO import DataIO


TESTING = True if os.environ.get("TESTING") else False

OAUTH2_CLIENT_ID = credentials.oauth2_client_id
OAUTH2_CLIENT_SECRET = credentials.oauth2_client_secret
OAUTH2_REDIRECT_URI = 'http://localhost:8000/' if TESTING else "https://www.avraebot.com/"

API_BASE_URL = os.environ.get('API_BASE_URL', 'https://discordapp.com/api')
AUTHORIZATION_BASE_URL = API_BASE_URL + '/oauth2/authorize'
TOKEN_URL = API_BASE_URL + '/oauth2/token'

app = Flask(__name__)
app.config['SECRET_KEY'] = OAUTH2_CLIENT_SECRET
db = DataIO(TESTING, credentials.test_database_url)

if 'http://' in OAUTH2_REDIRECT_URI:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'

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

def token_updater(token):
    session['oauth2_token'] = token


def make_session(token=None, state=None, scope=None, redirect_uri=OAUTH2_REDIRECT_URI):
    return OAuth2Session(
        client_id=OAUTH2_CLIENT_ID,
        token=token,
        state=state,
        scope=scope,
        redirect_uri=redirect_uri,
        auto_refresh_kwargs={
            'client_id': OAUTH2_CLIENT_ID,
            'client_secret': OAUTH2_CLIENT_SECRET,
        },
        auto_refresh_url=TOKEN_URL,
        token_updater=token_updater)

@app.route('/<redir>callback')
def callback(redir):
    if request.values.get('error'):
        return request.values['error']
    discord = make_session(state=session.get('oauth2_state'), redirect_uri=OAUTH2_REDIRECT_URI + "{}callback".format(redir))
    token = discord.fetch_token(
        TOKEN_URL,
        client_secret=OAUTH2_CLIENT_SECRET,
        authorization_response=request.url)
    session['oauth2_token'] = token
    return redirect(url_for('.{}'.format(redir)))

# -----Web Alias Test-----

@app.route('/aliases/auth')
def aliases_auth():
    scope = request.args.get(
        'scope',
        'identify')
    discord = make_session(scope=scope.split(' '), redirect_uri=OAUTH2_REDIRECT_URI + "aliases_listcallback")
    authorization_url, state = discord.authorization_url(AUTHORIZATION_BASE_URL)
    session['oauth2_state'] = state
    return redirect(authorization_url)

@app.route('/aliases/list')
def aliases_list():
    discord = make_session(token=session.get('oauth2_token'))
    resp = discord.get(API_BASE_URL + '/users/@me')
    if resp.status_code == 401:
        return redirect(url_for(".aliases_auth"))
    else:
        r = "Aliases:<br>"
        user_id = resp.json().get('id')
        aliases = db.jget('cmd_aliases', {}).get(user_id, {})
        snippets = db.jget('damage_snippets', {}).get(user_id, {})
        cvars = db.jget('char_vars', {}).get(user_id, {})
        r += ', '.join([name for name in aliases.keys()]) + '<br><br>Snippets:<br>' + \
             ', '.join([name for name in snippets.keys()]) + '<br><br>Cvars:<br>' + \
             ', '.join([name for name in cvars.keys()])
        return r

# -----Tests-----

@app.route('/test/oauth')
def test_oauth():
    scope = request.args.get(
        'scope',
        'identify')
    discord = make_session(scope=scope.split(' '), redirect_uri=OAUTH2_REDIRECT_URI + "test_testcallback")
    authorization_url, state = discord.authorization_url(AUTHORIZATION_BASE_URL)
    session['oauth2_state'] = state
    return redirect(authorization_url)

@app.route('/test/test')
def test_test():
    discord = make_session(token=session.get('oauth2_token'))
    resp = discord.get(API_BASE_URL + '/users/@me')
    if resp.status_code == 401:
        return redirect(url_for(".test_oauth"))
    else:
        return jsonify(resp.json())
    
@app.route('/test/testclear')
def test_testclear():
    session.pop('oauth2_token', None)
    session.pop('oauth2_state', None)
    return "Session cleared!"

# -----Misc Handlers-----

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
