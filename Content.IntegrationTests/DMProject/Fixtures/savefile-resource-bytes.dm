/proc/savefile_resource_reads(path, count)
    var/savefile/F = new("payload.sav")
    F["payload"] << file(path)
    var/list/results = list()
    for(var/i = 1, i <= count, i++)
        results += F["payload"]
    del(F)
    return results

/proc/savefile_resource_identity(a, b)
    // Keeping distinct resource objects preserves both equality and refs.
    return list(a == b, "\ref[a]", "\ref[b]", locate("\ref[a]") == a, locate("\ref[b]") == b)

/proc/savefile_resource_drop(path)
    var/savefile/F = new("payload.sav")
    for(var/i = 1, i <= 1000, i++)
        var/value = F["payload"]
        value = null
    del(F)
    return 17
