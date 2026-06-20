import os
import time
import requests
from typing import Optional
from app.config import config

class VercelService:
    def __init__(self):
        self.token = config.VERCEL_TOKEN
        self.team_id = config.VERCEL_TEAM_ID
        self.base_url = "https://api.vercel.com"

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def create_project(self, name: str, repo_url: str) -> str:
        """Create Vercel project linked to GitHub repo. Returns project_id."""
        payload = {
            "name": name,
            "framework": "nextjs",
            "gitRepository": {
                "repo": repo_url.replace("https://github.com/", ""),
                "type": "github"
            }
        }
        if self.team_id:
            payload["teamId"] = self.team_id

        resp = requests.post(
            f"{self.base_url}/v9/projects",
            headers=self._headers(),
            json=payload
        )
        resp.raise_for_status()
        return resp.json()["id"]

    async def deploy_project(self, project_id: str, repo: str, branch: str = "main") -> str:
        """Trigger deployment. Returns deploy_id."""
        repo_full = repo  # owner/repo-name
        payload = {
            "name": repo.split("/")[1],
            "project": project_id,
            "gitSource": {
                "type": "github",
                "repoId": repo_full,
                "ref": branch,
                "repo": repo_full
            },
            "target": "production"
        }

        resp = requests.post(
            f"{self.base_url}/v13/deployments",
            headers=self._headers(),
            json=payload
        )
        resp.raise_for_status()
        return resp.json()["id"]

    async def get_deployment_status(self, deploy_id: str) -> dict:
        """Get deployment status."""
        url = f"{self.base_url}/v13/deployments/{deploy_id}"
        if self.team_id:
            url += f"?teamId={self.team_id}"

        resp = requests.get(url, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def wait_for_deploy(self, deploy_id: str, timeout: int = 60) -> str:
        """Poll deployment until ready. Returns URL."""
        for _ in range(timeout // 2):
            status = await self.get_deployment_status(deploy_id)

            if status.get("readyState") == "READY":
                return status.get("url")

            if status.get("readyState") in ["ERROR", "CANCELED"]:
                raise Exception(f"Deploy failed: {status.get('errorMessage', 'Unknown error')}")

            time.sleep(2)

        raise TimeoutError(f"Deploy didn't finish in {timeout}s")

    async def deploy_repo(self, repo: str, project_name: str, branch: str = "main") -> str:
        """Full deploy flow: create project, trigger deploy, wait for URL."""
        repo_url = f"https://github.com/{repo}"

        # Create project
        project_id = await self.create_project(project_name, repo_url)

        # Trigger deploy
        deploy_id = await self.deploy_project(project_id, repo, branch)

        # Wait for ready
        url = await self.wait_for_deploy(deploy_id)

        return f"https://{url}"

    async def get_preview_url(self, repo: str, branch: str = "main") -> Optional[str]:
        """Get preview URL for branch (predictable)."""
        project_name = repo.split("/")[1]
        safe_branch = branch.replace("/", "-")
        return f"https://{project_name}-git-{safe_branch}.vercel.app"
