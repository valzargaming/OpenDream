# Savefile failure cleanup regression

This package-free fixture compiles the actual savefile `Initialize`, `Close`,
`Flush`, and deletion bodies, the base object's refcount/deletion bodies, and the
complete production reference bucket. Type/proc integration, resource loading,
and JSON leaf conversion use explicit inert adapters. Disk writes are confined
to a unique temporary directory, including temporary savefiles.

It checks repeated null-resource and malformed-input disposal, child-variable
release, empty reference/open/dirty/cache registries, CLR weak-reference
collection, normal shared-file contents, survival of the remaining shared
handle, missing-file behavior, temporary-file cleanup, and write exceptions.
Flush errors must propagate while all closed-handle registrations are removed.
The malformed input must retain its original disk bytes.

Run with an absolute .NET 10 SDK path:

```sh
python tests/savefile_cleanup/run.py --dotnet /absolute/path/to/dotnet --output /temporary/receipts --work /temporary/work --all-controls
```

The controls require precise runtime assertion failures, never compilation
failure: fork baseline `ac6fc2f065734a56c47c4e8ec8e78f70f29727c7`, omitted base
cleanup, old close detachment (with a null guard to isolate write failure), and
omitted final directory eviction. Logs and receipts bind the checkout and
fixture sources. They do not establish complete-interpreter behavior, native
client acceptance, gameplay performance, or a cause of Gaia's memory growth.

On the shared Windows investigation host, use `guard-windows.py` only with the
runtime owner's fresh resource grant. It gates its child before execution,
uses a kill-on-close job with a hard 2 GiB aggregate commit limit, and samples
the 6 GiB host free-memory floor through `GlobalMemoryStatusEx`. It stops on
unmeasured children, floor/cap violations, or deadline and records cleanup.
