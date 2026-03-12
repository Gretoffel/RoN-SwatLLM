local CommandQueue = {}

-- States for commands
CommandQueue.Status = {
    PENDING = "PENDING",
    RUNNING = "RUNNING",
    COMPLETED = "COMPLETED"
}

-- The actual queue
CommandQueue.Queue = {}

-- Internal reference to modules
local StatusScanner = nil
local Config = nil
local Utils = nil
local Commands = nil

-- Initialization
function CommandQueue.Init(modules)
    StatusScanner = modules.StatusScanner
    Config = modules.Config
    Utils = modules.Utils
    Commands = modules.Commands
end

-- Parse a line from commands.txt into a command object
-- Syntax: [TEAM] [COMMAND] [ARGS...] [ID:N] [WAITFOR:M]
function CommandQueue.ParseCommandLine(line)
    if line == "" or string.sub(line, 1, 2) == "--" then return nil end
    
    local cmdObj = {
        Raw = line,
        Team = nil,
        Action = nil,
        Args = {},
        Id = nil,
        WaitFor = nil,
        Status = CommandQueue.Status.PENDING
    }
    
    -- Extract ID:N if present
    local id_match = string.match(line, "ID:(%d+)")
    if id_match then
        cmdObj.Id = tonumber(id_match)
        line = string.gsub(line, "ID:%d+", "") -- Strip it for further parsing
    end
    
    -- Extract WAITFOR:M if present
    local wait_match = string.match(line, "WAITFOR:(%d+)")
    if wait_match then
        cmdObj.WaitFor = tonumber(wait_match)
        line = string.gsub(line, "WAITFOR:%d+", "") -- Strip it
    end
    
    -- Parse the remaining parts
    local parts = {}
    for word in string.gmatch(line, "%S+") do
        table.insert(parts, word)
    end
    
    if #parts >= 2 then
        cmdObj.Team = string.upper(parts[1])
        cmdObj.Action = string.upper(parts[2])
        for i = 3, #parts do
            table.insert(cmdObj.Args, parts[i])
        end
    else
        return nil -- Invalid command format
    end
    
    return cmdObj
end

-- Refresh the queue from a content string
function CommandQueue.RefreshFromContent(content)
    if not content or content == "" then return end
    
    local newQueue = {}
    -- Split content by lines
    for line in string.gmatch(content, "[^\r\n]+") do
        local cmd = CommandQueue.ParseCommandLine(line)
        if cmd then
            table.insert(newQueue, cmd)
        end
    end
    
    -- In a sophisticated system, we'd merge queues. 
    -- For now, we rebuild the queue when new commands arrive via file sync.
    CommandQueue.Queue = newQueue
    print(string.format("[SwatLLM] CommandQueue: Loaded %d commands.\n", #CommandQueue.Queue))
end

-- Get a human-readable summary of the current queue status
function CommandQueue.GetStatusSummary()
    if #CommandQueue.Queue == 0 then
        return "Queue is EMPTY"
    end
    
    local summary = string.format("Queue Status (%d commands):", #CommandQueue.Queue)
    local counts = { PENDING = 0, RUNNING = 0, COMPLETED = 0 }
    
    for i, cmd in ipairs(CommandQueue.Queue) do
        counts[cmd.Status] = counts[cmd.Status] + 1
        
        if cmd.Status == CommandQueue.Status.RUNNING then
            local activity = StatusScanner.GetTeamActivity(cmd.Team)
            summary = summary .. string.format("\n  [#%d] Team %s -> %s (Task: %s)", i, cmd.Team, cmd.Action, activity)
        end
    end
    
    summary = summary .. string.format("\n  Stats: %d Pending, %d Running, %d Completed", counts.PENDING, counts.RUNNING, counts.COMPLETED)
    return summary
end

-- Find a command in the queue by ID
function CommandQueue.FindCommandById(id)
    if not id then return nil end
    for _, cmd in ipairs(CommandQueue.Queue) do
        if cmd.Id == id then return cmd end
    end
    return nil
end

-- Check if all commands before this one for the SAME TEAM are COMPLETED
function CommandQueue.IsTeamPathClear(index)
    local targetCmd = CommandQueue.Queue[index]
    if not targetCmd then return false end
    
    for i = 1, index - 1 do
        local prevCmd = CommandQueue.Queue[i]
        -- If it's the same team (or GOLD which affects everyone), it must be COMPLETED
        if prevCmd.Team == targetCmd.Team or targetCmd.Team == "GOLD" or prevCmd.Team == "GOLD" then
            if prevCmd.Status ~= CommandQueue.Status.COMPLETED then
                return false
            end
        end
    end
    return true
end

-- The main progression logic
function CommandQueue.Process()
    if #CommandQueue.Queue == 0 then return end
    
    local anyChanged = false
    
    for i, cmd in ipairs(CommandQueue.Queue) do
        if cmd.Status == CommandQueue.Status.PENDING then
            -- CHECK START CONDITIONS
            
            -- 1. WAITFOR dependency
            local waitReady = true
            if cmd.WaitFor then
                local dependency = CommandQueue.FindCommandById(cmd.WaitFor)
                if dependency then
                    if dependency.Status ~= CommandQueue.Status.COMPLETED then
                        waitReady = false
                    end
                else
                    -- Warning: dependent ID not found in current queue. 
                    -- We'll allow it to proceed but log a warning.
                    print(string.format("[SwatLLM] WARNING: Command %d waiting for non-existent ID %d\n", i, cmd.WaitFor))
                end
            end
            
            -- 2. Sequentiality for same team
            local pathClear = CommandQueue.IsTeamPathClear(i)
            
            -- 3. Is the team actually idle in-game?
            local teamIdle = StatusScanner.IsTeamIdle(cmd.Team)
            
            if waitReady and pathClear and teamIdle then
                -- START COMMAND
                print(string.format("[SwatLLM] Starting Command %d: %s %s\n", i, cmd.Team, cmd.Action))
                cmd.Status = CommandQueue.Status.RUNNING
                
                -- Call the original execution logic
                Commands.ExecuteAction(cmd.Team, cmd.Action, cmd.Args)
                anyChanged = true
            end
            
        elseif cmd.Status == CommandQueue.Status.RUNNING then
            -- CHECK COMPLETION
            -- A command is "COMPLETED" when the team becomes IDLE again
            if StatusScanner.IsTeamIdle(cmd.Team) then
                print(string.format("[SwatLLM] Completed Command %d: %s %s\n", i, cmd.Team, cmd.Action))
                cmd.Status = CommandQueue.Status.COMPLETED
                anyChanged = true
            end
        end
    end
    
    return anyChanged
end

return CommandQueue
