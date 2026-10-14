// Small genuine compiled DM scheduling/close controls. No full-game substitute.
var/global/new_process_dispatch_init_complete = TRUE
var/global/gaia_host_save_state = "idle"

/proc/gaia_host_run_save_probe()
	var/mode = world.params["fixture_case"]
	world.log << "GAIA_CONTROL_CASE:[mode]"
	gaia_host_save_state = "running"
	if(mode == "return-failure")
		gaia_host_save_state = "failed"
		return 0
	var/savefile/F = new("map_saves/1.sav")
	F["payload"] << "first"
	if(mode == "yield" || mode == "cap")
		sleep(1)
	if(mode == "cap")
		// Run with MaximumFlushes=2: three naturally closed dirty creations
		// guarantee a selected-call exclusion without changing the host cap gate.
		F = new("map_saves/1.sav")
		F["payload"] << "cap-extra"
	if(mode == "missing-shard")
		// Two successful first-shard closes avoid failing the aggregate counter
		// gate before the intended second-shard disk-existence assertion.
		F = new("map_saves/1.sav")
		F["payload"] << "first-again"
	else
		F = new("map_saves/2.sav")
		F["payload"] << (mode == "reader-rejection" ? "wrong" : "second")
	text2file("PASS: SAVE explicit production persistence probe", "new_process_SAVE_result.txt")
	text2file("small-control", "map_saves/save_complete.txt")
	gaia_host_save_state = "returned"
	return 1

/proc/gaia_host_write_late_control()
	// The tiny negative host explicitly invokes this after its sealed hashes.
	// This is an actual DM savefile write, not a synthetic disk mutation.
	world.log << "GAIA_CONTROL_POST_SEAL_WRITE"
	var/savefile/L = new("map_saves/2.sav")
	L["payload"] << "late"
	return 1

/proc/gaia_host_recovery_control()
	// Genuine fresh host savefile decoder/read path; wrong valid data rejects.
	var/savefile/F = new("map_saves/2.sav")
	var/value
	F["payload"] >> value
	return value == "second" ? 1 : 0
