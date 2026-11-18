-- Pokemon Adaptive OST
-- Lua -> Python communication

local ADDRESSES = {
    isInBattle = 0xD05B,
    curMap = 0xD362,
    battleResult = 0xCF0B,
    channelSoundIDs = 0xC026,
    audioROMBank = 0xC0EF,
    trainerSpriteOffset = 0xCD3D
}

local HOST = "127.0.0.1"
local PORT = 8765

local previous = {
    isInBattle = nil,
    curMap = nil,
    battleResult = nil,
    channelKey = nil,
    sfxId = nil,
    trainerSpriteOffset = nil,
    frame = nil
}

-- Sent every HEARTBEAT_FRAMES frames. Frames stop while mGBA is paused (also when
-- it pauses in the background), so the controller pauses the music when they stop.
local HEARTBEAT_FRAMES = 10
local framesSinceHeartbeat = 0

-- Song detection: the script only reports the song id the game starts
-- (MUSIC_CHANGED) and the sound effect on channel 4 (SFX_CHANGED, with the audio
-- bank). The controller maps ids to tracks, because ids are bank-relative and
-- need context (map, battle, trainer spotted) to be read.

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

local function sendSfxChanged(soundId, bank)
    local message = string.format(
        '{"event":"SFX_CHANGED","sound_id":%d,"bank":%d}\n',
        soundId,
        bank
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
    previous.sfxId = nil
    previous.trainerSpriteOffset = emu:read8(ADDRESSES.trainerSpriteOffset)

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

    -- Report each new song. Every song uses music channels 0 and 1, and the audio
    -- engine writes the song id to each channel it uses, so the same new id on
    -- both means the game started that song. Channels 4-7 are sound effects.
    local ch0 = emu:read8(ADDRESSES.channelSoundIDs)
    local ch1 = emu:read8(ADDRESSES.channelSoundIDs + 1)
    local channelKey = ch0 .. "," .. ch1

    if channelKey ~= previous.channelKey then
        previous.channelKey = channelKey

        if ch0 == ch1 and ch0 ~= 0 then
            sendMusicChanged(ch0)
        end
    end

    -- Report the sound effect on channel 4 (the first sound-effect channel; every
    -- fanfare starts there). The engine sets it to 0 when the sound ends.
    local sfx = emu:read8(ADDRESSES.channelSoundIDs + 4)

    if sfx ~= previous.sfxId then
        previous.sfxId = sfx
        sendSfxChanged(sfx, emu:read8(ADDRESSES.audioROMBank))
    end

    local trainerOffset = emu:read8(ADDRESSES.trainerSpriteOffset)

    if trainerOffset == 255 and previous.trainerSpriteOffset ~= 255 then
        console:log("[TRAINER] Trainer spotted!")

        sendEvent('{"event":"TRAINER_SPOTTED"}\n')
    end

    previous.trainerSpriteOffset = trainerOffset
end)