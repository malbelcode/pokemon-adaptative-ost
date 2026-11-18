local variables = {
    { name = "wIsInBattle", address = 0xD05B },
    { name = "wCurOpponent", address = 0xD05D },
    { name = "wBattleType", address = 0xD05E },
    { name = "wCurMap", address = 0xD362 }
}

console:log("=== Pokemon Yellow Spanish RAM diagnostic ===")

for _, variable in ipairs(variables) do
    local value = emu:read8(variable.address)

    console:log(string.format(
        "%s = 0x%02X (%d)",
        variable.name,
        value,
        value
    ))
end