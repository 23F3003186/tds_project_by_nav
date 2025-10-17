from openai import OpenAI
from dotenv import load_dotenv
import os
import ast
import re
load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") 
client = OpenAI(base_url=OPENAI_BASE_URL,api_key=OPENAI_API_KEY)

def _execute_llm_call(prompt: str, model: str = "gpt-4o-mini") -> dict:
    """
    Executes a call to the LLM, handles potential API errors, and robustly
    parses the response to extract a Python dictionary.
    """
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        content = response.choices[0].message.content
        print(f"LLM Response: {content}")

        # Robust parsing: Find the dictionary within the response string
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            print("Could not find a dictionary in the LLM response.")
            # Fallback: return the raw content as the only file
            return {"index.html": content}

        dict_str = match.group(0)
        try:
            # Use the safer ast.literal_eval to parse the dictionary string
            files = ast.literal_eval(dict_str)
            if isinstance(files, dict):
                return files
            else:
                raise ValueError("Parsed content is not a dictionary.")
        except (ValueError, SyntaxError) as e:
            print(f"Could not parse LLM response as a dictionary: {e}")
            return {"error.txt": f"Failed to parse LLM response.\n\nRaw Content:\n{content}"}

    except Exception as e:
        print(f"An unexpected error occurred during LLM call: {e}")
        return {
            "error.html": f"<html><body><h1>Failed to generate app via LLM</h1><pre>{e}</pre></body></html>"
        }

def _llm_filter_relevant_files(brief: str, file_list: list) -> list:
    """
    Uses an LLM call to intelligently select which files are relevant for a given change request.
    """
    prompt = f"""
As a senior software architect, your task is to identify which files need to be edited to fulfill a user's request.
User's Request: "{brief}"
Available Files: {file_list}

Respond ONLY with a Python list of the full file paths that need to be modified.
Example response: ['src/components/Header.vue', 'src/assets/style.css']
"""
    print("Asking LLM to identify relevant files...")
    response_dict = _execute_llm_call(prompt)
    
    # The response is a dict, but the value we need is a list string. Let's find it.
    for key, value in response_dict.items():
        try:
            # Assuming the response is a string representation of a list
            relevant_files = ast.literal_eval(value)
            if isinstance(relevant_files, list):
                return relevant_files
        except (ValueError, SyntaxError):
            continue
    
    print("Warning: Could not parse relevant files list from LLM. Falling back to all files.")
    return file_list # Fallback to all files if parsing fails

def _generate_new_app(task_name: str, brief: str, checks: list, attachments: list) -> dict:
    """Generates a new application from a brief, checks, and attachments."""
    prompt = f"""
As an expert software developer, create a complete, production-ready application.
This application must work entirely as a static website.
The official name for this task is '{task_name}'. Use this for titles or project names.
Your response must include a professional README.md  in file for the project.
Do **not** include any LICENSE file or licensing text in this output.

User Brief: "{brief}"

The following files are provided as attachments. Your code should be able to use them:
{attachments}

Crucially, the code you generate must satisfy all of the following evaluation checks:
{checks}

Based on all the information, determine the required files (e.g., index.html, style.css, src/app.js, etc.).
Respond ONLY with a single-line Python dictionary that maps full file paths to their complete string content.
Ensure all code is complete and does not contain placeholders.
"""
    return _execute_llm_call(prompt)

def _modify_existing_app(task_name: str, brief: str, checks: list, attachments: list, existing_files: dict) -> dict:
    """Modifies an existing application based on a brief, checks, attachments, and file context."""
    prompt = f"""
As an expert software developer, your task is to modify an existing project named '{task_name}'.
Apply the following change based on the user's request.

User Request: "{brief}"

The following files are provided as attachments. Your code should be able to use them:
{attachments}

The final code must satisfy all of the following evaluation checks:
{checks}

Here is the current content of the relevant files:
{existing_files}

Respond ONLY with a Python dictionary containing the complete, updated content for ONLY the files that need to change.
Do not include files that were not modified.
"""
    return _execute_llm_call(prompt)

def generate_app_code(task_name: str, brief: str, checks: list = None, attachments: list = None, existing_files: dict = None) -> dict:
    """
    Main function to generate or modify an application.
    It acts as a dispatcher to the appropriate helper function.
    """
    if checks is None:
        checks = []
    if attachments is None:
        attachments = []

    if existing_files:
        print(f"Modifying files for brief: '{brief[:50]}...'")
        all_file_paths = list(existing_files.keys())
        relevant_file_paths = _llm_filter_relevant_files(brief, all_file_paths)
        
        print(f"LLM identified {len(relevant_file_paths)} relevant files out of {len(all_file_paths)} total.")
        
        context_files = {path: existing_files[path] for path in relevant_file_paths if path in existing_files}
        
        return _modify_existing_app(task_name, brief, checks, attachments, context_files)
    else:
        print(f"Generating new app for brief: '{brief[:50]}...'")
        return _generate_new_app(task_name, brief, checks, attachments)
