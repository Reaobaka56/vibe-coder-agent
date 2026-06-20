import os
import base64
import time
import jwt
import requests
from typing import Dict, Optional, List
from app.config import config

class GitHubService:
    def __init__(self):
        self.app_id = config.GITHUB_APP_ID
        self.private_key = config.GITHUB_PRIVATE_KEY
        self.base_url = "https://api.github.com"

    def _generate_jwt(self) -> str:
        """Generate JWT for GitHub App authentication."""
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 600,
            "iss": self.app_id
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def get_installation_token(self, installation_id: str) -> str:
        """Exchange JWT for installation access token."""
        jwt_token = self._generate_jwt()
        resp = requests.post(
            f"{self.base_url}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        resp.raise_for_status()
        return resp.json()["token"]

    async def create_repo(self, token: str, name: str, description: str = "") -> str:
        """Create repo under user's account. Returns full_name."""
        resp = requests.post(
            f"{self.base_url}/user/repos",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            },
            json={
                "name": name,
                "description": description,
                "private": False,
                "auto_init": True,
                "gitignore_template": "Node"
            }
        )
        resp.raise_for_status()
        return resp.json()["full_name"]

    async def get_default_branch(self, token: str, repo: str) -> str:
        """Get default branch name."""
        resp = requests.get(
            f"{self.base_url}/repos/{repo}",
            headers={"Authorization": f"token {token}"}
        )
        resp.raise_for_status()
        return resp.json()["default_branch"]

    async def create_branch(self, token: str, repo: str, branch_name: str, from_branch: str = None) -> str:
        """Create new branch from default or specified branch."""
        if not from_branch:
            from_branch = await self.get_default_branch(token, repo)

        # Get SHA of latest commit on from_branch
        ref_resp = requests.get(
            f"{self.base_url}/repos/{repo}/git/ref/heads/{from_branch}",
            headers={"Authorization": f"token {token}"}
        )
        ref_resp.raise_for_status()
        sha = ref_resp.json()["object"]["sha"]

        # Create new branch
        resp = requests.post(
            f"{self.base_url}/repos/{repo}/git/refs",
            headers={"Authorization": f"token {token}"},
            json={
                "ref": f"refs/heads/{branch_name}",
                "sha": sha
            }
        )
        resp.raise_for_status()
        return branch_name

    async def commit_files(self, token: str, repo: str, branch: str, 
                          files: Dict[str, str], message: str) -> str:
        """Create/update multiple files in a single commit."""
        # Get latest commit SHA on branch
        ref_resp = requests.get(
            f"{self.base_url}/repos/{repo}/git/ref/heads/{branch}",
            headers={"Authorization": f"token {token}"}
        )
        ref_resp.raise_for_status()
        latest_sha = ref_resp.json()["object"]["sha"]

        # Get tree SHA
        commit_resp = requests.get(
            f"{self.base_url}/repos/{repo}/git/commits/{latest_sha}",
            headers={"Authorization": f"token {token}"}
        )
        commit_resp.raise_for_status()
        base_tree_sha = commit_resp.json()["tree"]["sha"]

        # Create blobs for each file
        blobs = []
        for path, content in files.items():
            blob_resp = requests.post(
                f"{self.base_url}/repos/{repo}/git/blobs",
                headers={"Authorization": f"token {token}"},
                json={"content": content, "encoding": "utf-8"}
            )
            blob_resp.raise_for_status()
            blobs.append({
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_resp.json()["sha"]
            })

        # Create new tree
        tree_resp = requests.post(
            f"{self.base_url}/repos/{repo}/git/trees",
            headers={"Authorization": f"token {token}"},
            json={"base_tree": base_tree_sha, "tree": blobs}
        )
        tree_resp.raise_for_status()
        new_tree_sha = tree_resp.json()["sha"]

        # Create commit
        new_commit = requests.post(
            f"{self.base_url}/repos/{repo}/git/commits",
            headers={"Authorization": f"token {token}"},
            json={
                "message": message,
                "tree": new_tree_sha,
                "parents": [latest_sha]
            }
        )
        new_commit.raise_for_status()
        new_commit_sha = new_commit.json()["sha"]

        # Update branch reference
        update_resp = requests.patch(
            f"{self.base_url}/repos/{repo}/git/refs/heads/{branch}",
            headers={"Authorization": f"token {token}"},
            json={"sha": new_commit_sha}
        )
        update_resp.raise_for_status()

        return new_commit_sha

    async def get_file(self, token: str, repo: str, branch: str, path: str) -> str:
        """Get file content from repo."""
        resp = requests.get(
            f"{self.base_url}/repos/{repo}/contents/{path}?ref={branch}",
            headers={"Authorization": f"token {token}"}
        )
        resp.raise_for_status()
        content = resp.json()["content"]
        return base64.b64decode(content).decode("utf-8")

    async def list_files(self, token: str, repo: str, branch: str, path: str = "") -> List[Dict]:
        """List files in directory."""
        url = f"{self.base_url}/repos/{repo}/contents/{path}?ref={branch}" if path else f"{self.base_url}/repos/{repo}/contents?ref={branch}"
        resp = requests.get(
            url,
            headers={"Authorization": f"token {token}"}
        )
        resp.raise_for_status()
        return resp.json()

    async def create_pull_request(self, token: str, repo: str, title: str, head: str, base: str, body: str = "") -> str:
        """Create pull request."""
        resp = requests.post(
            f"{self.base_url}/repos/{repo}/pulls",
            headers={"Authorization": f"token {token}"},
            json={
                "title": title,
                "head": head,
                "base": base,
                "body": body
            }
        )
        resp.raise_for_status()
        return resp.json()["html_url"]
