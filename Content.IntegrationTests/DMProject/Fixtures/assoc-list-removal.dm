/proc/assoc_list_remove_owned_route(alist/target, key, route)
    switch(route)
        if("remove")
            return target.Remove(key)
        if("remove-all")
            return target.RemoveAll(key)
        if("remove-op")
            target -= key
            return target
        if("subtract")
            return target - key
        if("mask")
            target &= list("keep")
            return target
    CRASH("Unknown associative list removal fixture route")
