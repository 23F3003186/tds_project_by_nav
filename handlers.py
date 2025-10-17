# handlers.py

import os
import base64
import json
import requests
from pydantic import BaseModel
from datetime import datetime
from generator import generate_app_code,_modify_existing_app


GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USER = os.getenv("GITHUB_USER")
GITHUB_API = "https://api.github.com"
class Attachment(BaseModel):
    name: str
    url: str

class TaskRequest(BaseModel):
    email: str
    secret: str
    task: str
    round: int
    nonce: str
    brief: str
    checks: list
    evaluation_url: str
    attachments: list[Attachment] = []

# --- Helper Functions ---

def _get_repo_files(session, repo_name: str, path: str = "") -> dict:
    """
    Recursively fetches the content of all files from a GitHub repository.
    """
    if path == "":
        print(f"Fetching existing files from {repo_name}...")
    
    contents_url = f"{GITHUB_API}/repos/{GITHUB_USER}/{repo_name}/contents/{path}"
    list_resp = session.get(contents_url)
    if list_resp.status_code != 200:
        raise Exception(f"Failed to list repo contents for path '{path}': {list_resp.text}")

    existing_files = {}
    for item in list_resp.json():
        if item['type'] == 'file':
            file_resp = session.get(item['download_url'])
            if file_resp.status_code == 200:
                existing_files[item['path']] = file_resp.text
            else:
                print(f"Warning: Could not fetch content for {item['path']}")
        elif item['type'] == 'dir':
            existing_files.update(_get_repo_files(session, repo_name, path=item['path']))
            
    if path == "":
        print(f"Found {len(existing_files)} files to use as context.")
    return existing_files

def upload_or_update_file(session, repo_name, path, content):
    """
    Uploads a new file or updates an existing one in a GitHub repository.
    Returns the commit SHA from the successful action.
    """
    upload_url = f"{GITHUB_API}/repos/{GITHUB_USER}/{repo_name}/contents/{path}"
    
    existing_file_sha = None
    get_resp = session.get(upload_url)
    if get_resp.status_code == 200:
        existing_file_sha = get_resp.json().get("sha")
    elif get_resp.status_code != 404:
        raise Exception(f"Failed to check for file {path}: {get_resp.text}")

    if isinstance(content, str):
        content_bytes = content.encode('utf-8')
    else:
        content_bytes = content
    encoded_content = base64.b64encode(content_bytes).decode('utf-8')

    payload = {
        "message": f"feat: Add or update {path}",
        "content": encoded_content,
        "branch": "main"
    }
    if existing_file_sha:
        payload["sha"] = existing_file_sha

    put_resp = session.put(upload_url, json=payload)
    if put_resp.status_code not in [200, 201]:
        raise Exception(f"Upload failed for {path}: {put_resp.text}")
    return put_resp.json()["commit"]["sha"]

def _handle_round_1(session, task: TaskRequest):
    """Handles creating a new repository for Round 1."""
    repo_name = task.task
    print(f"Creating repository: {repo_name}")
    repo_data = {
        "name": repo_name,
        "private": False,
        "auto_init": True,
        "license_template": "mit"
    }
    create_resp = session.post(f"{GITHUB_API}/user/repos", json=repo_data)
    if create_resp.status_code != 201:
        raise Exception(f"Failed to create repo: {create_resp.text}")

    # Convert attachment objects to a list of dicts for the generator prompt
    attachments_for_generator = [att.dict() for att in task.attachments]

    files_to_upload = generate_app_code(
        task_name=task.task,
        brief=task.brief,
        checks=task.checks,
        attachments=attachments_for_generator
    )
    
    # Use dot notation (att.name) to access attributes on Pydantic objects
    for att in task.attachments:
        files_to_upload[att.name] = base64.b64decode(att.url.split(",")[1])

    latest_commit_sha = None
    for path, content in files_to_upload.items():
        latest_commit_sha = upload_or_update_file(session, repo_name, path, content)
    
    print("Enabling GitHub Pages...")
    pages_resp = session.post(f"{GITHUB_API}/repos/{GITHUB_USER}/{repo_name}/pages", json={"source": {"branch": "main", "path": "/"}})
    if pages_resp.status_code not in [201, 204]:
        print(f"Warning: GitHub Pages setup returned status {pages_resp.status_code}")
        
    return latest_commit_sha

def _handle_round_2(session, task: TaskRequest):
    """Handles updating an existing repository for Round 2."""
    repo_name = task.task
    existing_files = _get_repo_files(session, repo_name)
    if not existing_files:
        raise Exception("Could not retrieve existing files to modify.")

    # Convert attachment objects to a list of dicts for the generator prompt
    attachments_for_generator = [att.dict() for att in task.attachments]

    files_to_update = generate_app_code(
        task_name=task.task,
        brief=task.brief,
        checks=task.checks,
        attachments=attachments_for_generator,
        existing_files=existing_files
    )
    
    # Use dot notation (att.name) to access attributes on Pydantic objects
    for att in task.attachments:
        files_to_update[att.name] = base64.b64decode(att.url.split(",")[1])

    latest_commit_sha = None
    for path, content in files_to_update.items():
        latest_commit_sha = upload_or_update_file(session, repo_name, path, content)
        
    return latest_commit_sha

# === Main Handler Function ===
def handle_task(task: TaskRequest):
    """
    Main workflow for creating/updating a GitHub repo. Called from main.py.
    """
    repo_name = task.task
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    with requests.Session() as session:
        session.headers.update(headers)
        
        if task.round == 1:
            latest_commit_sha = _handle_round_1(session, task)
        elif task.round > 1:
            latest_commit_sha = _handle_round_2(session, task)
        else:
            raise Exception(f"Unknown round: {task.round}")
        
        if not latest_commit_sha:
             raise Exception("Failed to retrieve a valid commit SHA.")

        print("Notifying evaluation server...")
        eval_payload = {
            "email": task.email, "task": task.task, "round": task.round,
            "nonce": task.nonce, "repo_url": f"https://github.com/{GITHUB_USER}/{repo_name}",
            "commit_sha": latest_commit_sha, "pages_url": f"https://{GITHUB_USER}.github.io/{repo_name}/"
        }
        eval_resp = session.post(task.evaluation_url, json=eval_payload)
        if eval_resp.status_code != 200:
            raise Exception(f"Evaluation notification failed: {eval_resp.text}")

        print("Task handled successfully.")