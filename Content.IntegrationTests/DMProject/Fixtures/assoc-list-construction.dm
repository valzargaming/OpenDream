// Isolated integration fixture. Not part of the ordinary NoRuntimes DMProject.
/proc/assoc_construct_reject_caught(bad, position, key, p, q, r)
    var/list/target
    try
        switch(position)
            if("first")
                target = list((bad) = p, (key) = q, "tail" = r)
            if("middle")
                target = list((key) = p, (bad) = q, "tail" = r)
            if("last")
                target = list((key) = p, "middle" = q, (bad) = r)
        return target
    catch
        // Same DMProcState resumes and pushes a return over the popped operand span.
        return 17
    return -1

/proc/assoc_construct_reject_uncaught(bad, position, key, p, q, r)
    switch(position)
        if("first")
            return list((bad) = p, (key) = q, "tail" = r)
        if("middle")
            return list((key) = p, (bad) = q, "tail" = r)
        if("last")
            return list((key) = p, "middle" = q, (bad) = r)
    return -1

/proc/assoc_construct_reject_unwind(bad, position, key, p, q, r)
    try
        return assoc_construct_reject_uncaught(bad, position, key, p, q, r)
    catch
        // The callee unwinds and disposes its frame before this caller resumes.
        return 17
    return -1

/proc/assoc_construct_reuse(payload)
    return payload

/proc/assoc_construct_success(route, key, p, q, r)
    switch(route)
        if("mixed")
            return list(p, (key) = q, "tail" = r)
        if("null")
            return list((null) = p, (key) = q, (null) = r)
        if("repeat")
            return list((key) = p, (key) = q, (key) = r)
        if("numeric")
            var/one = 1
            var/two = 2
            var/three = 3
            return list((one) = p, (two) = q, (three) = r)
        if("empty")
            return list()
    return -1
// Temporary operands have no caller/global object owners. Record only strings.
var/global/assoc_timing_events = ""

/datum/assoc_timing_callback
    var/release_timing_tag

/datum/assoc_timing_callback/New(name)
    release_timing_tag = name

/datum/assoc_timing_callback/Del()
    assoc_timing_events += release_timing_tag
    ..()

/proc/assoc_construct_release_timing(list_payload)
    assoc_timing_events = ""
    var/list/result
    if(list_payload)
        // Deleting each temporary list releases its sole-owned callback child.
        result = list("a" = list(new /datum/assoc_timing_callback("A")), "b" = list(new /datum/assoc_timing_callback("B")), "b" = null, "a" = null)
    else
        result = list("a" = new /datum/assoc_timing_callback("A"), "b" = new /datum/assoc_timing_callback("B"), "b" = null, "a" = null)
    if(result.len != 2 || result["a"] != null || result["b"] != null)
        return "wrong-shape"
    return assoc_timing_events
