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
OAUTH2_REDIRECT_URI = 'http://localhost:8000/callback' if TESTING else "https://www.avraebot.com/callback"

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


def make_session(token=None, state=None, scope=None):
    return OAuth2Session(
        client_id=OAUTH2_CLIENT_ID,
        token=token,
        state=state,
        scope=scope,
        redirect_uri=OAUTH2_REDIRECT_URI,
        auto_refresh_kwargs={
            'client_id': OAUTH2_CLIENT_ID,
            'client_secret': OAUTH2_CLIENT_SECRET,
        },
        auto_refresh_url=TOKEN_URL,
        token_updater=token_updater)

@app.route('/callback')
def callback():
    if request.values.get('error'):
        return request.values['error']
    discord = make_session(state=session.get('oauth2_state'))
    token = discord.fetch_token(
        TOKEN_URL,
        client_secret=OAUTH2_CLIENT_SECRET,
        authorization_response=request.url)
    session['oauth2_token'] = token
    original_page = session.pop("original_page", ".home")
    return redirect(url_for(original_page))

@app.route('/auth')
def auth():
    scope = request.args.get(
        'scope',
        'identify')
    discord = make_session(scope=scope.split(' '))
    authorization_url, state = discord.authorization_url(AUTHORIZATION_BASE_URL)
    session['oauth2_state'] = state
    return redirect(authorization_url)

# -----Web Alias Things-----

@app.route('/aliases/list')
def aliases_list():
    if not 'oauth2_token' in session:
        session['original_page'] = ".aliases_list"
        return redirect(url_for(".auth"))
    discord = make_session(token=session.get('oauth2_token'))
    resp = discord.get(API_BASE_URL + '/users/@me')
    if resp.status_code == 401:
        session['original_page'] = ".aliases_list"
        return redirect(url_for(".auth"))
    user_id = resp.json().get('id')
    aliases = db.jget('cmd_aliases', {}).get(user_id, {})
    snippets = db.jget('damage_snippets', {}).get(user_id, {})
    cvars = db.jget('char_vars', {}).get(user_id, {})
    aliases = sorted([(k, v) for k, v in aliases.items()], key=lambda i: i[0])
    snippets = sorted([(k, v) for k, v in snippets.items()], key=lambda i: i[0])
    cvars = sorted([[k, v] for k, v in cvars.items()], key=lambda i: i[0])
    for cvar in cvars:
        cvar[1] = sorted([(k, v) for k, v in cvar[1].items()], key=lambda i: i[0])
    chars = db.jget(user_id + ".characters", {})
    return render_template('aliases/list.html', aliases=aliases, snippets=snippets, cvars=cvars, chars=chars)

@app.route('/aliases/delete', methods=['POST'])
def aliases_delete():
    if not 'oauth2_token' in session:
        session['original_page'] = ".aliases_list"
        return redirect(url_for(".auth"))
    discord = make_session(token=session.get('oauth2_token'))
    resp = discord.get(API_BASE_URL + '/users/@me')
    if resp.status_code == 401:
        session['original_page'] = ".aliases_list"
        return redirect(url_for(".auth"))
    user_id = resp.json().get('id')
    alias_type = request.values.get('type')
    alias_name = request.values.get('name')
    if alias_type == 'alias':
        aliases = db.jget('cmd_aliases', {})
        user_aliases = aliases.get(user_id, {})
        try:
            del user_aliases[alias_name]
        except KeyError:
            return "Alias not found", 404
        aliases[user_id] = user_aliases
        db.jset('cmd_aliases', aliases)
    elif alias_type == 'snippet':
        snippets = db.jget('damage_snippets', {})
        user_snippets = snippets.get(user_id, {})
        try:
            del user_snippets[alias_name]
        except KeyError:
            return "Alias not found", 404
        snippets[user_id] = user_snippets
        db.jset('damage_snippets', snippets)
    else: # "cvar-cid"
        cvars = db.jget('char_vars', {})
        cid = '-'.join(alias_type.split('-')[1:])
        char_cvars = cvars.get(user_id, {}).get(cid, {})
        try:
            del char_cvars[alias_name]
        except KeyError:
            return "Alias not found", 404
        cvars[user_id][cid] = char_cvars
        db.jset('char_vars', cvars)
    return "Alias deleted"

@app.route('/aliases/edit', methods=['POST'])
def aliases_edit():
    if not 'oauth2_token' in session:
        session['original_page'] = ".aliases_list"
        return redirect(url_for(".auth"))
    discord = make_session(token=session.get('oauth2_token'))
    resp = discord.get(API_BASE_URL + '/users/@me')
    if resp.status_code == 401:
        session['original_page'] = ".aliases_list"
        return redirect(url_for(".auth"))
    user_id = resp.json().get('id')
    alias_type = request.values.get('type')
    old_alias_name = request.values.get('target')
    new_alias_name = request.values.get('name')
    new_alias_value = request.values.get('value')
    if alias_type == 'alias':
        aliases = db.jget('cmd_aliases', {})
        user_aliases = aliases.get(user_id, {})
        try:
            del user_aliases[old_alias_name]
        except KeyError:
            return "Alias not found", 404
        user_aliases[new_alias_name] = new_alias_value
        aliases[user_id] = user_aliases
        db.jset('cmd_aliases', aliases)
    elif alias_type == 'snippet':
        snippets = db.jget('damage_snippets', {})
        user_snippets = snippets.get(user_id, {})
        try:
            del user_snippets[old_alias_name]
        except KeyError:
            return "Alias not found", 404
        user_snippets[new_alias_name] = new_alias_value
        snippets[user_id] = user_snippets
        db.jset('damage_snippets', snippets)
    else: # "cvar-cid"
        cvars = db.jget('char_vars', {})
        cid = '-'.join(alias_type.split('-')[1:])
        char_cvars = cvars.get(user_id, {}).get(cid, {})
        try:
            del char_cvars[old_alias_name]
        except KeyError:
            return "Alias not found", 404
        char_cvars[new_alias_name] = new_alias_value
        cvars[user_id][cid] = char_cvars
        db.jset('char_vars', cvars)
    return "Alias edited"

# -----Tests-----

@app.route('/test/test')
def test_test():
    if not 'oauth2_token' in session:
        session['original_page'] = ".test_test"
        return redirect(url_for(".auth"))
    discord = make_session(token=session.get('oauth2_token'))
    resp = discord.get(API_BASE_URL + '/users/@me')
    print(resp.status_code)
    if resp.status_code == 401:
        session['original_page'] = ".test_test"
        return redirect(url_for(".auth"))
    else:
        return jsonify(resp.json())
    
@app.route('/test/testclear')
def test_testclear():
    session.pop('oauth2_token', None)
    session.pop('oauth2_state', None)
    return "Session cleared!"

# -----Misc Handlers-----

# @app.after_request
# def add_header(response):
#     """
#     Add headers to both force latest IE rendering engine or Chrome Frame,
#     and also to cache the rendered page for 10 minutes.
#     """
#     response.headers['X-UA-Compatible'] = 'IE=Edge,chrome=1'
#     response.headers['Cache-Control'] = 'public, max-age=600'
#     return response


@app.errorhandler(404)
def page_not_found(error):
    """Custom 404 page."""
    return render_template('error.html', status=404, error="Page not Found"), 404

@app.errorhandler(403)
def forbidden(error):
    """Custom 403 page."""
    return render_template('error.html', status=403, error="Forbidden"), 403
