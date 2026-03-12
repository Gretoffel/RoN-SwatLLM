local StatusScanner = require("Modules.StatusScanner")
local Utils = require("Modules.Utils")
local Config = require("Modules.Config")

local EnvironmentScanner = {}

-- Cache for environmental data
EnvironmentScanner.TacticalData = {
    teams = {},
    nearby_doors = {},
    nearby_characters = {},
    nearby_evidence = {},
    last_update_time = 0
}

-- Optimization Cache for Actor Lists
local CachedActors = {
    doors = {},
    suspects = {},
    civilians = {},
    initialized = false
}

-- Perform a ONE-TIME full scan of the world to find interactive actors
function EnvironmentScanner.InitializeCache(force)
    if not force and CachedActors.initialized then return end

    Utils.Log("Initializing Environment Actor Cache (Full World Scan)...")
    
    -- Doors: RoN doors are typically of class "Door"
    CachedActors.doors = FindAllOf("Door") or {}
    
    -- Characters
    CachedActors.suspects = FindAllOf("SuspectCharacter") or {}
    CachedActors.civilians = FindAllOf("CivilianCharacter") or {}

    CachedActors.initialized = true
    
    Utils.Log(string.format("Cache Initialized: %d Doors, %d Suspects, %d Civilians", 
        #CachedActors.doors, #CachedActors.suspects, #CachedActors.civilians))
end

-- Calculate team's average position and orientation
function EnvironmentScanner.GetTeamTacticalStatus(teamName)
    if not StatusScanner.IsCacheValid() then
        StatusScanner.UpdateCache()
    end

    local members = {}
    local avgPos = {X = 0, Y = 0, Z = 0}
    local avgForward = {X = 0, Y = 0, Z = 0}
    local count = 0

    for _, controller in ipairs(StatusScanner.CachedControllers) do
        local ctrlTeam = StatusScanner.GetControllerTeam(controller)
        if teamName == "GOLD" or ctrlTeam == teamName then
            local pawn = controller.Pawn
            if pawn and pawn:IsValid() then
                local loc = pawn:K2_GetActorLocation()
                local fwd = pawn:GetActorForwardVector()
                local posName = StatusScanner.GetControllerPosition(controller)
                
                table.insert(members, {
                    name = posName,
                    status = StatusScanner.IsControllerIdle(controller) and "IDLE" or "BUSY",
                    activity = StatusScanner.GetTeamActivity(ctrlTeam),
                    location = {X = loc.X, Y = loc.Y, Z = loc.Z}
                })

                avgPos.X = avgPos.X + loc.X
                avgPos.Y = avgPos.Y + loc.Y
                avgPos.Z = avgPos.Z + loc.Z
                
                avgForward.X = avgForward.X + fwd.X
                avgForward.Y = avgForward.Y + fwd.Y
                avgForward.Z = avgForward.Z + fwd.Z
                
                count = count + 1
            end
        end
    end

    if count > 0 then
        avgPos.X = avgPos.X / count
        avgPos.Y = avgPos.Y / count
        avgPos.Z = avgPos.Z / count
        
        -- Normalize forward vector
        local mag = math.sqrt(avgForward.X^2 + avgForward.Y^2 + avgForward.Z^2)
        if mag > 0 then
            avgForward.X = avgForward.X / mag
            avgForward.Y = avgForward.Y / mag
            avgForward.Z = avgForward.Z / mag
        end

        return {
            center = avgPos,
            forward = avgForward,
            members = members,
            count = count
        }
    end
    return nil
end

-- Scan for nearby tactical objects from CACHED actors only
function EnvironmentScanner.ScanEnvironment()
    -- Ensure we have the base actors (only runs once unless forced)
    EnvironmentScanner.InitializeCache()

    local teams = { "RED", "BLUE", "GOLD" }
    local tacticalState = {
        teams = {},
        nearby_doors = {},
        nearby_characters = {},
        nearby_evidence = {}, -- Evidence logic would require another cache or one-time scan
        timestamp = os.time()
    }

    -- 1. Get Team Statuses for scan origin (export conditionally)
    local internalTeams = {}
    for _, tName in ipairs(teams) do
        local status = EnvironmentScanner.GetTeamTacticalStatus(tName)
        if status then
            internalTeams[tName] = status
            if Config.SCAN_SWAT then
                tacticalState.teams[tName] = status
            end
        end
    end

    -- Use GOLD team center as the primary scan point if available, else RED or BLUE
    local scanOrigin = nil
    if internalTeams.GOLD then
        scanOrigin = internalTeams.GOLD.center
    elseif internalTeams.RED then
        scanOrigin = internalTeams.RED.center
    elseif internalTeams.BLUE then
        scanOrigin = internalTeams.BLUE.center
    end

    if not scanOrigin then return end
    
    local radiusSq = Config.SCAN_RADIUS * Config.SCAN_RADIUS

    -- 2. Update Door States (from cache)
    if Config.SCAN_DOORS then
        local roomPosMap = {
            [0] = "Center", [1] = "CornerLeft", [2] = "CornerRight",
            [3] = "Hallway", [4] = "HallwayLeft", [5] = "HallwayRight"
        }

        local doorMap = {} -- Map to group double doors by ID or linked ID

        for _, door in ipairs(CachedActors.doors) do
            if door:IsValid() then
                local loc = door:K2_GetActorLocation()
                local distSq = Utils.GetDistanceSquared(scanOrigin, loc)
                
                if distSq < radiusSq then
                    local myId = door:GetFName():ToString()
                    -- Find link: either via DriveSubDoor or MainSubDoor relationship
                    local linkedId = (door.DriveSubDoor and door.DriveSubDoor:IsValid()) and door.DriveSubDoor:GetFName():ToString() or nil
                    
                    -- Use math.abs because doors can swing in negative directions
                    local amount = door.OpenCloseAmount or 0
                    local isOpen = math.abs(amount) > 5.0
                    local isLocked = door.bLocked == 1 or door.bLocked == true
                    local isJammed = door.bJamInProgress == 1 or door.bJamInProgress == true
                    local isBroken = door.bBroken == 1 or door.bBroken == true
                    local isWedged = (door.AttachedWedge and door.AttachedWedge:IsValid()) or false
                    
                    local existingEntry = doorMap[myId] or (linkedId and doorMap[linkedId])
                    
                    if existingEntry then
                        -- Merge: True if EITHER is true
                        existingEntry.is_open = existingEntry.is_open or isOpen
                        existingEntry.locked = existingEntry.locked or isLocked
                        existingEntry.is_broken = existingEntry.is_broken or isBroken
                        existingEntry.is_wedged = existingEntry.is_wedged or isWedged
                        existingEntry.jammed = existingEntry.jammed or isJammed
                        existingEntry.is_double_door = true
                        
                        local myDist = math.floor(math.sqrt(distSq) / 100)
                        if myDist < existingEntry.distance then existingEntry.distance = myDist end
                    else
                        local entry = {
                            id = myId,
                            location = {X = loc.X, Y = loc.Y, Z = loc.Z},
                            distance = math.floor(math.sqrt(distSq) / 100),
                            locked = isLocked,
                            jammed = isJammed,
                            is_broken = isBroken,
                            is_wedged = isWedged,
                            is_open = isOpen,
                            front_room = roomPosMap[door.FrontRoomPosition] or "Unknown",
                            back_room = roomPosMap[door.BackRoomPosition] or "Unknown",
                            is_double_door = (linkedId ~= nil)
                        }
                        doorMap[myId] = entry
                        if linkedId then doorMap[linkedId] = entry end
                    end
                end
            end
        end

        -- Convert map back to unique array
        local processedEntries = {}
        for _, entry in pairs(doorMap) do
            if not processedEntries[entry] then
                table.insert(tacticalState.nearby_doors, entry)
                processedEntries[entry] = true
            end
        end

        -- Sort doors by distance (closest first)
        table.sort(tacticalState.nearby_doors, function(a, b)
            return a.distance < b.distance
        end)
    end
    -- 3. Update Character States (from cache)
    if Config.SCAN_CHARACTERS then
        local processChar = function(charList, charType)
            for _, char in ipairs(charList) do
                if char:IsValid() then
                    local loc = char:K2_GetActorLocation()
                    local distSq = Utils.GetDistanceSquared(scanOrigin, loc)
                    if distSq < radiusSq then
                        table.insert(tacticalState.nearby_characters, {
                            type = charType,
                            id = char:GetFName():ToString(),
                            location = {X = loc.X, Y = loc.Y, Z = loc.Z},
                            distance = math.floor(math.sqrt(distSq) / 100),
                            is_complying = char.bIsComplying == 1 or char.bIsComplying == true,
                            is_surrendered = char.bSurrendered == 1 or char.bSurrendered == true,
                            combat_state = tostring(char.CombatState or "UNKNOWN")
                        })
                    end
                end
            end
        end
        processChar(CachedActors.suspects, "SUSPECT")
        processChar(CachedActors.civilians, "CIVILIAN")
    end

    EnvironmentScanner.TacticalData = tacticalState
    return tacticalState
end

-- Export tactical data to file
function EnvironmentScanner.ExportToFile()
    local data = EnvironmentScanner.ScanEnvironment()
    if not data then return end
    
    local jsonStr = Utils.TableToJson(data)
    local path = Config.baseDir .. "environment.json"
    local file = io.open(path, "w")
    if file then
        file:write(jsonStr)
        file:close()
    else
        Utils.Log("Error: Could not open environment.json for writing at " .. path)
    end
end

return EnvironmentScanner
