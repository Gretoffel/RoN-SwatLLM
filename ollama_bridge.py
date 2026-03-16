import json
import time
import os
import urllib.request
import urllib.error
import re
import math
from typing import Any, Dict, List, Tuple, cast

# --- Configuration ---
MOD_DIR = os.path.dirname(os.path.abspath(__file__))
COMMANDS_FILE = os.path.join(MOD_DIR, "commands.txt")

# Set to 'ollama' or 'lmstudio'
PROVIDER = "ollama"

# Ollama settings
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gpt-oss:20b"
OLLAMA_THINK = "low" # Set to "low", "medium", or "high" for reasoning models

# LM Studio settings (OpenAI-compatible)
LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
LM_STUDIO_MODEL = "deepseek/deepseek-r1-0528-qwen3-8b" # Set to the model name shown in LM Studio


SYSTEM_PROMPT = """
You are a Tactical Command AI for a SWAT team.
Your goal is to translate natural language prompts and current situational context into specific commands for RED and BLUE teams.
We use a "Single-Call System" ("Gold Commander"): you must process both teams simultaneously.

CONTEXT STRUCTURE:
You will receive a room-centric view of the situation. Only rooms containing teams are shown.
- ROOM: [Name]
- Teams in this room: [List of teams currently here]
- Doors in this room: [List of doors with IDs, where they lead, relative direction, distance, and states like OPEN, LOCKED, or DOUBLE-DOOR]

AVAILABLE COMMANDS:
- [TEAM] STACK_UP [DOOR_ID]: Stack up on a door.
- [TEAM] OPEN_DOOR [DOOR_ID]: Open a door (fails if locked).
- [TEAM] BREACH [DOOR_ID]: Breach and clear a door (works on locked doors).
- [TEAM] FALL_IN: Team returns to player.
- [TEAM] SEARCH_AND_SECURE: Search area for suspects/evidence.

CRITICAL RULES FOR COMMANDS:
1. NEVER use placeholders like [TEAM]. You MUST explicitly use GOLD, RED, or BLUE.
   - Use GOLD if the user says "all teams" or you want both teams at the same door.
2. ONLY issue the IMMEDIATE NEXT ACTION per team. DO NOT output multiple steps for the same team in one turn.
3. If the user asks for sequential steps ("... THEN ..."), issue ONLY the first one. Save subsequent steps in the 'new_objective' memory.
4. Use the exact DOOR_ID as provided in the room-centric context.

OUTPUT FORMAT:
Your final output MUST EXACTLY follow this structure:

done:
- [List of completed actions]

new_objective:
- [Overarching goal for future turns]

commands:
[Commands list, e.g., RED STACK_UP Door_1. If no command: NONE]
"""

# Global memory state
memory_done = []
memory_objective = "None"

def get_door_direction_and_sort(doors, player_center, player_forward):
    if not player_center or not player_forward:
        for door in doors:
            door['semantic_direction'] = door.get('direction', 'unknown')
        return doors

    sectors = {
        'Front': [], 'Front-Right': [], 'Right': [], 'Back-Right': [],
        'Back': [], 'Back-Left': [], 'Left': [], 'Front-Left': []
    }

    for door in doors:
        dx = door['location']['X'] - player_center['X']
        dy = door['location']['Y'] - player_center['Y']
        
        mag = math.sqrt(dx*dx + dy*dy)
        if mag < 1.0:
            door['angle'] = 0.0
            sectors['Front'].append(door)
            continue
            
        dx /= mag
        dy /= mag
        fx = player_forward['X']
        fy = player_forward['Y']
        
        dot = fx * dx + fy * dy
        crossZ = fx * dy - fy * dx
        angle = math.degrees(math.atan2(crossZ, dot))
        door['angle'] = angle
        
        if -22.5 <= angle < 22.5: sec = 'Front'
        elif 22.5 <= angle < 67.5: sec = 'Front-Right'
        elif 67.5 <= angle < 112.5: sec = 'Right'
        elif 112.5 <= angle < 157.5: sec = 'Back-Right'
        elif angle >= 157.5 or angle < -157.5: sec = 'Back'
        elif -157.5 <= angle < -112.5: sec = 'Back-Left'
        elif -112.5 <= angle < -67.5: sec = 'Left'
        else: sec = 'Front-Left'
        
        sectors[sec].append(door)

    processed_doors = []
    for sec_name, sec_doors in sectors.items():
        if not sec_doors: continue
        sec_doors.sort(key=lambda d: d['angle'])
        
        if len(sec_doors) == 1:
            sec_doors[0]['semantic_direction'] = sec_name
        elif len(sec_doors) == 2:
            sec_doors[0]['semantic_direction'] = sec_name + " (Leftmost)"
            sec_doors[1]['semantic_direction'] = sec_name + " (Rightmost)"
        elif len(sec_doors) == 3:
            sec_doors[0]['semantic_direction'] = sec_name + " (Leftmost)"
            sec_doors[1]['semantic_direction'] = sec_name + " (Center)"
            sec_doors[2]['semantic_direction'] = sec_name + " (Rightmost)"
        else:
            sec_doors[0]['semantic_direction'] = sec_name + " (Leftmost)"
            for i in range(1, len(sec_doors) - 1):
                sec_doors[i]['semantic_direction'] = sec_name + " (Center-" + str(i) + ")"
            sec_doors[-1]['semantic_direction'] = sec_name + " (Rightmost)"
        processed_doors.extend(sec_doors)
            
    processed_doors.sort(key=lambda d: d.get('distance', 999))
    return processed_doors

def build_semantic_context(env: Dict[str, Any], graph_data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    teams: Dict[str, Any] = env.get('teams', {})
    player: Dict[str, Any] = teams.get('GOLD', {})
    player_center: Dict[str, float] = player.get('center', {})
    player_forward: Dict[str, float] = player.get('forward', {})
    edges: List[Dict[str, Any]] = graph_data.get('edges', [])
    nearby_doors: List[Dict[str, Any]] = env.get('nearby_doors', [])
    
    # Get 8-way relative sectors for all nearby doors
    processed_doors = get_door_direction_and_sort(nearby_doors, player_center, player_forward)
    door_info_map: Dict[str, Dict[str, Any]] = {str(d['id']): cast(Dict[str, Any], d) for d in processed_doors}
    
    # 1. Map rooms to teams (reuse logic from debug info)
    room_to_teams: Dict[str, List[str]] = {}
    for t_name in ['GOLD', 'RED', 'BLUE']:
        if t_name in teams:
            t_data = teams[t_name]
            center = t_data.get('center', {})
            if not center: continue
            
            # Find closest room
            edge_dists: List[Tuple[float, Dict[str, Any]]] = []
            for e in edges:
                eloc = e.get('location', {})
                dx = eloc.get('X', 0.0) - center.get('X', 0.0)
                dy = eloc.get('Y', 0.0) - center.get('Y', 0.0)
                edge_dists.append(((dx*dx + dy*dy)**0.5, e))
            
            edge_dists.sort(key=lambda x: x[0])
            rooms_count: Dict[str, int] = {}
            for i in range(min(4, len(edge_dists))):
                dist_val, e_data = edge_dists[i]
                if dist_val > 1500.0: continue 
                for r in [e_data.get('roomA'), e_data.get('roomB')]:
                    if isinstance(r, str) and r != "Unknown":
                        rooms_count[r] = rooms_count.get(r, 0) + 1
            
            curr_room = max(rooms_count.items(), key=lambda x: x[1])[0] if rooms_count else "Unknown"
            if curr_room not in room_to_teams:
                room_to_teams[curr_room] = []
            
            # Use explicit cast for Pyre2 strict generic checking
            t_list = cast(List[str], room_to_teams[curr_room])
            t_list.append(str(t_name))

    # 2. Construct context lines
    door_coords_map: Dict[str, Any] = {}
    context_lines: List[str] = []
    context_lines.append("=== CURRENT TACTICAL ROOMS (Rooms with Teams) ===")
    
    context_lines.append("\n[MEMORY OF CURRENT TASK]")
    done_str = ", ".join(memory_done) if memory_done else "Nothing"
    context_lines.append(f"Done so far: {done_str}")
    context_lines.append(f"Current Objective: {memory_objective}")
    
    # Only iterate through rooms where teams are actually located
    for room, teams_list in room_to_teams.items():
        if room == "Unknown": continue
        
        team_str = ", ".join(teams_list).replace("GOLD", "PLAYER")
        context_lines.append(f"\nROOM: {room}")
        context_lines.append(f"Teams in this room: {team_str}")
        
        # Find doors connected to this room
        room_edges = [e for e in edges if e.get('roomA') == room or e.get('roomB') == room]
        context_lines.append("Doors in this room:")
        
        found_doors = False
        for e in room_edges:
            eloc = e.get('location', {})
            ra, rb = e.get('roomA'), e.get('roomB')
            leads_to = rb if ra == room else ra
            
            # Match edge with a door ID from environment
            matched_d_id = None
            for d_id, d_data in door_info_map.items():
                dloc = d_data.get('location', {})
                if ((eloc.get('X', 0) - dloc.get('X', 0))**2 + (eloc.get('Y', 0) - dloc.get('Y', 0))**2)**0.5 < 100:
                    matched_d_id = d_id
                    break
            
            if matched_d_id:
                found_doors = True
                # Use cast to satisfy Pyre2's strict type checking on dict access
                d = cast(Dict[str, Any], door_info_map[str(matched_d_id)])
                dist = d.get('distance', '?')
                sem_dir = d.get('semantic_direction', 'Unknown')
                
                states = []
                states.append('OPEN' if d.get('is_open') else 'CLOSED')
                if d.get('locked'): states.append('LOCKED')
                if d.get('is_double_door'): states.append('DOUBLE-DOOR')
                if d.get('is_broken'): states.append('BROKEN')
                if d.get('is_wedged'): states.append('WEDGED')
                
                state_str = ", ".join(states)
                context_lines.append(f"- '{matched_d_id}': leads to {leads_to} | {sem_dir} ({dist}m) | [{state_str}]")
                
                # Ensure door_coords_map handles potentially None or Unknown locations safely
                dloc = d.get('location', {})
                if matched_d_id and dloc:
                    door_coords_map[str(matched_d_id)] = dloc
        
        if not found_doors:
            context_lines.append("- No specific doors filtered for this room.")

    chars = env.get('nearby_characters', [])
    if chars:
        context_lines.append("\n[NEARBY CHARACTERS / SUSPECTS]")
        for c in chars:
            c_type = c.get('type', 'UNKNOWN')
            c_dir = c.get('direction', 'unknown')
            c_dist = c.get('distance', '?')
            c_state = ['SURRENDERED' if c.get('is_surrendered') else ('COMPLYING' if c.get('is_complying') else f"ACTIVE / {c.get('combat_state', 'UNKNOWN')}")]
            context_lines.append(f"- {c_type} at {c_dir} ({c_dist}m) -> Status: {', '.join(c_state)}")

    return "\n".join(context_lines), door_coords_map

def strip_thoughts(text):
    """
    Removes <think>...</think> blocks from the text.
    Handles multiple blocks and unclosed tags.
    """
    if not text:
        return ""
    
    # Remove complete <think>...</think> blocks (non-greedy)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    # Remove unclosed <think> tags (if the model gets cut off)
    text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
    
    return text.strip()

def call_llm(prompt, context_text):
    full_prompt = f"{SYSTEM_PROMPT}\n\n{context_text}\n\nUSER PROMPT: {prompt}"
    
    # Save to lastPrompt.txt for debugging
    prompt_file = os.path.join(MOD_DIR, "lastPrompt.txt")
    try:
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(full_prompt)
    except Exception as e:
        print(f"Failed to write lastPrompt.txt: {e}")

    if PROVIDER == "lmstudio":
        data = {
            "model": LM_STUDIO_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{context_text}\n\nUSER PROMPT: {prompt}"}
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
                return strip_thoughts(res_data['choices'][0]['message']['content'])
        except Exception as e:
            print(f"Error calling LM Studio: {e}")
            return ""
    else:  # ollama
        data = {
            "model": OLLAMA_MODEL,
            "prompt": full_prompt,
            "stream": False,
            "think": OLLAMA_THINK
        }
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                return strip_thoughts(res_data.get('response', ''))
        except Exception as e:
            print(f"Error calling Ollama: {e}")
            return ""

def update_memory_from_response(text):
    global memory_done, memory_objective
    current_section = None
    new_done = []
    new_obj = []
    
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        
        lower_line = line.lower()
        if lower_line.startswith('done:'):
            current_section = 'done'
            continue
        elif lower_line.startswith('new_objective:'):
            current_section = 'objective'
            continue
        elif lower_line.startswith('commands:'):
            current_section = 'commands'
            continue
            
        if current_section == 'done':
            clean_item = line.lstrip('-*').strip()
            if clean_item and clean_item.lower() != "none" and clean_item.lower() != "[none]":
                new_done.append(clean_item)
        elif current_section == 'objective':
            clean_item = line.lstrip('-*').strip()
            if clean_item and clean_item.lower() != "none" and clean_item.lower() != "[none]":
                new_obj.append(clean_item)
                
    if new_done: memory_done = new_done
    if new_obj: memory_objective = " ".join(new_obj)

def extract_commands_from_response(text, door_map):
    in_commands_section = False
    game_commands: List[str] = []
    
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        
        if line.lower().startswith('commands:'):
            in_commands_section = True
            continue
            
        if line.lower().startswith('done:') or line.lower().startswith('new_objective:'):
            in_commands_section = False
            continue
            
        if in_commands_section:
            # Strip dash/asterisk from bulleted lists
            if line.startswith('- ') or line.startswith('* '):
                line = line[2:].strip()
                
            if line.upper() == "NONE":
                continue
                
            # Proactively fix [TEAM] placeholders or missing team names
            if line.startswith("[TEAM]") or line.startswith("TEAM"):
                line = line.replace("[TEAM]", "GOLD").replace("TEAM", "GOLD")
            
            parts = line.split()
            if len(parts) >= 1:
                team = parts[0].upper()
                # Fallback if first word isn't a known team - assume GOLD for extraction
                if team not in ["RED", "BLUE", "GOLD"]:
                    team = "GOLD"
                
                if len(parts) >= 2:
                    action = parts[1].upper()
                    
                    if action in ["FALL_IN", "SEARCH_AND_SECURE", "HOLD"]:
                        game_commands.append(str(team) + " " + str(action))
                    elif len(parts) >= 3:
                        door_id = str(parts[2].replace("'", "").replace('"', ""))
                        if door_id in door_map:
                            loc = door_map[door_id]
                            cmd_str = str(team) + " " + str(action) + " " + str(loc['X']) + " " + str(loc['Y']) + " " + str(loc['Z'])
                            game_commands.append(cmd_str)
                        else:
                            # If door_id lookup failed, maybe the action and ID were swapped or model formatted weirdly
                            # We don't want to crash, so we just append as is but it might fail in LUA
                            game_commands.append(str(team) + " " + str(action) + " " + str(door_id))
                    else:
                        # Single word commands that might just be the action?
                        game_commands.append(str(line))
            
    return "\n".join(game_commands)


def print_debug_info(env: Dict[str, Any], graph_data: Dict[str, Any]):
    teams: Dict[str, Any] = env.get('teams', {})
    edges: List[Dict[str, Any]] = graph_data.get('edges', [])
    nearby_doors: List[Dict[str, Any]] = env.get('nearby_doors', [])
    
    # Map door IDs to their states for easier lookup
    door_states: Dict[str, Any] = {str(d['id']): d for d in nearby_doors}
    
    room_to_teams: Dict[str, List[str]] = {}
    
    for t_name in ['GOLD', 'RED', 'BLUE']:
        if t_name in teams:
            t_data: Dict[str, Any] = teams[t_name]
            center: Dict[str, float] = t_data.get('center', {})
            if not center: continue
            
            # Find closest room for this team
            edge_dists: List[Tuple[float, Dict[str, Any]]] = []
            for e in edges:
                eloc: Dict[str, float] = e.get('location', {})
                dx = eloc.get('X', 0.0) - center.get('X', 0.0)
                dy = eloc.get('Y', 0.0) - center.get('Y', 0.0)
                dist = float((dx*dx + dy*dy)**0.5)
                edge_dists.append((dist, e))
            
            edge_dists.sort(key=lambda x: x[0])
            
            rooms_count: Dict[str, int] = {}
            max_idx = min(4, len(edge_dists))
            for i in range(max_idx):
                dist_val, e_data = edge_dists[i]
                if dist_val > 1500.0: continue 
                for r in [e_data.get('roomA'), e_data.get('roomB')]:
                    if isinstance(r, str) and r != "Unknown":
                        rooms_count[r] = rooms_count.get(r, 0) + 1
            
            current_room = "Unknown"
            if rooms_count:
                current_room = max(rooms_count.items(), key=lambda x: x[1])[0]
            
            if current_room not in room_to_teams:
                room_to_teams[current_room] = []
            
            # Use explicit cast to satisfy Pyre2's strict generic checking
            target_list = cast(List[str], room_to_teams[current_room])
            target_list.append(str(t_name))

    print("-" * 30 + " TACTICAL OVERVIEW " + "-" * 30)
    for room, teams_list in room_to_teams.items():
        team_str = " and ".join(teams_list).replace("GOLD", "Player")
        print(f"Room: {room} (Teams: {team_str})")
        
        # Show detailed door info for this room
        room_edges = [e for e in edges if e.get('roomA') == room or e.get('roomB') == room]
        for e in room_edges:
            ra, rb = e.get('roomA'), e.get('roomB')
            other = rb if ra == room else ra
            
            # Find door ID in graph if possible, or match by location
            # Note: environment.json IDs are often "BP_Door_NewX"
            # We match by looking for nearby_doors with similar location
            eloc = e.get('location', {})
            matched_door_id = "Unknown"
            state_str = "Unknown"
            dist_val = -1.0
            
            for d_id, d_data in door_states.items():
                dloc = d_data.get('location', {})
                d_dx = eloc.get('X', 0) - dloc.get('X', 0)
                d_dy = eloc.get('Y', 0) - dloc.get('Y', 0)
                if (d_dx*d_dx + d_dy*d_dy)**0.5 < 100: # 1 meter tolerance
                    matched_door_id = d_id
                    locked = "Locked" if d_data.get('locked') else "Unlocked"
                    open_st = "Open" if d_data.get('is_open') else "Closed"
                    state_str = f"{open_st}, {locked}"
                    dist_val = float(d_data.get('distance', -1.0))
                    break
            
            dist_info = " (" + str(dist_val) + "m)" if dist_val >= 0.0 else ""
            print("  -> Door " + str(matched_door_id) + str(dist_info) + ": leads to " + str(other) + " [" + str(state_str) + "]")
            
    print("-" * 79)


def main():
    USER_PROMPT_FILE = os.path.join(MOD_DIR, "user_prompt.txt")
    ENVIRONMENT_FILE = os.path.join(MOD_DIR, "environment.json")
    GRAPH_FILE = os.path.join(MOD_DIR, "environment_graph.json")
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

                # Read environment graph data
                graph_data = {}
                if os.path.exists(GRAPH_FILE):
                    try:
                        with open(GRAPH_FILE, 'r', encoding='utf-8') as f:
                            graph_data = json.load(f)
                    except Exception as e:
                        print(f"Warning: could not read environment_graph.json: {e}")
                else:
                    print("Warning: environment_graph.json not found.")

                print_debug_info(environment, graph_data)

                context_text, door_map = build_semantic_context(environment, graph_data)
                
                response_text = call_llm(user_prompt, context_text)

                if response_text:
                    print("-" * 30 + " LLM RESPONSE " + "-" * 30)
                    print(response_text)
                    print("-" * 74)
                    
                    update_memory_from_response(response_text)
                    final_commands_str = extract_commands_from_response(response_text, door_map)

                    print("-" * 30 + " PARSED COMMANDS " + "-" * 27)
                    if final_commands_str:
                        print(final_commands_str)
                    else:
                        print("(No commands to execute)")
                    print("-" * 74)

                    try:
                        with open(COMMANDS_FILE, 'w', encoding='utf-8') as f:
                            f.write(final_commands_str)
                    except Exception as e:
                        print(f"Error writing commands.txt: {e}")
                else:
                    print("No output received from Ollama.")

        time.sleep(1)

if __name__ == "__main__":
    main()
