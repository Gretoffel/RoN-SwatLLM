import json
import time
import os
import urllib.request
import urllib.error

# --- Configuration ---
MOD_DIR = os.path.dirname(os.path.abspath(__file__))
COMMANDS_FILE = os.path.join(MOD_DIR, "commands.txt")

# Set to 'ollama' or 'lmstudio'
PROVIDER = "ollama"

# Ollama settings
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gpt-oss:20b"

# LM Studio settings (OpenAI-compatible)
LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
LM_STUDIO_MODEL = "deepseek/deepseek-r1-0528-qwen3-8b" # Set to the model name shown in LM Studio

SYSTEM_PROMPT = """
You are a Tactical Command AI for the game Ready Or Not. 
Your goal is to translate natural language prompts into a specific command sequence for a SWAT team.

AVAILABLE COMMANDS:
- [TEAM] MOVE X Y Z: Moves the team to coordinates. (TEAM: RED, BLUE, GOLD)
- [TEAM] STACK_UP X Y Z: Stack up on the door at the specified coordinates.
- [TEAM] OPEN_DOOR X Y Z: Open the door at the specified coordinates. does not work if the door is locked
- [TEAM] BREACH X Y Z: Breach and clear the door at the specified coordinates. also works if the door is locked
- [TEAM] FALL_IN: Team follows the player. ONLY USE AT THE END OF THE FULL TASK, when the user requests it, or the team is not supposed to stay where they end up after the full task
- [TEAM] SEARCH_AND_SECURE: Search and secure the area for evidence/suspects. only recommended when all suspects are confirmed to be dead or arrested and/or the user specifically requests it.

Note: Coordinates (X Y Z) for objects like doors are provided in the environment data.

ENVIRONMENT DATA:
You will receive a JSON containing the 'teams' and 'nearby_doors'.
Use the 'location' (X, Y, Z) from the 'nearby_doors' to target specific doors.

OUTPUT FORMAT:
Provide ONLY the list of commands, one per line. No conversation, no explanations.
Example Output:
BLUE MOVE 1500 2400 100
BLUE STACK_UP 1500 2400 100
"""

def sanitize_environment(env):
    """
    Strips sensitive/noisy fields from environment data before sending to the LLM.
    - Removes 'id' from nearby_doors.
    - Collapses team member lists into a single center position + combined status.
    Does NOT modify the original dict.
    """
    sanitized = {}

    # Clean up doors: strip 'id' field
    if 'nearby_doors' in env:
        sanitized['nearby_doors'] = [
            {k: v for k, v in door.items() if k != 'id'}
            for door in env['nearby_doors']
        ]

    # Clean up teams: collapse members into position + combined status
    if 'teams' in env:
        sanitized['teams'] = {}
        for team_name, team_data in env['teams'].items():
            members = team_data.get('members', [])
            # Idle only if ALL members are idle
            all_idle = all(m.get('status', 'BUSY') == 'IDLE' for m in members) if members else True
            sanitized['teams'][team_name] = {
                'center': team_data.get('center'),
                'count': team_data.get('count', 0),
                'status': 'IDLE' if all_idle else 'BUSY'
            }

    # Pass through any other top-level fields (e.g. timestamp, nearby_characters)
    for key in env:
        if key not in ('nearby_doors', 'teams'):
            sanitized[key] = env[key]

    return sanitized

def call_llm(prompt, context_data):
    full_prompt = f"{SYSTEM_PROMPT}\n\nENVIRONMENT DATA:\n{json.dumps(context_data, indent=2)}\n\nUSER PROMPT: {prompt}"

    if PROVIDER == "lmstudio":
        data = {
            "model": LM_STUDIO_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"ENVIRONMENT DATA:\n{json.dumps(context_data, indent=2)}\n\nUSER PROMPT: {prompt}"}
            ],
            "stream": False
        }
        req = urllib.request.Request(
            LM_STUDIO_URL,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                return res_data['choices'][0]['message']['content']
        except Exception as e:
            print(f"Error calling LM Studio: {e}")
            return ""
    else:  # ollama
        data = {
            "model": OLLAMA_MODEL,
            "prompt": full_prompt,
            "stream": False
        }
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                return res_data.get('response', '')
        except Exception as e:
            print(f"Error calling Ollama: {e}")
            return ""

def main():
    USER_PROMPT_FILE = os.path.join(MOD_DIR, "user_prompt.txt")
    ENVIRONMENT_FILE = os.path.join(MOD_DIR, "environment.json")
    print(f"Ollama Bridge started. Provider: {PROVIDER.upper()}. Watching {USER_PROMPT_FILE}...")
    
    while True:
        if os.path.exists(USER_PROMPT_FILE):
            try:
                with open(USER_PROMPT_FILE, 'r', encoding='utf-8') as f:
                    user_prompt = f.read().strip()
            except Exception as e:
                print(f"Error reading user_prompt.txt: {e}")
                time.sleep(1)
                continue

            if user_prompt:
                print(f"Detected prompt: {user_prompt}")

                # Clear the prompt file immediately to avoid re-processing
                try:
                    with open(USER_PROMPT_FILE, 'w', encoding='utf-8') as f:
                        f.write("")
                except Exception as e:
                    print(f"Warning: could not clear user_prompt.txt: {e}")

                # Read environment data (best-effort - may not exist yet)
                environment = {}
                if os.path.exists(ENVIRONMENT_FILE):
                    try:
                        with open(ENVIRONMENT_FILE, 'r', encoding='utf-8') as f:
                            environment = json.load(f)
                    except Exception as e:
                        print(f"Warning: could not read environment.json: {e}")
                else:
                    print("Warning: environment.json not found. Make sure the game is running in a mission.")

                llm_environment = sanitize_environment(environment)
                llm_output = call_llm(user_prompt, llm_environment)

                if llm_output:
                    print("Received commands from Ollama:")
                    print(llm_output)
                    try:
                        with open(COMMANDS_FILE, 'w', encoding='utf-8') as f:
                            f.write(llm_output.strip())
                        print(f"Commands written to {COMMANDS_FILE}")
                    except Exception as e:
                        print(f"Error writing commands.txt: {e}")
                else:
                    print("No output received from Ollama.")

        time.sleep(1)

if __name__ == "__main__":
    main()
