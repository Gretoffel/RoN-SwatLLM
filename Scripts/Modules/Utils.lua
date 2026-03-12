local UEHelpers = require("UEHelpers")

local Utils = {}

local CommandStruct_C = nil
local PlayerController = nil

function Utils.Log(msg)
    print("\n[SwatLLM] " .. tostring(msg) .. "\n")
end

function Utils.GetCommandStruct()
    if CommandStruct_C == nil or not CommandStruct_C:IsValid() then
        CommandStruct_C = FindFirstOf("SWATManager")
    end
    return CommandStruct_C
end

function Utils.GetPlayerController()
    if PlayerController == nil or not PlayerController:IsValid() then
        PlayerController = UEHelpers:GetPlayerController()
    end
    return PlayerController
end

function Utils.GetDistanceSquared(loc1, loc2)
    -- We lower the weight of Z distance so doors on slightly different floor heights 
    -- don't get rejected immediately compared to X/Y distance.
    local dx = loc1.X - loc2.X
    local dy = loc1.Y - loc2.Y
    local dz = (loc1.Z - loc2.Z) * 0.2
    return dx*dx + dy*dy + dz*dz
end

-- Find nearest door to a location within a specific radius
function Utils.FindNearestDoor(location, radius)
    local doors = FindAllOf("Door")
    local nearest = nil
    local minDist = radius * radius
    
    if doors ~= nil then
        for _, door in ipairs(doors) do
            if door:IsValid() and door:IsA("/Script/ReadyOrNot.Door") then
                -- Determine the actual interactive sub-door (like the reference mod does)
                local interactiveDoor = door
                if door.bMainSubDoor == true then
                    interactiveDoor = door
                elseif door.DriveSubDoor and door.DriveSubDoor:IsValid() then
                    interactiveDoor = door.DriveSubDoor
                end
                
                local doorLoc = interactiveDoor:K2_GetActorLocation()
                local distSq = Utils.GetDistanceSquared(location, doorLoc)
                if distSq < minDist then
                    minDist = distSq
                    nearest = interactiveDoor
                end
            end
        end
    end
    return nearest
end

-- Serialize a table to a JSON string with optional pretty-printing
function Utils.TableToJson(t, indent)
    local function serialize(val, level)
        level = level or 0
        local spacing = string.rep("  ", level)
        local next_spacing = string.rep("  ", level + 1)
        
        if type(val) == "string" then
            return '"' .. val:gsub('"', '\\"') .. '"'
        elseif type(val) == "number" or type(val) == "boolean" then
            return tostring(val)
        elseif type(val) == "table" then
            local isArray = (#val > 0)
            local res = {}
            if isArray then
                for i = 1, #val do
                    table.insert(res, serialize(val[i], level + 1))
                end
                if #res == 0 then return "[]" end
                return "[\n" .. next_spacing .. table.concat(res, ",\n" .. next_spacing) .. "\n" .. spacing .. "]"
            else
                for k, v in pairs(val) do
                    table.insert(res, '"' .. tostring(k) .. '": ' .. serialize(v, level + 1))
                end
                if #res == 0 then return "{}" end
                return "{\n" .. next_spacing .. table.concat(res, ",\n" .. next_spacing) .. "\n" .. spacing .. "}"
            end
        else
            return "null"
        end
    end
    return serialize(t, 0)
end

return Utils
