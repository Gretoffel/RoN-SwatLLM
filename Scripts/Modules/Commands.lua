local Utils = require("Modules.Utils")
local Config = require("Modules.Config")

local Commands = {}

Commands.TeamMap = {
    RED = 1,
    BLUE = 2,
    GOLD = 5
}

function Commands.ExportAllDoors()
    local doors = FindAllOf("Door")
    if not doors then
        Utils.Log("No doors found to export.")
        return
    end
    
    local file, err = io.open(Config.doorsFilepath, "w")
    if file then
        file:write("# List of all available main doors and their approximate center coordinates:\n")
        local count = 0
        local seenLocs = {} -- Deduplicate to avoid printing frame and leaf at same spot
        for _, door in ipairs(doors) do
            if door:IsValid() and door:IsA("/Script/ReadyOrNot.Door") then
                local interactiveDoor = door
                if door.bMainSubDoor == true then
                    interactiveDoor = door
                elseif door.DriveSubDoor and door.DriveSubDoor:IsValid() then
                    interactiveDoor = door.DriveSubDoor
                end
                
                local loc = interactiveDoor:K2_GetActorLocation()
                local locKey = string.format("%.0f,%.0f,%.0f", loc.X, loc.Y, loc.Z)
                if not seenLocs[locKey] then
                    seenLocs[locKey] = true
                    local name = interactiveDoor:GetFullName()
                    file:write(string.format("%s: %.2f %.2f %.2f\n", name, loc.X, loc.Y, loc.Z))
                    count = count + 1
                end
            end
        end
        file:close()
        Utils.Log("Exported " .. tostring(count) .. " unique doors to doors.txt")
    else
        Utils.Log("Failed to open doors.txt for writing.")
    end
end

function Commands.ExecuteAction(teamName, action, args)
    local team = Commands.TeamMap[teamName] or Commands.TeamMap["GOLD"]
    local cmd = string.upper(action)
    
    if cmd == "GET_DOORS" then
        Commands.ExportAllDoors()
        return
    end
    
    -- Parse coordinates from args if available
    local specificTargetLoc = nil
    if args and #args >= 3 then
        local nx = tonumber(args[1])
        local ny = tonumber(args[2])
        local nz = tonumber(args[3])
        if nx and ny and nz then
            specificTargetLoc = { X = nx, Y = ny, Z = nz }
            Utils.Log(string.format("Action %s Team %s - Target: %.2f %.2f %.2f", cmd, teamName, nx, ny, nz))
        end
    end
    
    local manager = Utils.GetCommandStruct()
    local pc = Utils.GetPlayerController()
    
    if not manager or not pc then
        Utils.Log("Could not get SWATManager or PlayerController.")
        return
    end
    
    local pawn = pc.Pawn
    if not pawn or not pawn:IsValid() then
        Utils.Log("Player Pawn not found.")
        return
    end
    
    local pawnLoc = pawn:K2_GetActorLocation()
    
    -- Determine target location
    local targetLoc = nil
    if specificTargetLoc ~= nil then
        targetLoc = {
            X = specificTargetLoc.X,
            Y = specificTargetLoc.Y,
            Z = specificTargetLoc.Z + 50.0
        }
    else
        local forward = pawn:GetActorForwardVector()
        local dist = 600.0
        targetLoc = {
            X = pawnLoc.X + forward.X * dist,
            Y = pawnLoc.Y + forward.Y * dist,
            Z = pawnLoc.Z
        }
    end
    
    if cmd == "FALL_IN" then
        Utils.Log("Executing FALL_IN for Team " .. tostring(team))
        manager:GiveFallInCommand(team, 1)
        
    elseif cmd == "HOLD" then
        Utils.Log("Executing HOLD for Team " .. tostring(team))
        manager:GiveHoldCommand(team)
        
    elseif cmd == "MOVE" then
        Utils.Log("Executing MOVE for Team " .. tostring(team))
        manager:GiveMoveCommand(team, targetLoc)

    elseif cmd == "COVER" then
        Utils.Log("Executing COVER for Team " .. tostring(team))
        manager:GiveMoveCommand(team, targetLoc)
        manager:GiveCoverAreaCommand(team, targetLoc)

    elseif cmd == "SEARCH_AND_SECURE" then
        Utils.Log("Executing SEARCH_AND_SECURE for Team " .. tostring(team))
        manager:GiveSearchAndSecureCommand(team, pawnLoc, true)
        
    elseif cmd == "OPEN_DOOR" then
        local searchRadius = specificTargetLoc and 350 or 1000
        local searchLoc = specificTargetLoc or pawnLoc
        local door = Utils.FindNearestDoor(searchLoc, searchRadius)
        if door then
            Utils.Log("Executing OPEN_DOOR on nearest door.")
            manager:GiveOpenDoorCommand(door, team, pawnLoc)
        else
            Utils.Log("No door found nearby to open.")
        end

    elseif cmd == "BREACH" then
        local searchRadius = specificTargetLoc and 350 or 1000
        local searchLoc = specificTargetLoc or pawnLoc
        local door = Utils.FindNearestDoor(searchLoc, searchRadius)
        if door then
            Utils.Log("Executing BREACH on nearest door.")
            manager:GiveBreachAndClearCommand(door, 1, team, pawnLoc, nil, nil, false, false, false, false, 0)
        else
            Utils.Log("No door found nearby to breach.")
        end

    elseif cmd == "STACK_UP" then
        local searchRadius = specificTargetLoc and 350 or 1000
        local searchLoc = specificTargetLoc or pawnLoc
        local door = Utils.FindNearestDoor(searchLoc, searchRadius)
        if door then
            Utils.Log("Executing STACK_UP on nearest door.")
            manager:GiveStackUpCommand(door, team, pawnLoc, pawn:GetActorUpVector(), true, 0)
        else
            Utils.Log("No door found nearby to stack up.")
        end
        
    elseif cmd == "YELL" then
        Utils.Log("Executing YELL command.")
        pawn:OnYellExecute()
        
    else
        Utils.Log("Unknown command: " .. cmd)
    end
end

-- Backward compatibility and Hotkey support
function Commands.ExecuteCommand(commandString)
    -- This is now a wrapper that parses a string and calls ExecuteAction immediately
    -- Note: This bypasses the queue (useful for hotkeys)
    local cleanStr = string.gsub(commandString, "#.*$", "")
    cleanStr = string.gsub(cleanStr, "['\"]", "")
    cleanStr = string.match(cleanStr, "^%s*(.-)%s*$")
    if not cleanStr or cleanStr == "" then return end

    local parts = {}
    for token in string.gmatch(cleanStr, "%S+") do
        table.insert(parts, string.upper(token))
    end

    local teamName = "GOLD"
    local action = nil
    local args = {}
    local startIdx = 1

    if Commands.TeamMap[parts[1]] then
        teamName = parts[1]
        action = parts[2]
        startIdx = 3
    else
        action = parts[1]
        startIdx = 2
    end

    if not action then return end

    for i = startIdx, #parts do
        table.insert(args, parts[i])
    end

    Commands.ExecuteAction(teamName, action, args)
end

return Commands
