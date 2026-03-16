local UEHelpers = require("UEHelpers")

local Utils = {}

local CommandStruct_C = nil
local PlayerController = nil

function Utils.Log(msg)
    print("\n[SwatLLM] " .. tostring(msg) .. "\n")
end

function Utils.GetCommandStruct()
    if CommandStruct_C == nil or not CommandStruct_C:IsValid() then
        CommandStruct_C = FindFirstOf("USWATManager")
        if not CommandStruct_C or not CommandStruct_C:IsValid() then
            CommandStruct_C = FindFirstOf("SWATManager")
        end
        if CommandStruct_C and CommandStruct_C:IsValid() then
            Utils.Log("Successfully retrieved SWATManager: " .. CommandStruct_C:GetFullName())
        else
            Utils.Log("CRITICAL: Failed to retrieve SWATManager (tried USWATManager and SWATManager).")
        end
    end
    return CommandStruct_C
end

function Utils.GetPlayerController()
    if PlayerController == nil or not PlayerController:IsValid() then
        PlayerController = UEHelpers:GetPlayerController()
        if PlayerController and PlayerController:IsValid() then
            Utils.Log("Successfully retrieved PlayerController: " .. PlayerController:GetFullName())
        else
            Utils.Log("CRITICAL: Failed to retrieve PlayerController.")
        end
    else
        -- Optional: Log that we are using the cached one if needed for debugging
        -- Utils.Log("Using cached PlayerController: " .. PlayerController:GetFullName())
    end
    return PlayerController
end

function Utils.GetPlayerViewpoint()
    local pc = Utils.GetPlayerController()
    local origin = nil
    local forward = {X = 1, Y = 0, Z = 0}
    
    if pc and pc:IsValid() then
        local pawn = pc.Pawn
        if not pawn or not pawn:IsValid() then pawn = pc.AcknowledgedPawn end
        if not pawn or not pawn:IsValid() then pawn = pc.Character end
        -- Optimization: Removed FindFirstOf here because it does a full world scan every second if pawn is not found
        
        if pawn and pawn:IsValid() then
            origin = pawn:K2_GetActorLocation()
            
            local yaw = 0
            local source = "None"
            
            -- Priority 1: Pawn BaseAimRotation (authoritative aim direction)
            local ok, rot = pcall(function() return pawn:GetBaseAimRotation() end)
            if ok and rot then
                local y = tonumber(tostring(rot.Yaw))
                if y then yaw = y; source = "BaseAimRotation" end
            end
            
            -- Priority 2: Camera Manager (Actual POV)
            if source == "None" then
                local cm = pc.PlayerCameraManager
                if cm and cm:IsValid() then
                    local ok2, rot2 = pcall(function() return cm:GetCameraRotation() end)
                    if ok2 and rot2 then
                        local y = tonumber(tostring(rot2.Yaw))
                        if y and y ~= 0 then yaw = y; source = "CameraManager" end
                    end
                end
            end
            
            -- Priority 3: Controller's GetControlRotation
            if source == "None" then
                local ok3, rot3 = pcall(function() return pc:GetControlRotation() end)
                if ok3 and rot3 then
                    local y = tonumber(tostring(rot3.Yaw))
                    if y then yaw = y; source = "ControlRotation" end
                end
            end
            
            -- Priority 4: Actor Forward Vector (fallback)
            if source == "None" then
                local ok4, fv = pcall(function() return pawn:GetActorForwardVector() end)
                if ok4 and fv then
                    forward = {X = fv.X or 1, Y = fv.Y or 0, Z = 0}
                    -- Calculate yaw from vector for logging
                    yaw = math.deg(math.atan2(forward.Y, forward.X))
                    source = "ActorForwardVector"
                end
            end
            
            -- Calculate forward vector from yaw
            if source ~= "ActorForwardVector" and source ~= "None" then
                local yawRad = math.rad(yaw)
                forward = {
                    X = math.cos(yawRad),
                    Y = math.sin(yawRad),
                    Z = 0
                }
            end

            -- Log to the console so the user can see if the viewpoint is frozen/found
            -- Utils.Log(string.format("[Viewpoint] Source: %s, Pawn: %s, Yaw: %.2f", source, pawn:GetFName():ToString(), yaw))
        end
    end
    
    return origin, forward
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

-- Serialize a table to a JSON string with pretty formatting
function Utils.TableToJson(t)
    local function serialize(val, indent)
        indent = indent or 0
        local current_indent = string.rep("  ", indent)
        local next_indent = string.rep("  ", indent + 1)
        
        local vType = type(val)
        if vType == "string" then
            return '"' .. val:gsub('"', '\\"') .. '"'
        elseif vType == "number" or vType == "boolean" then
            return tostring(val)
        elseif vType == "table" then
            local isArray = (#val > 0)
            local res = {}
            if isArray then
                for i = 1, #val do
                    table.insert(res, next_indent .. serialize(val[i], indent + 1))
                end
                if #res == 0 then return "[]" end
                return "[\n" .. table.concat(res, ",\n") .. "\n" .. current_indent .. "]"
            else
                for k, v in pairs(val) do
                    table.insert(res, next_indent .. '"' .. tostring(k) .. '": ' .. serialize(v, indent + 1))
                end
                if #res == 0 then return "{}" end
                return "{\n" .. table.concat(res, ",\n") .. "\n" .. current_indent .. "}"
            end
        else
            return "null"
        end
    end
    return serialize(t, 0)
end

function Utils.GetDotProduct(v1, v2)
    return v1.X * v2.X + v1.Y * v2.Y + v1.Z * v2.Z
end

function Utils.GetCrossProductZ(v1, v2)
    return v1.X * v2.Y - v1.Y * v2.X
end

function Utils.GetRelativeDirection(origin, forward, target)
    local toTarget = {
        X = target.X - origin.X,
        Y = target.Y - origin.Y,
        Z = 0 -- Ignore Z for horizontal direction
    }
    
    -- Normalize toTarget
    local mag = math.sqrt(toTarget.X^2 + toTarget.Y^2)
    if mag < 10.0 then return "at your position" end
    toTarget.X = toTarget.X / mag
    toTarget.Y = toTarget.Y / mag
    
    local dot = Utils.GetDotProduct(forward, toTarget)
    local crossZ = Utils.GetCrossProductZ(forward, toTarget)
    
    local direction = ""
    
    if dot > 0.707 then
        direction = "front"
    elseif dot < -0.707 then
        direction = "back"
    else
        if crossZ > 0 then
            direction = "right"
        else
            direction = "left"
        end
    end
    
    -- refine with diagonals if needed, but simple 4-way is often better for LLMs
    -- let's do 8-way for more precision
    if dot > 0.382 and dot <= 0.924 then
        if crossZ > 0 then direction = "front-right" else direction = "front-left" end
    elseif dot < -0.382 and dot >= -0.924 then
        if crossZ > 0 then direction = "back-right" else direction = "back-left" end
    elseif dot > 0.924 then
        direction = "front"
    elseif dot < -0.924 then
        direction = "back"
    else
        if crossZ > 0 then direction = "right" else direction = "left" end
    end
    
    return direction
end

return Utils

