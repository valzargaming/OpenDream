"""Suspended-root client/inert containment; never attach existing processes.

Windows interop and inventory adapted from the separately owned memory audit.
This module is not a launch authorization. Native layout remains a client gate.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

class MemoryStatus(C.Structure):
    _fields_ = [('length', W.DWORD), ('load', W.DWORD)] + [(n, C.c_ulonglong) for n in
                ('total', 'available', 'page_total', 'page_available', 'virtual_total', 'virtual_available', 'extended')]

class Counters(C.Structure):
    _fields_ = [('size', W.DWORD), ('faults', W.DWORD)] + [(n, C.c_size_t) for n in
                ('peak_working', 'working', 'peak_paged', 'paged', 'peak_nonpaged', 'nonpaged', 'page', 'peak_page', 'private')]

class BasicLimits(C.Structure):
    _fields_ = [('process_time', C.c_longlong), ('job_time', C.c_longlong), ('flags', W.DWORD),
                ('min_working', C.c_size_t), ('max_working', C.c_size_t), ('active', W.DWORD),
                ('affinity', C.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]

class IoCounters(C.Structure):
    _fields_ = [(n, C.c_ulonglong) for n in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]

class ExtendedLimits(C.Structure):
    _fields_ = [('basic', BasicLimits), ('io', IoCounters)] + [(n, C.c_size_t) for n in
                ('process_memory', 'job_memory', 'peak_process', 'peak_job')]

class JobPids(C.Structure):
    _fields_ = [('assigned', W.DWORD), ('count', W.DWORD), ('pids', C.c_size_t * 512)]

k = C.WinDLL('kernel32', use_last_error=True)
p = C.WinDLL('psapi', use_last_error=True)
for name, args, result in (
    ('CreateJobObjectW', [W.LPVOID, W.LPCWSTR], W.HANDLE),
    ('OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
    ('CloseHandle', [W.HANDLE], W.BOOL),
    ('SetInformationJobObject', [W.HANDLE, C.c_int, W.LPVOID, W.DWORD], W.BOOL),
    ('AssignProcessToJobObject', [W.HANDLE, W.HANDLE], W.BOOL),
    ('QueryInformationJobObject', [W.HANDLE, C.c_int, W.LPVOID, W.DWORD, W.LPVOID], W.BOOL),
    ('TerminateJobObject', [W.HANDLE, W.UINT], W.BOOL),
    ('GlobalMemoryStatusEx', [C.POINTER(MemoryStatus)], W.BOOL),
):
    function = getattr(k, name)
    function.argtypes, function.restype = args, result
p.GetProcessMemoryInfo.argtypes = [W.HANDLE, C.POINTER(Counters), W.DWORD]
p.GetProcessMemoryInfo.restype = W.BOOL

def utc():
    return datetime.now(timezone.utc).isoformat()

def free_bytes():
    value = MemoryStatus()
    value.length = C.sizeof(value)
    if not k.GlobalMemoryStatusEx(C.byref(value)):
        raise OSError(C.get_last_error())
    return value.available

def pids(job):
    value = JobPids()
    if not k.QueryInformationJobObject(job, 3, C.byref(value), C.sizeof(value), None):
        raise OSError(C.get_last_error())
    if value.assigned > 512 or value.count > 512:
        raise RuntimeError('Owned process inventory exceeded bound')
    return list(value.pids[:value.count])

def private(pid):
    handle = k.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        value = Counters()
        value.size = C.sizeof(value)
        return value.private if p.GetProcessMemoryInfo(handle, C.byref(value), C.sizeof(value)) else None
    finally:
        k.CloseHandle(handle)

class StartupInfo(C.Structure):
    _fields_ = [('cb', W.DWORD), ('reserved', W.LPWSTR), ('desktop', W.LPWSTR),
                ('title', W.LPWSTR)] + [(name, W.DWORD) for name in
                ('x', 'y', 'width', 'height', 'chars_x', 'chars_y', 'fill', 'flags')] + [
                ('show', W.WORD), ('reserved_bytes', W.WORD), ('reserved_ptr', W.LPBYTE),
                ('stdin', W.HANDLE), ('stdout', W.HANDLE), ('stderr', W.HANDLE)]

class ProcessInfo(C.Structure):
    _fields_ = [('process', W.HANDLE), ('thread', W.HANDLE), ('pid', W.DWORD), ('tid', W.DWORD)]

k.CreateProcessW.argtypes = [W.LPCWSTR, W.LPWSTR, W.LPVOID, W.LPVOID, W.BOOL,
                            W.DWORD, W.LPVOID, W.LPCWSTR, C.POINTER(StartupInfo), C.POINTER(ProcessInfo)]
k.CreateProcessW.restype = W.BOOL
k.ResumeThread.argtypes, k.ResumeThread.restype = [W.HANDLE], W.DWORD
k.TerminateProcess.argtypes, k.TerminateProcess.restype = [W.HANDLE, W.UINT], W.BOOL
k.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
k.GetExitCodeProcess.restype = W.BOOL
k.WaitForSingleObject.argtypes, k.WaitForSingleObject.restype = [W.HANDLE, W.DWORD], W.DWORD

def selector(value):
    if not value or not value.strip() or any(ch in value for ch in ('\0', '\r', '\n')):
        raise ValueError('A private explicit expected username is required')
    return value

def redacted_arguments(arguments, expected_username):
    return ['+launchauth <private-expected-username>' if item.startswith('+launchauth')
            else '<private-expected-username>' if item == expected_username else item for item in arguments]

def stop_reason(elapsed, timeout, total, cap, available, floor, unknown):
    if elapsed >= timeout:
        return 'deadline'
    if total > cap:
        return 'owned-private-cap'
    if available < floor:
        return 'host-free-floor'
    if unknown:
        return 'unmeasured-owned-process'
    return None

def run_owned(command, output, *, timeout, cap, floor, preflight, env=None,
              inert_control=None, redacted_command=None):
    """Only a fresh suspended process is assigned; job breakaway flags stay absent."""
    if not 0 < timeout <= 180 or cap > 1024**3 or floor < 6*1024**3:
        raise ValueError('Client resource/deadline limits exceeded')
    output = Path(output).resolve()
    if output.exists() or free_bytes() < preflight:
        raise RuntimeError('Unique output and sufficient fresh host memory required')
    if inert_control and Path(command[0]).resolve() != Path(sys.executable).resolve():
        raise ValueError('Injected controls are restricted to inert Python tests')
    output.mkdir()
    job = k.CreateJobObjectW(None, None)
    if not job:
        raise OSError(C.get_last_error())
    limits = ExtendedLimits()
    limits.basic.flags = 0x2200  # KILL_ON_JOB_CLOSE | JOB_MEMORY; NO breakaway permission
    limits.job_memory = cap-32*1024**2  # reserve guard private memory inside the aggregate budget
    info = ProcessInfo()
    reason, cleanup_error, assigned, resumed = None, None, False, False
    seen, peak, lowest, child_handles = set(), 0, free_bytes(), {}
    start, started = time.monotonic(), utc()
    try:
        if not k.SetInformationJobObject(job, 9, C.byref(limits), C.sizeof(limits)):
            raise OSError(C.get_last_error())
        startup = StartupInfo()
        startup.cb, startup.flags, startup.show = C.sizeof(startup), 1, 0  # hidden console
        cmdline = C.create_unicode_buffer(subprocess.list2cmdline(command))
        environment = None
        if env is not None:
            environment = C.create_unicode_buffer('\0'.join(k+'='+v for k,v in sorted(env.items(), key=lambda item:item[0].upper()))+'\0\0')
        if not k.CreateProcessW(command[0], cmdline, None, None, False,
                                0x08000404, environment, str(output), C.byref(startup), C.byref(info)):
            raise OSError(C.get_last_error(), 'Fresh suspended root creation failed')
        if inert_control == 'assignment' or not k.AssignProcessToJobObject(job, info.process):
            raise OSError(C.get_last_error(), 'Suspended root assignment failed')
        assigned = True
        if info.pid not in pids(job):
            raise RuntimeError('Root Job membership was not verified before resume')
        if k.ResumeThread(info.thread) == 0xffffffff:
            raise OSError(C.get_last_error(), 'Root resume failed')
        resumed = True
        with (output/'resource-trace.jsonl').open('w') as trace:
            while True:
                inventory = pids(job)
                seen.update(inventory)
                for pid in inventory:
                    if pid != info.pid and pid not in child_handles:
                        handle = k.OpenProcess(0x00101000,False,pid)
                        if handle:
                            child_handles[pid] = handle
                values = {pid: private(pid) for pid in inventory}
                fresh = set(pids(job))
                unknown = [pid for pid,value in values.items() if value is None and pid in fresh]
                watcher = private(os.getpid())
                if watcher is None:
                    unknown.append(os.getpid())
                total = sum(value for value in values.values() if value is not None)+(watcher or 0)
                available, elapsed = free_bytes(), time.monotonic()-start
                peak, lowest = max(peak,total), min(lowest,available)
                decision_total = cap+1 if inert_control == 'private' else total
                decision_free = floor-1 if inert_control == 'floor' else available
                decision_unknown = [info.pid] if inert_control == 'unknown' else unknown
                reason = stop_reason(elapsed,timeout,decision_total,cap,decision_free,floor,decision_unknown)
                trace.write(json.dumps({'utc':utc(),'owned_pids':inventory,'owned_private':total,
                                        'host_free':available,'unmeasured_pids':unknown})+'\n')
                trace.flush()
                if reason:
                    break
                exitcode = W.DWORD()
                if not k.GetExitCodeProcess(info.process,C.byref(exitcode)):
                    raise OSError(C.get_last_error())
                if exitcode.value != 259:
                    reason = 'descendants-survived-root' if inventory else None
                    break
                time.sleep(0.1)
    except Exception as error:
        # Never include command/env/identity in diagnostic exception receipts.
        reason = 'guard-error:'+type(error).__name__
    finally:
        errors, remaining = [], []
        cleanup_end = min(start+timeout+30,time.monotonic()+30)
        try:
            if assigned:
                if not k.TerminateJobObject(job,137):
                    errors.append('TerminateJobObject failed')
            elif info.process and not k.TerminateProcess(info.process,137):
                errors.append('TerminateProcess failed for fresh suspended root')
            if inert_control == 'cleanup-query':
                raise OSError('Injected cleanup inventory failure')
            while assigned and pids(job) and time.monotonic() < cleanup_end:
                time.sleep(0.1)
            if assigned:
                remaining = pids(job)
                if remaining:
                    errors.append('Job inventory remains')
        except Exception as error:
            errors.append('cleanup-query:'+type(error).__name__)
        finally:
            # Kill-on-close remains unconditional even if termination/inventory fails.
            if not k.CloseHandle(job):
                errors.append('CloseHandle(job) failed')
            try:
                handles = {info.pid:info.process} if info.process else {}
                handles.update(child_handles)
                remaining = []
                for pid,handle in handles.items():
                    milliseconds = max(0,int((cleanup_end-time.monotonic())*1000))
                    if k.WaitForSingleObject(handle,milliseconds) != 0:
                        remaining.append(pid)
                if remaining:
                    errors.append('Owned process exit not confirmed')
            finally:
                for handle in (info.thread,info.process,*child_handles.values()):
                    if handle and not k.CloseHandle(handle):
                        errors.append('CloseHandle(process/thread) failed')
        cleanup_error = '; '.join(errors) or None
    receipt = {'started_utc':started,'ended_utc':utc(),'elapsed_including_cleanup':time.monotonic()-start,
               'owned_root_pid':info.pid,'owned_pids_seen':sorted(seen),'remaining_owned_pids':remaining,
               'assigned_before_resume':assigned and resumed,'stop_reason':reason,'cleanup_error':cleanup_error,
               'root_resumed':resumed,'held_process_exit_confirmed':not remaining,
               'all_owned_exit_confirmed':not remaining and cleanup_error is None,
               'peak_owned_private_including_watcher':peak,'lowest_host_free':lowest,
               'job_commit_cap':limits.job_memory,'combined_owned_cap':cap,
               'watcher_reserve_bytes':32*1024**2,'host_free_floor':floor,
               'job_breakaway_allowed':False,'execution_limit':timeout,'cleanup_limit':30,
               'command':redacted_command or ['<inert-owned-test>'],
               'baseline_processes_attached':False,'candidate_launched':inert_control is None and cap==1024**3}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2))
    return receipt

