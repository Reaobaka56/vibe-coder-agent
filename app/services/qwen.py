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

    def _call(self, system_prompt: str, user_prompt: str, max_tokens: int = None, image_url: str = None) -> str:
        """Call Ollama or DashScope API."""
        tokens = max_tokens or self.max_tokens

        if "dashscope" in self.api_url.lower():
            # DashScope API
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Multi-modal payload structure
            if image_url:
                user_content = [{"image": image_url}, {"text": user_prompt}]
                sys_content = [{"text": system_prompt}]
                model = "qwen-vl-plus" # Vision model
            else:
                user_content = user_prompt
                sys_content = system_prompt
                model = self.model

            payload = {
                "model": model,
                "input": {
                    "messages": [
                        {"role": "system", "content": sys_content},
                        {"role": "user", "content": user_content}
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
            # Ollama API (Skipping image handling for local ollama MVP)
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

    def plan_project(self, description: str) -> Dict:
        """Plan a new project and define memory context."""
        system = self._load_prompt("system_plan_project.txt")
        user = f"Description: {description}"
        
        raw = self._call(system, user, max_tokens=2048)
        
        try:
            return self._parse_json(raw)
        except json.JSONDecodeError:
            # Basic fallback if parsing fails
            return {
                "project_memory": {},
                "plan_description": description
            }

    def plan_architecture(self, plan_description: str, project_memory: Dict) -> Dict:
        """Plan the technical architecture (files and dependencies) based on the project plan."""
        system = self._load_prompt("system_plan_architecture.txt")
        memory_str = json.dumps(project_memory, indent=2)
        user = f"Project Memory:\n{memory_str}\n\nProject Plan:\n{plan_description}"
        
        raw = self._call(system, user, max_tokens=2048)
        
        try:
            return self._parse_json(raw)
        except json.JSONDecodeError:
            return {"file_tree": [], "dependencies": {}, "architecture_notes": ""}

    def generate_project(self, plan_description: str, arch_plan: Dict, project_memory: Dict, project_type: str = "nextjs") -> Dict[str, str]:
        """Generate complete file structure from plan and architecture."""
        system = self._load_prompt("system_new_project.txt")
        memory_str = json.dumps(project_memory, indent=2)
        arch_str = json.dumps(arch_plan, indent=2)
        user = f"Project type: {project_type}\nProject Memory:\n{memory_str}\n\nPlan:\n{plan_description}\n\nArchitecture Spec:\n{arch_str}"

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

    def plan_edit(self, instruction: str, files: Dict[str, str], project_memory: Dict, image_url: str = None) -> Dict:
        """Plan an edit operation."""
        system = self._load_prompt("system_plan_edit.txt")
        file_list = "\n".join(files.keys())
        memory_str = json.dumps(project_memory, indent=2)
        user = f"Instruction: {instruction}\n\nProject Memory:\n{memory_str}\n\nCurrent Files:\n{file_list}"
        
        raw = self._call(system, user, max_tokens=2048, image_url=image_url)
        
        try:
            return self._parse_json(raw)
        except json.JSONDecodeError:
            # Fallback
            return {"files_to_edit": [{"filename": list(files.keys())[0], "instruction": instruction}]} if files else {"files_to_edit": []}

    def edit_file(self, filename: str, current_content: str, instruction: str, project_memory: Dict) -> str:
        """Precise file edit based on instruction."""
        system = self._load_prompt("system_edit_file.txt")
        memory_str = json.dumps(project_memory, indent=2)
        user = f"""Project Memory:\n{memory_str}\n\nFile: {filename}
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

    def review_code(self, filename: str, old_content: str, new_content: str, instruction: str) -> str:
        """Review and fix the coder's output."""
        system = self._load_prompt("system_review_code.txt")
        user = f"Filename: {filename}\nInstruction: {instruction}\n\nOld Content:\n```\n{old_content}\n```\n\nCoder's Output:\n```\n{new_content}\n```"
        
        result = self._call(system, user, max_tokens=self.max_tokens).strip()

        # Clean up markdown fences if present
        if result.startswith("```"):
            lines = result.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            result = "\n".join(lines)

        return result.strip()

    def test_code(self, files: Dict[str, str], instruction: str) -> Dict[str, str]:
        """Holistic static analysis of all generated code to catch missing imports or syntax issues."""
        system = self._load_prompt("system_test_code.txt")
        files_json = json.dumps(files, indent=2)
        user = f"Instruction Context:\n{instruction}\n\nGenerated Files:\n{files_json}"
        
        raw = self._call(system, user, max_tokens=8192)
        
        try:
            return self._parse_json(raw)
        except json.JSONDecodeError:
            # Fallback to returning original files
            return files

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

    def _parse_json(self, raw: str) -> dict:
        """Robustly parse JSON by stripping markdown fences."""
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines)
        
        # Sometimes the LLM includes prefix text before the JSON
        start_idx = raw.find("{")
        end_idx = raw.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            raw = raw[start_idx:end_idx+1]

        return json.loads(raw)
