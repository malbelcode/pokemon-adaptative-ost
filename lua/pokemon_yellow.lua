-- Pokemon Adaptive OST
-- Lua -> Python communication

local ADDRESSES = {
    isInBattle = 0xD05B,
    curMap = 0xD362,
    battleResult = 0xCF0B,
    channelSoundIDs = 0xC026,
    trainerSpriteOffset = 0xCD3D
}

local HOST = "127.0.0.1"
local PORT = 8765

local previous = {
    isInBattle = nil,
    curMap = nil,
    battleResult = nil,
    channelKey = nil,
    victoryDetected = false,
    trainerSpriteOffset = nil,
    frame = nil
}

-- Sent every HEARTBEAT_FRAMES frames. Frames stop while mGBA is paused (also when
-- it pauses in the background), so the controller pauses the music when they stop.
local HEARTBEAT_FRAMES = 10
local framesSinceHeartbeat = 0

-- Trainer intro songs (audio bank 0x1F), read from the ROM's music headers.
-- When a trainer spots the player, the game starts one of these on channels 0-2.
-- Ids are bank-relative: 0xFB is also Indigo Plateau's map song (bank 0x02), so
-- only look for them for a short window after the trainer-spotted flag.
local TRAINER_INTRO_SONGS = {
    [0xF5] = "EVIL",
    [0xF8] = "FEMALE",
    [0xFB] = "MALE"
}
local TRAINER_INTRO_WINDOW = 180 -- frames (3 s)
local trainerIntroFramesLeft = 0

--------------------------------------------------
-- TCP CONNECTION
--------------------------------------------------

console:log("[OST] Connecting to Python controller...")

if type(socket) ~= "table" then
    console:error("[OST] mGBA socket API unavailable")
    return
end

local client, err = socket.connect(HOST, PORT)

if not client then
    console:error("[OST] Connection failed: " .. tostring(err))
    return
end

console:log("[OST] Connected to Python controller")

--------------------------------------------------
-- EVENT TRANSMISSION
--------------------------------------------------

local function sendEvent(message)
    local position = 1

    while position <= #message do
        local ok, last, sendError = pcall(function()
            return client:send(message, position)
        end)

        if not ok then
            console:error("[OST] Send failed: " .. tostring(last))
            return false
        end

        if not last then
            console:error("[OST] Send failed: " .. tostring(sendError))
            return false
        end

        if last < position then
            console:error("[OST] No data sent")
            return false
        end

        position = last + 1
    end

    return true
end

local function sendMapChanged(map)
    local message = string.format(
        '{"event":"MAP_CHANGED","map_id":%d}\n',
        map
    )

    sendEvent(message)
end

local function getBattleState(value)
    if value == 0 then
        return "OVERWORLD"
    elseif value == 1 then
        return "WILD_BATTLE"
    elseif value == 2 then
        return "TRAINER_BATTLE"
    elseif value == 255 then
        return "LOST_BATTLE"
    end

    return "UNKNOWN"
end

local function sendBattleChanged(value, map, result)
    local state = getBattleState(value)

    local message = string.format(
        '{"event":"BATTLE_CHANGED","state":"%s","value":%d,"map_id":%d,"battle_result":%d}\n',
        state,
        value,
        map,
        result
    )

    sendEvent(message)
end

local function sendMusicChanged(musicId)
    local message = string.format(
        '{"event":"MUSIC_CHANGED","music_id":%d}\n',
        musicId
    )

    sendEvent(message)
end

-- A savestate load (or rewind/reset) restores mGBA's frame counter, so the
-- frame number jumps instead of advancing by one. Resync the controller then.
local function sendStateLoaded()
    local battle = emu:read8(ADDRESSES.isInBattle)
    local map = emu:read8(ADDRESSES.curMap)
    local result = emu:read8(ADDRESSES.battleResult)

    previous.isInBattle = battle
    previous.curMap = map
    previous.battleResult = result
    previous.channelKey = nil
    previous.victoryDetected = false
    previous.trainerSpriteOffset = emu:read8(ADDRESSES.trainerSpriteOffset)
    trainerIntroFramesLeft = 0

    console:log("[OST] State loaded, resyncing music")

    sendEvent(string.format(
        '{"event":"STATE_LOADED","map_id":%d,"state":"%s","value":%d,"battle_result":%d}\n',
        map,
        getBattleState(battle),
        battle,
        result
    ))
end

--------------------------------------------------
-- INITIAL GAME STATE
--------------------------------------------------

local initialBattle = emu:read8(ADDRESSES.isInBattle)
local initialMap = emu:read8(ADDRESSES.curMap)

previous.isInBattle = initialBattle
previous.curMap = initialMap

sendMapChanged(initialMap)
local initialResult = emu:read8(ADDRESSES.battleResult)
previous.battleResult = initialResult

sendBattleChanged(initialBattle, initialMap, initialResult)

previous.frame = emu:currentFrame()

--------------------------------------------------
-- GAME STATE MONITORING
--------------------------------------------------

console:log("[OST] Game-state monitoring started")

callbacks:add("frame", function()
    framesSinceHeartbeat = framesSinceHeartbeat + 1

    if framesSinceHeartbeat >= HEARTBEAT_FRAMES then
        sendEvent('{"event":"HEARTBEAT"}\n')
        framesSinceHeartbeat = 0
    end

    local frame = emu:currentFrame()
    local stateLoaded = previous.frame ~= nil and frame ~= previous.frame + 1
    previous.frame = frame

    if stateLoaded then
        sendStateLoaded()
        return
    end

    local battle = emu:read8(ADDRESSES.isInBattle)
    local map = emu:read8(ADDRESSES.curMap)

    -- Detect map changes
    if map ~= previous.curMap then
        sendMapChanged(map)
        previous.curMap = map
    end

    -- Detect battle transitions
    if battle ~= previous.isInBattle then
        local result = emu:read8(ADDRESSES.battleResult)
        sendBattleChanged(battle, map, result)
        previous.isInBattle = battle
    end

    -- Detect victory music from the first three music channels
    local channels = {}
    for i = 0, 2 do
        channels[i + 1] = emu:read8(ADDRESSES.channelSoundIDs + i)
    end

    local channelKey = table.concat(channels, ",")

    if channelKey ~= previous.channelKey then
        local victoryType = nil

        if channels[1] == channels[2] and channels[2] == channels[3] then
            if channels[1] == 249 then
                victoryType = "WILD_BATTLE"
            elseif channels[1] == 246 then
                victoryType = "TRAINER_BATTLE"
            elseif channels[1] == 252 then
                victoryType = "GYM_LEADER_BATTLE"
            end
        end

        if victoryType and not previous.victoryDetected then
            console:log("[VICTORY] " .. victoryType)

            sendEvent(string.format(
                '{"event":"VICTORY_STARTED","victory_type":"%s"}\n',
                victoryType
            ))

            previous.victoryDetected = true
        elseif not victoryType then
            previous.victoryDetected = false
        end

        previous.channelKey = channelKey
    end

    local trainerOffset = emu:read8(ADDRESSES.trainerSpriteOffset)

    if trainerOffset == 255 and previous.trainerSpriteOffset ~= 255 then
        console:log("[TRAINER] Trainer spotted!")
        trainerIntroFramesLeft = TRAINER_INTRO_WINDOW
    end

    previous.trainerSpriteOffset = trainerOffset

    -- Wait for the game to start a trainer intro song, then report which one.
    if trainerIntroFramesLeft > 0 then
        trainerIntroFramesLeft = trainerIntroFramesLeft - 1

        local intro = nil

        if battle == 0 and channels[1] == channels[2] and channels[2] == channels[3] then
            intro = TRAINER_INTRO_SONGS[channels[1]]
        end

        if intro then
            console:log("[TRAINER] Trainer intro music: " .. intro)

            sendEvent(string.format(
                '{"event":"TRAINER_SPOTTED","trainer_music":"%s"}\n',
                intro
            ))

            trainerIntroFramesLeft = 0
        elseif battle ~= 0 or trainerIntroFramesLeft == 0 then
            console:log("[TRAINER] No trainer intro music started; keeping current music")
            trainerIntroFramesLeft = 0
        end
    end
end)