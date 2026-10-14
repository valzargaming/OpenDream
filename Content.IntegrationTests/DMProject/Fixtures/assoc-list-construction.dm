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