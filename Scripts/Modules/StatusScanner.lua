local StatusScanner = {}

-- Cache for SWAT controllers to avoid expensive FindAllOf calls every tick
StatusScanner.CachedControllers = {}
StatusScanner.LastCacheUpdate = 0
StatusScanner.CACHE_INTERVAL = 5.0 -- SECONDS

-- Team mapping from ETeamType (ReadyOrNot_enums.hpp)
-- TT_NONE = 0
-- TT_SERT_RED = 1
-- TT_SERT_BLUE = 2
-- TT_SUSPECT = 3
-- TT_CIVILIAN = 4
-- TT_SQUAD = 5 (GOLD)
StatusScanner.TeamEnum = {
    RED = 1,
    BLUE = 2,
    GOLD = 5
}

-- Individual positions from ERosterSquadPosition
StatusScanner.PositionEnum = {
    RedOne = 1,
    RedTwo = 2,
    BlueOne = 3,
    BlueTwo = 4
}

-- Update the cache of SWAT controllers
function StatusScanner.UpdateCache()
    local currentTime = os.time()
    
    StatusScanner.CachedControllers = {}
    local allControllers = FindAllOf("SWATController")
    
    if allControllers then
        for _, controller in ipairs(allControllers) do
            if controller:IsValid() and controller.Pawn and controller.Pawn:IsValid() then
                local botName = controller.Pawn:GetFName():ToString()
                -- Filter out trailers or non-swat if necessary
                if not string.find(botName, "Trailer") then
                    table.insert(StatusScanner.CachedControllers, controller)
                end
            end
        end
    end
    
    StatusScanner.LastCacheUpdate = currentTime
    -- print(string.format("[SwatLLM] StatusScanner: Cached %d SWAT controllers.", #StatusScanner.CachedControllers))
end

-- Check if the cache is still valid
function StatusScanner.IsCacheValid()
    local currentTime = os.time()
    if currentTime - StatusScanner.LastCacheUpdate > StatusScanner.CACHE_INTERVAL then
        return false -- Force update every 5 seconds
    end

    if #StatusScanner.CachedControllers == 0 then
        -- We didn't find any. Instead of scanning every tick, rely on the 5-sec interval
        return true 
    end
    
    for _, controller in ipairs(StatusScanner.CachedControllers) do
        if not controller:IsValid() or not controller.Pawn or not controller.Pawn:IsValid() then
            -- Controller invalid, force update
            return false
        end
    end
    
    return true
end

-- Get the team of a controller
function StatusScanner.GetControllerTeam(controller)
    if not controller:IsValid() then return nil end
    -- ACyberneticController:GetTeam() returns ETeamType
    local teamType = controller:GetTeam()
    
    if teamType == StatusScanner.TeamEnum.RED then return "RED" end
    if teamType == StatusScanner.TeamEnum.BLUE then return "BLUE" end
    if teamType == StatusScanner.TeamEnum.GOLD then return "GOLD" end
    return "UNKNOWN"
end

-- Get the position (RedOne, etc) of a controller
function StatusScanner.GetControllerPosition(controller)
    if not controller:IsValid() or not controller.Pawn then return nil end
    
    -- Based on research: ASWATCharacter -> RosterCharacter -> Position (ERosterSquadPosition)
    local pawn = controller.Pawn
    if pawn.RosterCharacter and pawn.RosterCharacter:IsValid() then
        local pos = pawn.RosterCharacter.Position
        for name, val in pairs(StatusScanner.PositionEnum) do
            if pos == val then return name end
        end
    end
    return "UNKNOWN"
end

-- Check if a specific controller is idle
function StatusScanner.IsControllerIdle(controller)
    if not controller:IsValid() then return true end
    
    -- Based on botStatScanner: CurrentActivity is nil/invalid if idle
    local currentActivity = controller.CurrentActivity
    if currentActivity and currentActivity:IsValid() then
        return false
    end
    return true
end

-- Check if an entire team is idle
function StatusScanner.IsTeamIdle(teamName)
    if not StatusScanner.IsCacheValid() then
        StatusScanner.UpdateCache()
    end
    
    teamName = string.upper(teamName)
    
    local foundAny = false
    for _, controller in ipairs(StatusScanner.CachedControllers) do
        local ctrlTeam = StatusScanner.GetControllerTeam(controller)
        
        -- Special handling for GOLD: include all SWAT
        if teamName == "GOLD" or ctrlTeam == teamName then
            foundAny = true
            if not StatusScanner.IsControllerIdle(controller) then
                return false
            end
        end
    end
    -- If no bots found or all are idle, return true
    return true
end

-- Get the names of current activities for a team
function StatusScanner.GetTeamActivity(teamName)
    if not StatusScanner.IsCacheValid() then
        StatusScanner.UpdateCache()
    end
    
    teamName = string.upper(teamName)
    local activities = {}
    
    for _, controller in ipairs(StatusScanner.CachedControllers) do
        local ctrlTeam = StatusScanner.GetControllerTeam(controller)
        
        if teamName == "GOLD" or ctrlTeam == teamName then
            local currentActivity = controller.CurrentActivity
            if currentActivity and currentActivity:IsValid() then
                local actName = currentActivity:GetFName():ToString()
                -- Simplify common activity names for better readability
                actName = string.gsub(actName, "CommandActivity", "")
                actName = string.gsub(actName, "Activity", "")
                table.insert(activities, actName)
            end
        end
    end
    
    if #activities == 0 then
        return "IDLE"
    else
        -- deduplicate activities
        local seen = {}
        local unique = {}
        for _, a in ipairs(activities) do
            if not seen[a] then
                seen[a] = true
                table.insert(unique, a)
            end
        end
        return table.concat(unique, ", ")
    end
end

return StatusScanner
