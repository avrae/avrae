'''
Created on May 16, 2017

@author: andrew
'''

import json
import os

from flask import Flask, session, redirect, request, url_for, jsonify
from flask.templating import render_template
import markdown2
from requests_oauthlib.oauth2_session import OAuth2Session

import credentials
from utils.dataIO import DataIO


TESTING = True if os.environ.get("TESTING") else False

OAUTH2_CLIENT_ID = credentials.oauth2_client_id
OAUTH2_CLIENT_SECRET = credentials.oauth2_client_secret
OAUTH2_REDIRECT_URI = 'http://localhost:5000/callback' if TESTING else "https://avrae.io/callback"

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

@app.route('/logout')
def logout():
    session.pop('oauth2_token', None)
    session.pop('oauth2_state', None)
    return redirect(url_for(".home"))

# -----Dashboard----

@app.route('/dashboard')
def dashboard():
    if not 'oauth2_token' in session:
        session['original_page'] = ".dashboard"
        return redirect(url_for(".auth"))
    discord = make_session(token=session.get('oauth2_token'))
    resp = discord.get(API_BASE_URL + '/users/@me')
    if resp.status_code == 401:
        session['original_page'] = ".dashboard"
        return redirect(url_for(".auth"))
    user_info = resp.json()
    user_id = user_info.get('id')
    if user_info.get('avatar'):
        avatar_url = "https://cdn.discordapp.com/avatars/{}/{}.webp?size=1024".format(user_info.get('id'), user_info.get('avatar'))
    else:
        avatar_url = "/static/assets/AvraeSquare.jpg"
    characters = db.jget(user_id + '.characters', {})
    numChars = len(characters)
    numCustomizations = len(db.jget('cmd_aliases', {}).get(user_id, {})) + len(db.jget('damage_snippets', {}).get(user_id, {}))
    numCustomizations += sum(len(v) for v in db.jget('char_vars', {}).get(user_id, {}).values())
    return render_template('dashboard.html', username=user_info.get('username'),
                           discriminator=user_info.get('discriminator'),
                           avatar=avatar_url,
                           numChars=numChars,
                           numCustomizations=numCustomizations,
                           characters=characters)
    
# -----Character-----

@app.route('/character/<cid>')
def character(cid):
    if not 'oauth2_token' in session:
        session['original_page'] = ".dashboard"
        return redirect(url_for(".auth"))
    discord = make_session(token=session.get('oauth2_token'))
    resp = discord.get(API_BASE_URL + '/users/@me')
    if resp.status_code == 401:
        session['original_page'] = ".dashboard"
        return redirect(url_for(".auth"))
    user_info = resp.json()
    user_id = user_info.get('id')
    character = db.jget(user_id + '.characters', {}).get(cid)
    if character is None:
        return render_template('error.html', status=404, error="Character not found"), 404
    numAttacks = len(character.get("attacks", []))
    classLevels = []
    for cls, lvl in character.get('levels', {}).items():
        if not cls == "level":
            classLevels.append("{} {}".format(cls.split("Level")[0], lvl))
    
    heights = {}
    colors = {}
    for stat in ('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma'):
        heights[stat] = max(0, min(75, (int(character.get('stats', {}).get(stat, 0)) - 5) * (75/15)))
        hue = int(max(0, min(120, (int(character.get('stats', {}).get(stat, 0)) - 5) * (120/15))))
        colors[stat] = hue
        
    return render_template('character/view.html', character=character,
                           classLevels='/'.join(classLevels) or "Level " + str(character.get('levels', {}).get('level', 0)),
                           numAttacks=str(numAttacks) + (" Attack" if numAttacks==1 else " Attacks"),
                           heights=heights,
                           colors=colors,
                           renderedCharDesc=markdown2.markdown(character.get("stats", {}).get("description", "No description available.")),
                           rawCharInfo=json.dumps(character, sort_keys=True, indent=4)) #"<h1>This page is under construction!</h1><br><br>" + str(character)

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
    chars = db.jget(user_id + '.characters', {})
    cvars = {c.get('stats', {}).get('name', 'No name'): c.get('cvars', {}) for c in chars.values()}
    aliases = sorted([(k, v) for k, v in aliases.items()], key=lambda i: i[0])
    snippets = sorted([(k, v) for k, v in snippets.items()], key=lambda i: i[0])
    cvars = sorted([[k, v] for k, v in cvars.items()], key=lambda i: i[0])
    for cvar in cvars:
        cvar[1] = sorted([(k, v) for k, v in cvar[1].items()], key=lambda i: i[0])
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
            return "Snippet not found", 404
        snippets[user_id] = user_snippets
        db.jset('damage_snippets', snippets)
    else: # "cvar-cid"
        chars = db.jget(user_id + '.characters', {})
        cid = '-'.join(alias_type.split('-')[1:])
        char_cvars = chars.get(cid, {}).get('cvars', {})
        try:
            del char_cvars[alias_name]
        except KeyError:
            return "Cvar not found", 404
        chars[cid]['cvars'] = char_cvars
        db.jset(user_id + '.characters', chars)
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
        chars = db.jget(user_id + '.characters', {})
        cid = '-'.join(alias_type.split('-')[1:])
        char_cvars = chars.get(cid, {}).get('cvars', {})
        try:
            del char_cvars[old_alias_name]
        except KeyError:
            return "Cvar not found", 404
        char_cvars[new_alias_name] = new_alias_value
        chars[cid]['cvars'] = char_cvars
        db.jset(user_id + '.characters', chars)
    return "Alias edited"

@app.route('/aliases/new', methods=['POST'])
def aliases_new():
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
    new_alias_name = request.values.get('name')
    new_alias_value = request.values.get('value')
    if alias_type == 'alias':
        default_commands = db.jget('default_commands', [])
        if new_alias_name in default_commands:
            return "Alias is a built-in bot command", 409
        aliases = db.jget('cmd_aliases', {})
        user_aliases = aliases.get(user_id, {})
        user_aliases[new_alias_name] = new_alias_value
        aliases[user_id] = user_aliases
        db.jset('cmd_aliases', aliases)
    elif alias_type == 'snippet':
        snippets = db.jget('damage_snippets', {})
        user_snippets = snippets.get(user_id, {})
        user_snippets[new_alias_name] = new_alias_value
        snippets[user_id] = user_snippets
        db.jset('damage_snippets', snippets)
    else: # "cvar-cid"
        chars = db.jget(user_id + '.characters', {})
        cid = '-'.join(alias_type.split('-')[1:])
        if new_alias_name in chars.get(cid, {}).get("stat_cvars", {}):
            return "Cvar is a built-in variable", 409
        char_cvars = chars.get(cid, {}).get('cvars', {})
        char_cvars[new_alias_name] = new_alias_value
        chars[cid]['cvars'] = char_cvars
        db.jset(user_id + '.characters', chars)
    return "Alias created"

# -----Tests-----

@app.route('/test/test')
def test_test():
    if not 'oauth2_token' in session:
        session['original_page'] = ".test_test"
        return redirect(url_for(".auth"))
    discord = make_session(token=session.get('oauth2_token'))
    resp = discord.get(API_BASE_URL + '/users/@me')
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
