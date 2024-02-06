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


from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'  # Update this path as needed
db = SQLAlchemy(app)

from flask_migrate import Migrate

migrate = Migrate(app, db)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    is_admin = db.Column(db.Boolean, default=False)

# Create a new table to store the assistants each user has access to
class UserAssistant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assistant_id = db.Column(db.String(80), nullable=False)
    

@app.route('/dashboard_selection')
def dashboard_selection():
    if 'username' in session:
        user = User.query.filter_by(username=session['username']).first()
        if user and user.is_admin:
            return render_template('dashboard_selection.html')
        else:
            return redirect(url_for('dashboard'))  # Non-admins are redirected to the regular dashboard
    return redirect(url_for('login'))


@app.route('/admin/dashboard')
def admin_dashboard():
    if 'username' in session and User.query.filter_by(username=session['username']).first().is_admin:
        return render_template('admin_dashboard.html')
    else:
        return 'Unauthorized!', 403


@app.route('/admin/user_assistants', methods=['GET'])
def view_user_assistants():
    if 'username' in session and User.query.filter_by(username=session['username']).first().is_admin:
        user_assistants = UserAssistant.query.all()
        user_assistants_details = []
        for ua in user_assistants:
            assistant_name = ASSISTANT_MAP.get(ua.assistant_id, 'Unknown Assistant')
            user_assistants_details.append({
                'id': ua.id,
                'user_id': ua.user_id,
                'assistant_id': ua.assistant_id,
                'assistant_name': assistant_name
            })
        return render_template('user_assistants.html', user_assistants=user_assistants_details)
    else:
        return 'Unauthorized!', 403


@app.route('/admin/user_assistants/add', methods=['POST'])
def add_user_assistant():
    if 'username' in session and User.query.filter_by(username=session['username']).first().is_admin:
        user_id = request.form['user_id']
        assistant_id = request.form['assistant_id']
        user_assistant = UserAssistant(user_id=user_id, assistant_id=assistant_id)
        db.session.add(user_assistant)
        db.session.commit()
        return redirect(url_for('view_user_assistants'))
    else:
        return 'Unauthorized!', 403

@app.route('/admin/user_assistants/remove', methods=['POST'])
def remove_user_assistant():
    if 'username' in session and User.query.filter_by(username=session['username']).first().is_admin:
        user_assistant_id = request.form['user_assistant_id']
        user_assistant = UserAssistant.query.get(user_assistant_id)
        db.session.delete(user_assistant)
        db.session.commit()
        return redirect(url_for('view_user_assistants'))
    else:
        return 'Unauthorized!', 403
    


@app.route('/admin/manage_users', methods=['GET'])
def manage_users():
    if 'username' in session and User.query.filter_by(username=session['username']).first().is_admin:
        users = User.query.all()
        return render_template('manage_users.html', users=users)
    else:
        return 'Unauthorized!', 403



@app.route('/admin/manage_users/add', methods=['POST'])
def add_user():
    if 'username' in session and User.query.filter_by(username=session['username']).first().is_admin:
        username = request.form['username']
        password = request.form['password']
        is_admin = 'is_admin' in request.form
        user = User(username=username)
        user.set_password(password)
        user.is_admin = is_admin
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('manage_users'))
    else:
        return 'Unauthorized!', 403


@app.route('/admin/manage_users/remove', methods=['POST'])
def remove_user():
    if 'username' in session and User.query.filter_by(username=session['username']).first().is_admin:
        user_id = request.form['user_id']
        user = User.query.get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
        return redirect(url_for('manage_users'))
    else:
        return 'Unauthorized!', 403



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['username'] = username
            # Check if the user is an admin
            if user.is_admin:
                return redirect(url_for('dashboard_selection'))  # Redirect to selection page for admins
            else:
                return redirect(url_for('dashboard'))  # Regular users go directly to the dashboard
        else:
            return 'Invalid username or password!'
    return render_template('login.html')



@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')


@app.route('/assistant_options', methods=['POST', 'GET'])
def assistant_options():
    try:
        default_assistant_id = app.config.get('DEFAULT_ASSISTANT_ID', None)
        username = session.get('username')
        user = User.query.filter_by(username=username).first()

        if user:
            user_assistants = UserAssistant.query.filter_by(user_id=user.username).all()
            print(f"user_assistants: {user_assistants}")  # Debug print
            available_assistants = [
                {'id': ua.assistant_id, 'name': ASSISTANT_MAP.get(ua.assistant_id, 'Unknown Assistant')}
                for ua in user_assistants
            ]
            print(f"available_assistants: {available_assistants}")  # Debug print
        else:
            available_assistants = []

        if request.method == 'GET':
            return render_template('assistant_options.html', assistants=available_assistants)

        if request.method == 'POST':
            agent_id = request.form.get('id', default_assistant_id)
            if agent_id is None or agent_id not in ASSISTANT_MAP:
                return jsonify({'status': 'error', 'message': f"Invalid assistant ID {agent_id}"}), 400

        session['selected_assistant_id'] = agent_id
        return redirect(url_for('index'))  # Redirect to chat page

    except Exception as e:
        print(f"Exception during assistant selection: {e}")
        traceback.print_exc()  # This will help you to see the full stack trace of the exception
        return jsonify({'status': 'error', 'message': 'invalid action'}), 500



@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))

    # Ensure thread_id is set, but do not modify conversation history here
    if 'thread_id' not in session:
        session['thread_id'] = None  # Or initialize a new thread if necessary

    # Pass only the existing conversation history for the selected assistant to the template
    selected_assistant_id = session.get('selected_assistant_id', app.config.get('DEFAULT_ASSISTANT_ID'))
    conversation_history = session.get('conversation', {}).get(selected_assistant_id, [])

    return render_template('index.html', conversation_history=conversation_history, ASSISTANT_MAP=ASSISTANT_MAP)


@app.route('/submit', methods=['POST'])
def submit():
    default_assistant_id = app.config.get('DEFAULT_ASSISTANT_ID')
    user_message = request.form['message'].strip()
    thread_id = session.get('thread_id')
    selected_assistant_id = session.get('selected_assistant_id', default_assistant_id)

    # Print the selected assistant ID for debugging
    print(f"Selected Assistant ID: {selected_assistant_id}")

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
    # Clear the conversation history for the current assistant
    selected_assistant_id = session.get('selected_assistant_id', app.config['DEFAULT_ASSISTANT_ID'])
    if 'conversation' in session and selected_assistant_id in session['conversation']:
        session['conversation'][selected_assistant_id] = []

    # Create a new thread for future messages
    try:
        new_thread = client.beta.threads.create()  # Assuming the client is your OpenAI API client
        session['thread_id'] = new_thread.id  # Update the thread ID in the session
    except Exception as e:
        print(f"Error creating a new thread: {e}")
        # Handle error appropriately

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
