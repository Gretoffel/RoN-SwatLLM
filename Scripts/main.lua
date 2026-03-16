local Utils = require("Modules.Utils")
local Config = require("Modules.Config")
local StatusScanner = require("Modules.StatusScanner")
local Commands = require("Modules.Commands")
local CommandQueue = require("Modules.CommandQueue")
local EnvironmentScanner = require("Modules.EnvironmentScanner")
local EnvironmentGraph = require("Modules.EnvironmentGraph")

-- CommandQueue and dependencies are already loaded globally or via require
CommandQueue.Init({
    StatusScanner = StatusScanner,
    Config = Config,
    Utils = Utils,
    Commands = Commands
})

local function ReadAndQueueCommands()
    local file, err = io.open(Config.filepath, "r")
    if file then
        local content = file:read("*all")
        file:close()
        
        if content and string.len(content) > 0 then
            -- Clear file first to prevent duplicate execution
            file = io.open(Config.filepath, "w")
            file:write("")
            file:close()
            
            -- Re-parse the content and update the queue
            CommandQueue.RefreshFromContent(content)
            Utils.Log("[SwatLLM] Commands refreshed and queued.")
        end
    end
end


local Timer = 0
local QueueTimer = 0
local DebugTimer = 0
local ScanTimer = 0
RegisterHook("/Script/ReadyOrNot.PlayerCharacter:Server_UpdateCameraRotationRate", function(Context) end,
function() 
    local currentClock = os.clock()
    
    -- Check for file updates every 1.0s
    if currentClock - Timer > 1.0 then
        Timer = currentClock
        ReadAndQueueCommands()
    end
    
    -- Process the command queue every 0.5s
    if currentClock - QueueTimer > 0.5 then
        QueueTimer = currentClock
        CommandQueue.Process()
    end
    
    -- Print debug status every 2.0s
    if currentClock - DebugTimer > 2.0 then
        DebugTimer = currentClock
        local status = CommandQueue.GetStatusSummary()
        if status ~= "Queue is EMPTY" then
            print("[SwatLLM] " .. status .. "\n")
        end
    end
    
    -- Scan environment and export to JSON based on config interval
    if currentClock - ScanTimer > Config.SCAN_INTERVAL then
        ScanTimer = currentClock
        EnvironmentScanner.ExportToFile()
        EnvironmentGraph.ExtractGraph()
    end
end)

local SavedCrosshairLoc = nil

RegisterKeyBind(Key.K, function()
    Utils.Log("Manual Environment Scan Triggered.")
    EnvironmentScanner.ExportToFile()
    EnvironmentGraph.ExtractGraph()
end)

RegisterKeyBind(Key.L, function()
    Utils.Log("L Hotkey Pressed. Attempting to copy coordinates...")
    local pc = Utils.GetPlayerController()
    if pc and pc:IsValid() then
        -- Try multiple ways to get the player pawn/character
        local pawn = pc.Pawn or pc.AcknowledgedPawn
        
        -- Fallback: If controller properties fail, find the character directly
        if not pawn or not pawn:IsValid() then
            pawn = FindFirstOf("PlayerCharacter")
        end

        if pawn and pawn:IsValid() then
            local widget = pawn.SwatCommandWidget
            if widget and widget:IsValid() then
                local ctx = widget.ContextualData1
                if ctx and ctx.Location then
                    local locX = tonumber(ctx.Location.X)
                    local locY = tonumber(ctx.Location.Y)
                    local locZ = tonumber(ctx.Location.Z)
                    
                    if locX and locY and locZ then
                        SavedCrosshairLoc = { X = locX, Y = locY, Z = locZ }
                        Utils.Log(string.format("Copied Crosshair Coordinates: %.2f %.2f %.2f", SavedCrosshairLoc.X, SavedCrosshairLoc.Y, SavedCrosshairLoc.Z))
                    else
                        Utils.Log("L failed: Coordinates are not numbers (UE4SS type mismatch).")
                    end
                else
                    Utils.Log("L failed: No tactical object under crosshair (ContextualData1 or Location is nil).")
                end
            else
                Utils.Log("L failed: SwatCommandWidget not found on character.")
            end
        else
            Utils.Log("L failed: Could not find player character (Pawn/Character is nil).")
        end
    else
        Utils.Log("L failed: PlayerController is invalid/nil.")
    end
end)

RegisterKeyBind(Key.P, function()
    if SavedCrosshairLoc then
        Utils.Log(string.format("Executing P hotkey action to saved coordinates: %.2f %.2f %.2f", SavedCrosshairLoc.X, SavedCrosshairLoc.Y, SavedCrosshairLoc.Z))
        
        if Config.P_Key_Action1 ~= "NONE" then
            local cmdStr1 = string.format("%s %.2f %.2f %.2f", Config.P_Key_Action1, SavedCrosshairLoc.X, SavedCrosshairLoc.Y, SavedCrosshairLoc.Z)
            Commands.ExecuteCommand(cmdStr1)
        end
        
        if Config.P_Key_Action2 ~= "NONE" then
            local cmdStr2 = string.format("%s %.2f %.2f %.2f", Config.P_Key_Action2, SavedCrosshairLoc.X, SavedCrosshairLoc.Y, SavedCrosshairLoc.Z)
            Commands.ExecuteCommand(cmdStr2)
        end
    else
        Utils.Log("No coordinates saved. Press L first while looking somewhere.")
    end
end)

Utils.Log("SwatLLM Mod Initialized. Waiting for commands.txt updates...")
