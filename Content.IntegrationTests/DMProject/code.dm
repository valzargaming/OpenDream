//Setup code - put whatever you need for testing here.
/proc/exception_discard_probe(payload)
	try
		throw payload
	catch
		return 1

/proc/exception_bound_probe(payload)
	try
		throw payload
	catch(var/caught)
		return caught

/proc/exception_nested_probe(payload)
	try
		try
			throw payload
		catch(var/caught)
			if(caught != payload)
				CRASH("Nested catch changed thrown value")
			throw caught
	catch(var/rethrown)
		return rethrown

/proc/exception_uncaught_probe(payload)
	exception_ownership_expected_payload = payload
	throw payload

var/global/exception_ownership_expected_payload
/world/Error(exception/error)
	if(exception_ownership_expected_payload)
		var/matched = (error.name == exception_ownership_expected_payload)
		exception_ownership_expected_payload = null
		if(!matched)
			CRASH("Uncaught exception changed thrown payload")
		// The engine test harness fails on error-level logs. Only this expected
		// throw is consumed; unrelated runtime errors still use the native path.
		return
	return ..()

/proc/spawn_pool_reuse_probe(count, datum/payload)
	var/datum/captured = payload
	var/list/completed = list(0)
	. = payload
	for(var/i in 1 to count)
		spawn(-1)
			if(src != world || usr != payload || captured != payload || . != payload)
				CRASH("Spawn did not preserve src, usr, arguments, locals or return value")
			. = captured
			completed[1]++
	return completed[1]

/proc/native_argument_failure_probe(payload)
	try
		clamp(payload, 0, 1)
	catch(var/exception/error)
		if(error.name != "Clamp expects a number or list")
			throw error
		return 1
	return 0

/proc/native_argument_rethrow_probe(payload)
	try
		try
			clamp(payload, 0, 1)
		catch(var/exception/error)
			throw error
	catch(var/exception/error)
		if(error.name != "Clamp expects a number or list")
			throw error
		return 1
	return 0

/proc/native_argument_success_probe(payload)
	return !isnull(payload)

/proc/cancellation_depth_probe(payload)
	var/local_payload = payload
	. = payload
	cancellation_depth_probe(local_payload)

/datum/cancellation_operator/proc/operator+(payload)
	var/local_payload = payload
	. = payload
	return src + local_payload

/proc/cancellation_operator_probe(datum/cancellation_operator/operator_owner, payload)
	return operator_owner + payload

/turf
/turf/border
/mob/test

var/global/list/areas_by_type = list()
/area/New()
	areas_by_type[type] = src
	

//The actual tests
//NOTE: Tests placed in the IntegrationTests suite
// should actually require a normal server in order to work.
// Tests that only check generic DM behaviour that is not icon nor map-facing
// should be done within Content.Tests.
// ALSO NOTE: If you're getting strange results, try rebuilding to make sure this DM file is copied correctly.

//Basic sanity check that the map actually loads correctly.
/proc/test_world_init()
	var/a = 0
	var/b = 0
	for(var/turf/t in world)
		if(istype(t,/turf/border))
			b += 1
		else
			a += 1
	if(a + b != 75)
		CRASH("Map probably failed to load; expected 75 tiles in the map, instead found [a + b].")

/datum/unit_test/proc/RunTest()
	throw EXCEPTION("You must override RunTest()")

/world/New()
	// prepare areas
	for(var/area_subtype in typesof(/area) - /area)
		new area_subtype()
	for(var/subtype in typesof(/datum/unit_test))
		if(subtype == /datum/unit_test) //skip the base class
			continue
		var/datum/unit_test/TEST = new subtype()
		TEST.RunTest()
		del(TEST) //and clean up
	world.log << "IntegrationTests successful, /world/New() exiting..."
/proc/async_return_ownership_probe(payload)
	return payload

/proc/arglist_first_owner_probe(first)
	return first

/proc/arglist_second_owner_probe(first, second)
	return second

/proc/arglist_failure_owner_probe(payload, named_first)
	var/list/arguments
	if(named_first)
		arguments = list(first = payload, unknown_argument = payload)
	else
		arguments = list(payload, unknown_argument = payload)
	try
		arglist_first_owner_probe(arglist(arguments))
	catch(var/exception/error)
		if(error.name != "/proc/arglist_first_owner_probe has no argument named \"unknown_argument\"")
			throw error
		return 1
	return 0

/proc/arglist_overwrite_owner_probe(original, replacement, named_first)
	if(named_first)
		return arglist_second_owner_probe(arglist(list(second = original, replacement)))
	return arglist_first_owner_probe(arglist(list(original, first = replacement)))

/proc/proc_initialization_boundary_probe(first)
	return args.len

/proc/proc_initialization_null_probe(first)

/proc/proc_initialization_locals_probe(first)
	var/local_payload = first
	return args.len + (local_payload == first ? 0 : 1)

/proc/proc_initialization_arglist_probe(payload, native)
	var/list/arguments = new/list(native ? 129 : 257)
	arguments[1] = payload
	try
		if(native)
			sleep(arglist(arguments))
		else
			proc_initialization_boundary_probe(arglist(arguments))
	catch(var/exception/error)
		if(native)
			return error.name == "Destination is too short. (Parameter 'destination')"
		return error.name == "Index was outside the bounds of the array."
	return 0
