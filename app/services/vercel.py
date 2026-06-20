import os
import asyncio
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

    async def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        return await asyncio.to_thread(requests.request, method, url, **kwargs)

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

        resp = await self._request("POST",
            f"{self.base_url}/v9/projects",
            headers=self._headers(),
            json=payload
        )
        resp.raise_for_status()
        return resp.json()["id"]

    async def deploy_project(self, project_id: str, repo: str, repo_id: str, branch: str = "main") -> str:
        """Trigger deployment. Returns deploy_id."""
        payload = {
            "name": repo.split("/")[1],
            "project": project_id,
            "gitSource": {
                "type": "github",
                "repoId": repo_id,
                "ref": branch,
                "repo": repo
            },
            "target": "production"
        }

        resp = await self._request("POST",
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

        resp = await self._request("GET", url, headers=self._headers())
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

            await asyncio.sleep(2)

        raise TimeoutError(f"Deploy didn't finish in {timeout}s")

    async def deploy_repo(self, repo: str, project_name: str, branch: str, repo_id: str) -> str:
        """Full deploy flow: create project, trigger deploy, wait for URL."""
        repo_url = f"https://github.com/{repo}"

        project_id = await self.create_project(project_name, repo_url)
        deploy_id = await self.deploy_project(project_id, repo, repo_id, branch)
        url = await self.wait_for_deploy(deploy_id)

        return f"https://{url}"

    async def get_preview_url(self, repo: str, branch: str = "main") -> Optional[str]:
        """Get preview URL for branch (predictable)."""
        project_name = repo.split("/")[1]
        safe_branch = branch.replace("/", "-")
        return f"https://{project_name}-git-{safe_branch}.vercel.app"
