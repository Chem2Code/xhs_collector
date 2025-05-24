import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from loguru import logger
import datetime

# Attempt to import existing scraper modules
try:
    from main import Data_Spider
    from xhs_utils.common_utils import init as xhs_init
    from xhs_utils.cookie_util import trans_cookies
    from xhs_utils.data_util import check_and_create_path # For ensuring download dirs exist
except ImportError as e:
    logger.error(f"Error importing scraper modules: {e}. Make sure main.py and xhs_utils are in the PYTHONPATH.")
    # Define dummy classes/functions if imports fail
    class Data_Spider:
        def __init__(self): logger.warning("Using dummy Data_Spider due to import error.")
        def spider_note(self, note_url, cookies_str, proxies=None): return False, "Dummy: Not implemented", {"id": "dummy_note", "title": "Dummy Note"}
        def spider_some_note(self, notes, cookies_str, base_path, save_choice, excel_name='', proxies=None): flash(f"Dummy: spider_some_note called with notes: {notes}", "info")
        def spider_user_all_note(self, user_url, cookies_str, base_path, save_choice, excel_name='', proxies=None): return [{"id":"dummy1","title":"Dummy Note 1"}], True, "Dummy: Fetched 1 note"
        def spider_some_search_note(self, query, require_num, cookies_str, base_path, save_choice, sort="general", note_type=0, excel_name='', proxies=None): return [{"id":"dummy_search","title":"Dummy Search Result"}], True, "Dummy: Searched notes"

    def xhs_init():
        logger.warning("Using dummy xhs_init due to import error.")
        media_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'datas/media_datas'))
        excel_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'datas/excel_datas'))
        os.makedirs(media_path, exist_ok=True)
        os.makedirs(excel_path, exist_ok=True)
        return "", {'media': media_path, 'excel': excel_path}

    def trans_cookies(cookie_str):
        logger.warning("Using dummy trans_cookies due to import error.")
        if not cookie_str: return {}
        return {i.split('=')[0]: '='.join(i.split('=')[1:]) for i in cookie_str.split('; ')}
    
    def check_and_create_path(path):
        os.makedirs(path, exist_ok=True)


app = Flask(__name__)
app.secret_key = os.urandom(24)

# Initialize scraper and base paths
try:
    _, base_path_global = xhs_init()
    data_spider_global = Data_Spider()
    # Ensure download directories exist
    check_and_create_path(base_path_global['excel'])
    check_and_create_path(base_path_global['media'])
except Exception as e:
    logger.error(f"Error initializing Data_Spider or paths: {e}")
    data_spider_global = Data_Spider() 
    base_path_global = {'media': 'datas/media_datas', 'excel': 'datas/excel_datas'}
    os.makedirs(base_path_global['media'], exist_ok=True)
    os.makedirs(base_path_global['excel'], exist_ok=True)

def add_to_log(message):
    log_entry = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}"
    if 'activity_log' not in session:
        session['activity_log'] = []
    session['activity_log'].insert(0, log_entry) # Add to the beginning
    session['activity_log'] = session['activity_log'][:20] # Keep only last 20 entries
    session.modified = True


@app.route('/', methods=['GET'])
def index():
    current_cookies = session.get('cookies_str', '')
    
    excel_files = []
    if os.path.exists(base_path_global['excel']):
        excel_files = [f for f in os.listdir(base_path_global['excel']) if f.endswith('.xlsx')]
    
    # For media, just indicate the base path as listing all can be too much
    media_base_folder = base_path_global['media']

    activity_log_display = "\n".join(session.get('activity_log', ["No activity yet."]))

    return render_template('index.html', 
                           current_cookies=current_cookies,
                           excel_files=excel_files,
                           media_base_folder=media_base_folder,
                           activity_log_display=activity_log_display,
                           single_note_result=session.get('single_note_result'),
                           user_notes_result=session.get('user_notes_result'),
                           search_notes_result=session.get('search_notes_result'))

@app.route('/submit', methods=['POST'])
def index_post():
    form_type = request.form.get('form_type')
    cookies_str = session.get('cookies_str')
    redirect_anchor = ""

    if not cookies_str and form_type != 'cookie':
        flash('Xiaohongshu cookies are not set. Please set them first.', 'error')
        add_to_log("Error: Attempted action without cookies set.")
        return redirect(url_for('index', _anchor='cookie-section'))

    if form_type == 'cookie':
        redirect_anchor = 'cookie-section'
        cookies_str_input = request.form['cookies_str']
        try:
            if not cookies_str_input or 'a1' not in trans_cookies(cookies_str_input):
                flash('Invalid cookie string. Must not be empty and contain "a1" cookie.', 'error')
                add_to_log(f"Error: Invalid cookie string provided: {cookies_str_input[:30]}...")
            else:
                session['cookies_str'] = cookies_str_input
                flash('Cookies saved successfully!', 'success')
                add_to_log("Info: Cookies saved.")
        except Exception as e:
            flash(f'Error processing cookies: {str(e)}', 'error')
            add_to_log(f"Error: Processing cookies: {str(e)}")

    elif form_type == 'single_note':
        redirect_anchor = 'single-note-section'
        note_url = request.form.get('note_url')
        save_choice = request.form.get('save_choice', 'all')
        excel_name = request.form.get('excel_name', '')
        if not excel_name and (save_choice == 'all' or save_choice == 'excel'):
             # Default excel name to note id if not provided
            try:
                excel_name = note_url.split('/')[-1].split('?')[0]
            except:
                flash('Could not derive excel_name from note_url, please provide one if saving to excel.','warning')
                excel_name = f"note_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"


        add_to_log(f"Action: Fetching single note: {note_url}, Save: {save_choice}, Excel: {excel_name}")
        try:
            # For single note, spider_note returns (success, msg, note_info)
            # We need to call spider_some_note to align with how main.py saves single notes
            success, msg, note_info = data_spider_global.spider_note(note_url, cookies_str)
            if success and note_info:
                # main.py uses spider_some_note to save even single notes if excel/media download is chosen
                data_spider_global.spider_some_note([note_url], cookies_str, base_path_global, save_choice, excel_name if (save_choice == 'all' or save_choice == 'excel') else '')
                flash(f"Successfully fetched note: {note_info.get('title', 'N/A')}. {msg}", 'success')
                session['single_note_result'] = note_info # Save for display
                add_to_log(f"Success: Fetched single note '{note_info.get('title', 'N/A')}'. Files saved according to choice '{save_choice}'.")
            else:
                flash(f"Failed to fetch note: {msg}", 'error')
                session['single_note_result'] = {"error": msg, "details": None}
                add_to_log(f"Error: Fetching single note {note_url}: {msg}")
        except Exception as e:
            flash(f"Error fetching single note: {str(e)}", 'error')
            session['single_note_result'] = {"error": str(e), "details": None}
            add_to_log(f"Exception: Fetching single note {note_url}: {str(e)}")

    elif form_type == 'user_notes':
        redirect_anchor = 'user-notes-section'
        user_url = request.form.get('user_url')
        save_choice = request.form.get('save_choice', 'all')
        # excel_name for user notes is derived inside spider_user_all_note from user_id
        add_to_log(f"Action: Fetching user notes: {user_url}, Save: {save_choice}")
        try:
            note_list, success, msg = data_spider_global.spider_user_all_note(user_url, cookies_str, base_path_global, save_choice)
            if success:
                flash(f"Successfully started fetching all notes for user. Found {len(note_list)} notes. {msg}", 'success')
                session['user_notes_result'] = {"count": len(note_list), "message": msg, "note_urls": note_list[:5]} # Display first 5 urls as sample
                add_to_log(f"Success: Fetching user notes for {user_url}. Found {len(note_list)}. Files saved according to choice '{save_choice}'.")
            else:
                flash(f"Failed to fetch user notes: {msg}", 'error')
                session['user_notes_result'] = {"error": msg, "count": 0}
                add_to_log(f"Error: Fetching user notes {user_url}: {msg}")
        except Exception as e:
            flash(f"Error fetching user notes: {str(e)}", 'error')
            session['user_notes_result'] = {"error": str(e), "count": 0}
            add_to_log(f"Exception: Fetching user notes {user_url}: {str(e)}")

    elif form_type == 'search_notes':
        redirect_anchor = 'search-notes-section'
        query = request.form.get('query')
        require_num_str = request.form.get('require_num', '10')
        try:
            require_num = int(require_num_str)
        except ValueError:
            flash("Invalid number for 'Number of Notes'. Using default 10.", "warning")
            require_num = 10
        sort = request.form.get('sort', 'general')
        note_type_str = request.form.get('note_type', '0')
        try:
            note_type = int(note_type_str)
        except ValueError:
            flash("Invalid value for 'Note Type'. Using default 'All'.", "warning")
            note_type = 0
        save_choice = request.form.get('save_choice', 'all')
        # excel_name for search notes is derived inside spider_some_search_note from query
        add_to_log(f"Action: Searching notes. Query: '{query}', Num: {require_num}, Sort: {sort}, Type: {note_type}, Save: {save_choice}")
        try:
            note_list, success, msg = data_spider_global.spider_some_search_note(query, require_num, cookies_str, base_path_global, save_choice, sort, note_type)
            if success:
                flash(f"Successfully started search for '{query}'. Found {len(note_list)} notes. {msg}", 'success')
                session['search_notes_result'] = {"count": len(note_list), "query": query, "message": msg, "note_urls": note_list[:5]}
                add_to_log(f"Success: Searching notes for '{query}'. Found {len(note_list)}. Files saved according to choice '{save_choice}'.")
            else:
                flash(f"Failed to search notes: {msg}", 'error')
                session['search_notes_result'] = {"error": msg, "query": query, "count": 0}
                add_to_log(f"Error: Searching notes for '{query}': {msg}")
        except Exception as e:
            flash(f"Error searching notes: {str(e)}", 'error')
            session['search_notes_result'] = {"error": str(e), "query": query, "count": 0}
            add_to_log(f"Exception: Searching notes for '{query}': {str(e)}")
            
    else:
        flash('Unknown action.', 'error')
        add_to_log(f"Error: Unknown form_type submitted: {form_type}")
        redirect_anchor = ''

    return redirect(url_for('index', _anchor=redirect_anchor))

@app.route('/download/<type>/<path:filename>')
def download_file(type, filename):
    directory = ""
    if type == 'excel':
        directory = os.path.abspath(base_path_global['excel'])
    # Add other types like 'media' if direct media file download is needed, though it's complex for nested structures.
    else:
        flash("Invalid download type.", "error")
        add_to_log(f"Error: Invalid download type '{type}' for filename '{filename}'.")
        return redirect(url_for('index', _anchor='downloads-section'))

    add_to_log(f"Action: Downloading file. Type: '{type}', Filename: '{filename}'.")
    if not os.path.exists(os.path.join(directory, filename)):
        flash(f"File not found: {filename}", "error")
        add_to_log(f"Error: File not found for download. Directory: '{directory}', Filename: '{filename}'.")
        return redirect(url_for('index', _anchor='downloads-section'))
        
    return send_from_directory(directory, filename, as_attachment=True)

if __name__ == '__main__':
    if not os.path.exists('templates'): os.makedirs('templates')
    if not os.path.exists('static'): os.makedirs('static')
    if not os.path.exists('templates/index.html'):
        with open('templates/index.html', 'w') as f: f.write('<h1>Basic Flask App</h1><p>Content will go here.</p>')
    
    logger.info("Starting Flask app on http://0.0.0.0:5001 ...")
    app.run(debug=True, host='0.0.0.0', port=5001)
