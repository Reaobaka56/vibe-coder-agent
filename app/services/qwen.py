import os
import json
import re
import requests
from typing import Dict, List, Tuple, Optional
from app.config import config

class QwenService:
    def __init__(self):
        self.api_url = config.QWEN_API_URL
        self.model = config.QWEN_MODEL
        self.api_key = config.QWEN_API_KEY
        self.temperature = 0.2
        self.max_tokens = 8192

    def _call(self, system_prompt: str, user_prompt: str, max_tokens: int = None) -> str:
        """Call Ollama or DashScope API."""
        tokens = max_tokens or self.max_tokens

        if "dashscope" in self.api_url.lower():
            # DashScope API
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "input": {
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                },
                "parameters": {
                    "temperature": self.temperature,
                    "max_tokens": tokens,
                    "result_format": "message"
                }
            }
            resp = requests.post(self.api_url, json=payload, headers=headers, timeout=180)
            return resp.json()["output"]["choices"][0]["message"]["content"]
        else:
            # Ollama API
            payload = {
                "model": self.model,
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_ctx": 32768,
                    "num_predict": tokens,
                }
            }
            resp = requests.post(self.api_url, json=payload, timeout=180)
            return resp.json()["response"]

    def generate_project(self, description: str, project_type: str = "nextjs") -> Dict[str, str]:
        """Generate complete file structure from description."""
        system = self._load_prompt("system_new_project.txt")
        user = f"Project type: {project_type}\nDescription: {description}"

        raw = self._call(system, user, max_tokens=8192)

        # Try JSON parse first
        try:
            parsed = json.loads(raw)
            if "files" in parsed:
                return parsed["files"]
            return parsed
        except json.JSONDecodeError:
            pass

        # Fallback: extract code blocks
        return self._extract_code_blocks(raw)

    def edit_file(self, filename: str, current_content: str, instruction: str) -> str:
        """Precise file edit based on instruction."""
        system = self._load_prompt("system_edit_file.txt")
        user = f"""File: {filename}
Current content:
```
{current_content}
```

Instruction: {instruction}

Return ONLY the new file content. No explanations, no markdown fences around the whole response."""

        result = self._call(system, user, max_tokens=4096).strip()

        # Clean up markdown fences if present
        if result.startswith("```"):
            lines = result.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            result = "\n".join(lines)

        return result.strip()

    def identify_target_file(self, file_list: str, instruction: str) -> str:
        """Determine which file to edit from instruction."""
        system = "You are a file router. Given a list of files and an instruction, return ONLY the most relevant filename. No explanation."
        user = f"Files:\n{file_list}\n\nInstruction: {instruction}\n\nMost relevant file:"

        result = self._call(system, user, max_tokens=100).strip()
        # Clean up
        result = result.replace("`", "").replace("\"", "").strip()
        return result

    def _load_prompt(self, filename: str) -> str:
        """Load prompt from file."""
        path = os.path.join(os.path.dirname(__file__), "../../prompts", filename)
        with open(path, "r") as f:
            return f.read()

    def _extract_code_blocks(self, text: str) -> Dict[str, str]:
        """Fallback parser for non-JSON LLM outputs."""
        files = {}

        # Pattern 1: ```filename\ncontent\n```
        pattern1 = r'```([\w./-]+)\n(.*?)```'
        matches1 = re.findall(pattern1, text, re.DOTALL)
        for fname, content in matches1:
            files[fname.strip()] = content.strip()

        # Pattern 2: // File: filename\ncontent
        pattern2 = r'//\s*File:\s*([\w./-]+)\n(.*?)\n(?=//\s*File:|```|$)'
        matches2 = re.findall(pattern2, text, re.DOTALL)
        for fname, content in matches2:
            files[fname.strip()] = content.strip()

        # Pattern 3: "filename": "content" (escaped JSON)
        if not files:
            try:
                # Try to find JSON-like structure
                json_match = re.search(r'\{[\s\S]*\}', text)
                if json_match:
                    parsed = json.loads(json_match.group())
                    if isinstance(parsed, dict):
                        for k, v in parsed.items():
                            if isinstance(v, str):
                                files[k] = v
            except:
                pass

        return files
