local Utils = require("Modules.Utils")
local Config = require("Modules.Config")
local EnvironmentScanner = require("Modules.EnvironmentScanner")

local EnvironmentGraph = {}

EnvironmentGraph.StaticCache = nil
EnvironmentGraph.LastDoorCount = 0

function EnvironmentGraph.ExtractGraph()
    EnvironmentScanner.InitializeCache()
    local doors = EnvironmentScanner.CachedActors.doors
    if not doors or #doors == 0 then
        -- Utils.Log("[SwatLLM] Warning: No doors found in cache for graph extraction.")
        return
    end

    -- 1. Build or retrieve static cache
    if not EnvironmentGraph.StaticCache or EnvironmentGraph.LastDoorCount ~= #doors then
        Utils.Log("[SwatLLM] Building Static Environment Graph Cache...")
        EnvironmentGraph.StaticCache = {
            nodes = {},
            doorMap = {}
        }
        EnvironmentGraph.LastDoorCount = #doors
        
        local discoveredRooms = {}
        local function AddRoomNode(roomName)
            if roomName and roomName ~= "None" and roomName ~= "Unknown" and roomName ~= "" then
                if not discoveredRooms[roomName] then
                    discoveredRooms[roomName] = true
                    table.insert(EnvironmentGraph.StaticCache.nodes, {
                        id = roomName,
                        size = "Unknown"
                    })
                end
                return true
            end
            return false
        end

        for _, door in ipairs(doors) do
            if door:IsValid() then
                local doorId = door:GetFName():ToString()
                local groupId = doorId
                
                -- Simple grouping logic for double doors
                if door.DriveSubDoor and door.DriveSubDoor:IsValid() then
                    local otherId = door.DriveSubDoor:GetFName():ToString()
                    if doorId > otherId then groupId = otherId .. "_" .. doorId 
                    else groupId = doorId .. "_" .. otherId end
                end

                if not EnvironmentGraph.StaticCache.doorMap[groupId] then
                    local roomA = "Unknown"
                    local roomB = "Unknown"
                    
                    pcall(function()
                        local rA = door:GetFrontThreatOwningRoom()
                        if rA then roomA = rA:ToString() end
                        local rB = door:GetBackThreatOwningRoom()
                        if rB then roomB = rB:ToString() end
                    end)

                    local validA = AddRoomNode(roomA)
                    local validB = AddRoomNode(roomB)

                    -- Only add edge if at least one room is valid
                    if validA or validB then
                        local loc = door:K2_GetActorLocation()
                        EnvironmentGraph.StaticCache.doorMap[groupId] = {
                            actors = { door },
                            roomA = roomA,
                            roomB = roomB,
                            location = { X = loc.X, Y = loc.Y, Z = loc.Z }
                        }
                    end
                else
                    table.insert(EnvironmentGraph.StaticCache.doorMap[groupId].actors, door)
                end
            end
        end
        Utils.Log("[SwatLLM] Static Graph Cache Built.")
    end

    -- 2. Build the final graph using static cache + dynamic properties
    local graph = {
        nodes = EnvironmentGraph.StaticCache.nodes,
        edges = {}
    }

    local dirOrigin, dirForward = Utils.GetPlayerViewpoint()
    if not dirOrigin then
        dirOrigin = {X = 0, Y = 0, Z = 0}
    end

    local radiusSq = Config.SCAN_RADIUS * Config.SCAN_RADIUS
    local edgeCount = 0
    local stateDirty = false
    
    if not EnvironmentGraph.StaticCache.doorStates then
        EnvironmentGraph.StaticCache.doorStates = {}
        stateDirty = true
    end

    for groupId, staticData in pairs(EnvironmentGraph.StaticCache.doorMap) do
        local isOpen = false
        local isLocked = false
        local isBroken = false
        
        -- Optimization: Only check dynamic properites for doors near the player
        local distSq = Utils.GetDistanceSquared(dirOrigin, staticData.location)
        if distSq < radiusSq then
            for _, door in ipairs(staticData.actors) do
                if door and door:IsValid() then
                    local broken = door.bDoorBroken == 1 or door.bDoorBroken == true
                    local open = (math.abs(door.OpenCloseAmount or 0) > 5.0) or broken
                    local locked = door.bLocked == 1 or door.bLocked == true
                    
                    isOpen = isOpen or open
                    isLocked = isLocked or locked
                    isBroken = isBroken or broken
                end
            end
        else
            -- use previous state for distant doors if available
            local prevState = EnvironmentGraph.StaticCache.doorStates[groupId]
            if prevState then
                isOpen = prevState.isOpen
                isLocked = prevState.isLocked
                isBroken = prevState.isBroken
            end
        end

        local prevState = EnvironmentGraph.StaticCache.doorStates[groupId]
        if not prevState or prevState.isOpen ~= isOpen or prevState.isLocked ~= isLocked or prevState.isBroken ~= isBroken then
            EnvironmentGraph.StaticCache.doorStates[groupId] = {
                isOpen = isOpen,
                isLocked = isLocked,
                isBroken = isBroken
            }
            stateDirty = true
        end

        table.insert(graph.edges, {
            roomA = staticData.roomA,
            roomB = staticData.roomB,
            isOpen = isOpen,
            isLocked = isLocked,
            isBroken = isBroken,
            location = { X = staticData.location.X, Y = staticData.location.Y, Z = staticData.location.Z }
        })
        edgeCount = edgeCount + 1
    end

    if not stateDirty and EnvironmentGraph.CachedJsonString then
        -- Graph hasn't changed, skip heavy TableToJson and disk write
        return
    end

    -- 3. Export to JSON using shared Utils
    local jsonString = Utils.TableToJson(graph)
    EnvironmentGraph.CachedJsonString = jsonString
    
    local graphFilepath = Config.baseDir .. "environment_graph.json"
    local file, err = io.open(graphFilepath, "w")
    if file then
        file:write(jsonString)
        file:close()
        -- Utils.Log(string.format("[SwatLLM] Environment Graph exported: %d nodes, %d edges", #graph.nodes, edgeCount))
    else
        Utils.Log("[SwatLLM] Error writing Environment Graph: " .. tostring(err))
    end
end

return EnvironmentGraph

