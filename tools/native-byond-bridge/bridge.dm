// Standalone client-local native observation prototype. Never include in the game DME.
// A launcher-owned temporary directory supplies bridge-request.json; no passwords or secrets.
#define TRUE 1
#define FALSE 0
var/list/bridge_request
var/bridge_claimed = FALSE

/world
    name = "Native BYOND identity observation"
    hub = ""
    maxx = 1
    maxy = 1
    maxz = 1
    fps = 10

/world/New()
    ..()
    fdel("native-report.json")
    var/request_text = file2text("bridge-request.json")
    if (!istext(request_text) || length(request_text) > 8192)
        del(world)
        return
    try
        bridge_request = json_decode(request_text)
    catch
        del(world)
        return
    if (!islist(bridge_request) || !bridge_hex(bridge_request["nonce"]) || !istext(bridge_request["epoch"]) || length(bridge_request["epoch"]) != 36)
        del(world)
        return
    // This is a finite observation world, not a background daemon or game session.
    spawn(600)
        del(world)
        return

/client/New(TopicData)
    // Observe actual read-only native client fields, never a volume serial or account hash.
    if (address != "127.0.0.1" && address != "::1")
        return null
    var/list/topic_fields = params2list(TopicData)
    if (!bridge_request || bridge_claimed || !islist(topic_fields) || topic_fields.len != 1 || topic_fields["nonce"] != bridge_request["nonce"])
        return null
    if (!istext(key) || !length(key) || !length(ckey) || bridge_guest(key) || !bridge_digits(computer_id))
        return null
    bridge_claimed = TRUE
    var/list/report = list("epoch" = bridge_request["epoch"], "nonce" = bridge_request["nonce"], "key" = key, "cid" = computer_id)
    // Client-owned report: deliberately no server-attestation or anti-spoofing claim.
    if (!text2file(json_encode(report), "native-report.json"))
        bridge_claimed = FALSE
    return null

/proc/bridge_digits(value)
    if (!istext(value) || length(value) < 1 || length(value) > 32)
        return FALSE
    for (var/index = 1, index <= length(value), index++)
        var/character = text2ascii(value, index)
        if (character < 48 || character > 57)
            return FALSE
    return TRUE

/proc/bridge_hex(value)
    if (!istext(value) || length(value) != 64)
        return FALSE
    for (var/index = 1, index <= length(value), index++)
        var/character = text2ascii(value, index)
        if (!(character >= 48 && character <= 57) && !(character >= 65 && character <= 70))
            return FALSE
    return TRUE

/proc/bridge_guest(value)
    // BYOND author documents Guest-[digits]; native pinned-version parity remains required.
    return copytext(value, 1, 7) == "Guest-" && bridge_digits(copytext(value, 7))
