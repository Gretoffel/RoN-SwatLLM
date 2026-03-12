local Config = {}

-- Mod Directories
Config.baseDir = "d:\\SteamLibrary\\steamapps\\common\\Ready Or Not\\ReadyOrNot\\Binaries\\Win64\\ue4ss\\Mods\\SwatLLM\\"
Config.filepath = Config.baseDir .. "commands.txt"
Config.doorsFilepath = Config.baseDir .. "doors.txt"

-- P Hotkey Configuration
-- Format: "TEAM COMMAND" or "COMMAND" (defaults to GOLD)
Config.P_Key_Action1 = "GOLD MOVE"
Config.P_Key_Action2 = "NONE"

-- Environment Sensing Configuration
Config.SCAN_INTERVAL = 3.0   -- How often to update the environment.json (seconds)
Config.SCAN_RADIUS = 4000.0   -- Range to detect objects (4000 units = 40 meters)
Config.SCAN_DOORS = true
Config.SCAN_CHARACTERS = false -- User disabled characters
Config.SCAN_SWAT = false       -- Toggle scanning of SWAT bots
Config.SCAN_EVIDENCE = true

-- Performance Settings
Config.ACTOR_CACHE_INTERVAL = 20.0 -- Refresh the list of all world actors every 20s

return Config
