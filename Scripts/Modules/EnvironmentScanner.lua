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
EnvironmentScanner.CachedActors = {
    doors = {},
    suspects = {},
    civilians = {},
    rooms = {},
    initialized = false,
    last_refresh = 0
}

local CachedActors = EnvironmentScanner.CachedActors

-- Perform a full scan of the world to find interactive actors
function EnvironmentScanner.InitializeCache(force)
    local currentTime = os.time()
    if not force and CachedActors.initialized and (currentTime - CachedActors.last_refresh < Config.ACTOR_CACHE_INTERVAL) then 
        return 
    end

    -- Utils.Log(string.format("Refreshing Environment Actor Cache (Full World Scan, Interval: %.1fs)...", Config.ACTOR_CACHE_INTERVAL))
    
    -- Doors: RoN doors are typically of class "Door"
    CachedActors.doors = FindAllOf("Door") or {}
    
    -- Characters
    CachedActors.suspects = FindAllOf("SuspectCharacter") or {}
    CachedActors.civilians = FindAllOf("CivilianCharacter") or {}

    -- Rooms (for EnvironmentGraph)
    CachedActors.rooms = FindAllOf("RoomVisualizer") or {}

    CachedActors.initialized = true
    CachedActors.last_refresh = currentTime
    
    -- Utils.Log(string.format("Cache Updated: %d Doors, %d Rooms, %d Suspects, %d Civilians", 
    --    #CachedActors.doors, #CachedActors.rooms, #CachedActors.suspects, #CachedActors.civilians))
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

EnvironmentScanner.StaticDoorCache = nil
EnvironmentScanner.LastDoorCount = 0

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

    local dirOrigin, dirForward = Utils.GetPlayerViewpoint()

    -- 2. Fallback to Team if Player not found
    local scanOrigin = dirOrigin
    if not scanOrigin then
        if internalTeams.GOLD then
            scanOrigin = internalTeams.GOLD.center
        elseif internalTeams.RED then
            scanOrigin = internalTeams.RED.center
        elseif internalTeams.BLUE then
            scanOrigin = internalTeams.BLUE.center
        end
        dirOrigin = scanOrigin
    end

    if not scanOrigin then return end
    
    local radiusSq = Config.SCAN_RADIUS * Config.SCAN_RADIUS

    -- 2. Update Door States (using static cache)
    if Config.SCAN_DOORS then
        local doors = CachedActors.doors
        
        if not EnvironmentScanner.StaticDoorCache or EnvironmentScanner.LastDoorCount ~= #doors then
            EnvironmentScanner.StaticDoorCache = {}
            EnvironmentScanner.LastDoorCount = #doors
            
            local roomPosMap = {
                [0] = "Center", [1] = "CornerLeft", [2] = "CornerRight",
                [3] = "Hallway", [4] = "HallwayLeft", [5] = "HallwayRight"
            }
            
            for _, door in ipairs(doors) do
                if door:IsValid() then
                    local myId = door:GetFName():ToString()
                    local groupId = myId
                    
                    local linkedId = nil
                    if door.DriveSubDoor and door.DriveSubDoor:IsValid() then
                        linkedId = door.DriveSubDoor:GetFName():ToString()
                        if myId > linkedId then groupId = linkedId .. "_" .. myId
                        else groupId = myId .. "_" .. linkedId end
                    end
                    
                    if not EnvironmentScanner.StaticDoorCache[groupId] then
                        local loc = door:K2_GetActorLocation()
                        EnvironmentScanner.StaticDoorCache[groupId] = {
                            actors = { door },
                            id = groupId,
                            is_double_door = (linkedId ~= nil),
                            front_room = roomPosMap[door.FrontRoomPosition] or "Unknown",
                            back_room = roomPosMap[door.BackRoomPosition] or "Unknown",
                            location = { X = loc.X, Y = loc.Y, Z = loc.Z }
                        }
                    else
                        table.insert(EnvironmentScanner.StaticDoorCache[groupId].actors, door)
                    end
                end
            end
        end

        for groupId, staticData in pairs(EnvironmentScanner.StaticDoorCache) do
            local distSq = Utils.GetDistanceSquared(scanOrigin, staticData.location)
            if distSq < radiusSq then
                local isOpen = false
                local isLocked = false
                local isBroken = false
                local isJammed = false
                local isWedged = false
                
                for _, door in ipairs(staticData.actors) do
                    if door and door:IsValid() then
                        local broken = door.bDoorBroken == 1 or door.bDoorBroken == true
                        local amount = door.OpenCloseAmount or 0
                        local open = math.abs(amount) > 5.0 or broken
                        local locked = door.bLocked == 1 or door.bLocked == true
                        local jammed = door.bJamInProgress == 1 or door.bJamInProgress == true
                        local wedged = (door.AttachedWedge and door.AttachedWedge:IsValid()) or false
                        
                        isOpen = isOpen or open
                        isLocked = isLocked or locked
                        isBroken = isBroken or broken
                        isJammed = isJammed or jammed
                        isWedged = isWedged or wedged
                    end
                end
                
                table.insert(tacticalState.nearby_doors, {
                    id = staticData.id,
                    location = {X = staticData.location.X, Y = staticData.location.Y, Z = staticData.location.Z},
                    distance = math.floor(math.sqrt(distSq) / 100),
                    direction = Utils.GetRelativeDirection(dirOrigin, dirForward, staticData.location),
                    locked = isLocked,
                    jammed = isJammed,
                    is_broken = isBroken,
                    is_wedged = isWedged,
                    is_open = isOpen,
                    front_room = staticData.front_room,
                    back_room = staticData.back_room,
                    is_double_door = staticData.is_double_door
                })
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
                            direction = Utils.GetRelativeDirection(dirOrigin, dirForward, loc),
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
