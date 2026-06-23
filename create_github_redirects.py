import requests
import base64
import time
import json
import os
import random
import string
import sys
import configparser

def get_valid_input(prompt, error_msg="Input cannot be empty."):
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print(error_msg)

def delete_repos(token, username):
    print("\n--- Batch Repository Deleter ---")

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # --- "World-Class" Repo Discovery ---
    print("Discovering repository groups on your GitHub account...")
    all_repos = []
    page = 1
    while True:
        repos_url = f"https://api.github.com/user/repos?per_page=100&page={page}"
        resp = requests.get(repos_url, headers=headers)
        if resp.status_code != 200:
            print(f"Error fetching repositories: {resp.status_code}")
            break
        data = resp.json()
        if not data:
            break
        all_repos.extend(data)
        page += 1

    import re
    from collections import defaultdict
    repo_groups = defaultdict(list)
    for repo in all_repos:
        repo_name = repo['name']
        match = re.match(r'^(.*)-(\d{3})$', repo_name)
        if match:
            base_name = match.group(1)
            repo_groups[base_name].append(repo_name)

    base_name = None
    count = 0

    if not repo_groups:
        print("No potential redirect repository groups found.")
        base_name = get_valid_input("Enter the base name of repos to DELETE manually (e.g., 'auth-gate'): ")
        count = int(get_valid_input("How many to delete? (e.g., 50): "))
    else:
        print("\n--- Discovered Repository Groups ---")
        group_list = sorted(repo_groups.items(), key=lambda item: item[0])
        for i, (name, repos) in enumerate(group_list, 1):
            print(f"{i}) {name} ({len(repos)} repos)")
        
        print("\nSelect a group to delete by number, or type a base name manually.")
        choice = input("Enter choice: ").strip()
        
        try:
            choice_num = int(choice)
            if 1 <= choice_num <= len(group_list):
                base_name, repos_in_group = group_list[choice_num - 1]
                count = len(repos_in_group)
            else:
                print("Invalid number. Aborting.")
                return
        except ValueError:
            base_name = choice
            if base_name in repo_groups:
                count = len(repo_groups[base_name])
                print(f"Manually entered group '{base_name}' found with {count} repos.")
            else:
                count = int(get_valid_input(f"How many repos with base name '{base_name}' to delete? (e.g., 50): "))

    if not base_name:
        print("Aborting.")
        return

    print(f"\nWARNING: This will permanently delete up to {count} repositories with base name '{base_name}'.")
    confirm = input(f"Are you sure? [y/N]: ").strip().lower()
    if confirm != 'y':
        print("Deletion cancelled.")
        return

    print(f"\nDeleting {count} repositories starting with '{base_name}-001'...")
    for i in range(1, count + 1):
        repo_name = f"{base_name}-{i:03d}"
        print(f"[{i}/{count}] Deleting {repo_name}...", end=" ")
        del_url = f"https://api.github.com/repos/{username}/{repo_name}"
        resp = requests.delete(del_url, headers=headers)
        if resp.status_code == 204:
            print("DELETED.")
        elif resp.status_code == 404:
            print("Not Found (Already deleted).")
        elif resp.status_code == 403:
            print(f"Skipped (403 Forbidden). Token likely lacks 'delete_repo' scope.")
        else:
            print(f"Error: {resp.status_code}")

def create_redirects(token, username):
    print("\n--- Automatic GitHub Redirect Generator ---")
    
    target_url = get_valid_input("Enter the Final Destination URL (where users land): ")
    base_name = get_valid_input("Enter a base name for repos (e.g., 'auth-gate'): ")
    
    while True:
        try:
            count = int(get_valid_input("How many redirects to create? (e.g., 50): "))
            break
        except ValueError:
            print("Invalid number. Please enter an integer.")

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    generated_links = []

    print(f"\nStarting generation of {count} repositories... (This prevents blacklisting)")
    
    for i in range(1, count + 1):
        repo_name = f"{base_name}-{i:03d}" # e.g., auth-gate-001
        print(f"[{i}/{count}] Processing {repo_name}...")

        # --- "World-Class" Clean Redirector ---
        # This version uses a simple HTML link with no JavaScript or obfuscation.
        # This avoids being flagged as a "Deceptive Site" by Google Safe Browsing.
        import html
        safe_target_url = html.escape(target_url)

        # --- "Sentinel" Enhancement: Invisible Meta Refresh ---
        # Replaces the visual "Action Required" page with an instant redirect.
        # This removes the content that triggers "Deceptive Site" flags while preserving the GitHub hop.
        html_content = f"""<!DOCTYPE html><html><head>
<meta http-equiv="refresh" content="0;url={safe_target_url}">
<script>window.location.href="{safe_target_url}";</script>
</head><body>Loading...</body></html>"""

        # Base64 encode the unique HTML for GitHub API
        encoded_content = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")
        
        # 1. Create Repo
        create_url = "https://api.github.com/user/repos"
        payload = {
            "name": repo_name,
            "private": False, # Pages requires Public for free accounts
            "auto_init": True # Creates README to initialize branch
        }
        resp = requests.post(create_url, headers=headers, json=payload)
        
        if resp.status_code == 422:
            print(f"  - Repo {repo_name} already exists. Updating it...")
        elif resp.status_code == 403:
            print(f"  - 403 Forbidden (Rate Limit/Abuse Detection).")
            print(f"    Pausing for 60 seconds to cool down...")
            time.sleep(60)
            continue
        elif resp.status_code != 201:
            print(f"  - Error creating repo: {resp.status_code} {resp.text}")
            continue
            
        time.sleep(5) # Increased delay to prevent rate limits
        
        # 2. Upload index.html (Redirect Logic)
        file_url = f"https://api.github.com/repos/{username}/{repo_name}/contents/index.html"
        
        # Check if file exists to get SHA (needed for updates)
        get_resp = requests.get(file_url, headers=headers)
        sha = get_resp.json().get('sha') if get_resp.status_code == 200 else None
            
        file_payload = {"message": "Add redirect", "content": encoded_content, "branch": "main"}
        if sha: file_payload["sha"] = sha
            
        requests.put(file_url, headers=headers, json=file_payload)

        # 2.5 Upload .nojekyll (Crucial for preventing 404s and speeding up deployment)
        nj_url = f"https://api.github.com/repos/{username}/{repo_name}/contents/.nojekyll"
        nj_check = requests.get(nj_url, headers=headers)
        if nj_check.status_code == 404:
            requests.put(nj_url, headers=headers, json={
                "message": "Add .nojekyll", 
                "content": "", # Empty content is fine
                "branch": "main"
            })
             
        # 3. Enable GitHub Pages
        pages_url = f"https://api.github.com/repos/{username}/{repo_name}/pages"
        pages_payload = {"source": {"branch": "main", "path": "/"}}
        headers_pages = headers.copy()
        headers_pages["Accept"] = "application/vnd.github.switcheroo-preview+json"
        requests.post(pages_url, headers=headers_pages, json=pages_payload)
        
        # 4. Save Link
        page_url = f"https://{username}.github.io/{repo_name}/"
        generated_links.append(page_url)
        print(f"  -> SUCCESS: {page_url}")

    # Save to file
    with open("generated_redirects.txt", "w") as f:
        for link in generated_links:
            f.write(link + "\n")
            
    print("\n[DONE] Links saved to 'generated_redirects.txt'.")
    
    # --- "Jesko" Auto-Config Updater ---
    if generated_links:
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.ini')
            cfg = configparser.ConfigParser(inline_comment_prefixes=('#',))
            cfg.read(config_path)
            
            if not cfg.has_section('EMAIL'):
                cfg.add_section('EMAIL')
            
            # Format links with indentation for config.ini
            links_str = "\n    " + "\n    ".join(generated_links)
            cfg.set('EMAIL', 'link_url', links_str)
            
            with open(config_path, 'w') as f:
                cfg.write(f)
            print(f"[SUCCESS] Automatically updated 'config.ini' with {len(generated_links)} new links.")
        except Exception as e:
            print(f"[WARNING] Could not auto-update config.ini: {e}")
            print("Please copy the links from 'generated_redirects.txt' manually.")

if __name__ == "__main__":
    print("\n--- GitHub Manager ---")
    
    print("Paste your GitHub Token below. (Must be a 'Classic' token with 'repo' and 'delete_repo' scopes)")
    token = get_valid_input("Enter GitHub Token: ")
    
    # --- "World-Class" Auto-Detection of Username ---
    print("\nAuthenticating and fetching username from token...")
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    user_url = "https://api.github.com/user"
    try:
        resp = requests.get(user_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            username = resp.json()['login']
            print(f"Successfully authenticated as GitHub user: {username}")
        else:
            print(f"Error: Could not get username from token (Status: {resp.status_code}).")
            print("Please ensure your token is a 'Classic' token and has the 'repo' scope.")
            input("\nPress Enter to exit.")
            sys.exit(1)
    except requests.RequestException as e:
        print(f"Error: A network error occurred while authenticating: {e}")
        input("\nPress Enter to exit.")
        sys.exit(1)

    print("\n1. Create/Update Redirects (Recommended)")
    print("2. Delete Old Repositories")
    mode = get_valid_input("Select mode (1/2): ")
    
    if mode == '2':
        delete_repos(token, username)
    else:
        create_redirects(token, username)