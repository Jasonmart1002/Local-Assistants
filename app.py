from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash
from markdown2 import markdown
from markupsafe import escape
import time
from flask_session import Session  # Make sure to install Flask-Session
from bs4 import BeautifulSoup
import traceback
from dotenv import load_dotenv
import os, sys

# Load environment variables from .env file
load_dotenv()

if os.environ.get("OPENAI_API_KEY") is None:
    print("Please set your OPENAI_API_KEY environment variable and try again.")
    sys.exit(1)

if os.environ.get("SECRET_KEY") is None:
    print("Please set your SECRET_KEY environment variable and try again.")
    sys.exit(1)

# Instantiate OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ASSISTANT_OPTIONS = [{'id': asst.id, 'name': asst.name} for asst in client.beta.assistants.list().data]
ASSISTANT_MAP = {item['id']: item['name'] for item in ASSISTANT_OPTIONS}


# User-specific assistant access
USER_ASSISTANT_ACCESS = {
    'user1': ['asst_wGwKpr1X9rTUixjM47mHknvu', 'asst_Zt6puzNDAL7XeEe2vRLGWTDp'],
    'user2': ['asst_wGwKpr1X9rTUixjM47mHknvu', 'asst_Zt6puzNDAL7XeEe2vRLGWTDp'],
}


# Predefined user dictionary
users = {
    'user1': generate_password_hash('password1'),
    'user2': generate_password_hash('password2'),
    # Add more users as needed
}


app = Flask(__name__)
# Check Flask-Session documentation for proper secret key settings
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
app.config['SESSION_TYPE']  = 'filesystem'
Session(app)

# Set the default selected assistant ID in session on app startup
app.config['DEFAULT_ASSISTANT_ID'] = ASSISTANT_OPTIONS[0]['id']


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_hash = users.get(username)
        if user_hash and check_password_hash(user_hash, password):
            session['username'] = username
            return redirect(url_for('assistant_options'))  # Redirect to assistant selection
        else:
            return 'Invalid username or password!'
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))



@app.route('/assistant_options', methods=['POST', 'GET'])
def assistant_options():
    try:
        default_assistant_id = app.config.get('DEFAULT_ASSISTANT_ID')
        username = session.get('username')

        available_assistants = [assistant for assistant in ASSISTANT_OPTIONS
                                if assistant['id'] in USER_ASSISTANT_ACCESS.get(username, [])]

        if request.method == 'GET':
            return render_template('assistant_options.html', assistants=available_assistants)

        if request.method == 'POST':
            agent_id = request.form.get('id', default_assistant_id)
            if agent_id not in ASSISTANT_MAP:
                return jsonify({'status': 'error', 'message': f"Invalid assistant ID {agent_id}"}), 400

            session['selected_assistant_id'] = agent_id
            return redirect(url_for('index'))  # Redirect to chat page

    except Exception as e:
        print(f"Exception during assistant selection: {e}")
        return jsonify({'status': 'error', 'message': 'invalid action'}), 500




@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))

    # Ensure thread_id is set, but do not modify conversation history here
    if 'thread_id' not in session:
        session['thread_id'] = None  # Or initialize a new thread if necessary

    # Pass only the existing conversation history for the selected assistant to the template
    selected_assistant_id = session.get('selected_assistant_id', app.config['DEFAULT_ASSISTANT_ID'])
    conversation_history = session.get('conversation', {}).get(selected_assistant_id, [])

    return render_template('index.html', conversation_history=conversation_history, ASSISTANT_MAP=ASSISTANT_MAP)


@app.route('/submit', methods=['POST'])
def submit():
    default_assistant_id = app.config.get('DEFAULT_ASSISTANT_ID')
    user_message = request.form['message'].strip()
    thread_id = session.get('thread_id')
    selected_assistant_id = session.get('selected_assistant_id', default_assistant_id)
    ai_reply = ""  # Initialize ai_reply to an empty string

    if not thread_id:
        thread = client.beta.threads.create()
        session['thread_id'] = thread.id  # Save the thread ID in the session
    else:
        thread = client.beta.threads.retrieve(thread_id=thread_id)

    run = submit_message(selected_assistant_id, thread, user_message)
    run = wait_on_run(run, thread)
    messages = get_response(thread)

    if messages:
        ai_reply = messages[-1].content[0].text.value  # Assign value to ai_reply

        # Ensure session['conversation'] is a dictionary
        if 'conversation' not in session or not isinstance(session['conversation'], dict):
            session['conversation'] = {}

        # Ensure the selected assistant has an entry in the conversation history
        if selected_assistant_id not in session['conversation']:
            session['conversation'][selected_assistant_id] = []

        # Append conversation to the assistant's history
        session['conversation'][selected_assistant_id].append({'user': user_message, 'ai': ai_reply})

    # Format the AI's latest response for display
    assistant_name = ASSISTANT_MAP.get(selected_assistant_id, "Unknown Assistant")
    ai_reply_html = markdown(ai_reply, extras=["tables", "fenced-code-blocks", "spoiler", "strike"])
    ai_reply_html = add_copy_buttons_to_code(ai_reply_html)
    user_message_html = markdown(user_message, extras=["tables", "fenced-code-blocks", "spoiler", "strike"])
    user_message_html = add_copy_buttons_to_code(user_message_html)

    chat_html = f'<div class="user-message">{user_message_html}</div>'
    chat_html += f'<div class="ai-message"><div class="ai-agent-name">{assistant_name}</div> {ai_reply_html}</div>'
    return chat_html


@app.route('/clear', methods=['POST'])
def clear():
    selected_assistant_id = session.get('selected_assistant_id', app.config['DEFAULT_ASSISTANT_ID'])
    if 'conversation' in session and selected_assistant_id in session['conversation']:
        session['conversation'][selected_assistant_id] = []
    return '', 204


def add_copy_buttons_to_code(html_content):
    # Create a BeautifulSoup object to parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find all code blocks and update them
    for pre in soup.find_all('pre'):
        copy_button = soup.new_tag('button', **{
            'class': 'copy-button',
            'onclick': 'copyCode(this)',
            'title': 'Copy to clipboard'
        })
        copy_button.string = 'Copy'
        pre.insert(0, copy_button)

    return str(soup)


def submit_message(assistant_id, thread, user_message):
    client.beta.threads.messages.create(thread_id=thread.id, role="user", content=user_message)
    return client.beta.threads.runs.create(thread_id=thread.id, assistant_id=assistant_id)


def wait_on_run(run, thread):
    while run.status == "queued" or run.status == "in_progress":
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        time.sleep(0.75)
    return run


def get_response(thread):
    messages_page = client.beta.threads.messages.list(thread_id=thread.id, order="asc")
    print(f"Got {len(messages_page.data)} messages")
    return [message for message in messages_page.data]


if __name__ == '__main__':
    app.run(debug=True)
